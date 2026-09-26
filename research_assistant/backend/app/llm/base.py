from typing import Protocol

from app.schemas.agents import AnalysisOutput


class AnalysisEnhancer(Protocol):
    def enhance(self, question: str, draft: AnalysisOutput) -> AnalysisOutput:
        """Improve narrative fields without changing facts, metrics or citations."""
        ...
