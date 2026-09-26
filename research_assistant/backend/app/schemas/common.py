from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Intent(str, Enum):
    OVERVIEW = "overview"
    FUNDAMENTAL_ANALYSIS = "fundamental_analysis"
    VALUATION_ANALYSIS = "valuation_analysis"
    NEWS_IMPACT = "news_impact"
    RISK_ANALYSIS = "risk_analysis"
    STOCK_COMPARISON = "stock_comparison"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceBalance(str, Enum):
    POSITIVE_FACTORS_DOMINANT = "积极因素较多"
    BALANCED = "积极与负面因素并存"
    NEGATIVE_FACTORS_DOMINANT = "负面因素较多"
    INSUFFICIENT = "证据不足"


class ReviewStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceReference(StrictModel):
    source_id: str
    name: str
    source_type: str
    retrieved_at: datetime
    as_of: datetime | None = None
    url: str | None = None


class AgentRun(StrictModel):
    agent: str
    status: AgentStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    error: str | None = None
