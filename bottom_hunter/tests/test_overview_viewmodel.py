"""PHASE 2-C — Overview state lifecycle & DTO contract tests.

Covers: DTO immutability + default factories, State.apply(dto), the state
machine transitions, notify signals, error recovery, stale state (old data
preserved), QML lifecycle binding, and the business-isolation rule.
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
CONTRACTS_DIR = SHELL_DIR / "contracts"


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


def _dto(**overrides):
    """Build an OverviewDTO with sensible values; overrides win."""
    from bottom_hunter.ui_demo.overview_shell.contracts import (
        HealthDTO,
        MarketDTO,
        OpportunityDTO,
        OverviewDTO,
        PortfolioDTO,
        ScanDTO,
        ValidationDTO,
    )

    kwargs = dict(
        market=MarketDTO(status="A股 开盘"),
        scan=ScanDTO(status="就绪", report_date="2026-09-01"),
        opportunity=OpportunityDTO(count="27", hint="有效观察 40 个", updated="2026-09-01"),
        health=HealthDTO(level="OK", text="正常"),
        validation=ValidationDTO(value="63%", hint="30 样本"),
        portfolio=PortfolioDTO(value="1.0845", hint="42 个交易日"),
        timestamp="2026-09-01T00:00:00",
    )
    kwargs.update(overrides)
    return OverviewDTO(**kwargs)


# ---- contract tests (PHASE 2-C) ---------------------------------------------

def test_overview_dto_defaults() -> None:
    from bottom_hunter.ui_demo.overview_shell.contracts import OverviewDTO

    dto = OverviewDTO()
    assert dto.market.status == "--"
    assert dto.opportunity.count == "--"
    assert dto.health.level == "UNKNOWN"
    assert dto.validation.value == "--"
    assert dto.portfolio.value == "1.0000"


def test_overview_dto_is_frozen() -> None:
    from bottom_hunter.ui_demo.overview_shell.contracts import OverviewDTO

    dto = OverviewDTO()
    with pytest.raises(Exception):
        dto.opportunity.count = "99"  # type: ignore[misc]


def test_state_apply_dto() -> None:
    state = _state()
    state.apply(_dto())
    assert state.property("opportunityCount") == "27"
    assert state.property("validation") == "63%"
    assert state.property("portfolioValue") == "1.0845"
    assert state.property("dataHealthLevel") == "OK"
    assert state.property("marketStatus") == "A股 开盘"
    assert state.property("scanStatus") == "就绪"


def test_state_apply_accepts_dict() -> None:
    state = _state()
    state.apply({
        "opportunity": {"count": "27", "hint": "x", "updated": "d"},
        "health": {"level": "OK", "text": "正常"},
        "validation": {"value": "63%", "hint": "y"},
        "portfolio": {"value": "1.0845", "hint": "z"},
        "market": {"status": "A股 开盘", "detail": ""},
        "scan": {"status": "就绪", "detail": "报告 d"},
    })
    assert state.property("opportunityCount") == "27"
    assert state.property("validation") == "63%"
    assert state.property("portfolioValue") == "1.0845"


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
    bridge.setDtoProvider(lambda: _dto())

    transitions = []
    state.lifecycleChanged.connect(lambda: transitions.append(state.property("lifecycle")))
    bridge.refresh()
    assert "LOADING" in transitions
    assert state.property("lifecycle") == "READY"
    assert state.property("lastSuccessfulUpdate") != ""


# ---- 3. INIT -> ERROR --------------------------------------------------------

def test_init_to_error() -> None:
    state = _state()
    bridge = _bridge(state)

    def _boom():
        raise RuntimeError("backend offline")

    bridge.setDtoProvider(_boom)
    bridge.refresh()
    assert state.property("lifecycle") == "ERROR"
    assert "backend offline" in state.property("lastError")
    assert state.property("opportunityCount") == "--"


# ---- 4. READY -> STALE keeps old data ---------------------------------------

def test_ready_to_stale_preserves_data() -> None:
    state = _state()
    bridge = _bridge(state)
    bridge.setDtoProvider(lambda: _dto())
    bridge.refresh()
    assert state.property("lifecycle") == "READY"
    assert state.property("opportunityCount") == "27"
    assert state.property("portfolioValue") == "1.0845"

    def _boom():
        raise RuntimeError("offline again")

    bridge.setDtoProvider(_boom)
    bridge.refresh()
    assert state.property("lifecycle") == "STALE"
    assert state.property("opportunityCount") == "27"       # NOT "--"
    assert state.property("portfolioValue") == "1.0845"     # NOT cleared
    assert "offline again" in state.property("lastError")


# ---- 5. STALE -> READY recovery ---------------------------------------------

def test_stale_to_ready_recovery() -> None:
    state = _state()
    bridge = _bridge(state)
    bridge.setDtoProvider(lambda: _dto())
    bridge.refresh()
    assert state.property("lifecycle") == "READY"

    def _boom():
        raise RuntimeError("offline")

    bridge.setDtoProvider(_boom)
    bridge.refresh()
    assert state.property("lifecycle") == "STALE"

    bridge.setDtoProvider(lambda: _dto())
    bridge.refresh()
    assert state.property("lifecycle") == "READY"


# ---- 6. lastError updates ----------------------------------------------------

def test_lasterror_updates() -> None:
    state = _state()
    bridge = _bridge(state)

    def _boom():
        raise ValueError("bad report")

    bridge.setDtoProvider(_boom)
    bridge.refresh()
    assert "bad report" in state.property("lastError")


# ---- 7. notify signal --------------------------------------------------------

def test_notify_signals_fire() -> None:
    state = _state()
    seen = []
    state.lifecycleChanged.connect(lambda: seen.append("lifecycle"))
    state.opportunityCountChanged.connect(lambda: seen.append("opportunityCount"))
    state.dataHealthChanged.connect(lambda: seen.append("dataHealth"))
    bridge = _bridge(state)
    bridge.setDtoProvider(lambda: _dto())
    bridge.refresh()
    assert "lifecycle" in seen
    assert "opportunityCount" in seen
    assert "dataHealth" in seen


# ---- 8. refresh controller --------------------------------------------------

def test_refresh_controller() -> None:
    state = _state()
    bridge = _bridge(state)
    controller = _controller()
    controller.refreshRequested.connect(bridge.refresh)
    bridge.setDtoProvider(lambda: _dto())
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
    for py in CONTRACTS_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {py.name}"
    for qml in SHELL_DIR.rglob("*.qml"):
        text = qml.read_text(encoding="utf-8", errors="ignore")
        assert not forbidden.search(text), f"business import in {qml.name}"
