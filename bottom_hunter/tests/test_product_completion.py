from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from bottom_hunter.src.watchlist_maintenance_gateway import (
    build_watchlist_maintenance_gateway,
)
from bottom_hunter.ui_demo.pages.chart_adapter import ChartDrawingAdapter
from bottom_hunter.ui_demo.pages.chart_contracts import ChartAssetDTO
from bottom_hunter.ui_demo.pages.chart_viewmodel import ChartViewModel
from bottom_hunter.ui_demo.pages.import_backend_adapter import AccountWatchlistMaintenanceAdapter
from bottom_hunter.ui_demo.pages.import_contracts import ImportMaintenanceCommandDTO
from bottom_hunter.ui_demo.pages.research_adapter import build_research_dto
from bottom_hunter.ui_demo.pages.task_contracts import TaskCommandDTO
from bottom_hunter.ui_demo.pages.task_controller import TaskController
from bottom_hunter.ui_demo.pages.task_viewmodel import TaskViewModel
from bottom_hunter.ui_demo.pages.watchlist_contracts import build_watchlist_dto
from PySide6.QtGui import QGuiApplication

_QT_APP_HOLDER: list[QGuiApplication] = []


def test_watchlist_joins_latest_report_without_writing(tmp_path: Path) -> None:
    summary = tmp_path / "watchlist_summary.json"
    reports = tmp_path / "reports"
    reports.mkdir()
    summary.write_text(
        json.dumps(
            {
                "generated_at": "2026-09-06T10:00:00Z",
                "category_counts": {"crypto": 1},
                "assets": [
                    {
                        "canonical_id": "crypto:BTC",
                        "symbol": "BTC-USDT",
                        "name": "Bitcoin",
                        "market": "CRYPTO",
                        "category": "crypto",
                        "industry": "加密货币",
                        "sources": ["binance", "okx"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report = reports / "daily_report_20260906.json"
    report.write_text(
        json.dumps(
            {
                "signals": [
                    {
                        "symbol": "BTC-USDT",
                        "signal_level": "WATCH",
                        "score": {"total": 5, "available_max": 8},
                        "metrics": {"close": 0.00001234, "return_1d": 0.025},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    before = summary.read_bytes(), report.read_bytes()

    dto = build_watchlist_dto(summary, reports)

    assert dto is not None
    assert dto.items[0].canonical_id == "crypto:BTC"
    assert dto.items[0].price == "0.00001234"
    assert dto.items[0].change == "+2.50%"
    assert dto.items[0].signal == "WATCH · 5/8"
    assert dto.items[0].sources == ("binance", "okx")
    assert before == (summary.read_bytes(), report.read_bytes())


def test_research_adapter_reads_sqlite_in_read_only_mode(tmp_path: Path) -> None:
    database = tmp_path / "signals.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE financial_facts (
            symbol TEXT, market TEXT, period_end TEXT, created_at TEXT
        );
        CREATE TABLE research_items (
            item_id INTEGER PRIMARY KEY, symbol TEXT, market TEXT, kind TEXT,
            tier TEXT, title TEXT, source TEXT, published_at TEXT, url TEXT,
            summary TEXT, sentiment TEXT, created_at TEXT
        );
        INSERT INTO financial_facts VALUES ('AAPL', 'US', '2026-06-30', '2026-09-01');
        INSERT INTO research_items VALUES (
            1, 'AAPL', 'US', 'news', 'primary', 'Apple update', 'Example',
            '2026-09-02', 'https://example.test/aapl', 'summary', 'positive', '2026-09-02'
        );
        """
    )
    connection.commit()
    connection.close()
    watchlist = tmp_path / "watchlist_summary.json"
    watchlist.write_text(
        json.dumps({"assets": [{"symbol": "AAPL", "name": "Apple", "market": "US"}]}),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    before = database.read_bytes()

    dto = build_research_dto(reports, database=database, watchlist_path=watchlist)

    assert dto is not None
    assert dto.assets[0].name == "Apple"
    assert dto.assets[0].financial_fact_count == 1
    assert dto.assets[0].research_item_count == 1
    assert dto.assets[0].items[0].title == "Apple update"
    assert database.read_bytes() == before
    assert not (tmp_path / "signals.db-journal").exists()


class _MemoryDrawingStore:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], list[dict]] = {}

    def get(self, canonical_id: str, timeframe: str) -> list[dict]:
        return self.values.get((canonical_id, timeframe), [])

    def save(self, canonical_id: str, timeframe: str, annotations: list[dict]) -> None:
        self.values[(canonical_id, timeframe)] = annotations


def test_chart_drawings_round_trip_and_viewmodel_scope() -> None:
    adapter = ChartDrawingAdapter(store=_MemoryDrawingStore())
    vm = ChartViewModel((ChartAssetDTO(canonical_id="crypto:BTC", symbol="BTC-USDT"),))
    saved = adapter.save(
        "crypto:BTC",
        "1d",
        [
            {"type": "horizontal", "price": 101.2},
            {"type": "invalid", "price": 0},
        ],
    )
    vm.applyDrawings(saved)

    assert vm.annotations == [{"price": 101.2, "type": "horizontal"}]
    requests = []
    vm.drawingsSaveRequested.connect(lambda *values: requests.append(values))
    vm.saveAnnotations([{"type": "horizontal", "price": 99}])
    assert requests[0][:2] == ("crypto:BTC", "1d")


class _FakeMaintenanceRepository:
    def __init__(self) -> None:
        self.calls = []

    def source_statuses(self):
        return {
            "binance": {
                "label": "币安",
                "count": 1,
                "manual_count": 1,
                "connected": True,
            }
        }

    def execute(self, action, payload):
        self.calls.append((action, payload))
        return {
            "summary": {"asset_count": 2},
            "message": "done",
            "affected_sources": [payload["source"]],
            "errors": {},
        }


def test_watchlist_maintenance_adapter_maps_commands_without_leaking_repository() -> None:
    repository = _FakeMaintenanceRepository()
    adapter = AccountWatchlistMaintenanceAdapter(gateway=repository)

    result = adapter.execute(
        ImportMaintenanceCommandDTO(
            action="add_manual",
            source="binance",
            symbol="BTC-USDT",
            name="Bitcoin",
            market="CRYPTO",
        )
    )

    assert result.success is True
    assert result.total_count == 2
    assert result.source_statuses[0].manual_count == 1
    assert not hasattr(result, "repository")
    assert repository.calls[0][0] == "add_manual"


def test_maintenance_gateway_writes_only_in_injected_workspace(tmp_path: Path) -> None:
    project = tmp_path / "project"
    gateway = build_watchlist_maintenance_gateway(
        str(project),
        state_dir=str(project / "state"),
        config_dir=str(project / "config"),
    )

    result = gateway.execute(
        "add_manual",
        {
            "source": "binance",
            "symbol": "BTC-USDT",
            "name": "Bitcoin",
            "market": "CRYPTO",
            "industry": "",
        },
    )

    assert result["summary"]["asset_count"] == 1
    assert gateway.source_statuses()["binance"]["manual_count"] == 1
    assert not (project / "state" / ".import.lock").exists()


class _ProcessPort:
    def _command(self, name: str) -> TaskCommandDTO:
        return TaskCommandDTO(
            kind=name,
            name=name,
            program=sys.executable,
            arguments=("-c", "print('task-ok')"),
            cwd=str(Path.cwd()),
        )

    def build_scan(self, _date: str, _offline: bool, _workers: int) -> TaskCommandDTO:
        return self._command("scan")

    def build_backtest(self, _start: str, _end: str, _offline: bool, _workers: int) -> TaskCommandDTO:
        return self._command("backtest")


def test_task_controller_runs_without_blocking_qt() -> None:
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication([])
        _QT_APP_HOLDER.append(app)
    controller = TaskController(_ProcessPort())
    vm = TaskViewModel()
    controller.taskStarted.connect(vm.markStarted)
    controller.outputReceived.connect(vm.appendOutput)
    controller.taskFinished.connect(vm.applyFinished)
    vm.startScanRequested.connect(controller.startScan)

    started = time.monotonic()
    vm.startScan("", False, 1)
    elapsed = time.monotonic() - started
    deadline = time.monotonic() + 3
    while controller.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert elapsed < 0.2
    assert controller.busy is False
    assert vm.state == "SUCCESS"
    assert "task-ok" in vm.log
