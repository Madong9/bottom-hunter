"""Overview shell POC launcher — Bottom Hunter 总览页外壳 Crystal Glass POC.

Batch mode (default) renders the shell screenshots and exits:
  overview_shell_clear_v4.png                    full shell (readability + rain last)
  overview_shell_clear_v4_readability_debug.png  rain zones (red) + readability zones (blue)

The shell reuses the ACCEPTED MaterialLab shaders (ClearGlass + StaticRain).
No business logic, no other pages, formal QtWidgets GUI untouched.

Usage:
  .venv/bin/python -m bottom_hunter.ui_demo.overview_shell.overview_shell_launcher
  .venv/bin/python -m bottom_hunter.ui_demo.overview_shell.overview_shell_launcher --out shots
  .venv/bin/python -m bottom_hunter.ui_demo.overview_shell.overview_shell_launcher --run

The GPU path needs a display with a working GL context (X11/Wayland).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent

WIDTH = 1440
HEIGHT = 900

MODES = (
    ("shell", "overview_shell_clear_v4.png"),
    ("readability_debug", "overview_shell_clear_v4_readability_debug.png"),
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Overview shell Crystal Glass POC (总览页外壳)"
    )
    parser.add_argument(
        "--out",
        default=str(LAB_DIR / "shots"),
        help="screenshot output directory (default: <overview_shell>/shots)",
    )
    parser.add_argument(
        "--modes",
        default=None,
        help="comma-separated subset of modes to render (default: all). "
        "Keys: " + ",".join(m for m, _ in MODES),
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="open an interactive window instead of batch screenshot mode",
    )
    return parser.parse_args(argv)


def _prepare_env() -> None:
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")


def _select_modes(spec: str | None) -> list[tuple[str, str]]:
    if not spec:
        return list(MODES)
    valid = dict(MODES)
    keys = [k.strip() for k in spec.split(",") if k.strip()]
    unknown = [k for k in keys if k not in valid]
    if unknown:
        raise SystemExit(
            f"unknown mode(s): {', '.join(unknown)}; valid: {', '.join(valid)}"
        )
    return [(k, valid[k]) for k in keys]


def _settle(app, ms: float) -> None:
    t0 = time.perf_counter()
    while (time.perf_counter() - t0) * 1000.0 < ms:
        app.processEvents()
        time.sleep(0.005)


def _size_of(v) -> tuple[int, int]:
    w = v.width() if hasattr(v, "width") else v.x()
    h = v.height() if hasattr(v, "height") else v.y()
    return int(w), int(h)


def _frame_delta(a, b) -> float:
    total, n = 0.0, 0
    step = 7
    w, h = min(a.width(), b.width()), min(a.height(), b.height())
    for y in range(0, h, step):
        for x in range(0, w, step):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += abs(ca.redF() - cb.redF()) + abs(ca.greenF() - cb.greenF()) + abs(ca.blueF() - cb.blueF())
            n += 1
    return total / (3.0 * n) if n else 0.0


def _make_view(qml_path: Path):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickView

    view = QQuickView(QUrl.fromLocalFile(str(qml_path)))
    view.setColor(QColor("#04070E"))
    view.resize(WIDTH, HEIGHT)
    view.show()
    return view


def run_batch(app, args: argparse.Namespace) -> int:
    view = _make_view(LAB_DIR / "OverviewShell.qml")
    _settle(app, 700)

    root = view.rootObject()
    if root is None:
        print("ERROR: OverviewShell.qml failed to load", file=sys.stderr)
        return 2

    dpr = view.devicePixelRatio()
    tex_w, tex_h = _size_of(root.property("captureTextureSize"))
    print(
        f"[shell] platform={os.environ.get('QT_QPA_PLATFORM', 'auto')} "
        f"rhi={os.environ.get('QSG_RHI_BACKEND', 'auto')} dpr={dpr} "
        f"window={view.width()}x{view.height()} "
        f"ShaderEffectSource.textureSize={tex_w}x{tex_h}"
    )
    if (tex_w, tex_h) != (WIDTH, HEIGHT):
        print(
            f"WARNING: textureSize {tex_w}x{tex_h} != expected {WIDTH}x{HEIGHT}",
            file=sys.stderr,
        )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    modes = _select_modes(args.modes)
    shots: dict[str, object] = {}
    for mode, filename in modes:
        root.setProperty("mode", mode)
        _settle(app, 500)
        img = view.grabWindow()
        expect = (int(WIDTH * dpr), int(HEIGHT * dpr))
        if (img.width(), img.height()) != expect:
            print(
                f"ERROR: {filename} grab size {img.width()}x{img.height()} != {expect}",
                file=sys.stderr,
            )
            return 3
        path = out / filename
        if not img.save(str(path)):
            print(f"ERROR: failed to save {path}", file=sys.stderr)
            return 3
        shots[mode] = img
        print(f"[shell] saved {path} ({img.width()}x{img.height()})")

    # sanity guard: rain mode must change the frame vs glass mode, otherwise
    # the ShaderEffect pipeline is inactive (no GPU / software RHI).
    if "shell" in shots and "glass" in shots:
        d_rain = _frame_delta(shots["glass"], shots["shell"])
        print(f"[shell] frame delta (glass -> rain): {d_rain:.4f}")
        if d_rain < 0.002:
            print(
                "WARNING: rain layer did not change the frame — ShaderEffect "
                "pipeline may be inactive (no GPU / software backend).",
                file=sys.stderr,
            )
            return 4

    view.close()
    return 0


def run_interactive(app, args: argparse.Namespace) -> int:
    view = _make_view(LAB_DIR / "OverviewShell.qml")
    _settle(app, 500)
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _prepare_env()

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    app.setApplicationName("OverviewShellPOC")

    if args.run:
        return run_interactive(app, args)
    return run_batch(app, args)


if __name__ == "__main__":
    raise SystemExit(main())
