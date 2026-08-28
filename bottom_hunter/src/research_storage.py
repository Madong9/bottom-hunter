from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from .research_models import (
    FinancialFact,
    MacroObservation,
    ResearchItem,
    ResearchKind,
    ResearchSnapshot,
    SourceTier,
)

RESEARCH_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS financial_facts (
    symbol TEXT NOT NULL,
    market TEXT NOT NULL,
    period_end TEXT NOT NULL,
    filed_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    period_type TEXT NOT NULL DEFAULT '',
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY(symbol, period_end, period_type, metric, source)
);
CREATE INDEX IF NOT EXISTS idx_financial_symbol_period
    ON financial_facts(symbol, period_end DESC);
CREATE TABLE IF NOT EXISTS research_items (
    item_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    tier TEXT NOT NULL,
    symbol TEXT NOT NULL DEFAULT '',
    market TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    published_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    report_date TEXT,
    source TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    sentiment TEXT NOT NULL DEFAULT 'neutral',
    confidence REAL NOT NULL DEFAULT 0.5,
    raw_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_research_dedup
    ON research_items(raw_hash);
CREATE INDEX IF NOT EXISTS idx_research_symbol_time
    ON research_items(symbol, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_kind_time
    ON research_items(kind, published_at DESC);
CREATE TABLE IF NOT EXISTS macro_observations (
    series_id TEXT NOT NULL,
    name TEXT NOT NULL,
    dimension TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    release_at TEXT NOT NULL,
    vintage_at TEXT NOT NULL,
    value REAL NOT NULL,
    previous REAL,
    change_value REAL,
    change_pct REAL,
    consensus REAL,
    signal INTEGER NOT NULL DEFAULT 0,
    unit TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY(series_id, observation_date, vintage_at, source)
);
CREATE INDEX IF NOT EXISTS idx_macro_series_date
    ON macro_observations(series_id, observation_date DESC, vintage_at DESC);
CREATE TABLE IF NOT EXISTS research_refreshes (
    scope TEXT PRIMARY KEY,
    refreshed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    errors_json TEXT NOT NULL DEFAULT '{}'
);
"""


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class ResearchStore:
    """Point-in-time research cache sharing the scanner's SQLite database."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(RESEARCH_SCHEMA)
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS research_items_fts USING fts5(
                        item_id UNINDEXED, title, summary, author, source
                    )
                    """
                )
            except sqlite3.OperationalError:
                # Some distro SQLite builds omit FTS5. Core storage still works.
                pass

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

    @staticmethod
    def _item_identity(item: ResearchItem) -> tuple[str, str]:
        raw = "|".join(
            (
                item.kind.value,
                item.symbol.upper(),
                item.source.casefold(),
                item.url.strip(),
                item.title.strip().casefold(),
                item.published_at.isoformat(),
            )
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return item.item_id or digest[:24], digest

    def save_financial_facts(self, facts: Iterable[FinancialFact]) -> int:
        rows = list(facts)
        if not rows:
            return 0
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO financial_facts(
                    symbol, market, period_end, filed_at, available_at, period_type,
                    metric, value, unit, currency, source, source_url, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, period_end, period_type, metric, source) DO UPDATE SET
                    filed_at=excluded.filed_at, available_at=excluded.available_at,
                    value=excluded.value, unit=excluded.unit, currency=excluded.currency,
                    source_url=excluded.source_url, payload_json=excluded.payload_json,
                    created_at=excluded.created_at
                """,
                [
                    (
                        item.symbol,
                        item.market,
                        item.period_end.isoformat(),
                        item.filed_at.isoformat(),
                        (item.available_at or item.filed_at).isoformat(),
                        item.period_type,
                        item.metric,
                        float(item.value),
                        item.unit,
                        item.currency,
                        item.source,
                        item.source_url,
                        json.dumps(item.extra, ensure_ascii=False, allow_nan=False),
                        now,
                    )
                    for item in rows
                ],
            )
        return len(rows)

    def save_items(self, items: Iterable[ResearchItem]) -> int:
        rows = list(items)
        if not rows:
            return 0
        now = datetime.now(UTC).isoformat()
        inserted = 0
        with self.connect() as connection:
            for item in rows:
                item_id, raw_hash = self._item_identity(item)
                cursor = connection.execute(
                    """
                    INSERT INTO research_items(
                        item_id, kind, tier, symbol, market, title, published_at,
                        available_at, report_date, source, url, author, summary,
                        sentiment, confidence, raw_hash, payload_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                        title=excluded.title, summary=excluded.summary,
                        sentiment=excluded.sentiment, confidence=excluded.confidence,
                        payload_json=excluded.payload_json, created_at=excluded.created_at
                    """,
                    (
                        item_id,
                        item.kind.value,
                        item.tier.value,
                        item.symbol,
                        item.market,
                        item.title,
                        item.published_at.isoformat(),
                        (item.available_at or item.published_at).isoformat(),
                        item.report_date.isoformat() if item.report_date else None,
                        item.source,
                        item.url,
                        item.author,
                        item.summary,
                        item.sentiment,
                        min(1.0, max(0.0, float(item.confidence))),
                        raw_hash,
                        json.dumps(item.extra, ensure_ascii=False, allow_nan=False),
                        now,
                    ),
                )
                inserted += max(0, cursor.rowcount)
                try:
                    connection.execute("DELETE FROM research_items_fts WHERE item_id=?", (item_id,))
                    connection.execute(
                        "INSERT INTO research_items_fts VALUES (?, ?, ?, ?, ?)",
                        (item_id, item.title, item.summary, item.author, item.source),
                    )
                except sqlite3.OperationalError:
                    pass
        return inserted

    def save_macro(self, observations: Iterable[MacroObservation]) -> int:
        rows = list(observations)
        if not rows:
            return 0
        now = datetime.now(UTC).isoformat()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO macro_observations(
                    series_id, name, dimension, observation_date, release_at, vintage_at,
                    value, previous, change_value, change_pct, consensus, signal, unit,
                    source, source_url, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(series_id, observation_date, vintage_at, source) DO UPDATE SET
                    value=excluded.value, previous=excluded.previous,
                    change_value=excluded.change_value, change_pct=excluded.change_pct,
                    consensus=excluded.consensus, signal=excluded.signal,
                    payload_json=excluded.payload_json, created_at=excluded.created_at
                """,
                [
                    (
                        item.series_id,
                        item.name,
                        item.dimension,
                        item.observation_date.isoformat(),
                        item.release_at.isoformat(),
                        (item.vintage_at or item.release_at).isoformat(),
                        float(item.value),
                        item.previous,
                        item.change,
                        item.change_pct,
                        item.consensus,
                        max(-2, min(2, int(item.signal))),
                        item.unit,
                        item.source,
                        item.source_url,
                        json.dumps(item.extra, ensure_ascii=False, allow_nan=False),
                        now,
                    )
                    for item in rows
                ],
            )
        return len(rows)

    def mark_refresh(self, scope: str, status: str, errors: dict[str, str] | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_refreshes(scope, refreshed_at, status, errors_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope) DO UPDATE SET refreshed_at=excluded.refreshed_at,
                    status=excluded.status, errors_json=excluded.errors_json
                """,
                (
                    scope,
                    datetime.now(UTC).isoformat(),
                    status,
                    json.dumps(errors or {}, ensure_ascii=False),
                ),
            )

    def refresh_status(self, scope: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_refreshes WHERE scope=?", (scope,)
            ).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["errors"] = json.loads(str(payload.pop("errors_json") or "{}"))
        return payload

    def financial_facts(self, symbol: str, limit: int = 120) -> list[FinancialFact]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM financial_facts WHERE symbol=?
                ORDER BY period_end DESC, metric LIMIT ?
                """,
                (symbol, max(1, limit)),
            ).fetchall()
        return [
            FinancialFact(
                symbol=row["symbol"], market=row["market"],
                period_end=date.fromisoformat(row["period_end"]),
                filed_at=_parse_datetime(row["filed_at"]), metric=row["metric"],
                value=float(row["value"]), unit=row["unit"], currency=row["currency"],
                source=row["source"], source_url=row["source_url"],
                period_type=row["period_type"], available_at=_parse_datetime(row["available_at"]),
                extra=json.loads(row["payload_json"] or "{}"),
            )
            for row in rows
        ]

    def research_items(
        self,
        symbol: str = "",
        kinds: Iterable[ResearchKind | str] | None = None,
        limit: int = 100,
    ) -> list[ResearchItem]:
        clauses: list[str] = []
        parameters: list[object] = []
        if symbol:
            clauses.append("symbol=?")
            parameters.append(symbol)
        normalized_kinds = [item.value if isinstance(item, ResearchKind) else str(item) for item in (kinds or [])]
        if normalized_kinds:
            clauses.append("kind IN (" + ",".join("?" for _ in normalized_kinds) + ")")
            parameters.extend(normalized_kinds)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.append(max(1, limit))
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM research_items{where} ORDER BY published_at DESC LIMIT ?",  # noqa: S608
                parameters,
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> ResearchItem:
        return ResearchItem(
            item_id=row["item_id"], kind=ResearchKind(row["kind"]),
            tier=SourceTier(row["tier"]), symbol=row["symbol"], market=row["market"],
            title=row["title"], published_at=_parse_datetime(row["published_at"]),
            available_at=_parse_datetime(row["available_at"]), source=row["source"],
            url=row["url"], author=row["author"], summary=row["summary"],
            sentiment=row["sentiment"], confidence=float(row["confidence"]),
            report_date=date.fromisoformat(row["report_date"]) if row["report_date"] else None,
            extra=json.loads(row["payload_json"] or "{}"),
        )

    def macro_latest(self) -> list[MacroObservation]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT m.* FROM macro_observations m
                JOIN (
                    SELECT series_id, MAX(observation_date || '|' || vintage_at) latest
                    FROM macro_observations GROUP BY series_id
                ) x ON x.series_id=m.series_id
                    AND (m.observation_date || '|' || m.vintage_at)=x.latest
                ORDER BY m.dimension, m.name
                """
            ).fetchall()
        return [
            MacroObservation(
                series_id=row["series_id"], name=row["name"], dimension=row["dimension"],
                observation_date=date.fromisoformat(row["observation_date"]),
                value=float(row["value"]), previous=row["previous"], change=row["change_value"],
                change_pct=row["change_pct"], consensus=row["consensus"],
                signal=int(row["signal"]), unit=row["unit"], source=row["source"],
                source_url=row["source_url"], release_at=_parse_datetime(row["release_at"]),
                vintage_at=_parse_datetime(row["vintage_at"]),
                extra=json.loads(row["payload_json"] or "{}"),
            )
            for row in rows
        ]

    def snapshot(self, symbol: str, market: str = "") -> ResearchSnapshot:
        items = self.research_items(symbol, limit=200)
        filings = [item for item in items if item.kind == ResearchKind.FILING]
        news = [item for item in items if item.kind in {ResearchKind.NEWS, ResearchKind.OFFICIAL_ANALYSIS}]
        opinions = [item for item in items if item.kind in {ResearchKind.MEDIA_OPINION, ResearchKind.COMMUNITY_OPINION}]
        status = self.refresh_status(f"asset:{symbol}") or {}
        return ResearchSnapshot(
            symbol=symbol,
            market=market,
            refreshed_at=_parse_datetime(str(status.get("refreshed_at") or "")),
            financial_facts=self.financial_facts(symbol),
            filings=filings,
            news=news,
            opinions=opinions,
            errors=dict(status.get("errors") or {}),
        )

    def report_summary(self, symbols: Iterable[str], per_symbol: int = 3) -> dict[str, object]:
        result: dict[str, object] = {}
        for symbol in dict.fromkeys(symbols):
            snapshot = self.snapshot(symbol)
            if not (snapshot.financial_facts or snapshot.filings or snapshot.news or snapshot.opinions):
                continue
            result[symbol] = {
                "latest_financial_period": (
                    max(item.period_end for item in snapshot.financial_facts).isoformat()
                    if snapshot.financial_facts else None
                ),
                "latest_items": [
                    {
                        "kind": item.kind.value,
                        "tier": item.tier.value,
                        "title": item.title,
                        "source": item.source,
                        "published_at": item.published_at.isoformat(),
                        "url": item.url,
                    }
                    for item in (snapshot.filings + snapshot.news + snapshot.opinions)[:per_symbol]
                ],
            }
        macro = self.macro_latest()
        return {
            "assets": result,
            "macro": [item.to_dict() for item in macro],
            "generated_at": datetime.now(UTC).isoformat(),
        }
