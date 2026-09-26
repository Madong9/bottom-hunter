"""PHASE 3-C — Page DTOs + read-only adapters (Report / Status).

Adapters are the ONLY sanctioned boundary that touches the existing backend
(read-only helpers). QML and the ViewModel layer never import business
modules. No scanner/backtest/chart is touched — these adapters read reports
and health-check data, which are already produced by the frozen backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _metric_number(metrics: dict[str, Any], key: str, digits: int = 2) -> str:
    value = metrics.get(key)
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "N/A"


def _metric_percent(metrics: dict[str, Any], key: str) -> str:
    value = metrics.get(key)
    try:
        return f"{float(value):+.2%}"
    except (TypeError, ValueError):
        return "N/A"


@dataclass(frozen=True)
class ReportDTO:
    """Latest daily-report summary (frozen page contract)."""
    report_date: str = "--"
    signal_count: int = 0
    opportunity_count: int = 0
    sector_count: int = 0
    error_count: int = 0
    file_name: str = ""
    generated_at: str = ""
    market_sessions: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    signals: tuple[ReportSignalDTO, ...] = field(default_factory=tuple)
    sectors: tuple[ReportSectorDTO, ...] = field(default_factory=tuple)
    alerts: tuple[str, ...] = field(default_factory=tuple)
    data_errors: tuple[str, ...] = field(default_factory=tuple)
    markdown: str = ""

    def as_dict(self) -> dict:
        return {
            "report_date": self.report_date,
            "signal_count": self.signal_count,
            "opportunity_count": self.opportunity_count,
            "sector_count": self.sector_count,
            "error_count": self.error_count,
            "file_name": self.file_name,
            "generated_at": self.generated_at,
            "market_sessions": dict(self.market_sessions),
            "signals": [item.as_dict() for item in self.signals],
            "sectors": [item.as_dict() for item in self.sectors],
            "alerts": list(self.alerts),
            "data_errors": list(self.data_errors),
            "markdown": self.markdown,
        }


@dataclass(frozen=True)
class ReportSignalDTO:
    chart_key: str = ""
    symbol: str = "--"
    name: str = "--"
    market: str = "--"
    sector: str = "--"
    score: int = 0
    available_max: int = 10
    level: str = "--"
    stage: str = "--"
    data_quality: str = "--"
    provider: str = "--"
    data_timestamp: str = "--"
    score_parts: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    metric_items: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)
    risks: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "chart_key": self.chart_key,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "sector": self.sector,
            "score": self.score,
            "available_max": self.available_max,
            "score_text": f"{self.score}/{self.available_max}",
            "level": self.level,
            "stage": self.stage,
            "data_quality": self.data_quality,
            "provider": self.provider,
            "data_timestamp": self.data_timestamp,
            "score_parts": [
                {"label": label, "value": value} for label, value in self.score_parts
            ],
            "metric_items": [
                {"label": label, "value": value} for label, value in self.metric_items
            ],
            "reasons": list(self.reasons),
            "risks": list(self.risks),
        }


@dataclass(frozen=True)
class ReportSectorDTO:
    name: str = "--"
    market: str = "--"
    score: int = 0
    breadth: float = 0.0
    coverage: float = 0.0

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "market": self.market,
            "score": self.score,
            "breadth": f"{self.breadth:.0%}",
            "coverage": f"{self.coverage:.0%}",
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
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    signals = []
    for raw in summary.signals:
        score = raw.get("score") or {}
        metrics = raw.get("metrics") or {}

        score_labels = (
            ("oversold", "超跌"),
            ("capitulation", "恐慌量价"),
            ("rejection", "止跌反转"),
            ("breadth", "板块宽度"),
            ("fundamental", "基本面"),
            ("timing", "时机"),
            ("support", "支撑位"),
        )
        signals.append(
            ReportSignalDTO(
                chart_key=str(raw.get("canonical_id") or raw.get("symbol") or ""),
                symbol=str(raw.get("symbol") or "--"),
                name=str(raw.get("name") or "--"),
                market=str(raw.get("market") or "--"),
                sector=str(raw.get("sector_name") or "--"),
                score=int(score.get("total") or 0),
                available_max=int(score.get("available_max") or 10),
                level=str(raw.get("signal_level") or "--"),
                stage=str(raw.get("entry_stage") or raw.get("state") or "--"),
                data_quality=str(raw.get("data_quality") or "--"),
                provider=str(raw.get("provider") or "--"),
                data_timestamp=str(raw.get("data_timestamp") or "--"),
                score_parts=tuple(
                    (
                        label,
                        "N/A" if score.get(key) is None else str(score.get(key, 0)),
                    )
                    for key, label in score_labels
                ),
                metric_items=(
                    ("收盘价", _metric_number(metrics, "close", 4)),
                    ("1日涨跌", _metric_percent(metrics, "return_1d")),
                    ("5日涨跌", _metric_percent(metrics, "return_5d")),
                    ("60日回撤", _metric_percent(metrics, "drawdown_60")),
                    ("RSI14", _metric_number(metrics, "rsi14", 1)),
                    ("相对MA20", _metric_percent(metrics, "ma20_distance")),
                    ("量比", _metric_number(metrics, "volume_ratio", 2)),
                    ("支撑位", _metric_number(metrics, "support_level", 4)),
                    ("压力位", _metric_number(metrics, "resistance_level", 4)),
                    ("时机环境", str(metrics.get("timing_context") or "N/A")),
                ),
                reasons=tuple(str(item) for item in (raw.get("reasons") or ())),
                risks=tuple(str(item) for item in (raw.get("risks") or ())),
            )
        )
    sectors = []
    for raw in summary.sectors:
        breadth = raw.get("breadth") or {}
        sectors.append(
            ReportSectorDTO(
                name=str(raw.get("sector_name") or "--"),
                market=str(raw.get("market") or "--"),
                score=int(raw.get("score") or 0),
                breadth=float(breadth.get("up_ratio") or 0.0),
                coverage=float(breadth.get("coverage") or 0.0),
            )
        )
    raw_errors = payload.get("data_errors") or {}
    if isinstance(raw_errors, dict):
        data_errors = tuple(f"{key}：{value}" for key, value in raw_errors.items())
    elif isinstance(raw_errors, list):
        data_errors = tuple(str(value) for value in raw_errors)
    else:
        data_errors = (str(raw_errors),) if raw_errors else ()
    markdown_path = path.with_suffix(".md")
    try:
        markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.is_file() else ""
    except OSError:
        markdown = ""
    return ReportDTO(
        report_date=summary.report_date,
        signal_count=summary.signal_count,
        opportunity_count=summary.opportunity_count,
        sector_count=summary.sector_count,
        error_count=summary.error_count,
        file_name=path.name,
        generated_at=str(payload.get("generated_at") or ""),
        market_sessions=tuple(summary.market_sessions.items()),
        signals=tuple(signals),
        sectors=tuple(sectors),
        alerts=tuple(str(item.get("message") or item) for item in summary.alerts),
        data_errors=data_errors,
        markdown=markdown,
    )


def build_status_dto() -> StatusDTO:
    """Collect runtime health checks (read-only)."""
    from bottom_hunter.src import gui_core

    items = tuple(gui_core.health_check())
    ok = sum(1 for _n, passed, _d in items if passed)
    return StatusDTO(items=items, ok_count=ok, total_count=len(items))
