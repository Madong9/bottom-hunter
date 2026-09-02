"""Import page state, DTO projection, and user-intent signals."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, Signal, Slot

from . import PAGE_IMPORT, PageViewModel
from .import_contracts import FileFingerprintDTO, ImportPreviewDTO, ImportResultDTO
from .import_preview_adapter import ImportPreviewError, build_import_preview_dto

LIFECYCLE_INIT = "INIT"
LIFECYCLE_SELECTING = "SELECTING"
LIFECYCLE_PREVIEWING = "PREVIEWING"
LIFECYCLE_READY = "READY"
LIFECYCLE_IMPORTING = "IMPORTING"
LIFECYCLE_SUCCESS = "SUCCESS"
LIFECYCLE_PARTIAL_REVIEW = "PARTIAL_REVIEW"
LIFECYCLE_ERROR = "ERROR"

_IMPORTING_STATES = frozenset({"QUEUED", "VALIDATING", "STAGING", "VERIFYING", "COMMITTING"})


class ImportViewModel(PageViewModel):
    """Owns display state while the controller owns command execution."""

    changed = Signal()
    lifecycleChanged = Signal()
    previewRequested = Signal(str, str)
    importRequested = Signal(str, str, object)
    cancelRequested = Signal()
    partialAccepted = Signal()
    retryRequested = Signal()

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
        self._selection = ""
        self._source = ""
        self._file_fingerprint: FileFingerprintDTO | None = None
        self._active_command_id = ""
        self._result: dict[str, Any] = {}
        self._result_warnings: list[str] = []
        self._progress = 0
        self._progress_message = ""

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

    @Property("QVariantMap", notify=changed)
    def result(self) -> dict:
        return self._result

    @Property("QVariantList", notify=changed)
    def resultWarnings(self) -> list:  # noqa: N802
        return self._result_warnings

    @Property(str, notify=changed)
    def activeCommandId(self) -> str:  # noqa: N802
        return self._active_command_id

    @Property(int, notify=changed)
    def progress(self) -> int:
        return self._progress

    @Property(str, notify=changed)
    def progressMessage(self) -> str:  # noqa: N802
        return self._progress_message

    def apply(self, dto: ImportPreviewDTO) -> None:  # noqa: N802
        self._filename = str(dto.filename)
        self._format = str(dto.format)
        self._detected_count = int(dto.detected_count)
        self._valid_count = int(dto.valid_count)
        self._invalid_count = int(dto.invalid_count)
        self._warnings = list(dto.warnings)
        self._preview_items = [item.as_dict() for item in dto.preview_items]
        self._file_fingerprint = dto.file_fingerprint
        self._error = ""
        self._result = {}
        self._result_warnings = []
        self._progress = 0
        self._progress_message = ""
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
        self._file_fingerprint = None
        self._result = {}
        self._result_warnings = []
        self._error = str(message)
        self._set_lifecycle(LIFECYCLE_ERROR)
        self.changed.emit()

    @Slot(str)
    def applyControllerState(self, state: str) -> None:  # noqa: N802
        normalized = str(state)
        if normalized in _IMPORTING_STATES:
            self._set_lifecycle(LIFECYCLE_IMPORTING)
        elif normalized == "PARTIAL_REVIEW":
            self._set_lifecycle(LIFECYCLE_PARTIAL_REVIEW)
        elif normalized == "CANCELLED":
            self._set_lifecycle(LIFECYCLE_READY)

    @Slot(int, str)
    def applyProgress(self, value: int, message: str) -> None:  # noqa: N802
        self._progress = max(0, min(100, int(value)))
        self._progress_message = str(message)
        self.changed.emit()

    @Slot(object)
    def applyResult(self, dto: ImportResultDTO) -> None:  # noqa: N802
        self._active_command_id = str(dto.command_id)
        self._result_warnings = list(dto.warnings)
        self._result = {
            "status": dto.status,
            "filename": dto.filename,
            "importedCount": dto.imported_count,
            "mergedCount": dto.merged_count,
            "duplicateCount": dto.duplicate_count,
            "invalidCount": dto.invalid_count,
            "unresolvedIndustryCount": dto.unresolved_industry_count,
            "generatedSectorCount": dto.generated_sector_count,
            "committed": dto.committed,
            "rollbackPerformed": dto.rollback_performed,
        }
        if dto.status == "SUCCESS":
            self._error = ""
            self._set_lifecycle(LIFECYCLE_SUCCESS)
        elif dto.status == "PARTIAL_REVIEW":
            self._error = ""
            self._set_lifecycle(LIFECYCLE_PARTIAL_REVIEW)
        elif dto.status == "CANCELLED":
            self._error = ""
            self._set_lifecycle(LIFECYCLE_READY)
        else:
            self._error = dto.error.message if dto.error is not None else "导入失败，请重试。"
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
        self._selection = str(selection)
        self._source = str(source)
        self._set_lifecycle(LIFECYCLE_SELECTING)
        self.previewRequested.emit(self._selection, self._source)
        self._set_lifecycle(LIFECYCLE_PREVIEWING)
        try:
            dto = build_import_preview_dto(selection, source)
        except (ImportPreviewError, OSError, ValueError) as exc:
            self.applyError(str(exc))
            return
        self.apply(dto)

    @Slot()
    def confirmImport(self) -> None:  # noqa: N802
        if (
            self._lifecycle != LIFECYCLE_READY
            or self._valid_count <= 0
            or self._file_fingerprint is None
        ):
            return
        self._set_lifecycle(LIFECYCLE_IMPORTING)
        self.importRequested.emit(self._selection, self._source, self._file_fingerprint)

    @Slot()
    def cancelImport(self) -> None:  # noqa: N802
        if self._lifecycle not in {LIFECYCLE_IMPORTING, LIFECYCLE_PARTIAL_REVIEW}:
            return
        self.cancelRequested.emit()

    @Slot()
    def acceptPartial(self) -> None:  # noqa: N802
        if self._lifecycle != LIFECYCLE_PARTIAL_REVIEW:
            return
        self._set_lifecycle(LIFECYCLE_IMPORTING)
        self.partialAccepted.emit()

    @Slot()
    def retryImport(self) -> None:  # noqa: N802
        if self._lifecycle != LIFECYCLE_ERROR or not self._selection:
            return
        self._error = ""
        self._set_lifecycle(LIFECYCLE_IMPORTING)
        self.retryRequested.emit()
