import { ArrowUp, Paperclip } from "lucide-react";
import { FormEvent, KeyboardEvent, useRef } from "react";

interface ComposerProps {
  value: string;
  loading: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

export function Composer({ value, loading, onChange, onSubmit }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (value.trim() && !loading) onSubmit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (value.trim() && !loading) onSubmit();
    }
  };

  return (
    <div className="composer-shell">
      <form className="composer" onSubmit={submit}>
        <button type="button" className="composer-tool" aria-label="添加附件" title="Demo 暂不支持附件">
          <Paperclip size={19} />
        </button>
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="问一只股票，例如：分析贵州茅台的基本面和近期风险"
          aria-label="输入股票问题"
          disabled={loading}
        />
        <button
          type="submit"
          className="send-button"
          aria-label="发送问题"
          disabled={!value.trim() || loading}
        >
          <ArrowUp size={19} strokeWidth={2.5} />
        </button>
      </form>
      <p className="composer-note">AI 可能会出错，请核验关键财务数据。本页面内容不构成投资建议。</p>
    </div>
  );
}
