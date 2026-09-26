import json
from functools import cached_property
from pathlib import Path
from typing import Any

from app.providers.base import FinancialDataProvider
from app.schemas.agents import (
    CompanyProfile,
    FinancialSnapshot,
    MarketQuote,
    NewsItem,
    StockDataBundle,
)
from app.schemas.research import StockSearchItem


class MockFinancialDataProvider(FinancialDataProvider):
    """Loads deterministic financial fixtures shipped with the project."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path(__file__).resolve().parent.parent / "mock_data"

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def is_real_data(self) -> bool:
        return False

    def _load_json(self, filename: str) -> list[dict[str, Any]]:
        with (self._data_dir / filename).open(encoding="utf-8") as file:
            return json.load(file)

    @cached_property
    def _stocks(self) -> list[dict[str, Any]]:
        return self._load_json("stocks.json")

    @cached_property
    def _news(self) -> list[dict[str, Any]]:
        return self._load_json("news.json")

    def stock_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "symbol": stock["symbol"],
                "name": stock["name"],
                "market": stock["market"],
                "industry": stock["industry"],
                "aliases": list(stock["aliases"]),
            }
            for stock in self._stocks
        ]

    def resolve_symbols(self, query: str) -> list[str]:
        normalized = query.casefold()
        symbols = []
        for stock in self.stock_catalog():
            names = [stock["symbol"], stock["name"], *stock["aliases"]]
            if any(name.casefold() in normalized for name in names):
                symbols.append(stock["symbol"])
        return symbols

    def source_url(self, symbol: str) -> str | None:
        return None

    def get_stock(self, symbol: str) -> StockDataBundle | None:
        stock = next((item for item in self._stocks if item["symbol"] == symbol), None)
        if stock is None:
            return None
        quote = dict(stock["quote"], symbol=symbol)
        financial = dict(stock["financial"], symbol=symbol)
        return StockDataBundle(
            company=CompanyProfile(
                symbol=symbol,
                name=stock["name"],
                market=stock["market"],
                industry=stock["industry"],
                description=stock["description"],
            ),
            quote=MarketQuote.model_validate(quote),
            financial=FinancialSnapshot.model_validate(financial),
        )

    def get_news(self, symbols: list[str]) -> list[NewsItem]:
        symbol_set = set(symbols)
        return [
            NewsItem.model_validate(item)
            for item in self._news
            if symbol_set.intersection(item["symbols"])
        ]

    def search_stocks(self, query: str) -> list[StockSearchItem]:
        needle = query.strip().casefold()
        results = []
        for stock in self._stocks:
            searchable = [stock["symbol"], stock["name"], *stock["aliases"]]
            if not needle or any(needle in value.casefold() for value in searchable):
                results.append(
                    StockSearchItem(
                        symbol=stock["symbol"],
                        name=stock["name"],
                        market=stock["market"],
                        industry=stock["industry"],
                    )
                )
        return results
