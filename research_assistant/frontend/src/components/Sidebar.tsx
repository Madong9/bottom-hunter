import { Clock3, MessageSquareText, PanelLeftClose, Plus, Sparkles } from "lucide-react";
import type { ConversationItem } from "../types/research";

interface SidebarProps {
  conversations: ConversationItem[];
  activeId: string | null;
  open: boolean;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  serviceLabel: string;
  serviceOnline: boolean;
}

export function Sidebar({
  conversations,
  activeId,
  open,
  onClose,
  onNew,
  onSelect,
  serviceLabel,
  serviceOnline,
}: SidebarProps) {
  return (
    <>
      {open && <button className="sidebar-scrim" aria-label="关闭侧栏" onClick={onClose} />}
      <aside className={`sidebar ${open ? "sidebar--open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark"><Sparkles size={18} /></div>
          <div>
            <div className="brand-name">研策</div>
            <div className="brand-subtitle">AI Research Copilot</div>
          </div>
          <button className="icon-button sidebar-close" onClick={onClose} aria-label="关闭侧栏">
            <PanelLeftClose size={18} />
          </button>
        </div>

        <button className="new-chat-button" onClick={onNew}>
          <Plus size={17} />
          新建投研
          <span className="new-chat-shortcut">⌘ K</span>
        </button>

        <div className="history-label"><Clock3 size={13} /> 最近对话</div>
        <nav className="history-list" aria-label="最近对话">
          {conversations.length === 0 ? (
            <div className="empty-history">你的投研记录会显示在这里</div>
          ) : (
            conversations.map((conversation) => (
              <button
                key={conversation.id}
                className={`history-item ${activeId === conversation.id ? "history-item--active" : ""}`}
                onClick={() => onSelect(conversation.id)}
              >
                <MessageSquareText size={15} />
                <span>{conversation.question}</span>
              </button>
            ))
          )}
        </nav>

        <div className="sidebar-footer">
          <span className={`status-dot ${serviceOnline ? "" : "status-dot--offline"}`} />
          {serviceLabel}
        </div>
      </aside>
    </>
  );
}
