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


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    # The production shell uses the accepted qsb rain/glass pipeline. OpenGL
    # is the verified Linux backend; callers may still override it explicitly.
    os.environ.setdefault("QSG_RHI_BACKEND", "opengl")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QColor, QGuiApplication
    from PySide6.QtQuick import QQuickView, QQuickWindow

    from .product_flow import build_production_flow

    # Request an alpha channel before constructing the native window. The
    # compositor, rather than an application image, supplies the background.
    QQuickWindow.setDefaultAlphaBuffer(True)
    app = QGuiApplication(argv if argv is not None else sys.argv)
    flow = build_production_flow()
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
    # ``flow`` remains strongly referenced by this stack frame until app.exec returns.
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
