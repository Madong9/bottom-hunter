"""The sole read-only boundary between QML chart flow and chart backend."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .chart_contracts import ChartAssetDTO, ChartBarDTO, ChartDTO

BACKEND_DIR = Path(__file__).resolve().parents[2]
SUMMARY_PATH = BACKEND_DIR / "state" / "watchlist_summary.json"


def _number(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def load_chart_assets(path: str | Path = SUMMARY_PATH) -> tuple[ChartAssetDTO, ...]:
    """Read chart candidates from the existing watchlist snapshot without mutation."""

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict):
        return ()

    assets: list[ChartAssetDTO] = []
    for raw in payload.get("assets") or ():
        if not isinstance(raw, dict):
            continue
        canonical_id = str(raw.get("canonical_id") or raw.get("symbol") or "").strip()
        symbol = str(raw.get("symbol") or "").strip()
        if not canonical_id or not symbol:
            continue
        source_symbols = raw.get("source_symbols") or {}
        assets.append(
            ChartAssetDTO(
                canonical_id=canonical_id,
                symbol=symbol,
                name=str(raw.get("name") or symbol),
                market=str(raw.get("market") or ""),
                category=str(raw.get("category") or ""),
                source_symbols=tuple(
                    sorted(
                        (str(key), str(value))
                        for key, value in source_symbols.items()
                        if value
                    )
                )
                if isinstance(source_symbols, dict)
                else (),
            )
        )
    return tuple(assets)


class ChartReadAdapter:
    """Resolve a selected asset and convert backend ChartResult into frozen DTOs."""

    def __init__(
        self,
        *,
        summary_path: str | Path = SUMMARY_PATH,
        service: object | None = None,
        assets: tuple[ChartAssetDTO, ...] | None = None,
    ) -> None:
        if service is None:
            from bottom_hunter.src.charting import MarketChartService

            service = MarketChartService()
        self._service = service
        loaded = load_chart_assets(summary_path) if assets is None else tuple(assets)
        self._assets = {asset.canonical_id: asset for asset in loaded}

    @property
    def assets(self) -> tuple[ChartAssetDTO, ...]:
        return tuple(self._assets.values())

    def fetch(self, canonical_id: str, timeframe: str, limit: int) -> ChartDTO:
        from bottom_hunter.src.charting import calculate_chart_indicators

        asset = self._assets.get(str(canonical_id))
        if asset is None:
            raise ValueError("所选标的已不在当前自选快照中。")
        result = self._service.fetch(asset.backend_mapping(), str(timeframe), int(limit))
        indicators = calculate_chart_indicators(result.bars)
        bars: list[ChartBarDTO] = []
        for timestamp, row in result.bars.iterrows():
            indicator = indicators.loc[timestamp] if timestamp in indicators.index else {}
            bars.append(
                ChartBarDTO(
                    timestamp=timestamp.isoformat(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0) or 0),
                    ma5=_number(indicator.get("ma5")),
                    ma10=_number(indicator.get("ma10")),
                    ma20=_number(indicator.get("ma20")),
                    ma60=_number(indicator.get("ma60")),
                    boll_upper=_number(indicator.get("boll_upper")),
                    boll_mid=_number(indicator.get("boll_mid")),
                    boll_lower=_number(indicator.get("boll_lower")),
                    macd_dif=_number(indicator.get("macd_dif")),
                    macd_dea=_number(indicator.get("macd_dea")),
                    macd_hist=_number(indicator.get("macd_hist")),
                    rsi14=_number(indicator.get("rsi14")),
                    kdj_k=_number(indicator.get("kdj_k")),
                    kdj_d=_number(indicator.get("kdj_d")),
                    kdj_j=_number(indicator.get("kdj_j")),
                )
            )
        return ChartDTO(
            canonical_id=result.canonical_id,
            symbol=result.symbol,
            name=result.name,
            market=asset.market,
            timeframe=result.timeframe,
            bars=tuple(bars),
            provider=result.provider,
            updated_at=result.updated_at.isoformat(),
            note=result.note,
        )
