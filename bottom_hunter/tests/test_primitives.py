"""Glass primitive loading and architecture checks.

Verifies the four abstract primitives load cleanly, and that they do not
violate isolation (no business imports).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

QML_AVAILABLE = True
try:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
except ImportError:  # pragma: no cover - PySide6 always present in this venv
    QML_AVAILABLE = False

PRIMITIVES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "primitives"


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def test_primitives_files_exist() -> None:
    for name in ("GlassSurface.qml", "GlassCard.qml", "GlassButton.qml",
                 "GlassText.qml", "qmldir"):
        assert (PRIMITIVES_DIR / name).exists(), f"missing {name}"


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_primitives_load(monkeypatch) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()

    # load each primitive standalone via a tiny wrapper using a local file
    for name in ("GlassSurface.qml", "GlassCard.qml", "GlassButton.qml", "GlassText.qml"):
        from PySide6.QtQml import QQmlComponent

        comp = QQmlComponent(engine, QUrl.fromLocalFile(str(PRIMITIVES_DIR / name)))
        obj = comp.create()
        # GlassCard references GlassSurface via sibling (same-dir implicit)
        assert obj is not None, f"{name} failed to instantiate: {comp.errorString()}"
        obj.deleteLater()

    engine.deleteLater()
    del app


def test_primitives_do_not_import_business() -> None:
    forbidden = re.compile(r"bottom_hunter\.src|scanner|StateStore", re.I)
    for qml in PRIMITIVES_DIR.rglob("*.qml"):
        text = qml.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {qml.name}"
