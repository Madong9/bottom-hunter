from __future__ import annotations

import numpy as np
import pandas as pd

from bottom_hunter.src.indicators import atr, enrich_bars, rsi


def test_rsi_and_atr_handle_one_sided_series() -> None:
    index = pd.bdate_range("2024-01-01", periods=30)
    close = pd.Series(np.arange(1, 31, dtype=float), index=index)
    assert rsi(close).iloc[-1] == 100.0
    bars = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1},
        index=index,
    )
    assert atr(bars).iloc[-1] > 0


def test_indicators_do_not_change_when_future_is_appended(selloff_bars) -> None:
    cutoff = selloff_bars.index[-10]
    prefix = enrich_bars(selloff_bars.loc[:cutoff])
    full = enrich_bars(selloff_bars)
    columns = [
        "rsi14",
        "atr14",
        "volume_ratio",
        "new_low_20",
        "drawdown_60",
        "bullish_engulfing",
    ]
    pd.testing.assert_series_equal(prefix.loc[cutoff, columns], full.loc[cutoff, columns])


def test_volume_baseline_excludes_current_bar(selloff_bars) -> None:
    enriched = enrich_bars(selloff_bars)
    panic = enriched.iloc[-2]
    assert panic["volume_ma20"] == 100.0
    assert panic["volume_ratio"] == 3.0

