"""Read-only adapter from the latest report snapshot to OverviewDTO."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from bottom_hunter.ui_demo.overview_shell.contracts import (
    HEALTH_OK,
    HEALTH_WARNING,
    HealthDTO,
    MarketDTO,
    OpportunityDTO,
    OverviewDTO,
    PortfolioDTO,
    ScanDTO,
    ValidationDTO,
)


def build_overview_dto() -> OverviewDTO | None:
    """Read existing report values without running a scan or backtest."""

    from bottom_hunter.src import gui_core

    path = gui_core.latest_json_report()
    if path is None:
        return None
    summary = gui_core.load_report_summary(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    validation = payload.get("validation_30d") or {}
    paper = payload.get("paper_history") or {}
    sample_size = int(validation.get("sample_size") or 0)
    win_rate = validation.get("win_rate")
    validation_value = f"{float(win_rate):.0%}" if win_rate is not None else "--"
    points = list(paper.get("points") or [])
    latest_equity = paper.get("latest")
    portfolio_value = f"{float(latest_equity):.4f}" if latest_equity is not None else "1.0000"
    health = (
        HealthDTO(level=HEALTH_WARNING, text=f"需关注 · {summary.error_count} 项异常")
        if summary.error_count
        else HealthDTO(level=HEALTH_OK, text="正常 · 本次行情完整")
    )
    return OverviewDTO(
        market=MarketDTO(
            status=" · ".join(f"{key} {value}" for key, value in summary.market_sessions.items()) or "--",
            detail=f"环境 {len(summary.environments)} 项",
        ),
        scan=ScanDTO(status="就绪", detail=f"报告 {summary.report_date}", report_date=summary.report_date),
        opportunity=OpportunityDTO(
            count=str(summary.opportunity_count),
            hint=f"有效观察 {summary.signal_count} 个",
            updated=summary.report_date,
        ),
        health=health,
        validation=ValidationDTO(value=validation_value, hint=f"{sample_size} 样本 · 近30天5日持有"),
        portfolio=PortfolioDTO(value=portfolio_value, hint=f"{len(points)} 个交易日"),
        timestamp=datetime.now(UTC).isoformat(),
    )
