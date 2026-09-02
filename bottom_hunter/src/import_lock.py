"""Cross-process import lock with stale-owner recovery."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import time
from typing import Any


class ImportLockBusy(RuntimeError):
    def __init__(self, lock_path: Path, owner: dict[str, Any]) -> None:
        super().__init__(f"另一个导入事务正在运行：{owner.get('transaction_id') or 'unknown'}")
        self.lock_path = lock_path
        self.owner = dict(owner)


class ImportProcessLock:
    """Atomic-create lock stored at state/.import.lock."""

    def __init__(
        self,
        state_dir: str | Path,
        transaction_id: str,
        *,
        stale_after_seconds: int = 3600,
    ) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.path = self.state_dir / ".import.lock"
        self.transaction_id = transaction_id
        self.stale_after_seconds = max(1, int(stale_after_seconds))
        self._inode: int | None = None
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    def acquire(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        for _attempt in range(3):
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                owner, inode, modified_at = self._read_owner()
                if self._owner_is_stale(owner, modified_at) and self._remove_if_unchanged(inode):
                    continue
                raise ImportLockBusy(self.path, owner) from None
            try:
                payload = {
                    "schema_version": 1,
                    "pid": os.getpid(),
                    "process_start": _process_start_token(os.getpid()),
                    "transaction_id": self.transaction_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
                os.write(descriptor, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
                os.fsync(descriptor)
                self._inode = os.fstat(descriptor).st_ino
            except Exception:
                os.close(descriptor)
                self.path.unlink(missing_ok=True)
                raise
            os.close(descriptor)
            self._acquired = True
            return
        owner, _inode, _modified_at = self._read_owner()
        raise ImportLockBusy(self.path, owner)

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            owner, inode, _modified_at = self._read_owner()
        except FileNotFoundError:
            self._acquired = False
            self._inode = None
            return
        owned = (
            inode == self._inode
            and int(owner.get("pid") or -1) == os.getpid()
            and str(owner.get("transaction_id") or "") == self.transaction_id
        )
        if owned:
            self.path.unlink(missing_ok=True)
        self._acquired = False
        self._inode = None

    def _read_owner(self) -> tuple[dict[str, Any], int, float]:
        stat = self.path.stat()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        return (payload if isinstance(payload, dict) else {}), stat.st_ino, stat.st_mtime

    def _owner_is_stale(self, owner: dict[str, Any], modified_at: float) -> bool:
        try:
            pid = int(owner.get("pid"))
        except (TypeError, ValueError):
            return time() - modified_at > self.stale_after_seconds
        if pid <= 0 or not _process_is_alive(pid):
            return True
        recorded_start = str(owner.get("process_start") or "")
        actual_start = _process_start_token(pid)
        return bool(recorded_start and actual_start and recorded_start != actual_start)

    def _remove_if_unchanged(self, expected_inode: int) -> bool:
        try:
            if self.path.stat().st_ino != expected_inode:
                return False
            self.path.unlink()
        except FileNotFoundError:
            return True
        return True

    def __enter__(self) -> ImportProcessLock:
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.release()


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_start_token(pid: int) -> str:
    try:
        content = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = content.rsplit(")", 1)[1].split()
        return fields[19]
    except (OSError, IndexError):
        return ""
