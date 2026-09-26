"""Runnable entry point for the PHASE 5 QML product shell."""

from __future__ import annotations

import os
import sys
from pathlib import Path

SHELL_PATH = Path(__file__).resolve().parent / "ApplicationShell.qml"
WINDOW_TITLE = "Bottom Hunter · 板块超跌反弹狩猎系统"


def rain_effect_supported() -> bool:
    """Return whether the selected RHI can render the qsb rain surface."""
    backend = os.environ.get("QSG_RHI_BACKEND", "").strip().casefold()
    return backend not in {"software", "null"}


def desktop_blur_supported() -> bool:
    """Return whether the Qt platform exposes a native compositor window."""

    platform = os.environ.get("QT_QPA_PLATFORM", "").strip().casefold()
    return platform not in {"offscreen", "minimal", "minimalegl", "vnc", "linuxfb"}


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv)
    from bottom_hunter.packaging.app_runtime import prepare_application_runtime
    from bottom_hunter.packaging.worker_dispatch import dispatch_internal

    runtime = prepare_application_runtime()
    internal_result = dispatch_internal(arguments)
    if internal_result is not None:
        return internal_result
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    # The production shell uses the accepted qsb rain/glass pipeline. OpenGL
    # is the verified Linux backend; callers may still override it explicitly.
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QColor, QGuiApplication
    from PySide6.QtQuick import QQuickView, QQuickWindow
    from PySide6.QtWebEngineQuick import QtWebEngineQuick

    from .desktop_blur import apply_desktop_blur
    from .product_flow import build_production_flow

    # Request an alpha channel before constructing the native window. The
    # compositor, rather than an application image, supplies the background.
    QtWebEngineQuick.initialize()
    QQuickWindow.setDefaultAlphaBuffer(True)
    QGuiApplication.setApplicationName("Bottom Hunter")
    QGuiApplication.setDesktopFileName("bottom-hunter")
    app = QGuiApplication(arguments)
    flow = build_production_flow(
        str(runtime.project_dir),
        state_dir=str(runtime.state_dir),
        config_dir=str(runtime.config_dir),
    )
    app.aboutToQuit.connect(flow.task_controller.shutdown)
    app.aboutToQuit.connect(flow.research_assistant_runtime.shutdown)
    view = QQuickView()
    surface_format = view.format()
    surface_format.setAlphaBufferSize(8)
    view.setFormat(surface_format)
    view.setTitle(WINDOW_TITLE)
    flow.install_context(view.engine())
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setColor(QColor(0, 0, 0, 0))
    view.setSource(QUrl.fromLocalFile(str(SHELL_PATH)))
    if view.status() == QQuickView.Status.Error:
        return 2
    root = view.rootObject()
    if root is not None and not rain_effect_supported():
        # Software RHI cannot display ShaderEffect reliably. Keep the captured
        # transparent product scene visible instead of presenting a blank UI.
        root.setProperty("rainEnabled", False)
    view.resize(1440, 900)
    view.show()
    if desktop_blur_supported():
        blur_result = apply_desktop_blur(int(view.winId()))
        if not blur_result.active:
            print(f"Bottom Hunter 桌面模糊：{blur_result.detail}", file=sys.stderr)
    # ``flow`` remains strongly referenced by this stack frame until app.exec returns.
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
