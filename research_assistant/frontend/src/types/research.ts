export type AgentName =
  | "query_router"
  | "stock_entity_resolver"
  | "question_understanding"
  | "data_retrieval"
  | "news_filter"
  | "analysis"
  | "risk_review";

export interface SourceReference {
  source_id: string;
  name: string;
  source_type: string;
  retrieved_at: string;
  as_of: string | null;
  url: string | null;
}

export interface AgentRun {
  agent: AgentName;
  status: "pending" | "running" | "completed" | "failed";
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  error: string | null;
}

export interface Understanding {
  normalized_query: string;
  symbols: string[];
  intent: string;
  time_range: { start: string | null; end: string | null };
  dimensions: string[];
  entities?: ResolvedStockEntity[];
  language: string;
  clarification_needed: boolean;
  clarification_reason: string | null;
}

export interface ResolvedStockEntity {
  symbol: string;
  name: string;
  market: string;
  industry: string;
  matched_term: string;
  match_source: string;
  confidence: number;
}

export interface StockData {
  company: {
    symbol: string;
    name: string;
    market: string;
    industry: string;
    description: string;
  };
  quote: {
    symbol: string;
    price: number;
    currency: string;
    change_percent: number | null;
    pe_ttm: number | null;
    pb: number | null;
    market_cap_billion: number | null;
    as_of: string;
  };
  financial: {
    symbol: string;
    fiscal_period: string;
    revenue_billion: number | null;
    revenue_growth_percent: number | null;
    net_profit_billion: number | null;
    net_profit_growth_percent: number | null;
    gross_margin_percent: number | null;
    roe_percent: number | null;
    debt_ratio_percent: number | null;
    operating_cash_flow_billion: number | null;
  };
}

export interface NewsItem {
  news_id: string;
  symbols: string[];
  title: string;
  summary: string;
  source: string;
  published_at: string;
  url: string;
  sentiment: "positive" | "negative" | "neutral";
  credibility: number;
  relevance_score: number;
  timeliness_score: number;
  importance_score: number;
  composite_score: number;
  event_type: string;
  retention_reason: string;
  attention_reason: string;
}

export interface AnalysisSection {
  title: string;
  content: string;
  evidence_ids: string[];
}

export interface ConfirmedFact {
  fact_id: string;
  content: string;
  source_ids: string[];
}

export interface AIAnalysisItem {
  content: string;
  based_on_fact_ids: string[];
}

export interface FutureScenario {
  condition: string;
  possible_outcome: string;
  based_on_fact_ids: string[];
}

export interface CompanyComparison {
  symbol: string;
  company_name: string;
  market?: string;
  industry?: string;
  price?: number | null;
  currency?: string;
  revenue_growth_percent: number | null;
  net_profit_growth_percent: number | null;
  roe_percent: number | null;
  pe_ttm: number | null;
  positive_factor: string;
  main_risk: string;
  business_characteristics: string;
}

export interface InvestorFocusGuide {
  company_name: string;
  questions: string[];
}

export interface CompanyPortrait {
  symbol: string;
  company_name: string;
  what_it_does: string;
  core_business: string;
  industry: string;
  business_characteristics: string;
}

export interface TermExplanation {
  term: string;
  professional_definition: string;
  plain_language_explanation: string;
}

export interface FollowUpQuestion {
  label: string;
  query: string;
}

export interface ResearchResult {
  routing?: {
    intent: string;
    category: string;
    confidence: number;
    reason: string;
    matched_signals: string[];
    output_requirements: string[];
  } | null;
  entity_resolution?: {
    entities: ResolvedStockEntity[];
    unresolved_terms: string[];
    clarification_needed: boolean;
    clarification_reason: string | null;
  } | null;
  understanding: Understanding;
  data: {
    stocks: StockData[];
    missing_fields: string[];
    sources: SourceReference[];
  };
  news: {
    selected: NewsItem[];
    rejected_count: number;
    stats: {
      candidate_count: number;
      duplicate_count: number;
      low_relevance_count: number;
      low_credibility_count: number;
      stale_count: number;
      selected_count: number;
    };
    sources: SourceReference[];
  };
  analysis: {
    title: string;
    summary: string;
    visible_modules?: ReportModule[];
    evidence_balance: "积极因素较多" | "积极与负面因素并存" | "负面因素较多" | "证据不足";
    investor_focus: InvestorFocusGuide[];
    company_portraits: CompanyPortrait[];
    term_explanations: TermExplanation[];
    facts: ConfirmedFact[];
    ai_analysis: AIAnalysisItem[];
    scenarios: FutureScenario[];
    uncertainties: string[];
    positive_factors: string[];
    negative_factors: string[];
    pending_verification: string[];
    future_watch: string[];
    follow_up_questions: FollowUpQuestion[];
    comparison: CompanyComparison[];
    comparison_notice: string | null;
    sections: AnalysisSection[];
    citations: SourceReference[];
    generated_at: string;
    analysis_method: string;
    analysis_warnings: string[];
  };
  risk_review: {
    status: "approved" | "rejected";
    risk_level: "low" | "medium" | "high";
    issues: string[];
    required_revisions: string[];
    disclaimer_required: boolean;
    evidence_coverage_rate: number;
    checks: Array<{
      check_id: string;
      label: string;
      passed: boolean;
      detail: string;
    }>;
    reviewed_at: string;
  };
  disclaimer: string;
}

export type ReportModule =
  | "investor_guide"
  | "company_profile"
  | "financial_snapshot"
  | "valuation"
  | "comparison"
  | "news"
  | "facts"
  | "analysis"
  | "future_watch"
  | "risk"
  | "risk_review"
  | "glossary"
  | "sources";

export interface ResearchTask {
  task_id: string;
  query: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  completed_at: string | null;
  agent_runs: AgentRun[];
  result: ResearchResult | null;
  error: string | null;
}

export interface ResearchTaskList {
  items: ResearchTask[];
  total: number;
}

export interface HealthStatus {
  status: string;
  service: string;
  timestamp: string;
  data_provider: string;
  real_data: boolean;
  qwen_enabled: boolean;
  qwen_configured: boolean;
  qwen_model: string;
  history_persistence: boolean;
}

export interface ConversationItem {
  id: string;
  question: string;
  task: ResearchTask | null;
  error: string | null;
  createdAt: Date;
}
