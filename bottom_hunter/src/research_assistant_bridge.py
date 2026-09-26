from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .models import StockSignal

MAX_DAILY_ANALYSES = 3


def analyze_daily_bottom_signals(signals: list[StockSignal], report_date: str) -> list[dict[str, Any]]:
    """Run selected daily bottom signals through the embedded research assistant."""
    candidates = sorted(
        signals,
        key=lambda signal: (
            signal.state.value != "FAILED",
            signal.score.total,
            signal.score.rejection,
            signal.relative_strength_turn,
        ),
        reverse=True,
    )[:MAX_DAILY_ANALYSES]
    if not candidates:
        return [
            {
                "symbol": "",
                "name": "市场概览",
                "status": "skipped",
                "error": "本次扫描没有可用证券信号，无法进行公司级底部分析。",
            }
        ]

    backend_dir = Path(__file__).resolve().parents[2] / "research_assistant" / "backend"
    if not backend_dir.is_dir():
        raise RuntimeError(f"未找到投研助手后端目录：{backend_dir}")

    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    try:
        from dotenv import load_dotenv

        load_dotenv(backend_dir / ".env", override=False)
        from app.api.dependencies import get_research_service
        from app.core.config import get_settings
        from app.schemas.research import ResearchRequest
    except ImportError as exc:
        raise RuntimeError("投研助手运行依赖未安装，请安装 bottom-hunter[research-assistant]") from exc

    get_settings.cache_clear()
    get_research_service.cache_clear()
    service = get_research_service()
    outcomes: list[dict[str, Any]] = []
    for signal in candidates:
        query = _build_query(signal, report_date)
        task = service.create(ResearchRequest(query=query))
        if task.result is None:
            outcomes.append(
                {
                    "symbol": signal.symbol,
                    "name": signal.name,
                    "status": "failed",
                    "error": task.error or "投研助手未返回分析结果",
                }
            )
            continue
        result = task.result
        outcomes.append(
            {
                "symbol": signal.symbol,
                "name": signal.name,
                "status": "completed",
                "intent": result.routing.category if result.routing else "底部分析",
                "summary": result.analysis.summary,
                "analysis": [item.content for item in result.analysis.ai_analysis[:2]],
                "watch": result.analysis.future_watch[:3],
                "uncertainties": result.analysis.uncertainties[:2],
                "sources": [
                    {"name": source.name, "url": source.url}
                    for source in result.analysis.citations[:3]
                ],
            }
        )
    return outcomes


def format_daily_bottom_analysis(outcomes: list[dict[str, Any]]) -> str:
    if not outcomes:
        return ""
    lines = ["## 投研助手底部分析", ""]
    for item in outcomes:
        lines.append(f"### {item['name']}（{item['symbol']}）")
        if item.get("status") != "completed":
            lines.append(f"- 分析暂不可用：{item.get('error', '未知错误')}")
            lines.append("")
            continue
        lines.append(f"- {item['summary']}")
        lines.extend(f"- {text}" for text in item.get("analysis", []))
        if item.get("watch"):
            lines.append("- 后续观察：" + "；".join(item["watch"]))
        if item.get("uncertainties"):
            lines.append("- 不确定性：" + "；".join(item["uncertainties"]))
        for source in item.get("sources", []):
            name = source.get("name") or "资料来源"
            url = source.get("url")
            lines.append(f"- 来源：[{name}]({url})" if url else f"- 来源：{name}")
        lines.append("")
    lines.append("以上为基于可用公开数据的辅助研究内容，仅供观察，不构成投资建议。")
    return "\n".join(lines).strip()


def _build_query(signal: StockSignal, report_date: str) -> str:
    stage = signal.entry_stage.value if signal.entry_stage else "仅观察"
    reasons = "；".join(signal.reasons[:3]) or "无明确触发原因"
    risks = "；".join(signal.risks[:2]) or "未列出额外风险"
    support = signal.metrics.get("support_level")
    support_text = f"支撑位 {float(support):.4g}" if support is not None else "支撑位未确认"
    return (
        f"对{signal.name}（{signal.symbol}）进行底部分析。底部狩猎扫描日期{report_date}，"
        f"评分{signal.score.total}/{signal.score.available_max}，状态{signal.state.value}，阶段{stage}；"
        f"拒绝新低得分{signal.score.rejection}/2，相对强弱拐点{('已出现' if signal.relative_strength_turn else '未确认')}，"
        f"{support_text}。信号原因：{reasons}。风险：{risks}。"
        "请结合可用行情、财务和新闻证据，区分超跌修复与趋势反转，说明反转确认条件、失效条件和待验证事项；不得给出买卖建议。"
    )[:1000]
