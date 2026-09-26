"""Sole backend boundary for building scanner and backtest commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .task_contracts import TaskCommandDTO


class TaskCommandAdapter:
    @staticmethod
    def _packaged_command(kind: str, name: str, arguments: list[str]) -> TaskCommandDTO:
        project_dir = Path(os.environ["BOTTOM_HUNTER_PROJECT_DIR"])
        config_dir = Path(os.environ.get("BOTTOM_HUNTER_CONFIG_DIR", project_dir / "config"))
        shared = [
            "--config-dir",
            str(config_dir),
            "--data-dir",
            str(project_dir / "data" / "raw"),
            "--output-dir",
            str(project_dir / "reports"),
        ]
        if kind == "scan":
            shared.extend(["--state-db", str(project_dir / "state" / "signals.db")])
        return TaskCommandDTO(
            kind=kind,
            name=name,
            program=sys.executable,
            arguments=(f"--internal-{kind}", *shared, *arguments),
            cwd=str(project_dir),
        )

    def build_scan(self, requested_date: str, offline: bool, workers: int) -> TaskCommandDTO:
        from bottom_hunter.src.gui_core import build_scan_command

        spec = build_scan_command(requested_date, offline, workers)
        if getattr(sys, "frozen", False):
            return self._packaged_command("scan", spec.name, spec.argv[2:])
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
        if getattr(sys, "frozen", False):
            return self._packaged_command("backtest", spec.name, spec.argv[2:])
        return TaskCommandDTO(
            kind="backtest",
            name=spec.name,
            program=str(spec.argv[0]),
            arguments=tuple(str(value) for value in spec.argv[1:]),
            cwd=str(spec.cwd),
        )


__all__ = ["TaskCommandAdapter"]
