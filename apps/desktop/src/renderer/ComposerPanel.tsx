/**
 * ComposerPanel.tsx — Codex 风格统一对话面板
 *
 * 对标 Cursor Composer：
 *   - Ask / Edit / Agent 三模式统一面板
 *   - NDJSON 流式响应解析
 *   - 浅色主题风格
 */
import { useEffect, useRef, useState } from 'react';
import { CommandInput } from './CommandInput';

const API_BASE = 'http://localhost:8000';

export interface ToolCall {
  name: string;
  args?: any;
  result?: any;
  success?: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  toolCalls?: ToolCall[];
  streaming?: boolean;
}

export interface ComposerPanelProps {
  visible: boolean;
}

type ComposerMode = 'ask' | 'edit' | 'agent';

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
  '--success': '#22c55e',
  '--warning': '#f59e0b',
  '--error': '#dc2626',
  '--font-sans': "'Inter', -apple-system, sans-serif",
  '--font-mono': "'JetBrains Mono', Menlo, monospace",
} as const;

export function ComposerPanel({ visible }: ComposerPanelProps) {
  const [mode, setMode] = useState<ComposerMode>('ask');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isStreaming]);

  // 解析 NDJSON（每一行是一个 JSON）
  async function handleSend() {
    const text = input.trim();
    if (!text || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };

    const assistantMsg: ChatMessage = {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      streaming: true,
      toolCalls: [],
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setIsStreaming(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mode,
          messages: [...messages, userMsg],
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';

      const processLine = (line: string) => {
        line = line.trim();
        if (!line) return;
        try {
          const data = JSON.parse(line);
          if (data.content) {
            fullContent += data.content;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, content: fullContent }
                  : m,
              ),
            );
          }
          if (data.tool_call) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? {
                      ...m,
                      toolCalls: [...(m.toolCalls || []), data.tool_call],
                    }
                  : m,
              ),
            );
          }
        } catch (e) {
          console.warn('Failed to parse NDJSON line:', line, e);
        }
      };

      // 流式读取
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(processLine);
      }

      // 处理最后剩余 buffer
      if (buffer) {
        processLine(buffer);
      }
    } catch (e) {
      console.error('Stream error:', e);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id
            ? {
                ...m,
                content: m.content + `\n\n❌ **错误**: ${e instanceof Error ? e.message : String(e)}`,
                streaming: false,
              }
            : m,
        ),
      );
    } finally {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id ? { ...m, streaming: false } : m,
        ),
      );
      setIsStreaming(false);
    }
  }

  function handleClear() {
    if (isStreaming) return;
    setMessages([]);
  }

  function handleCopyCode(code: string) {
    navigator.clipboard.writeText(code).catch(console.error);
  }

  if (!visible) return null;

  return (
    <div ref={containerRef} style={styles.container}>
      {/* 顶部模式 Tab */}
      <div style={styles.modeBar}>
        {(['ask', 'edit', 'agent'] as ComposerMode[]).map((m) => (
          <button
            key={m}
            style={{
              ...styles.modeTab,
              ...(mode === m ? styles.modeTabActive : {}),
            }}
            onClick={() => setMode(m)}
          >
            {m === 'ask' && 'Ask'}
            {m === 'edit' && 'Edit'}
            {m === 'agent' && 'Agent'}
          </button>
        ))}
        {messages.length > 0 && (
          <button
            style={styles.clearBtn}
            onClick={handleClear}
            disabled={isStreaming}
            title="新建会话"
          >
            清空
          </button>
        )}
      </div>

      {/* 消息列表 */}
      <div style={styles.messagesContainer}>
        {messages.length === 0 ? (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>💬</div>
            <p style={styles.emptyTitle}>Ask me anything about your code...</p>
            <p style={styles.emptySubtitle}>
              {mode === 'ask' && '问我任何关于代码的问题'}
              {mode === 'edit' && '让我帮你修改代码'}
              {mode === 'agent' && '让我自动完成任务'}
            </p>
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              onCopyCode={handleCopyCode}
            />
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 底部输入区 */}
      <div style={styles.inputContainer}>
        <CommandInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          disabled={isStreaming}
          placeholder={
            mode === 'ask'
              ? 'Ask anything about your code...'
              : mode === 'edit'
              ? 'Describe the changes you want...'
              : 'What should I do for you?'
          }
        />
      </div>

      {/* 流式动画样式 */}
      {isStreaming && <StreamingCursorStyle />}
    </div>
  );
}

function MessageBubble({
  message,
  onCopyCode,
}: {
  message: ChatMessage;
  onCopyCode: (code: string) => void;
}) {
  const [toolExpanded, setToolExpanded] = useState(true);

  if (message.role === 'user') {
    return (
      <div style={styles.userBubble}>
        <div style={styles.userContent}>{message.content}</div>
      </div>
    );
  }

  // assistant
  return (
    <div style={styles.assistantContainer}>
      <div style={styles.assistantContent}>
        <MessageContent content={message.content} streaming={message.streaming} onCopyCode={onCopyCode} />
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div style={styles.toolCallsContainer}>
            {message.toolCalls.map((tool, idx) => (
              <div key={idx} style={styles.toolCard}>
                <button
                  style={styles.toolHeader}
                  onClick={() => setToolExpanded(!toolExpanded)}
                >
                  <span style={styles.toolName}>{tool.name}</span>
                  {tool.success === true && (
                    <span style={{ ...styles.toolStatus, color: CSS['--success'] }}>
                      ✓
                    </span>
                  )}
                  {tool.success === false && (
                    <span style={{ ...styles.toolStatus, color: CSS['--error'] }}>
                      ✗
                    </span>
                  )}
                  <span style={styles.toolToggle}>
                    {toolExpanded ? '▼' : '▶'}
                  </span>
                </button>
                {toolExpanded && tool.args && (
                  <pre style={styles.toolArgs}>
                    {JSON.stringify(tool.args, null, 2)}
                  </pre>
                )}
                {toolExpanded && tool.result && (
                  <pre style={styles.toolResult}>
                    {typeof tool.result === 'string'
                      ? tool.result
                      : JSON.stringify(tool.result, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MessageContent({
  content,
  streaming,
  onCopyCode,
}: {
  content: string;
  streaming?: boolean;
  onCopyCode: (code: string) => void;
}) {
  // 简单分割代码块（不依赖 markdown 解析库）
  const blocks = splitCodeBlocks(content);

  return (
    <>
      {blocks.map((block, idx) => {
        if (block.type === 'text') {
          return (
            <span key={idx} style={styles.textBlock}>
              {block.content}
              {streaming && idx === blocks.length - 1 && (
                <span className="streaming-cursor" style={styles.cursor}>
                  ▋
                </span>
              )}
            </span>
          );
        }
        // code block
        return (
          <div key={idx} style={styles.codeBlockContainer}>
            <div style={styles.codeBlockHeader}>
              <span style={styles.codeBlockLang}>{block.lang || 'code'}</span>
              <button
                style={styles.copyBtn}
                onClick={() => onCopyCode(block.content)}
              >
                📋 复制
              </button>
            </div>
            <pre style={styles.codeBlock}>
              <code>{block.content}</code>
            </pre>
          </div>
        );
      })}
    </>
  );
}

// 简单分割 ``` 包裹的代码块
interface ContentBlock {
  type: 'text' | 'code';
  content: string;
  lang?: string;
}
function splitCodeBlocks(content: string): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  const lines = content.split('\n');
  let inCode = false;
  let currentText = '';
  let currentCode = '';
  let currentLang = '';

  for (const line of lines) {
    if (line.startsWith('```')) {
      if (!inCode) {
        // start code block
        if (currentText) {
          blocks.push({ type: 'text', content: currentText });
          currentText = '';
        }
        inCode = true;
        currentLang = line.slice(3).trim();
      } else {
        // end code block
        blocks.push({
          type: 'code',
          content: currentCode.replace(/\n$/, ''),
          lang: currentLang,
        });
        currentCode = '';
        currentLang = '';
        inCode = false;
      }
    } else if (inCode) {
      currentCode += line + '\n';
    } else {
      currentText += line + '\n';
    }
  }

  if (inCode && currentCode) {
    blocks.push({
      type: 'code',
      content: currentCode.replace(/\n$/, ''),
      lang: currentLang,
    });
  } else if (currentText) {
    blocks.push({ type: 'text', content: currentText });
  }

  return blocks;
}

function StreamingCursorStyle() {
  const id = 'streaming-cursor-keyframe';
  if (typeof document !== 'undefined' && !document.getElementById(id)) {
    const style = document.createElement('style');
    style.id = id;
    style.textContent = `
      @keyframes blink {
        0%, 50% { opacity: 1; }
        51%, 100% { opacity: 0; }
      }
      .streaming-cursor {
        animation: blink 1s infinite;
      }
      @keyframes fadeIn {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
      }
    `;
    document.head.appendChild(style);
  }
  return null;
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    width: '100%',
    background: CSS['--bg-primary'],
    fontFamily: CSS['--font-sans'],
  },
  modeBar: {
    display: 'flex',
    alignItems: 'center',
    height: 40,
    borderBottom: `1px solid ${CSS['--border-color']}`,
    background: CSS['--bg-secondary'],
    padding: '0 8px',
    gap: 4,
    flexShrink: 0,
    justifyContent: 'space-between',
  },
  modeTab: {
    padding: '0 16px',
    height: '100%',
    border: 'none',
    background: 'transparent',
    color: CSS['--text-secondary'],
    fontSize: 13,
    cursor: 'pointer',
    borderBottom: '2px solid transparent',
    transition: 'all 0.15s',
  },
  modeTabActive: {
    color: CSS['--accent'],
    borderBottom: `2px solid ${CSS['--accent']}`,
    background: CSS['--bg-primary'],
  },
  clearBtn: {
    marginLeft: 'auto',
    padding: '4px 12px',
    border: `1px solid ${CSS['--border-color']}`,
    background: 'transparent',
    color: CSS['--text-secondary'],
    borderRadius: 4,
    fontSize: 12,
    cursor: 'pointer',
  },
  messagesContainer: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: '12px 16px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 16,
  },
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: CSS['--text-tertiary'],
    animation: 'fadeIn 0.3s ease-out',
  },
  emptyIcon: { fontSize: 48, marginBottom: 12, opacity: 0.4 },
  emptyTitle: { margin: '0 0 8px', fontSize: 16, color: CSS['--text-secondary'] },
  emptySubtitle: { margin: 0, fontSize: 13, color: CSS['--text-tertiary'] },
  userBubble: {
    display: 'flex',
    justifyContent: 'flex-end' as const,
    animation: 'fadeIn 0.2s ease-out',
  },
  userContent: {
    maxWidth: '85%',
    padding: '10px 14px',
    background: CSS['--accent'],
    color: '#ffffff',
    borderRadius: '14px 14px 2px 14px',
    fontSize: 14,
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
  },
  assistantContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    animation: 'fadeIn 0.2s ease-out',
  },
  assistantContent: {
    maxWidth: '100%',
    borderRadius: '2px 14px 14px 14px',
    fontSize: 14,
    lineHeight: 1.6,
  },
  textBlock: {
    color: CSS['--text-primary'],
    whiteSpace: 'pre-wrap' as const,
  },
  cursor: {
    color: CSS['--accent'],
    fontWeight: 'bold',
  },
  codeBlockContainer: {
    margin: '8px 0',
    borderRadius: 6,
    overflow: 'hidden',
    border: `1px solid ${CSS['--border-color']}`,
  },
  codeBlockHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 12px',
    background: CSS['--bg-secondary'],
    borderBottom: `1px solid ${CSS['--border-color']}`,
  },
  codeBlockLang: {
    fontSize: 11,
    color: CSS['--text-secondary'],
    fontFamily: CSS['--font-mono'],
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  copyBtn: {
    padding: '2px 8px',
    border: `1px solid ${CSS['--border-color']}`,
    background: CSS['--bg-primary'],
    color: CSS['--text-secondary'],
    borderRadius: 4,
    fontSize: 11,
    cursor: 'pointer',
  },
  codeBlock: {
    margin: 0,
    padding: '10px 12px',
    background: CSS['--bg-secondary'],
    color: CSS['--text-primary'],
    fontSize: 13,
    lineHeight: 1.5,
    fontFamily: CSS['--font-mono'],
    overflowX: 'auto' as const,
  },
  toolCallsContainer: {
    marginTop: 8,
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  toolCard: {
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 6,
    background: CSS['--bg-secondary'],
    overflow: 'hidden',
  },
  toolHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    width: '100%',
    padding: '8px 12px',
    background: CSS['--bg-secondary'],
    border: 'none',
    cursor: 'pointer',
    textAlign: 'left' as const,
  },
  toolName: {
    flex: 1,
    fontSize: 13,
    fontWeight: 500,
    color: CSS['--text-primary'],
    fontFamily: CSS['--font-mono'],
  },
  toolStatus: {
    fontSize: 14,
    fontWeight: 'bold',
    flexShrink: 0,
  },
  toolToggle: {
    color: CSS['--text-tertiary'],
    fontSize: 10,
    flexShrink: 0,
  },
  toolArgs: {
    margin: 0,
    padding: '8px 12px',
    background: CSS['--bg-primary'],
    borderTop: `1px solid ${CSS['--border-color']}`,
    fontSize: 11,
    fontFamily: CSS['--font-mono'],
    color: CSS['--text-secondary'],
    maxHeight: 150,
    overflowY: 'auto' as const,
  },
  toolResult: {
    margin: 0,
    padding: '8px 12px',
    background: CSS['--bg-primary'],
    borderTop: `1px solid ${CSS['--border-color']}`,
    fontSize: 11,
    fontFamily: CSS['--font-mono'],
    color: CSS['--text-secondary'],
    maxHeight: 200,
    overflowY: 'auto' as const,
  },
  inputContainer: {
    borderTop: `1px solid ${CSS['--border-color']}`,
    flexShrink: 0,
  },
};
