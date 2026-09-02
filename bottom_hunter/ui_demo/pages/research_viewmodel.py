"""PHASE 4-B — Research read-only page ViewModel."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_RESEARCH, PageViewModel
from .research_contracts import ResearchDTO, build_research_dto

LIFECYCLE_INIT = "INIT"
LIFECYCLE_LOADING = "LOADING"
LIFECYCLE_READY = "READY"
LIFECYCLE_EMPTY = "EMPTY"
LIFECYCLE_ERROR = "ERROR"


class ResearchViewModel(PageViewModel):
    """QML-friendly display state populated only through ``ResearchDTO``."""

    changed = Signal()
    lifecycleChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_RESEARCH, "研究", parent)
        self._assets: list[dict[str, Any]] = []
        self._macro: list[dict[str, Any]] = []
        self._generated_at = ""
        self._report_date = "--"
        self._lifecycle = LIFECYCLE_INIT
        self._loaded = False
        self._error = ""

    @Property("QVariantList", notify=changed)
    def assets(self) -> list:  # noqa: N802
        return self._assets

    @Property("QVariantList", notify=changed)
    def macro(self) -> list:  # noqa: N802
        return self._macro

    @Property(int, notify=changed)
    def assetCount(self) -> int:  # noqa: N802
        return len(self._assets)

    @Property(int, notify=changed)
    def macroCount(self) -> int:  # noqa: N802
        return len(self._macro)

    @Property(str, notify=changed)
    def generatedAt(self) -> str:  # noqa: N802
        return self._generated_at

    @Property(str, notify=changed)
    def reportDate(self) -> str:  # noqa: N802
        return self._report_date

    @Property(str, notify=lifecycleChanged)
    def lifecycle(self) -> str:  # noqa: N802
        return self._lifecycle

    @Property(bool, notify=changed)
    def loaded(self) -> bool:  # noqa: N802
        return self._loaded

    @Property(str, notify=changed)
    def error(self) -> str:  # noqa: N802
        return self._error

    def apply(self, dto: ResearchDTO) -> None:  # noqa: N802
        self._assets = [asset.as_dict() for asset in dto.assets]
        self._macro = [item.as_dict() for item in dto.macro]
        self._generated_at = str(dto.generated_at)
        self._report_date = str(dto.report_date)
        self._loaded = True
        self._error = ""
        lifecycle = LIFECYCLE_READY if self._assets or self._macro else LIFECYCLE_EMPTY
        self._set_lifecycle(lifecycle)
        self.changed.emit()

    def applyError(self, message: str) -> None:  # noqa: N802
        self._assets = []
        self._macro = []
        self._error = str(message)
        self._loaded = False
        self._set_lifecycle(LIFECYCLE_ERROR)
        self.changed.emit()

    def markLoading(self) -> None:  # noqa: N802
        self._set_lifecycle(LIFECYCLE_LOADING)

    def _set_lifecycle(self, value: str) -> None:
        if value != self._lifecycle:
            self._lifecycle = value
            self.lifecycleChanged.emit()

    @Slot()
    def refresh(self) -> None:  # noqa: N802
        self.markLoading()
        try:
            dto = build_research_dto()
        except (OSError, ValueError) as exc:
            self.applyError(str(exc))
            return
        self.apply(dto or ResearchDTO())
