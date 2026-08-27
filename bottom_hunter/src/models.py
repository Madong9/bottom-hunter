from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

import pandas as pd


class SignalLevel(StrEnum):
    IGNORE = "IGNORE"
    WATCH = "WATCH"
    EARLY_REVERSAL = "EARLY REVERSAL"
    BUY_CANDIDATE = "BUY CANDIDATE"
    STRONG_REVERSAL = "STRONG REVERSAL"
    FAILED = "FAILED"


class BottomState(StrEnum):
    NORMAL = "NORMAL"
    SELL_OFF = "SELL_OFF"
    CAPITULATION = "CAPITULATION"
    REVERSAL_DAY = "REVERSAL_DAY"
    NO_NEW_LOW = "NO_NEW_LOW"
    BREADTH_CONFIRM = "BREADTH_CONFIRM"
    TREND_CONFIRM = "TREND_CONFIRM"
    FAILED = "FAILED"


class EntryStage(StrEnum):
    ENTRY_STAGE_1 = "ENTRY_STAGE_1"
    ENTRY_STAGE_2 = "ENTRY_STAGE_2"
    ENTRY_STAGE_3 = "ENTRY_STAGE_3"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    market: str
    sector_id: str | None = None
    leader: bool = False
    inverse: bool = False
    provider_symbol: str | None = None
    volume_optional: bool = False
    category: str = ""
    industry: str = ""
    asset_type: str = "equity"
    tokenized_stock: bool = False
    sources: tuple[str, ...] = ()
    source_symbols: dict[str, str] = field(default_factory=dict)


@dataclass
class DataResult:
    symbol: str
    bars: pd.DataFrame
    provider: str
    data_timestamp: datetime
    quality: str = "complete"
    warnings: list[str] = field(default_factory=list)


@dataclass
class FundamentalResult:
    score: int | None
    reason: str
    source: str | None = None
    as_of: date | None = None


@dataclass
class ScoreBreakdown:
    oversold: int
    capitulation: int
    rejection: int
    breadth: int
    fundamental: int | None
    timing: int

    @property
    def total(self) -> int:
        return (
            self.oversold
            + self.capitulation
            + self.rejection
            + self.breadth
            + (self.fundamental or 0)
            + self.timing
        )

    @property
    def available_max(self) -> int:
        return 10 if self.fundamental is not None else 8


@dataclass
class StockSignal:
    date: date
    symbol: str
    name: str
    market: str
    sector_id: str
    sector_name: str
    score: ScoreBreakdown
    signal_level: SignalLevel
    state: BottomState
    entry_stage: EntryStage | None
    metrics: dict[str, Any]
    reasons: list[str]
    risks: list[str]
    relative_strength_turn: bool
    capitulation_date: date | None
    capitulation_low: float | None
    data_quality: str
    provider: str
    data_timestamp: datetime

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["date"] = self.date.isoformat()
        payload["signal_level"] = self.signal_level.value
        payload["state"] = self.state.value
        payload["entry_stage"] = self.entry_stage.value if self.entry_stage else None
        payload["capitulation_date"] = (
            self.capitulation_date.isoformat() if self.capitulation_date else None
        )
        payload["data_timestamp"] = self.data_timestamp.isoformat()
        payload["score"]["total"] = self.score.total
        payload["score"]["available_max"] = self.score.available_max
        return payload


@dataclass
class BreadthResult:
    date: date
    sector_id: str
    market: str
    asset_count: int
    up_ratio: float
    down_ratio: float
    new_low_ratio: float
    new_high_ratio: float
    above_ma5_ratio: float
    above_ma10_ratio: float
    strong_up_ratio: float
    breadth_score: int
    improving: bool
    etf_up: bool | None
    coverage: float
    worsening: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["date"] = self.date.isoformat()
        return result


@dataclass
class SectorResult:
    date: date
    sector_id: str
    sector_name: str
    market: str
    score: int
    components: dict[str, float]
    breadth: BreadthResult
    leader_ranking: list[str]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["date"] = self.date.isoformat()
        result["breadth"] = self.breadth.to_dict()
        return result


@dataclass
class Alert:
    date: date
    alert_type: str
    entity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "date": self.date.isoformat(),
            "type": self.alert_type,
            "entity": self.entity,
            "message": self.message,
        }
