from __future__ import annotations

import csv
import io
import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .config import AppConfig

PACKAGE_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PACKAGE_DIR.parent


@dataclass(frozen=True)
class CommandSpec:
    name: str
    argv: list[str]
    cwd: Path


@dataclass(frozen=True)
class ReportSummary:
    path: Path
    report_date: str
    market_sessions: dict[str, str]
    environments: dict[str, str]
    signal_count: int
    opportunity_count: int
    sector_count: int
    error_count: int
    signals: list[dict[str, Any]]
    sectors: list[dict[str, Any]]
    alerts: list[dict[str, Any]]


def parse_date(value: str, *, optional: bool = False) -> date | None:
    cleaned = value.strip()
    if not cleaned and optional:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError as exc:
        raise ValueError("日期格式必须为 YYYY-MM-DD") from exc


def build_scan_command(
    requested_date: str,
    offline: bool,
    workers: int,
    python_executable: str = sys.executable,
    workspace: Path = WORKSPACE_DIR,
) -> CommandSpec:
    parsed = parse_date(requested_date, optional=True)
    if workers < 1 or workers > 32:
        raise ValueError("并发线程数必须在 1～32 之间")
    argv = [python_executable, str(workspace / "scanner.py"), "--workers", str(workers)]
    if parsed:
        argv.extend(["--date", parsed.isoformat()])
    if offline:
        argv.append("--offline")
    return CommandSpec("历史扫描" if parsed else "最新交易日扫描", argv, workspace)


def build_backtest_command(
    start: str,
    end: str,
    offline: bool,
    workers: int,
    python_executable: str = sys.executable,
    workspace: Path = WORKSPACE_DIR,
) -> CommandSpec:
    start_date = parse_date(start)
    end_date = parse_date(end)
    if start_date > end_date:
        raise ValueError("回测开始日期不能晚于结束日期")
    if workers < 1 or workers > 32:
        raise ValueError("并发线程数必须在 1～32 之间")
    argv = [
        python_executable,
        str(workspace / "backtest.py"),
        "--start",
        start_date.isoformat(),
        "--end",
        end_date.isoformat(),
        "--workers",
        str(workers),
    ]
    if offline:
        argv.append("--offline")
    return CommandSpec("历史回测", argv, workspace)


def list_reports(report_dir: Path = PACKAGE_DIR / "reports") -> list[Path]:
    reports = list(report_dir.glob("daily_report_*.md"))
    reports.extend(report_dir.glob("backtest_*.md"))
    return sorted(reports, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)


def latest_json_report(report_dir: Path = PACKAGE_DIR / "reports") -> Path | None:
    reports = sorted(
        report_dir.glob("daily_report_*.json"),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    return reports[0] if reports else None


def load_report_summary(path: Path) -> ReportSummary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    signals = list(payload.get("signals") or [])
    opportunities = [
        item
        for item in signals
        if int(item.get("score", {}).get("total", 0)) >= 7
        and item.get("signal_level") != "FAILED"
        and item.get("data_quality") == "complete"
    ]
    sorted_signals = sorted(
        signals,
        key=lambda item: (
            int(item.get("score", {}).get("total", 0)),
            int(item.get("score", {}).get("rejection", 0)),
        ),
        reverse=True,
    )
    sorted_sectors = sorted(
        list(payload.get("sectors") or []),
        key=lambda item: int(item.get("score", 0)),
        reverse=True,
    )
    return ReportSummary(
        path=path,
        report_date=str(payload.get("report_date", "--")),
        market_sessions={
            str(key): str(value)
            for key, value in (payload.get("market_sessions") or {}).items()
        },
        environments={
            str(key): str(value)
            for key, value in (payload.get("market_environment") or {}).items()
        },
        signal_count=len(signals),
        opportunity_count=len(opportunities),
        sector_count=len(sorted_sectors),
        error_count=len(payload.get("data_errors") or {}),
        signals=sorted_signals,
        sectors=sorted_sectors,
        alerts=list(payload.get("alerts") or []),
    )


def recent_scan_runs(
    database: Path = PACKAGE_DIR / "state" / "signals.db", limit: int = 10
) -> list[dict[str, Any]]:
    if not database.exists():
        return []
    with sqlite3.connect(database, timeout=20) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, report_date, started_at, completed_at, status
            FROM scan_runs ORDER BY id DESC LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def validate_editor_content(path: Path, content: str) -> None:
    if not content.strip():
        raise ValueError("内容不能为空")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            payload = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML 格式错误：{exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("YAML 顶层必须是对象")
        if path.name == "watchlist.yaml" and not {"markets", "sectors"}.issubset(payload):
            raise ValueError("watchlist.yaml 必须包含 markets 和 sectors")
        if path.name == "thresholds.yaml" and "defaults" not in payload:
            raise ValueError("thresholds.yaml 必须包含 defaults")
        return
    if path.suffix.lower() == ".csv":
        reader = csv.DictReader(io.StringIO(content))
        required = {"date", "symbol", "score", "reason", "source"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"CSV 必须包含字段：{', '.join(sorted(required))}")
        for line_number, row in enumerate(reader, 2):
            if not row or str(row.get("date", "")).lstrip().startswith("#"):
                continue
            score = str(row.get("score", "")).strip()
            if score and score not in {"0", "1", "2"}:
                raise ValueError(f"CSV 第 {line_number} 行 score 必须是 0、1 或 2")
        return
    raise ValueError(f"不支持编辑此文件类型：{path.suffix}")


def save_editor_content(path: Path, content: str) -> Path:
    validate_editor_content(path, content)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".bak")
    if path.exists():
        shutil.copy2(path, backup)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    # Run the full cross-file validation after the atomic replacement. If it fails,
    # restore the known-good backup before surfacing the error.
    if path.name in {"watchlist.yaml", "thresholds.yaml"}:
        try:
            AppConfig.load(path.parent)
        except Exception:
            if backup.exists():
                shutil.copy2(backup, path)
            raise
    return backup


def health_check() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    try:
        import PySide6

        results.append(("Qt 桌面", True, f"PySide6 {PySide6.__version__}"))
    except ImportError as exc:
        results.append(("Qt 桌面", False, str(exc)))
    try:
        config = AppConfig.load()
        results.append(
            (
                "账号自选",
                True,
                f"{config.configured_asset_count} 个标的 · {len(config.sectors)} 个检测板块",
            )
        )
    except Exception as exc:
        results.append(("配置", False, str(exc)))
    database = PACKAGE_DIR / "state" / "signals.db"
    try:
        runs = recent_scan_runs(database, 1)
        results.append(("SQLite", True, f"最近批次 {runs[0]['status']}" if runs else "尚无批次"))
    except (sqlite3.Error, OSError) as exc:
        results.append(("SQLite", False, str(exc)))
    try:
        from .research_storage import ResearchStore

        research_store = ResearchStore(database)
        with research_store.connect() as connection:
            item_count = int(
                connection.execute("SELECT COUNT(*) FROM research_items").fetchone()[0]
            )
            fact_count = int(
                connection.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0]
            )
            macro_count = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT series_id) FROM macro_observations"
                ).fetchone()[0]
            )
        results.append(
            ("研究中心", True, f"财务 {fact_count} 项 · 资讯 {item_count} 条 · 宏观 {macro_count} 组")
        )
    except (sqlite3.Error, OSError, ValueError) as exc:
        results.append(("研究中心", False, str(exc)))
    latest = latest_json_report()
    if latest:
        try:
            summary = load_report_summary(latest)
            results.append(("日报", True, f"{summary.report_date}，{summary.signal_count} 个信号"))
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            results.append(("日报", False, str(exc)))
    else:
        results.append(("日报", True, "尚无日报"))
    return results
