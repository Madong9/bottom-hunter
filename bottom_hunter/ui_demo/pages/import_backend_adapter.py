"""PHASE 4-D4-C — The sole production import mutation boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from .import_contracts import FileFingerprintDTO, ImportCommandDTO, ImportResultDTO
from .import_controller import StagedImportDTO, TransactionWorkspace

BACKEND_INTEGRATION_ISSUES = (
    "行业补全失败只能从待分类数量判断，没有结构化错误。",
    "多文件提交使用原子替换与补偿回滚，外部读者仍无全局事务视图。",
)


@dataclass(frozen=True)
class BackendPreparedImportDTO:
    """Backend-neutral output of a future preparation-only gateway."""

    imported_count: int = 0
    merged_count: int = 0
    duplicate_count: int = 0
    invalid_count: int = 0
    unresolved_industry_count: int = 0
    generated_sector_count: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)


class BackendPreparationPort(Protocol):
    """Future backend adapter stub. It may prepare only inside staging."""

    def prepare_import(
        self,
        command: ImportCommandDTO,
        staging_location: str,
    ) -> BackendPreparedImportDTO: ...

    def verify_prepared(self, command_id: str, staging_location: str) -> None: ...


class FingerprintReaderPort(Protocol):
    def read(self, file_path: str) -> FileFingerprintDTO: ...


class BackendTransactionPort(BackendPreparationPort, Protocol):
    def begin(self, command_id: str) -> None: ...

    def staging_location(self, command_id: str) -> str: ...

    def commit_prepared(self, command_id: str) -> object: ...

    def rollback_prepared(self, command_id: str) -> None: ...

    def discard_prepared(self, command_id: str) -> None: ...


class ImportResultCompatibilityAdapter:
    """Maps a private backend commit result to the public transport DTO."""

    @staticmethod
    def from_backend(result: object, command: ImportCommandDTO) -> ImportResultDTO:
        return ImportResultDTO(
            command_id=command.command_id,
            source=str(result.source),
            filename=str(result.filename),
            status="SUCCESS",
            committed=True,
            imported_count=int(result.imported_count),
            merged_count=int(result.merged_count),
            duplicate_count=int(result.duplicate_count),
            invalid_count=int(result.invalid_count),
            unresolved_industry_count=int(result.unresolved_industry_count),
            generated_sector_count=int(result.generated_sector_count),
            warnings=tuple(str(item) for item in result.warnings),
            started_at=command.requested_at,
            finished_at=str(result.committed_at),
        )


class ProductionFingerprintReader:
    def __init__(self, gateway: object) -> None:
        self._gateway = gateway

    def read(self, file_path: str) -> FileFingerprintDTO:
        fingerprint = self._gateway.read_fingerprint(str(file_path))
        return FileFingerprintDTO(
            size=int(fingerprint.size),
            mtime_ns=int(fingerprint.mtime_ns),
            sha256=str(fingerprint.sha256),
        )


class ProductionTransactionWorkspace:
    """Controller workspace facade; backend transaction objects remain private."""

    def __init__(self, gateway: BackendTransactionPort) -> None:
        self._gateway = gateway
        self._command: ImportCommandDTO | None = None
        self._staged: StagedImportDTO | None = None
        self._result_dto: ImportResultDTO | None = None
        self._finished = False

    @property
    def command_id(self) -> str:
        return self._command.command_id if self._command is not None else ""

    @property
    def staging_location(self) -> str:
        return self._gateway.staging_location(self.command_id) if self.command_id else ""

    @property
    def result_dto(self) -> ImportResultDTO | None:
        return self._result_dto

    def prepare(self, command: ImportCommandDTO) -> None:
        if self._command is not None:
            raise RuntimeError("导入 workspace 已经 prepare")
        self._command = command
        self._gateway.begin(command.command_id)

    def stage(self, staged: StagedImportDTO) -> None:
        if self._command is None:
            raise RuntimeError("导入 workspace 尚未 prepare")
        self._staged = staged

    def verify(self, staged: StagedImportDTO) -> None:
        if self._staged is None or self._staged != staged:
            raise RuntimeError("导入 workspace 结果不匹配")

    def commit(self, staged: StagedImportDTO) -> None:
        if self._command is None or self._staged != staged:
            raise RuntimeError("导入 workspace 不能 commit")
        result = self._gateway.commit_prepared(self._command.command_id)
        self._result_dto = ImportResultCompatibilityAdapter.from_backend(result, self._command)
        self._finished = True

    def rollback(self) -> None:
        if self._command is not None and not self._finished:
            self._gateway.rollback_prepared(self._command.command_id)
            self._finished = True

    def discard(self) -> None:
        if self._command is not None and not self._finished:
            self._gateway.discard_prepared(self._command.command_id)
            self._finished = True


class RealMutationPort:
    """Concrete adapter mapping backend preparation into transport DTOs."""

    def __init__(
        self,
        backend: BackendPreparationPort,
        fingerprint_reader: FingerprintReaderPort,
    ) -> None:
        self._backend = backend
        self._fingerprint_reader = fingerprint_reader
        self._staging_by_command: dict[str, str] = {}

    def current_fingerprint(self, file_path: str) -> FileFingerprintDTO:
        return self._fingerprint_reader.read(str(file_path))

    def stage(
        self,
        command: ImportCommandDTO,
        workspace: TransactionWorkspace,
    ) -> StagedImportDTO:
        location = str(getattr(workspace, "staging_location", "") or "")
        if not location:
            raise RuntimeError("暂存工作区没有提供 staging_location。")
        prepared = self._backend.prepare_import(command, location)
        staged = StagedImportDTO(
            imported_count=int(prepared.imported_count),
            merged_count=int(prepared.merged_count),
            duplicate_count=int(prepared.duplicate_count),
            invalid_count=int(prepared.invalid_count),
            unresolved_industry_count=int(prepared.unresolved_industry_count),
            generated_sector_count=int(prepared.generated_sector_count),
            warnings=tuple(str(item) for item in prepared.warnings),
        )
        workspace.stage(staged)
        self._staging_by_command[command.command_id] = location
        return staged

    def verify(self, staged: StagedImportDTO, workspace: TransactionWorkspace) -> None:
        command_id = str(getattr(workspace, "command_id", "") or "")
        location = str(getattr(workspace, "staging_location", "") or "")
        if not command_id or self._staging_by_command.get(command_id) != location:
            raise RuntimeError("暂存命令与 MutationPort 记录不匹配。")
        try:
            self._backend.verify_prepared(command_id, location)
            workspace.verify(staged)
        finally:
            self._staging_by_command.pop(command_id, None)


def build_production_import_stack(
    project_dir: str | None = None,
    *,
    state_dir: str | None = None,
    config_dir: str | None = None,
    workspace_failure_injector: Callable[[str, int], None] | None = None,
) -> tuple[RealMutationPort, Callable[[], ProductionTransactionWorkspace]]:
    """Deferred backend wiring; callers receive only adapter-layer objects."""

    from bottom_hunter.src.import_backend_gateway import build_account_watchlist_gateway

    gateway = build_account_watchlist_gateway(
        project_dir,
        state_dir=state_dir,
        config_dir=config_dir,
        workspace_failure_injector=workspace_failure_injector,
    )
    mutation_port = RealMutationPort(gateway, ProductionFingerprintReader(gateway))
    return mutation_port, lambda: ProductionTransactionWorkspace(gateway)
