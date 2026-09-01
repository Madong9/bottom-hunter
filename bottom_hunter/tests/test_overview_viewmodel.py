"""PHASE 2-A — Overview QObject ViewModel bridge tests.

Covers: QObject construction, fallback defaults, QML property binding,
mock backend data propagation, QML rendering with mock data, and the
business-isolation rule (business modules never import QML; the shell never
imports business modules).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

QML_AVAILABLE = True
try:
    from PySide6.QtCore import QCoreApplication, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
except ImportError:  # pragma: no cover - PySide6 always present in this venv
    QML_AVAILABLE = False

SHELL_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "overview_shell"
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
VIEWMODEL_DIR = SHELL_DIR / "viewmodel"


def _find_registry(root):
    for child in root.findChildren(object):
        if child.metaObject().className().startswith("ProtectionRegistry"):
            return child
    raise AssertionError("ProtectionRegistry not found")


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def _make_state():
    from bottom_hunter.ui_demo.overview_shell.viewmodel import OverviewState

    return OverviewState()


def _make_bridge(state):
    from bottom_hunter.ui_demo.overview_shell.viewmodel import OverviewBridge

    return OverviewBridge(state)


# ---- 1. QObject construction ------------------------------------------------

def test_viewmodel_qobject_construction() -> None:
    state = _make_state()
    bridge = _make_bridge(state)
    assert state is not None and bridge is not None
    assert bridge.parent() is None or bridge.parent() is not state


# ---- 2. fallback defaults ----------------------------------------------------

def test_default_state_is_fallback() -> None:
    state = _make_state()
    assert state.property("opportunityCount") == "--"
    assert state.property("dataHealth") == "--"
    assert state.property("signalValidation") == "--"
    assert state.property("portfolioValue") == "1.0000"
    assert state.property("opportunityHint") == "等待最新扫描"
    state.resetToFallback()
    assert state.property("portfolioValue") == "1.0000"


# ---- 3. QML can read properties ----------------------------------------------

@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_qml_reads_properties(monkeypatch) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    state = _make_state()
    state.setOpportunity("12")
    state.setPortfolio("1.0500")

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("overviewState", state)
    engine.rootContext().setContextProperty("overviewBridge", _make_bridge(state))
    engine.load(QUrl.fromLocalFile(str(SHELL_DIR / "OverviewShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "OverviewShell.qml produced no root object"
        registry = _find_registry(roots[0])
        cards = registry.property("cards").toVariant()
        assert len(cards) == 4
        # QML bound values reflect the state (2 of 4 cards set, others fallback)
        values = sorted(c.property("value") for c in cards)
        assert "12" in values and "1.0500" in values and "--" in values
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


# ---- 4. no-backend fallback in QML --------------------------------------------

@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_qml_fallback_without_backend(monkeypatch) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    # NO context property set: QML must fall back to the POC defaults
    engine.load(QUrl.fromLocalFile(str(SHELL_DIR / "OverviewShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "OverviewShell.qml produced no root object"
        registry = _find_registry(roots[0])
        cards = registry.property("cards").toVariant()
        assert len(cards) == 4
        values = sorted(c.property("value") for c in cards)
        assert values == ["--", "--", "--", "1.0000"]
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


# ---- 5. mock backend data ------------------------------------------------------

def test_mock_backend_data_propagates() -> None:
    state = _make_state()
    bridge = _make_bridge(state)

    def _opportunity():
        return {"value": "27", "hint": "有效观察 40 个", "report_date": "2026-09-01"}

    def _validation():
        return {"value": "63%", "hint": "30 样本 · +2.10%"}

    def _paper():
        return {"value": "1.0845", "hint": "42 个交易日"}

    bridge.setOpportunityLoader(_opportunity)
    bridge.setValidationLoader(_validation)
    bridge.setPaperLoader(_paper)
    bridge.refresh()

    assert state.property("opportunityCount") == "27"
    assert state.property("signalValidation") == "63%"
    assert state.property("portfolioValue") == "1.0845"
    assert state.property("reportDate") == "2026-09-01"

    # notify signals fired (Qt auto-detects changed property reads); a broken
    # loader must NOT clear the state
    bridge.setValidationLoader(lambda: None)
    bridge.refresh()
    assert state.property("signalValidation") == "63%"

    # raising loader must not crash and must keep current values
    def _boom():
        raise RuntimeError("backend offline")

    bridge.setOpportunityLoader(_boom)
    bridge.refresh()
    assert state.property("opportunityCount") == "27"


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_qml_shows_mock_backend_data(monkeypatch) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    state = _make_state()
    bridge = _make_bridge(state)
    bridge.setOpportunityLoader(lambda: {"value": "27", "hint": "有效观察 40 个"})
    bridge.setValidationLoader(lambda: {"value": "63%"})
    bridge.setPaperLoader(lambda: {"value": "1.0845"})
    bridge.refresh()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("overviewState", state)
    engine.rootContext().setContextProperty("overviewBridge", bridge)
    engine.load(QUrl.fromLocalFile(str(SHELL_DIR / "OverviewShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots
        registry = _find_registry(roots[0])
        cards = registry.property("cards").toVariant()
        values = sorted(c.property("value") for c in cards)
        assert values == ["--", "1.0845", "27", "63%"]
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


# ---- 6. business isolation ------------------------------------------------------

def test_business_modules_do_not_import_qml() -> None:
    """Production business modules must never import QML/Quick."""
    forbidden = re.compile(r"from\s+PySide6\.QtQml|import\s+PySide6\.QtQml|QtQuick", re.I)
    for py in SRC_DIR.glob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"QML import in production module {py.name}"


def test_shell_does_not_import_business_modules() -> None:
    """The QML shell + viewmodel must not import business modules. The
    launcher is the ONLY file allowed to wire backend loaders."""
    forbidden = re.compile(r"bottom_hunter\.src|from\s+bottom_hunter\.src|scanner", re.I)
    for py in VIEWMODEL_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {py.name}"
    for qml in SHELL_DIR.rglob("*.qml"):
        text = qml.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {qml.name}"
