from pydantic import Field

from app.schemas.agents import (
    AIAnalysisItem,
    FutureScenario,
)
from app.schemas.common import StrictModel


class AnalysisNarrative(StrictModel):
    summary: str = Field(min_length=10, max_length=800)
    ai_analysis: list[AIAnalysisItem] = Field(min_length=1, max_length=4)
    scenarios: list[FutureScenario] = Field(min_length=1, max_length=4)
    uncertainties: list[str] = Field(min_length=1, max_length=5)
    future_watch: list[str] = Field(min_length=1, max_length=6)
