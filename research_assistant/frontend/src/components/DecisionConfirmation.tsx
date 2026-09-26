import { ArrowLeft, ArrowRight, Scale, ShieldAlert } from "lucide-react";

interface DecisionConfirmationProps {
  question: string;
  onContinue: () => void;
  onEdit: () => void;
}

export function DecisionConfirmation({
  question,
  onContinue,
  onEdit,
}: DecisionConfirmationProps) {
  return (
    <section className="decision-gate" aria-label="投资决策风险确认">
      <div className="gate-question"><span>你的问题</span>{question}</div>
      <div className="gate-card">
        <div className="gate-icon"><ShieldAlert size={22} /></div>
        <div className="gate-kicker">HUMAN CONFIRMATION REQUIRED</div>
        <h2>这涉及一项投资行动决策</h2>
        <p>
          你的问题涉及投资决策。AI 可以继续帮助比较基本面、估值、事件和风险，
          但不会替你直接作出买卖决策。
        </p>
        <div className="gate-boundary">
          <Scale size={16} />
          <span><strong>分析边界</strong> 系统将输出证据和情景，不输出“应该买入”或“应该卖出”。</span>
        </div>
        <div className="gate-actions">
          <button className="gate-edit" onClick={onEdit}><ArrowLeft size={15} />修改问题</button>
          <button className="gate-continue" onClick={onContinue}>继续分析<ArrowRight size={15} /></button>
        </div>
      </div>
    </section>
  );
}
