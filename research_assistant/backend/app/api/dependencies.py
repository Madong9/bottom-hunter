from functools import lru_cache

from app.agents import StockEntityResolverAgent
from app.core.config import get_settings
from app.core.exceptions import ConfigurationError
from app.llm import QwenAnalysisEnhancer
from app.orchestration.workflow import ResearchWorkflow
from app.providers import MockFinancialDataProvider, YFinanceProvider
from app.repositories import InMemoryTaskRepository, SQLiteTaskRepository
from app.services import ResearchService


@lru_cache
def get_research_service() -> ResearchService:
    settings = get_settings()
    if settings.data_provider == "mock":
        provider = MockFinancialDataProvider()
    elif settings.data_provider == "yfinance":
        provider = YFinanceProvider()
    else:
        raise ConfigurationError(f"不支持的 DATA_PROVIDER：{settings.data_provider}")

    enhancer = None
    if settings.qwen_enabled and settings.qwen_api_key:
        enhancer = QwenAnalysisEnhancer(
            api_key=settings.qwen_api_key,
            model=settings.qwen_model,
            base_url=settings.qwen_base_url,
            timeout_seconds=settings.qwen_timeout_seconds,
        )
    entity_resolver = StockEntityResolverAgent(
        provider,
        cache_path=None
        if settings.database_path == ":memory:"
        else settings.database_path,
    )
    workflow = ResearchWorkflow(provider, enhancer, entity_resolver)
    repository = (
        InMemoryTaskRepository()
        if settings.database_path == ":memory:"
        else SQLiteTaskRepository(settings.database_path)
    )
    return ResearchService(
        workflow=workflow,
        provider=provider,
        repository=repository,
        entity_resolver=entity_resolver,
    )
