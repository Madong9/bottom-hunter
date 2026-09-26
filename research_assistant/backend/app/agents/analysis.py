from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.llm.base import AnalysisEnhancer
from app.schemas.agents import (
    AIAnalysisItem,
    AnalysisInput,
    AnalysisOutput,
    AnalysisSection,
    CompanyComparison,
    CompanyPortrait,
    ConfirmedFact,
    FollowUpQuestion,
    FutureScenario,
    InvestorFocusGuide,
    TermExplanation,
)
from app.schemas.common import EvidenceBalance, Intent

COMPARISON_NOTICE = (
    "即使行业分类相同，不同公司的估值、资本结构、成长阶段也不可直接等同，"
    "因此本报告不根据单一指标给出买卖结论。"
)

REPORT_CONFIG = {
    Intent.OVERVIEW: ("公司分析报告", "公司画像、核心业务、经营概览和关键关注事项"),
    Intent.STOCK_COMPARISON: ("同行比较报告", "统一口径比较、商业差异和各自风险"),
    Intent.FUNDAMENTAL_ANALYSIS: (
        "财务分析报告",
        "营收利润、盈利质量、现金流和资产负债结构",
    ),
    Intent.VALUATION_ANALYSIS: (
        "估值分析报告",
        "估值指标、财务基础、参照口径和敏感因素",
    ),
    Intent.RISK_ANALYSIS: ("风险分析报告", "经营、财务、行业监管风险和待验证事项"),
    Intent.NEWS_IMPACT: ("新闻解读报告", "事件事实、来源时效、影响链路和后续观察"),
    Intent.BOTTOM_ANALYSIS: ("底部分析报告", "超跌与恐慌释放、反转确认、市场宽度和失效条件"),
}

MODULE_ORDER = (
    "investor_guide",
    "company_profile",
    "financial_snapshot",
    "valuation",
    "comparison",
    "news",
    "facts",
    "analysis",
    "bottom_analysis",
    "future_watch",
    "risk",
    "risk_review",
    "glossary",
    "sources",
)

MODULES_BY_INTENT = {
    Intent.OVERVIEW: {
        "investor_guide",
        "company_profile",
        "financial_snapshot",
        "news",
        "facts",
        "analysis",
        "future_watch",
        "risk",
        "risk_review",
        "glossary",
        "sources",
    },
    Intent.STOCK_COMPARISON: {
        "investor_guide",
        "comparison",
        "facts",
        "analysis",
        "future_watch",
        "risk_review",
        "sources",
    },
    Intent.FUNDAMENTAL_ANALYSIS: {
        "investor_guide",
        "financial_snapshot",
        "facts",
        "analysis",
        "future_watch",
        "risk",
        "risk_review",
        "glossary",
        "sources",
    },
    Intent.VALUATION_ANALYSIS: {
        "investor_guide",
        "financial_snapshot",
        "valuation",
        "facts",
        "analysis",
        "future_watch",
        "risk",
        "risk_review",
        "glossary",
        "sources",
    },
    Intent.RISK_ANALYSIS: {
        "investor_guide",
        "news",
        "facts",
        "analysis",
        "future_watch",
        "risk",
        "risk_review",
        "sources",
    },
    Intent.NEWS_IMPACT: {
        "news",
        "facts",
        "analysis",
        "future_watch",
        "risk",
        "risk_review",
        "sources",
    },
    Intent.BOTTOM_ANALYSIS: {
        "investor_guide",
        "bottom_analysis",
        "facts",
        "analysis",
        "future_watch",
        "risk",
        "risk_review",
        "sources",
    },
}

PROMPT_MODULE_SIGNALS = {
    "company_profile": ("公司", "业务", "商业模式", "做什么", "公司画像"),
    "financial_snapshot": (
        "财务",
        "财报",
        "营收",
        "利润",
        "现金流",
        "毛利",
        "负债",
        "roe",
    ),
    "valuation": ("估值", "市盈率", "市净率", "pe", "pb", "贵不贵", "便宜"),
    "news": ("新闻", "消息", "舆情", "事件", "公告", "近期"),
    "risk": ("风险", "隐患", "利空", "下行", "不确定性"),
}


def _visible_modules(intent: Intent, query: str) -> list[str]:
    selected = set(MODULES_BY_INTENT[intent])
    normalized = query.casefold()
    for module, signals in PROMPT_MODULE_SIGNALS.items():
        if any(signal in normalized for signal in signals):
            selected.add(module)
            if module in {"financial_snapshot", "valuation"}:
                selected.add("glossary")
    return [module for module in MODULE_ORDER if module in selected]


TERM_EXPLANATIONS = [
    TermExplanation(
        term="PE",
        professional_definition="市盈率，股票价格与每股收益的比值。",
        plain_language_explanation="可以理解为市场愿意为公司一年盈利能力支付多少倍价格。PE 需要结合行业和成长阶段比较。",
    ),
    TermExplanation(
        term="ROE",
        professional_definition="净资产收益率，即净利润与平均股东权益的比率。",
        plain_language_explanation="衡量公司利用股东投入资金创造利润的能力，但过高时也要留意负债等因素。",
    ),
    TermExplanation(
        term="营收增长率",
        professional_definition="本期营业收入相较上期的增长比例。",
        plain_language_explanation="表示公司卖出的产品或服务收入增长得有多快，需要观察增长能否持续。",
    ),
    TermExplanation(
        term="净利润增长率",
        professional_definition="本期归属利润相较上期的增长比例。",
        plain_language_explanation="表示公司最终赚到的钱增长得有多快，还要结合现金流和一次性收益判断质量。",
    ),
]

INDUSTRY_GUIDANCE = {
    "白酒": {
        "core_business": "高端白酒的生产、品牌运营与渠道销售",
        "characteristics": "品牌和渠道是重要竞争基础，经营表现与消费需求、批价及渠道库存密切相关。",
        "focus": [
            "消费需求是否稳定？",
            "渠道库存和批发价格如何变化？",
            "高端白酒竞争格局是否变化？",
        ],
        "watch": [
            "终端消费需求与动销变化",
            "渠道库存和核心产品批价",
            "高端白酒市场竞争与产品结构",
        ],
    },
    "动力电池": {
        "core_business": "动力电池与储能系统的研发、生产和销售",
        "characteristics": "技术、规模和客户结构重要，经营表现受原材料、价格竞争、产能利用率和海外市场影响。",
        "focus": [
            "电池价格竞争如何演变？",
            "储能业务能否保持增长？",
            "海外市场拓展和政策环境如何变化？",
        ],
        "watch": [
            "动力电池价格与单位盈利变化",
            "储能业务订单和收入增长",
            "海外客户、产能及政策环境",
        ],
    },
    "消费电子": {
        "core_business": "智能硬件、操作系统生态与数字服务",
        "characteristics": "品牌和生态黏性较强，经营表现受换机周期、产品创新、服务收入和供应链影响。",
        "focus": [
            "核心硬件需求是否稳定？",
            "服务业务能否保持增长？",
            "新功能能否带动产品竞争力？",
        ],
        "watch": [
            "核心产品销量与换机周期",
            "服务业务收入和盈利贡献",
            "产品创新、供应链与监管变化",
        ],
    },
}


def _metric(value: float | None, suffix: str = "", digits: int = 1) -> str:
    return "待确认" if value is None else f"{value:.{digits}f}{suffix}"


def _guidance_for(industry: str, description: str) -> dict[str, str | list[str]]:
    direct = INDUSTRY_GUIDANCE.get(industry)
    if direct is not None:
        return direct
    lowered = industry.casefold()
    if any(word in lowered for word in ("beverage", "winery", "distiller")):
        return INDUSTRY_GUIDANCE["白酒"]
    if any(
        word in lowered for word in ("auto part", "battery", "electrical equipment")
    ):
        return INDUSTRY_GUIDANCE["动力电池"]
    if any(
        word in lowered for word in ("consumer electronic", "hardware", "technology")
    ):
        return INDUSTRY_GUIDANCE["消费电子"]
    return {
        "core_business": description,
        "characteristics": "需要结合行业需求、竞争格局、盈利能力和资本投入持续观察。",
        "focus": [
            "公司的收入来源是否稳定？",
            "行业竞争是否发生变化？",
            "盈利能力能否保持？",
        ],
        "watch": ["收入和利润增长", "行业竞争格局", "现金流与资本投入"],
    }


def _comparison_observations(rows: list[CompanyComparison]) -> list[str]:
    definitions = (
        ("revenue_growth_percent", "营收增速", False, "%"),
        ("net_profit_growth_percent", "净利润增速", False, "%"),
        ("roe_percent", "ROE", False, "%"),
        ("pe_ttm", "PE(TTM)", True, " 倍"),
    )
    observations: list[str] = []
    for field, label, prefer_lower, suffix in definitions:
        available = [
            (row.company_name, getattr(row, field))
            for row in rows
            if getattr(row, field) is not None
        ]
        if len(available) < 2:
            continue
        ordered = sorted(available, key=lambda item: item[1], reverse=not prefer_lower)
        leader_name, leader_value = ordered[0]
        tail_name, tail_value = ordered[-1]
        if abs(leader_value - tail_value) < 0.01:
            observations.append(f"各公司{label}接近（{leader_value:.1f}{suffix}）")
        else:
            direction = "较低" if prefer_lower else "较高"
            observations.append(
                f"{leader_name}的{label}{direction}（{leader_value:.1f}{suffix}），"
                f"{tail_name}为 {tail_value:.1f}{suffix}"
            )
    return observations


class AnalysisAgent(BaseAgent[AnalysisInput, AnalysisOutput]):
    name = "analysis"

    def __init__(self, enhancer: AnalysisEnhancer | None = None) -> None:
        self._enhancer = enhancer

    def run(self, agent_input: AnalysisInput) -> AnalysisOutput:
        stocks = agent_input.data.stocks
        visible_modules = _visible_modules(
            agent_input.understanding.intent, agent_input.question
        )
        report_title, report_focus = REPORT_CONFIG[agent_input.understanding.intent]
        if not stocks:
            return AnalysisOutput(
                title=report_title,
                summary=f"当前任务为“{report_title.removesuffix('报告')}”，但缺少可用股票数据，证据不足以形成分析。",
                visible_modules=visible_modules,
                evidence_balance=EvidenceBalance.INSUFFICIENT,
                investor_focus=[],
                company_portraits=[],
                term_explanations=TERM_EXPLANATIONS,
                facts=[],
                ai_analysis=[],
                scenarios=[],
                uncertainties=["关键行情和财务数据缺失"],
                positive_factors=[],
                negative_factors=[],
                pending_verification=["补充可追溯的行情与财务数据"],
                future_watch=["等待补充公司、行业和财务数据"],
                follow_up_questions=[],
                comparison=[],
                sections=[],
                citations=[],
                generated_at=datetime.now(timezone.utc),
            )

        facts: list[ConfirmedFact] = []
        analyses: list[AIAnalysisItem] = []
        scenarios: list[FutureScenario] = []
        sections: list[AnalysisSection] = []
        comparisons: list[CompanyComparison] = []
        investor_focus: list[InvestorFocusGuide] = []
        company_portraits: list[CompanyPortrait] = []
        future_watch: list[str] = []
        follow_up_questions: list[FollowUpQuestion] = []
        positive_factors: list[str] = []
        negative_factors: list[str] = []
        pending_verification: list[str] = ["最新一期正式公告对当前经营趋势的确认"]
        uncertainties: list[str] = ["宏观环境、政策与行业竞争的后续变化尚无法确认"]
        if any("mock" in source.name.casefold() for source in agent_input.data.sources):
            uncertainties.insert(0, "Mock 数据不代表实时市场状态")
        if agent_input.data.missing_fields:
            uncertainties.append("部分公开财务字段缺失，已在报告中标记为待确认")

        for stock in stocks:
            symbol = stock.company.symbol
            company_name = stock.company.name
            financial = stock.financial
            quote = stock.quote
            pe_text = (
                f"{quote.pe_ttm:.1f} 倍" if quote.pe_ttm is not None else "暂无数据"
            )
            quote_fact_id = f"fact-quote:{symbol}"
            growth_fact_id = f"fact-growth:{symbol}"
            quality_fact_id = f"fact-quality:{symbol}"
            guidance = _guidance_for(stock.company.industry, stock.company.description)
            focus_questions = guidance["focus"]
            if agent_input.understanding.intent == Intent.RISK_ANALYSIS:
                focus_questions = [
                    "收入和利润增长是否出现持续走弱？",
                    "现金流、负债与盈利质量是否匹配？",
                    "行业竞争、需求或监管是否正在变化？",
                    "哪些风险判断仍需要公告或后续数据确认？",
                ]
            elif agent_input.understanding.intent == Intent.STOCK_COMPARISON:
                focus_questions = [
                    "各公司的增长、盈利能力和估值差异是什么？",
                    "商业模式和所处成长阶段是否可直接比较？",
                    "各自最需要验证的积极因素和风险是什么？",
                ]
            elif agent_input.understanding.intent == Intent.FUNDAMENTAL_ANALYSIS:
                focus_questions = [
                    "营收与净利润增长是否同步？",
                    "毛利率、ROE 和经营现金流能否相互印证？",
                    "资产负债结构是否会带来偿债或融资压力？",
                ]
            elif agent_input.understanding.intent == Intent.VALUATION_ANALYSIS:
                focus_questions = [
                    "当前 PE、PB 能否由增长和盈利质量支撑？",
                    "适合使用什么同行或历史口径作为参照？",
                    "哪些经营变化可能使当前估值逻辑失效？",
                ]
            elif agent_input.understanding.intent == Intent.BOTTOM_ANALYSIS:
                focus_questions = [
                    "当前超跌、恐慌释放或支撑区域证据是否充分？",
                    "拒绝创新低、成交量和市场宽度是否确认反转？",
                    "哪些价位或结构变化会使底部判断失效？",
                    "哪些条件尚未满足，仍需等待后续交易日验证？",
                ]
            investor_focus.append(
                InvestorFocusGuide(company_name=company_name, questions=focus_questions)
            )
            company_portraits.append(
                CompanyPortrait(
                    symbol=symbol,
                    company_name=company_name,
                    what_it_does=stock.company.description,
                    core_business=guidance["core_business"],
                    industry=stock.company.industry,
                    business_characteristics=guidance["characteristics"],
                )
            )
            future_watch.extend(f"{company_name}：{item}" for item in guidance["watch"])
            follow_up_questions.extend(
                [
                    FollowUpQuestion(
                        label="它靠什么赚钱？", query=f"{company_name}靠什么赚钱？"
                    ),
                    FollowUpQuestion(
                        label="最近发生了什么变化？",
                        query=f"{company_name}最近发生了什么变化？",
                    ),
                    FollowUpQuestion(
                        label="未来应该关注哪些风险？",
                        query=f"{company_name}未来应该关注哪些风险？",
                    ),
                    FollowUpQuestion(
                        label="和同行相比有什么特点？",
                        query=f"{company_name}和同行相比有什么特点？",
                    ),
                ]
            )

            quote_detail = f"，PE(TTM) 为 {pe_text}" if quote.pe_ttm is not None else ""
            facts.append(
                ConfirmedFact(
                    fact_id=quote_fact_id,
                    content=(
                        f"{company_name}在行情截止时点的价格为 "
                        f"{quote.price:.2f} {quote.currency}{quote_detail}。"
                    ),
                    source_ids=[f"quote:{symbol}"],
                )
            )
            company_fact_ids = [quote_fact_id]
            growth_values = (
                financial.revenue_billion,
                financial.revenue_growth_percent,
                financial.net_profit_billion,
                financial.net_profit_growth_percent,
            )
            if any(value is not None for value in growth_values):
                growth_parts = []
                if financial.revenue_billion is not None:
                    growth_parts.append(
                        f"营收 {_metric(financial.revenue_billion)} 十亿元"
                    )
                if financial.revenue_growth_percent is not None:
                    growth_parts.append(
                        f"营收增速 {_metric(financial.revenue_growth_percent, '%')}"
                    )
                if financial.net_profit_billion is not None:
                    growth_parts.append(
                        f"净利润 {_metric(financial.net_profit_billion)} 十亿元"
                    )
                if financial.net_profit_growth_percent is not None:
                    growth_parts.append(
                        f"净利润增速 {_metric(financial.net_profit_growth_percent, '%')}"
                    )
                facts.append(
                    ConfirmedFact(
                        fact_id=growth_fact_id,
                        content=f"{company_name} {financial.fiscal_period}：{'；'.join(growth_parts)}。",
                        source_ids=[f"financial:{symbol}"],
                    )
                )
                company_fact_ids.append(growth_fact_id)
            quality_values = (
                financial.roe_percent,
                financial.gross_margin_percent,
                financial.debt_ratio_percent,
            )
            if any(value is not None for value in quality_values):
                quality_parts = []
                if financial.roe_percent is not None:
                    quality_parts.append(f"ROE {_metric(financial.roe_percent, '%')}")
                if financial.gross_margin_percent is not None:
                    quality_parts.append(
                        f"毛利率 {_metric(financial.gross_margin_percent, '%')}"
                    )
                if financial.debt_ratio_percent is not None:
                    quality_parts.append(
                        f"资产负债率 {_metric(financial.debt_ratio_percent, '%')}"
                    )
                facts.append(
                    ConfirmedFact(
                        fact_id=quality_fact_id,
                        content=f"{company_name}公开财务数据：{'；'.join(quality_parts)}。",
                        source_ids=[f"financial:{symbol}"],
                    )
                )
                company_fact_ids.append(quality_fact_id)

            if (
                financial.net_profit_growth_percent is not None
                and financial.net_profit_growth_percent > 10
            ):
                positive = f"{company_name}当前财务数据中的净利润增速高于 10%"
                positive_factors.append(positive)
            else:
                positive = f"{company_name}经营现金流可作为盈利质量观察项"
                pending_verification.append(f"{company_name}增长能否重新加速")

            if (
                financial.debt_ratio_percent is not None
                and financial.debt_ratio_percent > 70
            ):
                main_risk = f"{company_name}资产负债率较高，需结合行业特征判断"
            elif quote.pe_ttm is not None and quote.pe_ttm > 30:
                main_risk = f"{company_name}当前估值倍数较高，估值波动敏感性较强"
            else:
                main_risk = f"{company_name}面临行业需求和竞争变化风险"
            negative_factors.append(main_risk)

            if agent_input.understanding.intent == Intent.RISK_ANALYSIS:
                analysis_text = (
                    f"{company_name}的风险扫描重点是：{main_risk}。"
                    "需继续用后续财报、公告和高可信新闻验证风险是否实际发生，"
                    "不应将风险清单直接等同于股价判断。"
                )
            elif agent_input.understanding.intent == Intent.STOCK_COMPARISON:
                analysis_text = (
                    f"{company_name}的可比观察项包括增长、ROE、PE 和业务特征；"
                    f"当前主要风险是“{main_risk}”。"
                    "单项指标不代表综合优劣。"
                )
            elif agent_input.understanding.intent == Intent.FUNDAMENTAL_ANALYSIS:
                analysis_text = (
                    f"{company_name}的财务分析应聚焦收入和利润增长、"
                    "毛利率、ROE、现金流与负债结构是否相互印证。"
                    f"当前需重点跟踪：{main_risk}。"
                )
            elif agent_input.understanding.intent == Intent.VALUATION_ANALYSIS:
                analysis_text = (
                    f"{company_name}当前 PE(TTM) 为 {pe_text}。"
                    "估值不能脱离增长、盈利质量、行业参照和历史区间；"
                    f"当前需留意：{main_risk}。"
                )
            elif agent_input.understanding.intent == Intent.BOTTOM_ANALYSIS:
                scan_context = ""
                if "底部狩猎扫描日期" in agent_input.question:
                    scan_context = (
                        agent_input.question.split("底部狩猎扫描日期", 1)[1]
                        .split("请结合", 1)[0]
                        .strip("，。； ")
                    )
                analysis_text = (
                    (f"本次扫描记录：{scan_context}。" if scan_context else "")
                    + f"{company_name}的底部分析需区分超跌后的修复与趋势反转；"
                    "当前公司财务和估值数据不能单独证明股价已见底。"
                    f"需结合近期低点、成交量、市场宽度和后续收盘确认，并留意{main_risk}。"
                )
            else:
                analysis_text = (
                    f"结合当前可得的经营和估值数据，{company_name}当前经营表现具有一定支撑，"
                    f"但 {main_risk}；这是一项基于已列事实的 AI 分析，不是投资建议。"
                )
            analyses.append(
                AIAnalysisItem(
                    content=analysis_text,
                    based_on_fact_ids=company_fact_ids,
                )
            )
            sections.append(
                AnalysisSection(
                    title=f"{company_name}：AI 综合分析",
                    content=analysis_text,
                    evidence_ids=[f"quote:{symbol}", f"financial:{symbol}"],
                )
            )
            scenario_fact_ids = company_fact_ids[1:] or company_fact_ids
            scenarios.extend(
                [
                    FutureScenario(
                        condition=f"如果{company_name}的收入和利润增长能够延续",
                        possible_outcome="盈利基础可能继续为估值提供支撑",
                        based_on_fact_ids=scenario_fact_ids,
                    ),
                    FutureScenario(
                        condition=f"如果{company_name}所处行业需求走弱或竞争加剧",
                        possible_outcome="收入增速、利润率和估值可能承受压力",
                        based_on_fact_ids=scenario_fact_ids,
                    ),
                ]
            )
            comparisons.append(
                CompanyComparison(
                    symbol=symbol,
                    company_name=company_name,
                    market=stock.company.market,
                    industry=stock.company.industry,
                    price=quote.price,
                    currency=quote.currency,
                    revenue_growth_percent=financial.revenue_growth_percent,
                    net_profit_growth_percent=financial.net_profit_growth_percent,
                    roe_percent=financial.roe_percent,
                    pe_ttm=quote.pe_ttm,
                    positive_factor=positive,
                    main_risk=main_risk,
                    business_characteristics=(
                        f"{stock.company.industry}行业；{stock.company.description}"
                    ),
                )
            )

        for item in agent_input.news.selected:
            fact_id = f"fact-news:{item.news_id}"
            facts.append(
                ConfirmedFact(
                    fact_id=fact_id,
                    content=(
                        f"{item.source}于 {item.published_at.date().isoformat()} 发布“{item.title}”："
                        f"{item.summary}"
                    ),
                    source_ids=[item.news_id],
                )
            )
            if item.sentiment == "positive":
                positive_factors.append(item.title)
            elif item.sentiment == "negative":
                negative_factors.append(item.title)
            else:
                pending_verification.append(f"“{item.title}”的后续经营影响")

        positive_factors = list(dict.fromkeys(positive_factors))
        negative_factors = list(dict.fromkeys(negative_factors))
        pending_verification = list(dict.fromkeys(pending_verification))
        if len(positive_factors) > len(negative_factors) + 1:
            evidence_balance = EvidenceBalance.POSITIVE_FACTORS_DOMINANT
        elif len(negative_factors) > len(positive_factors) + 1:
            evidence_balance = EvidenceBalance.NEGATIVE_FACTORS_DOMINANT
        else:
            evidence_balance = EvidenceBalance.BALANCED

        names = "、".join(stock.company.name for stock in stocks)
        intent = agent_input.understanding.intent
        comparison_notice = None
        if intent == Intent.STOCK_COMPARISON:
            observations = _comparison_observations(comparisons)
            comparison_fact_ids = [
                item.fact_id
                for item in facts
                if item.fact_id.startswith(
                    ("fact-quote:", "fact-growth:", "fact-quality:")
                )
            ]
            comparison_text = (
                "统一口径比较显示：" + "；".join(observations)
                if observations
                else (
                    "当前可比较的财务字段不足；业务定位方面，"
                    + "；".join(
                        f"{row.company_name}：{row.business_characteristics[:100]}"
                        for row in comparisons
                    )
                )
            )
            analyses = [
                AIAnalysisItem(
                    content=(
                        f"{comparison_text}。这些只是指标和商业特征差异，"
                        "不等于综合优劣或买卖结论。"
                    ),
                    based_on_fact_ids=comparison_fact_ids,
                )
            ]
            scenarios = [
                FutureScenario(
                    condition="如果各公司后续披露的增长和盈利指标继续分化",
                    possible_outcome="可能扩大当前财务表现和估值参照的差异",
                    based_on_fact_ids=comparison_fact_ids,
                ),
                FutureScenario(
                    condition="如果行业需求、竞争或监管环境发生变化",
                    possible_outcome="可能使现有比较结论失效，需按新数据重新评估",
                    based_on_fact_ids=comparison_fact_ids,
                ),
            ]
            future_watch = [
                "各公司下一期财报的营收和净利润增速差异",
                "ROE、毛利率与经营现金流的同口径变化",
                "PE 差异背后的成长阶段、业务结构和风险差异",
            ]
            follow_up_questions = [
                FollowUpQuestion(label="对比财务质量", query=f"对比{names}的财务质量"),
                FollowUpQuestion(label="对比估值口径", query=f"对比{names}的估值口径"),
                FollowUpQuestion(
                    label="对比各自风险", query=f"对比{names}各自的主要风险"
                ),
            ]
            auto_peers = [
                entity.name
                for entity in agent_input.understanding.entities
                if entity.match_source == "industry_peer"
            ]
            comparison_notice = COMPARISON_NOTICE
            if auto_peers:
                comparison_notice = (
                    f"系统按同一数据源的行业分类自动补充了"
                    f"{'、'.join(auto_peers)}作为参照对象。{COMPARISON_NOTICE}"
                )
        elif intent == Intent.RISK_ANALYSIS:
            follow_up_questions = [
                FollowUpQuestion(
                    label="追踪负面新闻", query=f"解读{names}近期负面新闻的影响"
                ),
                FollowUpQuestion(
                    label="检查财务风险", query=f"分析{names}的现金流和负债风险"
                ),
                FollowUpQuestion(
                    label="查看风险触发器", query=f"{names}的哪些风险指标需要持续跟踪"
                ),
            ]
        elif intent == Intent.FUNDAMENTAL_ANALYSIS:
            follow_up_questions = [
                FollowUpQuestion(
                    label="看盈利质量", query=f"分析{names}的利润和现金流是否匹配"
                ),
                FollowUpQuestion(
                    label="看负债结构", query=f"分析{names}的负债结构和偿债压力"
                ),
                FollowUpQuestion(
                    label="看增长趋势", query=f"{names}的营收和净利润增速如何变化"
                ),
            ]
        elif intent == Intent.VALUATION_ANALYSIS:
            follow_up_questions = [
                FollowUpQuestion(
                    label="看估值基础", query=f"{names}的估值由哪些盈利和增长因素支撑"
                ),
                FollowUpQuestion(
                    label="看估值风险", query=f"{names}的估值对哪些风险最敏感"
                ),
                FollowUpQuestion(
                    label="明确参照对象", query=f"将{names}和可比同行做估值对比"
                ),
            ]
        elif intent == Intent.NEWS_IMPACT:
            news_fact_ids = [
                item.fact_id for item in facts if item.fact_id.startswith("fact-news:")
            ]
            fallback_fact_ids = news_fact_ids or [facts[0].fact_id]
            if agent_input.news.selected:
                analyses = [
                    AIAnalysisItem(
                        content=(
                            f"新闻“{item.title}”的关注重点是："
                            f"{item.attention_reason.rstrip('。！？!?')}。这是影响链路解读，"
                            "不代表影响已经发生。"
                        ),
                        based_on_fact_ids=[f"fact-news:{item.news_id}"],
                    )
                    for item in agent_input.news.selected[:3]
                ]
            else:
                analyses = [
                    AIAnalysisItem(
                        content="当前没有新闻通过相关性、可信度和时效筛选，暂不解读事件影响。",
                        based_on_fact_ids=fallback_fact_ids,
                    )
                ]
            scenarios = [
                FutureScenario(
                    condition="如果保留新闻中提及的事件获得公司公告或后续数据确认",
                    possible_outcome="可能需要重新评估对收入、利润率、成本或监管的影响",
                    based_on_fact_ids=fallback_fact_ids,
                ),
                FutureScenario(
                    condition="如果后续缺少高可信来源或公司正式确认",
                    possible_outcome="当前新闻的投研重要性可能下降",
                    based_on_fact_ids=fallback_fact_ids,
                ),
            ]
            future_watch = [
                "公司公告是否确认新闻中的核心事实",
                "事件是否开始影响经营指标或监管环境",
                "后续报道的来源可信度与信息一致性",
            ]
            follow_up_questions = [
                FollowUpQuestion(
                    label="只看负面事件", query=f"筛选{names}近期负面新闻"
                ),
                FollowUpQuestion(
                    label="看事件影响链", query=f"这些新闻可能影响{names}的哪些经营指标"
                ),
                FollowUpQuestion(
                    label="查找公告确认", query=f"查找{names}对近期新闻的正式公告"
                ),
            ]
        elif intent == Intent.BOTTOM_ANALYSIS:
            follow_up_questions = [
                FollowUpQuestion(label="检查反转确认", query=f"分析{names}的反转确认和成交量变化"),
                FollowUpQuestion(label="列出失效条件", query=f"分析{names}底部判断的失效条件和风险"),
                FollowUpQuestion(label="继续跟踪", query=f"持续跟踪{names}后续交易日的底部结构"),
            ]
            future_watch = [
                "是否持续守住近期低点与关键支撑区域",
                "反弹是否伴随成交量改善、拒绝创新低和市场宽度确认",
                "后续收盘是否确认反转，避免把单日波动当作底部",
            ]

        if intent == Intent.RISK_ANALYSIS:
            summary = (
                f"本次专门扫描{names}的下行风险，重点是经营、财务、"
                "行业/监管与待验证事项，不把一般公司介绍当作主结论。"
                f"当前证据结构为“{evidence_balance.value}”。"
            )
        elif intent == Intent.STOCK_COMPARISON:
            summary = (
                f"本次将{names}纳入统一表格，重点比较增长、盈利能力、"
                "估值、商业特征和各自风险，不用单一指标排名。"
            )
        elif intent == Intent.FUNDAMENTAL_ANALYSIS:
            summary = (
                f"本次以{names}的财务模块为主体，依次检查营收与利润、"
                "盈利质量、现金流和资产负债结构，并明确标注缺失数据。"
            )
        elif intent == Intent.VALUATION_ANALYSIS:
            summary = (
                f"本次以{names}的估值模块为主体，将 PE、PB 与增长、"
                "盈利质量和风险敏感因素一起展示，不使用单一倍数判断高估或低估。"
            )
        elif intent == Intent.NEWS_IMPACT:
            summary = (
                f"本次以{names}的新闻解读为主体："
                f"从 {agent_input.news.stats.candidate_count} 条候选信息中保留 "
                f"{agent_input.news.stats.selected_count} 条，重点展示事件事实、"
                "来源时效、可能的经营影响链和后续验证点。"
            )
        elif intent == Intent.BOTTOM_ANALYSIS:
            summary = (
                f"本次以{names}的底部结构为主体，重点检查超跌与恐慌释放、"
                "拒绝创新低、成交量及市场宽度等反转证据，并列明失效条件。"
                "底部判断需要后续交易日确认，不代表买卖建议。"
            )
        else:
            summary = (
                f"本次任务重点覆盖{report_focus}。基于当前行情、财务及筛选后新闻，"
                f"{names}的当前证据结构为“{evidence_balance.value}”。"
                "下文严格区分已确认事实、AI 分析与未来情景。"
            )
        citations = [*agent_input.data.sources, *agent_input.news.sources]
        draft = AnalysisOutput(
            title=f"{names}{report_title}",
            summary=summary,
            visible_modules=visible_modules,
            evidence_balance=evidence_balance,
            investor_focus=investor_focus,
            company_portraits=company_portraits,
            term_explanations=TERM_EXPLANATIONS,
            facts=facts,
            ai_analysis=analyses,
            scenarios=scenarios,
            uncertainties=uncertainties,
            positive_factors=positive_factors,
            negative_factors=negative_factors,
            pending_verification=pending_verification,
            future_watch=list(dict.fromkeys(future_watch)),
            follow_up_questions=follow_up_questions,
            comparison=comparisons if intent == Intent.STOCK_COMPARISON else [],
            comparison_notice=comparison_notice,
            sections=sections,
            citations=citations,
            generated_at=datetime.now(timezone.utc),
        )
        if self._enhancer is None:
            return draft
        try:
            return self._enhancer.enhance(agent_input.question, draft)
        except Exception as exc:
            return draft.model_copy(
                update={
                    "analysis_method": "rule_based_fallback",
                    "analysis_warnings": [f"千问增强未生效，已使用本地规则分析：{exc}"],
                }
            )
