"""PHASE 2-B — Overview state lifecycle & model enhancement tests.

Covers: state machine transitions, notify signals, error recovery, stale
state (old data preserved), QML lifecycle binding, mock backend data, and
the business-isolation rule (QML never imports backend; business modules
never import QML).
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


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def _find_registry(root):
    for child in root.findChildren(object):
        if child.metaObject().className().startswith("ProtectionRegistry"):
            return child
    raise AssertionError("ProtectionRegistry not found")


def _state():
    from bottom_hunter.ui_demo.overview_shell.viewmodel import OverviewState

    return OverviewState()


def _bridge(state):
    from bottom_hunter.ui_demo.overview_shell.viewmodel import OverviewBridge

    return OverviewBridge(state)


def _controller():
    from bottom_hunter.ui_demo.overview_shell.viewmodel import OverviewRefreshController

    return OverviewRefreshController()


def _loaders(values: dict):
    """Return a dict of loader setter -> loader for the bridge."""
    return values


# ---- 1. default lifecycle is INIT -------------------------------------------

def test_default_lifecycle_is_init() -> None:
    state = _state()
    assert state.property("lifecycle") == "INIT"
    assert state.property("lastError") == ""
    assert state.property("lastSuccessfulUpdate") == ""
    assert state.property("dataHealthLevel") == "UNKNOWN"
    assert state.property("portfolioValue") == "1.0000"


# ---- 2. LOADING -> READY -----------------------------------------------------

def test_loading_to_ready() -> None:
    state = _state()
    bridge = _bridge(state)
    bridge.setOpportunityLoader(lambda: {"value": "27", "hint": "x", "report_date": "2026-09-01"})
    bridge.setValidationLoader(lambda: {"value": "63%", "hint": "y"})
    bridge.setPaperLoader(lambda: {"value": "1.0845", "hint": "z"})

    transitions = []
    state.lifecycleChanged.connect(lambda: transitions.append(state.property("lifecycle")))
    bridge.refresh()
    # INIT -> LOADING -> READY
    assert "LOADING" in transitions
    assert state.property("lifecycle") == "READY"
    assert state.property("lastSuccessfulUpdate") != ""


# ---- 3. INIT -> ERROR --------------------------------------------------------

def test_init_to_error() -> None:
    state = _state()
    bridge = _bridge(state)

    def _boom():
        raise RuntimeError("backend offline")

    bridge.setOpportunityLoader(_boom)
    bridge.refresh()
    assert state.property("lifecycle") == "ERROR"
    assert "今日机会" in state.property("lastError")
    # fallback data preserved (not cleared)
    assert state.property("opportunityCount") == "--"


# ---- 4. READY -> STALE keeps old data ---------------------------------------

def test_ready_to_stale_preserves_data() -> None:
    state = _state()
    bridge = _bridge(state)
    good = lambda: {"value": "27", "hint": "x", "report_date": "2026-09-01"}
    bridge.setOpportunityLoader(good)
    bridge.setPaperLoader(lambda: {"value": "1.0845", "hint": "z"})

    bridge.refresh()
    assert state.property("lifecycle") == "READY"
    assert state.property("opportunityCount") == "27"
    assert state.property("portfolioValue") == "1.0845"

    # now the opportunity loader breaks -> STALE, old data preserved (no "--")
    def _boom():
        raise RuntimeError("offline again")

    bridge.setOpportunityLoader(_boom)
    bridge.refresh()
    assert state.property("lifecycle") == "STALE"
    assert state.property("opportunityCount") == "27"       # NOT "--"
    assert state.property("portfolioValue") == "1.0845"     # NOT cleared
    assert "今日机会" in state.property("lastError")


# ---- 5. STALE -> READY recovery ---------------------------------------------

def test_stale_to_ready_recovery() -> None:
    state = _state()
    bridge = _bridge(state)
    bridge.setOpportunityLoader(lambda: {"value": "27", "hint": "x"})
    bridge.refresh()
    assert state.property("lifecycle") == "READY"

    def _boom():
        raise RuntimeError("offline")

    bridge.setOpportunityLoader(_boom)
    bridge.refresh()
    assert state.property("lifecycle") == "STALE"

    bridge.setOpportunityLoader(lambda: {"value": "30", "hint": "x"})
    bridge.refresh()
    assert state.property("lifecycle") == "READY"
    assert state.property("opportunityCount") == "30"


# ---- 6. lastError updates ----------------------------------------------------

def test_lasterror_updates() -> None:
    state = _state()
    bridge = _bridge(state)

    def _boom():
        raise ValueError("bad report")

    bridge.setOpportunityLoader(_boom)
    bridge.refresh()
    first = state.property("lastError")
    assert "今日机会" in first


# ---- 7. notify signal --------------------------------------------------------

def test_notify_signals_fire() -> None:
    state = _state()
    seen = []
    state.lifecycleChanged.connect(lambda: seen.append("lifecycle"))
    state.opportunityCountChanged.connect(lambda: seen.append("opportunityCount"))
    state.dataHealthChanged.connect(lambda: seen.append("dataHealth"))
    bridge = _bridge(state)
    bridge.setOpportunityLoader(lambda: {"value": "27", "hint": "x"})
    bridge.setHealthLoader(lambda: {"level": "OK", "text": "正常"})
    bridge.refresh()
    assert "lifecycle" in seen
    assert "opportunityCount" in seen
    assert "dataHealth" in seen


# ---- 8. refresh controller --------------------------------------------------

def test_refresh_controller() -> None:
    from bottom_hunter.ui_demo.overview_shell.viewmodel import OverviewBridge

    state = _state()
    bridge = OverviewBridge(state)
    controller = _controller()
    controller.refreshRequested.connect(bridge.refresh)
    bridge.setOpportunityLoader(lambda: {"value": "27", "hint": "x"})
    controller.requestRefresh()
    assert state.property("lifecycle") == "READY"
    assert state.property("opportunityCount") == "27"


# ---- 9. QML reads lifecycle -------------------------------------------------

@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_qml_reads_lifecycle(monkeypatch) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    state = _state()
    state.markReady()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("overviewState", state)
    engine.load(QUrl.fromLocalFile(str(SHELL_DIR / "OverviewShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "OverviewShell.qml produced no root object"
        registry = _find_registry(roots[0])
        cards = registry.property("cards").toVariant()
        assert len(cards) == 4
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


# ---- 10. business isolation -------------------------------------------------

def test_business_modules_do_not_import_qml() -> None:
    forbidden = re.compile(r"from\s+PySide6\.QtQml|import\s+PySide6\.QtQml|QtQuick", re.I)
    for py in SRC_DIR.glob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"QML import in production module {py.name}"


def test_shell_does_not_import_business_modules() -> None:
    forbidden = re.compile(r"bottom_hunter\.src|from\s+bottom_hunter\.src|scanner", re.I)
    for py in VIEWMODEL_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {py.name}"
    for qml in SHELL_DIR.rglob("*.qml"):
        text = qml.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {qml.name}"
