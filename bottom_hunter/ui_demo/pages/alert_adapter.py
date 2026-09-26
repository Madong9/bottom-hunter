"""Persistence and quote-polling boundary for intraday alert rules."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .alert_contracts import AlertAssetDTO, PriceAlertDTO, PriceAlertSnapshotDTO

BACKEND_DIR = Path(
    os.environ.get("BOTTOM_HUNTER_PROJECT_DIR", Path(__file__).resolve().parents[2])
).resolve()


class PriceAlertAdapter:
    def __init__(self, state_dir: str | Path | None = None, summary_path: str | Path | None = None) -> None:
        from bottom_hunter.src.price_alerts import PriceAlertStore

        self._state_dir = Path(state_dir).resolve() if state_dir else BACKEND_DIR / "state"
        self._summary_path = Path(summary_path) if summary_path else self._state_dir / "watchlist_summary.json"
        self._store = PriceAlertStore(self._state_dir / "price_alerts.json")
        self._chart_port: object | None = None
        self.refresh_assets()

    def refresh_assets(self) -> tuple[AlertAssetDTO, ...]:
        try:
            payload = json.loads(self._summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        assets = []
        for raw in payload.get("assets", []) if isinstance(payload, dict) else []:
            if not isinstance(raw, dict):
                continue
            canonical_id = str(raw.get("canonical_id") or raw.get("symbol") or "")
            symbol = str(raw.get("symbol") or "")
            if canonical_id and symbol:
                assets.append(AlertAssetDTO(canonical_id, symbol, str(raw.get("name") or symbol), str(raw.get("market") or "")))
        if self._chart_port is not None:
            self._chart_port.refresh_assets()
        return tuple(assets)

    def snapshot(self, monitoring: bool = False) -> PriceAlertSnapshotDTO:
        assets = self.refresh_assets()
        rules = tuple(PriceAlertDTO(**rule.as_dict()) for rule in self._store.list_rules())
        return PriceAlertSnapshotDTO(assets, rules, monitoring)

    def add_rule(self, canonical_id: str, condition: str, threshold: float) -> PriceAlertSnapshotDTO:
        assets = self.refresh_assets()
        asset = next((item for item in assets if item.canonical_id == str(canonical_id)), None)
        if asset is None:
            raise ValueError("自选快照中找不到所选标的，请先刷新自选列表。")
        self._store.add_rule(
            canonical_id=asset.canonical_id,
            symbol=asset.symbol,
            name=asset.name,
            market=asset.market,
            condition=str(condition),
            threshold=float(threshold),
        )
        return self.snapshot()

    def remove_rule(self, rule_id: str) -> PriceAlertSnapshotDTO:
        self._store.remove_rule(str(rule_id))
        return self.snapshot()

    def set_enabled(self, rule_id: str, enabled: bool) -> PriceAlertSnapshotDTO:
        from bottom_hunter.src.price_alerts import PriceAlertRule

        rules = [
            PriceAlertRule(**{**rule.as_dict(), "enabled": bool(enabled), "triggered": False})
            if rule.rule_id == str(rule_id)
            else rule
            for rule in self._store.list_rules()
        ]
        self._store.update_rules(rules)
        return self.snapshot()

    def _chart(self):
        if self._chart_port is None:
            from .chart_adapter import ChartReadAdapter

            self._chart_port = ChartReadAdapter(summary_path=self._summary_path, retry_attempts=1, retry_delay=0)
        return self._chart_port

    def poll(self) -> tuple[PriceAlertSnapshotDTO, list[str]]:
        from bottom_hunter.src.price_alerts import evaluate_alert_rule

        rules = self._store.list_rules()
        if not rules:
            return self.snapshot(monitoring=True), []
        chart = self._chart()
        by_asset: dict[str, tuple[float | None, float | None]] = {}
        events = []
        updated_rules = []
        for rule in rules:
            quote = by_asset.get(rule.canonical_id)
            if quote is None:
                try:
                    intraday = chart.fetch(rule.canonical_id, "1m", 3)
                    daily = chart.fetch(rule.canonical_id, "1d", 3)
                    price = intraday.bars[-1].close if intraday.bars else (daily.bars[-1].close if daily.bars else None)
                    change = _intraday_change(intraday, daily, price)
                    quote = (price, change)
                    by_asset[rule.canonical_id] = quote
                except Exception:
                    quote = (None, None)
                    by_asset[rule.canonical_id] = quote
            updated, notify = evaluate_alert_rule(rule, price=quote[0], change_percent=quote[1])
            updated_rules.append(updated)
            if notify:
                measured = quote[0] if rule.condition.startswith("price_") else quote[1]
                unit = "" if rule.condition.startswith("price_") else "%"
                events.append(f"{rule.name}（{rule.symbol}）触发 {condition_label(rule.condition)} {rule.threshold:g}{unit}，当前 {measured:.4g}{unit}")
        self._store.update_rules(updated_rules)
        return self.snapshot(monitoring=True), events


def condition_label(condition: str) -> str:
    return {
        "price_above": "价格 ≥",
        "price_below": "价格 ≤",
        "change_above": "涨幅 ≥",
        "change_below": "涨幅 ≤",
    }.get(condition, condition)


def _intraday_change(intraday: object, daily: object, price: float | None) -> float | None:
    minute_bars = getattr(intraday, "bars", ())
    daily_bars = getattr(daily, "bars", ())
    if price is None or not minute_bars or len(daily_bars) < 2:
        return None
    latest_date = str(minute_bars[-1].timestamp)[:10]
    closes = [float(bar.close) for bar in daily_bars]
    dates = [str(bar.timestamp)[:10] for bar in daily_bars]
    prior_close = next((closes[index] for index in range(len(closes) - 1, -1, -1) if dates[index] < latest_date), None)
    if prior_close is None:
        prior_close = closes[-2]
    return (float(price) / prior_close - 1) * 100 if prior_close > 0 else None
