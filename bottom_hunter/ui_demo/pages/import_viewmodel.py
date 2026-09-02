"""PHASE 4-D1 — Import preview-only ViewModel."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_IMPORT, PageViewModel
from .import_contracts import ImportPreviewDTO
from .import_preview_adapter import ImportPreviewError, build_import_preview_dto

LIFECYCLE_INIT = "INIT"
LIFECYCLE_SELECTING = "SELECTING"
LIFECYCLE_PREVIEWING = "PREVIEWING"
LIFECYCLE_READY = "READY"
LIFECYCLE_ERROR = "ERROR"


class ImportViewModel(PageViewModel):
    """Display state and user intent for a zero-write file preview."""

    changed = Signal()
    lifecycleChanged = Signal()
    previewRequested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(PAGE_IMPORT, "导入", parent)
        self._filename = ""
        self._format = ""
        self._detected_count = 0
        self._valid_count = 0
        self._invalid_count = 0
        self._warnings: list[str] = []
        self._preview_items: list[dict[str, Any]] = []
        self._lifecycle = LIFECYCLE_INIT
        self._error = ""

    @Property(str, notify=changed)
    def filename(self) -> str:
        return self._filename

    @Property(str, notify=changed)
    def fileFormat(self) -> str:  # noqa: N802
        return self._format

    @Property(int, notify=changed)
    def detectedCount(self) -> int:  # noqa: N802
        return self._detected_count

    @Property(int, notify=changed)
    def validCount(self) -> int:  # noqa: N802
        return self._valid_count

    @Property(int, notify=changed)
    def invalidCount(self) -> int:  # noqa: N802
        return self._invalid_count

    @Property("QVariantList", notify=changed)
    def warnings(self) -> list:
        return self._warnings

    @Property("QVariantList", notify=changed)
    def previewItems(self) -> list:  # noqa: N802
        return self._preview_items

    @Property(str, notify=lifecycleChanged)
    def lifecycle(self) -> str:
        return self._lifecycle

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    def apply(self, dto: ImportPreviewDTO) -> None:  # noqa: N802
        self._filename = str(dto.filename)
        self._format = str(dto.format)
        self._detected_count = int(dto.detected_count)
        self._valid_count = int(dto.valid_count)
        self._invalid_count = int(dto.invalid_count)
        self._warnings = list(dto.warnings)
        self._preview_items = [item.as_dict() for item in dto.preview_items]
        self._error = ""
        self._set_lifecycle(LIFECYCLE_READY)
        self.changed.emit()

    def applyError(self, message: str) -> None:  # noqa: N802
        self._filename = ""
        self._format = ""
        self._detected_count = 0
        self._valid_count = 0
        self._invalid_count = 0
        self._warnings = []
        self._preview_items = []
        self._error = str(message)
        self._set_lifecycle(LIFECYCLE_ERROR)
        self.changed.emit()

    def _set_lifecycle(self, value: str) -> None:
        if value != self._lifecycle:
            self._lifecycle = value
            self.lifecycleChanged.emit()

    @Slot()
    def beginSelection(self) -> None:  # noqa: N802
        self._set_lifecycle(LIFECYCLE_SELECTING)

    @Slot(str, str)
    def requestPreview(self, selection: str, source: str) -> None:  # noqa: N802
        self._set_lifecycle(LIFECYCLE_SELECTING)
        self.previewRequested.emit(str(selection), str(source))
        self._set_lifecycle(LIFECYCLE_PREVIEWING)
        try:
            dto = build_import_preview_dto(selection, source)
        except (ImportPreviewError, OSError, ValueError) as exc:
            self.applyError(str(exc))
            return
        self.apply(dto)
