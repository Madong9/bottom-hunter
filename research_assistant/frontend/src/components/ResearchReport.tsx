import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  BookOpen,
  BrainCircuit,
  Building2,
  Check,
  CircleHelp,
  ExternalLink,
  FileCheck2,
  GraduationCap,
  Route,
  Search,
  Scale,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import type {
  CompanyComparison,
  NewsItem,
  ReportModule,
  ResearchResult,
  SourceReference,
  StockData,
} from "../types/research";
import { readableText } from "../utils/readableText";

const currencySymbol: Record<string, string> = { CNY: "¥", USD: "$", HKD: "HK$" };

const moduleLabels: Record<ReportModule, string> = {
  investor_guide: "研究问题",
  company_profile: "公司画像",
  financial_snapshot: "财务快照",
  valuation: "估值分析",
  comparison: "同行比较",
  news: "新闻解读",
  facts: "事实证据",
  analysis: "AI 分析",
  future_watch: "后续观察",
  risk: "风险因素",
  risk_review: "风险审核",
  glossary: "指标词典",
  sources: "数据来源",
};

const legacyModules: ReportModule[] = Object.keys(moduleLabels) as ReportModule[];
const legacyModulesByIntent: Record<string, ReportModule[]> = {
  overview: ["investor_guide", "company_profile", "financial_snapshot", "news", "facts", "analysis", "future_watch", "risk", "risk_review", "glossary", "sources"],
  stock_comparison: ["investor_guide", "comparison", "facts", "analysis", "future_watch", "risk_review", "sources"],
  fundamental_analysis: ["investor_guide", "financial_snapshot", "facts", "analysis", "future_watch", "risk", "risk_review", "glossary", "sources"],
  valuation_analysis: ["investor_guide", "financial_snapshot", "valuation", "facts", "analysis", "future_watch", "risk", "risk_review", "glossary", "sources"],
  risk_analysis: ["investor_guide", "news", "facts", "analysis", "future_watch", "risk", "risk_review", "sources"],
  news_impact: ["news", "facts", "analysis", "future_watch", "risk", "risk_review", "sources"],
};

function number(value: number | null | undefined, digits = 1) {
  if (value == null) return "—";
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function percent(value: number | null | undefined, digits = 1) {
  return value == null ? "—" : `${number(value, digits)}%`;
}

function stockSourceIds(stock: StockData) {
  return [`quote:${stock.company.symbol}`, `financial:${stock.company.symbol}`];
}

function factSourceIds(factIds: string[], facts: ResearchResult["analysis"]["facts"]) {
  const ids = new Set(factIds);
  return [...new Set(facts.filter((fact) => ids.has(fact.fact_id)).flatMap((fact) => fact.source_ids))];
}

function StockCard({ stock, sources }: { stock: StockData; sources: SourceReference[] }) {
  const up = stock.quote.change_percent != null && stock.quote.change_percent >= 0;
  return (
    <article className="stock-card">
      <div className="stock-card-head">
        <div>
          <strong>{stock.company.name}</strong>
          <span>{stock.company.symbol} · {stock.company.market}</span>
        </div>
        <div className={`quote-change ${stock.quote.change_percent == null ? "" : up ? "positive" : "negative"}`}>
          {stock.quote.change_percent != null && (up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />)}
          {stock.quote.change_percent == null ? "涨跌待确认" : `${up ? "+" : ""}${number(stock.quote.change_percent, 2)}%`}
        </div>
      </div>
      <div className="stock-price">
        <span>{currencySymbol[stock.quote.currency] ?? stock.quote.currency}</span>
        {number(stock.quote.price, 2)}
      </div>
      <div className="metric-grid">
        <div><span>PE (TTM)</span><strong>{stock.quote.pe_ttm != null ? `${number(stock.quote.pe_ttm)}x` : "—"}</strong></div>
        <div><span>营收增速</span><strong>{percent(stock.financial.revenue_growth_percent)}</strong></div>
        <div><span>净利增速</span><strong>{percent(stock.financial.net_profit_growth_percent)}</strong></div>
        <div><span>ROE</span><strong>{percent(stock.financial.roe_percent)}</strong></div>
      </div>
      <div className="data-time">数据截至 {new Date(stock.quote.as_of).toLocaleDateString("zh-CN")}</div>
      <SourceTags sourceIds={stockSourceIds(stock)} sources={sources} />
    </article>
  );
}

function ScoreMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="score-metric">
      <div><span>{label}</span><strong>{Math.round(value * 100)}</strong></div>
      <div className="score-track"><i style={{ width: `${value * 100}%` }} /></div>
    </div>
  );
}

function NewsRow({ item }: { item: NewsItem }) {
  const sentimentText = item.sentiment === "positive" ? "积极事件" : item.sentiment === "negative" ? "负面事件" : "中性事件";
  return (
    <details className="news-row">
      <summary>
        <div className={`sentiment-dot sentiment-dot--${item.sentiment}`} />
        <div className="news-copy">
          <div className="news-title-line"><strong><a className="inline-news-source" href={item.url} target="_blank" rel="noreferrer">{readableText(item.title)} <ExternalLink size={11} /></a></strong></div>
          <div className="news-meta">
            <span>{readableText(item.source)}</span><span>{item.event_type}</span>
            <span className={`sentiment-text sentiment-text--${item.sentiment}`}>{sentimentText}</span>
          </div>
        </div>
        <div className="news-score"><strong>{Math.round(item.composite_score * 100)}</strong><span>综合分</span></div>
      </summary>
      <div className="news-detail">
        <p>{readableText(item.summary)}</p>
        <div className="news-score-grid">
          <ScoreMetric label="相关性" value={item.relevance_score} />
          <ScoreMetric label="来源可信度" value={item.credibility} />
          <ScoreMetric label="时效性" value={item.timeliness_score} />
          <ScoreMetric label="事件重要度" value={item.importance_score} />
          <ScoreMetric label="综合评分" value={item.composite_score} />
        </div>
        <div className="retention-reason"><Check size={13} /> <strong>保留原因：</strong>{item.retention_reason}</div>
        <div className="attention-reason"><CircleHelp size={13} /> <strong>为什么关注：</strong>{item.attention_reason}</div>
        <a href={item.url} target="_blank" rel="noreferrer">查看原始来源 <ExternalLink size={12} /></a>
      </div>
    </details>
  );
}

function NewsFunnel({ result }: { result: ResearchResult }) {
  const stats = result.news.stats;
  const steps = [
    ["候选新闻", stats.candidate_count],
    ["去重数量", stats.duplicate_count],
    ["低相关过滤", stats.low_relevance_count],
    ["低可信过滤", stats.low_credibility_count],
    ["过期过滤", stats.stale_count],
    ["最终保留", stats.selected_count],
  ] as const;
  return (
    <div className="filter-funnel" aria-label="新闻过滤统计">
      {steps.map(([label, count], index) => (
        <div className="funnel-fragment" key={label}>
          <div className={index === steps.length - 1 ? "funnel-node funnel-node--final" : "funnel-node"}>
            <strong>{count}</strong><span>{label}</span>
          </div>
          {index < steps.length - 1 && <ArrowRight size={13} />}
        </div>
      ))}
    </div>
  );
}

function ComparisonTable({ rows, sources }: { rows: CompanyComparison[]; sources: SourceReference[] }) {
  const tableRows: Array<[string, (item: CompanyComparison) => string, "quote" | "financial"]> = [
    ["上市市场", (item) => item.market || "—", "financial"],
    ["所属行业", (item) => item.industry || "—", "financial"],
    ["当前价格", (item) => item.price == null ? "—" : `${item.currency || ""} ${number(item.price, 2)}`.trim(), "quote"],
    ["营收增速", (item) => percent(item.revenue_growth_percent), "financial"],
    ["净利润增速", (item) => percent(item.net_profit_growth_percent), "financial"],
    ["ROE", (item) => percent(item.roe_percent), "financial"],
    ["PE (TTM)", (item) => item.pe_ttm == null ? "—" : `${number(item.pe_ttm)}x`, "quote"],
    ["当前主要积极因素", (item) => item.positive_factor, "financial"],
    ["当前主要风险", (item) => item.main_risk, "financial"],
    ["商业特征", (item) => item.business_characteristics, "financial"],
  ];
  return (
    <div className="comparison-wrap">
      <table className="comparison-table">
        <thead><tr><th>比较维度</th>{rows.map((item) => <th key={item.symbol}>{item.company_name}<span>{item.symbol}</span></th>)}</tr></thead>
        <tbody>
          {tableRows.map(([label, render, sourceKind]) => (
            <tr key={label}><th>{label}</th>{rows.map((item) => <td key={item.symbol}>
              <span>{render(item)}</span>
              <SourceTags sourceIds={[`${sourceKind}:${item.symbol}`]} sources={sources} />
            </td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValuationPanel({ stocks, sources }: { stocks: StockData[]; sources: SourceReference[] }) {
  return (
    <div className="valuation-grid">
      {stocks.map((stock) => {
        const pe = stock.quote.pe_ttm;
        const interpretation = pe == null
          ? "当前 PE 数据缺失，不宜得出高估或低估结论。"
          : pe > 30
            ? "PE 倍数较高，估值对增长预期和盈利变化可能更敏感。"
            : "PE 需结合行业、成长阶段和历史区间继续判断。";
        return (
          <article key={stock.company.symbol}>
            <div><strong>{stock.company.name}</strong><span>{stock.company.symbol}</span></div>
            <dl>
              <div><dt>PE (TTM)</dt><dd>{pe == null ? "—" : `${number(pe)}x`}</dd></div>
              <div><dt>PB</dt><dd>{stock.quote.pb == null ? "—" : `${number(stock.quote.pb)}x`}</dd></div>
              <div><dt>市值</dt><dd>{stock.quote.market_cap_billion == null ? "—" : `${number(stock.quote.market_cap_billion)} 十亿`}</dd></div>
              <div><dt>净利增速</dt><dd>{percent(stock.financial.net_profit_growth_percent)}</dd></div>
            </dl>
            <p>{interpretation}</p>
            <SourceTags sourceIds={stockSourceIds(stock)} sources={sources} />
          </article>
        );
      })}
    </div>
  );
}

function SourceTags({ sourceIds, sources }: { sourceIds: string[]; sources: SourceReference[] }) {
  const visibleSources = sourceIds
    .filter((sourceId, index) => sourceIds.indexOf(sourceId) === index)
    .map((sourceId) => sources.find((item) => item.source_id === sourceId))
    .filter((source): source is SourceReference => source !== undefined);
  if (!visibleSources.length) return null;
  return (
    <div className="fact-sources" aria-label="本段内容的资料来源">
      {visibleSources.map((source) => {
        return source.url ? (
          <a href={source.url} target="_blank" rel="noreferrer" key={source.source_id} title={`打开来源：${readableText(source.name)}`}><BookOpen size={10} />{readableText(source.name)}<ExternalLink size={10} /></a>
        ) : (
          <span key={source.source_id} title="该来源未提供可打开的网址"><BookOpen size={10} />{readableText(source.name)}</span>
        );
      })}
    </div>
  );
}

interface ResearchReportProps {
  result: ResearchResult;
  onFollowUp: (question: string) => void;
}

export function ResearchReport({ result, onFollowUp }: ResearchReportProps) {
  const approved = result.risk_review.status === "approved";
  const isComparison = result.understanding.intent === "stock_comparison";
  const isRiskAnalysis = result.understanding.intent === "risk_analysis";
  const guideTitle = isComparison ? "比较这些公司时看什么？" : isRiskAnalysis ? "这家公司的风险重点是什么？" : "这家公司当前需要了解什么？";
  const guideSubtitle = isComparison ? "使用统一口径观察差异，不用单项指标排名" : isRiskAnalysis ? "聚焦下行因素、触发条件和待验证事项" : "作为普通投资者，可以先从这些问题建立理解框架";
  const fallbackModules = legacyModulesByIntent[result.understanding.intent] ?? legacyModules;
  const modules = new Set<ReportModule>(result.analysis.visible_modules?.length ? result.analysis.visible_modules : fallbackModules);
  const show = (module: ReportModule) => modules.has(module);
  const hasCoreSection = show("company_profile") || show("financial_snapshot") || show("valuation") || show("glossary");
  const sectionKeys = [
    hasCoreSection && "core",
    (show("facts") || show("news")) && "evidence",
    show("analysis") && "analysis",
    show("future_watch") && "future",
    (show("risk") || show("risk_review")) && "risk",
  ].filter(Boolean) as string[];
  const sectionNumber = (key: string) => String(sectionKeys.indexOf(key) + 1).padStart(2, "0");
  const coreTitle = show("valuation") ? "估值与财务基础" : show("financial_snapshot") && !show("company_profile") ? "财务表现" : "公司当前画像";
  const factPrefixes: Partial<Record<string, string[]>> = {
    stock_comparison: ["fact-quote:", "fact-growth:", "fact-quality:"],
    fundamental_analysis: ["fact-growth:", "fact-quality:"],
    valuation_analysis: ["fact-quote:", "fact-growth:", "fact-quality:"],
    risk_analysis: ["fact-growth:", "fact-quality:", "fact-news:"],
    news_impact: ["fact-news:"],
  };
  const allowedFactPrefixes = factPrefixes[result.understanding.intent];
  const filteredFacts = allowedFactPrefixes
    ? result.analysis.facts.filter((fact) => allowedFactPrefixes.some((prefix) => fact.fact_id.startsWith(prefix)))
    : result.analysis.facts;
  const visibleFacts = allowedFactPrefixes ? filteredFacts : result.analysis.facts;
  const allVisibleFactIds = visibleFacts.map((fact) => fact.fact_id);
  const allVisibleSourceIds = factSourceIds(allVisibleFactIds, result.analysis.facts);
  const tocItems = [
    ...(show("investor_guide") ? [{ id: "investor-guide", label: guideTitle }] : []),
    ...(isComparison && show("comparison") && result.analysis.comparison.length > 1 ? [{ id: "intent-focus", label: "同行对比核心结果" }] : []),
    ...(isRiskAnalysis && show("risk") ? [{ id: "intent-focus", label: "风险扫描核心结果" }] : []),
    ...(hasCoreSection ? [{ id: "report-core", label: coreTitle }] : []),
    ...((show("facts") || show("news")) ? [{ id: "report-evidence", label: show("news") && !show("facts") ? "新闻证据" : "当前已确认事实" }] : []),
    ...(show("analysis") ? [{ id: "report-analysis", label: "AI 分析" }] : []),
    ...(show("future_watch") ? [{ id: "report-future", label: "后续观察与情景" }] : []),
    ...((show("risk") || show("risk_review")) ? [{ id: "report-risk", label: "风险因素与审核" }] : []),
  ];
  return (
    <div className="report">
      <div className="answer-header">
        <div><div className="eyebrow">EVIDENCE-BASED REPORT</div><h2>{result.analysis.title}</h2></div>
        <div className="evidence-badge"><Scale size={15} /><span>当前证据结构</span><strong>{result.analysis.evidence_balance}</strong></div>
      </div>
      {result.routing && (
        <div className="routing-summary">
          <div className="routing-heading">
            <div><Route size={17} /></div>
            <span><small>QUERY ROUTER</small><strong>{result.routing.category}</strong></span>
            <em>置信度 {Math.round(result.routing.confidence * 100)}%</em>
          </div>
          <p>{result.routing.reason}</p>
          <div className="routing-requirements">
            {result.routing.output_requirements.map((requirement) => <span key={requirement}>{requirement}</span>)}
          </div>
        </div>
      )}
      {result.entity_resolution && (
        <div className="entity-resolution-summary">
          <div><Search size={15} /><strong>STOCK ENTITY RESOLVER</strong></div>
          <div className="entity-resolution-list">
            {result.entity_resolution.entities.map((entity) => (
              <span key={entity.symbol}>
                <b>{entity.name}</b>
                <em>{entity.symbol} · {entity.market}</em>
                <small>{Math.round(entity.confidence * 100)}%</small>
              </span>
            ))}
          </div>
        </div>
      )}
      <div className="module-plan">
        <strong>本次报告模块</strong>
        <div>{[...modules].map((module) => <span key={module}>{moduleLabels[module]}</span>)}</div>
      </div>
      {tocItems.length > 0 && <nav className="report-toc" aria-label="报告目录">
        <div><BookOpen size={15} /><strong>报告目录</strong><span>点击跳转到对应内容</span></div>
        <ol>{tocItems.map((item, index) => <li key={`${item.id}-${index}`}><a href={`#${item.id}`}><span>{String(index + 1).padStart(2, "0")}</span>{item.label}<ArrowRight size={12} /></a></li>)}</ol>
      </nav>}
      <div className="executive-summary">{result.analysis.summary}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></div>
      {result.analysis.citations.length > 0 && <section className="source-index" aria-label="报告资料来源">
        <div className="subsection-heading"><BookOpen size={14} /><strong>资料来源</strong><span>来源链接会同时标在对应内容旁</span></div>
        <div className="source-index-links">{result.analysis.citations.map((source) => source.url
          ? <a href={source.url} target="_blank" rel="noreferrer" key={source.source_id}><BookOpen size={11} />{readableText(source.name)}<ExternalLink size={10} /></a>
          : <span key={source.source_id}><BookOpen size={11} />{readableText(source.name)} · 未提供链接</span>)}</div>
      </section>}
      {show("comparison") && isComparison && result.analysis.comparison.length > 1 && (
        <section id="intent-focus" className="intent-focus-panel intent-focus-panel--comparison">
          <div className="intent-focus-heading"><Scale size={17} /><div><strong>同行对比核心结果</strong><span>增长 · 盈利能力 · 估值 · 业务差异 · 各自风险</span></div></div>
          <ComparisonTable rows={result.analysis.comparison} sources={result.analysis.citations} />
          <div className="comparison-notice"><AlertTriangle size={14} />{result.analysis.comparison_notice}</div>
        </section>
      )}
      {show("risk") && isRiskAnalysis && (
        <section id="intent-focus" className="intent-focus-panel intent-focus-panel--risk">
          <div className="intent-focus-heading"><ShieldAlert size={17} /><div><strong>风险扫描核心结果</strong><span>先看下行因素，再看哪些信息仍需验证</span></div></div>
          <div className="risk-priority-grid">
            <div><strong>已识别风险</strong>{result.analysis.negative_factors.map((item) => <p key={item}><AlertTriangle size={12} /><span>{item}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></span></p>)}</div>
            <div><strong>待验证事项</strong>{result.analysis.pending_verification.map((item) => <p key={item}><CircleHelp size={12} /><span>{item}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></span></p>)}</div>
          </div>
        </section>
      )}
      <div className="analysis-runtime">
        分析方式：{result.analysis.analysis_method.startsWith("qwen:") ? `千问大模型（${result.analysis.analysis_method.slice(5)}）` : "本地规则引擎"}
      </div>
      {result.analysis.analysis_warnings.map((warning) => (
        <div className="analysis-warning" key={warning}><AlertTriangle size={13} />{warning}</div>
      ))}

      {show("investor_guide") && <section id="investor-guide" className="investor-guide">
        <div className="guide-heading"><GraduationCap size={19} /><div><strong>{guideTitle}</strong><span>{guideSubtitle}</span></div></div>
        <div className="guide-grid">
          {result.analysis.investor_focus.map((guide) => (
            <article key={guide.company_name}>
              <h3>{guide.company_name}</h3>
              <ol>{guide.questions.map((question) => <li key={question}>{question}</li>)}</ol>
            </article>
          ))}
        </div>
        <p>这里只列出值得关注的问题，不对公司价值或股价方向作出结论。</p>
      </section>}

      {hasCoreSection && <section id="report-core" className="report-section">
        <div className="section-title"><span className="section-number">{sectionNumber("core")}</span><h3>{coreTitle}</h3></div>
        {show("company_profile") && <div className="portrait-grid">
          {result.analysis.company_portraits.map((portrait) => (
            <article className="portrait-card" key={portrait.symbol}>
              <div className="portrait-title"><Building2 size={16} /><div><strong>{portrait.company_name}</strong><span>{portrait.symbol}</span></div></div>
              <dl>
                <div><dt>公司做什么</dt><dd>{portrait.what_it_does}</dd></div>
                <div><dt>核心业务</dt><dd>{portrait.core_business}</dd></div>
                <div><dt>所属行业</dt><dd>{portrait.industry}</dd></div>
                <div><dt>商业特点</dt><dd>{portrait.business_characteristics}</dd></div>
              </dl>
              <SourceTags sourceIds={[`quote:${portrait.symbol}`, `financial:${portrait.symbol}`]} sources={result.analysis.citations} />
            </article>
          ))}
        </div>}
        {show("financial_snapshot") && <div className="stock-grid portrait-stocks">{result.data.stocks.map((stock) => <StockCard stock={stock} sources={result.analysis.citations} key={stock.company.symbol} />)}</div>}
        {show("valuation") && <ValuationPanel stocks={result.data.stocks} sources={result.analysis.citations} />}

        {show("glossary") && <div className="glossary">
          <div className="subsection-heading"><BookOpen size={14} /><strong>小白指标词典</strong><span>不改变原始数据，只增加解释</span></div>
          <div className="glossary-grid">
            {result.analysis.term_explanations.map((term) => (
              <details key={term.term}>
                <summary>{term.term}<span>查看通俗解释</span></summary>
                <div><p><strong>专业解释</strong>{term.professional_definition}</p><p><strong>通俗解释</strong>{term.plain_language_explanation}</p></div>
              </details>
            ))}
          </div>
        </div>}

        {show("comparison") && !isComparison && result.analysis.comparison.length > 1 && (
          <div className="comparison-section">
            <div className="subsection-heading"><Scale size={14} /><strong>结构化横向比较</strong></div>
            <ComparisonTable rows={result.analysis.comparison} sources={result.analysis.citations} />
            <div className="comparison-notice"><AlertTriangle size={14} />{result.analysis.comparison_notice}</div>
          </div>
        )}
      </section>}

      {(show("facts") || show("news")) && <section id="report-evidence" className="report-section evidence-report">
        <div className="section-title"><span className="section-number">{sectionNumber("evidence")}</span><h3>{show("news") && !show("facts") ? "新闻证据" : "当前已确认事实 Fact"}</h3><span className="section-count">每条均可追溯</span></div>
        {show("facts") && <div className="report-layer fact-layer">
          <div className="layer-heading"><div><FileCheck2 size={17} /></div><span><strong>已确认事实 Fact</strong><small>仅包含可由行情、财务或新闻直接支持的内容</small></span></div>
          <div className="fact-list">
            {visibleFacts.length ? visibleFacts.map((fact) => <article key={fact.fact_id}><p>{readableText(fact.content)}</p><SourceTags sourceIds={fact.source_ids} sources={result.analysis.citations} /></article>) : <p className="muted-copy">当前没有与本任务直接相关的已确认事实。</p>}
          </div>
        </div>}

        {show("news") && <div className="news-evidence">
          <div className="subsection-heading"><FileCheck2 size={14} /><strong>重要变化与新闻过滤</strong><span>为什么留下、为什么值得关注</span></div>
          <NewsFunnel result={result} />
          <div className="news-list">{result.news.selected.length ? result.news.selected.map((item) => <NewsRow item={item} key={item.news_id} />) : <p className="muted-copy">暂无通过筛选的相关新闻。</p>}</div>
        </div>}
      </section>}

      {show("analysis") && <section id="report-analysis" className="report-section evidence-report">
        <div className="section-title"><span className="section-number">{sectionNumber("analysis")}</span><h3>这些事实意味着什么 AI Analysis</h3></div>
        <div className="report-layer analysis-layer">
          <div className="layer-heading"><div><BrainCircuit size={17} /></div><span><strong>AI 分析 Analysis</strong><small>这是模型根据事实形成的解释，不是事实或投资建议</small></span><em>AI 分析</em></div>
          <div className="layer-items">{result.analysis.ai_analysis.map((item, index) => <div className="sourced-report-item" key={index}><p>{item.content}</p><SourceTags sourceIds={factSourceIds(item.based_on_fact_ids, result.analysis.facts)} sources={result.analysis.citations} /></div>)}</div>
        </div>
        <div className="evidence-structure">
          <div className="evidence-column evidence-column--positive"><h3><ArrowUpRight size={15} />积极因素</h3><ul>{result.analysis.positive_factors.map((item) => <li key={item}>{item}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></li>)}</ul></div>
          <div className="evidence-column evidence-column--negative"><h3><ArrowDownRight size={15} />负面因素</h3><ul>{result.analysis.negative_factors.map((item) => <li key={item}>{item}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></li>)}</ul></div>
          <div className="evidence-column evidence-column--pending"><h3><CircleHelp size={15} />待验证因素</h3><ul>{result.analysis.pending_verification.map((item) => <li key={item}>{item}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></li>)}</ul></div>
        </div>
      </section>}

      {show("future_watch") && <section id="report-future" className="report-section evidence-report">
        <div className="section-title"><span className="section-number">{sectionNumber("future")}</span><h3>未来需要关注什么 Future Watch</h3><span className="section-count">不是涨跌预测</span></div>
        <div className="future-watch-list">{result.analysis.future_watch.map((item, index) => <div key={item}><span>{String(index + 1).padStart(2, "0")}</span><div><p>{item}</p><SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></div></div>)}</div>
        <div className="report-layer scenario-layer">
          <div className="layer-heading"><div><Sparkles size={17} /></div><span><strong>未来情景 Scenario</strong><small>条件式推演，用于理解关键变量，不预测股价</small></span></div>
          <div className="scenario-grid">{result.analysis.scenarios.map((item, index) => <article key={index}><strong>{item.condition}</strong><ArrowRight size={14} /><p>{item.possible_outcome}</p><SourceTags sourceIds={factSourceIds(item.based_on_fact_ids, result.analysis.facts)} sources={result.analysis.citations} /></article>)}</div>
        </div>
        <div className="report-layer uncertainty-layer">
          <div className="layer-heading"><div><CircleHelp size={17} /></div><span><strong>主要不确定性 Uncertainty</strong><small>当前数据无法确认的因素</small></span></div>
          <ul>{result.analysis.uncertainties.map((item) => <li key={item}>{item}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></li>)}</ul>
        </div>
      </section>}

      {(show("risk") || show("risk_review")) && <section id="report-risk" className="report-section">
        <div className="section-title"><span className="section-number">{sectionNumber("risk")}</span><h3>{show("risk") ? "风险因素与审核" : "风险审核"}</h3></div>
        {show("risk") && !isRiskAnalysis && <div className="risk-factor-list">{result.analysis.negative_factors.map((item) => <div key={item}><AlertTriangle size={13} /><span>{item}<SourceTags sourceIds={allVisibleSourceIds} sources={result.analysis.citations} /></span></div>)}</div>}
        {show("risk_review") &&
        <div className={`risk-review ${approved ? "risk-review--approved" : "risk-review--rejected"}`}>
          <div className="risk-icon">{approved ? <BadgeCheck size={21} /> : <ShieldAlert size={21} />}</div>
          <div>
            <div className="risk-title-row"><h3>{approved ? "风险审核检查通过" : "风险审核需要修订"}</h3><span>{result.risk_review.risk_level.toUpperCase()} RISK</span></div>
            <div className="review-checks">
              {result.risk_review.checks.map((check) => (
                <div className={check.passed ? "review-check is-passed" : "review-check is-failed"} key={check.check_id}>
                  {check.passed ? <Check size={13} /> : <AlertTriangle size={13} />}<span><strong>{check.label}</strong><small>{check.detail}</small></span>
                </div>
              ))}
            </div>
            <div className="coverage-note">证据覆盖率仅表示事实来源的完整程度，不代表投资判断正确率或投资成功概率。</div>
          </div>
        </div>}
      </section>}

      <section className="follow-up">
        <div><GraduationCap size={16} /><span><strong>继续了解</strong><small>从这些问题继续建立你的公司认知</small></span></div>
        <div>{result.analysis.follow_up_questions.slice(0, 4).map((item) => <button key={item.query} onClick={() => onFollowUp(item.query)}>{item.label}<ArrowRight size={12} /></button>)}</div>
      </section>
      <div className="disclaimer"><ShieldAlert size={14} />{result.disclaimer}</div>
    </div>
  );
}
