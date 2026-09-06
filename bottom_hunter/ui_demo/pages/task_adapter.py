"""Sole backend boundary for building scanner and backtest commands."""

from __future__ import annotations

from .task_contracts import TaskCommandDTO


class TaskCommandAdapter:
    def build_scan(self, requested_date: str, offline: bool, workers: int) -> TaskCommandDTO:
        from bottom_hunter.src.gui_core import build_scan_command

        spec = build_scan_command(requested_date, offline, workers)
        return TaskCommandDTO(
            kind="scan",
            name=spec.name,
            program=str(spec.argv[0]),
            arguments=tuple(str(value) for value in spec.argv[1:]),
            cwd=str(spec.cwd),
        )

    def build_backtest(self, start: str, end: str, offline: bool, workers: int) -> TaskCommandDTO:
        from bottom_hunter.src.gui_core import build_backtest_command

        spec = build_backtest_command(start, end, offline, workers)
        return TaskCommandDTO(
            kind="backtest",
            name=spec.name,
            program=str(spec.argv[0]),
            arguments=tuple(str(value) for value in spec.argv[1:]),
            cwd=str(spec.cwd),
        )


__all__ = ["TaskCommandAdapter"]
