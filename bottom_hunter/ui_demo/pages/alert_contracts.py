"""Frozen contracts for local intraday alert configuration and events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AlertAssetDTO:
    canonical_id: str = ""
    symbol: str = ""
    name: str = ""
    market: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "canonical_id": self.canonical_id,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "label": f"{self.name} · {self.symbol} · {self.market}",
        }


@dataclass(frozen=True)
class PriceAlertDTO:
    rule_id: str = ""
    canonical_id: str = ""
    symbol: str = ""
    name: str = ""
    market: str = ""
    condition: str = "price_above"
    threshold: float = 0.0
    triggered: bool = False
    enabled: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "canonical_id": self.canonical_id,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "condition": self.condition,
            "threshold": self.threshold,
            "triggered": self.triggered,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class PriceAlertSnapshotDTO:
    assets: tuple[AlertAssetDTO, ...] = field(default_factory=tuple)
    rules: tuple[PriceAlertDTO, ...] = field(default_factory=tuple)
    monitoring: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "assets": [item.as_dict() for item in self.assets],
            "rules": [item.as_dict() for item in self.rules],
            "monitoring": self.monitoring,
        }
