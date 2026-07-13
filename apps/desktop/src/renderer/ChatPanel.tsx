/**
 * AI 对话面板(Phase 3.1 右侧栏)
 *
 * 功能:
 *   - 与 fnixagent 后端流式对话(SSE / NDJSON)
 *   - 显示用户消息与 AI 回复(支持 thought / action / text / error 分块)
 *   - 自动滚动到底部
 *   - 创建 / 切换会话
 *   - 错误处理与重试提示
 */
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { sdk } from '@fnixagent/sdk';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'error';
  content: string;
  /** 流式分块类型(仅 assistant 消息) */
  chunks?: { type: string; content: string }[];
  streaming?: boolean;
}

interface ChatPanelProps {
  /** 当前激活的文件路径(显示在上下文中) */
  activeFilePath: string | null;
}

export function ChatPanel({ activeFilePath }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function ensureSession() {
    if (sessionId) return sessionId;
    try {
      const resp = await sdk.chat.createSession();
      setSessionId(resp.session_id);
      return resp.session_id;
    } catch {
      return null;
    }
  }

  async function handleSend(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
    };
    const assistantMsg: ChatMessage = {
      id: `a-${Date.now()}`,
      role: 'assistant',
      content: '',
      chunks: [],
      streaming: true,
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setLoading(true);

    const sid = await ensureSession();
    if (!sid) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, streaming: false, role: 'error', content: '无法创建会话,请检查后端连接' }
            : m,
        ),
      );
      setLoading(false);
      return;
    }

    try {
      const context: Record<string, unknown> = {};
      if (activeFilePath) context.current_file = activeFilePath;

      let aggregated = '';
      for await (const chunk of sdk.chat.stream({
        session_id: sid,
        user_input: text,
        context,
      })) {
        aggregated += chunk.content ?? '';
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? {
                  ...m,
                  content: aggregated,
                  chunks: [...(m.chunks ?? []), { type: chunk.chunk_type, content: chunk.content }],
                }
              : m,
          ),
        );
      }
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantMsg.id ? { ...m, streaming: false } : m)),
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id
            ? {
                ...m,
                streaming: false,
                role: 'error',
                content: err instanceof Error ? err.message : 'AI 回复失败',
              }
            : m,
        ),
      );
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setMessages([]);
    setSessionId(null);
  }

  return (
    <div style={styles.container}>
      <div style={styles.toolbar}>
        <span style={styles.title}>AI 助手</span>
        {messages.length > 0 && (
          <button style={styles.clearBtn} onClick={handleClear} title="清空对话">
            清空
          </button>
        )}
      </div>

      <div style={styles.messagesContainer}>
        {messages.length === 0 ? (
          <div style={styles.welcome}>
            <div style={styles.welcomeIcon}>🤖</div>
            <p style={styles.welcomeTitle}>fnixagent 已就绪</p>
            <p style={styles.welcomeText}>
              输入问题,AI 会基于当前工作区上下文提供智能辅助。
            </p>
            {activeFilePath && (
              <div style={styles.contextBox}>
                <span style={styles.contextLabel}>当前文件:</span>
                <span style={styles.contextPath}>{activeFilePath}</span>
              </div>
            )}
          </div>
        ) : (
          messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)
        )}
        <div ref={messagesEndRef} />
      </div>

      <form style={styles.inputArea} onSubmit={handleSend}>
        <textarea
          style={styles.input}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void handleSend(e as unknown as FormEvent);
            }
          }}
          placeholder="输入消息,Enter 发送,Shift+Enter 换行..."
          disabled={loading}
          rows={3}
        />
        <button
          type="submit"
          style={loading || !input.trim() ? styles.sendBtnDisabled : styles.sendBtn}
          disabled={loading || !input.trim()}
        >
          {loading ? '发送中...' : '发送'}
        </button>
      </form>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <div style={styles.userBubble}>
        <div style={styles.userContent}>{message.content}</div>
      </div>
    );
  }

  if (message.role === 'error') {
    return (
      <div style={styles.errorBubble}>
        <span style={styles.errorIcon}>⚠️</span>
        <span style={styles.errorContent}>{message.content}</span>
      </div>
    );
  }

  // assistant
  return (
    <div style={styles.assistantBubble}>
      <div style={styles.assistantHeader}>
        <span style={styles.assistantAvatar}>🤖</span>
        <span style={styles.assistantName}>Assistant</span>
        {message.streaming && <span style={styles.streamingDot}>●</span>}
      </div>
      <div style={styles.assistantContent}>
        {message.content || (message.streaming ? '思考中...' : '')}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    width: 380,
    background: 'rgba(15, 23, 42, 0.4)',
    borderLeft: '1px solid rgba(148, 163, 184, 0.1)',
    color: '#e2e8f0',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  toolbar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    borderBottom: '1px solid rgba(148, 163, 184, 0.1)',
  },
  title: {
    fontSize: 11,
    fontWeight: 600,
    color: '#94a3b8',
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  clearBtn: {
    background: 'transparent',
    border: '1px solid rgba(148, 163, 184, 0.2)',
    color: '#94a3b8',
    cursor: 'pointer',
    fontSize: 11,
    padding: '2px 8px',
    borderRadius: 4,
  },
  messagesContainer: {
    flex: 1,
    overflow: 'auto' as const,
    padding: 12,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 12,
  },
  welcome: {
    textAlign: 'center' as const,
    padding: 32,
    color: '#64748b',
  },
  welcomeIcon: { fontSize: 40, marginBottom: 12, opacity: 0.6 },
  welcomeTitle: { margin: '0 0 8px', fontSize: 15, color: '#94a3b8', fontWeight: 600 },
  welcomeText: { margin: '0 0 16px', fontSize: 12, lineHeight: 1.6 },
  contextBox: {
    marginTop: 12,
    padding: '8px 12px',
    background: 'rgba(59, 130, 246, 0.08)',
    border: '1px solid rgba(59, 130, 246, 0.2)',
    borderRadius: 6,
    fontSize: 11,
    textAlign: 'left' as const,
  },
  contextLabel: { color: '#60a5fa', marginRight: 4 },
  contextPath: {
    color: '#94a3b8',
    fontFamily: 'monospace',
    wordBreak: 'break-all' as const,
  },
  userBubble: {
    display: 'flex',
    justifyContent: 'flex-end' as const,
  },
  userContent: {
    maxWidth: '85%',
    padding: '8px 12px',
    background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
    color: '#fff',
    borderRadius: '12px 12px 2px 12px',
    fontSize: 13,
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
  },
  assistantBubble: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 6,
  },
  assistantHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 12,
    color: '#94a3b8',
  },
  assistantAvatar: { fontSize: 14 },
  assistantName: { fontWeight: 600 },
  streamingDot: {
    color: '#60a5fa',
    fontSize: 10,
    animation: 'spin 1s linear infinite',
  },
  assistantContent: {
    padding: '10px 12px',
    background: 'rgba(30, 41, 59, 0.6)',
    borderRadius: '2px 12px 12px 12px',
    fontSize: 13,
    lineHeight: 1.6,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
    border: '1px solid rgba(148, 163, 184, 0.1)',
  },
  errorBubble: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '8px 12px',
    background: 'rgba(239, 68, 68, 0.12)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    borderRadius: 8,
    fontSize: 12,
    color: '#fca5a5',
  },
  errorIcon: { fontSize: 14 },
  errorContent: { flex: 1 },
  inputArea: {
    display: 'flex',
    gap: 8,
    padding: 12,
    borderTop: '1px solid rgba(148, 163, 184, 0.1)',
    background: 'rgba(15, 23, 42, 0.6)',
  },
  input: {
    flex: 1,
    padding: '8px 10px',
    background: 'rgba(15, 23, 42, 0.6)',
    border: '1px solid rgba(148, 163, 184, 0.2)',
    borderRadius: 8,
    color: '#e2e8f0',
    fontSize: 13,
    outline: 'none',
    resize: 'none' as const,
    fontFamily: 'inherit',
    lineHeight: 1.5,
  },
  sendBtn: {
    padding: '8px 16px',
    background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    whiteSpace: 'nowrap' as const,
  },
  sendBtnDisabled: {
    padding: '8px 16px',
    background: 'rgba(100, 116, 139, 0.3)',
    color: '#94a3b8',
    border: 'none',
    borderRadius: 8,
    cursor: 'not-allowed',
    fontSize: 13,
    fontWeight: 600,
    whiteSpace: 'nowrap' as const,
  },
};
