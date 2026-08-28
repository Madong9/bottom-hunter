"""Shared I/O helpers and constants used by multiple modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Public search token used by Eastmoney's web search endpoint.
EASTMONEY_SEARCH_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"

# CJK font preference shared by every matplotlib consumer (SC first).
CJK_FONT_FAMILIES = [
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Droid Sans Fallback",
    "DejaVu Sans",
]


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
