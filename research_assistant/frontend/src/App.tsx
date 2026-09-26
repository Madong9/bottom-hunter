import {
  BarChart3,
  Building2,
  Menu,
  Newspaper,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { createResearch, getHealth, listResearch } from "./api/research";
import { Composer } from "./components/Composer";
import { DecisionConfirmation } from "./components/DecisionConfirmation";
import { ResearchConversation } from "./components/ResearchConversation";
import { Sidebar } from "./components/Sidebar";
import type { ConversationItem, HealthStatus } from "./types/research";
import { requiresInvestmentConfirmation } from "./utils/actionIntent";

const suggestions = [
  { icon: Building2, label: "基本面分析", question: "分析贵州茅台的基本面和估值" },
  { icon: Newspaper, label: "新闻影响", question: "宁德时代近期有什么新闻和风险？" },
  { icon: BarChart3, label: "横向比较", question: "比较贵州茅台和宁德时代" },
  { icon: ShieldAlert, label: "风险扫描", question: "Apple 的估值和主要风险如何？" },
];

const sleep = (milliseconds: number) =>
  new Promise((resolve) => window.setTimeout(resolve, milliseconds));

const AGENT_STEP_COUNT = 7;

export default function App() {
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [completedSteps, setCompletedSteps] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  const activeConversation = conversations.find((item) => item.id === activeId) ?? null;

  useEffect(() => {
    void Promise.all([getHealth(), listResearch()])
      .then(([runtime, history]) => {
        setHealth(runtime);
        setConversations(
          history.items.map((task) => ({
            id: task.task_id,
            question: task.query,
            task,
            error: null,
            createdAt: new Date(task.created_at),
          })),
        );
      })
      .catch(() => setHealth(null));
  }, []);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setActiveId(null);
        setPendingQuestion(null);
        setDraft("");
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  const executeResearch = async (question: string) => {
    const id = crypto.randomUUID();
    const conversation: ConversationItem = {
      id,
      question,
      task: null,
      error: null,
      createdAt: new Date(),
    };
    setConversations((items) => [conversation, ...items]);
    setActiveId(id);
    setDraft("");
    setLoading(true);
    setCompletedSteps(0);
    setPendingQuestion(null);
    setSidebarOpen(false);

    try {
      const progressAnimation = async () => {
        for (let step = 1; step < 6; step += 1) {
          await sleep(420);
          setCompletedSteps(step);
        }
      };
      const [task] = await Promise.all([
        createResearch(question),
        progressAnimation(),
      ]);
      setCompletedSteps(task.status === "completed" ? AGENT_STEP_COUNT : task.agent_runs.filter((run) => run.status === "completed").length);
      setConversations((items) =>
        items.map((item) => (item.id === id ? { ...item, task } : item)),
      );
    } catch (error) {
      setConversations((items) =>
        items.map((item) =>
          item.id === id
            ? { ...item, error: error instanceof Error ? error.message : "网络连接异常" }
            : item,
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  const submitQuestion = (preset?: string) => {
    const question = (preset ?? draft).trim();
    if (!question || loading) return;
    setDraft("");
    if (requiresInvestmentConfirmation(question)) {
      setPendingQuestion(question);
      setActiveId(null);
      return;
    }
    void executeResearch(question);
  };

  const newConversation = () => {
    if (loading) return;
    setActiveId(null);
    setPendingQuestion(null);
    setDraft("");
    setCompletedSteps(0);
    setSidebarOpen(false);
  };

  const selectConversation = (id: string) => {
    if (loading) return;
    const selected = conversations.find((item) => item.id === id);
    setPendingQuestion(null);
    setActiveId(id);
    setCompletedSteps(
      selected?.task?.status === "completed"
        ? AGENT_STEP_COUNT
        : selected?.task?.agent_runs.filter((run) => run.status === "completed").length ?? 0,
    );
    setSidebarOpen(false);
  };

  return (
    <div className="app-shell">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNew={newConversation}
        onSelect={selectConversation}
        serviceLabel={
          health
            ? `${health.real_data ? "真实行情" : "Mock 数据"} · ${health.qwen_configured ? "千问已连接" : "规则分析"}`
            : "后端未连接"
        }
        serviceOnline={health !== null}
      />

      <main className="main-panel">
        <header className="topbar">
          <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="打开侧栏">
            <Menu size={20} />
          </button>
          <div className="topbar-title">
            <strong>AI 投研助手</strong>
            <span>多智能体协作分析</span>
          </div>
          <div className="mode-pill">
            <span />
            {health
              ? `${health.real_data ? "REAL DATA" : "MOCK DATA"} · ${health.qwen_configured ? health.qwen_model.toUpperCase() : "RULE ENGINE"}`
              : "BACKEND OFFLINE"}
          </div>
        </header>

        <div className="chat-scroll">
          {pendingQuestion ? (
            <DecisionConfirmation
              question={pendingQuestion}
              onContinue={() => void executeResearch(pendingQuestion)}
              onEdit={() => {
                setDraft(pendingQuestion);
                setPendingQuestion(null);
              }}
            />
          ) : !activeConversation ? (
            <section className="welcome">
              <div className="welcome-logo"><Sparkles size={25} /></div>
              <div className="welcome-kicker">YOUR AI RESEARCH TEAM</div>
              <h1>今天想研究哪只股票？</h1>
              <p>AI投研助手帮助普通投资者理解公司信息、发现关键变化并建立关注框架，不提供买卖建议。</p>
              <div className="suggestion-grid">
                {suggestions.map((suggestion) => {
                  const Icon = suggestion.icon;
                  return (
                    <button key={suggestion.question} onClick={() => submitQuestion(suggestion.question)}>
                      <span className="suggestion-icon"><Icon size={17} /></span>
                      <span><strong>{suggestion.label}</strong><small>{suggestion.question}</small></span>
                    </button>
                  );
                })}
              </div>
              <div className="capability-line">
                <span>问题理解</span><i />
                <span>金融数据</span><i />
                <span>新闻筛选</span><i />
                <span>风险审核</span>
              </div>
            </section>
          ) : (
            <ResearchConversation
              conversation={activeConversation}
              completedSteps={completedSteps}
              loading={loading}
              onRetry={(question) => void executeResearch(question)}
              onFollowUp={(question) => submitQuestion(question)}
            />
          )}
        </div>

        <Composer
          value={draft}
          loading={loading}
          onChange={setDraft}
          onSubmit={() => submitQuestion()}
        />
      </main>
    </div>
  );
}
