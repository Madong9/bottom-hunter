from __future__ import annotations

import json

from .models import Alert, BottomState, SectorResult, StockSignal
from .storage import StateStore


def build_alerts(
    signals: list[StockSignal], sectors: list[SectorResult], store: StateStore
) -> list[Alert]:
    alerts: list[Alert] = []
    previous_signals = store.previous_signals_map(signals)
    for signal in signals:
        previous = previous_signals.get((signal.symbol, signal.sector_id))
        previous_score = int(previous["score"]) if previous else None
        previous_stage = previous["entry_stage"] if previous else None
        previous_state = previous["state"] if previous else None
        previous_relative = False
        if previous:
            try:
                previous_payload = json.loads(previous["payload_json"])
                previous_relative = bool(
                    previous_payload.get("metrics", {}).get("index_new_low_stock_holds")
                )
            except (json.JSONDecodeError, TypeError):
                previous_relative = False
        if previous_score is not None and previous_score <= 6 and signal.score.total >= 8:
            alerts.append(
                Alert(
                    signal.date,
                    "A_SCORE_JUMP",
                    signal.symbol,
                    f"{signal.symbol} 首次从 {previous_score} 分跃升至 {signal.score.total} 分。",
                )
            )
        if signal.entry_stage and signal.entry_stage.value != previous_stage:
            alerts.append(
                Alert(
                    signal.date,
                    "B_ENTRY_STAGE",
                    signal.symbol,
                    f"{signal.symbol} 进入 {signal.entry_stage.value}；仅为仓位框架提示，不自动下单。",
                )
            )
        exact_divergence = bool(signal.metrics.get("index_new_low_stock_holds"))
        if exact_divergence and signal.metrics.get("is_leader") and not previous_relative:
            alerts.append(
                Alert(
                    signal.date,
                    "D_RELATIVE_DIVERGENCE",
                    signal.symbol,
                    f"{signal.symbol} 出现指数/板块走弱但个股拒绝创新低的相对强度拐点。",
                )
            )
        prior_bottom_state = previous_stage is not None or previous_state in {
            "CAPITULATION",
            "REVERSAL_DAY",
            "NO_NEW_LOW",
            "BREADTH_CONFIRM",
            "TREND_CONFIRM",
        }
        if (
            signal.state == BottomState.FAILED
            and previous_state != BottomState.FAILED.value
            and prior_bottom_state
        ):
            alerts.append(
                Alert(
                    signal.date,
                    "E_SIGNAL_FAILED",
                    signal.symbol,
                    f"{signal.symbol} 之前的反转结构已失败，底部确认状态已重置。",
                )
            )
    previous_sectors = store.previous_sectors_map(sectors)
    for sector in sectors:
        previous = previous_sectors.get((sector.sector_id, sector.market))
        if previous:
            increase = sector.score - int(previous["score"])
            if increase > 15 and int(previous["score"]) <= 75 and sector.score > 75:
                entity = f"{sector.sector_id}:{sector.market}"
                message = (
                    f"{sector.sector_name}({sector.market}) 板块分数单日上升 {increase} 分"
                    f"并突破 75，当前 {sector.score}/100。"
                )
                alerts.append(
                    Alert(
                        sector.date,
                        "C_SECTOR_SURGE",
                        entity,
                        message,
                    )
                )
    return alerts
