from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle

from .indicators import enrich_bars, normalized_relative_curve
from .io_utils import CJK_FONT_FAMILIES
from .models import Alert, SectorResult, StockSignal
from .research_storage import ResearchStore
from .storage import StateStore

LOGGER = logging.getLogger(__name__)
plt.rcParams["font.sans-serif"] = list(CJK_FONT_FAMILIES)
plt.rcParams["axes.unicode_minus"] = False


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def _num(value: float | None, digits: int = 2) -> str:
    return "N/A" if value is None else f"{value:.{digits}f}"


def report_payload(
    report_date: date,
    market_sessions: Mapping[str, date],
    risk_environment: Mapping[str, str],
    risk_details: Mapping[str, dict[str, float]],
    signals: list[StockSignal],
    sectors: list[SectorResult],
    alerts: list[Alert],
    errors: Mapping[str, str],
    research: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return _json_safe(
        {
            "report_date": report_date,
            "generated_at": datetime.now(UTC),
            "disclaimer": "仅用于观察和信号研究，不构成投资建议，不自动下单。",
            "market_sessions": dict(market_sessions),
            "market_environment": dict(risk_environment),
            "risk_details": dict(risk_details),
            "signals": [signal.to_dict() for signal in signals],
            "sectors": [sector.to_dict() for sector in sectors],
            "alerts": [alert.to_dict() for alert in alerts],
            "data_errors": dict(errors),
            "research": dict(research or {}),
        }
    )


def write_json(payload: dict[str, Any], output_dir: Path, report_date: date) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"daily_report_{report_date:%Y%m%d}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    return path


def write_markdown(
    payload: dict[str, Any],
    output_dir: Path,
    report_date: date,
    chart_paths: Mapping[str, Path],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"daily_report_{report_date:%Y%m%d}.md"
    signals = payload["signals"]
    sectors = sorted(payload["sectors"], key=lambda item: item["score"], reverse=True)
    opportunities = [
        signal
        for signal in signals
        if signal["score"]["total"] >= 7
        and signal["signal_level"] != "FAILED"
        and signal["data_quality"] == "complete"
    ]
    opportunities.sort(
        key=lambda item: (
            item["score"]["total"],
            item["score"]["rejection"],
            item["relative_strength_turn"],
        ),
        reverse=True,
    )
    lines = [
        "# 每日底部狩猎报告",
        "",
        f"日期：{report_date.isoformat()}",
        "",
        "用途：只产生观察/交易框架信号，不自动下单，不构成投资建议。",
        "",
        "## 市场环境",
        "",
    ]
    for market, environment in payload["market_environment"].items():
        session = payload["market_sessions"].get(market, "N/A")
        lines.append(f"- {market}（行情日 {session}）：{environment}")
    lines += ["", "## 今日最高优先级机会", ""]
    if not opportunities:
        valid = [item for item in signals if item["signal_level"] != "FAILED"]
        highest = max(valid, key=lambda item: item["score"]["total"], default=None)
        lines.append("今日没有高质量反弹底部机会。")
        lines.append("")
        if highest:
            lines.append(
                f"最高分：{highest['name']}（{highest['symbol']}）"
                f" {highest['score']['total']}/{highest['score']['available_max']}"
            )
            lines.append("")
        lines.append("建议继续等待。")
    for rank, signal in enumerate(opportunities, 1):
        score = signal["score"]
        state = signal["state"]
        stage = signal["entry_stage"] or "仅观察"
        lines += [
            f"### {rank}. {signal['name']}（{signal['symbol']}）",
            "",
            (
                f"Score：{score['total']}/{score['available_max']}（基本面 N/A，满分尚不完整）"
                if score["fundamental"] is None
                else f"Score：{score['total']}/10"
            ),
            "",
            f"状态：{state}",
            "",
            f"信号：{stage}；等级 {signal['signal_level']}",
            "",
            "分项："
            f"超跌 {score['oversold']}/2、恐慌 {score['capitulation']}/2、"
            f"拒绝创新低 {score['rejection']}/2、宽度 {score['breadth']}/1、"
            f"基本面 {score['fundamental'] if score['fundamental'] is not None else 'N/A'}/2、"
            f"时间 {score['timing']}/1。",
            "",
            "原因：",
            "",
        ]
        lines.extend(f"- {reason}" for reason in signal["reasons"])
        lines += [
            "",
            "相对强弱："
            + ("已出现拐点。" if signal["relative_strength_turn"] else "尚未确认拐点。"),
            "",
            "风险：",
            "",
        ]
        lines.extend(f"- {risk}" for risk in signal["risks"])
        if signal["symbol"] in chart_paths:
            relative = chart_paths[signal["symbol"]].relative_to(output_dir)
            lines += ["", f"![{signal['symbol']} 底部结构图]({relative.as_posix()})"]
        lines.append("")
    lines += ["## 今日最值得观察的反弹板块", ""]
    if sectors:
        lines += ["| 排名 | 板块 | 市场 | Sector Bottom Score | 宽度/覆盖率 |", "|---:|---|---|---:|---:|"]
        for rank, sector in enumerate(sectors, 1):
            breadth = sector["breadth"]
            lines.append(
                f"| {rank} | {sector['sector_name']} | {sector['market']} | "
                f"{sector['score']}/100 | {breadth['up_ratio']:.0%}/{breadth['coverage']:.0%} |"
            )
        lines += ["", "反转领先顺序：", ""]
        for sector in sectors:
            names = " → ".join(sector["leader_ranking"][:5]) or "数据不足"
            lines.append(f"- {sector['sector_name']}（{sector['market']}）：{names}")
    if payload["alerts"]:
        lines += ["", "## 高级别提醒（已去重）", ""]
        lines.extend(f"- [{item['type']}] {item['message']}" for item in payload["alerts"])
    research = payload.get("research") or {}
    research_assets = research.get("assets") or {}
    macro_items = research.get("macro") or []
    if research_assets or macro_items:
        lines += ["", "## 研究数据摘要", ""]
        for symbol, item in research_assets.items():
            period = item.get("latest_financial_period") or "N/A"
            lines.append(f"### {symbol}（最新财务期 {period}）")
            lines.append("")
            for research_item in item.get("latest_items") or []:
                tier = research_item.get("tier") or "unknown"
                title = research_item.get("title") or "未命名内容"
                source = research_item.get("source") or "未知来源"
                url = research_item.get("url") or ""
                linked_title = f"[{title}]({url})" if url else title
                lines.append(f"- [{tier}] {linked_title} · {source}")
            lines.append("")
        if macro_items:
            lines += ["宏观环境最新观测：", ""]
            for item in macro_items[:12]:
                lines.append(
                    f"- {item.get('dimension', '其他')} / {item.get('name', item.get('series_id'))}："
                    f"{item.get('value')} {item.get('unit', '')}（{item.get('observation_date', '--')}）"
                )
    lines += ["", "## 数据质量", ""]
    if payload["data_errors"]:
        lines.append("以下证券数据不完整，未生成其交易信号：")
        lines.append("")
        lines.extend(f"- {symbol}：{message}" for symbol, message in payload["data_errors"].items())
    else:
        lines.append("本次入选信号所需行情完整。")
    if research_assets:
        fundamental_note = (
            "研究中心已缓存部分财报和公告；社区观点不参与基本面评分。"
            "评分仍为 N/A 的标的需人工核对原始披露。"
        )
    else:
        fundamental_note = (
            "基本面数据不足，需要人工确认。基本面为 N/A 的标的必须人工核查"
            "财报、业绩指引、监管和重大事件；系统不会编造新闻。"
        )
    lines += ["", fundamental_note, ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_chart(
    signal: StockSignal,
    bars: pd.DataFrame,
    reference: pd.DataFrame | None,
    output_dir: Path,
    store: StateStore,
    lookback: int = 120,
) -> Path:
    enriched = bars if "rsi14" in bars.columns else enrich_bars(bars)
    enriched = enriched.loc[: pd.Timestamp(signal.date)].tail(lookback)
    if enriched.empty:
        raise ValueError(f"{signal.symbol} 没有可绘制行情")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{signal.symbol.replace('^', 'INDEX_')}_{signal.date:%Y%m%d}.png"
    fig, axes = plt.subplots(
        5,
        1,
        figsize=(13, 12),
        sharex=True,
        gridspec_kw={"height_ratios": [4, 1.3, 1.3, 1.3, 1.5]},
    )
    ax_price, ax_volume, ax_rsi, ax_atr, ax_relative = axes
    numeric_dates = mdates.date2num(enriched.index.to_pydatetime())
    for x, (_, row) in zip(numeric_dates, enriched.iterrows(), strict=True):
        color = "#d62728" if row["close"] >= row["open"] else "#2ca02c"
        ax_price.vlines(x, row["low"], row["high"], color=color, linewidth=0.8)
        lower = min(row["open"], row["close"])
        height = max(abs(row["close"] - row["open"]), row["close"] * 0.0005)
        ax_price.add_patch(Rectangle((x - 0.3, lower), 0.6, height, color=color, alpha=0.8))
    ax_price.plot(enriched.index, enriched["ma5"], label="MA5", linewidth=1)
    ax_price.plot(enriched.index, enriched["ma10"], label="MA10", linewidth=1)
    ax_price.plot(enriched.index, enriched["ma20"], label="MA20", linewidth=1.1)
    if signal.capitulation_low is not None:
        ax_price.axhline(
            signal.capitulation_low, color="#9467bd", linestyle="--", label="capitulation_low"
        )
    stage_colors = {
        "ENTRY_STAGE_1": "#ff7f0e",
        "ENTRY_STAGE_2": "#1f77b4",
        "ENTRY_STAGE_3": "#9467bd",
    }
    for stage_date, stage in store.stage_history(signal.symbol, signal.date):
        stamp = pd.Timestamp(stage_date)
        if stamp in enriched.index:
            ax_price.scatter(
                stamp,
                enriched.at[stamp, "low"] * 0.985,
                marker="^",
                s=60,
                color=stage_colors.get(stage, "black"),
                label=stage,
                zorder=5,
            )
    handles, labels = ax_price.get_legend_handles_labels()
    unique = dict(zip(labels, handles, strict=True))
    ax_price.legend(unique.values(), unique.keys(), loc="upper left", ncol=4, fontsize=8)
    ax_price.set_title(f"{signal.name} ({signal.symbol}) — {signal.date}")
    colors = np.where(enriched["close"] >= enriched["open"], "#d62728", "#2ca02c")
    ax_volume.bar(enriched.index, enriched["volume"], color=colors, alpha=0.65, label="Volume")
    ax_volume.plot(enriched.index, enriched["volume_ma20"], color="#1f77b4", label="Vol MA20")
    ax_volume.legend(loc="upper left", fontsize=8)
    ax_rsi.plot(enriched.index, enriched["rsi14"], color="#9467bd", label="RSI14")
    ax_rsi.axhline(30, linestyle="--", color="gray", linewidth=0.8)
    ax_rsi.axhline(70, linestyle="--", color="gray", linewidth=0.8)
    ax_rsi.set_ylim(0, 100)
    ax_rsi.legend(loc="upper left", fontsize=8)
    ax_atr.plot(enriched.index, enriched["atr14"], color="#ff7f0e", label="ATR14")
    ax_atr.legend(loc="upper left", fontsize=8)
    if reference is not None:
        relative = normalized_relative_curve(enriched, reference.loc[: pd.Timestamp(signal.date)]).tail(60)
        if not relative.empty:
            ax_relative.plot(relative.index, relative["stock"], label=signal.symbol)
            ax_relative.plot(relative.index, relative["reference"], label="Sector ETF")
            ax_relative.legend(loc="upper left", fontsize=8)
    ax_relative.set_ylabel("60d=100")
    ax_relative.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    for axis in axes:
        axis.grid(alpha=0.15)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def generate_reports(
    report_date: date,
    market_sessions: Mapping[str, date],
    risk_environment: Mapping[str, str],
    risk_details: Mapping[str, dict[str, float]],
    signals: list[StockSignal],
    sectors: list[SectorResult],
    alerts: list[Alert],
    errors: Mapping[str, str],
    bars: Mapping[str, pd.DataFrame],
    sector_references: Mapping[tuple[str, str], pd.DataFrame | None],
    output_dir: Path,
    store: StateStore,
    chart_score: int = 7,
    chart_lookback: int = 120,
) -> tuple[Path, Path]:
    chart_paths: dict[str, Path] = {}
    chart_dir = output_dir / "charts" / f"{report_date:%Y%m%d}"
    for signal in signals:
        if signal.score.total < chart_score or signal.data_quality != "complete":
            continue
        try:
            chart_paths[signal.symbol] = generate_chart(
                signal,
                bars[signal.symbol],
                sector_references.get((signal.sector_id, signal.market)),
                chart_dir,
                store,
                chart_lookback,
            )
        except Exception as exc:
            LOGGER.exception("生成 %s 图表失败: %s", signal.symbol, exc)
    payload = report_payload(
        report_date,
        market_sessions,
        risk_environment,
        risk_details,
        signals,
        sectors,
        alerts,
        errors,
        ResearchStore(store.path).report_summary(
            [signal.symbol for signal in signals if signal.score.total >= chart_score]
        ),
    )
    json_path = write_json(payload, output_dir, report_date)
    markdown_path = write_markdown(payload, output_dir, report_date, chart_paths)
    return markdown_path, json_path
