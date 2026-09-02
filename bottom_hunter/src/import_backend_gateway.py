"""Production gateway joining command adapters to backend import transactions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .account_watchlist import AccountWatchlistRepository, _prepared_file_fingerprint
from .import_lock import ImportProcessLock
from .import_transaction import PreparedImport
from .import_transaction_workspace import (
    FailureInjector,
    ImportConflictError,
    ImportTransactionWorkspace,
    commit_prepared_import,
)


@dataclass(frozen=True)
class BackendFingerprint:
    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class BackendPreparedSummary:
    imported_count: int
    merged_count: int
    duplicate_count: int
    invalid_count: int
    unresolved_industry_count: int
    generated_sector_count: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BackendCommittedResult:
    command_id: str
    source: str
    filename: str
    imported_count: int
    merged_count: int
    duplicate_count: int
    invalid_count: int
    unresolved_industry_count: int
    generated_sector_count: int
    warnings: tuple[str, ...]
    active_watchlist: str
    committed_at: str


class AccountWatchlistTransactionGateway:
    """Owns backend objects so none cross into QML/ViewModel contracts."""

    def __init__(
        self,
        repository: AccountWatchlistRepository,
        *,
        workspace_failure_injector: FailureInjector | None = None,
    ) -> None:
        self._repository = repository
        self._workspace_failure_injector = workspace_failure_injector
        self._locks: dict[str, ImportProcessLock] = {}
        self._prepared: dict[str, PreparedImport] = {}
        self._workspaces: dict[str, ImportTransactionWorkspace] = {}

    def begin(self, command_id: str) -> None:
        if command_id in self._locks:
            raise RuntimeError("导入命令已经开始")
        process_lock = ImportProcessLock(self._repository.state_dir, command_id)
        process_lock.acquire()
        self._locks[command_id] = process_lock

    def staging_location(self, command_id: str) -> str:
        return str(self._repository.state_dir / ".import_transactions" / command_id)

    def read_fingerprint(self, file_path: str) -> BackendFingerprint:
        fingerprint = _prepared_file_fingerprint(Path(file_path).expanduser().resolve())
        return BackendFingerprint(fingerprint.size, fingerprint.mtime_ns, fingerprint.sha256)

    def prepare_import(self, command: Any, staging_location: str) -> BackendPreparedSummary:
        command_id = str(command.command_id)
        self._require_lock(command_id)
        if staging_location != self.staging_location(command_id):
            raise ValueError("staging location 与 command 不匹配")
        prepared = self._repository.prepare_import(
            str(command.source),
            str(command.file_path),
            str(command.account_alias),
            resolve_industries=True,
            transaction_id=command_id,
        )
        self._prepared[command_id] = prepared
        return BackendPreparedSummary(
            imported_count=prepared.imported_count,
            merged_count=prepared.merged_count,
            duplicate_count=prepared.duplicate_count,
            invalid_count=len(prepared.warnings),
            unresolved_industry_count=prepared.unresolved_industry_count,
            generated_sector_count=prepared.generated_sector_count,
            warnings=prepared.warnings,
        )

    def verify_prepared(self, command_id: str, staging_location: str) -> None:
        prepared = self._require_prepared(command_id, staging_location)
        verification = self._repository.verify_import(prepared)
        if not verification.valid:
            raise ImportConflictError(verification)

    def release_for_review(self, command_id: str) -> None:
        self._require_prepared(command_id, self.staging_location(command_id))
        process_lock = self._locks.pop(command_id)
        process_lock.release()

    def reacquire_for_commit(self, command_id: str) -> None:
        if command_id in self._locks:
            return
        if command_id not in self._prepared:
            raise RuntimeError("导入命令尚未 prepare")
        process_lock = ImportProcessLock(self._repository.state_dir, command_id)
        process_lock.acquire()
        self._locks[command_id] = process_lock
        try:
            verification = self._repository.verify_import(self._prepared[command_id])
            if not verification.valid:
                raise ImportConflictError(verification)
        except Exception:
            self._locks.pop(command_id, None)
            process_lock.release()
            raise

    def commit_prepared(self, command_id: str) -> BackendCommittedResult:
        prepared = self._require_prepared(command_id, self.staging_location(command_id))
        workspace = ImportTransactionWorkspace(
            self._repository.state_dir,
            command_id,
            allowed_target_roots=(self._repository.state_dir, self._repository.config_dir),
            failure_injector=self._workspace_failure_injector,
        )
        self._workspaces[command_id] = workspace
        commit_prepared_import(self._repository, prepared, workspace)
        self._repository._summary_cache = None
        result = BackendCommittedResult(
            command_id=command_id,
            source=prepared.source,
            filename=Path(prepared.source_file).name,
            imported_count=prepared.imported_count,
            merged_count=prepared.merged_count,
            duplicate_count=prepared.duplicate_count,
            invalid_count=len(prepared.warnings),
            unresolved_industry_count=prepared.unresolved_industry_count,
            generated_sector_count=prepared.generated_sector_count,
            warnings=prepared.warnings,
            active_watchlist=str(self._repository.active_watchlist_path),
            committed_at=datetime.now(UTC).isoformat(),
        )
        self._finish(command_id)
        return result

    def rollback_prepared(self, command_id: str) -> None:
        workspace = self._workspaces.get(command_id)
        if workspace is not None and workspace.root.exists():
            if workspace.backup_complete:
                workspace.rollback()
            workspace.cleanup()
        self._finish(command_id)

    def discard_prepared(self, command_id: str) -> None:
        workspace = self._workspaces.get(command_id)
        if workspace is not None and workspace.root.exists():
            if workspace.status == "RECOVERY_REQUIRED":
                raise RuntimeError("事务需要恢复，拒绝丢弃 backup")
            workspace.cleanup()
        self._finish(command_id)

    def _require_lock(self, command_id: str) -> None:
        process_lock = self._locks.get(command_id)
        if process_lock is None or not process_lock.acquired:
            raise RuntimeError("导入命令未持有跨进程锁")

    def _require_prepared(self, command_id: str, staging_location: str) -> PreparedImport:
        self._require_lock(command_id)
        if staging_location != self.staging_location(command_id):
            raise ValueError("staging location 与 command 不匹配")
        try:
            return self._prepared[command_id]
        except KeyError:
            raise RuntimeError("导入命令尚未 prepare") from None

    def _finish(self, command_id: str) -> None:
        self._prepared.pop(command_id, None)
        self._workspaces.pop(command_id, None)
        process_lock = self._locks.pop(command_id, None)
        if process_lock is not None:
            process_lock.release()


def build_account_watchlist_gateway(
    project_dir: str | Path | None = None,
    *,
    state_dir: str | Path | None = None,
    config_dir: str | Path | None = None,
    workspace_failure_injector: Callable[[str, int], None] | None = None,
) -> AccountWatchlistTransactionGateway:
    kwargs: dict[str, Any] = {}
    if project_dir is not None:
        kwargs["project_dir"] = project_dir
    if state_dir is not None:
        kwargs["state_dir"] = state_dir
    if config_dir is not None:
        kwargs["config_dir"] = config_dir
    return AccountWatchlistTransactionGateway(
        AccountWatchlistRepository(**kwargs),
        workspace_failure_injector=workspace_failure_injector,
    )
