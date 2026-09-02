"""PHASE 4-B — Research read-only page contract and isolation tests."""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

QML_AVAILABLE = True
try:
    from PySide6.QtCore import QCoreApplication, QObject, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
except ImportError:  # pragma: no cover - PySide6 is a project dependency
    QML_AVAILABLE = False

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"


def _software_env(monkeypatch) -> None:
    monkeypatch.setenv("QSG_RHI_BACKEND", "software")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def _snapshot() -> dict:
    return {
        "report_date": "2026-09-01",
        "research": {
            "generated_at": "2026-09-01T08:00:00+00:00",
            "assets": {
                "AAPL": {
                    "latest_financial_period": "2026-06-30",
                    "latest_items": [
                        {
                            "kind": "filing",
                            "tier": "official",
                            "title": "Quarterly filing",
                            "source": "SEC",
                            "published_at": "2026-08-01T00:00:00+00:00",
                            "url": "https://example.test/filing",
                        }
                    ],
                }
            },
            "macro": [
                {
                    "series_id": "DGS10",
                    "name": "US 10Y",
                    "dimension": "liquidity",
                    "observation_date": "2026-08-31",
                    "value": 4.2,
                    "unit": "%",
                    "source": "FRED",
                    "source_url": "https://example.test/macro",
                    "signal": -1,
                }
            ],
        },
    }


def test_research_dto_construction_is_frozen() -> None:
    from bottom_hunter.ui_demo.pages.research_contracts import (
        ResearchAssetDTO,
        ResearchDTO,
        ResearchItemDTO,
        ResearchMacroDTO,
    )

    dto = ResearchDTO(
        assets=(ResearchAssetDTO(symbol="AAPL", items=(ResearchItemDTO(title="Filing"),)),),
        macro=(ResearchMacroDTO(series_id="DGS10", value=4.2),),
        generated_at="2026-09-01T08:00:00+00:00",
        report_date="2026-09-01",
    )
    assert dto.assets[0].items[0].title == "Filing"
    assert dto.macro[0].value == 4.2
    with pytest.raises(FrozenInstanceError):
        dto.report_date = "changed"  # type: ignore[misc]


def test_research_adapter_reads_latest_report(tmp_path: Path) -> None:
    from bottom_hunter.ui_demo.pages.research_contracts import build_research_dto

    (tmp_path / "daily_report_20260831.json").write_text(
        json.dumps({"research": {"assets": {}, "macro": []}}), encoding="utf-8"
    )
    (tmp_path / "daily_report_20260901.json").write_text(json.dumps(_snapshot()), encoding="utf-8")

    dto = build_research_dto(tmp_path)
    assert dto is not None
    assert dto.report_date == "2026-09-01"
    assert dto.generated_at == "2026-09-01T08:00:00+00:00"
    assert dto.assets[0].symbol == "AAPL"
    assert dto.assets[0].items[0].source == "SEC"
    assert dto.macro[0].series_id == "DGS10"
    assert dto.macro[0].signal == -1


def test_research_adapter_missing_and_invalid_snapshot(tmp_path: Path) -> None:
    from bottom_hunter.ui_demo.pages.research_contracts import build_research_dto

    assert build_research_dto(tmp_path) is None
    (tmp_path / "daily_report_20260901.json").write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="无法读取研究快照"):
        build_research_dto(tmp_path)


def test_research_viewmodel_lifecycle_ready() -> None:
    from bottom_hunter.ui_demo.pages.research_contracts import ResearchDTO, ResearchMacroDTO
    from bottom_hunter.ui_demo.pages.research_viewmodel import ResearchViewModel

    vm = ResearchViewModel()
    assert vm.property("lifecycle") == "INIT"
    assert vm.property("pageId") == "research"
    vm.markLoading()
    assert vm.property("lifecycle") == "LOADING"
    vm.apply(ResearchDTO(macro=(ResearchMacroDTO(name="US 10Y"),), report_date="2026-09-01"))
    assert vm.property("lifecycle") == "READY"
    assert vm.property("loaded") is True
    assert vm.property("macroCount") == 1
    assert vm.property("reportDate") == "2026-09-01"


def test_research_viewmodel_empty_state() -> None:
    from bottom_hunter.ui_demo.pages.research_contracts import ResearchDTO
    from bottom_hunter.ui_demo.pages.research_viewmodel import ResearchViewModel

    vm = ResearchViewModel()
    vm.apply(ResearchDTO(report_date="2026-09-01"))
    assert vm.property("lifecycle") == "EMPTY"
    assert vm.property("assetCount") == 0
    assert vm.property("macroCount") == 0
    assert vm.property("loaded") is True


def test_research_viewmodel_error_state(monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages import research_viewmodel

    def fail():
        raise ValueError("broken snapshot")

    vm = research_viewmodel.ResearchViewModel()
    monkeypatch.setattr(research_viewmodel, "build_research_dto", fail)
    vm.refresh()
    assert vm.property("lifecycle") == "ERROR"
    assert vm.property("error") == "broken snapshot"
    assert vm.property("loaded") is False


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_research_qml_load_smoke(monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages.research_contracts import ResearchDTO, ResearchMacroDTO
    from bottom_hunter.ui_demo.pages.research_viewmodel import ResearchViewModel

    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    vm = ResearchViewModel()
    vm.apply(ResearchDTO(macro=(ResearchMacroDTO(name="US 10Y", value=4.2, unit="%"),)))

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("researchVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "research" / "Research.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "Research.qml produced no root object"
        assert roots[0].objectName() == "researchPage"
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
    del app


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_application_shell_loads_research_route(monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages import NavigationController
    from bottom_hunter.ui_demo.pages.research_contracts import ResearchDTO
    from bottom_hunter.ui_demo.pages.research_viewmodel import ResearchViewModel

    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = NavigationController()
    vm = ResearchViewModel()
    vm.apply(ResearchDTO())

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("navController", controller)
    engine.rootContext().setContextProperty("researchVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "ApplicationShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots
        controller.navigate("research")
        QCoreApplication.processEvents()
        loader = roots[0].findChild(QObject, "researchPageLoader")
        assert loader is not None
        assert loader.property("active") is True
        assert loader.property("item") is not None
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
    del app


def test_research_layers_are_isolated() -> None:
    adapter = (PAGES_DIR / "research_contracts.py").read_text(encoding="utf-8")
    viewmodel = (PAGES_DIR / "research_viewmodel.py").read_text(encoding="utf-8")
    qml = (PAGES_DIR / "research" / "Research.qml").read_text(encoding="utf-8")

    backend = re.compile(r"bottom_hunter\.src|scanner|StateStore|ResearchStore|ResearchService", re.I)
    direct_storage = re.compile(r"sqlite3|\.connect\s*\(", re.I)
    qt_in_dto = re.compile(r"PySide6|QObject|QtQuick", re.I)
    assert not backend.search(viewmodel)
    assert not backend.search(qml)
    assert not direct_storage.search(viewmodel)
    assert not direct_storage.search(qml)
    assert not qt_in_dto.search(adapter)


def test_research_layers_call_no_write_api() -> None:
    files = (
        PAGES_DIR / "research_contracts.py",
        PAGES_DIR / "research_viewmodel.py",
        PAGES_DIR / "research" / "Research.qml",
    )
    write_api = re.compile(
        r"\b(save_financial_facts|save_items|save_macro|mark_refresh|"
        r"refresh_asset|refresh_macro|import_items)\s*\(",
    )
    for path in files:
        assert not write_api.search(path.read_text(encoding="utf-8")), f"write API call in {path.name}"
