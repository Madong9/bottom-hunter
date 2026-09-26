from datetime import datetime, timedelta, timezone

from app.agents.base import BaseAgent
from app.schemas.agents import (
    QuestionUnderstandingInput,
    QuestionUnderstandingOutput,
    TimeRange,
)
from app.schemas.common import Intent


class QuestionUnderstandingAgent(
    BaseAgent[QuestionUnderstandingInput, QuestionUnderstandingOutput]
):
    name = "question_understanding"

    def run(
        self, agent_input: QuestionUnderstandingInput
    ) -> QuestionUnderstandingOutput:
        query = agent_input.query.strip()
        entities = agent_input.resolution.entities
        symbols = [entity.symbol for entity in entities]

        intent = agent_input.routing.intent
        dimensions = self._detect_dimensions(intent)
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=365)).date() if "近一年" in query else None

        return QuestionUnderstandingOutput(
            normalized_query=query,
            symbols=symbols,
            intent=intent,
            time_range=TimeRange(start=start, end=now.date()),
            dimensions=dimensions,
            entities=entities,
        )

    @staticmethod
    def _detect_dimensions(intent: Intent) -> list[str]:
        dimensions_by_intent = {
            Intent.OVERVIEW: ["company", "business", "industry", "financial", "risk"],
            Intent.STOCK_COMPARISON: [
                "company",
                "financial",
                "valuation",
                "comparison",
                "risk",
            ],
            Intent.FUNDAMENTAL_ANALYSIS: [
                "financial",
                "profitability",
                "cash_flow",
                "balance_sheet",
            ],
            Intent.VALUATION_ANALYSIS: [
                "valuation",
                "financial",
                "peer_benchmark",
                "risk",
            ],
            Intent.RISK_ANALYSIS: ["financial", "news", "risk", "uncertainty"],
            Intent.NEWS_IMPACT: ["news", "event_impact", "source_quality", "risk"],
        }
        dimensions = dimensions_by_intent[intent]
        if intent == Intent.NEWS_IMPACT:
            return dimensions
        return dimensions
