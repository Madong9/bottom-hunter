from abc import ABC, abstractmethod
from typing import Any

from app.schemas.agents import NewsItem, StockDataBundle
from app.schemas.research import StockSearchItem


class FinancialDataProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_real_data(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stock_catalog(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def resolve_symbols(self, query: str) -> list[str]:
        """Resolve canonical symbols from a natural-language question."""
        raise NotImplementedError

    @abstractmethod
    def source_url(self, symbol: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def get_stock(self, symbol: str) -> StockDataBundle | None:
        raise NotImplementedError

    @abstractmethod
    def get_news(self, symbols: list[str]) -> list[NewsItem]:
        raise NotImplementedError

    @abstractmethod
    def search_stocks(self, query: str) -> list[StockSearchItem]:
        raise NotImplementedError
