import {
  BarChart3,
  Check,
  Database,
  FileSearch,
  LoaderCircle,
  Newspaper,
  Route,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";
import type { ResearchResult } from "../types/research";

interface ProcessTimelineProps {
  completedSteps: number;
  loading: boolean;
  result: ResearchResult | null;
}

const stages = [
  { title: "任务路由", subtitle: "识别六类金融任务与输出要求", icon: Route },
  { title: "证券识别", subtitle: "解析公司名、代码与上市市场", icon: Search },
  { title: "理解问题", subtitle: "确定标的与专项分析维度", icon: FileSearch },
  { title: "获取金融数据", subtitle: "读取行情、估值和财务指标", icon: Database },
  { title: "过滤相关新闻", subtitle: "去重并评估来源可信度", icon: Newspaper },
  { title: "生成分析", subtitle: "整合基本面、估值与事件影响", icon: BarChart3 },
  { title: "风险审核", subtitle: "检查证据、措辞与投资风险", icon: ShieldCheck },
];

function stageSummary(index: number, result: ResearchResult | null) {
  if (!result) return null;
  if (index === 0) {
    return (
      <div className="process-tags">
        <span>{result.routing?.category ?? result.understanding.intent.replaceAll("_", " ")}</span>
        {result.routing && <span>{Math.round(result.routing.confidence * 100)}%</span>}
      </div>
    );
  }
  if (index === 1) {
    const entities = result.entity_resolution?.entities ?? result.understanding.entities ?? [];
    return (
      <div className="process-tags">
        {entities.map((entity) => <span key={entity.symbol}>{entity.name} · {entity.symbol}</span>)}
      </div>
    );
  }
  if (index === 2) {
    return (
      <div className="process-tags">
        {result.understanding.symbols.map((symbol) => <span key={symbol}>{symbol}</span>)}
        {result.understanding.dimensions.slice(0, 2).map((dimension) => <span key={dimension}>{dimension}</span>)}
      </div>
    );
  }
  if (index === 3) {
    return <p className="stage-result">已获取 {result.data.stocks.length} 只股票的行情与财务数据</p>;
  }
  if (index === 4) {
    return (
      <p className="stage-result">
        {result.news.stats.candidate_count} 条候选 → {result.news.stats.selected_count} 条保留
      </p>
    );
  }
  if (index === 5) {
    return (
      <p className="stage-result">
        已拆分 {result.analysis.facts.length} 条事实、{result.analysis.ai_analysis.length} 条 AI 分析
      </p>
    );
  }
  return (
    <p className="stage-result">
      {result.risk_review.status === "approved" ? "审核通过" : "需要修订"} · 风险等级 {result.risk_review.risk_level.toUpperCase()}
    </p>
  );
}

export function ProcessTimeline({ completedSteps, loading, result }: ProcessTimelineProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!loading) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [loading]);

  return (
    <section className="process-card" aria-label="投研处理过程">
      <div className="process-heading">
        <span>多智能体协作过程</span>
        {loading ? (
          <span className="live-label"><span /> 运行中 · {elapsedSeconds}秒</span>
        ) : result ? (
          <span className="done-label">已完成</span>
        ) : (
          <span className="stopped-label">已中止</span>
        )}
      </div>
      <div className="process-list">
        {stages.map((stage, index) => {
          const complete = index < completedSteps;
          const active = loading && index === completedSteps;
          const Icon = stage.icon;
          return (
            <div className={`process-step ${complete ? "is-complete" : ""} ${active ? "is-active" : ""}`} key={stage.title}>
              <div className="step-rail">
                <div className="step-icon">
                  {complete ? <Check size={16} strokeWidth={3} /> : active ? <LoaderCircle className="spinner" size={17} /> : <Icon size={17} />}
                </div>
                {index < stages.length - 1 && <div className="step-line" />}
              </div>
              <div className="step-copy">
                <div className="step-title-row">
                  <strong>{stage.title}</strong>
                  <span>{complete ? "完成" : active ? "处理中" : "等待"}</span>
                </div>
                <p>
                  {active && index === 5 && elapsedSeconds >= 5
                    ? "正在等待千问生成结构化分析，超时将自动返回规则报告"
                    : stage.subtitle}
                </p>
                {complete && stageSummary(index, result)}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
