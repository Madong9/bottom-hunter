"""PHASE 4-D3-B — Production mutation boundary, still dry-run only.

The current backend command persists before returning and exposes internal
types, so it is not safe to connect in this phase.  RealMutationPort therefore
depends on a preparation-only gateway stub.  A future integration may supply
that gateway without changing Controller, ViewModel, or QML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .import_contracts import FileFingerprintDTO, ImportCommandDTO
from .import_controller import StagedImportDTO, TransactionWorkspace

BACKEND_INTEGRATION_ISSUES = (
    "当前 backend 命令在返回前已写入来源快照。",
    "当前 backend 结果含内部路径类型，不能暴露给 UI。",
    "当前 backend 没有 prepare/verify/commit 三段式接口。",
    "行业补全失败只能从待分类数量判断，没有结构化错误。",
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


class RealMutationPort:
    """Concrete command adapter over injected, preparation-only interfaces."""

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
