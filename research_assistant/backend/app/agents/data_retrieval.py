from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.core.exceptions import DataProviderError
from app.providers.base import FinancialDataProvider
from app.schemas.agents import DataRetrievalInput, DataRetrievalOutput
from app.schemas.common import SourceReference


class DataRetrievalAgent(BaseAgent[DataRetrievalInput, DataRetrievalOutput]):
    name = "data_retrieval"

    def __init__(self, provider: FinancialDataProvider) -> None:
        self._provider = provider

    def run(self, agent_input: DataRetrievalInput) -> DataRetrievalOutput:
        stocks = []
        missing_fields = []
        sources = []
        retrieved_at = datetime.now(timezone.utc)

        for symbol in agent_input.understanding.symbols:
            try:
                stock = self._provider.get_stock(symbol)
            except DataProviderError as exc:
                missing_fields.append(f"{symbol}: 数据源暂时不可用（{exc}）")
                continue
            if stock is None:
                missing_fields.append(f"{symbol}:all")
                continue
            stocks.append(stock)
            financial_values = stock.financial.model_dump()
            for field, value in financial_values.items():
                if field != "symbol" and value is None:
                    missing_fields.append(f"{symbol}:{field}")
            sources.extend(
                [
                    SourceReference(
                        source_id=f"quote:{symbol}",
                        name=f"{self._provider.provider_name} 行情 - {stock.company.name}",
                        source_type="market_quote",
                        retrieved_at=retrieved_at,
                        as_of=stock.quote.as_of,
                        url=self._provider.source_url(symbol),
                    ),
                    SourceReference(
                        source_id=f"financial:{symbol}",
                        name=f"{self._provider.provider_name} 财务数据 - {stock.company.name}",
                        source_type="financial_statement",
                        retrieved_at=retrieved_at,
                        url=self._provider.source_url(symbol),
                    ),
                ]
            )

        return DataRetrievalOutput(
            stocks=stocks,
            missing_fields=missing_fields,
            sources=sources,
        )
