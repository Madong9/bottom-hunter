import { AlertCircle, Bot, Copy, RotateCcw, ThumbsDown, ThumbsUp, UserRound } from "lucide-react";
import type { ConversationItem } from "../types/research";
import { ProcessTimeline } from "./ProcessTimeline";
import { ResearchReport } from "./ResearchReport";

interface ResearchConversationProps {
  conversation: ConversationItem;
  completedSteps: number;
  loading: boolean;
  onRetry: (question: string) => void;
  onFollowUp: (question: string) => void;
}

export function ResearchConversation({
  conversation,
  completedSteps,
  loading,
  onRetry,
  onFollowUp,
}: ResearchConversationProps) {
  const result = conversation.task?.result ?? null;
  const failed = conversation.error ?? conversation.task?.error;

  return (
    <div className="conversation">
      <div className="message message--user">
        <div className="message-avatar user-avatar"><UserRound size={17} /></div>
        <div className="user-bubble">{conversation.question}</div>
      </div>

      <div className="message message--assistant">
        <div className="message-avatar assistant-avatar"><Bot size={18} /></div>
        <div className="assistant-content">
          <ProcessTimeline completedSteps={completedSteps} loading={loading} result={result} />

          {failed && (
            <div className="error-card">
              <AlertCircle size={20} />
              <div><strong>本次研究未能完成</strong><p>{failed}</p></div>
              <button onClick={() => onRetry(conversation.question)}><RotateCcw size={15} />重试</button>
            </div>
          )}

          {result && <ResearchReport result={result} onFollowUp={onFollowUp} />}

          {result && (
            <div className="message-actions" aria-label="回答操作">
              <button title="复制"><Copy size={15} /></button>
              <button title="有帮助"><ThumbsUp size={15} /></button>
              <button title="需改进"><ThumbsDown size={15} /></button>
              <span>由 7 个 Agent 协作完成</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
