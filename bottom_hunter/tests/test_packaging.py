from __future__ import annotations

import tomllib
from pathlib import Path


def test_longbridge_extra_is_restricted_to_compatible_python_versions() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    longbridge_dep = metadata["project"]["optional-dependencies"]["longbridge"]
    assert any("python_version < '3.13'" in item for item in longbridge_dep)
