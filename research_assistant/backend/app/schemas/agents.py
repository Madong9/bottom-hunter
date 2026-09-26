from datetime import date, datetime

from pydantic import Field

from app.schemas.common import (
    EvidenceBalance,
    Intent,
    ReviewStatus,
    RiskLevel,
    SourceReference,
    StrictModel,
)


class TimeRange(StrictModel):
    start: date | None = None
    end: date | None = None


class QueryRouterInput(StrictModel):
    query: str = Field(min_length=2, max_length=1000)


class QueryRouterOutput(StrictModel):
    intent: Intent
    category: str
    confidence: float = Field(ge=0, le=1)
    reason: str
    matched_signals: list[str] = Field(default_factory=list)
    output_requirements: list[str] = Field(min_length=1)


class StockEntityResolverInput(StrictModel):
    query: str = Field(min_length=2, max_length=1000)
    routing: QueryRouterOutput


class ResolvedStockEntity(StrictModel):
    symbol: str
    name: str
    market: str
    industry: str
    matched_term: str
    match_source: str
    confidence: float = Field(ge=0, le=1)


class StockEntityResolverOutput(StrictModel):
    entities: list[ResolvedStockEntity] = Field(min_length=1)
    unresolved_terms: list[str] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_reason: str | None = None


class QuestionUnderstandingInput(StrictModel):
    query: str = Field(min_length=2, max_length=1000)
    routing: QueryRouterOutput
    resolution: StockEntityResolverOutput


class QuestionUnderstandingOutput(StrictModel):
    normalized_query: str
    symbols: list[str]
    intent: Intent
    time_range: TimeRange
    dimensions: list[str]
    entities: list[ResolvedStockEntity] = Field(default_factory=list)
    language: str = "zh-CN"
    clarification_needed: bool = False
    clarification_reason: str | None = None


class DataRetrievalInput(StrictModel):
    understanding: QuestionUnderstandingOutput


class CompanyProfile(StrictModel):
    symbol: str
    name: str
    market: str
    industry: str
    description: str


class MarketQuote(StrictModel):
    symbol: str
    price: float = Field(gt=0)
    currency: str
    change_percent: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    market_cap_billion: float | None = None
    as_of: datetime


class FinancialSnapshot(StrictModel):
    symbol: str
    fiscal_period: str
    revenue_billion: float | None = None
    revenue_growth_percent: float | None = None
    net_profit_billion: float | None = None
    net_profit_growth_percent: float | None = None
    gross_margin_percent: float | None = None
    roe_percent: float | None = None
    debt_ratio_percent: float | None = None
    operating_cash_flow_billion: float | None = None


class StockDataBundle(StrictModel):
    company: CompanyProfile
    quote: MarketQuote
    financial: FinancialSnapshot


class DataRetrievalOutput(StrictModel):
    stocks: list[StockDataBundle]
    missing_fields: list[str] = Field(default_factory=list)
    sources: list[SourceReference]


class NewsItem(StrictModel):
    news_id: str
    symbols: list[str]
    title: str
    summary: str
    source: str
    published_at: datetime
    url: str
    sentiment: str
    credibility: float = Field(ge=0, le=1)


class FilteredNewsItem(NewsItem):
    relevance_score: float = Field(ge=0, le=1)
    timeliness_score: float = Field(ge=0, le=1)
    importance_score: float = Field(ge=0, le=1)
    composite_score: float = Field(ge=0, le=1)
    event_type: str
    retention_reason: str
    attention_reason: str


class NewsFilterStats(StrictModel):
    candidate_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    low_relevance_count: int = Field(ge=0)
    low_credibility_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)


class NewsFilterInput(StrictModel):
    understanding: QuestionUnderstandingOutput
    candidates: list[NewsItem]


class NewsFilterOutput(StrictModel):
    selected: list[FilteredNewsItem]
    rejected_count: int = Field(ge=0)
    stats: NewsFilterStats
    sources: list[SourceReference]


class AnalysisInput(StrictModel):
    question: str
    understanding: QuestionUnderstandingOutput
    data: DataRetrievalOutput
    news: NewsFilterOutput


class AnalysisSection(StrictModel):
    title: str
    content: str
    evidence_ids: list[str]


class ConfirmedFact(StrictModel):
    fact_id: str
    content: str
    source_ids: list[str] = Field(min_length=1)


class AIAnalysisItem(StrictModel):
    content: str
    based_on_fact_ids: list[str] = Field(min_length=1)


class FutureScenario(StrictModel):
    condition: str
    possible_outcome: str
    based_on_fact_ids: list[str] = Field(min_length=1)


class CompanyComparison(StrictModel):
    symbol: str
    company_name: str
    market: str = ""
    industry: str = ""
    price: float | None = None
    currency: str = ""
    revenue_growth_percent: float | None = None
    net_profit_growth_percent: float | None = None
    roe_percent: float | None = None
    pe_ttm: float | None = None
    positive_factor: str
    main_risk: str
    business_characteristics: str


class InvestorFocusGuide(StrictModel):
    company_name: str
    questions: list[str] = Field(min_length=1)


class CompanyPortrait(StrictModel):
    symbol: str
    company_name: str
    what_it_does: str
    core_business: str
    industry: str
    business_characteristics: str


class TermExplanation(StrictModel):
    term: str
    professional_definition: str
    plain_language_explanation: str


class FollowUpQuestion(StrictModel):
    label: str
    query: str


class AnalysisOutput(StrictModel):
    title: str
    summary: str
    visible_modules: list[str] = Field(default_factory=list)
    evidence_balance: EvidenceBalance
    investor_focus: list[InvestorFocusGuide]
    company_portraits: list[CompanyPortrait]
    term_explanations: list[TermExplanation]
    facts: list[ConfirmedFact]
    ai_analysis: list[AIAnalysisItem]
    scenarios: list[FutureScenario]
    uncertainties: list[str]
    positive_factors: list[str]
    negative_factors: list[str]
    pending_verification: list[str]
    future_watch: list[str]
    follow_up_questions: list[FollowUpQuestion]
    comparison: list[CompanyComparison]
    comparison_notice: str | None = None
    sections: list[AnalysisSection]
    citations: list[SourceReference]
    generated_at: datetime
    analysis_method: str = "rule_based"
    analysis_warnings: list[str] = Field(default_factory=list)


class RiskReviewInput(StrictModel):
    question: str
    analysis: AnalysisOutput
    available_source_ids: list[str]


class ReviewCheck(StrictModel):
    check_id: str
    label: str
    passed: bool
    detail: str


class RiskReviewOutput(StrictModel):
    status: ReviewStatus
    risk_level: RiskLevel
    issues: list[str]
    required_revisions: list[str]
    disclaimer_required: bool
    evidence_coverage_rate: float = Field(ge=0, le=1)
    checks: list[ReviewCheck]
    reviewed_at: datetime
