"""Immutable transport contracts for the read-only QML chart page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChartAssetDTO:
    canonical_id: str = ""
    symbol: str = ""
    name: str = ""
    market: str = ""
    category: str = ""
    source_symbols: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalId": self.canonical_id,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "category": self.category,
            "label": f"{self.name or self.symbol}  ·  {self.symbol}  ·  {self.market}",
        }

    def backend_mapping(self) -> dict[str, Any]:
        """Return a detached mapping consumed only by the chart adapter."""

        return {
            "canonical_id": self.canonical_id,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "category": self.category,
            "source_symbols": dict(self.source_symbols),
        }


@dataclass(frozen=True)
class ChartBarDTO:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    boll_upper: float | None = None
    boll_mid: float | None = None
    boll_lower: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None
    rsi14: float | None = None
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "ma5": self.ma5,
            "ma10": self.ma10,
            "ma20": self.ma20,
            "ma60": self.ma60,
            "bollUpper": self.boll_upper,
            "bollMid": self.boll_mid,
            "bollLower": self.boll_lower,
            "macdDif": self.macd_dif,
            "macdDea": self.macd_dea,
            "macdHist": self.macd_hist,
            "rsi14": self.rsi14,
            "kdjK": self.kdj_k,
            "kdjD": self.kdj_d,
            "kdjJ": self.kdj_j,
        }


@dataclass(frozen=True)
class ChartDTO:
    canonical_id: str = ""
    symbol: str = ""
    name: str = ""
    market: str = ""
    timeframe: str = "1d"
    bars: tuple[ChartBarDTO, ...] = field(default_factory=tuple)
    provider: str = ""
    updated_at: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalId": self.canonical_id,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "timeframe": self.timeframe,
            "bars": [bar.as_dict() for bar in self.bars],
            "provider": self.provider,
            "updatedAt": self.updated_at,
            "note": self.note,
        }
