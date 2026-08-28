from __future__ import annotations

import argparse
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .alerts import build_alerts
from .breadth import calculate_breadth
from .config import AppConfig
from .data_provider import (
    BinanceKlineProvider,
    CachedMarketDataProvider,
    CboeVixProvider,
    CircuitBreakerProvider,
    CompositeMarketDataProvider,
    CsvFundamentalProvider,
    EastmoneyProvider,
    LocalCsvProvider,
    LongbridgeProvider,
    MarketDataProvider,
    OkxCandleProvider,
    TencentProvider,
    YahooChartProvider,
    fetch_many,
)
from .indicators import enrich_bars
from .models import BottomState, DataResult, Instrument, SignalLevel, StockSignal
from .notify import load_notify_config, push
from .paper import record_stage_fills, update_valuations
from .report import generate_reports
from .research import CachedResearchFundamentalProvider
from .research_storage import ResearchStore
from .scoring import score_stock
from .sector_scoring import assess_risk_environment, calculate_sector_score
from .state_machine import decide_state
from .storage import StateStore
from .trading_calendar import TradingCalendarService
from .validate import update_outcomes

LOGGER = logging.getLogger(__name__)


@dataclass
class ScanOutput:
    report_date: date
    markdown_path: Path
    json_path: Path
    signals: list[StockSignal]
    errors: dict[str, str]


def _provider(config: AppConfig, data_dir: Path, offline: bool) -> MarketDataProvider:
    local = LocalCsvProvider(data_dir)
    if offline:
        return local
    timeout = int(config.defaults["data"]["request_timeout_seconds"])
    breaker_failures = int(config.defaults["data"].get("circuit_breaker_failures", 3))
    eastmoney_concurrency = int(config.defaults["data"].get("eastmoney_max_concurrency", 3))
    remote = CompositeMarketDataProvider(
        [
            CircuitBreakerProvider(BinanceKlineProvider(timeout=timeout), breaker_failures),
            CircuitBreakerProvider(OkxCandleProvider(timeout=timeout), breaker_failures),
            CircuitBreakerProvider(LongbridgeProvider(), breaker_failures),
            CircuitBreakerProvider(CboeVixProvider(timeout=timeout), breaker_failures),
            CircuitBreakerProvider(TencentProvider(timeout=timeout), breaker_failures),
            CircuitBreakerProvider(
                EastmoneyProvider(
                    timeout=timeout,
                    max_concurrency=eastmoney_concurrency,
                ),
                breaker_failures,
            ),
            CircuitBreakerProvider(YahooChartProvider(timeout=timeout), breaker_failures),
        ]
    )
    return CachedMarketDataProvider(local, remote)


def _select_market_sessions(
    config: AppConfig,
    calendar: TradingCalendarService,
    requested: date | None,
    fetched: Mapping[str, DataResult],
    errors: dict[str, str],
) -> dict[str, date]:
    sessions: dict[str, date] = {}
    for market, market_config in config.markets.items():
        cutoff, calendar_reliable = calendar.latest_completed_session(market, requested)
        benchmark = str(market_config["benchmark"])
        result = fetched.get(benchmark)
        if result is None or result.bars.empty:
            errors[f"market:{market}"] = f"市场基准 {benchmark} 缺失，跳过该市场"
            continue
        available = [stamp.date() for stamp in result.bars.index if stamp.date() <= cutoff]
        if not available:
            errors[f"market:{market}"] = f"市场基准 {benchmark} 在 {cutoff} 前无数据"
            continue
        actual = available[-1]
        if calendar_reliable and actual != cutoff:
            errors[f"market:{market}"] = (
                f"市场基准 {benchmark} 最新行情为 {actual}，预期完整交易日为 {cutoff}；"
                "为防止不完整数据，本市场不生成信号"
            )
            continue
        sessions[market] = actual
    return sessions


def _usable_frame(
    instrument: Instrument,
    result: DataResult | None,
    session: date,
    min_bars: int,
    errors: dict[str, str],
) -> pd.DataFrame | None:
    instrument_symbol = instrument.symbol
    if result is None:
        errors.setdefault(instrument_symbol, "行情获取失败")
        return None
    bars = result.bars.loc[: pd.Timestamp(session)]
    if result.quality != "complete":
        errors[instrument_symbol] = (
            f"数据质量为 {result.quality}（{'; '.join(result.warnings)}），不生成信号"
        )
        return None
    if pd.Timestamp(session) not in bars.index:
        errors[instrument_symbol] = f"{session} 无日K（可能停牌或数据缺失），不生成信号"
        return None
    if len(bars) < min_bars:
        errors[instrument_symbol] = f"历史日K仅 {len(bars)} 根，至少需要 {min_bars} 根"
        return None
    if not instrument.volume_optional and bars.at[pd.Timestamp(session), "volume"] <= 0:
        errors[instrument_symbol] = f"{session} 成交量为零（疑似停牌），不生成信号"
        return None
    return enrich_bars(bars)


def run_scan(
    requested_date: date | None = None,
    config_dir: str | Path | None = None,
    data_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    state_db: str | Path | None = None,
    offline: bool = False,
    workers: int = 8,
    provider: MarketDataProvider | None = None,
) -> ScanOutput:
    config = AppConfig.load(config_dir)
    if config.configured_asset_count == 0:
        raise ValueError(
            "账号自选观察池为空；请先在桌面端“账号与自选”中导入"
            "同花顺、币安或欧易自选文件。"
        )
    raw_dir = Path(data_dir) if data_dir else config.project_dir / "data" / "raw"
    reports_dir = Path(output_dir) if output_dir else config.project_dir / "reports"
    database = Path(state_db) if state_db else config.project_dir / "state" / "signals.db"
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    store = StateStore(database)
    calendar = TradingCalendarService(config.markets)
    # The filename follows the requested China-local run date; each market's actual
    # completed session is explicitly recorded inside the report.
    report_date = requested_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    run_id = store.start_run(report_date)
    errors: dict[str, str] = {}
    try:
        preliminary = {
            market: calendar.latest_completed_session(market, requested_date)[0]
            for market in config.markets
        }
        end = max(preliminary.values())
        history_days = int(config.defaults["history_days"])
        start = min(preliminary.values()) - timedelta(days=int(history_days * 1.65))
        active_provider = provider or _provider(config, raw_dir, offline)
        fetched, fetch_errors = fetch_many(
            active_provider, config.all_instruments(), start, end, workers=workers
        )
        errors.update(fetch_errors)
        market_sessions = _select_market_sessions(
            config, calendar, requested_date, fetched, errors
        )
        # Watchdog: one retry for markets whose benchmark data was stale/missing,
        # so a slow provider does not forfeit the whole day for that market.
        missing_markets = sorted(set(config.markets) - set(market_sessions))
        if missing_markets and not offline:
            retry_symbols = {
                item.symbol: item
                for market in missing_markets
                for item in config.risk_instruments(market)
            }
            retry_symbols.update(
                {
                    item.symbol: item
                    for market in missing_markets
                    for item in config.market_instruments(market)
                }
            )
            if retry_symbols:
                LOGGER.warning("数据看门狗：重试 %d 个缺失市场的标的", len(retry_symbols))
                retry_fetched, retry_errors = fetch_many(
                    active_provider,
                    list(retry_symbols.values()),
                    start,
                    end,
                    workers=workers,
                )
                for symbol, message in retry_errors.items():
                    errors.setdefault(symbol, message)
                fetched.update(retry_fetched)
                for market in missing_markets:
                    errors.pop(f"market:{market}", None)
                market_sessions = _select_market_sessions(
                    config, calendar, requested_date, fetched, errors
                )
        min_bars = int(config.defaults["min_history_bars"])
        enriched: dict[str, pd.DataFrame] = {}
        for instrument in config.all_instruments():
            session = market_sessions.get(instrument.market)
            if session is None:
                continue
            frame = _usable_frame(
                instrument, fetched.get(instrument.symbol), session, min_bars, errors
            )
            if frame is not None:
                enriched[instrument.symbol] = frame
        risk_environment: dict[str, str] = {}
        risk_details: dict[str, dict[str, float]] = {}
        for market, session in market_sessions.items():
            risk_assets = config.risk_instruments(market)
            risk_frames = {
                item.symbol: enriched[item.symbol]
                for item in risk_assets
                if item.symbol in enriched
            }
            environment, details = assess_risk_environment(
                risk_frames,
                session,
                {item.symbol for item in risk_assets if item.inverse},
            )
            risk_environment[market] = environment
            risk_details[market] = details
        fundamental_provider = CsvFundamentalProvider(
            config.project_dir / "data" / "fundamentals.csv"
        )
        cached_fundamental_provider = CachedResearchFundamentalProvider(
            ResearchStore(database)
        )
        signals: list[StockSignal] = []
        sectors = []
        sector_references: dict[tuple[str, str], pd.DataFrame | None] = {}
        for sector_id, sector in config.sectors.items():
            markets = sorted({item.market for item in config.sector_assets(sector_id)})
            for market in markets:
                if market not in market_sessions:
                    continue
                session = market_sessions[market]
                assets = config.sector_assets(sector_id, market)
                asset_frames = {
                    item.symbol: enriched[item.symbol]
                    for item in assets
                    if item.symbol in enriched
                }
                etfs = config.sector_etfs(sector_id, market)
                etf = next((item for item in etfs if item.symbol in enriched), None)
                etf_frame = enriched.get(etf.symbol) if etf else None
                sector_references[(sector_id, market)] = etf_frame
                settings = config.sector_thresholds(sector_id)
                breadth = calculate_breadth(
                    sector_id,
                    market,
                    asset_frames,
                    session,
                    len(assets),
                    settings["breadth"],
                    etf_frame,
                )
                minimum_coverage = float(settings["data"]["minimum_latest_coverage"])
                if breadth.coverage < minimum_coverage:
                    errors[f"sector:{sector_id}:{market}"] = (
                        f"板块最新行情覆盖率 {breadth.coverage:.0%} 低于 "
                        f"{minimum_coverage:.0%}，不生成该板块交易信号"
                    )
                    sector_result = calculate_sector_score(
                        sector_id,
                        str(sector["name"]),
                        market,
                        session,
                        asset_frames,
                        breadth,
                        [],
                        etf_frame,
                        {item.symbol for item in assets if item.leader},
                    )
                    sectors.append(sector_result)
                    continue
                sector_signals: list[StockSignal] = []
                market_benchmark = enriched.get(config.markets[market]["benchmark"])
                timing = calendar.timing_window(market, session, settings["timing"])
                configured_leaders = [item for item in assets if item.leader]
                available_leaders = [
                    asset_frames[item.symbol].loc[pd.Timestamp(session)]
                    for item in configured_leaders
                    if item.symbol in asset_frames
                ]
                if configured_leaders:
                    leaders_confirmed = bool(
                        len(available_leaders) / len(configured_leaders) >= minimum_coverage
                        and sum(not bool(row["new_low_20"]) for row in available_leaders)
                        / len(available_leaders)
                        >= 0.60
                    )
                else:
                    # 动态自选未配置龙头股时，以板块宽度确认代替龙头确认，
                    # 否则 ENTRY_STAGE_3 对动态板块永远不可达。
                    leaders_confirmed = bool(breadth.breadth_score == 1 or breadth.breadth_ready)
                for instrument in assets:
                    frame = asset_frames.get(instrument.symbol)
                    result = fetched.get(instrument.symbol)
                    if frame is None or result is None:
                        continue
                    fundamental = fundamental_provider.get_fundamental_data(instrument, session)
                    if fundamental.score is None:
                        fundamental = cached_fundamental_provider.get_fundamental_data(
                            instrument, session
                        )
                    scored = score_stock(
                        frame,
                        session,
                        settings,
                        breadth,
                        fundamental,
                        timing,
                        etf_frame,
                        market_benchmark,
                    )
                    scored.metrics["is_leader"] = instrument.leader
                    decision = decide_state(
                        scored,
                        frame,
                        session,
                        breadth,
                        risk_environment.get(market, "Neutral"),
                        leaders_confirmed,
                    )
                    if decision.allocation_hint:
                        scored.reasons.append(decision.allocation_hint)
                    signal = StockSignal(
                        date=session,
                        symbol=instrument.symbol,
                        name=instrument.name,
                        market=market,
                        sector_id=sector_id,
                        sector_name=str(sector["name"]),
                        score=scored.score,
                        signal_level=(
                            SignalLevel.FAILED
                            if decision.state == BottomState.FAILED
                            else scored.signal_level
                        ),
                        state=decision.state,
                        entry_stage=decision.entry_stage,
                        metrics=scored.metrics,
                        reasons=scored.reasons,
                        risks=scored.risks,
                        relative_strength_turn=scored.relative_strength_turn,
                        capitulation_date=(
                            scored.capitulation.event_date if scored.capitulation else None
                        ),
                        capitulation_low=(scored.capitulation.low if scored.capitulation else None),
                        data_quality=result.quality,
                        provider=result.provider,
                        data_timestamp=result.data_timestamp,
                        breakout=bool(scored.breakout),
                    )
                    sector_signals.append(signal)
                    signals.append(signal)
                sector_result = calculate_sector_score(
                    sector_id,
                    str(sector["name"]),
                    market,
                    session,
                    asset_frames,
                    breadth,
                    sector_signals,
                    etf_frame,
                    {item.symbol for item in assets if item.leader},
                )
                sectors.append(sector_result)
        alerts = build_alerts(signals, sectors, store)
        store.save_signals(signals)
        store.save_sectors(sectors)
        new_alerts = store.save_alerts(alerts)
        update_outcomes(store, enriched, max(market_sessions.values()))
        record_stage_fills(store, signals, enriched, max(market_sessions.values()))
        paper_summary = update_valuations(store, enriched, max(market_sessions.values()))
        if paper_summary.get("positions"):
            LOGGER.info(
                "模拟组合：%d 个持仓，加权收益 %.2f%%",
                paper_summary["positions"],
                paper_summary["weighted_return"] * 100,
            )
        notify_errors = push(alerts, signals, load_notify_config())
        if notify_errors:
            errors["notify"] = "; ".join(notify_errors)
        markdown_path, json_path = generate_reports(
            report_date,
            market_sessions,
            risk_environment,
            risk_details,
            signals,
            sectors,
            new_alerts,
            errors,
            enriched,
            sector_references,
            reports_dir,
            store,
            int(config.defaults["report"]["chart_score"]),
            int(config.defaults["report"]["chart_lookback"]),
        )
        store.finish_run(run_id, "partial" if errors else "success", errors)
        return ScanOutput(report_date, markdown_path, json_path, signals, errors)
    except KeyboardInterrupt:
        store.finish_run(run_id, "aborted", {"fatal": "用户中断", **errors})
        raise
    except Exception as exc:
        store.finish_run(run_id, "failed", {"fatal": str(exc), **errors})
        raise


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期格式必须为 YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="每日板块超跌反弹狩猎系统")
    parser.add_argument("--date", type=_parse_date, help="历史扫描日期 YYYY-MM-DD")
    parser.add_argument("--config-dir", type=Path, help="自定义配置目录")
    parser.add_argument("--data-dir", type=Path, help="本地日K CSV/缓存目录")
    parser.add_argument("--output-dir", type=Path, help="报告输出目录")
    parser.add_argument("--state-db", type=Path, help="SQLite 状态数据库路径")
    parser.add_argument("--offline", action="store_true", help="只读本地 CSV，不访问网络")
    parser.add_argument("--workers", type=int, default=8, help="并发取数线程数")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出详细日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        output = run_scan(
            requested_date=args.date,
            config_dir=args.config_dir,
            data_dir=args.data_dir,
            output_dir=args.output_dir,
            state_db=args.state_db,
            offline=args.offline,
            workers=max(1, args.workers),
        )
    except KeyboardInterrupt:
        LOGGER.warning("扫描已取消。")
        return 130
    except (FileNotFoundError, ValueError) as exc:
        LOGGER.error("无法开始扫描：%s", exc)
        return 2
    LOGGER.info("Markdown 报告: %s", output.markdown_path)
    LOGGER.info("JSON 报告: %s", output.json_path)
    if output.errors:
        LOGGER.warning("有 %d 项数据质量问题，详见报告", len(output.errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
