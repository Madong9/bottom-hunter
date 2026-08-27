from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any


class SourceTier(StrEnum):
    OFFICIAL = "official"
    PROFESSIONAL = "professional"
    COMMUNITY = "community"


class ResearchKind(StrEnum):
    FILING = "filing"
    NEWS = "news"
    MEDIA_OPINION = "media_opinion"
    COMMUNITY_OPINION = "community_opinion"
    OFFICIAL_ANALYSIS = "official_analysis"


@dataclass(frozen=True)
class FinancialFact:
    symbol: str
    market: str
    period_end: date
    filed_at: datetime
    metric: str
    value: float
    unit: str
    currency: str
    source: str
    source_url: str
    period_type: str = ""
    available_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["period_end"] = self.period_end.isoformat()
        payload["filed_at"] = self.filed_at.isoformat()
        payload["available_at"] = (
            self.available_at or self.filed_at
        ).isoformat()
        return payload


@dataclass(frozen=True)
class ResearchItem:
    kind: ResearchKind
    tier: SourceTier
    symbol: str
    market: str
    title: str
    published_at: datetime
    source: str
    url: str
    summary: str = ""
    author: str = ""
    sentiment: str = "neutral"
    confidence: float = 0.5
    available_at: datetime | None = None
    report_date: date | None = None
    item_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["tier"] = self.tier.value
        payload["published_at"] = self.published_at.isoformat()
        payload["available_at"] = (
            self.available_at or self.published_at
        ).isoformat()
        payload["report_date"] = self.report_date.isoformat() if self.report_date else None
        return payload


@dataclass(frozen=True)
class MacroObservation:
    series_id: str
    name: str
    dimension: str
    observation_date: date
    value: float
    unit: str
    source: str
    source_url: str
    release_at: datetime
    previous: float | None = None
    change: float | None = None
    change_pct: float | None = None
    signal: int = 0
    vintage_at: datetime | None = None
    consensus: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observation_date"] = self.observation_date.isoformat()
        payload["release_at"] = self.release_at.isoformat()
        payload["vintage_at"] = (self.vintage_at or self.release_at).isoformat()
        return payload


@dataclass
class ResearchSnapshot:
    symbol: str
    market: str
    refreshed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    financial_facts: list[FinancialFact] = field(default_factory=list)
    filings: list[ResearchItem] = field(default_factory=list)
    news: list[ResearchItem] = field(default_factory=list)
    opinions: list[ResearchItem] = field(default_factory=list)
    macro: list[MacroObservation] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "refreshed_at": self.refreshed_at.isoformat(),
            "financial_facts": [item.to_dict() for item in self.financial_facts],
            "filings": [item.to_dict() for item in self.filings],
            "news": [item.to_dict() for item in self.news],
            "opinions": [item.to_dict() for item in self.opinions],
            "macro": [item.to_dict() for item in self.macro],
            "errors": dict(self.errors),
        }
