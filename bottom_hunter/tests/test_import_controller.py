"""PHASE 4-D3-A — ImportController skeleton tests with in-memory fakes."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from bottom_hunter.ui_demo.pages.import_contracts import (
    FileFingerprintDTO,
    ImportCommandDTO,
)
from bottom_hunter.ui_demo.pages.import_controller import (
    ImportCommandGate,
    ImportController,
    StagedImportDTO,
)

PAGES_DIR = Path(__file__).resolve().parent.parent / "ui_demo" / "pages"
FINGERPRINT = FileFingerprintDTO(size=42, mtime_ns=99, sha256="preview-sha")


class FakeMutationPort:
    def __init__(self, staged: StagedImportDTO | None = None) -> None:
        self.fingerprint = FINGERPRINT
        self.staged = staged or StagedImportDTO(imported_count=2, merged_count=2)
        self.fingerprint_calls = 0
        self.stage_calls = 0
        self.verify_calls = 0
        self.stage_error = False
        self.verify_error = False
        self.on_stage: Callable[[], None] | None = None

    def current_fingerprint(self, _file_path: str) -> FileFingerprintDTO:
        self.fingerprint_calls += 1
        return self.fingerprint

    def stage(self, _command: ImportCommandDTO, workspace) -> StagedImportDTO:
        self.stage_calls += 1
        if self.on_stage is not None:
            self.on_stage()
        if self.stage_error:
            raise RuntimeError("fake staging failure")
        workspace.stage(self.staged)
        return self.staged

    def verify(self, staged: StagedImportDTO, workspace) -> None:
        self.verify_calls += 1
        if self.verify_error:
            raise RuntimeError("fake verification failure")
        workspace.verify(staged)


class FakeTransactionWorkspace:
    def __init__(self) -> None:
        self.prepared = False
        self.committed = False
        self.rolled_back = False
        self.discarded = False
        self.staged = False
        self.verified = False
        self.commit_error = False
        self.rollback_error = False

    def prepare(self, _command: ImportCommandDTO) -> None:
        self.prepared = True

    def stage(self, _staged: StagedImportDTO) -> None:
        self.staged = True

    def verify(self, _staged: StagedImportDTO) -> None:
        self.verified = True

    def commit(self, _staged: StagedImportDTO) -> None:
        if self.commit_error:
            raise RuntimeError("fake commit failure")
        self.committed = True

    def rollback(self) -> None:
        if self.rollback_error:
            raise RuntimeError("fake rollback failure")
        self.rolled_back = True

    def discard(self) -> None:
        self.discarded = True


class FakeRuntimeActivityPort:
    def __init__(self, active: str = "") -> None:
        self.active = active

    def active_operation(self) -> str:
        return self.active


def _command(
    command_id: str = "cmd-1",
    *,
    preview_id: str = "preview-1",
    fingerprint: FileFingerprintDTO = FINGERPRINT,
    allow_partial: bool = False,
) -> ImportCommandDTO:
    return ImportCommandDTO(
        command_id=command_id,
        preview_id=preview_id,
        source="tonghuashun",
        file_path="/virtual/watchlist.csv",
        file_fingerprint=fingerprint,
        account_alias="main",
        allow_partial=allow_partial,
        requested_at="2026-09-02T00:00:00+00:00",
    )


def _controller(
    mutation: FakeMutationPort | None = None,
    workspace: FakeTransactionWorkspace | None = None,
    runtime: FakeRuntimeActivityPort | None = None,
    gate: ImportCommandGate | None = None,
) -> tuple[ImportController, FakeMutationPort, FakeTransactionWorkspace, ImportCommandGate]:
    mutation = mutation or FakeMutationPort()
    workspace = workspace or FakeTransactionWorkspace()
    gate = gate or ImportCommandGate()
    controller = ImportController(
        mutation,
        lambda: workspace,
        runtime or FakeRuntimeActivityPort(),
        gate,
    )
    return controller, mutation, workspace, gate


def test_command_and_result_contracts_are_frozen() -> None:
    command = _command()
    with pytest.raises(FrozenInstanceError):
        command.source = "okx"  # type: ignore[misc]


def test_command_validation_stops_before_ports() -> None:
    controller, mutation, workspace, gate = _controller()
    result = controller.submit(_command(preview_id=""))

    assert result.status == "FAILED"
    assert result.error is not None
    assert result.error.code == "INVALID_COMMAND"
    assert mutation.fingerprint_calls == 0
    assert mutation.stage_calls == 0
    assert workspace.prepared is False
    assert gate.owner == ""


def test_fingerprint_mismatch_stops_before_staging() -> None:
    mutation = FakeMutationPort()
    mutation.fingerprint = FileFingerprintDTO(size=43, mtime_ns=99, sha256="changed")
    controller, mutation, workspace, gate = _controller(mutation=mutation)

    result = controller.submit(_command())

    assert result.status == "FAILED"
    assert result.error is not None
    assert result.error.code == "FILE_CHANGED"
    assert mutation.stage_calls == 0
    assert workspace.prepared is False
    assert gate.owner == ""


def test_runtime_busy_rejects_command() -> None:
    controller, mutation, workspace, _gate = _controller(runtime=FakeRuntimeActivityPort("扫描"))
    result = controller.submit(_command())

    assert result.status == "FAILED"
    assert result.error is not None
    assert result.error.code == "RUNTIME_BUSY"
    assert result.error.retryable is True
    assert mutation.fingerprint_calls == 0
    assert workspace.prepared is False


def test_busy_gate_rejects_second_controller() -> None:
    gate = ImportCommandGate()
    first_staged = StagedImportDTO(imported_count=2, unresolved_industry_count=1)
    first, _mutation, first_workspace, _gate = _controller(
        mutation=FakeMutationPort(first_staged),
        gate=gate,
    )
    pending = first.submit(_command("cmd-1"))
    assert pending.status == "PARTIAL_REVIEW"
    assert gate.owner == "cmd-1"

    second, second_mutation, _workspace, _gate = _controller(gate=gate)
    rejected = second.submit(_command("cmd-2"))
    assert rejected.status == "FAILED"
    assert rejected.error is not None
    assert rejected.error.code == "IMPORT_BUSY"
    assert second_mutation.fingerprint_calls == 0

    assert first.cancel("cmd-1") is True
    assert first_workspace.discarded is True
    assert gate.owner == ""


def test_cancel_during_staging_discards_fake_workspace() -> None:
    mutation = FakeMutationPort()
    controller, mutation, workspace, gate = _controller(mutation=mutation)
    mutation.on_stage = lambda: controller.cancel("cmd-1")

    result = controller.submit(_command())

    assert result.status == "CANCELLED"
    assert controller.property("state") == "CANCELLED"
    assert workspace.discarded is True
    assert workspace.committed is False
    assert gate.owner == ""


def test_staging_failure_never_commits() -> None:
    mutation = FakeMutationPort()
    mutation.stage_error = True
    controller, _mutation, workspace, gate = _controller(mutation=mutation)

    result = controller.submit(_command())

    assert result.status == "FAILED"
    assert result.error is not None
    assert result.error.code == "STAGING_FAILED"
    assert workspace.discarded is True
    assert workspace.committed is False
    assert workspace.rolled_back is False
    assert gate.owner == ""


def test_commit_failure_rolls_back() -> None:
    workspace = FakeTransactionWorkspace()
    workspace.commit_error = True
    controller, _mutation, workspace, gate = _controller(workspace=workspace)

    result = controller.submit(_command(allow_partial=True))

    assert result.status == "FAILED"
    assert result.error is not None
    assert result.error.code == "COMMIT_FAILED"
    assert result.rollback_performed is True
    assert workspace.rolled_back is True
    assert gate.owner == ""


def test_rollback_failure_requires_recovery() -> None:
    workspace = FakeTransactionWorkspace()
    workspace.commit_error = True
    workspace.rollback_error = True
    controller, _mutation, workspace, gate = _controller(workspace=workspace)

    result = controller.submit(_command(allow_partial=True))

    assert result.status == "RECOVERY_REQUIRED"
    assert result.error is not None
    assert result.error.code == "ROLLBACK_FAILED"
    assert result.rollback_performed is False
    assert controller.property("state") == "RECOVERY_REQUIRED"
    assert gate.owner == ""


def test_partial_review_can_be_accepted() -> None:
    staged = StagedImportDTO(
        imported_count=5,
        merged_count=4,
        unresolved_industry_count=1,
        warnings=("行业待确认",),
    )
    controller, _mutation, workspace, gate = _controller(mutation=FakeMutationPort(staged))
    states: list[str] = []
    controller.stateChanged.connect(states.append)

    pending = controller.submit(_command())
    assert pending.status == "PARTIAL_REVIEW"
    assert pending.finished_at == ""
    assert controller.property("state") == "PARTIAL_REVIEW"
    assert workspace.committed is False
    assert gate.owner == "cmd-1"

    result = controller.accept_partial("cmd-1")
    assert result is not None
    assert result.status == "SUCCESS"
    assert result.committed is True
    assert workspace.committed is True
    assert gate.owner == ""
    assert states == ["QUEUED", "VALIDATING", "STAGING", "VERIFYING", "PARTIAL_REVIEW", "COMMITTING", "SUCCESS"]


def test_success_result_dto_maps_staged_counts() -> None:
    staged = StagedImportDTO(
        imported_count=7,
        merged_count=6,
        duplicate_count=1,
        invalid_count=2,
        unresolved_industry_count=1,
        generated_sector_count=3,
        warnings=("warning-1",),
    )
    controller, mutation, workspace, gate = _controller(mutation=FakeMutationPort(staged))
    emitted: list[object] = []
    controller.resultReady.connect(emitted.append)

    result = controller.submit(_command(allow_partial=True))

    assert result.status == "SUCCESS"
    assert result.filename == "watchlist.csv"
    assert result.imported_count == 7
    assert result.merged_count == 6
    assert result.duplicate_count == 1
    assert result.invalid_count == 2
    assert result.unresolved_industry_count == 1
    assert result.generated_sector_count == 3
    assert result.warnings == ("warning-1",)
    assert result.error is None
    assert result.committed is True
    assert result.started_at
    assert result.finished_at
    assert emitted == [result]
    assert mutation.stage_calls == 1
    assert mutation.verify_calls == 1
    assert workspace.prepared is True
    assert workspace.committed is True
    assert gate.owner == ""


def test_controller_has_no_real_backend_or_io_path() -> None:
    text = (PAGES_DIR / "import_controller.py").read_text(encoding="utf-8")
    forbidden = re.compile(
        r"bottom_hunter\.src|AccountWatchlistRepository|sqlite3|StateStore|"
        r"\b(import_file|add_manual_asset|clear_source|refresh_linked_files|"
        r"write_text|write_bytes|unlink|open)\s*\(",
        re.I,
    )
    assert not forbidden.search(text)
