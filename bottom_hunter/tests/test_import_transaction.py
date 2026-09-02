"""PHASE 4-D4-B backend transaction and failure-injection tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from bottom_hunter.src import account_watchlist as watchlist_module
from bottom_hunter.src.account_watchlist import AccountWatchlistRepository
from bottom_hunter.src.import_transaction_workspace import (
    ImportRecoveryRequired,
    ImportTransactionError,
    ImportTransactionWorkspace,
    commit_prepared_import,
)

FIXED_TIME = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _prepare(tmp_path: Path, monkeypatch, *, with_existing_targets: bool = False):
    project = tmp_path / "project"
    repository = AccountWatchlistRepository(project)
    if with_existing_targets:
        _write(
            repository.source_snapshot_path("tonghuashun"),
            json.dumps(
                {
                    "schema_version": 2,
                    "source": "tonghuashun",
                    "source_label": "同花顺",
                    "items": [],
                },
                ensure_ascii=False,
            ),
        )
        _write(repository.active_watchlist_path, "schema_version: 2\nmode: old\n")
        _write(repository.summary_path, '{"asset_count": 0, "old": true}')
    selected = _write(
        tmp_path / "watchlist.csv",
        "symbol,name,industry\n600519,贵州茅台,食品饮料\nAAPL,Apple,Technology Hardware\n",
    )
    monkeypatch.setattr(watchlist_module, "_utc_now", lambda: FIXED_TIME.isoformat())
    prepared = repository.prepare_import(
        "tonghuashun",
        selected,
        "main",
        resolve_industries=False,
        transaction_id="txn-d4b",
    )
    return repository, selected, prepared


def _workspace(repository, prepared, injector=None) -> ImportTransactionWorkspace:
    return ImportTransactionWorkspace(
        repository.state_dir,
        prepared.transaction_id,
        allowed_target_roots=(repository.state_dir, repository.config_dir),
        failure_injector=injector,
    )


def _target_snapshot(prepared) -> dict[str, bytes | None]:
    return {
        artifact.target: Path(artifact.target).read_bytes() if Path(artifact.target).is_file() else None
        for artifact in prepared.planned_artifacts
    }


def test_verify_reports_source_fingerprint_conflict(tmp_path, monkeypatch) -> None:
    repository, selected, prepared = _prepare(tmp_path, monkeypatch)
    selected.write_text(selected.read_text(encoding="utf-8") + "MSFT,Microsoft,Software\n", encoding="utf-8")

    result = repository.verify_import(prepared, now=FIXED_TIME)

    assert result.valid is False
    assert {conflict.code for conflict in result.conflicts} == {"SOURCE_FILE_CHANGED"}


@pytest.mark.parametrize(
    ("target", "expected_code"),
    [
        ("source", "SOURCE_SNAPSHOT_CHANGED"),
        ("override", "INDUSTRY_OVERRIDE_CHANGED"),
        ("summary", "TARGET_CHANGED"),
    ],
)
def test_verify_reports_repository_baseline_conflicts(
    tmp_path,
    monkeypatch,
    target: str,
    expected_code: str,
) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch)
    paths = {
        "source": repository.source_snapshot_path("tonghuashun"),
        "override": repository.override_path,
        "summary": repository.summary_path,
    }
    _write(paths[target], "changed")

    result = repository.verify_import(prepared, now=FIXED_TIME)

    assert result.valid is False
    assert expected_code in {conflict.code for conflict in result.conflicts}


def test_verify_reports_expired_transaction(tmp_path, monkeypatch) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch)

    result = repository.verify_import(
        prepared,
        max_age_seconds=900,
        now=FIXED_TIME + timedelta(seconds=901),
    )

    assert result.valid is False
    assert {conflict.code for conflict in result.conflicts} == {"TRANSACTION_EXPIRED"}


def test_staging_failure_cleans_workspace_without_touching_targets(tmp_path, monkeypatch) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch)
    before = _target_snapshot(prepared)

    def injector(event: str, index: int) -> None:
        if event == "stage.before_artifact" and index == 1:
            raise RuntimeError("injected staging failure")

    workspace = _workspace(repository, prepared, injector)
    with pytest.raises(ImportTransactionError) as caught:
        commit_prepared_import(repository, prepared, workspace, now=FIXED_TIME)

    assert caught.value.stage == "STAGING"
    assert caught.value.rollback_performed is False
    assert _target_snapshot(prepared) == before
    assert not workspace.root.exists()


def test_staging_verify_failure_cleans_workspace(tmp_path, monkeypatch) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch)

    def injector(event: str, index: int) -> None:
        if event == "verify.before_artifact" and index == 0:
            raise RuntimeError("injected verify failure")

    workspace = _workspace(repository, prepared, injector)
    with pytest.raises(ImportTransactionError) as caught:
        commit_prepared_import(repository, prepared, workspace, now=FIXED_TIME)

    assert caught.value.stage == "VERIFYING"
    assert not workspace.root.exists()
    assert all(not Path(artifact.target).exists() for artifact in prepared.planned_artifacts)


def test_commit_failure_rolls_back_all_replaced_targets(tmp_path, monkeypatch) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch, with_existing_targets=True)
    before = _target_snapshot(prepared)

    def injector(event: str, index: int) -> None:
        if event == "commit.before_replace" and index == 2:
            raise RuntimeError("injected commit failure")

    workspace = _workspace(repository, prepared, injector)
    with pytest.raises(ImportTransactionError) as caught:
        commit_prepared_import(repository, prepared, workspace, now=FIXED_TIME)

    assert caught.value.stage == "COMMITTING"
    assert caught.value.rollback_performed is True
    assert _target_snapshot(prepared) == before
    assert not workspace.root.exists()


def test_rollback_failure_preserves_workspace_for_recovery(tmp_path, monkeypatch) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch, with_existing_targets=True)

    def injector(event: str, index: int) -> None:
        if event == "commit.before_replace" and index == 2:
            raise RuntimeError("injected commit failure")
        if event == "rollback.before_restore" and index == 1:
            raise RuntimeError("injected rollback failure")

    workspace = _workspace(repository, prepared, injector)
    with pytest.raises(ImportRecoveryRequired) as caught:
        commit_prepared_import(repository, prepared, workspace, now=FIXED_TIME)

    assert caught.value.stage == "RECOVERY_REQUIRED"
    assert caught.value.workspace_path == str(workspace.root)
    assert workspace.root.is_dir()
    manifest = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "RECOVERY_REQUIRED"
    workspace.cleanup()


def test_manifest_contains_artifacts_and_backup_metadata(tmp_path, monkeypatch) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch, with_existing_targets=True)
    workspace = _workspace(repository, prepared)

    workspace.create()
    workspace.stage(prepared)
    workspace.verify()
    workspace.backup()
    manifest = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))

    assert manifest["status"] == "BACKED_UP"
    assert len(manifest["artifacts"]) == len(prepared.planned_artifacts)
    assert len(manifest["backups"]) == len(prepared.planned_artifacts)
    assert all(record["sha256"] for record in manifest["backups"])
    workspace.rollback()
    workspace.cleanup()
    assert not workspace.root.exists()


def test_successful_commit_preserves_schemas_and_cleans_workspace(tmp_path, monkeypatch) -> None:
    repository, _selected, prepared = _prepare(tmp_path, monkeypatch)
    workspace = _workspace(repository, prepared)

    receipt = commit_prepared_import(repository, prepared, workspace, now=FIXED_TIME)

    assert receipt.status == "COMMITTED"
    assert receipt.artifact_count == 3
    assert receipt.cleaned_up is True
    assert not workspace.root.exists()
    snapshot = json.loads(repository.source_snapshot_path("tonghuashun").read_text(encoding="utf-8"))
    watchlist = yaml.safe_load(repository.active_watchlist_path.read_text(encoding="utf-8"))
    summary = json.loads(repository.summary_path.read_text(encoding="utf-8"))
    assert snapshot["schema_version"] == 2
    assert watchlist["schema_version"] == 2
    assert summary["asset_count"] == 2
