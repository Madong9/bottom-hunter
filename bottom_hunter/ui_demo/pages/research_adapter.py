"""Read-only research adapter joining report snapshots with the SQLite cache."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from .research_contracts import (
    REPORT_DIR,
    ResearchAssetDTO,
    ResearchDTO,
    ResearchItemDTO,
)
from .research_contracts import build_research_dto as build_report_research_dto

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATABASE_PATH = BACKEND_DIR / "state" / "signals.db"
WATCHLIST_PATH = BACKEND_DIR / "state" / "watchlist_summary.json"


def _read_watchlist(path: Path) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, dict[str, str]] = {}
    for raw in payload.get("assets") or () if isinstance(payload, dict) else ():
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol") or "").upper()
        if symbol:
            result[symbol] = {
                "name": str(raw.get("name") or symbol),
                "market": str(raw.get("market") or "--"),
            }
    return result


def _connect_read_only(path: Path) -> sqlite3.Connection:
    encoded = quote(path.resolve().as_posix(), safe="/")
    connection = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _cached_assets(
    database: Path,
    watchlist_path: Path,
) -> tuple[tuple[ResearchAssetDTO, ...], str]:
    if not database.is_file():
        return (), ""
    metadata = _read_watchlist(watchlist_path)
    try:
        with _connect_read_only(database) as connection:
            facts = connection.execute(
                """
                SELECT symbol, market, MAX(period_end) latest_period, COUNT(*) fact_count,
                       MAX(created_at) latest_created
                FROM financial_facts WHERE symbol <> '' GROUP BY symbol, market
                """
            ).fetchall()
            item_counts = connection.execute(
                """
                SELECT symbol, market, COUNT(*) item_count, MAX(created_at) latest_created
                FROM research_items WHERE symbol <> '' GROUP BY symbol, market
                """
            ).fetchall()
            recent_items = connection.execute(
                """
                SELECT symbol, kind, tier, title, source, published_at, url, summary, sentiment
                FROM (
                    SELECT symbol, kind, tier, title, source, published_at, url, summary,
                           sentiment,
                           ROW_NUMBER() OVER (
                               PARTITION BY symbol ORDER BY published_at DESC, item_id DESC
                           ) row_number
                    FROM research_items WHERE symbol <> ''
                ) WHERE row_number <= 4
                ORDER BY symbol, published_at DESC
                """
            ).fetchall()
    except sqlite3.Error:
        return (), ""

    records: dict[str, dict[str, object]] = {}
    generated_at = ""
    for row in facts:
        symbol = str(row["symbol"] or "").upper()
        if not symbol:
            continue
        record = records.setdefault(symbol, {})
        record.update(
            market=str(row["market"] or "--"),
            latest_period=str(row["latest_period"] or "--"),
            fact_count=int(row["fact_count"] or 0),
        )
        generated_at = max(generated_at, str(row["latest_created"] or ""))
    for row in item_counts:
        symbol = str(row["symbol"] or "").upper()
        if not symbol:
            continue
        record = records.setdefault(symbol, {})
        record.setdefault("market", str(row["market"] or "--"))
        record["item_count"] = int(row["item_count"] or 0)
        generated_at = max(generated_at, str(row["latest_created"] or ""))

    items_by_symbol: dict[str, list[ResearchItemDTO]] = defaultdict(list)
    for row in recent_items:
        symbol = str(row["symbol"] or "").upper()
        items_by_symbol[symbol].append(
            ResearchItemDTO(
                kind=str(row["kind"] or ""),
                tier=str(row["tier"] or ""),
                title=str(row["title"] or "--"),
                source=str(row["source"] or "--"),
                published_at=str(row["published_at"] or ""),
                url=str(row["url"] or ""),
                summary=str(row["summary"] or ""),
                sentiment=str(row["sentiment"] or "neutral"),
            )
        )

    assets = []
    for symbol, record in records.items():
        meta = metadata.get(symbol, {})
        assets.append(
            ResearchAssetDTO(
                symbol=symbol,
                name=str(meta.get("name") or symbol),
                market=str(meta.get("market") or record.get("market") or "--"),
                latest_financial_period=str(record.get("latest_period") or "--"),
                financial_fact_count=int(record.get("fact_count") or 0),
                research_item_count=int(record.get("item_count") or 0),
                items=tuple(items_by_symbol.get(symbol, ())),
            )
        )
    assets.sort(key=lambda item: (-(item.research_item_count + item.financial_fact_count), item.symbol))
    return tuple(assets), generated_at


def _merge_assets(
    report_assets: tuple[ResearchAssetDTO, ...],
    cached_assets: tuple[ResearchAssetDTO, ...],
) -> tuple[ResearchAssetDTO, ...]:
    merged = {asset.symbol.upper(): asset for asset in cached_assets}
    for asset in report_assets:
        key = asset.symbol.upper()
        cached = merged.get(key)
        merged[key] = ResearchAssetDTO(
            symbol=asset.symbol,
            name=asset.name if asset.name != "--" else (cached.name if cached else asset.symbol),
            market=asset.market if asset.market != "--" else (cached.market if cached else "--"),
            latest_financial_period=(
                asset.latest_financial_period
                if asset.latest_financial_period != "--"
                else (cached.latest_financial_period if cached else "--")
            ),
            financial_fact_count=cached.financial_fact_count if cached else asset.financial_fact_count,
            research_item_count=cached.research_item_count if cached else len(asset.items),
            items=asset.items or (cached.items if cached else ()),
        )
    return tuple(merged.values())


def build_research_dto(
    report_dir: Path = REPORT_DIR,
    *,
    database: Path = DATABASE_PATH,
    watchlist_path: Path = WATCHLIST_PATH,
) -> ResearchDTO | None:
    """Return existing report/cache content without refreshing or writing either source."""

    report = build_report_research_dto(Path(report_dir))
    cached_assets, cache_generated_at = _cached_assets(Path(database), Path(watchlist_path))
    if report is None and not cached_assets:
        return None
    report = report or ResearchDTO()
    return ResearchDTO(
        assets=_merge_assets(report.assets, cached_assets),
        macro=tuple(report.macro),
        generated_at=report.generated_at or cache_generated_at,
        report_date=report.report_date,
    )


__all__ = ["build_research_dto"]
