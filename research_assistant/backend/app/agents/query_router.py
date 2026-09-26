import re

from app.agents.base import BaseAgent
from app.schemas.agents import QueryRouterInput, QueryRouterOutput
from app.schemas.common import Intent

ROUTE_CONFIG: dict[Intent, dict[str, object]] = {
    Intent.OVERVIEW: {
        "category": "公司分析",
        "keywords": (),
        "requirements": ["公司画像", "核心业务与行业", "经营概览", "关键关注事项"],
    },
    Intent.STOCK_COMPARISON: {
        "category": "同行比较",
        "keywords": ("比较", "对比", "同行", "竞品", "哪个", "区别", "差异", "vs"),
        "requirements": ["统一比较口径", "核心财务指标", "商业特点差异", "各自风险"],
    },
    Intent.FUNDAMENTAL_ANALYSIS: {
        "category": "财务分析",
        "keywords": ("财务", "基本面", "财报", "营收", "利润", "现金流", "毛利", "负债", "roe"),
        "requirements": ["营收与利润", "盈利质量", "现金流与负债", "财务趋势"],
    },
    Intent.VALUATION_ANALYSIS: {
        "category": "估值分析",
        "keywords": ("估值", "市盈率", "市净率", "pe", "pb", "贵不贵", "便宜", "估值水平"),
        "requirements": ["估值指标", "财务基础", "同行或历史参照", "估值敏感因素"],
    },
    Intent.RISK_ANALYSIS: {
        "category": "风险分析",
        "keywords": ("风险", "隐患", "利空", "风险点", "不确定性", "下行"),
        "requirements": ["经营风险", "财务风险", "行业与监管风险", "待验证事项"],
    },
    Intent.NEWS_IMPACT: {
        "category": "新闻解读",
        "keywords": ("新闻", "消息", "舆情", "事件", "公告", "发生了什么", "影响"),
        "requirements": ["事件事实", "来源与时效", "影响链路", "后续观察"],
    },
    Intent.BOTTOM_ANALYSIS: {
        "category": "底部分析",
        "keywords": ("底部分析", "底部结构", "底部信号", "反弹底部", "超跌反弹", "是否见底", "筑底", "抄底信号"),
        "requirements": ["超跌与恐慌释放证据", "拒绝新低及反转确认", "成交量与市场宽度", "失效条件与待验证事项"],
    },
}

# A specific task instruction should win over a generic company-analysis request.
ROUTE_PRIORITY = (
    Intent.BOTTOM_ANALYSIS,
    Intent.STOCK_COMPARISON,
    Intent.RISK_ANALYSIS,
    Intent.NEWS_IMPACT,
    Intent.VALUATION_ANALYSIS,
    Intent.FUNDAMENTAL_ANALYSIS,
)


class QueryRouterAgent(BaseAgent[QueryRouterInput, QueryRouterOutput]):
    """Classify a financial request before any research work is performed."""

    name = "query_router"

    def run(self, agent_input: QueryRouterInput) -> QueryRouterOutput:
        query = agent_input.query.strip()
        normalized = query.casefold()
        intent = Intent.OVERVIEW
        matched_signals: list[str] = []

        for candidate in ROUTE_PRIORITY:
            keywords = ROUTE_CONFIG[candidate]["keywords"]
            matches = [
                keyword
                for keyword in keywords
                if self._contains_keyword(normalized, str(keyword))
            ]
            if matches:
                intent = candidate
                matched_signals = matches
                break

        config = ROUTE_CONFIG[intent]
        if matched_signals:
            confidence = min(0.98, 0.88 + 0.03 * len(matched_signals))
            reason = f"识别到任务信号：{'、'.join(matched_signals)}"
        else:
            confidence = 0.72
            reason = "未发现更具体的专项指令，按公司综合分析处理"

        return QueryRouterOutput(
            intent=intent,
            category=str(config["category"]),
            confidence=confidence,
            reason=reason,
            matched_signals=matched_signals,
            output_requirements=list(config["requirements"]),
        )

    @staticmethod
    def _contains_keyword(query: str, keyword: str) -> bool:
        if keyword in {"pe", "pb", "roe", "vs"}:
            return bool(re.search(rf"(?<![a-z]){keyword}(?![a-z])", query))
        return keyword in query
