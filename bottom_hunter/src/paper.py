"""Paper portfolio following the staged entry framework.

ENTRY_STAGE_1 opens 25% of the per-signal framework, ENTRY_STAGE_2
brings it to 60%, ENTRY_STAGE_3 to 100%. Fills are recorded once per
(signal date, symbol, stage); valuations use the latest close from the
scan's own price history. All numbers are research artifacts — no real
orders are ever placed.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any

import pandas as pd

from .models import EntryStage, StockSignal
from .storage import StateStore

LOGGER = logging.getLogger(__name__)

STAGE_WEIGHTS: dict[str, float] = {
    EntryStage.ENTRY_STAGE_1.value: 0.25,
    EntryStage.ENTRY_STAGE_2.value: 0.60,
    EntryStage.ENTRY_STAGE_3.value: 1.00,
}


def record_stage_fills(
    store: StateStore,
    signals: list[StockSignal],
    enriched: Mapping[str, pd.DataFrame],
    target: date,
) -> int:
    fills: list[dict[str, Any]] = []
    for signal in signals:
        stage = signal.entry_stage.value if signal.entry_stage else None
        weight = STAGE_WEIGHTS.get(stage)
        if not weight or signal.state.value == "FAILED":
            continue
        frame = enriched.get(signal.symbol)
        if frame is None or frame.empty:
            continue
        stamp = pd.Timestamp(target)
        if stamp not in frame.index:
            continue
        price = float(frame.at[stamp, "close"])
        if price <= 0:
            continue
        fills.append(
            {
                "symbol": signal.symbol,
                "sector_id": signal.sector_id,
                "stage": stage,
                "weight": weight,
                "price": price,
            }
        )
    written = store.paper_fills(target, fills)
    if written:
        LOGGER.info("模拟组合记录 %d 笔阶段入场", written)
    return written


def update_valuations(
    store: StateStore,
    enriched: Mapping[str, pd.DataFrame],
    target: date,
) -> dict[str, Any]:
    positions = store.paper_positions(target)
    valuations: list[dict[str, Any]] = []
    for position in positions:
        frame = enriched.get(position["symbol"])
        if frame is None or frame.empty:
            continue
        stamp = pd.Timestamp(target)
        if stamp not in frame.index:
            continue
        last_price = float(frame.at[stamp, "close"])
        entry_price = float(position["entry_price"])
        if entry_price <= 0:
            continue
        valuations.append(
            {
                "symbol": position["symbol"],
                "sector_id": position["sector_id"],
                "weight": float(position["weight"]),
                "entry_price": entry_price,
                "last_price": last_price,
                "unrealized_return": last_price / entry_price - 1,
            }
        )
    store.save_valuations(target, valuations)
    weighted = sum(item["weight"] * item["unrealized_return"] for item in valuations)
    total_weight = sum(item["weight"] for item in valuations)
    return {
        "positions": len(valuations),
        "total_weight": total_weight,
        "weighted_return": weighted / total_weight if total_weight else 0.0,
        "equity_index": (
            sum(
                item["weight"] * item["last_price"] / item["entry_price"]
                for item in valuations
            )
            if valuations
            else None
        ),
    }
