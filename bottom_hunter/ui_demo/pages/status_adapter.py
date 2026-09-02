"""Read-only adapter over existing health checks and report snapshots."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .status_contracts import StatusDTO, StatusItemDTO

REPORT_DIR = Path(__file__).resolve().parents[2] / "reports"


def _latest_report(report_dir: Path) -> Path | None:
    reports = sorted(report_dir.glob("daily_report_*.json"))
    return reports[-1] if reports else None


def _read_report_status(path: Path | None) -> tuple[str, str, tuple[str, ...]]:
    if path is None:
        return "尚无日报快照", "--", ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取状态快照：{path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"状态快照格式无效：{path.name}")

    raw_errors = payload.get("data_errors") or {}
    if isinstance(raw_errors, dict):
        errors = tuple(f"{key}：{value}" for key, value in list(raw_errors.items())[:5])
        error_count = len(raw_errors)
    elif isinstance(raw_errors, list):
        errors = tuple(str(value) for value in raw_errors[:5])
        error_count = len(raw_errors)
    else:
        errors = (str(raw_errors),)
        error_count = 1
    data_status = "数据正常" if error_count == 0 else f"发现 {error_count} 项数据异常"
    last_scan = str(payload.get("generated_at") or payload.get("report_date") or "--")
    return data_status, last_scan, errors


def build_status_dto(
    report_dir: Path = REPORT_DIR,
    *,
    health_reader: Callable[[], list[tuple[str, bool, str]]] | None = None,
) -> StatusDTO:
    """Build display status without starting or modifying runtime modules."""

    if health_reader is None:
        from bottom_hunter.src import gui_core

        health_reader = gui_core.health_check

    rows = tuple(StatusItemDTO(str(name), bool(ok), str(detail)) for name, ok, detail in health_reader())
    data_status, last_scan, recent_errors = _read_report_status(_latest_report(Path(report_dir)))
    ok_count = sum(item.ok for item in rows)
    all_healthy = bool(rows) and ok_count == len(rows)
    return StatusDTO(
        data_status=data_status,
        last_scan_time=last_scan,
        system_health="正常" if all_healthy else "需检查",
        items=rows,
        recent_errors=recent_errors,
        ok_count=ok_count,
        total_count=len(rows),
        generated_at=datetime.now(UTC).isoformat(),
    )
