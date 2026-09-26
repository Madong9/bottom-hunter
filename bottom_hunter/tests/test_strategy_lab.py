from __future__ import annotations

import numpy as np
import pandas as pd

from bottom_hunter.src.strategy_lab import run_strategy_research


def test_strategy_lab_runs_factor_ml_and_rl_on_chronological_bars() -> None:
    rng = np.random.default_rng(9)
    index = pd.bdate_range("2022-01-03", periods=320)
    bars = {}
    for ordinal in range(8):
        returns = 0.0004 + ordinal * 0.00003 + rng.normal(0, 0.012, len(index))
        close = 20 * np.cumprod(1 + returns)
        bars[f"TEST{ordinal}"] = pd.DataFrame(
            {
                "open": close * (1 - 0.002),
                "high": close * (1 + 0.01),
                "low": close * (1 - 0.01),
                "close": close,
                "volume": rng.integers(100_000, 300_000, len(index)),
            },
            index=index,
        )

    result = run_strategy_research(bars)

    assert result.asset_count == 8
    assert result.sample_count > 1000
    assert len(result.factors) == 5
    assert result.machine_learning["status"] == "完成"
    assert result.machine_learning["test_start"] > "2022-01-03"
    assert result.reinforcement_learning["status"] == "完成"
    assert result.reinforcement_learning["test_days"] > 0
    assert result.caveats
