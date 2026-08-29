"""Signal validation loop: backfill real forward returns for past signals.

Every scan writes the realized 3/5/10/20-day returns of historical
signals using the price history it already fetched (bars end at the
latest completed session, so each horizon is only recorded when enough
*completed* sessions exist after the signal date — no lookahead).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date

import pandas as pd

from .storage import OUTCOME_HORIZONS, StateStore

LOGGER = logging.getLogger(__name__)


def update_outcomes(
    store: StateStore,
    enriched: Mapping[str, pd.DataFrame],
    target: date,
    max_age_days: int = 30,
) -> int:
    """Record forward returns for pending signals using bars through `target`.

    Bars indexed by session include the target day itself; a horizon h is
    evaluated only when the session at signal_date + h trading bars exists
    and is strictly <= target, i.e. fully in the past.
    """
    pending = store.pending_signals(target, max_age_days)
    if not pending:
        return 0
    outcomes: list[tuple[str, str, str, int, float | None, float | None]] = []
    for row in pending:
        symbol = row["symbol"]
        frame = enriched.get(symbol)
        if frame is None or frame.empty:
            continue
        signal_date = date.fromisoformat(row["signal_date"])
        stamp = pd.Timestamp(signal_date)
        if stamp not in frame.index:
            continue
        location = frame.index.get_loc(stamp)
        if isinstance(location, slice) or not isinstance(location, int):
            location = frame.index.get_indexer([stamp], method="nearest")[0]
        entry = float(frame["close"].iloc[location])
        if entry <= 0:
            continue
        for horizon in OUTCOME_HORIZONS:
            if location + horizon >= len(frame):
                # Not enough completed sessions yet.
                continue
            future = frame.iloc[location + 1 : location + horizon + 1]
            forward_return = float(frame["close"].iloc[location + horizon] / entry - 1)
            drawdown = float((future["low"] / entry - 1).min())
            outcomes.append(
                (
                    row["signal_date"],
                    symbol,
                    row["sector_id"],
                    horizon,
                    forward_return,
                    drawdown,
                )
            )
    written = store.save_outcomes(outcomes)
    if written:
        LOGGER.info("信号验证回填 %d 条结果", written)
    return written


def validation_headline(store: StateStore) -> dict:
    """Rolling win-rate used by the report and the GUI overview card."""
    summary_30 = store.outcome_summary(window_days=30, horizon=5)
    summary_90 = store.outcome_summary(window_days=90, horizon=5)
    return {"days_30": summary_30, "days_90": summary_90}


def outcomes_age_notice(store: StateStore, today: date | None = None) -> str | None:
    """Warn when outcome backfill has not run recently (watchdog for the loop)."""
    today = today or date.today()
    with store.connect() as connection:
        row = connection.execute("SELECT MAX(evaluated_at) AS latest FROM signal_outcomes").fetchone()
    latest = row["latest"] if row else None
    if not latest:
        return "信号验证闭环尚无任何回填结果；首次扫描后约 5 个交易日开始产出胜率。"
    latest_date = str(latest)[:10]
    if (today - date.fromisoformat(latest_date)).days > 7:
        return f"信号验证已 {latest_date} 未回填，胜率统计可能过期。"
    return None
