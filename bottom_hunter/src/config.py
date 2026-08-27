from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import Instrument


PROJECT_DIR = Path(__file__).resolve().parents[1]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


@dataclass(frozen=True)
class AppConfig:
    config_dir: Path
    project_dir: Path
    watchlist: dict[str, Any]
    thresholds: dict[str, Any]

    @classmethod
    def load(cls, config_dir: str | Path | None = None) -> "AppConfig":
        directory = Path(config_dir) if config_dir else PROJECT_DIR / "config"
        directory = directory.resolve()
        watchlist_path = directory / "watchlist.yaml"
        thresholds_path = directory / "thresholds.yaml"
        if not watchlist_path.exists() or not thresholds_path.exists():
            raise FileNotFoundError(
                f"配置目录必须包含 watchlist.yaml 和 thresholds.yaml: {directory}"
            )
        with watchlist_path.open(encoding="utf-8") as handle:
            watchlist = yaml.safe_load(handle) or {}
        with thresholds_path.open(encoding="utf-8") as handle:
            thresholds = yaml.safe_load(handle) or {}
        _validate_watchlist(watchlist)
        return cls(directory, PROJECT_DIR, watchlist, thresholds)

    @property
    def markets(self) -> dict[str, dict[str, Any]]:
        return self.watchlist["markets"]

    @property
    def sectors(self) -> dict[str, dict[str, Any]]:
        return self.watchlist["sectors"]

    @property
    def defaults(self) -> dict[str, Any]:
        return self.thresholds.get("defaults", {})

    @property
    def mode(self) -> str:
        return str(self.watchlist.get("mode", "static"))

    @property
    def configured_asset_count(self) -> int:
        return sum(len(sector.get("assets", [])) for sector in self.sectors.values())

    def sector_thresholds(self, sector_id: str) -> dict[str, Any]:
        override = self.thresholds.get("sector_overrides", {}).get(sector_id, {})
        return deep_merge(self.defaults, override)

    def sector_assets(self, sector_id: str, market: str | None = None) -> list[Instrument]:
        sector = self.sectors[sector_id]
        assets = [
            _instrument(item, sector_id)
            for item in sector.get("assets", [])
            if market is None or item["market"] == market
        ]
        return assets

    def sector_etfs(self, sector_id: str, market: str | None = None) -> list[Instrument]:
        sector = self.sectors[sector_id]
        return [
            _instrument(item, sector_id)
            for item in sector.get("etfs", [])
            if market is None or item["market"] == market
        ]

    def all_instruments(self) -> list[Instrument]:
        result: dict[str, Instrument] = {}
        for sector_id in self.sectors:
            for item in self.sector_assets(sector_id) + self.sector_etfs(sector_id):
                result.setdefault(item.symbol, item)
        for item in self.watchlist.get("risk_appetite", []):
            instrument = _instrument(item, None)
            result.setdefault(instrument.symbol, instrument)
        for market_id, market in self.markets.items():
            benchmark = Instrument(
                symbol=str(market["benchmark"]),
                name=f"{market['name']}基准",
                market=market_id,
                volume_optional=True,
                category=str(market.get("category", "")),
                asset_type="crypto" if market_id == "CRYPTO" else "index",
                sources=tuple((market.get("benchmark_source_symbols") or {}).keys()),
                source_symbols={
                    str(key): str(value)
                    for key, value in (market.get("benchmark_source_symbols") or {}).items()
                },
            )
            result.setdefault(benchmark.symbol, benchmark)
        return list(result.values())

    def risk_instruments(self, market: str) -> list[Instrument]:
        return [
            _instrument(item, None)
            for item in self.watchlist.get("risk_appetite", [])
            if item["market"] == market
        ]


def _instrument(item: dict[str, Any], sector_id: str | None) -> Instrument:
    return Instrument(
        symbol=str(item["symbol"]),
        name=str(item.get("name", item["symbol"])),
        market=str(item["market"]),
        sector_id=sector_id,
        leader=bool(item.get("leader", False)),
        inverse=bool(item.get("inverse", False)),
        provider_symbol=item.get("provider_symbol"),
        volume_optional=bool(item.get("volume_optional", False)),
        category=str(item.get("category", "")),
        industry=str(item.get("industry", "")),
        asset_type=str(item.get("asset_type", "equity")),
        tokenized_stock=bool(item.get("tokenized_stock", False)),
        sources=tuple(str(value) for value in item.get("sources", [])),
        source_symbols={
            str(key): str(value) for key, value in (item.get("source_symbols") or {}).items()
        },
    )


def _validate_watchlist(payload: dict[str, Any]) -> None:
    if (
        not payload.get("markets")
        or "sectors" not in payload
        or not isinstance(payload.get("sectors"), dict)
    ):
        raise ValueError("watchlist.yaml 缺少 markets 或 sectors")
    known_markets = set(payload["markets"])
    seen: set[tuple[str, str]] = set()
    for sector_id, sector in payload["sectors"].items():
        for kind in ("assets", "etfs"):
            for item in sector.get(kind, []):
                missing = {"symbol", "market"} - set(item)
                if missing:
                    raise ValueError(f"{sector_id}.{kind} 缺少字段: {sorted(missing)}")
                if item["market"] not in known_markets:
                    raise ValueError(f"未知市场 {item['market']}: {item['symbol']}")
                key = (sector_id, str(item["symbol"]))
                if key in seen:
                    raise ValueError(f"板块内证券重复: {sector_id}/{item['symbol']}")
                seen.add(key)
