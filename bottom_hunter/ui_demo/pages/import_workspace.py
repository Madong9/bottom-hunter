"""PHASE 4-D3-B — Dry-run transaction workspace.

The workspace is backed only by an injected filesystem interface.  D3-B does
not provide a production filesystem implementation, so tests and accidental
runtime use cannot touch the host filesystem.  Real commit is deliberately
forbidden.
"""

from __future__ import annotations

from typing import Protocol

from .import_contracts import ImportCommandDTO
from .import_controller import StagedImportDTO


class WorkspaceFileSystem(Protocol):
    """Minimal temporary-directory operations supplied by a future host."""

    def create_temp_dir(self, command_id: str) -> str: ...

    def remove_tree(self, location: str) -> None: ...


class DryRunCommitForbidden(RuntimeError):
    pass


class DryRunTransactionWorkspace:
    """Lifecycle-safe staging workspace that can never commit real state."""

    def __init__(self, filesystem: WorkspaceFileSystem) -> None:
        self._filesystem = filesystem
        self._command_id = ""
        self._staging_location = ""
        self._staged: StagedImportDTO | None = None
        self._prepared = False
        self._verified = False

    @property
    def command_id(self) -> str:
        return self._command_id

    @property
    def staging_location(self) -> str:
        return self._staging_location

    @property
    def prepared(self) -> bool:
        return self._prepared

    @property
    def verified(self) -> bool:
        return self._verified

    def prepare(self, command: ImportCommandDTO) -> None:
        if self._prepared:
            raise RuntimeError("暂存工作区已经准备。")
        if not command.command_id.strip():
            raise ValueError("暂存工作区缺少 command_id。")
        location = self._filesystem.create_temp_dir(command.command_id)
        if not str(location).strip():
            raise RuntimeError("未能创建隔离暂存目录。")
        self._command_id = command.command_id
        self._staging_location = str(location)
        self._prepared = True

    def stage(self, staged: StagedImportDTO) -> None:
        if not self._prepared or not self._staging_location:
            raise RuntimeError("暂存工作区尚未准备。")
        self._staged = staged
        self._verified = False

    def verify(self, staged: StagedImportDTO) -> None:
        if self._staged is None or self._staged != staged:
            raise RuntimeError("暂存结果与当前工作区不匹配。")
        counts = (
            staged.imported_count,
            staged.merged_count,
            staged.duplicate_count,
            staged.invalid_count,
            staged.unresolved_industry_count,
            staged.generated_sector_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("暂存结果包含无效负数计数。")
        self._verified = True

    def commit(self, _staged: StagedImportDTO) -> None:
        raise DryRunCommitForbidden("PHASE 4-D3-B 只允许 dry-run，禁止提交到真实目录。")

    def rollback(self) -> None:
        self.discard()

    def discard(self) -> None:
        location = self._staging_location
        self._command_id = ""
        self._staging_location = ""
        self._staged = None
        self._prepared = False
        self._verified = False
        if location:
            self._filesystem.remove_tree(location)

    def __enter__(self) -> DryRunTransactionWorkspace:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.discard()
