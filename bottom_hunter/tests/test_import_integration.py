"""PHASE 4-D4-C production adapter, legacy compatibility and lock tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from bottom_hunter.src import account_watchlist as watchlist_module
from bottom_hunter.src.account_watchlist import AccountWatchlistRepository
from bottom_hunter.src.import_lock import ImportLockBusy, ImportProcessLock
from bottom_hunter.ui_demo.pages.import_backend_adapter import (
    ImportResultCompatibilityAdapter,
    build_production_import_stack,
)
from bottom_hunter.ui_demo.pages.import_contracts import ImportCommandDTO
from bottom_hunter.ui_demo.pages.import_controller import ImportCommandGate, ImportController
from bottom_hunter.ui_demo.pages.import_runtime_adapter import RealRuntimeActivityPort, RuntimeStatusDTO


class IdleRuntimeProvider:
    def snapshot(self) -> RuntimeStatusDTO:
        return RuntimeStatusDTO()


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _command(port, selected: Path, *, command_id: str = "cmd-production") -> ImportCommandDTO:
    return ImportCommandDTO(
        command_id=command_id,
        preview_id=f"preview-{command_id}",
        source="tonghuashun",
        file_path=str(selected),
        file_fingerprint=port.current_fingerprint(str(selected)),
        account_alias="main",
        allow_partial=True,
        requested_at="2026-09-02T08:00:00+00:00",
    )


def _production_stack(tmp_path: Path, *, injector=None):
    project = tmp_path / "project"
    return build_production_import_stack(
        str(project),
        state_dir=str(project / "state"),
        config_dir=str(project / "config"),
        workspace_failure_injector=injector,
    )


def _target_files(project: Path) -> dict[str, bytes]:
    targets = [
        project / "state" / "industry_cache.json",
        project / "state" / "watchlists" / "tonghuashun.json",
        project / "state" / "watchlist_summary.json",
        project / "config" / "watchlist.yaml",
    ]
    return {str(path): path.read_bytes() for path in targets if path.is_file()}


def test_legacy_import_file_uses_transaction_chain_and_keeps_result_fields(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    repository = AccountWatchlistRepository(project)
    selected = _write(
        tmp_path / "watchlist.csv",
        "symbol,name,industry\n600519,贵州茅台,食品饮料\nAAPL,Apple,Technology Hardware\n",
    )
    calls = {"prepare": 0, "verify": 0, "commit": 0}
    original_prepare = repository.prepare_import
    original_verify = repository.verify_import
    original_commit = watchlist_module.commit_prepared_import

    def prepare_spy(*args, **kwargs):
        calls["prepare"] += 1
        return original_prepare(*args, **kwargs)

    def verify_spy(*args, **kwargs):
        calls["verify"] += 1
        return original_verify(*args, **kwargs)

    def commit_spy(*args, **kwargs):
        calls["commit"] += 1
        return original_commit(*args, **kwargs)

    monkeypatch.setattr(repository, "prepare_import", prepare_spy)
    monkeypatch.setattr(repository, "verify_import", verify_spy)
    monkeypatch.setattr(watchlist_module, "commit_prepared_import", commit_spy)

    result = repository.import_file("tonghuashun", selected, "main", resolve_industries=True)

    assert calls["prepare"] == 1
    assert calls["verify"] >= 3
    assert calls["commit"] == 1
    assert result.imported_count == 2
    assert result.merged_count == 2
    assert result.duplicate_count == 0
    assert result.unresolved_industry_count == 0
    assert result.generated_sector_count == 2
    assert result.active_watchlist == repository.active_watchlist_path
    assert not (repository.state_dir / ".import.lock").exists()


def test_controller_runs_production_real_mutation_port(tmp_path) -> None:
    port, raw_workspace_factory = _production_stack(tmp_path)
    selected = _write(
        tmp_path / "watchlist.csv",
        "symbol,name,industry\n600519,贵州茅台,食品饮料\n",
    )
    workspaces = []

    def workspace_factory():
        workspace = raw_workspace_factory()
        workspaces.append(workspace)
        return workspace

    controller = ImportController(
        port,
        workspace_factory,
        RealRuntimeActivityPort(IdleRuntimeProvider()),
        ImportCommandGate(),
    )
    command = _command(port, selected)

    result = controller.submit(command)

    assert result.status == "SUCCESS"
    assert result.committed is True
    assert result.imported_count == 1
    assert result.merged_count == 1
    assert workspaces[0].result_dto is not None
    assert result == workspaces[0].result_dto
    assert workspaces[0].result_dto.imported_count == result.imported_count
    assert workspaces[0].result_dto.generated_sector_count == result.generated_sector_count
    project = tmp_path / "project"
    assert (project / "state" / "watchlists" / "tonghuashun.json").is_file()
    assert (project / "config" / "watchlist.yaml").is_file()
    assert not (project / "state" / ".import.lock").exists()


def test_process_lock_rejects_concurrent_owner(tmp_path) -> None:
    first = ImportProcessLock(tmp_path / "state", "txn-first")
    second = ImportProcessLock(tmp_path / "state", "txn-second")
    first.acquire()
    try:
        with pytest.raises(ImportLockBusy) as caught:
            second.acquire()
        assert caught.value.owner["transaction_id"] == "txn-first"
    finally:
        first.release()
    assert not first.path.exists()


def test_process_lock_recovers_dead_stale_owner(tmp_path) -> None:
    state_dir = tmp_path / "state"
    lock_path = _write(
        state_dir / ".import.lock",
        json.dumps(
            {
                "schema_version": 1,
                "pid": 999_999_999,
                "process_start": "dead-process",
                "transaction_id": "crashed-import",
            }
        ),
    )
    recovered = ImportProcessLock(state_dir, "txn-recovered")

    recovered.acquire()
    owner = json.loads(lock_path.read_text(encoding="utf-8"))

    assert recovered.acquired is True
    assert owner["transaction_id"] == "txn-recovered"
    recovered.release()
    assert not lock_path.exists()


def test_controller_commit_failure_rolls_back_and_releases_lock(tmp_path) -> None:
    project = tmp_path / "project"
    repository = AccountWatchlistRepository(project)
    initial = _write(
        tmp_path / "initial.csv",
        "symbol,name,industry\n600519,贵州茅台,食品饮料\n",
    )
    repository.import_file("tonghuashun", initial, resolve_industries=True)
    before = _target_files(project)

    def injector(event: str, index: int) -> None:
        if event == "commit.before_replace" and index == 3:
            raise RuntimeError("injected production commit failure")

    port, workspace_factory = _production_stack(tmp_path, injector=injector)
    selected = _write(
        tmp_path / "replacement.csv",
        "symbol,name,industry\nAAPL,Apple,Technology Hardware\n",
    )
    controller = ImportController(
        port,
        workspace_factory,
        RealRuntimeActivityPort(IdleRuntimeProvider()),
        ImportCommandGate(),
    )

    result = controller.submit(_command(port, selected, command_id="cmd-rollback"))

    assert result.status == "FAILED"
    assert result.error is not None
    assert result.error.code == "COMMIT_FAILED"
    assert result.rollback_performed is True
    assert _target_files(project) == before
    assert not (project / "state" / ".import.lock").exists()


def test_result_compatibility_adapter_maps_all_legacy_counts() -> None:
    command = SimpleNamespace(
        command_id="cmd-result",
        requested_at="2026-09-02T08:00:00+00:00",
    )
    backend_result = SimpleNamespace(
        source="okx",
        filename="okx.csv",
        imported_count=8,
        merged_count=7,
        duplicate_count=2,
        invalid_count=1,
        unresolved_industry_count=3,
        generated_sector_count=4,
        warnings=("warning",),
        committed_at="2026-09-02T08:01:00+00:00",
    )

    result = ImportResultCompatibilityAdapter.from_backend(backend_result, command)

    assert result.command_id == "cmd-result"
    assert result.status == "SUCCESS"
    assert result.committed is True
    assert result.imported_count == 8
    assert result.merged_count == 7
    assert result.duplicate_count == 2
    assert result.invalid_count == 1
    assert result.unresolved_industry_count == 3
    assert result.generated_sector_count == 4
    assert result.warnings == ("warning",)
