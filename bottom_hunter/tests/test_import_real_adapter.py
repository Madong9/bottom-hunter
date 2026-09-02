"""PHASE 4-D3-B adapter tests using only in-memory collaborators."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from bottom_hunter.ui_demo.pages.import_backend_adapter import (
    BackendPreparedImportDTO,
    RealMutationPort,
)
from bottom_hunter.ui_demo.pages.import_contracts import (
    FileFingerprintDTO,
    ImportCommandDTO,
)
from bottom_hunter.ui_demo.pages.import_controller import (
    ImportCommandGate,
    ImportController,
    StagedImportDTO,
)
from bottom_hunter.ui_demo.pages.import_runtime_adapter import (
    RealRuntimeActivityPort,
    RuntimeStatusDTO,
)
from bottom_hunter.ui_demo.pages.import_workspace import (
    DryRunCommitForbidden,
    DryRunTransactionWorkspace,
)

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"
FINGERPRINT = FileFingerprintDTO(size=18, mtime_ns=77, sha256="preview-sha")


class FakeFileSystem:
    """Records lifecycle calls without touching the host filesystem."""

    def __init__(self) -> None:
        self.locations: set[str] = set()
        self.created: list[str] = []
        self.removed: list[str] = []

    def create_temp_dir(self, command_id: str) -> str:
        location = f"memory://import/{command_id}"
        self.locations.add(location)
        self.created.append(location)
        return location

    def remove_tree(self, location: str) -> None:
        self.locations.discard(location)
        self.removed.append(location)


class FakeBackendPreparation:
    def __init__(self, result: BackendPreparedImportDTO | None = None) -> None:
        self.result = result or BackendPreparedImportDTO(
            imported_count=3,
            merged_count=2,
            duplicate_count=1,
        )
        self.prepare_calls: list[tuple[ImportCommandDTO, str]] = []
        self.verify_calls: list[tuple[str, str]] = []

    def prepare_import(
        self,
        command: ImportCommandDTO,
        staging_location: str,
    ) -> BackendPreparedImportDTO:
        self.prepare_calls.append((command, staging_location))
        return self.result

    def verify_prepared(self, command_id: str, staging_location: str) -> None:
        self.verify_calls.append((command_id, staging_location))


class FakeFingerprintReader:
    def read(self, _file_path: str) -> FileFingerprintDTO:
        return FINGERPRINT


@dataclass
class FakeRuntimeStatusProvider:
    status: RuntimeStatusDTO = RuntimeStatusDTO()

    def snapshot(self) -> RuntimeStatusDTO:
        return self.status


def _command(*, allow_partial: bool = False) -> ImportCommandDTO:
    return ImportCommandDTO(
        command_id="cmd-dry-run",
        preview_id="preview-1",
        source="tonghuashun",
        file_path="/virtual/watchlist.csv",
        file_fingerprint=FINGERPRINT,
        allow_partial=allow_partial,
        requested_at="2026-09-02T00:00:00+00:00",
    )


def test_real_mutation_port_maps_backend_output_to_internal_dto() -> None:
    backend = FakeBackendPreparation(
        BackendPreparedImportDTO(
            imported_count=8,
            merged_count=6,
            duplicate_count=2,
            invalid_count=1,
            unresolved_industry_count=3,
            generated_sector_count=4,
            warnings=("industry unresolved",),
        )
    )
    filesystem = FakeFileSystem()
    workspace = DryRunTransactionWorkspace(filesystem)
    workspace.prepare(_command())
    port = RealMutationPort(backend, FakeFingerprintReader())

    staged = port.stage(_command(), workspace)
    port.verify(staged, workspace)

    assert isinstance(staged, StagedImportDTO)
    assert staged.imported_count == 8
    assert staged.merged_count == 6
    assert staged.unresolved_industry_count == 3
    assert staged.warnings == ("industry unresolved",)
    assert workspace.verified is True
    assert backend.prepare_calls == [(_command(), "memory://import/cmd-dry-run")]
    assert backend.verify_calls == [("cmd-dry-run", "memory://import/cmd-dry-run")]


def test_adapter_does_not_expose_backend_object() -> None:
    backend = FakeBackendPreparation()
    port = RealMutationPort(backend, FakeFingerprintReader())

    assert not hasattr(port, "backend")
    assert not hasattr(port, "repository")
    assert all(name.startswith("_") for name in vars(port))


def test_workspace_lifecycle_uses_only_fake_filesystem() -> None:
    filesystem = FakeFileSystem()
    staged = StagedImportDTO(imported_count=2, merged_count=2)

    with DryRunTransactionWorkspace(filesystem) as workspace:
        workspace.prepare(_command())
        location = workspace.staging_location
        workspace.stage(staged)
        workspace.verify(staged)
        assert workspace.command_id == "cmd-dry-run"
        assert workspace.prepared is True
        assert workspace.verified is True
        assert location in filesystem.locations

    assert location not in filesystem.locations
    assert filesystem.removed == [location]
    assert workspace.command_id == ""
    assert workspace.prepared is False


def test_dry_run_workspace_forbids_commit_and_rollback_discards() -> None:
    filesystem = FakeFileSystem()
    workspace = DryRunTransactionWorkspace(filesystem)
    staged = StagedImportDTO(imported_count=1, merged_count=1)
    workspace.prepare(_command())
    location = workspace.staging_location
    workspace.stage(staged)
    workspace.verify(staged)

    with pytest.raises(DryRunCommitForbidden):
        workspace.commit(staged)

    workspace.rollback()
    assert filesystem.removed == [location]
    assert workspace.prepared is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (RuntimeStatusDTO(scanner_running=True), "扫描"),
        (RuntimeStatusDTO(backtest_running=True), "回测"),
        (RuntimeStatusDTO(import_running=True), "导入"),
        (RuntimeStatusDTO(), ""),
    ],
)
def test_runtime_activity_adapter(status: RuntimeStatusDTO, expected: str) -> None:
    adapter = RealRuntimeActivityPort(FakeRuntimeStatusProvider(status))
    assert adapter.active_operation() == expected


def test_controller_accepts_real_port_with_fake_backend() -> None:
    backend = FakeBackendPreparation(
        BackendPreparedImportDTO(
            imported_count=2,
            merged_count=1,
            unresolved_industry_count=1,
        )
    )
    filesystem = FakeFileSystem()
    port = RealMutationPort(backend, FakeFingerprintReader())
    runtime = RealRuntimeActivityPort(FakeRuntimeStatusProvider())
    controller = ImportController(
        port,
        lambda: DryRunTransactionWorkspace(filesystem),
        runtime,
        ImportCommandGate(),
    )

    result = controller.submit(_command())

    assert result.status == "PARTIAL_REVIEW"
    assert result.committed is False
    assert len(backend.prepare_calls) == 1
    assert len(filesystem.locations) == 1
    assert controller.cancel("cmd-dry-run") is True
    assert filesystem.locations == set()


def test_adapter_modules_have_no_real_backend_io_or_database_dependency() -> None:
    files = [
        PAGES_DIR / "import_backend_adapter.py",
        PAGES_DIR / "import_workspace.py",
        PAGES_DIR / "import_runtime_adapter.py",
    ]
    forbidden = re.compile(
        r"from\s+bottom_hunter\.src|AccountWatchlistRepository|sqlite3|"
        r"StateStore|\bPath\b|\b(import_file|add_manual_asset|clear_source|"
        r"refresh_linked_files|rebuild_active_watchlist|write_text|write_bytes|"
        r"unlink|open)\s*\(",
        re.I,
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not forbidden.search(text), f"real side effect dependency in {path.name}"


def test_controller_does_not_depend_on_concrete_repository_or_adapter() -> None:
    text = (PAGES_DIR / "import_controller.py").read_text(encoding="utf-8")
    forbidden = re.compile(
        r"AccountWatchlistRepository|RealMutationPort|import_backend_adapter|"
        r"bottom_hunter\.src|sqlite3",
        re.I,
    )
    assert not forbidden.search(text)
