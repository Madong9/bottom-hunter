from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .breadth import calculate_breadth
from .config import AppConfig
from .data_provider import CsvFundamentalProvider, MarketDataProvider, fetch_many
from .indicators import enrich_bars
from .scanner import _parse_date, _provider
from .scoring import score_stock
from .trading_calendar import TradingCalendarService

LOGGER = logging.getLogger(__name__)
HORIZONS = (3, 5, 10, 20, 60)
SCORE_THRESHOLDS = (6, 7, 8, 9, 10)


@dataclass
class BacktestEvent:
    signal_date: str
    symbol: str
    market: str
    sector_id: str
    score: int
    available_max: int
    timing_group: str
    returns: dict[str, float | None]
    drawdowns: dict[str, float | None]


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
) -> tuple[Path, Path, Path]:
    if start_date > end_date:
        raise ValueError("start 日期不能晚于 end")
    config = AppConfig.load(config_dir)
    if config.configured_asset_count == 0:
        raise ValueError(
            "账号自选观察池为空；请先导入自选文件后再回测。"
        )
    raw_dir = Path(data_dir) if data_dir else config.project_dir / "data" / "raw"
    reports_dir = Path(output_dir) if output_dir else config.project_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    history_start = start_date - timedelta(days=400)
    forward_end = end_date + timedelta(days=120)
    active_provider = provider or _provider(config, raw_dir, offline)
    fetched, errors = fetch_many(
        active_provider, config.all_instruments(), history_start, forward_end, workers
    )
    for symbol, message in errors.items():
        LOGGER.warning("回测跳过 %s: %s", symbol, message)
    enriched = {
        symbol: enrich_bars(result.bars)
        for symbol, result in fetched.items()
        if result.quality == "complete" and len(result.bars) >= 65
    }
    calendar = TradingCalendarService(config.markets)
    fundamentals = CsvFundamentalProvider(config.project_dir / "data" / "fundamentals.csv")
    events: list[BacktestEvent] = []
    min_bars = int(config.defaults["min_history_bars"])
    # Signal production is chronological. Every call receives target-date slices;
    # forward bars are only touched afterwards by _forward_metrics.
    for sector_id in config.sectors:
        settings = config.sector_thresholds(sector_id)
        markets = sorted({asset.market for asset in config.sector_assets(sector_id)})
        for market in markets:
            assets = config.sector_assets(sector_id, market)
            asset_frames = {
                item.symbol: enriched[item.symbol]
                for item in assets
                if item.symbol in enriched
            }
            etf = next(
                (
                    item
                    for item in config.sector_etfs(sector_id, market)
                    if item.symbol in enriched
                ),
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
                    location = full_frame.index.get_loc(pd.Timestamp(target))
                    if not isinstance(location, (int, np.integer)):
                        continue
                    returns, drawdowns = _forward_metrics(full_frame, int(location))
                    events.append(
                        BacktestEvent(
                            signal_date=target.isoformat(),
                            symbol=instrument.symbol,
                            market=market,
                            sector_id=sector_id,
                            score=scored.score.total,
                            available_max=scored.score.available_max,
                            timing_group=_timing_group(timing),
                            returns=returns,
                            drawdowns=drawdowns,
                        )
                    )
    summary = summarize_events(events)
    stem = f"backtest_{start_date:%Y%m%d}_{end_date:%Y%m%d}"
    json_path = reports_dir / f"{stem}.json"
    csv_path = reports_dir / f"{stem}_events.csv"
    markdown_path = reports_dir / f"{stem}.md"
    payload = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "lookahead_policy": "评分只使用信号日及以前数据；未来收益在信号冻结后单独计算。",
        "events": [asdict(event) for event in events],
        "summary": summary,
        "data_errors": errors,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
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
        }
        row.update({f"return_{key}": value for key, value in event.returns.items()})
        row.update({f"drawdown_{key}": value for key, value in event.drawdowns.items()})
        flattened.append(row)
    pd.DataFrame(flattened).to_csv(csv_path, index=False)
    markdown_path.write_text(_summary_markdown(start_date, end_date, summary), encoding="utf-8")
    return markdown_path, json_path, csv_path


def summarize_events(events: list[BacktestEvent]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for threshold in SCORE_THRESHOLDS:
        threshold_key = f"score_gte_{threshold}"
        summary[threshold_key] = {}
        candidates = [event for event in events if event.score >= threshold]
        for group in ("all", "ordinary", "month_window", "quarter_window"):
            grouped = candidates if group == "all" else [
                event for event in candidates if event.timing_group == group
            ]
            summary[threshold_key][group] = {}
            for horizon in HORIZONS:
                key = f"{horizon}d"
                pairs = [
                    (event.returns[key], event.drawdowns[key])
                    for event in grouped
                    if event.returns[key] is not None
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
                }
    return summary


def _summary_markdown(start: date, end: date, summary: dict[str, Any]) -> str:
    lines = [
        "# 底部狩猎历史回测",
        "",
        f"区间：{start} 至 {end}",
        "",
        "评分按真实交易日顺序生成；未来收益只在信号冻结后计算。季度/月末效果不作预设。",
        "",
        "## 汇总（5日持有期）",
        "",
        "| 分数阈值 | 窗口 | 样本 | 胜率 | 平均收益 | 中位收益 | 最大回撤 | 盈亏比 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
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
                f"{fmt(item['median_return'], True)} | {fmt(item['max_drawdown'], True)} | "
                f"{fmt(item['profit_loss_ratio'])} |"
            )
    lines += [
        "",
        "完整的 3/5/10/20/60 日统计位于同名 JSON；逐事件明细位于 CSV。",
        "",
        "注意：重叠的逐日信号不是独立样本，结果未包含滑点、手续费、涨跌停和容量约束。",
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
