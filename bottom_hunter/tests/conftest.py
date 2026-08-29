from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def selloff_bars() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=82)
    close = np.linspace(105, 84, len(dates))
    frame = pd.DataFrame(index=dates)
    frame["close"] = close
    frame["open"] = close + 0.2
    frame["high"] = close + 0.8
    frame["low"] = close - 0.8
    frame["volume"] = 100.0
    # Strong panic exhaustion on the penultimate day, confirmation on the last.
    frame.iloc[-2, frame.columns.get_loc("open")] = 80.0
    frame.iloc[-2, frame.columns.get_loc("high")] = 85.0
    frame.iloc[-2, frame.columns.get_loc("low")] = 70.0
    frame.iloc[-2, frame.columns.get_loc("close")] = 84.0
    frame.iloc[-2, frame.columns.get_loc("volume")] = 300.0
    frame.iloc[-1, frame.columns.get_loc("open")] = 82.0
    frame.iloc[-1, frame.columns.get_loc("high")] = 88.0
    frame.iloc[-1, frame.columns.get_loc("low")] = 71.0
    frame.iloc[-1, frame.columns.get_loc("close")] = 87.0
    frame.iloc[-1, frame.columns.get_loc("volume")] = 130.0
    return frame.astype(float)
