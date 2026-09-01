"""PHASE 3-C — Page ViewModels wired through DTO adapters (Report / Status).

Each PageViewModel is a pure display-state QObject; adapters (contracts.py)
feed it DTOs. No business import here and no metric computation.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PageViewModel, PAGE_REPORT, PAGE_STATUS
from .contracts import ReportDTO, StatusDTO, build_report_dto, build_status_dto


class ReportViewModel(PageViewModel):
    """Display state for the 报告 page (frozen ReportDTO contract)."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_REPORT, "报告", parent)
        self._report_date = "--"
        self._signal_count = 0
        self._opportunity_count = 0
        self._sector_count = 0
        self._error_count = 0
        self._loaded = False

    @Property(str, notify=changed)
    def reportDate(self) -> str:  # noqa: N802
        return self._report_date

    @Property(int, notify=changed)
    def signalCount(self) -> int:  # noqa: N802
        return self._signal_count

    @Property(int, notify=changed)
    def opportunityCount(self) -> int:  # noqa: N802
        return self._opportunity_count

    @Property(int, notify=changed)
    def sectorCount(self) -> int:  # noqa: N802
        return self._sector_count

    @Property(int, notify=changed)
    def errorCount(self) -> int:  # noqa: N802
        return self._error_count

    @Property(bool, notify=changed)
    def loaded(self) -> bool:  # noqa: N802
        return self._loaded

    def apply(self, dto: ReportDTO) -> None:  # noqa: N802
        self._report_date = str(dto.report_date)
        self._signal_count = int(dto.signal_count)
        self._opportunity_count = int(dto.opportunity_count)
        self._sector_count = int(dto.sector_count)
        self._error_count = int(dto.error_count)
        self._loaded = True
        self.changed.emit()

    @Slot()
    def refresh(self) -> None:  # noqa: N802
        dto = build_report_dto()
        if dto is not None:
            self.apply(dto)


class StatusViewModel(PageViewModel):
    """Display state for the 状态 page (frozen StatusDTO contract)."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_STATUS, "状态", parent)
        self._items: list[dict[str, Any]] = []
        self._ok_count = 0
        self._total_count = 0
        self._loaded = False

    @Property("QVariantList", notify=changed)
    def items(self) -> list:  # noqa: N802
        return self._items

    @Property(int, notify=changed)
    def okCount(self) -> int:  # noqa: N802
        return self._ok_count

    @Property(int, notify=changed)
    def totalCount(self) -> int:  # noqa: N802
        return self._total_count

    @Property(bool, notify=changed)
    def loaded(self) -> bool:  # noqa: N802
        return self._loaded

    def apply(self, dto: StatusDTO) -> None:  # noqa: N802
        self._items = [{"name": n, "ok": ok, "detail": d} for n, ok, d in dto.items]
        self._ok_count = int(dto.ok_count)
        self._total_count = int(dto.total_count)
        self._loaded = True
        self.changed.emit()

    @Slot()
    def refresh(self) -> None:  # noqa: N802
        self.apply(build_status_dto())
