"""Filesystem boundary for local-only factor and strategy experiments."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

BACKEND_DIR = Path(
    os.environ.get("BOTTOM_HUNTER_PROJECT_DIR", Path(__file__).resolve().parents[2])
).resolve()


def run_local_strategy_research(
    project_dir: str | Path | None = None,
    state_dir: str | Path | None = None,
    *,
    max_assets: int = 120,
) -> dict[str, Any]:
    """Read existing local daily-bar cache and return an experimental report."""
    root = Path(project_dir).resolve() if project_dir else BACKEND_DIR
    state = Path(state_dir).resolve() if state_dir else root / "state"
    summary_path = state / "watchlist_summary.json"
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("找不到自选快照；请先打开自选页或完成一次扫描。") from exc
    assets = payload.get("assets") if isinstance(payload, dict) else None
    if not isinstance(assets, list) or not assets:
        raise ValueError("当前自选为空，无法执行策略研究。")

    raw_dir = root / "data" / "raw"
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    missing = 0
    for asset in assets[: max(1, min(int(max_assets), 300))]:
        if not isinstance(asset, dict):
            continue
        symbol = str(asset.get("symbol") or "").strip()
        if not symbol:
            continue
        safe_symbol = symbol.replace("^", "INDEX_").replace("/", "_")
        path = next(
            (candidate for candidate in (raw_dir / f"{safe_symbol}.csv", raw_dir / f"{symbol}.csv") if candidate.is_file()),
            None,
        )
        if path is None:
            missing += 1
            continue
        try:
            bars_by_symbol[symbol] = pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            missing += 1
    if not bars_by_symbol:
        raise ValueError(f"自选行情缓存为空（{missing} 个标的无本地日K）；请先运行扫描或准备历史行情。")

    from bottom_hunter.src.strategy_lab import run_strategy_research

    result = run_strategy_research(bars_by_symbol).as_dict()
    result["missing_assets"] = missing
    result["universe_size"] = len(assets)
    return result
