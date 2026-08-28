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
    "cap_band": 0.03,
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


def find_resistance_levels(
    enriched: pd.DataFrame,
    target: date,
    settings: dict | None = None,
) -> list[float]:
    """Swing highs from history before the target; never uses future bars."""
    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    stamp = pd.Timestamp(target)
    history = enriched.loc[:stamp]
    if len(history) > 1:
        history = history.iloc[:-1]
    history = history.tail(int(merged["lookback_days"]))
    if history.empty:
        return []
    window = max(1, int(merged["swing_window"]))
    highs = history["high"]
    rolling_max = highs.rolling(2 * window + 1, center=True, min_periods=window + 1).max()
    swing = highs[highs == rolling_max].dropna()
    return sorted({round(float(value), 6) for value in swing})


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


def detect_breakout(
    enriched: pd.DataFrame,
    target: date,
    settings: dict | None = None,
) -> tuple[bool, float | None, list[str]]:
    """Second signal class: trend-following breakout above resistance.

    Requires (all causal): close above the nearest prior swing high,
    volume ratio at/above `breakout_volume`, close above MA20, and the
    day not in an already-flagged capitulation-failure state.
    """
    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    stamp = pd.Timestamp(target)
    if stamp not in enriched.index:
        return False, None, []
    row = enriched.loc[stamp]
    close = float(row["close"])
    levels = find_resistance_levels(enriched, target, merged)
    below = [level for level in levels if level < close]
    if not below:
        return False, None, []
    broken_level = max(below)
    if close / broken_level - 1 > float(merged["touch_band"]):
        # Too far above the level — chase risk, not a fresh breakout.
        return False, broken_level, []
    volume_ratio = float(row.get("volume_ratio", float("nan")))
    ma20 = row.get("ma20")
    reasons: list[str] = []
    if not (pd.notna(volume_ratio) and volume_ratio >= 1.5):
        return False, broken_level, []
    if ma20 is None or pd.isna(ma20) or close <= float(ma20):
        return False, broken_level, []
    reasons.append(
        f"突破候选：收盘 {close:.2f} 越过压力位 {broken_level:.2f}，"
        f"量比 {volume_ratio:.2f}、站上 MA20"
    )
    return True, broken_level, reasons


def evaluate_resistance(
    enriched: pd.DataFrame,
    target: date,
    settings: dict | None = None,
) -> tuple[float | None, float | None, bool, list[str], dict]:
    """Grade the target day against the nearest resistance level above.

    Returns (nearest level, distance, breakout flag, reasons, metrics).
    Resistance is contextual only — it never changes the point total.
    """
    merged = {**DEFAULT_SETTINGS, **(settings or {})}
    stamp = pd.Timestamp(target)
    empty = {"resistance_level": None, "resistance_distance": None, "resistance_breakout": False}
    if stamp not in enriched.index:
        return None, None, False, [], empty
    close = float(enriched.at[stamp, "close"])
    all_levels = find_resistance_levels(enriched, target, merged)
    above = [level for level in all_levels if level >= close]
    broken = [
        level
        for level in all_levels
        if level < close and level >= close * (1 - float(merged["touch_band"]))
    ]
    metrics = {
        "resistance_level": None,
        "resistance_distance": None,
        "resistance_breakout": False,
    }
    if above:
        nearest = min(above)
        distance = nearest / close - 1
        metrics = {
            "resistance_level": nearest,
            "resistance_distance": float(distance),
            "resistance_breakout": False,
        }
        if distance <= float(merged["cap_band"]):
            reasons = [f"上方压力位 {nearest:.2f} 仅距 {distance:.1%}，反弹空间受限"]
        else:
            reasons = [f"上方压力位 {nearest:.2f}，距离 {distance:.1%}"]
        return nearest, float(distance), False, reasons, metrics
    if broken:
        nearest = max(broken)
        distance = nearest / close - 1
        metrics = {
            "resistance_level": nearest,
            "resistance_distance": float(distance),
            "resistance_breakout": True,
        }
        reasons = [f"收盘已突破近期压力位 {nearest:.2f}，压力转为支撑参考"]
        return nearest, float(distance), True, reasons, metrics
    return None, None, False, ["上方无明显历史压力位"], metrics
