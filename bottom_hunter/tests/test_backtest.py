from __future__ import annotations

import pandas as pd
import pytest
from bottom_hunter.src.backtest import (
    BacktestEvent,
    _episode_events,
    _execution_metrics,
    _forward_metrics,
    summarize_events,
)


def test_forward_returns_start_after_signal_day() -> None:
    frame = pd.DataFrame(
        {
            "close": [100, 110, 120, 90],
            "low": [99, 105, 115, 80],
        },
        index=pd.bdate_range("2024-01-01", periods=4),
    )
    returns, drawdowns = _forward_metrics(frame, 0, (1, 2, 3))
    assert returns["1d"] == pytest.approx(0.1)
    assert returns["2d"] == pytest.approx(0.2)
    assert drawdowns["2d"] == pytest.approx(0.05)
    assert drawdowns["3d"] == pytest.approx(-0.2)


def test_summary_reports_required_statistics() -> None:
    event = BacktestEvent(
        "2024-01-01",
        "TEST",
        "US",
        "x",
        8,
        10,
        "quarter_window",
        near_resistance=False,
        returns={f"{day}d": 0.1 for day in (3, 5, 10, 20, 60)},
        drawdowns={f"{day}d": -0.03 for day in (3, 5, 10, 20, 60)},
    )
    summary = summarize_events([event])
    stats = summary["score_gte_8"]["quarter_window"]["5d"]
    assert stats["sample_size"] == 1
    assert stats["win_rate"] == 1.0
    assert stats["average_return"] == 0.1
    assert stats["max_drawdown"] == -0.03
    experiment = summary["score_gte_8"]["resistance_experiment"]
    assert experiment["not_near"]["sample_size"] == 1
    assert experiment["near_resistance"]["sample_size"] == 0


def test_execution_uses_next_open_costs_and_benchmark() -> None:
    index = pd.bdate_range("2024-01-01", periods=4)
    frame = pd.DataFrame(
        {
            "open": [100, 102, 105, 107],
            "high": [101, 106, 109, 111],
            "low": [99, 101, 104, 106],
            "close": [100, 105, 108, 110],
        },
        index=index,
    )
    benchmark = pd.DataFrame(
        {
            "open": [200, 201, 202, 203],
            "high": [201, 203, 204, 205],
            "low": [199, 200, 201, 202],
            "close": [200, 202, 203, 204],
        },
        index=index,
    )
    returns, _, benchmark_returns, excess, *_ = _execution_metrics(
        frame,
        benchmark,
        0,
        cost_bps=20,
        stop_loss=0.20,
        take_profit=0.50,
        max_holding_sessions=3,
        horizons=(1, 2),
    )
    assert returns["1d"] == pytest.approx(105 / 102 - 1 - 0.002)
    assert benchmark_returns["1d"] == pytest.approx(202 / 201 - 1)
    assert excess["1d"] == pytest.approx(returns["1d"] - benchmark_returns["1d"])


def test_episode_dedup_resets_after_inactive_observations() -> None:
    events = []
    for day, score in enumerate([6, 6, 6, 0, 0, 0, 0, 0, 6], 1):
        events.append(
            BacktestEvent(
                f"2024-01-{day:02d}",
                "TEST",
                "US",
                "x",
                score,
                10,
                "ordinary",
                False,
            )
        )
    selected = _episode_events(events, 6, 5)
    assert [event.signal_date for event in selected] == ["2024-01-01", "2024-01-09"]
