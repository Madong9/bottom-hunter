"""RainGlassDemo launcher — PHASE 1 independent GPU visual prototype.

Runs the QML demo with a Bridge QObject that provides diagnostics data
(Qt version, RHI backend, FPS) and quality-preset switching.

Usage:
    .venv/bin/python -m bottom_hunter.ui_demo.demo_launcher
    .venv/bin/python -m bottom_hunter.ui_demo.demo_launcher --quality high
    QSG_RHI_BACKEND=opengl .venv/bin/python -m bottom_hunter.ui_demo.demo_launcher
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

DEMO_DIR = Path(__file__).resolve().parent


class Bridge(QObject):
    """Diagnostics + quality bridge (read-only view state; no business logic)."""

    fpsChanged = Signal()
    frameMsChanged = Signal()
    qualityChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fps = 0.0
        self._frame_ms = 0.0
        self._quality = os.environ.get("RAINGLASS_QUALITY", "balanced")
        self._frames = 0
        self._window_start = time.perf_counter()
        self._sample_timer = QTimer(self)
        self._sample_timer.setInterval(1000)
        self._sample_timer.timeout.connect(self._sample)
        self._sample_timer.start()

    # ---- diagnostics (MASTER_PROMPT §14) --------------------------------

    @Property(str, constant=True)
    def qtVersion(self) -> str:  # noqa: N802 (QML property name)
        import PySide6

        return PySide6.__version__

    @Property(float, notify=fpsChanged)
    def fps(self) -> float:
        return self._fps

    @Property(float, notify=frameMsChanged)
    def frameMs(self) -> float:  # noqa: N802
        return self._frame_ms

    @Property(bool, constant=True)
    def diagnosticsVisible(self) -> bool:
        return os.environ.get("RAINGLASS_DIAGNOSTICS") == "1"

    @Slot(result=str)
    def rhiBackendName(self) -> str:
        # Qt RHI backend via QSG_RENDERER_API env or scene-graph log; report
        # what was requested, never fabricate the actual adapter name.
        requested = os.environ.get("QSG_RHI_BACKEND", "auto")
        return requested

    def _sample(self) -> None:
        now = time.perf_counter()
        elapsed = now - self._window_start
        # The scene graph renders on demand; approximate FPS from the
        # animation driver (u_time NumberAnimation drives continuous repaint).
        self._fps = min(60.0, self._frames * (1.0 / max(elapsed, 1e-3)))
        self._frame_ms = 1000.0 / self._fps if self._fps > 0 else 0.0
        self._window_start = now
        self._frames = 0
        self.fpsChanged.emit()
        self.frameMsChanged.emit()

    def note_frame(self) -> None:
        self._frames += 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RainGlass GPU UI demo")
    parser.add_argument(
        "--quality",
        choices=("high", "balanced", "low"),
        default=os.environ.get("RAINGLASS_QUALITY", "balanced"),
        help="quality preset (default: balanced; Low disables rain shader)",
    )
    parser.add_argument(
        "--diagnostics", action="store_true", help="show the diagnostics overlay"
    )
    parser.add_argument(
        "--software", action="store_true",
        help="force QSG_RHI_BACKEND=software (CI / no-GPU fallback)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.diagnostics:
        os.environ["RAINGLASS_DIAGNOSTICS"] = "1"
    if args.software:
        os.environ["QSG_RHI_BACKEND"] = "software"

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("RainGlass Demo")

    engine = QQmlApplicationEngine()
    bridge = Bridge()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.rootContext().setContextProperty("initialQuality", args.quality)

    engine.addImportPath(str(DEMO_DIR))
    engine.load(str(DEMO_DIR / "DemoWindow.qml"))
    if not engine.rootObjects():
        print("QML 加载失败：RainGlassDemo.qml", file=sys.stderr)
        return 2

    root = engine.rootObjects()[0]
    root.setProperty("quality", args.quality)
    # 实际 RHI 后端在首帧后才确定；用日志信息尽量报告（不伪造 adapter 名）。
    root.setProperty("rhiBackend", bridge.rhiBackendName())

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
