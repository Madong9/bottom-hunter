from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

RUNTIME_READY_ENV = "BOTTOM_HUNTER_RUNTIME_READY"


def prepared_environment(
    executable: str | Path,
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build an isolated environment for a Conda-backed project venv."""

    environment = dict(source if source is not None else os.environ)
    executable = Path(executable).resolve()
    configuration = executable.parent.parent / "pyvenv.cfg"
    runtime_prefix: Path | None = None
    try:
        for line in configuration.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "home":
                runtime_prefix = Path(value.strip()).resolve().parent
                break
    except OSError:
        pass
    if runtime_prefix is None and (Path(sys.prefix) / "lib").is_dir():
        runtime_prefix = Path(sys.prefix)
    library_paths: list[str] = []
    if runtime_prefix is not None:
        library_paths.append(str(runtime_prefix / "lib"))
        if runtime_prefix.parent.name == "envs":
            library_paths.append(str(runtime_prefix.parent.parent / "lib"))
    conda_prefix = Path(environment.get("CONDA_PREFIX", ""))
    if conda_prefix.is_dir():
        library_paths.append(str(conda_prefix / "lib"))
    existing = environment.get("LD_LIBRARY_PATH", "")
    library_paths.extend(item for item in existing.split(os.pathsep) if item)
    if library_paths:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(dict.fromkeys(library_paths))
    # ROS/global Python paths can inject modules from another Python ABI.
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment[RUNTIME_READY_ENV] = "1"
    return environment


def reexec_with_runtime(
    executable: str | Path | None = None,
    arguments: Sequence[str] | None = None,
) -> None:
    if os.environ.get(RUNTIME_READY_ENV) == "1":
        return
    target = Path(executable or sys.executable).resolve()
    argv = list(arguments or [str(target), *sys.argv])
    os.execve(str(target), argv, prepared_environment(target))
