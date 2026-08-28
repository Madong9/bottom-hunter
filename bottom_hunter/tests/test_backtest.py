from __future__ import annotations

import pandas as pd
import pytest
from bottom_hunter.src.backtest import BacktestEvent, _forward_metrics, summarize_events


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
        {f"{day}d": 0.1 for day in (3, 5, 10, 20, 60)},
        {f"{day}d": -0.03 for day in (3, 5, 10, 20, 60)},
    )
    summary = summarize_events([event])
    stats = summary["score_gte_8"]["quarter_window"]["5d"]
    assert stats["sample_size"] == 1
    assert stats["win_rate"] == 1.0
    assert stats["average_return"] == 0.1
    assert stats["max_drawdown"] == -0.03
