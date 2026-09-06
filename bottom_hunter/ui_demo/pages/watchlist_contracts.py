"""PHASE 4-A — Watchlist page DTO + read-only adapter.

Architecture (read-only, frozen):

    watchlist_summary.json (state snapshot, backend-produced)
            |
            v  (read-only file load; NO write / rebuild / import)
    WatchlistItemDTO / WatchlistDTO  (pure frozen data)
            |
            v
    WatchlistViewModel.apply(dto)  (display state only)
            |
            v
    Watchlist.qml

The adapter is the ONLY sanctioned boundary that reads watchlist data. It
reads the already-generated ``watchlist_summary.json`` directly instead of
calling the repository's ``summary`` method, because that method can fall
back to a rebuild (a WRITE). This phase is strictly read-only, so no backend
write path may be touched.

The adapter may join values already present in the latest report snapshot. It
does not request quotes or calculate a new signal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# backend package dir (frozen; read-only file reference only)
BACKEND_DIR = Path(__file__).resolve().parents[2]
STATE_DIR = BACKEND_DIR / "state"
SUMMARY_PATH = STATE_DIR / "watchlist_summary.json"
REPORT_DIR = BACKEND_DIR / "reports"


@dataclass(frozen=True)
class WatchlistItemDTO:
    """Single read-only row. Pure data — no computation, no DB, no state."""

    canonical_id: str = ""
    symbol: str = "--"
    name: str = "--"
    market: str = "--"
    industry: str = "--"
    category: str = "--"
    price: str = "--"
    change: str = "--"
    change_percent: str = "--"
    signal: str = "--"
    sources: tuple[str, ...] = field(default_factory=tuple)
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_id": self.canonical_id,
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "industry": self.industry,
            "category": self.category,
            "price": self.price,
            "change": self.change,
            "change_percent": self.change_percent,
            "signal": self.signal,
            "sources": list(self.sources),
            "source_text": " / ".join(self.sources) or "--",
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class WatchlistDTO:
    """Complete read-only watchlist snapshot. Immutable."""

    items: tuple[WatchlistItemDTO, ...] = field(default_factory=tuple)
    generated_at: str = ""
    crypto_count: int = 0
    global_equity_count: int = 0
    cn_equity_count: int = 0
    overlap_count: int = 0
    unresolved_industry_count: int = 0
    sector_count: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": [i.as_dict() for i in self.items],
            "generated_at": self.generated_at,
            "crypto_count": self.crypto_count,
            "global_equity_count": self.global_equity_count,
            "cn_equity_count": self.cn_equity_count,
            "overlap_count": self.overlap_count,
            "unresolved_industry_count": self.unresolved_industry_count,
            "sector_count": self.sector_count,
        }


def _load_summary(path: Path = SUMMARY_PATH) -> dict[str, Any] | None:
    """Read the backend-produced summary snapshot (read-only JSON load).

    Returns None when the snapshot is absent or malformed. This is a pure
    file read — no repo construction, no rebuild fallback, no writes.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _latest_signal_rows(report_dir: Path) -> dict[str, dict[str, Any]]:
    paths = sorted(report_dir.glob("daily_report_*.json"))
    if not paths:
        return {}
    try:
        payload = json.loads(paths[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("signals") if isinstance(payload, dict) else ()
    return {
        str(row.get("symbol") or "").upper(): row
        for row in rows or ()
        if isinstance(row, dict) and row.get("symbol")
    }


def _display_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "--"
    absolute = abs(number)
    if 0 < absolute < 0.0001:
        return f"{number:.10f}".rstrip("0").rstrip(".")
    if 0 < absolute < 1:
        return f"{number:.6f}".rstrip("0").rstrip(".")
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def build_watchlist_dto(
    summary_path: Path = SUMMARY_PATH,
    report_dir: Path = REPORT_DIR,
) -> WatchlistDTO | None:
    """Build a read-only WatchlistDTO from the summary snapshot; None when
    there is no snapshot yet (view model reports an empty/error state)."""
    data = _load_summary(Path(summary_path))
    if data is None:
        return None
    signals = _latest_signal_rows(Path(report_dir))

    items: list[WatchlistItemDTO] = []
    for asset in data.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        symbol = str(asset.get("symbol") or "--")
        signal = signals.get(symbol.upper(), {})
        metrics = signal.get("metrics") if isinstance(signal, dict) else {}
        metrics = metrics if isinstance(metrics, dict) else {}
        score = signal.get("score") if isinstance(signal, dict) else {}
        score = score if isinstance(score, dict) else {}
        return_1d = metrics.get("return_1d")
        try:
            change_percent = f"{float(return_1d):+.2%}" if return_1d is not None else "--"
        except (TypeError, ValueError):
            change_percent = "--"
        signal_level = str(signal.get("signal_level") or "--") if signal else "--"
        score_text = (
            f"{signal_level} · {int(score.get('total') or 0)}/{int(score.get('available_max') or 10)}"
            if signal
            else "--"
        )
        raw_sources = asset.get("sources") or ()
        sources = tuple(str(value) for value in raw_sources if value) if isinstance(raw_sources, list) else ()
        items.append(
            WatchlistItemDTO(
                canonical_id=str(asset.get("canonical_id") or symbol),
                symbol=symbol,
                name=str(asset.get("name") or "--"),
                market=str(asset.get("market") or "--"),
                industry=str(asset.get("industry") or "--"),
                category=str(asset.get("category") or "--"),
                price=_display_number(metrics.get("close")),
                change=change_percent,
                change_percent=change_percent,
                signal=score_text,
                sources=sources,
                updated_at=str(signal.get("data_timestamp") or data.get("generated_at") or ""),
            )
        )
    counts = data.get("category_counts") or {}
    return WatchlistDTO(
        items=tuple(items),
        generated_at=str(data.get("generated_at") or ""),
        crypto_count=int(counts.get("crypto") or 0),
        global_equity_count=int(counts.get("global_equity") or 0),
        cn_equity_count=int(counts.get("cn_equity") or 0),
        overlap_count=int(data.get("overlap_count") or 0),
        unresolved_industry_count=int(data.get("unresolved_industry_count") or 0),
        sector_count=int(data.get("sector_count") or 0),
    )
