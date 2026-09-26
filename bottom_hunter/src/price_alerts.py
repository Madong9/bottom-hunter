"""Local persistence and transition logic for user-defined price alerts."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4
from typing import Any

ALLOWED_CONDITIONS = frozenset({"price_above", "price_below", "change_above", "change_below"})


@dataclass(frozen=True)
class PriceAlertRule:
    rule_id: str
    canonical_id: str
    symbol: str
    name: str
    market: str
    condition: str
    threshold: float
    triggered: bool = False
    enabled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PriceAlertStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    def list_rules(self) -> list[PriceAlertRule]:
        with self._lock:
            try:
                payload = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return []
            rules = []
            for raw in payload if isinstance(payload, list) else []:
                if not isinstance(raw, dict) or raw.get("condition") not in ALLOWED_CONDITIONS:
                    continue
                try:
                    rules.append(PriceAlertRule(
                        rule_id=str(raw["rule_id"]),
                        canonical_id=str(raw["canonical_id"]),
                        symbol=str(raw["symbol"]),
                        name=str(raw.get("name") or raw["symbol"]),
                        market=str(raw.get("market") or ""),
                        condition=str(raw["condition"]),
                        threshold=float(raw["threshold"]),
                        triggered=bool(raw.get("triggered", False)),
                        enabled=bool(raw.get("enabled", True)),
                    ))
                except (KeyError, TypeError, ValueError):
                    continue
            return rules

    def add_rule(
        self,
        *,
        canonical_id: str,
        symbol: str,
        name: str,
        market: str,
        condition: str,
        threshold: float,
    ) -> PriceAlertRule:
        if condition not in ALLOWED_CONDITIONS:
            raise ValueError("不支持的预警条件")
        if not canonical_id or not symbol:
            raise ValueError("请选择有效自选标的")
        value = float(threshold)
        if not (value == value and abs(value) != float("inf")):
            raise ValueError("预警阈值必须是有效数字")
        if condition.startswith("change_") and not -100 <= value <= 1000:
            raise ValueError("涨跌幅阈值应在 -100% 到 1000% 之间")
        if condition.startswith("price_") and value <= 0:
            raise ValueError("价格阈值必须大于 0")
        rule = PriceAlertRule(uuid4().hex, canonical_id, symbol, name, market, condition, value)
        with self._lock:
            rules = self.list_rules()
            rules.append(rule)
            self._write(rules)
        return rule

    def remove_rule(self, rule_id: str) -> None:
        with self._lock:
            self._write([rule for rule in self.list_rules() if rule.rule_id != str(rule_id)])

    def update_rules(self, rules: list[PriceAlertRule]) -> None:
        with self._lock:
            self._write(rules)

    def _write(self, rules: list[PriceAlertRule]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps([rule.as_dict() for rule in rules], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def evaluate_alert_rule(rule: PriceAlertRule, *, price: float | None, change_percent: float | None) -> tuple[PriceAlertRule, bool]:
    value = price if rule.condition.startswith("price_") else change_percent
    if value is None:
        return rule, False
    reached = {
        "price_above": value >= rule.threshold,
        "price_below": value <= rule.threshold,
        "change_above": value >= rule.threshold,
        "change_below": value <= rule.threshold,
    }[rule.condition]
    should_notify = rule.enabled and reached and not rule.triggered
    updated = PriceAlertRule(
        rule_id=rule.rule_id,
        canonical_id=rule.canonical_id,
        symbol=rule.symbol,
        name=rule.name,
        market=rule.market,
        condition=rule.condition,
        threshold=rule.threshold,
        triggered=reached if rule.enabled else False,
        enabled=rule.enabled,
    )
    return updated, should_notify
