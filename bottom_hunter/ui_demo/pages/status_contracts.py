"""Pure immutable contracts for the read-only product status page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StatusItemDTO:
    name: str = "--"
    ok: bool = False
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class StatusDTO:
    data_status: str = "等待状态快照"
    last_scan_time: str = "--"
    system_health: str = "未知"
    items: tuple[StatusItemDTO, ...] = field(default_factory=tuple)
    recent_errors: tuple[str, ...] = field(default_factory=tuple)
    ok_count: int = 0
    total_count: int = 0
    generated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "data_status": self.data_status,
            "last_scan_time": self.last_scan_time,
            "system_health": self.system_health,
            "items": [item.as_dict() for item in self.items],
            "recent_errors": list(self.recent_errors),
            "ok_count": self.ok_count,
            "total_count": self.total_count,
            "generated_at": self.generated_at,
        }
