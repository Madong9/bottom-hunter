from __future__ import annotations

import pandas as pd

from bottom_hunter.src.breadth import calculate_breadth
from bottom_hunter.src.models import BreadthResult, FundamentalResult
from bottom_hunter.src.scoring import score_stock
from bottom_hunter.src.state_machine import decide_state
from bottom_hunter.src.config import AppConfig
from bottom_hunter.src.indicators import enrich_bars


def _frame(target, up: bool, was_low: bool, is_low: bool) -> pd.DataFrame:
    prior = pd.Timestamp(target) - pd.offsets.BDay(1)
    change = 0.03 if up else -0.01
    return pd.DataFrame(
        {
            "rsi14": [30, 35],
            "return_1d": [-0.02, change],
            "close": [90, 90 * (1 + change)],
            "ma5": [92, 89],
            "ma10": [94, 89],
            "new_low_20": [was_low, is_low],
            "new_high_20": [False, False],
        },
        index=[prior, pd.Timestamp(target)],
    )


def test_breadth_needs_up_ratio_low_contraction_and_etf() -> None:
    target = pd.Timestamp("2024-03-28").date()
    frames = {
        "A": _frame(target, True, True, False),
        "B": _frame(target, True, True, False),
        "C": _frame(target, False, False, False),
    }
    etf = _frame(target, True, False, False)
    result = calculate_breadth(
        "test", "US", frames, target, 3, {"up_ratio": 0.6, "strong_up_return": 0.02}, etf
    )
    assert result.up_ratio == 2 / 3
    assert result.improving is True
    assert result.etf_up is True
    assert result.breadth_score == 1


def test_state_two_after_confirmed_rejection(selloff_bars) -> None:
    target = selloff_bars.index[-1].date()
    settings = AppConfig.load().defaults
    breadth = BreadthResult(
        target, "x", "US", 2, 1, 0, 0, 0, 1, 1, 1, 1, True, True, 1
    )
    scored = score_stock(
        selloff_bars,
        target,
        settings,
        breadth,
        FundamentalResult(2, "人工确认", "test", target),
        type("Timing", (), {"score": 0, "label": "普通交易日"})(),
    )
    decision = decide_state(scored, enrich_bars(selloff_bars), target, breadth, "Neutral")
    assert decision.entry_stage is not None
    assert decision.entry_stage.value == "ENTRY_STAGE_2"

