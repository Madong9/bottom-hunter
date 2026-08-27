from __future__ import annotations

from datetime import date
from typing import Mapping

import numpy as np
import pandas as pd

from .indicators import enrich_bars
from .models import BreadthResult, SectorResult, StockSignal


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(np.clip(value, low, high))


def calculate_sector_score(
    sector_id: str,
    sector_name: str,
    market: str,
    target: date,
    frames: Mapping[str, pd.DataFrame],
    breadth: BreadthResult,
    signals: list[StockSignal],
    etf_frame: pd.DataFrame | None,
    leaders: set[str],
) -> SectorResult:
    stamp = pd.Timestamp(target)
    rows: list[pd.Series] = []
    enriched_frames: dict[str, pd.DataFrame] = {}
    for symbol, frame in frames.items():
        enriched = frame if "rsi14" in frame.columns else enrich_bars(frame)
        enriched_frames[symbol] = enriched
        if stamp in enriched.index:
            rows.append(enriched.loc[stamp])
    if not rows:
        components = {
            "oversold": 0,
            "low_contraction": 0,
            "breadth": 0,
            "leaders": 0,
            "etf": 0,
            "volume": 0,
            "patterns": 0,
        }
        return SectorResult(
            target, sector_id, sector_name, market, 0, components, breadth, []
        )
    avg_drawdown = float(np.nanmean([row["drawdown_20"] for row in rows]))
    avg_rsi = float(np.nanmean([row["rsi14"] for row in rows]))
    oversold_intensity = max(_clip((-avg_drawdown - 0.05) / 0.15), _clip((45 - avg_rsi) / 20))
    oversold_points = 20 * oversold_intensity
    low_contraction_points = 15 * _clip(1 - breadth.new_low_ratio / 0.60)
    breadth_points = 20 * (
        0.45 * breadth.up_ratio
        + 0.25 * breadth.above_ma5_ratio
        + 0.20 * breadth.above_ma10_ratio
        + 0.10 * float(breadth.improving)
    )
    signal_map = {signal.symbol: signal for signal in signals}
    leader_values = [
        (signal_map[symbol].score.rejection / 2)
        + (0.5 if signal_map[symbol].relative_strength_turn else 0)
        for symbol in leaders
        if symbol in signal_map
    ]
    leader_points = 15 * _clip(float(np.mean(leader_values)) if leader_values else 0)
    etf_points = 0.0
    if etf_frame is not None:
        etf = etf_frame if "return_1d" in etf_frame else enrich_bars(etf_frame)
        if stamp in etf.index:
            etf_row = etf.loc[stamp]
            etf_points = 10 * (
                0.5 * float(etf_row["return_1d"] > 0)
                + 0.5 * float(etf_row["close"] > etf_row["ma5"])
            )
    volume_confirmations = [
        float(row["volume_ratio"] >= 1.2 and row["close_position"] >= 0.55)
        for row in rows
    ]
    volume_points = 10 * float(np.mean(volume_confirmations))
    pattern_points = 10 * float(
        np.mean(
            [
                bool(
                    row["bullish_engulfing"]
                    or row["morning_star"]
                    or row["long_lower_shadow"]
                    or row["higher_low_2"]
                )
                for row in rows
            ]
        )
    )
    components = {
        "oversold": round(oversold_points, 2),
        "low_contraction": round(low_contraction_points, 2),
        "breadth": round(breadth_points, 2),
        "leaders": round(leader_points, 2),
        "etf": round(etf_points, 2),
        "volume": round(volume_points, 2),
        "patterns": round(pattern_points, 2),
    }
    total = int(round(min(100, sum(components.values()))))
    ranking = sorted(
        signals,
        key=lambda signal: (
            signal.score.rejection,
            signal.relative_strength_turn,
            signal.metrics.get("sector_rs_5d") or -99,
            signal.score.capitulation,
        ),
        reverse=True,
    )
    return SectorResult(
        target,
        sector_id,
        sector_name,
        market,
        total,
        components,
        breadth,
        [f"{signal.name}({signal.symbol})" for signal in ranking],
    )


def assess_risk_environment(
    frames: Mapping[str, pd.DataFrame], target: date, inverse_symbols: set[str]
) -> tuple[str, dict[str, float]]:
    stamp = pd.Timestamp(target)
    votes: list[float] = []
    details: dict[str, float] = {}
    for symbol, frame in frames.items():
        enriched = frame if "return_1d" in frame.columns else enrich_bars(frame)
        if stamp not in enriched.index or pd.isna(enriched.at[stamp, "return_1d"]):
            continue
        value = float(enriched.at[stamp, "return_1d"])
        adjusted = -value if symbol in inverse_symbols else value
        details[symbol] = value
        votes.append(float(adjusted > 0))
    if len(votes) < 2:
        return "Neutral", details
    ratio = float(np.mean(votes))
    if ratio >= 0.60:
        return "Risk-On", details
    if ratio <= 0.40:
        return "Risk-Off", details
    return "Neutral", details
