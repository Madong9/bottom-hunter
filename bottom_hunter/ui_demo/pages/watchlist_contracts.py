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

Price / change / signal are NOT computed here (that would be business logic
and data-provider territory). They are carried through as empty/unknown
strings so the view model + QML can render a neutral, honest read-only row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# backend package dir (frozen; read-only file reference only)
BACKEND_DIR = Path(__file__).resolve().parents[2]
STATE_DIR = BACKEND_DIR / "state"
SUMMARY_PATH = STATE_DIR / "watchlist_summary.json"


@dataclass(frozen=True)
class WatchlistItemDTO:
    """Single read-only row. Pure data — no computation, no DB, no state."""

    symbol: str = "--"
    name: str = "--"
    market: str = "--"
    industry: str = "--"
    category: str = "--"
    price: str = "--"
    change: str = "--"
    change_percent: str = "--"
    signal: str = "--"
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "industry": self.industry,
            "category": self.category,
            "price": self.price,
            "change": self.change,
            "change_percent": self.change_percent,
            "signal": self.signal,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class WatchlistDTO:
    """Complete read-only watchlist snapshot. Immutable."""

    items: tuple[WatchlistItemDTO, ...] = field(default_factory=tuple)
    generated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": [i.as_dict() for i in self.items],
            "generated_at": self.generated_at,
        }


def _load_summary(path: Path = SUMMARY_PATH) -> dict[str, Any] | None:
    """Read the backend-produced summary snapshot (read-only JSON load).

    Returns None when the snapshot is absent or malformed. This is a pure
    file read — no repo construction, no rebuild fallback, no writes.
    """
    if not path.exists():
        return None
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def build_watchlist_dto() -> WatchlistDTO | None:
    """Build a read-only WatchlistDTO from the summary snapshot; None when
    there is no snapshot yet (view model reports an empty/error state)."""
    data = _load_summary()
    if data is None:
        return None

    items: list[WatchlistItemDTO] = []
    for asset in data.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        items.append(
            WatchlistItemDTO(
                symbol=str(asset.get("symbol") or "--"),
                name=str(asset.get("name") or "--"),
                market=str(asset.get("market") or "--"),
                industry=str(asset.get("industry") or "--"),
                category=str(asset.get("category") or "--"),
                # read-only phase: no snapshotting of quotes/signals
                price="--",
                change="--",
                change_percent="--",
                signal="--",
                updated_at=str(data.get("generated_at") or ""),
            )
        )
    return WatchlistDTO(items=tuple(items), generated_at=str(data.get("generated_at") or ""))
