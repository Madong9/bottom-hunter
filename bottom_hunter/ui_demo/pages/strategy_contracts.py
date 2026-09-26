"""Frozen transport objects for the experimental strategy research page."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FactorResultDTO:
    label: str = ""
    mean_ic: float = 0.0
    icir: float = 0.0
    periods: int = 0
    direction: str = "--"

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "mean_ic": self.mean_ic,
            "icir": self.icir,
            "periods": self.periods,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class StrategyResearchDTO:
    generated_at: str = ""
    asset_count: int = 0
    sample_count: int = 0
    factors: tuple[FactorResultDTO, ...] = field(default_factory=tuple)
    machine_learning: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    reinforcement_learning: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    caveats: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "asset_count": self.asset_count,
            "sample_count": self.sample_count,
            "factors": [item.as_dict() for item in self.factors],
            "machine_learning": dict(self.machine_learning),
            "reinforcement_learning": dict(self.reinforcement_learning),
            "caveats": list(self.caveats),
        }


def build_strategy_research_dto(
    payload: dict[str, Any] | None = None,
) -> StrategyResearchDTO:
    if not payload:
        return StrategyResearchDTO()
    return StrategyResearchDTO(
        generated_at=str(payload.get("generated_at") or ""),
        asset_count=int(payload.get("asset_count") or 0),
        sample_count=int(payload.get("sample_count") or 0),
        factors=tuple(
            FactorResultDTO(
                label=str(item.get("label") or ""),
                mean_ic=float(item.get("mean_ic") or 0),
                icir=float(item.get("icir") or 0),
                periods=int(item.get("periods") or 0),
                direction=str(item.get("direction") or "--"),
            )
            for item in payload.get("factors") or ()
        ),
        machine_learning=tuple(sorted((payload.get("machine_learning") or {}).items())),
        reinforcement_learning=tuple(sorted((payload.get("reinforcement_learning") or {}).items())),
        caveats=tuple(str(item) for item in payload.get("caveats") or ()),
    )
