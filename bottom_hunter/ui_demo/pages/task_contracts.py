"""Immutable command transport for scan/backtest process execution."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskCommandDTO:
    kind: str
    name: str
    program: str
    arguments: tuple[str, ...] = field(default_factory=tuple)
    cwd: str = ""


__all__ = ["TaskCommandDTO"]
