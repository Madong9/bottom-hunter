"""PHASE 4-D3-A — Import command architecture with abstract ports only.

No production backend is imported or wired here.  The controller coordinates
validation, exclusion, cancellation, staged verification, commit and rollback
through injected Protocols.  Tests use in-memory fakes exclusively.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePath
from threading import Lock
from typing import Protocol

from PySide6.QtCore import Property, QObject, Signal

from .import_contracts import (
    FileFingerprintDTO,
    ImportCommandDTO,
    ImportErrorDTO,
    ImportResultDTO,
)

SUPPORTED_SOURCES = frozenset({"tonghuashun", "binance", "okx"})


class ImportCommandState(StrEnum):
    IDLE = "IDLE"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    STAGING = "STAGING"
    VERIFYING = "VERIFYING"
    PARTIAL_REVIEW = "PARTIAL_REVIEW"
    COMMITTING = "COMMITTING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True)
class StagedImportDTO:
    """Backend-neutral summary retained inside the command boundary."""

    imported_count: int = 0
    merged_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0
    unresolved_industry_count: int = 0
    generated_sector_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def partial(self) -> bool:
        return bool(self.invalid_count or self.unresolved_industry_count or self.warnings)


class MutationPort(Protocol):
    """Abstract backend command port; no production implementation in D3-A."""

    def current_fingerprint(self, file_path: str) -> FileFingerprintDTO: ...

    def stage(self, command: ImportCommandDTO, workspace: TransactionWorkspace) -> StagedImportDTO: ...

    def verify(self, staged: StagedImportDTO, workspace: TransactionWorkspace) -> None: ...


class TransactionWorkspace(Protocol):
    """Abstract staging/commit/rollback workspace."""

    def prepare(self, command: ImportCommandDTO) -> None: ...

    def stage(self, staged: StagedImportDTO) -> None: ...

    def verify(self, staged: StagedImportDTO) -> None: ...

    def commit(self, staged: StagedImportDTO) -> None: ...

    def rollback(self) -> None: ...

    def discard(self) -> None: ...


class RuntimeActivityPort(Protocol):
    """Reports a conflicting scan/backtest/sync operation, if any."""

    def active_operation(self) -> str: ...


class ImportCommandGate:
    """Thread-safe single-owner command gate with no external side effects."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._owner = ""

    @property
    def owner(self) -> str:
        with self._lock:
            return self._owner

    def acquire(self, command_id: str) -> bool:
        with self._lock:
            if self._owner:
                return False
            self._owner = command_id
            return True

    def release(self, command_id: str) -> None:
        with self._lock:
            if self._owner == command_id:
                self._owner = ""


@dataclass
class _PendingCommand:
    command: ImportCommandDTO
    workspace: TransactionWorkspace
    staged: StagedImportDTO
    started_at: str


class ImportController(QObject):
    """State machine coordinating only injected command interfaces."""

    stateChanged = Signal(str)
    resultReady = Signal(object)

    def __init__(
        self,
        mutation_port: MutationPort,
        workspace_factory: Callable[[], TransactionWorkspace],
        runtime_activity: RuntimeActivityPort,
        gate: ImportCommandGate,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._mutation_port = mutation_port
        self._workspace_factory = workspace_factory
        self._runtime_activity = runtime_activity
        self._gate = gate
        self._state = ImportCommandState.IDLE
        self._active_command_id = ""
        self._cancel_requested = False
        self._pending: _PendingCommand | None = None

    @Property(str, notify=stateChanged)
    def state(self) -> str:
        return self._state.value

    @Property(str, notify=stateChanged)
    def activeCommandId(self) -> str:  # noqa: N802
        return self._active_command_id

    def submit(self, command: ImportCommandDTO) -> ImportResultDTO:
        """Run synchronously through abstract ports; a host may place this on a worker."""

        started_at = _now()
        self._set_state(ImportCommandState.QUEUED)
        if not self._gate.acquire(command.command_id):
            return self._finish_failure(
                command,
                started_at,
                _error(command, "IMPORT_BUSY", ImportCommandState.QUEUED, "另一个导入任务正在运行。", True),
                release_gate=False,
            )

        self._active_command_id = command.command_id
        self._cancel_requested = False
        self._set_state(ImportCommandState.VALIDATING)

        validation_error = self._validate(command)
        if validation_error is not None:
            return self._finish_failure(command, started_at, validation_error)

        active_operation = self._runtime_activity.active_operation().strip()
        if active_operation:
            return self._finish_failure(
                command,
                started_at,
                _error(
                    command,
                    "RUNTIME_BUSY",
                    ImportCommandState.VALIDATING,
                    f"请等待{active_operation}完成后重试。",
                    True,
                ),
            )

        try:
            actual_fingerprint = self._mutation_port.current_fingerprint(command.file_path)
        except Exception:
            return self._finish_failure(
                command,
                started_at,
                _error(
                    command,
                    "FINGERPRINT_FAILED",
                    ImportCommandState.VALIDATING,
                    "无法验证所选文件，请重新预览。",
                    True,
                ),
            )
        if actual_fingerprint != command.file_fingerprint:
            return self._finish_failure(
                command,
                started_at,
                _error(
                    command,
                    "FILE_CHANGED",
                    ImportCommandState.VALIDATING,
                    "文件在预览后已变化，请重新预览。",
                    True,
                ),
            )
        if self._cancel_requested:
            return self._finish_cancelled(command, started_at)

        workspace = self._workspace_factory()
        try:
            workspace.prepare(command)
            self._set_state(ImportCommandState.STAGING)
            staged = self._mutation_port.stage(command, workspace)
        except Exception:
            _safe_discard(workspace)
            return self._finish_failure(
                command,
                started_at,
                _error(command, "STAGING_FAILED", ImportCommandState.STAGING, "导入暂存失败，未修改当前数据。", True),
            )
        if self._cancel_requested:
            _safe_discard(workspace)
            return self._finish_cancelled(command, started_at, staged)

        self._set_state(ImportCommandState.VERIFYING)
        try:
            self._mutation_port.verify(staged, workspace)
        except Exception:
            _safe_discard(workspace)
            return self._finish_failure(
                command,
                started_at,
                _error(
                    command,
                    "VERIFY_FAILED",
                    ImportCommandState.VERIFYING,
                    "暂存结果校验失败，未修改当前数据。",
                    False,
                ),
                staged,
            )
        if self._cancel_requested:
            _safe_discard(workspace)
            return self._finish_cancelled(command, started_at, staged)

        if staged.partial and not command.allow_partial:
            self._pending = _PendingCommand(command, workspace, staged, started_at)
            self._set_state(ImportCommandState.PARTIAL_REVIEW)
            result = self._map_result(command, staged, "PARTIAL_REVIEW", started_at)
            self.resultReady.emit(result)
            return result

        return self._commit(command, workspace, staged, started_at)

    def accept_partial(self, command_id: str) -> ImportResultDTO | None:
        pending = self._pending
        if pending is None or pending.command.command_id != command_id:
            return None
        self._pending = None
        return self._commit(pending.command, pending.workspace, pending.staged, pending.started_at)

    def cancel(self, command_id: str) -> bool:
        if not command_id or command_id != self._active_command_id:
            return False
        if self._state == ImportCommandState.PARTIAL_REVIEW and self._pending is not None:
            pending = self._pending
            self._pending = None
            _safe_discard(pending.workspace)
            self._finish_cancelled(pending.command, pending.started_at, pending.staged)
            return True
        if self._state in {
            ImportCommandState.QUEUED,
            ImportCommandState.VALIDATING,
            ImportCommandState.STAGING,
            ImportCommandState.VERIFYING,
        }:
            self._cancel_requested = True
            return True
        return False

    def _validate(self, command: ImportCommandDTO) -> ImportErrorDTO | None:
        valid = (
            bool(command.command_id.strip())
            and bool(command.preview_id.strip())
            and command.source in SUPPORTED_SOURCES
            and bool(command.file_path.strip())
            and command.file_fingerprint.size >= 0
            and command.file_fingerprint.mtime_ns >= 0
            and bool(command.file_fingerprint.sha256.strip())
        )
        if valid:
            return None
        return _error(
            command,
            "INVALID_COMMAND",
            ImportCommandState.VALIDATING,
            "导入命令不完整，请重新预览文件。",
            False,
        )

    def _commit(
        self,
        command: ImportCommandDTO,
        workspace: TransactionWorkspace,
        staged: StagedImportDTO,
        started_at: str,
    ) -> ImportResultDTO:
        self._set_state(ImportCommandState.COMMITTING)
        try:
            workspace.commit(staged)
        except Exception:
            try:
                workspace.rollback()
            except Exception:
                return self._finish_failure(
                    command,
                    started_at,
                    _error(
                        command,
                        "ROLLBACK_FAILED",
                        ImportCommandState.RECOVERY_REQUIRED,
                        "提交和回滚均失败，需要人工检查导入状态。",
                        False,
                    ),
                    staged,
                    state=ImportCommandState.RECOVERY_REQUIRED,
                )
            return self._finish_failure(
                command,
                started_at,
                _error(command, "COMMIT_FAILED", ImportCommandState.COMMITTING, "提交失败，已恢复原有数据。", True),
                staged,
                rollback_performed=True,
            )

        self._set_state(ImportCommandState.SUCCESS)
        result = self._map_result(command, staged, "SUCCESS", started_at, committed=True)
        return self._finish_terminal(command.command_id, result)

    def _finish_failure(
        self,
        command: ImportCommandDTO,
        started_at: str,
        error: ImportErrorDTO,
        staged: StagedImportDTO | None = None,
        *,
        rollback_performed: bool = False,
        state: ImportCommandState = ImportCommandState.FAILED,
        release_gate: bool = True,
    ) -> ImportResultDTO:
        self._set_state(state)
        result = self._map_result(
            command,
            staged or StagedImportDTO(),
            state.value,
            started_at,
            rollback_performed=rollback_performed,
            error=error,
        )
        return self._finish_terminal(command.command_id, result, release_gate=release_gate)

    def _finish_cancelled(
        self,
        command: ImportCommandDTO,
        started_at: str,
        staged: StagedImportDTO | None = None,
    ) -> ImportResultDTO:
        self._set_state(ImportCommandState.CANCELLED)
        result = self._map_result(command, staged or StagedImportDTO(), "CANCELLED", started_at)
        return self._finish_terminal(command.command_id, result)

    def _finish_terminal(
        self,
        command_id: str,
        result: ImportResultDTO,
        *,
        release_gate: bool = True,
    ) -> ImportResultDTO:
        if release_gate:
            self._gate.release(command_id)
        if self._active_command_id == command_id:
            self._active_command_id = ""
            self._cancel_requested = False
        self.resultReady.emit(result)
        return result

    @staticmethod
    def _map_result(
        command: ImportCommandDTO,
        staged: StagedImportDTO,
        status: str,
        started_at: str,
        *,
        committed: bool = False,
        rollback_performed: bool = False,
        error: ImportErrorDTO | None = None,
    ) -> ImportResultDTO:
        return ImportResultDTO(
            command_id=command.command_id,
            source=command.source,
            filename=PurePath(command.file_path).name,
            status=status,
            committed=committed,
            rollback_performed=rollback_performed,
            imported_count=staged.imported_count,
            merged_count=staged.merged_count,
            duplicate_count=staged.duplicate_count,
            invalid_count=staged.invalid_count,
            unresolved_industry_count=staged.unresolved_industry_count,
            generated_sector_count=staged.generated_sector_count,
            warnings=staged.warnings,
            error=error,
            started_at=started_at,
            finished_at=_now() if status != "PARTIAL_REVIEW" else "",
        )

    def _set_state(self, state: ImportCommandState) -> None:
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state.value)


def _error(
    command: ImportCommandDTO,
    code: str,
    stage: ImportCommandState,
    message: str,
    retryable: bool,
) -> ImportErrorDTO:
    return ImportErrorDTO(
        code=code,
        stage=stage.value,
        message=message,
        retryable=retryable,
        technical_reference=command.command_id,
    )


def _safe_discard(workspace: TransactionWorkspace) -> None:
    try:
        workspace.discard()
    except Exception:
        pass


def _now() -> str:
    return datetime.now(UTC).isoformat()
