"""Convenience entry point for the Bottom Hunter desktop console."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from bottom_hunter.src.gui_launcher import main
from bottom_hunter.src.runtime_bootstrap import (
    prepared_environment,
    reexec_with_runtime,
)


def _activate_project_venv() -> None:
    """Re-exec with the compatible project interpreter when it is available."""

    if os.environ.get("BOTTOM_HUNTER_NO_VENV") == "1":
        return
    project_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if not project_python.is_file():
        return
    try:
        current = Path(sys.executable).resolve()
        target = project_python.resolve()
    except OSError:
        return
    if current == target:
        reexec_with_runtime()
        return
    arguments = [str(target), str(Path(__file__).resolve()), *sys.argv[1:]]
    os.execve(str(target), arguments, prepared_environment(target))


if __name__ == "__main__":
    _activate_project_venv()


if __name__ == "__main__":
    raise SystemExit(main())
