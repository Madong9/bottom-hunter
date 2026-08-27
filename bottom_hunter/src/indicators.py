from __future__ import annotations

import numpy as np
import pandas as pd


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, np.nan)
    return numerator / denominator


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI without backward filling startup values."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    relative = safe_divide(avg_gain, avg_loss)
    result = 100 - 100 / (1 + relative)
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    result = result.mask((avg_loss == 0) & (avg_gain == 0), 50.0)
    return result


def true_range(bars: pd.DataFrame) -> pd.Series:
    previous_close = bars["close"].shift(1)
    return pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - previous_close).abs(),
            (bars["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(bars).ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def bullish_engulfing(bars: pd.DataFrame) -> pd.Series:
    previous_bearish = bars["close"].shift(1) < bars["open"].shift(1)
    current_bullish = bars["close"] > bars["open"]
    engulfs = (bars["open"] <= bars["close"].shift(1)) & (
        bars["close"] >= bars["open"].shift(1)
    )
    return (previous_bearish & current_bullish & engulfs).fillna(False)


def morning_star(bars: pd.DataFrame) -> pd.Series:
    body = (bars["close"] - bars["open"]).abs()
    first_bearish = bars["close"].shift(2) < bars["open"].shift(2)
    small_middle = body.shift(1) <= body.shift(2) * 0.5
    third_bullish = bars["close"] > bars["open"]
    midpoint_first = (bars["open"].shift(2) + bars["close"].shift(2)) / 2
    recovery = bars["close"] >= midpoint_first
    return (first_bearish & small_middle & third_bullish & recovery).fillna(False)


def enrich_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Add causal indicators: every row only depends on that row and its past."""
    result = bars.copy().sort_index()
    close = result["close"]
    for days in (1, 3, 5, 10, 20, 60):
        result[f"return_{days}d"] = close.pct_change(days, fill_method=None)
    for days in (5, 10, 20):
        result[f"ma{days}"] = close.rolling(days, min_periods=days).mean()
    result["ma20_distance"] = safe_divide(close, result["ma20"]) - 1
    result["drawdown_20"] = safe_divide(
        close, close.rolling(20, min_periods=20).max()
    ) - 1
    result["drawdown_60"] = safe_divide(
        close, close.rolling(60, min_periods=60).max()
    ) - 1
    result["rsi14"] = rsi(close, 14)
    result["atr14"] = atr(result, 14)
    result["true_range"] = true_range(result)
    result["range_atr"] = safe_divide(result["true_range"], result["atr14"].shift(1))
    result["volume_ma20"] = result["volume"].shift(1).rolling(20, min_periods=20).mean()
    result["volume_ratio"] = safe_divide(result["volume"], result["volume_ma20"])
    candle_range = result["high"] - result["low"]
    result["close_position"] = safe_divide(result["close"] - result["low"], candle_range)
    body_low = result[["open", "close"]].min(axis=1)
    result["lower_shadow_ratio"] = safe_divide(body_low - result["low"], candle_range)
    result["intraday_low_return"] = safe_divide(result["low"], result["open"]) - 1
    prior_low20 = result["low"].shift(1).rolling(20, min_periods=20).min()
    prior_low60 = result["low"].shift(1).rolling(60, min_periods=60).min()
    prior_high20 = result["high"].shift(1).rolling(20, min_periods=20).max()
    result["new_low_20"] = (result["low"] <= prior_low20).fillna(False)
    result["new_low_60"] = (result["low"] <= prior_low60).fillna(False)
    result["new_high_20"] = (result["high"] >= prior_high20).fillna(False)
    result["bullish_engulfing"] = bullish_engulfing(result)
    result["morning_star"] = morning_star(result)
    result["long_lower_shadow"] = (
        (result["lower_shadow_ratio"] >= 0.40)
        & (result["close_position"] >= 0.60)
    ).fillna(False)
    result["higher_low_2"] = (
        (result["low"] > result["low"].shift(1))
        & (result["low"].shift(1) > result["low"].shift(2))
    ).fillna(False)
    return result


def aligned_returns(
    stock: pd.DataFrame, reference: pd.DataFrame, periods: tuple[int, ...] = (1, 3, 5, 10)
) -> dict[str, float]:
    joined = pd.concat(
        [stock["close"].rename("stock"), reference["close"].rename("reference")],
        axis=1,
        join="inner",
    ).dropna()
    output: dict[str, float] = {}
    for period in periods:
        if len(joined) <= period:
            output[f"rs_{period}d"] = np.nan
            continue
        stock_return = joined["stock"].iloc[-1] / joined["stock"].iloc[-period - 1] - 1
        reference_return = (
            joined["reference"].iloc[-1] / joined["reference"].iloc[-period - 1] - 1
        )
        output[f"rs_{period}d"] = float(stock_return - reference_return)
    return output


def normalized_relative_curve(stock: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    joined = pd.concat(
        [stock["close"].rename("stock"), reference["close"].rename("reference")],
        axis=1,
        join="inner",
    ).dropna()
    if joined.empty:
        return joined
    return joined / joined.iloc[0] * 100

