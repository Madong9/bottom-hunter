from __future__ import annotations

import json
import shutil
import time
from datetime import UTC
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from bottom_hunter.src.account_watchlist import ImportResult
from bottom_hunter.src.chart_widget import (
    ChartWorkspace,
    merge_live_candle,
    parse_live_candle,
)
from bottom_hunter.src.charting import ChartResult
from bottom_hunter.src.gui_core import (
    PACKAGE_DIR,
    build_backtest_command,
    build_scan_command,
    load_data_health,
    load_report_summary,
    save_editor_content,
    validate_editor_content,
)
from bottom_hunter.src.gui_qt import BottomHunterWindow, WatchlistImportWorker
from bottom_hunter.src.gui_qt import main as gui_main


def test_gui_builds_safe_argument_lists() -> None:
    latest = build_scan_command("", False, 6, python_executable="python", workspace=Path("/app"))
    assert latest.argv == ["python", "/app/scanner.py", "--workers", "6"]
    historical = build_scan_command("2026-08-13", True, 3, python_executable="python", workspace=Path("/app"))
    assert historical.argv[-3:] == ["--date", "2026-08-13", "--offline"]
    backtest = build_backtest_command("2026-01-01", "2026-08-13", False, 4, "python", Path("/app"))
    assert backtest.argv[2:6] == ["--start", "2026-01-01", "--end", "2026-08-13"]


def test_live_crypto_messages_replace_or_append_the_current_candle() -> None:
    from datetime import datetime

    index = pd.to_datetime(["2026-08-25T00:00:00", "2026-08-26T00:00:00"])
    result = ChartResult(
        canonical_id="crypto:DOGE",
        symbol="DOGE-USDT",
        name="Dogecoin",
        timeframe="1d",
        bars=pd.DataFrame(
            {
                "open": [0.10, 0.09],
                "high": [0.11, 0.10],
                "low": [0.09, 0.08],
                "close": [0.095, 0.085],
                "volume": [1000, 1200],
            },
            index=index,
        ),
        provider="币安公开行情",
        updated_at=datetime.now(UTC),
    )
    message = json.dumps(
        {
            "e": "kline",
            "k": {
                "t": 1787702400000,
                "o": "0.09",
                "h": "0.105",
                "l": "0.08",
                "c": "0.101",
                "v": "1800",
                "x": False,
            },
        }
    )

    candle = parse_live_candle("binance", message)
    assert candle is not None
    updated = merge_live_candle(result, candle, 80)

    assert len(updated.bars) == 2
    assert updated.bars.iloc[-1]["close"] == pytest.approx(0.101)
    assert updated.provider == "币安 WebSocket"

    okx = parse_live_candle(
        "okx",
        json.dumps(
            {
                "arg": {"channel": "candle1Dutc", "instId": "DOGE-USDT"},
                "data": [
                    [
                        "1787788800000",
                        "0.101",
                        "0.11",
                        "0.10",
                        "0.108",
                        "2000",
                        "0",
                        "0",
                        "0",
                    ]
                ],
            }
        ),
    )
    assert okx is not None
    appended = merge_live_candle(updated, okx, 80)
    assert len(appended.bars) == 3
    assert appended.bars.iloc[-1]["close"] == pytest.approx(0.108)


def test_gui_rejects_bad_dates_and_worker_counts() -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        build_scan_command("2026/08/13", False, 6)
    with pytest.raises(ValueError, match="开始日期"):
        build_backtest_command("2026-08-14", "2026-08-13", False, 6)
    with pytest.raises(ValueError, match="线程"):
        build_scan_command("", False, 0)


def test_report_summary_counts_only_complete_high_scores(tmp_path) -> None:
    path = tmp_path / "daily_report_20260813.json"
    path.write_text(
        json.dumps(
            {
                "report_date": "2026-08-13",
                "market_sessions": {"US": "2026-08-13"},
                "market_environment": {"US": "Neutral"},
                "signals": [
                    {
                        "symbol": "A",
                        "market": "US",
                        "provider": "test",
                        "score": {"total": 8, "rejection": 2},
                        "signal_level": "EARLY REVERSAL",
                        "data_quality": "complete",
                    },
                    {
                        "symbol": "B",
                        "market": "US",
                        "provider": "test",
                        "score": {"total": 9, "rejection": 2},
                        "signal_level": "FAILED",
                        "data_quality": "complete",
                    },
                ],
                "sectors": [],
                "alerts": [],
                "data_errors": {"notify": "missing"},
            }
        ),
        encoding="utf-8",
    )
    summary = load_report_summary(path)
    assert summary.signal_count == 2
    assert summary.opportunity_count == 1
    assert summary.error_count == 1
    assert summary.signals[0]["symbol"] == "B"
    health = load_data_health(path)
    us = next(item for item in health if item["market"] == "US")
    global_row = next(item for item in health if item["market"] == "全局")
    assert us["complete"] == 2
    assert us["errors"] == 0
    assert global_row["errors"] == 1


def test_config_editor_validates_backs_up_and_saves(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in ("watchlist.yaml", "thresholds.yaml"):
        shutil.copy2(PACKAGE_DIR / "config" / name, config_dir / name)
    path = config_dir / "thresholds.yaml"
    original = path.read_text(encoding="utf-8")
    changed = original.replace("history_days: 420", "history_days: 421")
    backup = save_editor_content(path, changed)
    assert "history_days: 421" in path.read_text(encoding="utf-8")
    assert backup.read_text(encoding="utf-8") == original
    with pytest.raises(ValueError, match="YAML"):
        validate_editor_content(path, "defaults: [unterminated")


def test_headless_health_check_entrypoint() -> None:
    assert gui_main(["--check"]) == 0


def test_qt_window_builds_all_workspaces(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = BottomHunterWindow()
    window.refresh_all()
    monkeypatch.setattr(window.chart_workspace, "ensure_loaded", lambda: None)
    monkeypatch.setattr(window.research_workspace, "refresh", lambda: None)
    for page in range(7):
        window.switch_page(page)
        app.processEvents()
    assert window.pages.count() == 7
    assert window.context_list.count() >= 2
    assert window.signal_table.columnCount() == 5
    assert window.chart_workspace.timeframe_combo.count() >= 8
    for source in ("tonghuashun", "binance", "okx"):
        fields = window.account_fields[source]
        assert "api_key" not in fields
        assert "secret" not in fields
        assert "verify_button" not in fields
        assert fields["import_button"].text() == "导入文件"
    assert "app_key" in window.account_fields["longbridge"]
    window.close()


def test_watchlist_import_worker_keeps_qt_event_loop_responsive(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QThread, QTimer
    from PySide6.QtWidgets import QApplication

    class SlowRepository:
        def import_file(self, source, path, alias, *, resolve_industries):
            assert (source, path, alias, resolve_industries) == (
                "tonghuashun",
                "watchlist.xlsx",
                "main",
                True,
            )
            time.sleep(0.15)
            return ImportResult(
                source=source,
                imported_count=1,
                merged_count=1,
                duplicate_count=0,
                unresolved_industry_count=0,
                generated_sector_count=1,
                active_watchlist=tmp_path / "watchlist.yaml",
            )

    app = QApplication.instance() or QApplication([])
    loop = QEventLoop()
    thread = QThread()
    worker = WatchlistImportWorker(
        SlowRepository(),  # type: ignore[arg-type]
        "tonghuashun",
        "watchlist.xlsx",
        "main",
    )
    worker.moveToThread(thread)
    heartbeat = {"seen": False}
    completed = {"seen": False}
    QTimer.singleShot(20, lambda: heartbeat.update(seen=True))
    thread.started.connect(worker.run)
    worker.succeeded.connect(lambda _source, _result: completed.update(seen=True))
    worker.finished.connect(thread.quit)
    thread.finished.connect(loop.quit)
    thread.start()
    loop.exec()
    thread.wait()
    app.processEvents()

    assert heartbeat["seen"] is True
    assert completed["seen"] is True


def test_scan_skips_resync_when_linked_file_is_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    window = BottomHunterWindow()
    started: list[object] = []
    monkeypatch.setattr(window.watchlist_repo, "summary", lambda: {"asset_count": 1})
    monkeypatch.setattr(window.watchlist_repo, "changed_linked_sources", lambda: [])
    monkeypatch.setattr(window, "_start_task", lambda spec: started.append(spec))

    window.start_scan()
    app.processEvents()

    assert len(started) == 1
    window.close()


def test_chart_workspace_draws_and_persists_lines(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from datetime import datetime

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    workspace = ChartWorkspace(tmp_path / "drawings.json")
    index = pd.date_range("2026-08-01", periods=30, freq="D")
    bars = pd.DataFrame(
        {
            "open": range(100, 130),
            "high": range(102, 132),
            "low": range(98, 128),
            "close": range(101, 131),
            "volume": [1000] * 30,
        },
        index=index,
    )
    result = ChartResult(
        canonical_id="equity:US:AAPL",
        symbol="AAPL",
        name="Apple",
        timeframe="1d",
        bars=bars,
        provider="test",
        updated_at=datetime.now(UTC),
    )
    workspace.current_result = result
    workspace.annotations = []
    workspace._render_chart()
    workspace._set_draw_mode("horizontal")
    workspace._chart_clicked(SimpleNamespace(inaxes=workspace.price_axis, xdata=5.0, ydata=106.5))
    workspace._set_draw_mode("trend")
    workspace._chart_clicked(SimpleNamespace(inaxes=workspace.price_axis, xdata=2.0, ydata=101.0))
    workspace._chart_clicked(SimpleNamespace(inaxes=workspace.price_axis, xdata=12.0, ydata=115.0))
    app.processEvents()

    assert [item["type"] for item in workspace.annotations] == ["horizontal", "trend"]
    assert len(workspace.annotation_store.get("equity:US:AAPL", "1d")) == 2
    workspace.shutdown()
    workspace.close()


def test_chart_workspace_ctrl_wheel_changes_visible_candle_count(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from datetime import datetime

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    workspace = ChartWorkspace(tmp_path / "drawings.json")
    index = pd.date_range("2026-01-01", periods=120, freq="D")
    bars = pd.DataFrame(
        {
            "open": range(100, 220),
            "high": range(103, 223),
            "low": range(98, 218),
            "close": range(101, 221),
            "volume": [1000] * 120,
        },
        index=index,
    )
    workspace.current_result = ChartResult(
        canonical_id="equity:US:AAPL",
        symbol="AAPL",
        name="Apple",
        timeframe="1d",
        bars=bars,
        provider="test",
        updated_at=datetime.now(UTC),
    )
    workspace.annotations = []
    workspace._render_chart()
    initial_width = workspace.price_axis.get_xlim()[1] - workspace.price_axis.get_xlim()[0]

    workspace._chart_scrolled(
        SimpleNamespace(
            inaxes=workspace.price_axis,
            xdata=75.0,
            key="control",
            step=1,
            button="up",
            guiEvent=None,
        )
    )
    app.processEvents()

    zoomed_left, zoomed_right = workspace.price_axis.get_xlim()
    assert zoomed_right - zoomed_left < initial_width
    assert zoomed_left <= 75.0 <= zoomed_right
    assert workspace._view_xlim == (zoomed_left, zoomed_right)
    assert "当前约显示" in workspace.draw_hint.text()
    workspace.shutdown()
    workspace.close()


def test_chart_workspace_can_switch_overlay_and_panel_indicators(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from datetime import datetime

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    workspace = ChartWorkspace(tmp_path / "drawings.json")
    index = pd.date_range("2026-01-01", periods=120, freq="D")
    bars = pd.DataFrame(
        {
            "open": range(100, 220),
            "high": range(103, 223),
            "low": range(98, 218),
            "close": range(101, 221),
            "volume": range(1000, 1120),
        },
        index=index,
    )
    workspace.current_result = ChartResult(
        canonical_id="equity:US:AAPL",
        symbol="AAPL",
        name="Apple",
        timeframe="1d",
        bars=bars,
        provider="test",
        updated_at=datetime.now(UTC),
    )
    workspace.annotations = []

    workspace.overlay_combo.setCurrentIndex(workspace.overlay_combo.findData("boll"))
    workspace.panel_combo.setCurrentIndex(workspace.panel_combo.findData("rsi"))
    workspace._render_chart()
    app.processEvents()

    price_labels = {line.get_label() for line in workspace.price_axis.lines}
    assert {"BOLL上轨", "BOLL中轨", "BOLL下轨"}.issubset(price_labels)
    assert workspace.indicator_axis is not None
    assert workspace.indicator_axis.get_ylabel() == "RSI"
    assert workspace.indicator_axis.get_ylim() == (0.0, 100.0)
    workspace.shutdown()
    workspace.close()
