from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from bottom_hunter.src.models import BreadthResult, ScoreBreakdown, SignalLevel
from bottom_hunter.src.scoring import CapitulationEvent, ScoreResult
from bottom_hunter.src.state_machine import decide_state, stage_rank


def _bars(days: int = 40, end: date | None = None) -> pd.DataFrame:
    end = end or date(2024, 3, 28)
    stamps = pd.bdate_range(end=pd.Timestamp(end), periods=days)
    close = np.linspace(100, 90, days)
    frame = pd.DataFrame(
        {
            "close": close,
            "ma10": close + 2.0,
        },
        index=stamps,
    )
    return frame


def _breadth(
    target: date,
    *,
    breadth_score: int = 0,
    breadth_ready: bool = False,
    worsening: bool = False,
) -> BreadthResult:
    return BreadthResult(
        date=target,
        sector_id="x",
        market="US",
        asset_count=3,
        up_ratio=0.6,
        down_ratio=0.2,
        new_low_ratio=0.1,
        new_high_ratio=0.0,
        above_ma5_ratio=0.5,
        above_ma10_ratio=0.5,
        strong_up_ratio=0.2,
        breadth_score=breadth_score,
        improving=True,
        etf_up=None,
        coverage=1.0,
        worsening=worsening,
        breadth_ready=breadth_ready,
    )


def _score(
    *,
    oversold: int = 2,
    capitulation: int = 2,
    rejection: int = 2,
    failure: bool = False,
) -> ScoreResult:
    return ScoreResult(
        score=ScoreBreakdown(oversold, capitulation, rejection, 1, 2, 0),
        signal_level=SignalLevel.WATCH,
        metrics={},
        reasons=[],
        risks=[],
        capitulation=None,
        relative_strength_turn=False,
        failure=failure,
    )


def _event(bars: pd.DataFrame, event_date: date) -> CapitulationEvent:
    row = bars.loc[pd.Timestamp(event_date)]
    return CapitulationEvent(
        event_date=event_date,
        low=float(row["close"]),
        high=float(row["close"]),
        close=float(row["close"]),
        strong=True,
    )


def test_stage3_reachable_with_breadth_ready_and_leaders() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    event_date = bars.index[-4].date()
    scored = _score(rejection=2)
    scored.capitulation = _event(bars, event_date)
    breadth = _breadth(target, breadth_score=0, breadth_ready=True)
    decision = decide_state(scored, bars, target, breadth, "Risk-On", True)
    assert decision.state.value == "BREADTH_CONFIRM"
    assert decision.entry_stage is not None
    assert decision.entry_stage.value == "ENTRY_STAGE_3"
    assert stage_rank(decision.entry_stage) == 3


def test_stage3_with_full_breadth_score_and_no_etf_required() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    event_date = bars.index[-4].date()
    scored = _score(rejection=2)
    scored.capitulation = _event(bars, event_date)
    breadth = _breadth(target, breadth_score=1, breadth_ready=True)
    decision = decide_state(scored, bars, target, breadth, "Risk-On", True)
    assert decision.entry_stage is not None
    assert decision.entry_stage.value == "ENTRY_STAGE_3"


def test_stage3_blocked_when_breadth_not_confirmed() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    event_date = bars.index[-4].date()
    scored = _score(rejection=2)
    scored.capitulation = _event(bars, event_date)
    breadth = _breadth(target, breadth_score=0, breadth_ready=False)
    decision = decide_state(scored, bars, target, breadth, "Risk-On", True)
    assert decision.entry_stage is not None
    assert decision.entry_stage.value == "ENTRY_STAGE_2"


def test_stage1_on_reversal_day() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    scored = _score(oversold=2, capitulation=2, rejection=0)
    scored.capitulation = _event(bars, target)
    decision = decide_state(scored, bars, target, _breadth(target), "Neutral")
    assert decision.state.value == "REVERSAL_DAY"
    assert decision.entry_stage is not None
    assert decision.entry_stage.value == "ENTRY_STAGE_1"


def test_capitulation_state_when_not_strong() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    scored = _score(oversold=2, capitulation=1, rejection=0)
    scored.capitulation = _event(bars, target)
    decision = decide_state(scored, bars, target, _breadth(target), "Neutral")
    assert decision.state.value == "CAPITULATION"
    assert decision.entry_stage is None


def test_failed_when_result_marks_failure() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    decision = decide_state(_score(failure=True), bars, target, _breadth(target), "Neutral")
    assert decision.state.value == "FAILED"
    assert decision.entry_stage is None


def test_failed_when_breadth_worsening_during_event() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    event_date = bars.index[-4].date()
    scored = _score(rejection=2)
    scored.capitulation = _event(bars, event_date)
    breadth = _breadth(target, breadth_score=1, breadth_ready=True, worsening=True)
    decision = decide_state(scored, bars, target, breadth, "Risk-On", True)
    assert decision.state.value == "FAILED"


def test_sell_off_when_oversold_without_event() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    decision = decide_state(_score(rejection=0), bars, target, _breadth(target), "Neutral")
    assert decision.state.value == "SELL_OFF"
    assert decision.entry_stage is None


def test_stage2_only_within_three_sessions() -> None:
    bars = _bars()
    target = bars.index[-1].date()
    event_date = bars.index[-8].date()
    scored = _score(rejection=2)
    scored.capitulation = _event(bars, event_date)
    breadth = _breadth(target)
    decision = decide_state(scored, bars, target, breadth, "Risk-On", True)
    assert decision.entry_stage is None
