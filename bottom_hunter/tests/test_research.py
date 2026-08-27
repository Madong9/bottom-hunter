from __future__ import annotations

from datetime import date, datetime, timezone

from bottom_hunter.src.models import Instrument
from bottom_hunter.src.research import (
    CachedResearchFundamentalProvider,
    EastmoneyResearchProvider,
    FredMacroProvider,
    MacroSeriesDefinition,
    ResearchConfig,
    ResearchService,
    macro_regime,
    macro_sector_impact,
)
from bottom_hunter.src.research_models import (
    FinancialFact,
    ResearchItem,
    ResearchKind,
    SourceTier,
)
from bottom_hunter.src.research_storage import ResearchStore


NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, payload=None, text="", content=b""):
        self._payload = payload
        self.text = text
        self.content = content or text.encode()

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response

    def get(self, *_args, **_kwargs):
        return self.response


def test_research_store_deduplicates_and_builds_snapshot(tmp_path) -> None:
    store = ResearchStore(tmp_path / "signals.db")
    fact = FinancialFact(
        "AAPL", "US", date(2026, 6, 30), NOW, "营业收入", 100.0,
        "USD", "USD", "SEC XBRL", "https://example.com/filing", "10-Q",
    )
    item = ResearchItem(
        ResearchKind.NEWS, SourceTier.PROFESSIONAL, "AAPL", "US", "Apple news",
        NOW, "Example", "https://example.com/news",
    )
    store.save_financial_facts([fact])
    store.save_items([item, item])
    snapshot = store.snapshot("AAPL", "US")
    assert len(snapshot.financial_facts) == 1
    assert len(snapshot.news) == 1
    assert snapshot.news[0].title == "Apple news"


def test_eastmoney_financial_and_filing_parsing() -> None:
    financial_payload = {
        "data": [
            {
                "REPORT_DATE": "2026-06-30 00:00:00",
                "NOTICE_DATE": "2026-08-15 00:00:00",
                "REPORT_DATE_NAME": "2026中报",
                "CURRENCY": "CNY",
                "TOTALOPERATEREVE": 1000,
                "PARENTNETPROFIT": 120,
                "ROEJQ": 12.5,
            }
        ]
    }
    provider = EastmoneyResearchProvider(FakeSession(FakeResponse(financial_payload)))
    asset = {"symbol": "600519.SS", "market": "CN"}
    facts = provider.financial_facts(asset)
    assert {item.metric for item in facts} == {"营业收入", "归母净利润", "ROE"}
    assert all(item.available_at.date() == date(2026, 8, 15) for item in facts)

    filing_payload = {
        "data": {
            "list": [
                {
                    "art_code": "AN1",
                    "title": "测试半年报",
                    "display_time": "2026-08-14 20:41:29:276",
                    "notice_date": "2026-08-15 00:00:00",
                    "columns": [{"column_name": "定期报告"}],
                }
            ]
        }
    }
    provider = EastmoneyResearchProvider(FakeSession(FakeResponse(filing_payload)))
    filings = provider.filings(asset)
    assert filings[0].item_id == "AN1"
    assert filings[0].published_at.year == 2026


def test_fred_observation_and_macro_mapping() -> None:
    response = FakeResponse(
        text="observation_date,TEST\n2026-06-01,100\n2026-07-01,103\n"
    )
    provider = FredMacroProvider(FakeSession(response))
    item = provider.observation(MacroSeriesDefinition("TEST", "测试", "经济增长", "点", 1))
    assert item.change == 3
    assert item.signal == 2
    regime = macro_regime([item])
    impact = macro_sector_impact(
        regime,
        {"经济增长": {"positive": ("工业",), "negative": ("公用事业",)}},
    )
    assert regime["label"] == "risk-on"
    assert impact["benefiting"] == ["工业"]


def test_cached_fundamental_is_point_in_time_and_ignores_news(tmp_path) -> None:
    store = ResearchStore(tmp_path / "signals.db")
    metrics = {
        "营收同比": 8.0,
        "净利润同比": 10.0,
        "ROE": 15.0,
        "资产负债率": 35.0,
    }
    facts = [
        FinancialFact(
            "600519.SS", "CN", date(2026, 6, 30), datetime(2026, 8, 15, tzinfo=timezone.utc),
            metric, value, "%", "CNY", "财报", "https://example.com", "2026中报",
        )
        for metric, value in metrics.items()
    ]
    store.save_financial_facts(facts)
    provider = CachedResearchFundamentalProvider(store)
    instrument = Instrument("600519.SS", "贵州茅台", "CN")
    assert provider.get_fundamental_data(instrument, date(2026, 8, 14)).score is None
    assert provider.get_fundamental_data(instrument, date(2026, 8, 16)).score == 2


def test_manual_research_import(tmp_path) -> None:
    config = ResearchConfig.load()
    store = ResearchStore(tmp_path / "signals.db")
    service = ResearchService(tmp_path, store=store, config=config, session=FakeSession(None))
    source = tmp_path / "opinions.csv"
    source.write_text(
        "kind,tier,symbol,title,source,url,published_at,summary\n"
        "community_opinion,community,AAPL,看多 Apple,雪球,https://xueqiu.com/1,2026-08-27,增长超预期\n",
        encoding="utf-8",
    )
    assert service.import_items(source) == 1
    items = store.research_items("AAPL")
    assert items[0].tier == SourceTier.COMMUNITY
    assert items[0].sentiment == "bullish"
