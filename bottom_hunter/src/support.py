"""Causal support-level detection for the bottom-hunting score.

A support level is identified only from data strictly before the target
date (swing lows) plus optional event anchors such as the capitulation
low. The target day is then graded on how it interacts with the nearest
level below: touching the zone and closing at/above it earns the
support point; drifting far above an untouched level does not.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

DEFAULT_SETTINGS = {
    "lookback_days": 120,
    "swing_window": 5,
    "touch_band": 0.02,
    "max_above": 0.05,
    "min_history": 40,
}


def find_support_levels(
    enriched: pd.DataFrame,
    target: date,
    settings: dict | None = None,
) -> list[float]:
    """Swing lows from history before the target; never uses future bars."""
    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    stamp = pd.Timestamp(target)
    history = enriched.loc[:stamp]
    if len(history) > 1:
        history = history.iloc[:-1]
    history = history.tail(int(merged["lookback_days"]))
    if history.empty:
        return []
    window = max(1, int(merged["swing_window"]))
    lows = history["low"]
    rolling_min = lows.rolling(2 * window + 1, center=True, min_periods=window + 1).min()
    swing = lows[lows == rolling_min].dropna()
    levels = {round(float(value), 6) for value in swing}
    ma200 = history["close"].rolling(200, min_periods=200).mean().dropna()
    if not ma200.empty:
        levels.add(round(float(ma200.iloc[-1]), 6))
    return sorted(levels)


def evaluate_support(
    enriched: pd.DataFrame,
    target: date,
    settings: dict | None = None,
    extra_levels: list[float] | None = None,
) -> tuple[int, float | None, list[str], dict]:
    """Score the target day against its nearest support level below.

    Returns (score 0/1, nearest level, reasons, metrics).
    """
    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    stamp = pd.Timestamp(target)
    if stamp not in enriched.index:
        return 0, None, [], {"support_level": None, "support_distance": None, "support_confluence": 0}
    row = enriched.loc[stamp]
    levels = set(find_support_levels(enriched, target, merged))
    for value in extra_levels or ():
        if value and pd.notna(value) and value > 0:
            levels.add(round(float(value), 6))
    metrics = {"support_level": None, "support_distance": None, "support_confluence": 0}
    if not levels:
        return 0, None, ["未识别到可用支撑位（历史摆动低点不足）"], metrics
    close = float(row["close"])
    day_low = float(row["low"])
    candidates = [level for level in levels if level <= close * (1 + float(merged["touch_band"]))]
    if not candidates:
        return 0, None, ["收盘价下方无邻近支撑位"], metrics
    nearest = max(candidates)
    distance = close / nearest - 1
    confluence = sum(
        1 for level in levels if abs(level - nearest) / nearest <= float(merged["touch_band"])
    )
    metrics = {
        "support_level": nearest,
        "support_distance": float(distance),
        "support_confluence": confluence,
    }
    touched = day_low <= nearest * (1 + float(merged["touch_band"]))
    held = close >= nearest
    near = distance <= float(merged["max_above"])
    if touched and held and near:
        reason = (
            f"回踩支撑位 {nearest:.2f} 后收于其上（距离 {distance:.1%}，"
            f"共振 {confluence} 处）"
        )
        return 1, nearest, [reason], metrics
    side = "上方" if distance >= 0 else "下方"
    return (
        0,
        nearest,
        [f"收盘位于支撑位 {nearest:.2f} {side} {abs(distance):.1%}，未形成支撑确认"],
        metrics,
    )
