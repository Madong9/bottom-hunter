from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

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
CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    sector_id TEXT NOT NULL,
    horizon INTEGER NOT NULL,
    forward_return REAL,
    max_drawdown REAL,
    evaluated_at TEXT NOT NULL,
    PRIMARY KEY(signal_date, symbol, sector_id, horizon)
);
CREATE TABLE IF NOT EXISTS paper_fills (
    fill_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    sector_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    weight REAL NOT NULL,
    price REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(fill_date, symbol, sector_id, stage)
);
CREATE TABLE IF NOT EXISTS paper_valuations (
    value_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    sector_id TEXT NOT NULL,
    weight REAL NOT NULL,
    entry_price REAL NOT NULL,
    last_price REAL NOT NULL,
    unrealized_return REAL NOT NULL,
    PRIMARY KEY(value_date, symbol, sector_id)
);
"""


OUTCOME_HORIZONS = (3, 5, 10, 20)


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(signals)").fetchall()
        }
        if "breakout" not in columns:
            connection.execute(
                "ALTER TABLE signals ADD COLUMN breakout INTEGER NOT NULL DEFAULT 0"
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=20)
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
                    datetime.now(UTC).isoformat(),
                    json.dumps({"fatal": "上次进程异常退出或被中断"}, ensure_ascii=False),
                ),
            )
            cursor = connection.execute(
                "INSERT INTO scan_runs(report_date, started_at, status) VALUES (?, ?, ?)",
                (report_date.isoformat(), datetime.now(UTC).isoformat(), "running"),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, status: str, errors: dict[str, str]) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE scan_runs SET completed_at=?, status=?, errors_json=? WHERE id=?",
                (
                    datetime.now(UTC).isoformat(),
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

    def previous_signals_map(
        self, signals: list[StockSignal]
    ) -> dict[tuple[str, str], Any]:
        """批量查询上一条信号，单连接完成，避免每个信号各开一次连接。"""
        keys = {(signal.symbol, signal.sector_id): signal.date for signal in signals}
        result: dict[tuple[str, str], Any] = {}
        with self.connect() as connection:
            for (symbol, sector_id), before in keys.items():
                result[(symbol, sector_id)] = connection.execute(
                    """
                    SELECT * FROM signals
                    WHERE symbol=? AND sector_id=? AND signal_date < ?
                    ORDER BY signal_date DESC LIMIT 1
                    """,
                    (symbol, sector_id, before.isoformat()),
                ).fetchone()
        return result

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

    def previous_sectors_map(
        self, sectors: list[SectorResult]
    ) -> dict[tuple[str, str], Any]:
        """批量查询板块上一条评分，单连接完成。"""
        keys = {(sector.sector_id, sector.market): sector.date for sector in sectors}
        result: dict[tuple[str, str], Any] = {}
        with self.connect() as connection:
            for (sector_id, market), before in keys.items():
                result[(sector_id, market)] = connection.execute(
                    """
                    SELECT * FROM sector_scores
                    WHERE sector_id=? AND market=? AND score_date < ?
                    ORDER BY score_date DESC LIMIT 1
                    """,
                    (sector_id, market, before.isoformat()),
                ).fetchone()
        return result

    def save_signals(self, signals: list[StockSignal]) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO signals(
                    signal_date, symbol, market, sector_id, score, available_max,
                    signal_level, state, entry_stage, relative_strength_turn,
                    capitulation_low, data_quality, payload_json, created_at, breakout
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_date, symbol, sector_id) DO UPDATE SET
                    score=excluded.score, available_max=excluded.available_max,
                    signal_level=excluded.signal_level, state=excluded.state,
                    entry_stage=excluded.entry_stage,
                    relative_strength_turn=excluded.relative_strength_turn,
                    capitulation_low=excluded.capitulation_low,
                    data_quality=excluded.data_quality, payload_json=excluded.payload_json,
                    created_at=excluded.created_at, breakout=excluded.breakout
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
                        int(signal.breakout),
                    )
                    for signal in signals
                ],
            )

    def save_sectors(self, sectors: list[SectorResult]) -> None:
        now = datetime.now(UTC).isoformat()
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
                        datetime.now(UTC).isoformat(),
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

    # ---------- signal outcomes ----------

    def pending_signals(self, through: date, max_age_days: int = 30) -> list[dict[str, Any]]:
        cutoff = (through - timedelta(days=max_age_days)).isoformat()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT signal_date, symbol, sector_id FROM signals
                WHERE signal_level NOT IN ('IGNORE', 'FAILED')
                  AND signal_date >= ?
                  AND signal_date <= ?
                ORDER BY signal_date
                """,
                (cutoff, through.isoformat()),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_outcomes(
        self, outcomes: list[tuple[str, str, str, int, float | None, float | None]]
    ) -> int:
        """Rows of (signal_date, symbol, sector_id, horizon, return, drawdown)."""
        if not outcomes:
            return 0
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            before = connection.execute(
                "SELECT COUNT(*) AS n FROM signal_outcomes"
            ).fetchone()["n"]
            connection.executemany(
                """
                INSERT INTO signal_outcomes(
                    signal_date, symbol, sector_id, horizon,
                    forward_return, max_drawdown, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_date, symbol, sector_id, horizon) DO UPDATE SET
                    forward_return=excluded.forward_return,
                    max_drawdown=excluded.max_drawdown,
                    evaluated_at=excluded.evaluated_at
                """,
                [
                    (
                        signal_date,
                        symbol,
                        sector_id,
                        horizon,
                        forward_return,
                        max_drawdown,
                        now,
                    )
                    for signal_date, symbol, sector_id, horizon, forward_return, max_drawdown in outcomes
                ],
            )
            after = connection.execute(
                "SELECT COUNT(*) AS n FROM signal_outcomes"
            ).fetchone()["n"]
        return int(after - before)

    def outcome_summary(self, window_days: int = 30, horizon: int = 5) -> dict[str, Any]:
        since = (date.today() - timedelta(days=window_days)).isoformat()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT o.forward_return, o.max_drawdown, s.market
                FROM signal_outcomes o
                JOIN signals s
                  ON s.signal_date = o.signal_date AND s.symbol = o.symbol
                 AND s.sector_id = o.sector_id
                WHERE o.signal_date >= ? AND o.horizon = ?
                  AND o.forward_return IS NOT NULL
                """,
                (since, horizon),
            ).fetchall()
        if not rows:
            return {"sample_size": 0, "window_days": window_days, "horizon": horizon}
        returns = [float(row["forward_return"]) for row in rows]
        drawdowns = [float(row["max_drawdown"]) for row in rows if row["max_drawdown"] is not None]
        wins = [value for value in returns if value > 0]
        losses = [value for value in returns if value <= 0]
        return {
            "sample_size": len(returns),
            "window_days": window_days,
            "horizon": horizon,
            "win_rate": len(wins) / len(returns),
            "average_return": float(np.mean(returns)),
            "median_return": float(np.median(returns)),
            "average_drawdown": float(np.mean(drawdowns)) if drawdowns else None,
            "profit_loss_ratio": (
                float(np.mean(wins) / abs(np.mean(losses)))
                if wins and losses and np.mean(losses) != 0
                else None
            ),
        }

    # ---------- paper portfolio ----------

    def paper_fills(self, fill_date: date, fills: list[dict[str, Any]]) -> int:
        if not fills:
            return 0
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            cursor = connection.executemany(
                """
                INSERT OR IGNORE INTO paper_fills(
                    fill_date, symbol, sector_id, stage, weight, price, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        fill_date.isoformat(),
                        fill["symbol"],
                        fill["sector_id"],
                        fill["stage"],
                        float(fill["weight"]),
                        float(fill["price"]),
                        now,
                    )
                    for fill in fills
                ],
            )
            return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

    def paper_positions(self, through: date) -> list[dict[str, Any]]:
        """Latest accumulated weight and entry VWAP per (symbol, sector)."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT symbol, sector_id,
                       SUM(weight) AS weight,
                       SUM(weight * price) / NULLIF(SUM(weight), 0) AS entry_price,
                       MAX(fill_date) AS last_fill
                FROM paper_fills
                WHERE fill_date <= ?
                GROUP BY symbol, sector_id
                HAVING SUM(weight) > 0
                ORDER BY last_fill DESC
                """,
                (through.isoformat(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_valuations(
        self, value_date: date, valuations: list[dict[str, Any]]
    ) -> None:
        if not valuations:
            return
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO paper_valuations(
                    value_date, symbol, sector_id, weight,
                    entry_price, last_price, unrealized_return
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(value_date, symbol, sector_id) DO UPDATE SET
                    weight=excluded.weight, entry_price=excluded.entry_price,
                    last_price=excluded.last_price,
                    unrealized_return=excluded.unrealized_return
                """,
                [
                    (
                        value_date.isoformat(),
                        item["symbol"],
                        item["sector_id"],
                        float(item["weight"]),
                        float(item["entry_price"]),
                        float(item["last_price"]),
                        float(item["unrealized_return"]),
                    )
                    for item in valuations
                ],
            )

    def paper_history_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT value_date,
                       SUM(weight * last_price / entry_price) AS equity_index
                FROM paper_valuations
                GROUP BY value_date
                ORDER BY value_date
                """
            ).fetchall()
        series = [
            {"date": row["value_date"], "equity_index": float(row["equity_index"])}
            for row in rows
        ]
        return {"points": series, "latest": series[-1]["equity_index"] if series else None}
