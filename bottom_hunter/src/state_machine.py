from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .models import BottomState, BreadthResult, EntryStage
from .scoring import ScoreResult


@dataclass(frozen=True)
class StateDecision:
    state: BottomState
    entry_stage: EntryStage | None
    allocation_hint: str | None


def decide_state(
    result: ScoreResult,
    bars: pd.DataFrame,
    target: date,
    breadth: BreadthResult,
    risk_environment: str,
    leaders_confirmed: bool = False,
) -> StateDecision:
    if result.failure:
        return StateDecision(BottomState.FAILED, None, None)
    stamp = pd.Timestamp(target)
    row = bars.loc[stamp]
    event = result.capitulation
    if event and breadth.worsening:
        return StateDecision(BottomState.FAILED, None, None)
    if event and event.event_date == target:
        if result.score.oversold == 2 and result.score.capitulation == 2:
            return StateDecision(
                BottomState.REVERSAL_DAY,
                EntryStage.ENTRY_STAGE_1,
                "计划仓位框架：试探 25%（不自动下单）",
            )
        return StateDecision(BottomState.CAPITULATION, None, None)
    if event and result.score.rejection >= 1:
        event_stamp = pd.Timestamp(event.event_date)
        sessions_after = max(0, len(bars.loc[event_stamp:stamp]) - 1)
        if (
            result.score.rejection == 2
            and (breadth.breadth_score == 1 or breadth.breadth_ready)
            and risk_environment == "Risk-On"
            and leaders_confirmed
        ):
            return StateDecision(
                BottomState.BREADTH_CONFIRM,
                EntryStage.ENTRY_STAGE_3,
                "计划仓位框架：补足剩余 40%（不自动下单）",
            )
        if result.score.rejection == 2 and sessions_after <= 3:
            return StateDecision(
                BottomState.NO_NEW_LOW,
                EntryStage.ENTRY_STAGE_2,
                "计划仓位框架：在试探仓基础上增加 35%（不自动下单）",
            )
        if result.score.rejection == 2 and row["close"] > row["ma10"]:
            return StateDecision(BottomState.TREND_CONFIRM, None, None)
        return StateDecision(BottomState.NO_NEW_LOW, None, None)
    if result.score.oversold:
        return StateDecision(BottomState.SELL_OFF, None, None)
    return StateDecision(BottomState.NORMAL, None, None)


def stage_rank(stage: EntryStage | None) -> int:
    return {
        None: 0,
        EntryStage.ENTRY_STAGE_1: 1,
        EntryStage.ENTRY_STAGE_2: 2,
        EntryStage.ENTRY_STAGE_3: 3,
    }[stage]
