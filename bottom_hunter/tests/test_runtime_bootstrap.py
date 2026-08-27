from __future__ import annotations

from pathlib import Path

from bottom_hunter.src.runtime_bootstrap import (
    RUNTIME_READY_ENV,
    prepared_environment,
)


def test_conda_backed_venv_gets_its_own_runtime_libraries(tmp_path: Path) -> None:
    venv = tmp_path / ".venv"
    executable = venv / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.touch()
    (venv / "pyvenv.cfg").write_text(
        "home = /opt/conda/envs/market/bin\nversion = 3.11.15\n",
        encoding="utf-8",
    )

    environment = prepared_environment(
        executable,
        {
            "LD_LIBRARY_PATH": "/opt/ros/lib:/usr/lib",
            "PYTHONPATH": "/opt/ros/python3.10",
            "CONDA_PREFIX": "/opt/conda",
        },
    )

    paths = environment["LD_LIBRARY_PATH"].split(":")
    assert paths[0] == "/opt/conda/envs/market/lib"
    assert paths[1] == "/opt/conda/lib"
    assert "PYTHONPATH" not in environment
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment[RUNTIME_READY_ENV] == "1"
