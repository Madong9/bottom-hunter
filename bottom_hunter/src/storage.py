from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import Alert, SectorResult, StockSignal


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    errors_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS signals (
    signal_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    sector_id TEXT NOT NULL,
    score INTEGER NOT NULL,
    available_max INTEGER NOT NULL,
    signal_level TEXT NOT NULL,
    state TEXT NOT NULL,
    entry_stage TEXT,
    relative_strength_turn INTEGER NOT NULL,
    capitulation_low REAL,
    data_quality TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(signal_date, symbol, sector_id)
);
CREATE INDEX IF NOT EXISTS idx_signals_symbol_date ON signals(symbol, signal_date);
CREATE TABLE IF NOT EXISTS sector_scores (
    score_date TEXT NOT NULL,
    sector_id TEXT NOT NULL,
    market TEXT NOT NULL,
    score INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(score_date, sector_id, market)
);
CREATE INDEX IF NOT EXISTS idx_sector_date ON sector_scores(sector_id, market, score_date);
CREATE TABLE IF NOT EXISTS alerts (
    alert_date TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    entity TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(alert_date, alert_type, entity, fingerprint)
);
"""


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def start_run(self, report_date: date) -> int:
        with self.connect() as connection:
            # This application is intentionally single-run. A prior row still marked
            # running means the process was killed before its exception handler ran.
            connection.execute(
                """
                UPDATE scan_runs
                SET completed_at=?, status='aborted', errors_json=?
                WHERE status='running'
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps({"fatal": "上次进程异常退出或被中断"}, ensure_ascii=False),
                ),
            )
            cursor = connection.execute(
                "INSERT INTO scan_runs(report_date, started_at, status) VALUES (?, ?, ?)",
                (report_date.isoformat(), datetime.now(timezone.utc).isoformat(), "running"),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, errors: dict[str, str]) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE scan_runs SET completed_at=?, status=?, errors_json=? WHERE id=?",
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    json.dumps(errors, ensure_ascii=False),
                    run_id,
                ),
            )

    def previous_signal(self, symbol: str, sector_id: str, before: date):
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM signals
                WHERE symbol=? AND sector_id=? AND signal_date < ?
                ORDER BY signal_date DESC LIMIT 1
                """,
                (symbol, sector_id, before.isoformat()),
            ).fetchone()

    def previous_sector(self, sector_id: str, market: str, before: date):
        with self.connect() as connection:
            return connection.execute(
                """
                SELECT * FROM sector_scores
                WHERE sector_id=? AND market=? AND score_date < ?
                ORDER BY score_date DESC LIMIT 1
                """,
                (sector_id, market, before.isoformat()),
            ).fetchone()

    def save_signals(self, signals: list[StockSignal]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO signals(
                    signal_date, symbol, market, sector_id, score, available_max,
                    signal_level, state, entry_stage, relative_strength_turn,
                    capitulation_low, data_quality, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_date, symbol, sector_id) DO UPDATE SET
                    score=excluded.score, available_max=excluded.available_max,
                    signal_level=excluded.signal_level, state=excluded.state,
                    entry_stage=excluded.entry_stage,
                    relative_strength_turn=excluded.relative_strength_turn,
                    capitulation_low=excluded.capitulation_low,
                    data_quality=excluded.data_quality, payload_json=excluded.payload_json,
                    created_at=excluded.created_at
                """,
                [
                    (
                        signal.date.isoformat(),
                        signal.symbol,
                        signal.market,
                        signal.sector_id,
                        signal.score.total,
                        signal.score.available_max,
                        signal.signal_level.value,
                        signal.state.value,
                        signal.entry_stage.value if signal.entry_stage else None,
                        int(signal.relative_strength_turn),
                        signal.capitulation_low,
                        signal.data_quality,
                        json.dumps(signal.to_dict(), ensure_ascii=False, allow_nan=False),
                        now,
                    )
                    for signal in signals
                ],
            )

    def save_sectors(self, sectors: list[SectorResult]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO sector_scores(
                    score_date, sector_id, market, score, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(score_date, sector_id, market) DO UPDATE SET
                    score=excluded.score, payload_json=excluded.payload_json,
                    created_at=excluded.created_at
                """,
                [
                    (
                        sector.date.isoformat(),
                        sector.sector_id,
                        sector.market,
                        sector.score,
                        json.dumps(sector.to_dict(), ensure_ascii=False, allow_nan=False),
                        now,
                    )
                    for sector in sectors
                ],
            )

    def save_alerts(self, alerts: list[Alert]) -> list[Alert]:
        inserted: list[Alert] = []
        with self.connect() as connection:
            for alert in alerts:
                fingerprint = hashlib.sha256(alert.message.encode("utf-8")).hexdigest()[:16]
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO alerts(
                        alert_date, alert_type, entity, fingerprint, message, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        alert.date.isoformat(),
                        alert.alert_type,
                        alert.entity,
                        fingerprint,
                        alert.message,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                if cursor.rowcount:
                    inserted.append(alert)
        return inserted

    def stage_history(self, symbol: str, through: date) -> list[tuple[date, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT signal_date, entry_stage FROM signals
                WHERE symbol=? AND signal_date <= ? AND entry_stage IS NOT NULL
                ORDER BY signal_date
                """,
                (symbol, through.isoformat()),
            ).fetchall()
        return [(date.fromisoformat(row["signal_date"]), row["entry_stage"]) for row in rows]
