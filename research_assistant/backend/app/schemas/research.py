from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.agents import (
    AnalysisOutput,
    DataRetrievalOutput,
    NewsFilterOutput,
    QueryRouterOutput,
    QuestionUnderstandingOutput,
    RiskReviewOutput,
    StockEntityResolverOutput,
)
from app.schemas.common import AgentRun, StrictModel, TaskStatus


class ResearchRequest(StrictModel):
    query: str = Field(min_length=2, max_length=1000)


class ResearchResult(StrictModel):
    # Optional so research history written before Query Router was introduced
    # remains readable from the local SQLite repository.
    routing: QueryRouterOutput | None = None
    entity_resolution: StockEntityResolverOutput | None = None
    understanding: QuestionUnderstandingOutput
    data: DataRetrievalOutput
    news: NewsFilterOutput
    analysis: AnalysisOutput
    risk_review: RiskReviewOutput
    disclaimer: str


class ResearchTask(StrictModel):
    task_id: UUID
    query: str
    status: TaskStatus
    created_at: datetime
    completed_at: datetime | None = None
    agent_runs: list[AgentRun] = Field(default_factory=list)
    result: ResearchResult | None = None
    error: str | None = None


class ResearchTaskList(StrictModel):
    items: list[ResearchTask]
    total: int


class StockSearchItem(StrictModel):
    symbol: str
    name: str
    market: str
    industry: str
