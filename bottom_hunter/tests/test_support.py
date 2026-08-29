from __future__ import annotations

import numpy as np
import pandas as pd
from bottom_hunter.src.support import (
    detect_breakout,
    evaluate_resistance,
    evaluate_support,
    find_resistance_levels,
    find_support_levels,
)


def _flat_frame(days: int = 60, close: float = 100.0) -> pd.DataFrame:
    stamps = pd.bdate_range("2024-01-02", periods=days)
    frame = pd.DataFrame(index=stamps)
    frame["close"] = float(close)
    frame["open"] = close + 0.2
    frame["high"] = close + 1.0
    frame["low"] = close - 0.8
    frame["volume"] = 100.0
    return frame


def test_swing_lows_are_detected_from_history_only() -> None:
    days = 80
    stamps = pd.bdate_range("2024-01-02", periods=days)
    close = np.linspace(110, 95, days)
    frame = pd.DataFrame(index=stamps)
    frame["close"] = close
    frame["open"] = close + 0.1
    frame["high"] = close + 0.6
    frame["low"] = close - 0.4
    frame["volume"] = 100.0
    # Two clear swing lows in the past.
    frame.iloc[30, frame.columns.get_loc("low")] = 96.0
    frame.iloc[31:34, frame.columns.get_loc("low")] = 97.0
    frame.iloc[60, frame.columns.get_loc("low")] = 98.0
    frame.iloc[61:66, frame.columns.get_loc("low")] = 99.0
    target = stamps[-1].date()
    levels = find_support_levels(frame, target)
    assert 96.0 in levels
    assert 98.0 in levels


def test_support_confirmed_on_retest_and_hold() -> None:
    frame = _flat_frame()
    # A past swing low at 95.0, then the target day retests it and closes above.
    frame.iloc[20, frame.columns.get_loc("low")] = 95.0
    frame.iloc[21:26, frame.columns.get_loc("low")] = 96.0
    target = frame.index[-1].date()
    frame.iloc[-1, frame.columns.get_loc("low")] = 95.3
    frame.iloc[-1, frame.columns.get_loc("close")] = 96.5
    score, level, reasons, metrics = evaluate_support(frame, target)
    assert score == 1
    assert level == 95.0
    assert reasons and "回踩支撑位" in reasons[0]
    assert metrics["support_level"] == 95.0


def test_no_points_when_price_drifts_far_above_support() -> None:
    frame = _flat_frame()
    target = frame.index[-1].date()
    frame.iloc[-1, frame.columns.get_loc("close")] = 120.0
    frame.iloc[-1, frame.columns.get_loc("low")] = 118.0
    score, _level, _reasons, _metrics = evaluate_support(frame, target)
    assert score == 0


def test_capitulation_low_is_used_as_anchor() -> None:
    frame = _flat_frame()
    target = frame.index[-1].date()
    frame.iloc[-1, frame.columns.get_loc("low")] = 94.8
    frame.iloc[-1, frame.columns.get_loc("close")] = 95.4
    score, level, _reasons, _metrics = evaluate_support(frame, target, extra_levels=[95.0])
    assert score == 1
    assert level == 95.0


def test_no_lookahead_future_bars_do_not_change_support() -> None:
    frame = _flat_frame()
    target = frame.index[-2].date()
    prefix = frame.iloc[:-1]
    future_changed = frame.copy()
    future_changed.iloc[-1, future_changed.columns.get_loc("low")] = 50.0
    assert evaluate_support(prefix, target) == evaluate_support(future_changed, target)


def test_swing_highs_are_detected_for_resistance() -> None:
    days = 80
    stamps = pd.bdate_range("2024-01-02", periods=days)
    close = np.linspace(90, 105, days)
    frame = pd.DataFrame(index=stamps)
    frame["close"] = close
    frame["open"] = close - 0.1
    frame["high"] = close + 0.4
    frame["low"] = close - 0.6
    frame["volume"] = 100.0
    # Two clear swing highs in the past.
    frame.iloc[30, frame.columns.get_loc("high")] = 100.0
    frame.iloc[31:34, frame.columns.get_loc("high")] = 99.0
    frame.iloc[60, frame.columns.get_loc("high")] = 102.0
    frame.iloc[61:66, frame.columns.get_loc("high")] = 101.0
    target = stamps[-1].date()
    levels = find_resistance_levels(frame, target)
    assert 100.0 in levels
    assert 102.0 in levels


def test_resistance_capped_when_close_below_nearest_level() -> None:
    days = 60
    stamps = pd.bdate_range("2024-01-02", periods=days)
    frame = pd.DataFrame(index=stamps)
    frame["close"] = 100.0
    frame["open"] = 100.0
    frame["high"] = 100.2
    frame["low"] = 99.8
    frame["volume"] = 100.0
    frame.iloc[20, frame.columns.get_loc("high")] = 103.0
    frame.iloc[21:26, frame.columns.get_loc("high")] = 101.0
    target = frame.index[-1].date()
    frame.iloc[-1, frame.columns.get_loc("close")] = 102.5
    frame.iloc[-1, frame.columns.get_loc("high")] = 102.8
    level, distance, breakout, reasons, metrics = evaluate_resistance(frame, target)
    assert level == 103.0
    assert breakout is False
    assert distance is not None and 0 < distance <= 0.03
    assert any("空间受限" in reason for reason in reasons)
    assert metrics["resistance_breakout"] is False


def test_resistance_breakout_when_close_above_prior_high() -> None:
    days = 60
    stamps = pd.bdate_range("2024-01-02", periods=days)
    frame = pd.DataFrame(index=stamps)
    frame["close"] = 98.0
    frame["open"] = 98.0
    frame["high"] = 98.2
    frame["low"] = 97.8
    frame["volume"] = 100.0
    frame.iloc[20, frame.columns.get_loc("high")] = 99.0
    frame.iloc[21:26, frame.columns.get_loc("high")] = 98.5
    target = frame.index[-1].date()
    frame.iloc[-1, frame.columns.get_loc("close")] = 99.5
    frame.iloc[-1, frame.columns.get_loc("high")] = 99.8
    level, _distance, breakout, reasons, metrics = evaluate_resistance(frame, target)
    assert level == 99.0
    assert breakout is True
    assert any("突破" in reason for reason in reasons)
    assert metrics["resistance_breakout"] is True


def test_resistance_no_lookahead() -> None:
    frame = _flat_frame()
    target = frame.index[-2].date()
    prefix = frame.iloc[:-1]
    future_changed = frame.copy()
    future_changed.iloc[-1, future_changed.columns.get_loc("high")] = 300.0
    assert evaluate_resistance(prefix, target) == evaluate_resistance(future_changed, target)


def test_breakout_requires_volume_and_ma20() -> None:
    days = 60
    stamps = pd.bdate_range("2024-01-02", periods=days)
    frame = pd.DataFrame(index=stamps)
    frame["close"] = 98.0
    frame["open"] = 98.0
    frame["high"] = 98.2
    frame["low"] = 97.8
    frame["volume"] = 100.0
    frame["ma20"] = 97.0
    frame["volume_ratio"] = 1.0
    frame.iloc[20, frame.columns.get_loc("high")] = 99.0
    frame.iloc[21:26, frame.columns.get_loc("high")] = 98.5
    target = frame.index[-1].date()
    # Close above the level but weak volume → rejected.
    frame.iloc[-1, frame.columns.get_loc("close")] = 99.5
    frame.iloc[-1, frame.columns.get_loc("volume_ratio")] = 1.2
    assert detect_breakout(frame, target)[0] is False
    # Volume confirmed and above MA20 → breakout candidate.
    frame.iloc[-1, frame.columns.get_loc("volume_ratio")] = 1.8
    detected, level, reasons = detect_breakout(frame, target)
    assert detected is True
    assert level == 99.0
    assert reasons and "突破候选" in reasons[0]
    # Far above the level within a single gap → chase risk, rejected.
    frame.iloc[-1, frame.columns.get_loc("close")] = 103.0
    assert detect_breakout(frame, target)[0] is False
