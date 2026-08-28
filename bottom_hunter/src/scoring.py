from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from .indicators import aligned_returns, enrich_bars
from .models import BreadthResult, FundamentalResult, ScoreBreakdown, SignalLevel
from .support import evaluate_support
from .trading_calendar import TimingWindow


@dataclass(frozen=True)
class CapitulationEvent:
    event_date: date
    low: float
    high: float
    close: float
    strong: bool


@dataclass
class ScoreResult:
    score: ScoreBreakdown
    signal_level: SignalLevel
    metrics: dict[str, Any]
    reasons: list[str]
    risks: list[str]
    capitulation: CapitulationEvent | None
    relative_strength_turn: bool
    failure: bool


def score_oversold(row: pd.Series, settings: dict) -> tuple[int, list[str]]:
    severe_hits = [
        row["drawdown_20"] <= settings["severe_drawdown_20"],
        row["drawdown_60"] <= settings["severe_drawdown_60"],
        row["rsi14"] < settings["severe_rsi"],
        row["ma20_distance"] <= settings["severe_ma20_distance"],
    ]
    moderate_hits = [
        row["drawdown_20"] <= settings["moderate_drawdown_20"],
        row["rsi14"] < settings["moderate_rsi"],
        row["ma20_distance"] <= settings["moderate_ma20_distance"],
        row["return_10d"] <= settings["moderate_drawdown_20"],
    ]
    severe_count, moderate_count = sum(bool(value) for value in severe_hits), sum(
        bool(value) for value in moderate_hits
    )
    if severe_count >= 2 or (severe_count >= 1 and moderate_count >= 3):
        score = 2
    elif severe_count >= 1 or moderate_count >= 2:
        score = 1
    else:
        score = 0
    reasons = [
        f"20日回撤 {row['drawdown_20']:.1%}",
        f"60日高点回撤 {row['drawdown_60']:.1%}",
        f"RSI14 {row['rsi14']:.1f}",
        f"相对MA20 {row['ma20_distance']:.1%}",
    ]
    return score, reasons


def capitulation_score(row: pd.Series, settings: dict) -> int:
    new_low = bool(row["new_low_20"] or row["new_low_60"])
    volume = row["volume_ratio"]
    range_atr = row["range_atr"]
    recovered = row["close_position"] >= settings["close_position_strong"]
    panic = row["intraday_low_return"] <= settings["intraday_drop"]
    shadow = row["lower_shadow_ratio"] >= settings["lower_shadow_ratio"]
    strong = (
        new_low
        and volume >= settings["volume_ratio_strong"]
        and range_atr >= settings["range_atr_strong"]
        and panic
        and recovered
        and shadow
    )
    weak = (
        new_low
        and volume >= settings["volume_ratio_weak"]
        and range_atr >= settings["range_atr_weak"]
        and (panic or shadow)
        and row["close_position"] >= settings["close_position_weak"]
    )
    return 2 if strong else 1 if weak else 0


def find_latest_capitulation(
    bars: pd.DataFrame, target: date, settings: dict, exclude_target: bool = False
) -> CapitulationEvent | None:
    current = bars.loc[: pd.Timestamp(target)].tail(int(settings["lookback_days"]) + 1)
    if exclude_target and not current.empty and current.index[-1].date() == target:
        current = current.iloc[:-1]
    if current.empty:
        return None
    found: CapitulationEvent | None = None
    for stamp, row in current.iterrows():
        score = capitulation_score(row, settings)
        if score:
            found = CapitulationEvent(
                event_date=stamp.date(),
                low=float(row["low"]),
                high=float(row["high"]),
                close=float(row["close"]),
                strong=score == 2,
            )
    return found


def _benchmark_new_low(reference: pd.DataFrame | None, target: date) -> bool:
    if reference is None or reference.empty:
        return False
    enriched = reference if "new_low_20" in reference.columns else enrich_bars(reference)
    stamp = pd.Timestamp(target)
    return bool(stamp in enriched.index and enriched.at[stamp, "new_low_20"])


def score_rejection(
    bars: pd.DataFrame,
    target: date,
    capitulation: CapitulationEvent | None,
    reference: pd.DataFrame | None,
    settings: dict,
) -> tuple[int, bool, bool, list[str]]:
    if capitulation is None:
        return 0, False, False, []
    event_stamp, target_stamp = pd.Timestamp(capitulation.event_date), pd.Timestamp(target)
    since = bars.loc[event_stamp:target_stamp]
    if since.empty:
        return 0, False, False, []
    latest = since.iloc[-1]
    post = since.iloc[1:]
    break_ratio = float(latest["low"] / capitulation.low - 1)
    consecutive_new_lows = bool(
        len(post) >= 2 and post["low"].iloc[-1] < capitulation.low and post["low"].iloc[-2] < capitulation.low
    )
    volume_break = bool(
        break_ratio < -settings["failure_break"]
        and latest["return_1d"] < 0
        and latest["volume_ratio"] >= settings.get("volume_ratio_weak", 1.2)
    )
    failure = bool(break_ratio < -settings["failure_break"] or consecutive_new_lows or volume_break)
    if failure:
        return 0, False, True, [f"跌破恐慌低点 {break_ratio:.1%}，底部结构失效"]
    if target == capitulation.event_date:
        return 0, False, False, []
    tolerance = settings["slight_break_tolerance"]
    held = break_ratio >= -tolerance
    broke_event_high = latest["close"] > capitulation.high
    closed_above_prior = latest["close"] > bars["close"].shift(1).loc[target_stamp]
    pattern = bool(
        latest["bullish_engulfing"]
        or latest["morning_star"]
        or latest["long_lower_shadow"]
        or latest["higher_low_2"]
    )
    index_divergence = _benchmark_new_low(reference, target) and held
    relative_turn = bool(index_divergence or (held and latest["return_1d"] > 0))
    confirmations = sum([held, broke_event_high, closed_above_prior, pattern, index_divergence])
    score = 2 if held and confirmations >= 2 else 1 if held else 0
    reasons: list[str] = []
    if held:
        reasons.append(f"恐慌低点后第{len(post)}个交易日未明显创新低")
    if broke_event_high:
        reasons.append("收盘突破恐慌日最高价")
    if pattern:
        reasons.append("出现反转K线/连续低点抬高")
    if index_divergence:
        reasons.append("指数创新低但个股拒绝创新低")
    return score, relative_turn, False, reasons


def classify_signal(total: int, fundamental_available: bool) -> SignalLevel:
    # Missing fundamentals never blocks a technical watch signal, but it caps the
    # action level below BUY CANDIDATE because the nominal 11-point score is incomplete.
    if total <= 4:
        return SignalLevel.IGNORE
    if total <= 6:
        return SignalLevel.WATCH
    if not fundamental_available:
        return SignalLevel.EARLY_REVERSAL
    if total == 7:
        return SignalLevel.EARLY_REVERSAL
    if total <= 10:
        return SignalLevel.BUY_CANDIDATE
    return SignalLevel.STRONG_REVERSAL


def score_stock(
    bars: pd.DataFrame,
    target: date,
    thresholds: dict,
    breadth: BreadthResult,
    fundamental: FundamentalResult,
    timing: TimingWindow,
    sector_reference: pd.DataFrame | None = None,
    market_reference: pd.DataFrame | None = None,
) -> ScoreResult:
    enriched = bars if "rsi14" in bars.columns else enrich_bars(bars)
    stamp = pd.Timestamp(target)
    if stamp not in enriched.index:
        raise ValueError(f"{target} 无交易数据")
    row = enriched.loc[stamp]
    oversold, oversold_reasons = score_oversold(row, thresholds["oversold"])
    current_cap = capitulation_score(row, thresholds["capitulation"])
    rejection_settings = {**thresholds["capitulation"], **thresholds["rejection"]}
    event = find_latest_capitulation(enriched, target, rejection_settings)
    previous_event = (
        find_latest_capitulation(enriched, target, rejection_settings, exclude_target=True)
        if event is not None and event.event_date == target
        else None
    )
    rejection, relative_turn, failure, rejection_reasons = score_rejection(
        enriched,
        target,
        previous_event or event,
        market_reference,
        rejection_settings,
    )
    if failure and previous_event is not None:
        event = previous_event
    support_score, _support_level, support_reasons, support_metrics = evaluate_support(
        enriched,
        target,
        thresholds.get("support"),
        extra_levels=[event.low] if event is not None else [],
    )
    breakdown = ScoreBreakdown(
        oversold=oversold,
        capitulation=(
            current_cap
            if event and event.event_date == target
            else (2 if event and event.strong else 1 if event else 0)
        ),
        rejection=rejection,
        breadth=breadth.breadth_score,
        fundamental=fundamental.score,
        timing=timing.score,
        support=support_score,
    )
    sector_rs = (
        aligned_returns(enriched.loc[:stamp], sector_reference.loc[:stamp])
        if sector_reference is not None
        else {f"rs_{days}d": np.nan for days in (1, 3, 5, 10)}
    )
    market_rs = (
        aligned_returns(enriched.loc[:stamp], market_reference.loc[:stamp])
        if market_reference is not None
        else {f"rs_{days}d": np.nan for days in (1, 3, 5, 10)}
    )
    metrics: dict[str, Any] = {
        key: float(row[key]) if pd.notna(row[key]) else None
        for key in (
            "close",
            "return_1d",
            "return_5d",
            "return_10d",
            "return_20d",
            "drawdown_20",
            "drawdown_60",
            "rsi14",
            "ma20_distance",
            "volume_ratio",
            "range_atr",
            "close_position",
            "lower_shadow_ratio",
        )
    }
    metrics.update(
        {
            f"sector_{key}": float(value) if pd.notna(value) else None
            for key, value in sector_rs.items()
        }
    )
    metrics["index_new_low_stock_holds"] = bool(
        event is not None
        and rejection > 0
        and _benchmark_new_low(market_reference, target)
    )
    metrics.update(
        {
            f"market_{key}": float(value) if pd.notna(value) else None
            for key, value in market_rs.items()
        }
    )
    metrics.update(support_metrics)
    relative_turn = bool(
        relative_turn
        or (
            (sector_rs.get("rs_1d", np.nan) > 0)
            and (sector_rs.get("rs_3d", np.nan) > 0)
            and row["return_1d"] > 0
        )
    )
    reasons = oversold_reasons
    if current_cap:
        reasons.append(
            f"恐慌抛售结构：量比 {row['volume_ratio']:.2f}、收盘位置 {row['close_position']:.0%}"
        )
    reasons.extend(rejection_reasons)
    reasons.extend(support_reasons)
    reasons.append(
        f"板块上涨 {breadth.up_ratio:.0%}，宽度{'改善' if breadth.improving else '未确认'}"
    )
    if fundamental.score is None:
        reasons.append("基本面数据不足，需要人工确认。")
    else:
        reasons.append(f"基本面 {fundamental.score}/2：{fundamental.reason}")
        if fundamental.score == 0:
            failure = True
            reasons.append("可靠的人工基本面数据标记为重大破坏，底部结构失效")
    if timing.score:
        reasons.append(f"处于{timing.label}（仅作赔率加分）")
    risks: list[str] = []
    if event:
        risks.append(
            f"若收盘/低点明显跌破恐慌低点 {event.low:.2f}（约2%），信号失效"
        )
    if _support_level is not None:
        risks.append(f"若收盘明显跌破支撑位 {_support_level:.2f}，支撑确认作废")
    if fundamental.score is None:
        risks.append("基本面未验证，禁止据此直接交易")
    return ScoreResult(
        score=breakdown,
        signal_level=SignalLevel.FAILED if failure else classify_signal(
            breakdown.total, fundamental.score is not None
        ),
        metrics=metrics,
        reasons=reasons,
        risks=risks,
        capitulation=event,
        relative_strength_turn=relative_turn,
        failure=failure,
    )
