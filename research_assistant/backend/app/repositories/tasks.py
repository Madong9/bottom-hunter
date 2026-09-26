import sqlite3
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import UUID

from app.schemas.research import ResearchTask


class TaskRepository(Protocol):
    def save(self, task: ResearchTask) -> None: ...

    def get(self, task_id: UUID) -> ResearchTask | None: ...

    def list(self, limit: int) -> tuple[list[ResearchTask], int]: ...


class InMemoryTaskRepository(TaskRepository):
    def __init__(self) -> None:
        self._tasks: dict[UUID, ResearchTask] = {}
        self._lock = RLock()

    def save(self, task: ResearchTask) -> None:
        with self._lock:
            self._tasks[task.task_id] = task

    def get(self, task_id: UUID) -> ResearchTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self, limit: int) -> tuple[list[ResearchTask], int]:
        with self._lock:
            tasks = sorted(
                self._tasks.values(), key=lambda item: item.created_at, reverse=True
            )
        return tasks[:limit], len(tasks)


class SQLiteTaskRepository(TaskRepository):
    """Small local repository; each task stores one validated JSON snapshot."""

    def __init__(self, database_path: str) -> None:
        self._path = Path(database_path).expanduser().resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS research_tasks (
                    task_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def save(self, task: ResearchTask) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_tasks(task_id, created_at, payload_json)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    created_at = excluded.created_at,
                    payload_json = excluded.payload_json
                """,
                (str(task.task_id), task.created_at.isoformat(), task.model_dump_json()),
            )

    def get(self, task_id: UUID) -> ResearchTask | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM research_tasks WHERE task_id = ?",
                (str(task_id),),
            ).fetchone()
        return ResearchTask.model_validate_json(row[0]) if row else None

    def list(self, limit: int) -> tuple[list[ResearchTask], int]:
        with self._lock, self._connect() as connection:
            total = int(
                connection.execute("SELECT COUNT(*) FROM research_tasks").fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT payload_json FROM research_tasks
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [ResearchTask.model_validate_json(row[0]) for row in rows], total
