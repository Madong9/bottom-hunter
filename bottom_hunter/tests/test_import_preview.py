"""PHASE 4-D1 — Zero-write import preview tests."""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

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


def test_import_preview_dto_is_frozen() -> None:
    from bottom_hunter.ui_demo.pages.import_contracts import (
        ImportPreviewDTO,
        ImportPreviewItemDTO,
    )

    dto = ImportPreviewDTO(
        filename="watchlist.csv",
        format="CSV",
        detected_count=1,
        valid_count=1,
        preview_items=(ImportPreviewItemDTO(symbol="AAPL", name="Apple"),),
    )
    assert dto.preview_items[0].symbol == "AAPL"
    assert dto.as_dict()["preview_items"][0]["name"] == "Apple"
    with pytest.raises(FrozenInstanceError):
        dto.valid_count = 2  # type: ignore[misc]


def test_adapter_builds_preview_from_existing_parser(tmp_path: Path) -> None:
    from bottom_hunter.ui_demo.pages.import_preview_adapter import build_import_preview_dto

    source = tmp_path / "watchlist.csv"
    source.write_text(
        "symbol,name,industry\nAAPL,Apple,Technology\n600519,贵州茅台,食品饮料\n",
        encoding="utf-8",
    )
    dto = build_import_preview_dto(source, "tonghuashun")

    assert dto.filename == "watchlist.csv"
    assert dto.format == "CSV"
    assert dto.detected_count == 2
    assert dto.valid_count == 2
    assert dto.invalid_count == 0
    assert {item.symbol for item in dto.preview_items} == {"AAPL", "600519.SS"}


def test_adapter_calls_parser_without_repository(monkeypatch, tmp_path: Path) -> None:
    from bottom_hunter.src import account_watchlist
    from bottom_hunter.ui_demo.pages.import_preview_adapter import build_import_preview_dto

    selected = tmp_path / "selected.txt"
    selected.write_text("BTCUSDT\n", encoding="utf-8")
    calls: list[tuple[Path, str]] = []

    def parse(path, source, *, failures_out):
        calls.append((path, source))
        failures_out.append("第 2 条：无效")
        return [
            SimpleNamespace(
                symbol="BTC-USDT",
                name="Bitcoin",
                market="CRYPTO",
                category="crypto",
                industry="加密货币",
            )
        ]

    monkeypatch.setattr(account_watchlist, "parse_watchlist_file", parse)
    dto = build_import_preview_dto(selected, "binance")

    assert calls == [(selected.resolve(), "binance")]
    assert dto.detected_count == 2
    assert dto.valid_count == 1
    assert dto.invalid_count == 1
    assert dto.warnings == ("第 2 条：无效",)


def test_adapter_empty_file_returns_zero_preview(tmp_path: Path) -> None:
    from bottom_hunter.ui_demo.pages.import_preview_adapter import build_import_preview_dto

    selected = tmp_path / "empty.csv"
    selected.write_text("", encoding="utf-8")
    dto = build_import_preview_dto(selected, "tonghuashun")

    assert dto.detected_count == 0
    assert dto.valid_count == 0
    assert dto.invalid_count == 0
    assert dto.preview_items == ()
    assert dto.warnings == ("文件为空，没有可预览的记录。",)


def test_adapter_invalid_file_raises_preview_error(tmp_path: Path) -> None:
    from bottom_hunter.ui_demo.pages.import_preview_adapter import (
        ImportPreviewError,
        build_import_preview_dto,
    )

    selected = tmp_path / "broken.json"
    selected.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ImportPreviewError, match="无法解析"):
        build_import_preview_dto(selected, "tonghuashun")


def test_import_viewmodel_lifecycle_and_intent(tmp_path: Path) -> None:
    from bottom_hunter.ui_demo.pages.import_viewmodel import ImportViewModel

    selected = tmp_path / "watchlist.csv"
    selected.write_text("symbol,name\nAAPL,Apple\n", encoding="utf-8")
    vm = ImportViewModel()
    lifecycles: list[str] = []
    intents: list[tuple[str, str]] = []
    vm.lifecycleChanged.connect(lambda: lifecycles.append(vm.property("lifecycle")))
    vm.previewRequested.connect(lambda path, source: intents.append((path, source)))

    assert vm.property("lifecycle") == "INIT"
    vm.requestPreview(str(selected), "tonghuashun")

    assert lifecycles == ["SELECTING", "PREVIEWING", "READY"]
    assert intents == [(str(selected), "tonghuashun")]
    assert vm.property("filename") == "watchlist.csv"
    assert vm.property("validCount") == 1
    assert vm.property("previewItems")[0]["symbol"] == "AAPL"


def test_import_viewmodel_error_state(tmp_path: Path) -> None:
    from bottom_hunter.ui_demo.pages.import_viewmodel import ImportViewModel

    selected = tmp_path / "broken.json"
    selected.write_text("[", encoding="utf-8")
    vm = ImportViewModel()
    vm.requestPreview(str(selected), "okx")

    assert vm.property("lifecycle") == "ERROR"
    assert vm.property("error")
    assert vm.property("previewItems") == []


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_import_qml_load_smoke(monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages.import_contracts import ImportPreviewDTO
    from bottom_hunter.ui_demo.pages.import_viewmodel import ImportViewModel

    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    vm = ImportViewModel()
    vm.apply(ImportPreviewDTO(filename="watchlist.csv", format="CSV"))

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("importVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "import" / "Import.qml")))
    roots = engine.rootObjects()
    try:
        assert roots, "Import.qml produced no root object"
        assert roots[0].objectName() == "importPage"
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
    del app


@pytest.mark.skipif(not QML_AVAILABLE, reason="PySide6 QtQuick unavailable")
def test_application_shell_loads_import_route(monkeypatch) -> None:
    from bottom_hunter.ui_demo.pages import NavigationController
    from bottom_hunter.ui_demo.pages.import_viewmodel import ImportViewModel

    _software_env(monkeypatch)
    app = QGuiApplication.instance() or QGuiApplication([])
    controller = NavigationController()
    vm = ImportViewModel()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("navController", controller)
    engine.rootContext().setContextProperty("importVm", vm)
    engine.load(QUrl.fromLocalFile(str(PAGES_DIR / "ApplicationShell.qml")))
    roots = engine.rootObjects()
    try:
        assert roots
        controller.navigate("import")
        QCoreApplication.processEvents()
        loader = roots[0].findChild(QObject, "importPageLoader")
        assert loader is not None
        assert loader.property("active") is True
        assert loader.property("item") is not None
    finally:
        for root in roots:
            root.deleteLater()
        engine.deleteLater()
    del app


def test_import_preview_architecture_isolation() -> None:
    dto = (PAGES_DIR / "import_contracts.py").read_text(encoding="utf-8")
    adapter = (PAGES_DIR / "import_preview_adapter.py").read_text(encoding="utf-8")
    viewmodel = (PAGES_DIR / "import_viewmodel.py").read_text(encoding="utf-8")
    qml = (PAGES_DIR / "import" / "Import.qml").read_text(encoding="utf-8")

    backend = re.compile(r"bottom_hunter\.src|account_watchlist|scanner", re.I)
    storage = re.compile(r"sqlite3|StateStore|ResearchStore|\.connect\s*\(", re.I)
    qt_in_dto = re.compile(r"PySide6|QObject|QtQuick", re.I)
    assert not backend.search(viewmodel)
    assert not backend.search(qml)
    assert not storage.search(viewmodel)
    assert not storage.search(qml)
    assert not qt_in_dto.search(dto)
    assert "parse_watchlist_file" in adapter


def test_import_preview_contains_no_write_path() -> None:
    files = (
        PAGES_DIR / "import_preview_adapter.py",
        PAGES_DIR / "import_viewmodel.py",
        PAGES_DIR / "import" / "Import.qml",
    )
    forbidden = re.compile(
        r"\b(import_file|add_manual_asset|update_industry|clear_source|"
        r"refresh_linked_files|rebuild_active_watchlist|save_items|"
        r"execute|executemany|write_text|write_bytes|unlink)\s*\(",
    )
    for path in files:
        assert not forbidden.search(path.read_text(encoding="utf-8")), f"write path in {path.name}"
