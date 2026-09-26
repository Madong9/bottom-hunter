from datetime import datetime, timedelta, timezone

from app.agents import (
    AnalysisAgent,
    DataRetrievalAgent,
    NewsFilterAgent,
    QueryRouterAgent,
    QuestionUnderstandingAgent,
    RiskReviewAgent,
    StockEntityResolverAgent,
)
from app.orchestration.workflow import ResearchWorkflow
from app.providers import MockFinancialDataProvider
from app.schemas.agents import (
    AnalysisInput,
    DataRetrievalInput,
    NewsFilterInput,
    NewsItem,
    QueryRouterInput,
    QuestionUnderstandingInput,
    RiskReviewInput,
    StockEntityResolverInput,
)
from app.schemas.common import Intent, ReviewStatus


def test_all_agents_have_typed_inputs_and_outputs() -> None:
    provider = MockFinancialDataProvider()
    routing = QueryRouterAgent().run(
        QueryRouterInput(query="分析贵州茅台的基本面和估值")
    )
    resolution = StockEntityResolverAgent(provider).run(
        StockEntityResolverInput(
            query="分析贵州茅台的基本面和估值",
            routing=routing,
        )
    )
    understanding = QuestionUnderstandingAgent().run(
        QuestionUnderstandingInput(
            query="分析贵州茅台的基本面和估值",
            routing=routing,
            resolution=resolution,
        )
    )
    assert understanding.symbols == ["600519.SH"]
    assert understanding.intent == Intent.VALUATION_ANALYSIS

    data = DataRetrievalAgent(provider).run(
        DataRetrievalInput(understanding=understanding)
    )
    assert data.stocks[0].company.name == "贵州茅台"

    news = NewsFilterAgent().run(
        NewsFilterInput(
            understanding=understanding,
            candidates=provider.get_news(understanding.symbols),
        )
    )
    assert news.rejected_count == 1
    assert len(news.selected) == 2

    analysis = AnalysisAgent().run(
        AnalysisInput(
            question="分析贵州茅台的基本面和估值",
            understanding=understanding,
            data=data,
            news=news,
        )
    )
    assert analysis.citations

    review = RiskReviewAgent().run(
        RiskReviewInput(
            question="分析贵州茅台的基本面和估值",
            analysis=analysis,
            available_source_ids=[
                source.source_id for source in [*data.sources, *news.sources]
            ],
        )
    )
    assert review.status == ReviewStatus.APPROVED
    assert review.evidence_coverage_rate == 1.0
    assert all(check.passed for check in review.checks)
    assert "confidence_score" not in review.model_dump()


def test_news_filter_statistics_are_explainable_and_add_up() -> None:
    provider = MockFinancialDataProvider()
    routing = QueryRouterAgent().run(QueryRouterInput(query="分析贵州茅台的新闻"))
    resolution = StockEntityResolverAgent(provider).run(
        StockEntityResolverInput(query="分析贵州茅台的新闻", routing=routing)
    )
    understanding = QuestionUnderstandingAgent().run(
        QuestionUnderstandingInput(
            query="分析贵州茅台的新闻",
            routing=routing,
            resolution=resolution,
        )
    )
    now = datetime.now(timezone.utc)

    def news(
        news_id: str, title: str, symbols: list[str], credibility: float, days: int
    ) -> NewsItem:
        return NewsItem(
            news_id=news_id,
            symbols=symbols,
            title=title,
            summary="测试新闻摘要",
            source="测试来源",
            published_at=now - timedelta(days=days),
            url=f"https://example.com/{news_id}",
            sentiment="neutral",
            credibility=credibility,
        )

    candidates = [
        news("kept", "公司发布经营数据", ["600519.SH"], 0.95, 2),
        news("duplicate", "公司发布经营数据", ["600519.SH"], 0.90, 3),
        news("irrelevant", "其他公司动态", ["AAPL.US"], 0.95, 2),
        news("untrusted", "网传公司即将提价", ["600519.SH"], 0.30, 2),
        news("stale", "公司历史经营回顾", ["600519.SH"], 0.90, 500),
    ]
    output = NewsFilterAgent().run(
        NewsFilterInput(understanding=understanding, candidates=candidates)
    )

    assert output.stats.candidate_count == 5
    assert output.stats.duplicate_count == 1
    assert output.stats.low_relevance_count == 1
    assert output.stats.low_credibility_count == 1
    assert output.stats.stale_count == 1
    assert output.stats.selected_count == 1
    assert (
        output.rejected_count + output.stats.selected_count
        == output.stats.candidate_count
    )
    assert output.selected[0].retention_reason
    assert output.selected[0].attention_reason
    assert 0 <= output.selected[0].composite_score <= 1


def test_query_router_covers_six_financial_task_categories() -> None:
    router = QueryRouterAgent()
    cases = {
        "分析一下贵州茅台": (Intent.OVERVIEW, "公司分析"),
        "比较贵州茅台和宁德时代": (Intent.STOCK_COMPARISON, "同行比较"),
        "分析宁德时代的财务和现金流": (Intent.FUNDAMENTAL_ANALYSIS, "财务分析"),
        "苹果当前 PE 估值贵不贵": (Intent.VALUATION_ANALYSIS, "估值分析"),
        "美团有哪些经营风险": (Intent.RISK_ANALYSIS, "风险分析"),
        "快手风险查询": (Intent.RISK_ANALYSIS, "风险分析"),
        "解读腾讯近期新闻的影响": (Intent.NEWS_IMPACT, "新闻解读"),
    }

    for query, (expected_intent, expected_category) in cases.items():
        output = router.run(QueryRouterInput(query=query))
        assert output.intent == expected_intent
        assert output.category == expected_category
        assert output.output_requirements
        assert 0 <= output.confidence <= 1


def test_workflow_routes_each_task_to_a_matching_report() -> None:
    workflow = ResearchWorkflow(MockFinancialDataProvider())
    cases = {
        "分析贵州茅台": "公司分析报告",
        "比较贵州茅台和宁德时代": "同行比较报告",
        "分析贵州茅台的财务和现金流": "财务分析报告",
        "贵州茅台当前 PE 估值贵不贵": "估值分析报告",
        "贵州茅台有哪些经营风险": "风险分析报告",
        "解读贵州茅台近期新闻": "新闻解读报告",
    }

    for query, expected_title in cases.items():
        result, runs = workflow.run(query)
        assert result.routing is not None
        assert result.routing.category in expected_title
        assert result.analysis.title.endswith(expected_title)
        assert runs[0].agent == "query_router"
        assert len(runs) == 7


def test_risk_and_peer_comparison_generate_materially_different_reports() -> None:
    workflow = ResearchWorkflow(MockFinancialDataProvider())

    risk_result, _ = workflow.run("贵州茅台有哪些经营风险")
    comparison_result, _ = workflow.run("比较贵州茅台和宁德时代")

    assert "下行风险" in risk_result.analysis.summary
    assert risk_result.analysis.comparison == []
    assert all("风险" in item.content for item in risk_result.analysis.ai_analysis)

    assert "统一表格" in comparison_result.analysis.summary
    assert len(comparison_result.analysis.comparison) == 2
    assert "统一口径比较" in comparison_result.analysis.ai_analysis[0].content
    assert comparison_result.analysis.summary != risk_result.analysis.summary


def test_each_routed_task_produces_its_own_module_plan() -> None:
    workflow = ResearchWorkflow(MockFinancialDataProvider())
    cases = {
        "分析贵州茅台": ("company_profile", "comparison"),
        "比较贵州茅台和宁德时代": ("comparison", "company_profile"),
        "分析贵州茅台的财务和现金流": ("financial_snapshot", "comparison"),
        "贵州茅台当前 PE 估值贵不贵": ("valuation", "comparison"),
        "贵州茅台有哪些经营风险": ("risk", "valuation"),
        "解读贵州茅台近期新闻": ("news", "financial_snapshot"),
    }

    for query, (included, excluded) in cases.items():
        result, _ = workflow.run(query)
        assert included in result.analysis.visible_modules
        assert excluded not in result.analysis.visible_modules


def test_prompt_signals_extend_the_primary_task_module_plan() -> None:
    result, _ = ResearchWorkflow(MockFinancialDataProvider()).run(
        "分析贵州茅台的风险和财务"
    )

    assert result.understanding.intent == Intent.RISK_ANALYSIS
    assert "risk" in result.analysis.visible_modules
    assert "financial_snapshot" in result.analysis.visible_modules
    assert "glossary" in result.analysis.visible_modules
