"""PHASE 5 product composition, Status page and seven-route tests."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from bottom_hunter.ui_demo.overview_shell.contracts import OverviewDTO
from bottom_hunter.ui_demo.pages.contracts import ReportDTO
from bottom_hunter.ui_demo.pages.product_flow import build_production_flow
from bottom_hunter.ui_demo.pages.research_contracts import ResearchDTO
from bottom_hunter.ui_demo.pages.status_adapter import build_status_dto
from bottom_hunter.ui_demo.pages.status_contracts import StatusDTO, StatusItemDTO
from bottom_hunter.ui_demo.pages.status_viewmodel import StatusViewModel
from bottom_hunter.ui_demo.pages.watchlist_contracts import WatchlistDTO
from PySide6.QtCore import QCoreApplication, QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def test_status_dto_is_frozen_and_serializable() -> None:
    dto = StatusDTO(
        data_status="数据正常",
        system_health="正常",
        items=(StatusItemDTO("日报", True, "ok"),),
        ok_count=1,
        total_count=1,
    )
    assert dto.as_dict()["items"][0]["name"] == "日报"
    with pytest.raises(FrozenInstanceError):
        dto.system_health = "changed"  # type: ignore[misc]


def test_status_adapter_reads_existing_snapshot_only(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "daily_report_20260902.json").write_text(
        json.dumps(
            {
                "report_date": "2026-09-02",
                "generated_at": "2026-09-02T08:30:00+00:00",
                "data_errors": {"AAPL": "missing daily bar", "BTC-USDT": "stale"},
            }
        ),
        encoding="utf-8",
    )
    dto = build_status_dto(
        report_dir,
        health_reader=lambda: [("Qt 桌面", True, "ok"), ("日报", False, "stale")],
    )

    assert dto.last_scan_time == "2026-09-02T08:30:00+00:00"
    assert dto.data_status == "发现 2 项数据异常"
    assert dto.system_health == "需检查"
    assert dto.ok_count == 1
    assert len(dto.recent_errors) == 2
    assert list(tmp_path.rglob("*")) == [report_dir, report_dir / "daily_report_20260902.json"]


def test_status_viewmodel_lifecycle() -> None:
    vm = StatusViewModel()
    assert vm.lifecycle == "INIT"
    vm.markLoading()
    assert vm.lifecycle == "LOADING"
    vm.apply(StatusDTO(items=(StatusItemDTO("日报", True, "ok"),), ok_count=1, total_count=1))
    assert vm.lifecycle == "READY"
    assert vm.items[0]["name"] == "日报"
    vm.apply(StatusDTO())
    assert vm.lifecycle == "EMPTY"
    vm.applyError("快照损坏")
    assert vm.lifecycle == "ERROR"
    assert vm.error == "快照损坏"


def _product_flow(tmp_path: Path):
    return build_production_flow(
        str(tmp_path / "project"),
        state_dir=str(tmp_path / "project" / "state"),
        config_dir=str(tmp_path / "project" / "config"),
        overview_provider=lambda: OverviewDTO(),
        watchlist_provider=lambda: WatchlistDTO(),
        research_provider=lambda: ResearchDTO(),
        report_provider=lambda: ReportDTO(report_date="2026-09-02"),
        status_provider=lambda: StatusDTO(
            data_status="数据正常",
            system_health="正常",
            items=(StatusItemDTO("日报", True, "ok"),),
            ok_count=1,
            total_count=1,
        ),
    )


def test_build_production_flow_exposes_all_context_positions(tmp_path: Path) -> None:
    flow = _product_flow(tmp_path)
    assert set(flow.context_properties()) == {
        "navController",
        "overviewState",
        "overviewBridge",
        "overviewRefreshController",
        "watchlistVm",
        "researchVm",
        "reportVm",
        "importVm",
        "statusVm",
        "chartVm",
    }
    assert flow.navigation.currentPage == "overview"
    assert flow.watchlist_view_model.lifecycle == "EMPTY"
    assert flow.research_view_model.lifecycle == "EMPTY"
    assert flow.report_view_model.lifecycle == "READY"
    assert flow.status_view_model.lifecycle == "READY"
    assert flow.chart_view_model.lifecycle == "PLACEHOLDER"


def test_product_flow_uses_fallback_states_when_snapshots_are_missing(tmp_path: Path) -> None:
    flow = build_production_flow(
        str(tmp_path / "project"),
        state_dir=str(tmp_path / "project" / "state"),
        config_dir=str(tmp_path / "project" / "config"),
        overview_provider=lambda: None,
        watchlist_provider=lambda: None,
        research_provider=lambda: None,
        report_provider=lambda: None,
        status_provider=lambda: StatusDTO(),
    )

    assert flow.overview_state.lifecycle == "ERROR"
    assert flow.watchlist_view_model.lifecycle == "EMPTY"
    assert flow.research_view_model.lifecycle == "EMPTY"
    assert flow.report_view_model.lifecycle == "EMPTY"
    assert flow.status_view_model.lifecycle == "EMPTY"


def test_application_shell_loads_all_seven_product_routes(monkeypatch, tmp_path: Path) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    flow = _product_flow(tmp_path)
    engine = QQmlApplicationEngine()
    flow.install_context(engine)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "ApplicationShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots
        for page_id in ("overview", "watchlist", "research", "report", "import", "status", "chart"):
            flow.navigation.navigate(page_id)
            QCoreApplication.processEvents()
            loader = roots[0].findChild(QObject, f"{page_id}PageLoader")
            assert loader is not None, f"missing loader for {page_id}"
            assert loader.property("active") is True
            assert loader.property("item") is not None, f"failed to load {page_id}"
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
        app.processEvents()


def test_application_shell_connects_accepted_rain_glass_pipeline() -> None:
    qml = (PAGES_DIR / "ApplicationShell.qml").read_text(encoding="utf-8")
    rain_shader = PAGES_DIR.parent / "overview_shell" / "effects" / "StaticRainUI.qsb"
    assert 'import "../overview_shell"' in qml
    assert "RainGlassSurface" in qml
    assert "sourceItem: sceneContent" in qml
    assert "maskSource: importanceMask" in qml
    assert "rainEnabled: root.rainEnabled" in qml
    assert "daylight_city_after_rain.png" not in qml
    assert "background_only.png" not in qml
    assert "Image {" not in qml
    assert rain_shader.is_file()


def test_product_pages_use_visible_daylight_liquid_glass() -> None:
    surface = (PAGES_DIR.parent / "primitives" / "GlassSurface.qml").read_text(
        encoding="utf-8"
    )
    assert "property real tintAlpha: 0.16" in surface
    assert "gradient: Gradient" in surface
    assert "border.color: Qt.rgba(1, 1, 1, 0.52)" in surface

    for relative in (
        "overview/Overview.qml",
        "watchlist/Watchlist.qml",
        "research/Research.qml",
        "report/Report.qml",
        "import/Import.qml",
        "status/Status.qml",
        "chart/Chart.qml",
    ):
        page = (PAGES_DIR / relative).read_text(encoding="utf-8")
        assert "tintAlpha: 0.16" in page
        assert "surfaceRadius: 24" in page


def test_status_qml_error_and_fallback_load(monkeypatch) -> None:
    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    vm = StatusViewModel()
    vm.applyError("状态快照不可用")
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("statusVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "status" / "Status.qml")))
    roots = engine.rootObjects()
    try:
        assert roots and roots[0].objectName() == "statusPage"
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
        app.processEvents()
