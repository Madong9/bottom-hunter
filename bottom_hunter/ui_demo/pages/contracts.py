"""PHASE 3-C — Page DTOs + read-only adapters (Report / Status).

Adapters are the ONLY sanctioned boundary that touches the existing backend
(read-only helpers). QML and the ViewModel layer never import business
modules. No scanner/backtest/chart is touched — these adapters read reports
and health-check data, which are already produced by the frozen backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ReportDTO:
    """Latest daily-report summary (frozen page contract)."""
    report_date: str = "--"
    signal_count: int = 0
    opportunity_count: int = 0
    sector_count: int = 0
    error_count: int = 0

    def as_dict(self) -> dict:
        return {
            "report_date": self.report_date,
            "signal_count": self.signal_count,
            "opportunity_count": self.opportunity_count,
            "sector_count": self.sector_count,
            "error_count": self.error_count,
        }


@dataclass(frozen=True)
class StatusDTO:
    """Runtime health status (frozen page contract)."""
    items: tuple[tuple[str, bool, str], ...] = field(default_factory=tuple)
    ok_count: int = 0
    total_count: int = 0

    def as_dict(self) -> dict:
        return {
            "items": [{"name": n, "ok": ok, "detail": d} for n, ok, d in self.items],
            "ok_count": self.ok_count,
            "total_count": self.total_count,
        }


def build_report_dto() -> ReportDTO | None:
    """Read the latest JSON report summary; None when unavailable/invalid."""
    from bottom_hunter.src import gui_core

    path = gui_core.latest_json_report()
    if path is None:
        return None
    summary = gui_core.load_report_summary(path)  # raises on malformed JSON
    return ReportDTO(
        report_date=summary.report_date,
        signal_count=summary.signal_count,
        opportunity_count=summary.opportunity_count,
        sector_count=summary.sector_count,
        error_count=summary.error_count,
    )


def build_status_dto() -> StatusDTO:
    """Collect runtime health checks (read-only)."""
    from bottom_hunter.src import gui_core

    items = tuple(gui_core.health_check())
    ok = sum(1 for _n, passed, _d in items if passed)
    return StatusDTO(items=items, ok_count=ok, total_count=len(items))
