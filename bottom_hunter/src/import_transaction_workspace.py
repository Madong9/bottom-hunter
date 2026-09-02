"""Backend staging, backup and atomic-replace primitives for prepared imports."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from .import_transaction import ImportVerificationResult, PlannedImportArtifact, PreparedImport

if TYPE_CHECKING:
    from .account_watchlist import AccountWatchlistRepository

FailureInjector = Callable[[str, int], None]


@dataclass(frozen=True)
class ImportCommitReceipt:
    transaction_id: str
    status: str
    artifact_count: int
    cleaned_up: bool


class ImportTransactionError(RuntimeError):
    def __init__(
        self,
        transaction_id: str,
        stage: str,
        message: str,
        *,
        rollback_performed: bool = False,
    ) -> None:
        super().__init__(message)
        self.transaction_id = transaction_id
        self.stage = stage
        self.rollback_performed = rollback_performed


class ImportConflictError(ImportTransactionError):
    def __init__(self, verification: ImportVerificationResult) -> None:
        codes = ", ".join(conflict.code for conflict in verification.conflicts)
        super().__init__(verification.transaction_id, "VERIFYING", f"导入冲突：{codes}")
        self.verification = verification


class ImportRecoveryRequired(ImportTransactionError):
    def __init__(self, transaction_id: str, message: str, workspace_path: str) -> None:
        super().__init__(transaction_id, "RECOVERY_REQUIRED", message)
        self.workspace_path = workspace_path


class ImportTransactionWorkspace:
    """Real filesystem workspace rooted below state/.import_transactions/."""

    def __init__(
        self,
        state_dir: str | Path,
        transaction_id: str,
        *,
        allowed_target_roots: Sequence[str | Path],
        failure_injector: FailureInjector | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", transaction_id):
            raise ValueError("不安全的 import transaction_id")
        self.transaction_id = transaction_id
        self.state_dir = Path(state_dir).resolve()
        self.transactions_dir = self.state_dir / ".import_transactions"
        self.root = self.transactions_dir / transaction_id
        self.artifacts_dir = self.root / "artifacts"
        self.backups_dir = self.root / "backups"
        self.manifest_path = self.root / "manifest.json"
        self.allowed_target_roots = tuple(Path(path).resolve() for path in allowed_target_roots)
        if not self.allowed_target_roots:
            raise ValueError("TransactionWorkspace 缺少允许的目标根目录")
        self._failure_injector = failure_injector
        self._prepared: PreparedImport | None = None
        self._artifact_records: list[dict[str, Any]] = []
        self._backup_records: list[dict[str, Any]] = []
        self._applied_indices: list[int] = []
        self._created = False
        self._verified = False
        self._backed_up = False
        self._status = "INIT"
        self._phase = "IDLE"

    @property
    def status(self) -> str:
        return self._status

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def backup_complete(self) -> bool:
        return self._backed_up

    @property
    def created(self) -> bool:
        return self._created

    def create(self) -> None:
        self._phase = "CREATING"
        self.root.mkdir(parents=True, exist_ok=False)
        self._created = True
        self.artifacts_dir.mkdir()
        self.backups_dir.mkdir()
        self._status = "CREATED"
        self._write_manifest()

    def stage(self, prepared: PreparedImport) -> None:
        self._require_created()
        if prepared.transaction_id != self.transaction_id:
            raise ValueError("PreparedImport 与 workspace transaction_id 不匹配")
        self._phase = "STAGING"
        self._prepared = prepared
        self._artifact_records = []
        for index, artifact in enumerate(prepared.planned_artifacts):
            self._inject("stage.before_artifact", index)
            target = Path(artifact.target).resolve()
            self._validate_target(target)
            suffix = ".json" if artifact.format == "json" else ".yaml"
            staged_path = self.artifacts_dir / f"{index:03d}-{_safe_name(artifact.kind)}{suffix}"
            content = _serialize_artifact(artifact)
            staged_path.write_text(content, encoding="utf-8")
            record = {
                "index": index,
                "kind": artifact.kind,
                "target": str(target),
                "format": artifact.format,
                "staged": str(staged_path.relative_to(self.root)),
                "sha256": _sha256_file(staged_path),
            }
            self._artifact_records.append(record)
            self._inject("stage.after_artifact", index)
        self._status = "STAGED"
        self._write_manifest()

    def verify(self) -> None:
        if self._prepared is None or self._status != "STAGED":
            raise RuntimeError("workspace 尚未完成 staging")
        self._phase = "VERIFYING"
        if len(self._artifact_records) != len(self._prepared.planned_artifacts):
            raise RuntimeError("staging artifact 数量不匹配")
        for index, (record, artifact) in enumerate(
            zip(self._artifact_records, self._prepared.planned_artifacts, strict=True)
        ):
            self._inject("verify.before_artifact", index)
            staged_path = self.root / record["staged"]
            if not staged_path.is_file() or _sha256_file(staged_path) != record["sha256"]:
                raise RuntimeError(f"staging artifact 哈希校验失败：{artifact.kind}")
            decoded = _deserialize_artifact(staged_path, artifact.format)
            if decoded != dict(artifact.payload):
                raise RuntimeError(f"staging artifact 内容校验失败：{artifact.kind}")
            self._inject("verify.after_artifact", index)
        self._verified = True
        self._status = "VERIFIED"
        self._write_manifest()

    def backup(self) -> None:
        if not self._verified or self._status != "VERIFIED":
            raise RuntimeError("workspace 尚未通过 verify")
        self._phase = "BACKING_UP"
        self._backup_records = []
        for index, record in enumerate(self._artifact_records):
            self._inject("backup.before_artifact", index)
            target = Path(record["target"])
            existed = target.is_file()
            backup_path = self.backups_dir / f"{index:03d}-{_safe_name(record['kind'])}.bak"
            if existed:
                shutil.copy2(target, backup_path)
            self._backup_records.append(
                {
                    "index": index,
                    "target": str(target),
                    "existed": existed,
                    "backup": str(backup_path.relative_to(self.root)) if existed else "",
                    "sha256": _sha256_file(backup_path) if existed else "",
                }
            )
            self._inject("backup.after_artifact", index)
        self._backed_up = True
        self._status = "BACKED_UP"
        self._write_manifest()

    def commit(self) -> None:
        if not self._backed_up or self._status != "BACKED_UP":
            raise RuntimeError("workspace 尚未完成 backup")
        self._phase = "COMMITTING"
        self._applied_indices = []
        for index, record in enumerate(self._artifact_records):
            self._inject("commit.before_replace", index)
            staged_path = self.root / record["staged"]
            target = Path(record["target"])
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.parent / f".{target.name}.{self.transaction_id}.{index}.tmp"
            try:
                shutil.copy2(staged_path, temporary)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
            self._applied_indices.append(index)
            self._inject("commit.after_replace", index)
        self._status = "COMMITTED"
        self._write_manifest()

    def rollback(self) -> None:
        if not self._backed_up:
            raise RuntimeError("workspace 没有可用 backup")
        self._phase = "ROLLING_BACK"
        backups = {int(record["index"]): record for record in self._backup_records}
        try:
            for index in reversed(self._applied_indices):
                self._inject("rollback.before_restore", index)
                record = backups[index]
                target = Path(record["target"])
                if record["existed"]:
                    backup_path = self.root / record["backup"]
                    if not backup_path.is_file() or _sha256_file(backup_path) != record["sha256"]:
                        raise RuntimeError(f"backup 不完整：{target}")
                    temporary = target.parent / f".{target.name}.{self.transaction_id}.{index}.rollback.tmp"
                    try:
                        shutil.copy2(backup_path, temporary)
                        os.replace(temporary, target)
                    finally:
                        temporary.unlink(missing_ok=True)
                else:
                    target.unlink(missing_ok=True)
                self._inject("rollback.after_restore", index)
        except Exception:
            self._status = "RECOVERY_REQUIRED"
            self._write_manifest()
            raise
        self._status = "ROLLED_BACK"
        self._write_manifest()

    def cleanup(self) -> None:
        if not self.root.exists():
            return
        resolved_root = self.root.resolve()
        if resolved_root.parent != self.transactions_dir.resolve():
            raise RuntimeError("拒绝清理 transaction 根目录之外的路径")
        shutil.rmtree(resolved_root)
        self._created = False

    def _validate_target(self, target: Path) -> None:
        if not any(root in target.parents for root in self.allowed_target_roots):
            raise ValueError(f"artifact 目标超出允许范围：{target}")

    def _require_created(self) -> None:
        if not self._created or self._status != "CREATED":
            raise RuntimeError("workspace 尚未 create")

    def _inject(self, event: str, index: int) -> None:
        if self._failure_injector is not None:
            self._failure_injector(event, index)

    def _write_manifest(self) -> None:
        if not self._created:
            return
        manifest = {
            "schema_version": 1,
            "transaction_id": self.transaction_id,
            "status": self._status,
            "artifacts": self._artifact_records,
            "backups": self._backup_records,
            "applied_indices": self._applied_indices,
        }
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.manifest_path)


def commit_prepared_import(
    repository: AccountWatchlistRepository,
    prepared: PreparedImport,
    workspace: ImportTransactionWorkspace,
    *,
    max_age_seconds: int = 900,
    now: datetime | None = None,
) -> ImportCommitReceipt:
    """Verify and commit one prepared import without using legacy import_file()."""

    verification = repository.verify_import(prepared, max_age_seconds=max_age_seconds, now=now)
    if not verification.valid:
        raise ImportConflictError(verification)
    if workspace.transaction_id != prepared.transaction_id:
        raise ValueError("workspace 与 PreparedImport transaction_id 不匹配")

    try:
        workspace.create()
        workspace.stage(prepared)
        workspace.verify()
        verification = repository.verify_import(prepared, max_age_seconds=max_age_seconds, now=now)
        if not verification.valid:
            raise ImportConflictError(verification)
        workspace.backup()
        workspace.commit()
    except ImportConflictError:
        if workspace.created:
            workspace.cleanup()
        raise
    except Exception as exc:
        if not workspace.backup_complete:
            if workspace.created:
                workspace.cleanup()
            raise ImportTransactionError(
                prepared.transaction_id,
                workspace.phase,
                f"导入事务在 {workspace.phase} 失败：{exc}",
            ) from exc
        try:
            workspace.rollback()
        except Exception as rollback_exc:
            raise ImportRecoveryRequired(
                prepared.transaction_id,
                f"导入提交失败且无法回滚：{rollback_exc}",
                str(workspace.root),
            ) from rollback_exc
        workspace.cleanup()
        raise ImportTransactionError(
            prepared.transaction_id,
            "COMMITTING",
            f"导入提交失败，已回滚：{exc}",
            rollback_performed=True,
        ) from exc

    try:
        workspace.cleanup()
    except OSError:
        cleaned_up = False
    else:
        cleaned_up = True
    return ImportCommitReceipt(
        transaction_id=prepared.transaction_id,
        status="COMMITTED",
        artifact_count=len(prepared.planned_artifacts),
        cleaned_up=cleaned_up,
    )


def _serialize_artifact(artifact: PlannedImportArtifact) -> str:
    payload = dict(artifact.payload)
    if artifact.format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if artifact.format == "yaml":
        return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    raise ValueError(f"不支持的 artifact 格式：{artifact.format}")


def _deserialize_artifact(path: Path, format_name: str) -> Any:
    content = path.read_text(encoding="utf-8")
    if format_name == "json":
        return json.loads(content)
    if format_name == "yaml":
        return yaml.safe_load(content)
    raise ValueError(f"不支持的 artifact 格式：{format_name}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "artifact"
