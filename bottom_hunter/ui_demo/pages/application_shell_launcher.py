"""Runnable entry point for the PHASE 5 QML product shell."""

from __future__ import annotations

import os
import sys
from pathlib import Path

SHELL_PATH = Path(__file__).resolve().parent / "ApplicationShell.qml"


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QColor, QGuiApplication
    from PySide6.QtQuick import QQuickView

    from .product_flow import build_production_flow

    app = QGuiApplication(argv if argv is not None else sys.argv)
    flow = build_production_flow()
    view = QQuickView()
    flow.install_context(view.engine())
    view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
    view.setColor(QColor("#04070E"))
    view.setSource(QUrl.fromLocalFile(str(SHELL_PATH)))
    if view.status() == QQuickView.Status.Error:
        return 2
    view.resize(1440, 900)
    view.show()
    # ``flow`` remains strongly referenced by this stack frame until app.exec returns.
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
