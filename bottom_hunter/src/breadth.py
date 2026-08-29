from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import numpy as np
import pandas as pd

from .indicators import enrich_bars
from .models import BreadthResult


def _value(frame: pd.DataFrame, target: date, column: str):
    stamp = pd.Timestamp(target)
    if stamp not in frame.index:
        return np.nan
    return frame.at[stamp, column]


def _snapshot(frames: Mapping[str, pd.DataFrame], target: date) -> list[dict[str, float | bool]]:
    rows: list[dict[str, float | bool]] = []
    for frame in frames.values():
        enriched = frame if "rsi14" in frame.columns else enrich_bars(frame)
        stamp = pd.Timestamp(target)
        if stamp not in enriched.index:
            continue
        row = enriched.loc[stamp]
        required = ("return_1d", "ma5", "ma10", "new_low_20", "new_high_20")
        if any(column not in row.index for column in required):
            continue
        rows.append(
            {
                "return_1d": float(row["return_1d"]),
                "above_ma5": bool(row["close"] > row["ma5"]),
                "above_ma10": bool(row["close"] > row["ma10"]),
                "new_low_20": bool(row["new_low_20"]),
                "new_high_20": bool(row["new_high_20"]),
            }
        )
    return rows


def calculate_breadth(
    sector_id: str,
    market: str,
    frames: Mapping[str, pd.DataFrame],
    target: date,
    expected_count: int,
    thresholds: dict,
    etf_frame: pd.DataFrame | None = None,
) -> BreadthResult:
    rows = _snapshot(frames, target)
    count = len(rows)
    coverage = count / expected_count if expected_count else 0.0
    if not count:
        return BreadthResult(target, sector_id, market, 0, 0, 0, 0, 0, 0, 0, 0, 0, False, None, coverage)
    up = np.mean([row["return_1d"] > 0 for row in rows])
    down = np.mean([row["return_1d"] < 0 for row in rows])
    new_low = np.mean([row["new_low_20"] for row in rows])
    new_high = np.mean([row["new_high_20"] for row in rows])
    above_ma5 = np.mean([row["above_ma5"] for row in rows])
    above_ma10 = np.mean([row["above_ma10"] for row in rows])
    strong_up = np.mean([row["return_1d"] >= thresholds["strong_up_return"] for row in rows])
    previous_frames = {symbol: frame for symbol, frame in frames.items()}
    prior_dates = sorted(
        {index.date() for frame in previous_frames.values() for index in frame.index if index.date() < target}
    )
    previous_new_low = np.nan
    previous_up = np.nan
    if prior_dates:
        previous_rows = _snapshot(previous_frames, prior_dates[-1])
        if previous_rows:
            previous_new_low = np.mean([row["new_low_20"] for row in previous_rows])
            previous_up = np.mean([row["return_1d"] > 0 for row in previous_rows])
    improving = bool(up >= thresholds["up_ratio"] and (np.isnan(previous_new_low) or new_low < previous_new_low))
    worsening = bool(
        pd.notna(previous_new_low) and pd.notna(previous_up) and new_low > previous_new_low and up < previous_up
    )
    etf_up: bool | None = None
    if etf_frame is not None:
        enriched_etf = etf_frame if "return_1d" in etf_frame else enrich_bars(etf_frame)
        etf_return = _value(enriched_etf, target, "return_1d")
        etf_up = bool(etf_return > 0) if pd.notna(etf_return) else None
    breadth_ready = bool(coverage >= 0.60 and up >= thresholds["up_ratio"] and improving)
    breadth_score = int(breadth_ready and etf_up is True)
    return BreadthResult(
        date=target,
        sector_id=sector_id,
        market=market,
        asset_count=count,
        up_ratio=float(up),
        down_ratio=float(down),
        new_low_ratio=float(new_low),
        new_high_ratio=float(new_high),
        above_ma5_ratio=float(above_ma5),
        above_ma10_ratio=float(above_ma10),
        strong_up_ratio=float(strong_up),
        breadth_score=breadth_score,
        improving=improving,
        etf_up=etf_up,
        coverage=float(coverage),
        worsening=worsening,
        breadth_ready=breadth_ready,
    )
