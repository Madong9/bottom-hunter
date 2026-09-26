import json
from pathlib import Path

import httpx
import pandas as pd
import yfinance as yf

from app.agents import DataRetrievalAgent
from app.core.exceptions import DataProviderError
from app.llm import QwenAnalysisEnhancer
from app.orchestration.workflow import ResearchWorkflow
from app.providers import MockFinancialDataProvider, YFinanceProvider
from app.repositories import SQLiteTaskRepository
from app.schemas.agents import (
    DataRetrievalInput,
    QuestionUnderstandingOutput,
    TimeRange,
)
from app.schemas.common import Intent
from app.schemas.research import ResearchRequest
from app.services import ResearchService


def test_yfinance_symbol_normalization_covers_three_markets_without_network() -> None:
    provider = YFinanceProvider()

    assert provider.resolve_symbols("比较 600519.SH、0700.HK 和 AAPL") == [
        "600519.SH",
        "0700.HK",
        "AAPL.US",
    ]
    assert provider.source_url("600519.SH") == "https://finance.yahoo.com/quote/600519.SS"
    assert provider.source_url("0700.HK") == "https://finance.yahoo.com/quote/0700.HK"
    assert provider.source_url("AAPL.US") == "https://finance.yahoo.com/quote/AAPL"


def test_chinese_company_name_resolves_to_a_share_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["input"] == "分众传媒"
        return httpx.Response(
            200,
            json={
                "QuotationCodeTable": {
                    "Data": [
                        {
                            "Code": "002027",
                            "Name": "分众传媒",
                            "Classify": "AStock",
                            "SecurityTypeName": "深A",
                            "QuoteID": "0.002027",
                        }
                    ]
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = YFinanceProvider(search_client=client)

    assert provider.resolve_symbols("分析分众传媒") == ["002027.SZ"]


def test_known_company_in_conversational_query_does_not_need_remote_search() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("known company should be resolved from the local catalog")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = YFinanceProvider(search_client=client)

    assert provider.resolve_symbols("你来分析一下美团") == ["3690.HK"]


def test_kuaishou_risk_query_resolves_to_hong_kong_stock_without_network() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("known company should be resolved from the local catalog")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = YFinanceProvider(search_client=client)

    assert provider.resolve_symbols("快手风险查询") == ["1024.HK"]


def test_chinese_stock_search_treats_null_data_as_empty_results() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"QuotationCodeTable": {"Data": None}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = YFinanceProvider(search_client=client)

    assert provider._search_chinese_stocks("未知公司") == []


def test_yfinance_uses_history_without_waiting_for_quote_info(monkeypatch) -> None:  # noqa: ANN001
    class HistoryOnlyTicker:
        def history(self, **_kwargs):  # noqa: ANN003, ANN201
            return pd.DataFrame(
                {"Close": [70.0, 72.8]},
                index=pd.to_datetime(["2026-09-24", "2026-09-25"], utc=True),
            )

        def get_info(self):  # noqa: ANN201
            raise AssertionError("history already supplied the current price")

        def get_income_stmt(self, **_kwargs):  # noqa: ANN003, ANN201
            return pd.DataFrame()

        def get_balance_sheet(self, **_kwargs):  # noqa: ANN003, ANN201
            return pd.DataFrame()

        def get_cash_flow(self, **_kwargs):  # noqa: ANN003, ANN201
            return pd.DataFrame()

    monkeypatch.setattr(yf, "Ticker", lambda _symbol: HistoryOnlyTicker())

    stock = YFinanceProvider().get_stock("3690.HK")

    assert stock is not None
    assert stock.company.name == "美团"
    assert stock.quote.price == 72.8
    assert round(stock.quote.change_percent or 0, 2) == 4.0
    assert stock.quote.currency == "HKD"


def test_data_retrieval_keeps_workflow_alive_when_provider_is_unavailable() -> None:
    class UnavailableProvider(MockFinancialDataProvider):
        def get_stock(self, symbol):  # noqa: ANN001, ANN201
            raise DataProviderError(f"{symbol} timeout")

    understanding = QuestionUnderstandingOutput(
        normalized_query="分析美团",
        symbols=["3690.HK"],
        intent=Intent.OVERVIEW,
        time_range=TimeRange(),
        dimensions=["company", "financial"],
    )

    output = DataRetrievalAgent(UnavailableProvider()).run(
        DataRetrievalInput(understanding=understanding)
    )

    assert output.stocks == []
    assert output.sources == []
    assert output.missing_fields == [
        "3690.HK: 数据源暂时不可用（3690.HK timeout）"
    ]


def test_yfinance_news_cleans_html_and_rejects_unrelated_items(monkeypatch) -> None:  # noqa: ANN001
    class NewsTicker:
        def get_news(self, **_kwargs):  # noqa: ANN003, ANN201
            return [
                {
                    "content": {
                        "id": "meituan-news",
                        "title": "Meituan &amp; quarterly results",
                        "summary": "<body><p>Revenue &amp; profit improved.</p></body>",
                        "provider": {"displayName": "Example &amp; News"},
                        "relatedTickers": ["MPNGF"],
                        "pubDate": "2026-09-25T08:00:00Z",
                    }
                },
                {
                    "content": {
                        "id": "robot-news",
                        "title": "Unrelated humanoid robot story",
                        "summary": "No relation to the researched company.",
                        "provider": {"displayName": "Example News"},
                        "relatedTickers": ["9866.HK"],
                        "pubDate": "2026-09-25T08:00:00Z",
                    }
                },
            ]

    monkeypatch.setattr(yf, "Ticker", lambda _symbol: NewsTicker())

    items = YFinanceProvider().get_news(["3690.HK"])

    assert len(items) == 1
    assert items[0].title == "Meituan & quarterly results"
    assert items[0].summary == "Revenue & profit improved."
    assert items[0].source == "Example & News"
    assert "3690.HK" in items[0].symbols


def test_qwen_enhances_only_narrative_and_preserves_evidence() -> None:
    provider = MockFinancialDataProvider()
    result, _ = ResearchWorkflow(provider).run("分析贵州茅台")
    draft = result.analysis
    narrative = {
        "summary": "这是千问根据现有事实生成的通俗认知摘要，不包含交易建议。",
        "ai_analysis": [item.model_dump() for item in draft.ai_analysis],
        "scenarios": [item.model_dump() for item in draft.scenarios],
        "uncertainties": draft.uncertainties,
        "future_watch": draft.future_watch,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        request_payload = json.loads(request.content)
        response_format = request_payload["response_format"]
        assert response_format["type"] == "json_schema"
        assert response_format["json_schema"]["strict"] is True
        assert request_payload["enable_thinking"] is False
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(narrative, ensure_ascii=False)}}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    enhanced = QwenAnalysisEnhancer(
        api_key="test-key",
        model="qwen-plus",
        client=client,
    ).enhance("分析贵州茅台", draft)

    assert enhanced.analysis_method == "qwen:qwen-plus"
    assert enhanced.summary == narrative["summary"]
    assert enhanced.facts == draft.facts
    assert enhanced.citations == draft.citations


def test_qwen_failure_falls_back_to_rule_analysis() -> None:
    class BrokenEnhancer:
        def enhance(self, question, draft):  # noqa: ANN001, ANN201
            raise RuntimeError("temporary failure")

    result, _ = ResearchWorkflow(
        MockFinancialDataProvider(), BrokenEnhancer()
    ).run("分析贵州茅台")

    assert result.analysis.analysis_method == "rule_based_fallback"
    assert result.analysis.analysis_warnings
    assert result.analysis.facts


def test_sqlite_repository_persists_research_history(tmp_path: Path) -> None:
    database_path = tmp_path / "research.db"
    provider = MockFinancialDataProvider()
    first_service = ResearchService(
        workflow=ResearchWorkflow(provider),
        provider=provider,
        repository=SQLiteTaskRepository(str(database_path)),
    )
    created = first_service.create(ResearchRequest(query="分析宁德时代"))

    second_service = ResearchService(
        workflow=ResearchWorkflow(provider),
        provider=provider,
        repository=SQLiteTaskRepository(str(database_path)),
    )
    restored = second_service.get(created.task_id)
    history = second_service.list_tasks()

    assert restored == created
    assert history.total == 1
    assert history.items[0].task_id == created.task_id
