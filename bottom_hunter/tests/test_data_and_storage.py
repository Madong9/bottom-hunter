from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
from bottom_hunter.src.alerts import build_alerts
from bottom_hunter.src.data_provider import CsvFundamentalProvider, normalize_bars
from bottom_hunter.src.models import (
    BottomState,
    EntryStage,
    ScoreBreakdown,
    SignalLevel,
    StockSignal,
)
from bottom_hunter.src.storage import StateStore


def test_normalize_rejects_duplicates_and_bad_rows() -> None:
    raw = pd.DataFrame(
        {
            "Date": ["2024-01-02", "2024-01-02", "2024-01-03"],
            "Open": [10, 11, -1],
            "High": [12, 13, 1],
            "Low": [9, 10, 2],
            "Close": [11, 12, 1],
            "Volume": [100, 200, 0],
        }
    )
    bars = normalize_bars(raw, date(2024, 1, 1), date(2024, 1, 4))
    assert len(bars) == 1
    assert bars.iloc[0]["close"] == 12


def test_fundamental_provider_is_point_in_time(tmp_path) -> None:
    path = tmp_path / "fundamentals.csv"
    path.write_text(
        "date,symbol,score,reason,source\n2024-01-10,TEST,1,不确定,source-a\n2024-02-10,TEST,2,已排除,source-b\n",
        encoding="utf-8",
    )
    provider = CsvFundamentalProvider(path)
    instrument = type("Instrument", (), {"symbol": "TEST"})()
    assert provider.get_fundamental_data(instrument, date(2024, 1, 5)).score is None
    assert provider.get_fundamental_data(instrument, date(2024, 1, 20)).score == 1
    assert provider.get_fundamental_data(instrument, date(2024, 2, 20)).score == 2


def _signal(target: date, score: int, stage=None, failed=False) -> StockSignal:
    breakdown = ScoreBreakdown(2, 2, 2, 1, score - 7, 0)
    return StockSignal(
        target,
        "TEST",
        "测试",
        "US",
        "sector",
        "测试板块",
        breakdown,
        SignalLevel.FAILED if failed else SignalLevel.BUY_CANDIDATE,
        BottomState.FAILED if failed else BottomState.NO_NEW_LOW,
        stage,
        {},
        [],
        [],
        False,
        target,
        10.0,
        "complete",
        "test",
        datetime.now(UTC),
    )


def test_alerts_are_persisted_once(tmp_path) -> None:
    store = StateStore(tmp_path / "signals.db")
    first = _signal(date(2024, 1, 2), 6)
    store.save_signals([first])
    second = _signal(date(2024, 1, 3), 8, EntryStage.ENTRY_STAGE_2)
    proposed = build_alerts([second], [], store)
    inserted = store.save_alerts(proposed)
    assert {item.alert_type for item in inserted} == {"A_SCORE_JUMP", "B_ENTRY_STAGE"}
    assert store.save_alerts(proposed) == []


def test_new_run_marks_interrupted_previous_run_aborted(tmp_path) -> None:
    store = StateStore(tmp_path / "signals.db")
    first = store.start_run(date(2026, 8, 13))
    second = store.start_run(date(2026, 8, 14))
    with store.connect() as connection:
        rows = connection.execute(
            "SELECT id, status FROM scan_runs WHERE id IN (?, ?) ORDER BY id", (first, second)
        ).fetchall()
    assert [(row["id"], row["status"]) for row in rows] == [
        (first, "aborted"),
        (second, "running"),
    ]


def test_paper_stage_weights_are_cumulative_targets_and_nav_keeps_cash(tmp_path) -> None:
    store = StateStore(tmp_path / "signals.db")
    store.paper_fills(
        date(2026, 8, 26),
        [{"symbol": "TEST", "sector_id": "s", "stage": "ENTRY_STAGE_1", "weight": 0.25, "price": 100}],
    )
    store.paper_fills(
        date(2026, 8, 27),
        [{"symbol": "TEST", "sector_id": "s", "stage": "ENTRY_STAGE_2", "weight": 0.60, "price": 110}],
    )
    position = store.paper_positions(date(2026, 8, 27))[0]
    assert position["weight"] == 0.60
    assert position["entry_price"] == (0.25 * 100 + 0.35 * 110) / 0.60
    store.save_valuations(
        date(2026, 8, 28),
        [
            {
                "symbol": "TEST",
                "sector_id": "s",
                "weight": 0.60,
                "entry_price": position["entry_price"],
                "last_price": position["entry_price"],
                "unrealized_return": 0.0,
            }
        ],
    )
    summary = store.paper_history_summary()
    assert summary["latest"] == 1.0
    assert summary["points"][0]["invested_weight"] == 0.60
