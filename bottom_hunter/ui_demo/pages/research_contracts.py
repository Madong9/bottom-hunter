"""PHASE 4-B — Research page DTOs and read-only report adapter.

The generated daily report is the boundary for this page.  The adapter only
reads the latest JSON snapshot and transports its existing ``research`` data;
it performs no refresh, persistence, scoring, or sentiment analysis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPORT_DIR = BACKEND_DIR / "reports"


@dataclass(frozen=True)
class ResearchItemDTO:
    """One existing filing/news/opinion item from a report snapshot."""

    kind: str = ""
    tier: str = ""
    title: str = "--"
    source: str = "--"
    published_at: str = ""
    url: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tier": self.tier,
            "title": self.title,
            "source": self.source,
            "published_at": self.published_at,
            "url": self.url,
        }


@dataclass(frozen=True)
class ResearchAssetDTO:
    """Research summary already attached to one asset in the report."""

    symbol: str = "--"
    latest_financial_period: str = "--"
    items: tuple[ResearchItemDTO, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "latest_financial_period": self.latest_financial_period,
            "items": [item.as_dict() for item in self.items],
        }


@dataclass(frozen=True)
class ResearchMacroDTO:
    """One existing macro observation from the report snapshot."""

    series_id: str = ""
    name: str = "--"
    dimension: str = "--"
    observation_date: str = "--"
    value: int | float | str | None = None
    unit: str = ""
    source: str = "--"
    source_url: str = ""
    signal: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "name": self.name,
            "dimension": self.dimension,
            "observation_date": self.observation_date,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "source_url": self.source_url,
            "signal": self.signal,
        }


@dataclass(frozen=True)
class ResearchDTO:
    """Complete immutable transport contract for the read-only page."""

    assets: tuple[ResearchAssetDTO, ...] = field(default_factory=tuple)
    macro: tuple[ResearchMacroDTO, ...] = field(default_factory=tuple)
    generated_at: str = ""
    report_date: str = "--"

    def as_dict(self) -> dict[str, Any]:
        return {
            "assets": [asset.as_dict() for asset in self.assets],
            "macro": [item.as_dict() for item in self.macro],
            "generated_at": self.generated_at,
            "report_date": self.report_date,
        }


def _latest_report(report_dir: Path) -> Path | None:
    paths = sorted(report_dir.glob("daily_report_*.json"))
    return paths[-1] if paths else None


def _read_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取研究快照：{path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"研究快照格式无效：{path.name}")
    return payload


def build_research_dto(report_dir: Path = REPORT_DIR) -> ResearchDTO | None:
    """Load existing research data from the latest generated report only."""

    path = _latest_report(report_dir)
    if path is None:
        return None

    payload = _read_report(path)
    research = payload.get("research") or {}
    if not isinstance(research, dict):
        raise ValueError(f"研究快照格式无效：{path.name}")

    assets: list[ResearchAssetDTO] = []
    raw_assets = research.get("assets") or {}
    if isinstance(raw_assets, dict):
        for symbol, raw_asset in raw_assets.items():
            if not isinstance(raw_asset, dict):
                continue
            items: list[ResearchItemDTO] = []
            for raw_item in raw_asset.get("latest_items") or ():
                if not isinstance(raw_item, dict):
                    continue
                items.append(
                    ResearchItemDTO(
                        kind=str(raw_item.get("kind") or ""),
                        tier=str(raw_item.get("tier") or ""),
                        title=str(raw_item.get("title") or "--"),
                        source=str(raw_item.get("source") or "--"),
                        published_at=str(raw_item.get("published_at") or ""),
                        url=str(raw_item.get("url") or ""),
                    )
                )
            assets.append(
                ResearchAssetDTO(
                    symbol=str(symbol or "--"),
                    latest_financial_period=str(raw_asset.get("latest_financial_period") or "--"),
                    items=tuple(items),
                )
            )

    macro: list[ResearchMacroDTO] = []
    for raw_item in research.get("macro") or ():
        if not isinstance(raw_item, dict):
            continue
        try:
            signal = int(raw_item.get("signal") or 0)
        except (TypeError, ValueError):
            signal = 0
        macro.append(
            ResearchMacroDTO(
                series_id=str(raw_item.get("series_id") or ""),
                name=str(raw_item.get("name") or "--"),
                dimension=str(raw_item.get("dimension") or "--"),
                observation_date=str(raw_item.get("observation_date") or "--"),
                value=raw_item.get("value"),
                unit=str(raw_item.get("unit") or ""),
                source=str(raw_item.get("source") or "--"),
                source_url=str(raw_item.get("source_url") or ""),
                signal=signal,
            )
        )

    return ResearchDTO(
        assets=tuple(assets),
        macro=tuple(macro),
        generated_at=str(research.get("generated_at") or ""),
        report_date=str(payload.get("report_date") or path.stem.removeprefix("daily_report_")),
    )
