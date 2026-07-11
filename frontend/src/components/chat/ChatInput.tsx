import { useState, useRef, useCallback, type KeyboardEvent } from 'react';
import { ArrowUp } from 'lucide-react';

interface Props {
  onSend: (message: string) => void;
  disabled: boolean;
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 160) + 'px';
    }
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
    // Reset height after clearing
    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }, 0);
  }, [value, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const hasText = value.trim().length > 0;

  return (
    <div className="px-4 py-3 pb-6 border-t" style={{ borderColor: '#1e293b' }}>
      <div
        className="flex items-end gap-2 rounded-xl px-3 py-2"
        style={{ background: '#1a2744', border: '1px solid #1e293b' }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            adjustHeight();
          }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabled ? '请先选择数据文件' : '输入分析问题，Shift+Enter 换行'}
          rows={1}
          className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-[#64748b]"
          style={{ color: '#e2e8f0', maxHeight: '160px' }}
        />
        <button
          onClick={handleSend}
          disabled={!hasText || disabled}
          className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center transition-colors disabled:opacity-30"
          style={{
            background: hasText && !disabled ? '#2563eb' : '#334155',
          }}
        >
          <ArrowUp size={16} style={{ color: '#ffffff' }} />
        </button>
      </div>
    </div>
  );
}
