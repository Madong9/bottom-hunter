from datetime import datetime, timezone
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel

from app.agents import (
    AnalysisAgent,
    DataRetrievalAgent,
    NewsFilterAgent,
    QueryRouterAgent,
    QuestionUnderstandingAgent,
    RiskReviewAgent,
    StockEntityResolverAgent,
)
from app.agents.base import BaseAgent
from app.llm.base import AnalysisEnhancer
from app.providers.base import FinancialDataProvider
from app.schemas.agents import (
    AnalysisInput,
    DataRetrievalInput,
    NewsFilterInput,
    QueryRouterInput,
    QuestionUnderstandingInput,
    RiskReviewInput,
    StockEntityResolverInput,
)
from app.schemas.common import AgentRun, AgentStatus
from app.schemas.research import ResearchResult

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)

MOCK_DISCLAIMER = (
    "本报告由 AI 基于 Mock 数据自动生成，仅用于产品演示和技术交流，"
    "不构成任何投资建议、收益承诺或交易依据。金融市场有风险，投资需谨慎。"
)

REAL_DATA_DISCLAIMER = (
    "本报告由 AI 基于公开市场数据自动生成，数据可能延迟、缺失或存在口径差异，"
    "仅用于个人研究和信息理解，不构成任何投资建议、收益承诺或交易依据。"
    "金融市场有风险，重要信息请以交易所和公司正式公告为准。"
)


class WorkflowAgentError(Exception):
    def __init__(self, cause: Exception, agent_runs: list[AgentRun]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.agent_runs = agent_runs


class ResearchWorkflow:
    def __init__(
        self,
        provider: FinancialDataProvider,
        enhancer: AnalysisEnhancer | None = None,
        entity_resolver: StockEntityResolverAgent | None = None,
    ) -> None:
        self._provider = provider
        self._router_agent = QueryRouterAgent()
        self._entity_resolver_agent = entity_resolver or StockEntityResolverAgent(
            provider
        )
        self._understanding_agent = QuestionUnderstandingAgent()
        self._retrieval_agent = DataRetrievalAgent(provider)
        self._news_agent = NewsFilterAgent()
        self._analysis_agent = AnalysisAgent(enhancer)
        self._risk_agent = RiskReviewAgent()

    def run(self, query: str) -> tuple[ResearchResult, list[AgentRun]]:
        runs: list[AgentRun] = []
        try:
            routing = self._run_agent(
                self._router_agent,
                QueryRouterInput(query=query),
                runs,
            )
            entity_resolution = self._run_agent(
                self._entity_resolver_agent,
                StockEntityResolverInput(query=query, routing=routing),
                runs,
            )
            understanding = self._run_agent(
                self._understanding_agent,
                QuestionUnderstandingInput(
                    query=query,
                    routing=routing,
                    resolution=entity_resolution,
                ),
                runs,
            )
            data = self._run_agent(
                self._retrieval_agent,
                DataRetrievalInput(understanding=understanding),
                runs,
            )
            candidates = self._provider.get_news(understanding.symbols)
            news = self._run_agent(
                self._news_agent,
                NewsFilterInput(understanding=understanding, candidates=candidates),
                runs,
            )
            analysis = self._run_agent(
                self._analysis_agent,
                AnalysisInput(
                    question=query,
                    understanding=understanding,
                    data=data,
                    news=news,
                ),
                runs,
            )
            available_source_ids = [
                source.source_id for source in [*data.sources, *news.sources]
            ]
            risk_review = self._run_agent(
                self._risk_agent,
                RiskReviewInput(
                    question=query,
                    analysis=analysis,
                    available_source_ids=available_source_ids,
                ),
                runs,
            )
        except Exception as exc:
            raise WorkflowAgentError(exc, runs) from exc

        return (
            ResearchResult(
                routing=routing,
                entity_resolution=entity_resolution,
                understanding=understanding,
                data=data,
                news=news,
                analysis=analysis,
                risk_review=risk_review,
                disclaimer=(
                    REAL_DATA_DISCLAIMER
                    if self._provider.is_real_data
                    else MOCK_DISCLAIMER
                ),
            ),
            runs,
        )

    @staticmethod
    def _run_agent(
        agent: BaseAgent[InputT, OutputT],
        agent_input: InputT,
        runs: list[AgentRun],
    ) -> OutputT:
        started_at = datetime.now(timezone.utc)
        started_perf = perf_counter()
        run = AgentRun(
            agent=agent.name,
            status=AgentStatus.RUNNING,
            started_at=started_at,
        )
        runs.append(run)
        try:
            output = agent.run(agent_input)
        except Exception as exc:
            completed_at = datetime.now(timezone.utc)
            runs[-1] = run.model_copy(
                update={
                    "status": AgentStatus.FAILED,
                    "completed_at": completed_at,
                    "duration_ms": int((perf_counter() - started_perf) * 1000),
                    "error": str(exc),
                }
            )
            raise

        runs[-1] = run.model_copy(
            update={
                "status": AgentStatus.COMPLETED,
                "completed_at": datetime.now(timezone.utc),
                "duration_ms": int((perf_counter() - started_perf) * 1000),
            }
        )
        return output
