from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .breadth import calculate_breadth
from .config import AppConfig
from .data_provider import (
    CsvFundamentalProvider,
    FallbackFundamentalProvider,
    MarketDataProvider,
    fetch_many,
)
from .indicators import enrich_bars
from .research import CachedResearchFundamentalProvider
from .research_storage import ResearchStore
from .scanner import _parse_date, _provider
from .scoring import score_stock
from .sector_scoring import assess_risk_environment
from .state_machine import decide_state
from .trading_calendar import TradingCalendarService

LOGGER = logging.getLogger(__name__)
HORIZONS = (3, 5, 10, 20, 60)
SCORE_THRESHOLDS = (5, 6, 7, 8, 9, 10)


@dataclass
class BacktestEvent:
    signal_date: str
    symbol: str
    market: str
    sector_id: str
    score: int
    available_max: int
    timing_group: str
    near_resistance: bool
    breakout: bool = False
    signal_level: str = ""
    state: str = ""
    entry_stage: str | None = None
    returns: dict[str, float | None] = field(default_factory=dict)
    drawdowns: dict[str, float | None] = field(default_factory=dict)
    benchmark_returns: dict[str, float | None] = field(default_factory=dict)
    excess_returns: dict[str, float | None] = field(default_factory=dict)
    trade_return: float | None = None
    trade_exit_reason: str | None = None
    trade_holding_days: int | None = None


def _forward_metrics(
    frame: pd.DataFrame, location: int, horizons: tuple[int, ...] = HORIZONS
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    entry = float(frame["close"].iloc[location])
    returns: dict[str, float | None] = {}
    drawdowns: dict[str, float | None] = {}
    for horizon in horizons:
        key = f"{horizon}d"
        if location + horizon >= len(frame):
            returns[key] = None
            drawdowns[key] = None
            continue
        future = frame.iloc[location + 1 : location + horizon + 1]
        returns[key] = float(frame["close"].iloc[location + horizon] / entry - 1)
        drawdowns[key] = float((future["low"] / entry - 1).min())
    return returns, drawdowns


def _execution_metrics(
    frame: pd.DataFrame,
    benchmark: pd.DataFrame,
    location: int,
    *,
    cost_bps: float,
    stop_loss: float,
    take_profit: float,
    max_holding_sessions: int,
    invalidation_level: float | None = None,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[
    dict[str, float | None],
    dict[str, float | None],
    dict[str, float | None],
    dict[str, float | None],
    float | None,
    str | None,
    int | None,
]:
    """Next-open execution, round-trip costs, benchmark excess and rule exit."""
    keys = [f"{horizon}d" for horizon in horizons]
    empty = {key: None for key in keys}
    if location + 1 >= len(frame):
        return empty.copy(), empty.copy(), empty.copy(), empty.copy(), None, None, None
    entry_row = frame.iloc[location + 1]
    entry = float(entry_row.get("open", entry_row["close"]))
    if entry <= 0:
        return empty.copy(), empty.copy(), empty.copy(), empty.copy(), None, None, None
    roundtrip_cost = max(0.0, cost_bps) / 10_000
    returns: dict[str, float | None] = {}
    drawdowns: dict[str, float | None] = {}
    benchmark_returns: dict[str, float | None] = {}
    excess_returns: dict[str, float | None] = {}
    signal_stamp = frame.index[location]
    benchmark_location = benchmark.index.get_indexer([signal_stamp], method="pad")[0]
    benchmark_entry = None
    if benchmark_location >= 0 and benchmark_location + 1 < len(benchmark):
        benchmark_row = benchmark.iloc[benchmark_location + 1]
        benchmark_entry = float(benchmark_row.get("open", benchmark_row["close"]))
    for horizon in horizons:
        key = f"{horizon}d"
        if location + horizon >= len(frame):
            returns[key] = drawdowns[key] = benchmark_returns[key] = excess_returns[key] = None
            continue
        future = frame.iloc[location + 1 : location + horizon + 1]
        net_return = float(frame["close"].iloc[location + horizon] / entry - 1 - roundtrip_cost)
        returns[key] = net_return
        drawdowns[key] = float((future["low"] / entry - 1).min() - roundtrip_cost)
        benchmark_return = None
        if benchmark_entry is not None and benchmark_entry > 0 and benchmark_location + horizon < len(benchmark):
            benchmark_return = float(benchmark["close"].iloc[benchmark_location + horizon] / benchmark_entry - 1)
        benchmark_returns[key] = benchmark_return
        excess_returns[key] = net_return - benchmark_return if benchmark_return is not None else None
    stop_price = entry * (1 - max(0.0, stop_loss))
    if invalidation_level is not None and 0 < invalidation_level < entry:
        stop_price = max(stop_price, invalidation_level)
    take_price = entry * (1 + max(0.0, take_profit))
    trade_return = None
    exit_reason = None
    holding_days = None
    last_location = min(len(frame) - 1, location + max(1, max_holding_sessions))
    for step, (_, row) in enumerate(frame.iloc[location + 1 : last_location + 1].iterrows(), 1):
        # If both levels trade in one daily bar, use the conservative stop-first assumption.
        if float(row["low"]) <= stop_price:
            trade_return = stop_price / entry - 1 - roundtrip_cost
            exit_reason, holding_days = "stop", step
            break
        if float(row["high"]) >= take_price:
            trade_return = take_price / entry - 1 - roundtrip_cost
            exit_reason, holding_days = "take_profit", step
            break
    if trade_return is None and last_location > location:
        trade_return = float(frame["close"].iloc[last_location] / entry - 1 - roundtrip_cost)
        exit_reason = "time"
        holding_days = last_location - location
    return (
        returns,
        drawdowns,
        benchmark_returns,
        excess_returns,
        trade_return,
        exit_reason,
        holding_days,
    )


def _timing_group(window) -> str:
    if window.quarter_end or window.quarter_start:
        return "quarter_window"
    if window.month_end or window.month_start:
        return "month_window"
    return "ordinary"


def run_backtest(
    start_date: date,
    end_date: date,
    config_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    offline: bool = False,
    workers: int = 8,
    provider: MarketDataProvider | None = None,
    cost_bps: float | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    max_holding_sessions: int | None = None,
    episode_reset_days: int | None = None,
    validation_folds: int | None = None,
) -> tuple[Path, Path, Path]:
    if start_date > end_date:
        raise ValueError("start 日期不能晚于 end")
    config = AppConfig.load(config_dir)
    backtest_settings = dict(config.defaults.get("backtest") or {})
    cost_bps = float(cost_bps if cost_bps is not None else backtest_settings.get("cost_bps", 20))
    stop_loss = float(stop_loss if stop_loss is not None else backtest_settings.get("stop_loss", 0.08))
    take_profit = float(take_profit if take_profit is not None else backtest_settings.get("take_profit", 0.12))
    max_holding_sessions = int(
        max_holding_sessions if max_holding_sessions is not None else backtest_settings.get("max_holding_sessions", 20)
    )
    episode_reset_days = int(
        episode_reset_days if episode_reset_days is not None else backtest_settings.get("episode_reset_days", 5)
    )
    validation_folds = int(
        validation_folds if validation_folds is not None else backtest_settings.get("walk_forward_folds", 4)
    )
    if config.configured_asset_count == 0:
        raise ValueError("账号自选观察池为空；请先导入自选文件后再回测。")
    raw_dir = Path(data_dir) if data_dir else config.project_dir / "data" / "raw"
    reports_dir = Path(output_dir) if output_dir else config.project_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    history_start = start_date - timedelta(days=400)
    forward_end = end_date + timedelta(days=120)
    active_provider = provider or _provider(config, raw_dir, offline)
    fetched, errors = fetch_many(active_provider, config.all_instruments(), history_start, forward_end, workers)
    for symbol, message in errors.items():
        LOGGER.warning("回测跳过 %s: %s", symbol, message)
    enriched = {
        symbol: enrich_bars(result.bars)
        for symbol, result in fetched.items()
        if result.quality == "complete" and len(result.bars) >= 65
    }
    calendar = TradingCalendarService(config.markets)
    fundamentals = FallbackFundamentalProvider(
        [
            CsvFundamentalProvider(config.project_dir / "data" / "fundamentals.csv"),
            CachedResearchFundamentalProvider(ResearchStore(config.project_dir / "state" / "signals.db")),
        ]
    )
    events: list[BacktestEvent] = []
    risk_cache: dict[tuple[str, date], str] = {}
    min_bars = int(config.defaults["min_history_bars"])
    total_jobs = sum(len({asset.market for asset in config.sector_assets(sector_id)}) for sector_id in config.sectors)
    completed_jobs = 0
    # Signal production is chronological. Every call receives target-date slices;
    # forward bars are only touched afterwards by _forward_metrics.
    for sector_id in config.sectors:
        settings = config.sector_thresholds(sector_id)
        markets = sorted({asset.market for asset in config.sector_assets(sector_id)})
        for market in markets:
            assets = config.sector_assets(sector_id, market)
            asset_frames = {item.symbol: enriched[item.symbol] for item in assets if item.symbol in enriched}
            etf = next(
                (item for item in config.sector_etfs(sector_id, market) if item.symbol in enriched),
                None,
            )
            etf_frame = enriched.get(etf.symbol) if etf else None
            market_reference = enriched.get(config.markets[market]["benchmark"])
            if market_reference is None:
                LOGGER.warning("回测跳过 %s/%s：市场基准缺失", sector_id, market)
                continue
            official_sessions = calendar.sessions_between(market, start_date, end_date)
            benchmark_dates = {stamp.date() for stamp in market_reference.index}
            all_dates = sorted(
                {
                    stamp.date()
                    for frame in asset_frames.values()
                    for stamp in frame.index
                    if start_date <= stamp.date() <= end_date
                    and stamp.date() in benchmark_dates
                    and (official_sessions is None or stamp.date() in official_sessions)
                }
            )
            for target in all_dates:
                point_in_time_frames = {
                    symbol: frame.loc[: pd.Timestamp(target)]
                    for symbol, frame in asset_frames.items()
                    if pd.Timestamp(target) in frame.index
                    and len(frame.loc[: pd.Timestamp(target)]) >= min_bars
                    and frame.at[pd.Timestamp(target), "volume"] > 0
                }
                if not point_in_time_frames:
                    continue
                point_etf = (
                    etf_frame.loc[: pd.Timestamp(target)]
                    if etf_frame is not None and pd.Timestamp(target) in etf_frame.index
                    else None
                )
                breadth = calculate_breadth(
                    sector_id,
                    market,
                    point_in_time_frames,
                    target,
                    len(assets),
                    settings["breadth"],
                    point_etf,
                )
                if breadth.coverage < float(settings["data"]["minimum_latest_coverage"]):
                    continue
                timing = calendar.timing_window(market, target, settings["timing"])
                point_market = (
                    market_reference.loc[: pd.Timestamp(target)]
                    if market_reference is not None and pd.Timestamp(target) in market_reference.index
                    else None
                )
                risk_key = (market, target)
                if risk_key not in risk_cache:
                    risk_assets = config.risk_instruments(market)
                    point_risk_frames = {
                        item.symbol: enriched[item.symbol].loc[: pd.Timestamp(target)]
                        for item in risk_assets
                        if item.symbol in enriched and pd.Timestamp(target) in enriched[item.symbol].index
                    }
                    risk_cache[risk_key] = assess_risk_environment(
                        point_risk_frames,
                        target,
                        {item.symbol for item in risk_assets if item.inverse},
                    )[0]
                configured_leaders = [item for item in assets if item.leader]
                available_leaders = [
                    point_in_time_frames[item.symbol].loc[pd.Timestamp(target)]
                    for item in configured_leaders
                    if item.symbol in point_in_time_frames
                ]
                if configured_leaders:
                    leaders_confirmed = bool(
                        len(available_leaders) / len(configured_leaders)
                        >= float(settings["data"]["minimum_latest_coverage"])
                        and sum(not bool(row["new_low_20"]) for row in available_leaders) / len(available_leaders)
                        >= 0.60
                    )
                else:
                    leaders_confirmed = bool(breadth.breadth_score == 1 or breadth.breadth_ready)
                for instrument in assets:
                    point_frame = point_in_time_frames.get(instrument.symbol)
                    full_frame = asset_frames.get(instrument.symbol)
                    if point_frame is None or full_frame is None:
                        continue
                    scored = score_stock(
                        point_frame,
                        target,
                        settings,
                        breadth,
                        fundamentals.get_fundamental_data(instrument, target),
                        timing,
                        point_etf,
                        point_market,
                    )
                    scored.metrics["is_leader"] = instrument.leader
                    decision = decide_state(
                        scored,
                        point_frame,
                        target,
                        breadth,
                        risk_cache[risk_key],
                        leaders_confirmed,
                    )
                    metrics = scored.metrics
                    near_resistance = bool(
                        metrics.get("resistance_level") is not None
                        and not metrics.get("resistance_breakout")
                        and (metrics.get("resistance_distance") or 1.0) <= 0.03
                    )
                    location = full_frame.index.get_loc(pd.Timestamp(target))
                    if not isinstance(location, (int, np.integer)):
                        continue
                    (
                        returns,
                        drawdowns,
                        benchmark_returns,
                        excess_returns,
                        trade_return,
                        exit_reason,
                        holding_days,
                    ) = _execution_metrics(
                        full_frame,
                        market_reference,
                        int(location),
                        cost_bps=cost_bps,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        max_holding_sessions=max_holding_sessions,
                        invalidation_level=(scored.capitulation.low if scored.capitulation else None),
                    )
                    events.append(
                        BacktestEvent(
                            signal_date=target.isoformat(),
                            symbol=instrument.symbol,
                            market=market,
                            sector_id=sector_id,
                            score=scored.score.total,
                            available_max=scored.score.available_max,
                            timing_group=_timing_group(timing),
                            near_resistance=near_resistance,
                            breakout=bool(metrics.get("breakout")),
                            signal_level=scored.signal_level.value,
                            state=decision.state.value,
                            entry_stage=(decision.entry_stage.value if decision.entry_stage else None),
                            returns=returns,
                            drawdowns=drawdowns,
                            benchmark_returns=benchmark_returns,
                            excess_returns=excess_returns,
                            trade_return=trade_return,
                            trade_exit_reason=exit_reason,
                            trade_holding_days=holding_days,
                        )
                    )
            completed_jobs += 1
            LOGGER.info(
                "回测进度 %d/%d：%s/%s，累计 %d 个逐日评分",
                completed_jobs,
                total_jobs,
                sector_id,
                market,
                len(events),
            )
    summary = summarize_events(
        events,
        episode_reset_days=max(1, episode_reset_days),
        validation_folds=max(2, validation_folds),
    )
    stem = f"backtest_{start_date:%Y%m%d}_{end_date:%Y%m%d}"
    json_path = reports_dir / f"{stem}.json"
    csv_path = reports_dir / f"{stem}_events.csv"
    markdown_path = reports_dir / f"{stem}.md"
    payload = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "lookahead_policy": "评分只使用信号日及以前数据；未来收益在信号冻结后单独计算。",
        "execution_policy": {
            "entry": "信号后的下一交易日开盘",
            "cost_bps_roundtrip": cost_bps,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "max_holding_sessions": max_holding_sessions,
            "episode_reset_days": episode_reset_days,
            "walk_forward_folds": validation_folds,
        },
        "events": [asdict(event) for event in events],
        "summary": summary,
        "data_errors": errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    flattened = []
    for event in events:
        row: dict[str, Any] = {
            "signal_date": event.signal_date,
            "symbol": event.symbol,
            "market": event.market,
            "sector_id": event.sector_id,
            "score": event.score,
            "available_max": event.available_max,
            "timing_group": event.timing_group,
            "near_resistance": int(event.near_resistance),
            "breakout": int(event.breakout),
            "signal_level": event.signal_level,
            "state": event.state,
            "entry_stage": event.entry_stage,
            "trade_return": event.trade_return,
            "trade_exit_reason": event.trade_exit_reason,
            "trade_holding_days": event.trade_holding_days,
        }
        row.update({f"return_{key}": value for key, value in event.returns.items()})
        row.update({f"drawdown_{key}": value for key, value in event.drawdowns.items()})
        row.update({f"benchmark_return_{key}": value for key, value in event.benchmark_returns.items()})
        row.update({f"excess_return_{key}": value for key, value in event.excess_returns.items()})
        flattened.append(row)
    pd.DataFrame(flattened).to_csv(csv_path, index=False)
    markdown_path.write_text(_summary_markdown(start_date, end_date, summary), encoding="utf-8")
    return markdown_path, json_path, csv_path


def _episode_events(events: list[BacktestEvent], threshold: int, reset_sessions: int) -> list[BacktestEvent]:
    """Keep one entry per score episode instead of correlated daily repeats."""
    selected: list[BacktestEvent] = []
    by_symbol: dict[str, list[BacktestEvent]] = {}
    for event in events:
        by_symbol.setdefault(event.symbol, []).append(event)
    for symbol_events in by_symbol.values():
        active = False
        inactive_sessions = reset_sessions
        for event in sorted(symbol_events, key=lambda item: item.signal_date):
            eligible = event.score >= threshold and event.state != "FAILED"
            if eligible:
                if not active and inactive_sessions >= reset_sessions:
                    selected.append(event)
                active = True
                inactive_sessions = 0
            else:
                inactive_sessions += 1
                if event.state == "FAILED" or inactive_sessions >= reset_sessions:
                    active = False
    return sorted(selected, key=lambda item: (item.signal_date, item.symbol))


def _walk_forward_stats(events: list[BacktestEvent], folds: int, horizon: str = "5d") -> list[dict[str, Any]]:
    dated = sorted({event.signal_date for event in events})
    if not dated:
        return []
    groups = [list(group) for group in np.array_split(dated, min(folds, len(dated))) if len(group)]
    results = []
    for index, dates in enumerate(groups, 1):
        date_set = set(dates)
        test_events = [event for event in events if event.signal_date in date_set]
        stats = _bucket_stats(test_events, horizon)
        stats.update(
            {
                "fold": index,
                "test_start": dates[0],
                "test_end": dates[-1],
            }
        )
        results.append(stats)
    return results


def summarize_events(
    events: list[BacktestEvent], episode_reset_days: int = 5, validation_folds: int = 4
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "methodology": {
            "event_deduplication": (
                f"同一标的连续达标视为一个信号事件；连续 {episode_reset_days} 个观察日不达标或结构失效后重置"
            ),
            "walk_forward_folds": validation_folds,
        }
    }
    for threshold in SCORE_THRESHOLDS:
        threshold_key = f"score_gte_{threshold}"
        summary[threshold_key] = {}
        raw_candidates = [event for event in events if event.score >= threshold]
        candidates = _episode_events(events, threshold, episode_reset_days)
        summary[threshold_key]["raw_sample_size"] = len(raw_candidates)
        summary[threshold_key]["episode_sample_size"] = len(candidates)
        for group in ("all", "ordinary", "month_window", "quarter_window"):
            grouped = candidates if group == "all" else [event for event in candidates if event.timing_group == group]
            summary[threshold_key][group] = {}
            for horizon in HORIZONS:
                key = f"{horizon}d"
                pairs = [
                    (event.returns[key], event.drawdowns[key]) for event in grouped if event.returns[key] is not None
                ]
                returns = np.asarray([pair[0] for pair in pairs], dtype=float)
                drawdowns = np.asarray([pair[1] for pair in pairs], dtype=float)
                gains = returns[returns > 0]
                losses = returns[returns < 0]
                profit_loss = (
                    float(gains.mean() / abs(losses.mean()))
                    if gains.size and losses.size and losses.mean() != 0
                    else None
                )
                summary[threshold_key][group][key] = {
                    "win_rate": float(np.mean(returns > 0)) if returns.size else None,
                    "average_return": float(returns.mean()) if returns.size else None,
                    "median_return": float(np.median(returns)) if returns.size else None,
                    "max_drawdown": float(drawdowns.min()) if drawdowns.size else None,
                    "profit_loss_ratio": profit_loss,
                    "sample_size": int(returns.size),
                    "average_excess_return": _mean_metric(grouped, "excess_returns", key),
                }
        summary[threshold_key]["markets"] = {
            market: {
                f"{horizon}d": _bucket_stats(
                    [event for event in candidates if event.market == market],
                    f"{horizon}d",
                )
                for horizon in HORIZONS
            }
            for market in sorted({event.market for event in candidates})
        }
        summary[threshold_key]["walk_forward"] = _walk_forward_stats(candidates, validation_folds)
        # Resistance-filter experiment: do signals pinned just under a
        # resistance level (≤3%) actually perform worse than the rest?
        capped = [event for event in candidates if event.near_resistance]
        free = [event for event in candidates if not event.near_resistance]
        summary[threshold_key]["resistance_experiment"] = {
            "near_resistance": _bucket_stats(capped, "5d"),
            "not_near": _bucket_stats(free, "5d"),
        }
    validated = []
    for threshold in SCORE_THRESHOLDS:
        item = summary[f"score_gte_{threshold}"]["all"]["5d"]
        folds = summary[f"score_gte_{threshold}"].get("walk_forward") or []
        usable_folds = [fold for fold in folds if fold.get("sample_size")]
        positive_folds = [
            fold
            for fold in usable_folds
            if (fold.get("average_return") or 0) > 0 and (fold.get("average_excess_return") or 0) > 0
        ]
        if (
            item["sample_size"] >= 20
            and (item.get("average_return") or 0) > 0
            and (item.get("average_excess_return") or 0) > 0
            and (item.get("win_rate") or 0) >= 0.50
            and usable_folds
            and len(positive_folds) / len(usable_folds) >= 0.50
        ):
            validated.append(threshold)
    summary["calibration"] = {
        "status": "validated" if validated else "no_validated_edge",
        "recommended_action_threshold": min(validated) if validated else None,
        "rule": "事件样本≥20、胜率≥50%、平均净收益和超额收益均为正，且至少半数时间分段同时为正",
        "scoring_change": "时间窗口退出总分；没有拒绝创新低触发时最高仅为观察。",
    }
    return summary


def _mean_metric(events: list[BacktestEvent], field_name: str, horizon: str) -> float | None:
    values = [
        getattr(event, field_name).get(horizon)
        for event in events
        if getattr(event, field_name).get(horizon) is not None
    ]
    return float(np.mean(values)) if values else None


def _bucket_stats(events: list[BacktestEvent], horizon: str) -> dict[str, Any]:
    pairs = [
        (event.returns[horizon], event.drawdowns[horizon]) for event in events if event.returns[horizon] is not None
    ]
    if not pairs:
        return {"sample_size": 0}
    returns = np.asarray([pair[0] for pair in pairs], dtype=float)
    drawdowns = np.asarray([pair[1] for pair in pairs], dtype=float)
    trade_returns = [event.trade_return for event in events if event.trade_return is not None]
    return {
        "sample_size": int(returns.size),
        "win_rate": float(np.mean(returns > 0)),
        "average_return": float(returns.mean()),
        "median_return": float(np.median(returns)),
        "max_drawdown": float(drawdowns.min()),
        "average_excess_return": _mean_metric(events, "excess_returns", horizon),
        "trade_average_return": float(np.mean(trade_returns)) if trade_returns else None,
        "trade_win_rate": (float(np.mean(np.asarray(trade_returns) > 0)) if trade_returns else None),
    }


def _summary_markdown(start: date, end: date, summary: dict[str, Any]) -> str:
    calibration = summary.get("calibration") or {}
    recommended = calibration.get("recommended_action_threshold")
    calibration_text = (
        f"通过验证的最低行动阈值：≥{recommended} 分。"
        if recommended is not None
        else "当前没有分数阈值通过行动级验证，信号应保持研究观察。"
    )
    lines = [
        "# 底部狩猎历史回测",
        "",
        f"区间：{start} 至 {end}",
        "",
        "评分按真实交易日顺序生成；下一交易日开盘成交，收益扣除双边成本。连续达标只计算一次信号事件。",
        "",
        f"校准结论：{calibration_text}",
        f"验证规则：{calibration.get('rule', '--')}",
        "",
        "## 汇总（5日持有期）",
        "",
        "| 分数阈值 | 窗口 | 事件样本 | 胜率 | 平均净收益 | 平均超额 | 中位收益 | 最大回撤 | 盈亏比 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "all": "全部",
        "ordinary": "普通交易日",
        "month_window": "月末/月初",
        "quarter_window": "季度末/季度初",
    }
    for threshold in SCORE_THRESHOLDS:
        for group, label in labels.items():
            item = summary[f"score_gte_{threshold}"][group]["5d"]

            def fmt(value, percent=False):
                if value is None:
                    return "N/A"
                return f"{value:.1%}" if percent else f"{value:.2f}"

            lines.append(
                f"| ≥{threshold} | {label} | {item['sample_size']} | "
                f"{fmt(item['win_rate'], True)} | {fmt(item['average_return'], True)} | "
                f"{fmt(item.get('average_excess_return'), True)} | "
                f"{fmt(item['median_return'], True)} | {fmt(item['max_drawdown'], True)} | "
                f"{fmt(item['profit_loss_ratio'])} |"
            )
    lines += [
        "",
        "## 分市场结果（5日持有期）",
        "",
        "| 分数阈值 | 市场 | 事件样本 | 胜率 | 平均净收益 | 平均超额 | 规则退出收益 |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for threshold in SCORE_THRESHOLDS:
        markets = summary[f"score_gte_{threshold}"].get("markets") or {}
        for market, values in markets.items():
            item = values["5d"]
            lines.append(
                f"| ≥{threshold} | {market} | {item.get('sample_size', 0)} | "
                f"{fmt(item.get('win_rate'), True)} | {fmt(item.get('average_return'), True)} | "
                f"{fmt(item.get('average_excess_return'), True)} | "
                f"{fmt(item.get('trade_average_return'), True)} |"
            )
    lines += [
        "",
        "## 压力位过滤实验（5日持有期）",
        "",
        "| 分数阈值 | 临近压力位(≤3%) | 样本 | 胜率 | 平均收益 | 非临近 | 样本 | 胜率 | 平均收益 |",
        "|---:|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for threshold in SCORE_THRESHOLDS:
        experiment = summary[f"score_gte_{threshold}"]["resistance_experiment"]
        capped = experiment["near_resistance"]
        free = experiment["not_near"]

        def _cell(stats: dict[str, Any]) -> str:
            if not stats.get("sample_size"):
                return "N/A"
            return f"{stats['win_rate']:.0%} / {stats['average_return']:+.2%}"

        lines.append(
            f"| ≥{threshold} | 是 | {capped.get('sample_size', 0)} | {_cell(capped)} | "
            f"| 否 | {free.get('sample_size', 0)} | {_cell(free)} |"
        )
    lines += [
        "",
        "## 滚动时间分段验证（5日持有期）",
        "",
        "| 分数阈值 | 分段 | 测试区间 | 事件样本 | 胜率 | 平均净收益 | 平均超额 |",
        "|---:|---:|---|---:|---:|---:|---:|",
    ]
    for threshold in SCORE_THRESHOLDS:
        for fold in summary[f"score_gte_{threshold}"].get("walk_forward") or []:
            lines.append(
                f"| ≥{threshold} | {fold['fold']} | {fold['test_start']} ~ {fold['test_end']} | "
                f"{fold.get('sample_size', 0)} | {fmt(fold.get('win_rate'), True)} | "
                f"{fmt(fold.get('average_return'), True)} | "
                f"{fmt(fold.get('average_excess_return'), True)} |"
            )
    lines += [
        "",
        "完整的 3/5/10/20/60 日统计位于同名 JSON；逐事件明细位于 CSV。",
        "",
        "注意：已按信号事件去重并计入配置成本，但日K无法还原盘中成交顺序；同日同时触及止损止盈时按止损优先。结果仍未模拟涨跌停和容量约束。",
        "",
    ]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="底部狩猎无未来函数历史回测")
    parser.add_argument("--start", required=True, type=_parse_date)
    parser.add_argument("--end", required=True, type=_parse_date)
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cost-bps", type=float, help="单次完整交易的手续费与滑点（基点）")
    parser.add_argument("--stop-loss", type=float, help="固定止损比例，例如 0.08")
    parser.add_argument("--take-profit", type=float, help="固定止盈比例，例如 0.12")
    parser.add_argument("--max-holding-sessions", type=int, help="规则退出最大持有交易日")
    parser.add_argument("--episode-reset-days", type=int, help="连续多少观察日不达标后视为新事件")
    parser.add_argument("--validation-folds", type=int, help="滚动时间分段数量")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        markdown, json_path, csv_path = run_backtest(
            args.start,
            args.end,
            args.config_dir,
            args.data_dir,
            args.output_dir,
            args.offline,
            max(1, args.workers),
            cost_bps=args.cost_bps,
            stop_loss=args.stop_loss,
            take_profit=args.take_profit,
            max_holding_sessions=args.max_holding_sessions,
            episode_reset_days=args.episode_reset_days,
            validation_folds=args.validation_folds,
        )
    except (FileNotFoundError, ValueError) as exc:
        LOGGER.error("无法开始回测：%s", exc)
        return 2
    LOGGER.info("回测报告: %s", markdown)
    LOGGER.info("回测 JSON: %s", json_path)
    LOGGER.info("逐事件 CSV: %s", csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
