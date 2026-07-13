/**
 * CommandInput.tsx — Slash 命令 + @-mention 输入框
 *
 * 对标 Cursor Composer 输入框：
 *   - / 弹出命令菜单
 *   - @ 弹出上下文菜单
 *   - 上下文 chip 标签
 *   - 多行 textarea 自动增高
 *   - Enter 发送，Shift+Enter 换行
 */
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';

export interface CommandInputProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
}

interface SlashCommand {
  id: string;
  label: string;
  description: string;
  action: string;
}

interface MentionItem {
  id: string;
  label: string;
  description: string;
  icon: string;
}

const SLASH_COMMANDS: SlashCommand[] = [
  { id: 'new', label: '/new', description: '新建会话', action: '/new' },
  { id: 'undo', label: '/undo', description: '撤销', action: '/undo' },
  { id: 'diff', label: '/diff', description: '显示变更', action: '/diff' },
  { id: 'reset', label: '/reset', description: '重置', action: '/reset' },
  { id: 'index', label: '/index', description: '索引代码', action: '/index' },
  { id: 'search', label: '/search', description: '搜索代码', action: '/search' },
  { id: 'test', label: '/test', description: '运行测试', action: '/test' },
  { id: 'help', label: '/help', description: '帮助', action: '/help' },
];

const MENTION_ITEMS: MentionItem[] = [
  { id: 'file', label: '@file', description: '引用文件', icon: '📄' },
  { id: 'folder', label: '@folder', description: '引用文件夹', icon: '📁' },
  { id: 'codebase', label: '@codebase', description: '整个代码库', icon: '📦' },
  { id: 'terminal', label: '@terminal', description: '终端输出', icon: '💻' },
];

type ContextChip = { type: 'slash' | 'mention'; value: string; label: string };

const CSS = {
  '--bg-primary': '#ffffff',
  '--bg-secondary': '#f4f5f7',
  '--bg-tertiary': '#ebecee',
  '--text-primary': '#28282c',
  '--text-secondary': '#6b7280',
  '--text-tertiary': '#9ca3af',
  '--border-color': '#e4e4e7',
  '--accent': '#0066b8',
  '--accent-hover': '#005299',
  '--accent-light': 'rgba(0, 102, 184, 0.08)',
  '--font-sans': "'Inter', -apple-system, sans-serif",
  '--font-mono': "'JetBrains Mono', Menlo, monospace",
} as const;

export function CommandInput({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder = '输入消息...',
}: CommandInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const [showPopup, setShowPopup] = useState<'slash' | 'mention' | null>(null);
  const [popupIndex, setPopupIndex] = useState(0);
  const [chips, setChips] = useState<ContextChip[]>([]);

  // 检测 / 或 @ 触发
  const handleChange = useCallback(
    (val: string) => {
      onChange(val);

      // 获取光标位置前的文本
      const cursorPos = textareaRef.current?.selectionStart ?? val.length;
      const textBefore = val.slice(0, cursorPos);

      // 检测最近的 / 或 @
      const lastSlash = textBefore.lastIndexOf('/');
      const lastAt = textBefore.lastIndexOf('@');

      if (lastSlash >= 0 && isTriggerValid(textBefore, lastSlash)) {
        setShowPopup('slash');
        setPopupIndex(0);
      } else if (lastAt >= 0 && isTriggerValid(textBefore, lastAt)) {
        setShowPopup('mention');
        setPopupIndex(0);
      } else {
        setShowPopup(null);
      }
    },
    [onChange],
  );

  function isTriggerValid(textBefore: string, triggerPos: number): boolean {
    // 触发字符前必须是空格或行首
    if (triggerPos === 0) return true;
    const charBefore = textBefore[triggerPos - 1];
    return charBefore === ' ' || charBefore === '\n';
  }

  function handleSelectPopup(item: SlashCommand | MentionItem) {
    if (showPopup === 'slash') {
      const cmd = item as SlashCommand;
      // 替换 / 开头的部分
      const cursorPos = textareaRef.current?.selectionStart ?? value.length;
      const textBefore = value.slice(0, cursorPos);
      const lastSlash = textBefore.lastIndexOf('/');
      const newValue = value.slice(0, lastSlash) + cmd.action + ' ' + value.slice(cursorPos);
      onChange(newValue);
      setChips([...chips, { type: 'slash', value: cmd.action, label: cmd.label }]);
    } else if (showPopup === 'mention') {
      const mention = item as MentionItem;
      const cursorPos = textareaRef.current?.selectionStart ?? value.length;
      const textBefore = value.slice(0, cursorPos);
      const lastAt = textBefore.lastIndexOf('@');
      const newValue = value.slice(0, lastAt) + mention.label + ' ' + value.slice(cursorPos);
      onChange(newValue);
      setChips([...chips, { type: 'mention', value: mention.label, label: mention.label }]);
    }
    setShowPopup(null);
    textareaRef.current?.focus();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (showPopup) {
      const items = showPopup === 'slash' ? SLASH_COMMANDS : MENTION_ITEMS;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setPopupIndex((prev) => Math.min(prev + 1, items.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setPopupIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (items[popupIndex]) {
          handleSelectPopup(items[popupIndex]);
        }
      } else if (e.key === 'Escape') {
        setShowPopup(null);
      }
      return;
    }

    // Enter 发送，Shift+Enter 换行
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  function removeChip(index: number) {
    setChips((prev) => prev.filter((_, i) => i !== index));
  }

  // 自动增高
  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const minHeight = 44;
    const maxHeight = 160;
    const newHeight = Math.min(Math.max(ta.scrollHeight, minHeight), maxHeight);
    ta.style.height = `${newHeight}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  const popupItems = showPopup === 'slash' ? SLASH_COMMANDS : MENTION_ITEMS;

  return (
    <div style={styles.container}>
      {/* 上下文 chips */}
      {chips.length > 0 && (
        <div style={styles.chipsContainer}>
          {chips.map((chip, idx) => (
            <span key={idx} style={styles.chip}>
              {chip.label}
              <button
                style={styles.chipRemove}
                onClick={() => removeChip(idx)}
                disabled={disabled}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 弹出菜单 */}
      {showPopup && (
        <div ref={popupRef} style={styles.popup}>
          {popupItems.map((item, idx) => (
            <div
              key={item.id}
              style={{
                ...styles.popupItem,
                background: idx === popupIndex ? CSS['--accent-light'] : 'transparent',
              }}
              onMouseEnter={() => setPopupIndex(idx)}
              onMouseDown={(e) => {
                e.preventDefault();
                handleSelectPopup(item);
              }}
            >
              <span style={styles.popupLabel}>
                {'icon' in item ? (
                  <>
                    <span style={styles.popupIcon}>{item.icon}</span>
                    {item.label}
                  </>
                ) : (
                  item.label
                )}
              </span>
              <span style={styles.popupDesc}>{item.description}</span>
            </div>
          ))}
        </div>
      )}

      {/* 输入框 */}
      <div style={styles.inputRow}>
        <textarea
          ref={textareaRef}
          style={styles.textarea}
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
        />
        <button
          style={{
            ...styles.sendBtn,
            opacity: value.trim() && !disabled ? 1 : 0.4,
            cursor: value.trim() && !disabled ? 'pointer' : 'default',
          }}
          onClick={onSend}
          disabled={disabled || !value.trim()}
        >
          ↑
        </button>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: 'relative',
    fontFamily: CSS['--font-sans'],
  },
  chipsContainer: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: 6,
    padding: '8px 12px 0 12px',
  },
  chip: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    padding: '2px 8px',
    background: CSS['--accent-light'],
    color: CSS['--accent'],
    borderRadius: 12,
    fontSize: 12,
    fontFamily: CSS['--font-mono'],
  },
  chipRemove: {
    background: 'transparent',
    border: 'none',
    color: CSS['--accent'],
    cursor: 'pointer',
    fontSize: 14,
    padding: 0,
    lineHeight: 1,
    opacity: 0.6,
  },
  inputRow: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: 8,
    padding: 12,
    borderTop: `1px solid ${CSS['--border-color']}`,
  },
  textarea: {
    flex: 1,
    minHeight: 44,
    maxHeight: 160,
    padding: '10px 12px',
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 8,
    background: CSS['--bg-primary'],
    color: CSS['--text-primary'],
    fontSize: 14,
    fontFamily: CSS['--font-sans'],
    lineHeight: 1.5,
    outline: 'none',
    resize: 'none' as const,
    overflowY: 'auto' as const,
    transition: 'border-color 0.15s',
  },
  sendBtn: {
    width: 36,
    height: 36,
    minWidth: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: CSS['--accent'],
    color: '#ffffff',
    border: 'none',
    borderRadius: 8,
    fontSize: 18,
    fontWeight: 'bold',
    cursor: 'pointer',
    transition: 'all 0.15s',
    flexShrink: 0,
  },
  popup: {
    position: 'absolute',
    bottom: '100%',
    left: 12,
    right: 12,
    maxHeight: 200,
    background: CSS['--bg-primary'],
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 8,
    boxShadow: '0 4px 16px rgba(0,0,0,0.1)',
    overflowY: 'auto' as const,
    zIndex: 100,
    marginBottom: 4,
  },
  popupItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 12px',
    cursor: 'pointer',
    fontSize: 13,
    borderRadius: 4,
    margin: '2px 4px',
  },
  popupLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    color: CSS['--text-primary'],
    fontFamily: CSS['--font-mono'],
    fontWeight: 500,
  },
  popupIcon: {
    fontSize: 14,
  },
  popupDesc: {
    color: CSS['--text-tertiary'],
    fontSize: 12,
  },
};