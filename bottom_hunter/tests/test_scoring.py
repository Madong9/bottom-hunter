from __future__ import annotations

from bottom_hunter.src.config import AppConfig
from bottom_hunter.src.indicators import enrich_bars
from bottom_hunter.src.models import BreadthResult, FundamentalResult, SignalLevel
from bottom_hunter.src.scoring import (
    capitulation_score,
    classify_signal,
    find_latest_capitulation,
    score_oversold,
    score_rejection,
    score_stock,
)
from bottom_hunter.src.trading_calendar import TimingWindow


def _breadth(target) -> BreadthResult:
    return BreadthResult(target, "test", "US", 3, 2 / 3, 1 / 3, 0, 0, 2 / 3, 2 / 3, 1 / 3, 1, True, True, 1)


def test_strong_capitulation_and_rejection(selloff_bars) -> None:
    settings = AppConfig.load().defaults
    enriched = enrich_bars(selloff_bars)
    panic_date = enriched.index[-2].date()
    target = enriched.index[-1].date()
    assert capitulation_score(enriched.iloc[-2], settings["capitulation"]) == 2
    event = find_latest_capitulation(enriched, target, {**settings["capitulation"], **settings["rejection"]})
    assert event is not None and event.event_date == panic_date
    score, relative, failed, reasons = score_rejection(
        enriched,
        target,
        event,
        None,
        {**settings["capitulation"], **settings["rejection"]},
    )
    assert score == 2
    assert relative is True
    assert failed is False
    assert reasons


def test_failure_when_capitulation_low_breaks(selloff_bars) -> None:
    settings = AppConfig.load().defaults
    broken = selloff_bars.copy()
    broken.iloc[-1, broken.columns.get_loc("low")] = 67.0
    broken.iloc[-1, broken.columns.get_loc("close")] = 68.0
    enriched = enrich_bars(broken)
    event = find_latest_capitulation(
        enriched,
        enriched.index[-1].date(),
        {**settings["capitulation"], **settings["rejection"]},
        exclude_target=True,
    )
    score, _, failed, _ = score_rejection(
        enriched,
        enriched.index[-1].date(),
        event,
        None,
        {**settings["capitulation"], **settings["rejection"]},
    )
    assert score == 0
    assert failed is True


def test_missing_fundamentals_are_not_awarded_two_points(selloff_bars) -> None:
    settings = AppConfig.load().defaults
    target = selloff_bars.index[-1].date()
    result = score_stock(
        selloff_bars,
        target,
        settings,
        _breadth(target),
        FundamentalResult(None, "基本面数据不足，需要人工确认。"),
        TimingWindow(1, True, False, False, False, True),
    )
    assert result.score.fundamental is None
    assert result.score.available_max == 8
    assert result.score.total <= 8


def test_score_on_target_is_unchanged_by_modified_future(selloff_bars) -> None:
    settings = AppConfig.load().defaults
    target = selloff_bars.index[-2].date()
    prefix = selloff_bars.iloc[:-1]
    future_changed = selloff_bars.copy()
    future_changed.iloc[-1, future_changed.columns.get_loc("close")] = 200.0
    future_changed.iloc[-1, future_changed.columns.get_loc("high")] = 210.0
    fundamental = FundamentalResult(None, "基本面数据不足，需要人工确认。")
    timing = TimingWindow(0, False, False, False, False, True)
    first = score_stock(prefix, target, settings, _breadth(target), fundamental, timing)
    second = score_stock(future_changed, target, settings, _breadth(target), fundamental, timing)
    assert first.score == second.score
    assert first.metrics == second.metrics


def test_oversold_requires_multiple_confirmations(selloff_bars) -> None:
    settings = AppConfig.load().defaults["oversold"]
    row = enrich_bars(selloff_bars).iloc[-2]
    score, reasons = score_oversold(row, settings)
    assert score >= 1
    assert len(reasons) == 4


def test_action_labels_require_rejection_and_validation_gate() -> None:
    assert classify_signal(9, True, rejection_score=0, action_signals_enabled=True) == SignalLevel.WATCH
    assert classify_signal(9, True, rejection_score=2, action_signals_enabled=False) == SignalLevel.EARLY_REVERSAL
    assert classify_signal(9, True, rejection_score=2, action_signals_enabled=True) == SignalLevel.BUY_CANDIDATE
