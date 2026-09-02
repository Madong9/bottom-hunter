"""Display-only ViewModel for the read-only status snapshot."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_STATUS, PageViewModel
from .status_adapter import build_status_dto
from .status_contracts import StatusDTO, StatusItemDTO

LIFECYCLE_INIT = "INIT"
LIFECYCLE_LOADING = "LOADING"
LIFECYCLE_READY = "READY"
LIFECYCLE_EMPTY = "EMPTY"
LIFECYCLE_ERROR = "ERROR"


class StatusViewModel(PageViewModel):
    changed = Signal()
    lifecycleChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_STATUS, "状态", parent)
        self._data_status = "等待状态快照"
        self._last_scan_time = "--"
        self._system_health = "未知"
        self._items: list[dict[str, Any]] = []
        self._recent_errors: list[str] = []
        self._ok_count = 0
        self._total_count = 0
        self._generated_at = ""
        self._lifecycle = LIFECYCLE_INIT
        self._error = ""

    @Property(str, notify=changed)
    def dataStatus(self) -> str:  # noqa: N802
        return self._data_status

    @Property(str, notify=changed)
    def lastScanTime(self) -> str:  # noqa: N802
        return self._last_scan_time

    @Property(str, notify=changed)
    def systemHealth(self) -> str:  # noqa: N802
        return self._system_health

    @Property("QVariantList", notify=changed)
    def items(self) -> list:
        return self._items

    @Property("QVariantList", notify=changed)
    def recentErrors(self) -> list:  # noqa: N802
        return self._recent_errors

    @Property(int, notify=changed)
    def okCount(self) -> int:  # noqa: N802
        return self._ok_count

    @Property(int, notify=changed)
    def totalCount(self) -> int:  # noqa: N802
        return self._total_count

    @Property(str, notify=changed)
    def generatedAt(self) -> str:  # noqa: N802
        return self._generated_at

    @Property(str, notify=lifecycleChanged)
    def lifecycle(self) -> str:
        return self._lifecycle

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=changed)
    def loaded(self) -> bool:
        return self._lifecycle in {LIFECYCLE_READY, LIFECYCLE_EMPTY}

    def apply(self, dto: StatusDTO | Any) -> None:
        raw_items = getattr(dto, "items", ())
        self._items = [
            item.as_dict()
            if isinstance(item, StatusItemDTO)
            else {"name": str(item[0]), "ok": bool(item[1]), "detail": str(item[2])}
            for item in raw_items
        ]
        self._data_status = str(getattr(dto, "data_status", "数据状态已读取"))
        self._last_scan_time = str(getattr(dto, "last_scan_time", "--"))
        self._system_health = str(getattr(dto, "system_health", "正常" if self._items else "未知"))
        self._recent_errors = [str(item) for item in getattr(dto, "recent_errors", ())]
        self._ok_count = int(getattr(dto, "ok_count", 0))
        self._total_count = int(getattr(dto, "total_count", len(self._items)))
        self._generated_at = str(getattr(dto, "generated_at", ""))
        self._error = ""
        self._set_lifecycle(LIFECYCLE_READY if self._items else LIFECYCLE_EMPTY)
        self.changed.emit()

    def applyError(self, message: str) -> None:  # noqa: N802
        self._error = str(message)
        self._set_lifecycle(LIFECYCLE_ERROR)
        self.changed.emit()

    def markLoading(self) -> None:  # noqa: N802
        self._set_lifecycle(LIFECYCLE_LOADING)

    def _set_lifecycle(self, value: str) -> None:
        if value != self._lifecycle:
            self._lifecycle = value
            self.lifecycleChanged.emit()

    @Slot()
    def refresh(self) -> None:
        self.markLoading()
        try:
            dto = build_status_dto()
        except (OSError, ValueError) as exc:
            self.applyError(str(exc))
            return
        self.apply(dto)
