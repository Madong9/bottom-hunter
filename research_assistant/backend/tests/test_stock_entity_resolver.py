import json

import pytest

from app.agents import QueryRouterAgent, StockEntityResolverAgent
from app.core.exceptions import StockNotFoundError
from app.providers import MockFinancialDataProvider
from app.schemas.agents import QueryRouterInput, StockEntityResolverInput
from app.schemas.research import StockSearchItem


def resolve(agent: StockEntityResolverAgent, query: str):
    routing = QueryRouterAgent().run(QueryRouterInput(query=query))
    return agent.run(StockEntityResolverInput(query=query, routing=routing))


def test_resolves_company_names_from_workspace_master_across_markets(tmp_path) -> None:
    master = tmp_path / "security_master.json"
    master.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "asset_type": "equity",
                        "symbol": "1810.HK",
                        "name": "小米集团-W",
                        "market": "HK",
                        "industry": "Consumer Electronics",
                        "source_symbols": {"yahoo": "1810.HK"},
                    },
                    {
                        "asset_type": "equity",
                        "symbol": "PDD",
                        "name": "拼多多",
                        "market": "US",
                        "industry": "Internet Retail",
                        "source_symbols": {"yahoo": "PDD"},
                    },
                    {
                        "asset_type": "equity",
                        "symbol": "002415.SZ",
                        "name": "海康威视",
                        "market": "CN",
                        "industry": "Security Equipment",
                        "source_symbols": {"yahoo": "002415.SZ"},
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent = StockEntityResolverAgent(
        MockFinancialDataProvider(), workspace_master_path=master
    )

    cases = {
        "小米风险查询": "1810.HK",
        "拼多多估值分析": "PDD.US",
        "海康威视财务分析": "002415.SZ",
    }
    for query, expected_symbol in cases.items():
        output = resolve(agent, query)
        assert output.entities[0].symbol == expected_symbol
        assert output.entities[0].match_source == "bottom_hunter_master"


def test_resolves_explicit_codes_and_verified_us_ticker(tmp_path) -> None:
    agent = StockEntityResolverAgent(
        MockFinancialDataProvider(), workspace_master_path=tmp_path / "missing.json"
    )

    output = resolve(agent, "比较 600519、0700.HK 和 AAPL")

    assert [entity.symbol for entity in output.entities] == [
        "600519.SH",
        "0700.HK",
        "AAPL.US",
    ]
    assert resolve(agent, "analyze Apple risk").entities[0].symbol == "AAPL.US"


class RemoteSearchProvider(MockFinancialDataProvider):
    def __init__(self, enabled: bool = True) -> None:
        super().__init__()
        self.enabled = enabled
        self.search_calls = 0

    def stock_catalog(self):
        return []

    def search_stocks(self, query: str) -> list[StockSearchItem]:
        self.search_calls += 1
        if not self.enabled or query != "测试公司":
            return []
        return [
            StockSearchItem(
                symbol="1234.HK",
                name="测试公司",
                market="港股",
                industry="Software",
            )
        ]


def test_remote_resolution_is_persisted_in_sqlite_cache(tmp_path) -> None:
    cache_path = tmp_path / "research.db"
    missing_master = tmp_path / "missing.json"
    online_provider = RemoteSearchProvider()
    online_agent = StockEntityResolverAgent(
        online_provider,
        cache_path=cache_path,
        workspace_master_path=missing_master,
    )

    first = resolve(online_agent, "测试公司风险查询")
    assert first.entities[0].symbol == "1234.HK"
    assert online_provider.search_calls == 1

    offline_provider = RemoteSearchProvider(enabled=False)
    cached_agent = StockEntityResolverAgent(
        offline_provider,
        cache_path=cache_path,
        workspace_master_path=missing_master,
    )
    second = resolve(cached_agent, "测试公司风险查询")

    assert second.entities[0].symbol == "1234.HK"
    assert second.entities[0].match_source == "remote_search"
    assert offline_provider.search_calls == 0


class AmbiguousProvider(MockFinancialDataProvider):
    def stock_catalog(self):
        return [
            {
                "symbol": "TEST.US",
                "name": "同名科技",
                "market": "美股",
                "industry": "Software",
                "aliases": ["同名"],
            },
            {
                "symbol": "1234.HK",
                "name": "同名科技",
                "market": "港股",
                "industry": "Software",
                "aliases": ["同名"],
            },
        ]


def test_ambiguous_company_name_requests_market_or_code(tmp_path) -> None:
    agent = StockEntityResolverAgent(
        AmbiguousProvider(), workspace_master_path=tmp_path / "missing.json"
    )

    with pytest.raises(StockNotFoundError, match="存在多个匹配") as error:
        resolve(agent, "同名科技风险分析")

    assert "TEST.US" in str(error.value)
    assert "1234.HK" in str(error.value)


def test_market_hint_disambiguates_cross_listed_company(tmp_path) -> None:
    agent = StockEntityResolverAgent(
        AmbiguousProvider(), workspace_master_path=tmp_path / "missing.json"
    )

    output = resolve(agent, "同名科技港股风险分析")

    assert output.entities[0].symbol == "1234.HK"
    assert output.entities[0].market == "港股"


class PeerProvider(MockFinancialDataProvider):
    def stock_catalog(self):
        return [
            {
                "symbol": "1024.HK",
                "name": "快手科技",
                "market": "港股",
                "industry": "Internet Content & Information",
                "aliases": ["快手"],
            },
            {
                "symbol": "0700.HK",
                "name": "腾讯控股",
                "market": "港股",
                "industry": "Internet Content & Information",
                "aliases": ["腾讯"],
            },
        ]


def test_single_company_peer_comparison_auto_selects_explainable_peer(tmp_path) -> None:
    agent = StockEntityResolverAgent(
        PeerProvider(), workspace_master_path=tmp_path / "missing.json"
    )

    output = resolve(agent, "快手的同行对比")

    assert [entity.symbol for entity in output.entities] == ["1024.HK", "0700.HK"]
    assert output.entities[1].match_source == "industry_peer"
