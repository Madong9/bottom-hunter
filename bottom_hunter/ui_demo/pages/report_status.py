"""Read-only Report ViewModel and compatibility export for Status."""

from __future__ import annotations

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_REPORT, PageViewModel
from .contracts import ReportDTO, build_report_dto
from .status_viewmodel import StatusViewModel

LIFECYCLE_INIT = "INIT"
LIFECYCLE_LOADING = "LOADING"
LIFECYCLE_READY = "READY"
LIFECYCLE_EMPTY = "EMPTY"
LIFECYCLE_ERROR = "ERROR"


class ReportViewModel(PageViewModel):
    """Display state for the latest generated report snapshot."""

    changed = Signal()
    lifecycleChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_REPORT, "报告", parent)
        self._report_date = "--"
        self._signal_count = 0
        self._opportunity_count = 0
        self._sector_count = 0
        self._error_count = 0
        self._loaded = False
        self._lifecycle = LIFECYCLE_INIT
        self._error = ""

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
    def loaded(self) -> bool:
        return self._loaded

    @Property(str, notify=lifecycleChanged)
    def lifecycle(self) -> str:
        return self._lifecycle

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    def apply(self, dto: ReportDTO) -> None:
        self._report_date = str(dto.report_date)
        self._signal_count = int(dto.signal_count)
        self._opportunity_count = int(dto.opportunity_count)
        self._sector_count = int(dto.sector_count)
        self._error_count = int(dto.error_count)
        self._loaded = True
        self._error = ""
        self._set_lifecycle(LIFECYCLE_READY if self._report_date != "--" else LIFECYCLE_EMPTY)
        self.changed.emit()

    def applyError(self, message: str) -> None:  # noqa: N802
        self._loaded = False
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
            dto = build_report_dto()
        except (OSError, ValueError) as exc:
            self.applyError(str(exc))
            return
        self.apply(dto or ReportDTO())


__all__ = ["ReportViewModel", "StatusViewModel"]
