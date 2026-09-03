"""PHASE 4-A — Watchlist read-only migration tests.

Covers: DTO creation, ViewModel init, mock data display, empty state, error
state, QML load smoke, business isolation, no-write-API guarantee, and page
registry route state.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

QML_AVAILABLE = True
try:
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
except ImportError:  # pragma: no cover - PySide6 always present in this venv
    QML_AVAILABLE = False

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"
SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


# ---- 1. DTO creation ---------------------------------------------------------

def test_watchlist_item_dto_defaults() -> None:
    from bottom_hunter.ui_demo.pages.watchlist_contracts import WatchlistItemDTO

    item = WatchlistItemDTO()
    assert item.symbol == "--"
    assert item.name == "--"
    assert item.market == "--"
    assert item.price == "--"
    assert item.change == "--"
    assert item.change_percent == "--"
    assert item.signal == "--"
    assert item.updated_at == ""


def test_watchlist_item_dto_frozen() -> None:
    from dataclasses import FrozenInstanceError

    from bottom_hunter.ui_demo.pages.watchlist_contracts import WatchlistItemDTO

    item = WatchlistItemDTO(symbol="AAPL")
    with pytest.raises(FrozenInstanceError):
        item.symbol = "MSFT"  # type: ignore[misc]


def test_watchlist_dto_as_dict() -> None:
    from bottom_hunter.ui_demo.pages.watchlist_contracts import WatchlistDTO, WatchlistItemDTO

    dto = WatchlistDTO(items=(WatchlistItemDTO(symbol="600000", name="浦发银行"),),
                       generated_at="2026-09-02T00:00:00")
    payload = dto.as_dict()
    assert payload["generated_at"] == "2026-09-02T00:00:00"
    assert payload["items"][0]["symbol"] == "600000"
    assert payload["items"][0]["name"] == "浦发银行"


# ---- 2. ViewModel init -------------------------------------------------------

def test_viewmodel_defaults() -> None:
    from bottom_hunter.ui_demo.pages.watchlist_viewmodel import (
        LIFECYCLE_INIT,
        WatchlistViewModel,
    )

    vm = WatchlistViewModel()
    assert vm.property("pageId") == "watchlist"
    assert vm.property("title") == "自选"
    assert vm.property("lifecycle") == LIFECYCLE_INIT
    assert vm.property("items") == []
    assert vm.property("count") == 0
    assert vm.property("loaded") is False
    assert vm.property("error") == ""


# ---- 3. mock data display ----------------------------------------------------

def _make_vm_with_rows():
    from bottom_hunter.ui_demo.pages.watchlist_contracts import WatchlistDTO, WatchlistItemDTO
    from bottom_hunter.ui_demo.pages.watchlist_viewmodel import WatchlistViewModel

    vm = WatchlistViewModel()
    dto = WatchlistDTO(
        items=(
            WatchlistItemDTO(symbol="600000", name="浦发银行", market="CN", industry="银行"),
            WatchlistItemDTO(symbol="AAPL", name="苹果", market="US", industry="科技"),
        ),
        generated_at="2026-09-02T00:00:00",
    )
    vm.apply(dto)
    return vm


def test_viewmodel_apply_mock_data() -> None:
    from bottom_hunter.ui_demo.pages.watchlist_viewmodel import LIFECYCLE_READY

    vm = _make_vm_with_rows()
    items = vm.property("items")
    assert vm.property("count") == 2
    assert vm.property("lifecycle") == LIFECYCLE_READY
    assert vm.property("loaded") is True
    assert vm.property("generatedAt") == "2026-09-02T00:00:00"
    assert items[0]["symbol"] == "600000"
    assert items[1]["name"] == "苹果"


# ---- 4. empty state ----------------------------------------------------------

def test_viewmodel_empty_state() -> None:
    from bottom_hunter.ui_demo.pages.watchlist_contracts import WatchlistDTO
    from bottom_hunter.ui_demo.pages.watchlist_viewmodel import (
        LIFECYCLE_EMPTY,
        WatchlistViewModel,
    )

    vm = WatchlistViewModel()
    vm.apply(WatchlistDTO(items=(), generated_at="2026-09-02"))
    assert vm.property("lifecycle") == LIFECYCLE_EMPTY
    assert vm.property("count") == 0
    assert vm.property("loaded") is True


# ---- 5. error state ----------------------------------------------------------

def test_viewmodel_error_state() -> None:
    from bottom_hunter.ui_demo.pages.watchlist_viewmodel import (
        LIFECYCLE_ERROR,
        WatchlistViewModel,
    )

    vm = WatchlistViewModel()
    vm.markLoading()
    assert vm.property("lifecycle") == "LOADING"
    vm.applyError("no snapshot")
    assert vm.property("lifecycle") == LIFECYCLE_ERROR
    assert vm.property("error") == "no snapshot"
    assert vm.property("loaded") is False


# ---- 6. QML load smoke -------------------------------------------------------

@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_qml_load_smoke(monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages.watchlist_viewmodel import WatchlistViewModel

    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    vm = WatchlistViewModel()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("watchlistVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "watchlist" / "Watchlist.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "Watchlist.qml produced no root object"
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_qml_watchlist_rows_have_readable_height_and_scroll(monkeypatch) -> None:
    """Guard against compressing a populated watchlist into unreadable bars."""
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    vm = _make_vm_with_rows()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("watchlistVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "watchlist" / "Watchlist.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "Watchlist.qml produced no root object"
        root = roots[0]
        watchlist = root.findChild(QObject, "watchlistList")
        assert root.property("tableRowHeight") >= 48
        assert watchlist is not None
        assert watchlist.property("interactive") is True
    finally:
        for r in roots:
            r.deleteLater()
        engine.deleteLater()
    del app


def test_watchlist_uses_unambiguous_glass_card_import() -> None:
    text = (PAGES_DIR / "watchlist" / "Watchlist.qml").read_text(encoding="utf-8")
    assert 'import "../../components" as Components' in text
    assert "Components.StatusBadge" in text
    for column in range(5):
        assert f"width: tableHeader.col{column}W" in text
        assert f"width: row.col{column}W" in text


# ---- 7. business isolation ---------------------------------------------------

def test_viewmodel_layer_does_not_import_business() -> None:
    """watchlist_viewmodel.py (viewmodel) + Watchlist.qml must not reference
    backend modules; only watchlist_contracts.py (adapter boundary) may."""
    forbidden = re.compile(r"bottom_hunter\.src|from\s+bottom_hunter\.src|scanner", re.I)
    vm_text = (PAGES_DIR / "watchlist_viewmodel.py").read_text(encoding="utf-8", errors="ignore")
    assert not forbidden.search(vm_text), "business import in watchlist_viewmodel.py"
    qml_text = (PAGES_DIR / "watchlist" / "Watchlist.qml").read_text(encoding="utf-8", errors="ignore")
    assert not forbidden.search(qml_text), "business import in Watchlist.qml"


# ---- 8. no write API calls ---------------------------------------------------

_WRITE_API = re.compile(
    r"\b(import_file|add_manual_asset|update_industry|clear_source|"
    r"refresh_linked_files|rebuild_active_watchlist|summary)\s*\(",
)


def test_adapter_has_no_write_api_calls() -> None:
    """The read-only adapter must never call a write-capable repository method
    (import/add/update/clear/rebuild). It loads the snapshot file directly."""
    text = (PAGES_DIR / "watchlist_contracts.py").read_text(encoding="utf-8")
    assert not _WRITE_API.search(text), "write API call found in watchlist_contracts.py"


def test_viewmodel_has_no_write_api_calls() -> None:
    text = (PAGES_DIR / "watchlist_viewmodel.py").read_text(encoding="utf-8")
    assert not _WRITE_API.search(text), "write API call found in watchlist_viewmodel.py"


# ---- 9. page registry route --------------------------------------------------

def test_page_registry_route_present() -> None:
    from bottom_hunter.ui_demo.pages import PAGE_WATCHLIST, PAGES

    ids = [pid for pid, _t, _g in PAGES]
    assert PAGE_WATCHLIST == "watchlist"
    assert "watchlist" in ids
    titles = [t for _pid, t, _g in PAGES if _pid == "watchlist"]
    assert titles == ["自选"]
