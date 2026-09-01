"""PHASE 2-C — frozen data contract for the overview page.

Backend -> OverviewDTO -> OverviewState.apply(dto) -> QML.

The DTO is a pure data contract: no business computation, no backend
dependencies, no Qt. It is the ONLY wire format between the backend and the
ViewModel, so the bridge never depends on backend detail (dicts are
assembled by the loader adapters in the host app, not the bridge).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# data-health levels (mirrors OverviewState constants)
HEALTH_OK = "OK"
HEALTH_WARNING = "WARNING"
HEALTH_ERROR = "ERROR"
HEALTH_UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MarketDTO:
    """Market-session / environment status."""
    status: str = "--"          # e.g. "A股 开盘 · 港股 休市"
    detail: str = ""


@dataclass(frozen=True)
class ScanDTO:
    """Latest scan/report status."""
    status: str = "--"          # e.g. "就绪"
    detail: str = "等待最新扫描"
    report_date: str = ""


@dataclass(frozen=True)
class OpportunityDTO:
    """Opportunity count from the latest report."""
    count: str = "--"
    hint: str = "等待最新扫描"
    updated: str = ""           # report date the count came from


@dataclass(frozen=True)
class HealthDTO:
    """Data-health level + human text."""
    level: str = HEALTH_UNKNOWN
    text: str = "--"


@dataclass(frozen=True)
class ValidationDTO:
    """Rolling validation (win-rate) metric."""
    value: str = "--"
    hint: str = "近30天5日持有胜率"


@dataclass(frozen=True)
class PortfolioDTO:
    """Paper portfolio equity."""
    value: str = "1.0000"
    hint: str = "三阶段框架净值"


@dataclass(frozen=True)
class OverviewDTO:
    """Complete overview snapshot. Immutable — one DTO = one apply()."""
    market: MarketDTO = field(default_factory=MarketDTO)
    scan: ScanDTO = field(default_factory=ScanDTO)
    opportunity: OpportunityDTO = field(default_factory=OpportunityDTO)
    health: HealthDTO = field(default_factory=HealthDTO)
    validation: ValidationDTO = field(default_factory=ValidationDTO)
    portfolio: PortfolioDTO = field(default_factory=PortfolioDTO)
    timestamp: str = ""          # ISO timestamp captured at load time

    def as_dict(self) -> dict[str, Any]:
        """Plain-dict view (test/debug; not the binding path)."""
        return {
            "market": {"status": self.market.status, "detail": self.market.detail},
            "scan": {"status": self.scan.status, "detail": self.scan.detail,
                     "report_date": self.scan.report_date},
            "opportunity": {"count": self.opportunity.count, "hint": self.opportunity.hint,
                            "updated": self.opportunity.updated},
            "health": {"level": self.health.level, "text": self.health.text},
            "validation": {"value": self.validation.value, "hint": self.validation.hint},
            "portfolio": {"value": self.portfolio.value, "hint": self.portfolio.hint},
            "timestamp": self.timestamp,
        }
