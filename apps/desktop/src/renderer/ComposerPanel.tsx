/**
 * ComposerPanel.tsx — Codex 风格统一对话面板
 *
 * 对标 Cursor Composer + TRAE Agent Mode：
 *   - Ask / Edit / Agent 三模式统一面板
 *   - Ask/Edit: NDJSON 流式响应 (/api/v1/chat/stream)
 *   - Agent: 增强流式响应 (/api/v1/chat/agent)
 *     - thinking: Agent 思考过程
 *     - plan: 执行计划步骤
 *     - step_start/step_end: 步骤执行状态
 *     - file_change: 文件变更(diff)
 *     - done: 最终结果
 *   - 浅色主题风格
 */
import { useEffect, useRef, useState } from 'react';
import { CommandInput } from './CommandInput';
import { API_BASE } from './apiConfig';

export interface ToolCall {
  name: string;
  args?: any;
  result?: any;
  success?: boolean;
}

export interface PlanStep {
  description: string;
  action: string;
  target: string;
  status: 'pending' | 'running' | 'done' | 'failed';
}

export interface FileChange {
  path: string;
  action: 'create' | 'modify' | 'delete';
  diff: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  toolCalls?: ToolCall[];
  planSteps?: PlanStep[];
  fileChanges?: FileChange[];
  thinking?: string;
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

  // Ask/Edit 模式流式调用
  async function handleSendAsk() {
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, messages: [...messages, userMsg] }),
      });

      if (!response.ok || !response.body) throw new Error(`Request failed: ${response.status}`);

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
              prev.map((m) => (m.id === assistantMsg.id ? { ...m, content: fullContent } : m)),
            );
          }
          if (data.tool_call) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsg.id
                  ? { ...m, toolCalls: [...(m.toolCalls || []), data.tool_call] }
                  : m,
              ),
            );
          }
        } catch (e) {
          console.warn('Failed to parse NDJSON line:', line, e);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(processLine);
      }

      if (buffer) processLine(buffer);
    } catch (e) {
      console.error('Stream error:', e);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id
            ? { ...m, content: m.content + `\n\n❌ **错误**: ${e instanceof Error ? e.message : String(e)}`, streaming: false }
            : m,
        ),
      );
    } finally {
      setMessages((prev) => prev.map((m) => (m.id === assistantMsg.id ? { ...m, streaming: false } : m)));
      setIsStreaming(false);
    }
  }

  // Agent 模式流式调用 (/api/v1/chat/agent)
  async function handleSendAgent() {
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
      planSteps: [],
      fileChanges: [],
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setIsStreaming(true);

    const updateMsg = (updater: (m: ChatMessage) => ChatMessage) => {
      setMessages((prev) => prev.map((m) => (m.id === assistantMsg.id ? updater(m) : m)));
    };

    try {
      const response = await fetch(`${API_BASE}/api/v1/chat/agent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: [...messages, userMsg] }),
      });

      if (!response.ok || !response.body) throw new Error(`Agent request failed: ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';

      const processLine = (line: string) => {
        line = line.trim();
        if (!line) return;
        try {
          const data = JSON.parse(line);
          switch (data.type) {
            case 'thinking':
              updateMsg((m) => ({ ...m, thinking: (m.thinking || '') + data.content }));
              break;
            case 'message':
              fullContent += data.content;
              updateMsg((m) => ({ ...m, content: fullContent }));
              break;
            case 'plan':
              updateMsg((m) => ({
                ...m,
                planSteps: (data.steps || []).map((s: any) => ({ ...s, status: 'pending' as const })),
              }));
              break;
            case 'step_start':
              updateMsg((m) => ({
                ...m,
                planSteps: (m.planSteps || []).map((s, i) =>
                  i === data.index ? { ...s, status: 'running' as const } : s,
                ),
              }));
              break;
            case 'step_end':
              updateMsg((m) => ({
                ...m,
                planSteps: (m.planSteps || []).map((s, i) =>
                  i === data.index ? { ...s, status: data.error ? ('failed' as const) : ('done' as const) } : s,
                ),
              }));
              break;
            case 'file_change':
              updateMsg((m) => ({
                ...m,
                fileChanges: [...(m.fileChanges || []), { path: data.path, action: data.action, diff: data.diff || '' }],
              }));
              fullContent += `\n📝 **${data.action === 'create' ? '创建' : data.action === 'delete' ? '删除' : '修改'}**: \`${data.path}\`\n`;
              updateMsg((m) => ({ ...m, content: fullContent }));
              break;
            case 'done':
              updateMsg((m) => ({ ...m, streaming: false }));
              if (data.status === 'failed') {
                fullContent += `\n\n❌ **执行失败**: ${data.error || '未知错误'}`;
                updateMsg((m) => ({ ...m, content: fullContent }));
              } else {
                fullContent += `\n\n✅ **任务完成** (${(data.changes || []).length} 个文件变更)`;
                updateMsg((m) => ({ ...m, content: fullContent }));
              }
              break;
          }
        } catch (e) {
          console.warn('Agent NDJSON parse error:', line, e);
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        lines.forEach(processLine);
      }

      if (buffer) processLine(buffer);
    } catch (e) {
      console.error('Agent stream error:', e);
      updateMsg((m) => ({
        ...m,
        content: m.content + `\n\n❌ **错误**: ${e instanceof Error ? e.message : String(e)}`,
        streaming: false,
      }));
    } finally {
      updateMsg((m) => ({ ...m, streaming: false }));
      setIsStreaming(false);
    }
  }

  // 统一入口
  function handleSend() {
    if (mode === 'agent') {
      handleSendAgent();
    } else {
      handleSendAsk();
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
  const [planExpanded, setPlanExpanded] = useState(true);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);

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
        {/* Thinking (Agent 思考过程) */}
        {message.thinking && (
          <div style={styles.thinkingContainer}>
            <button
              style={styles.thinkingHeader}
              onClick={() => setThinkingExpanded(!thinkingExpanded)}
            >
              <span style={{ fontSize: 12 }}>🧠 思考过程</span>
              <span style={styles.toolToggle}>{thinkingExpanded ? '▼' : '▶'}</span>
            </button>
            {thinkingExpanded && (
              <pre style={styles.thinkingContent}>{message.thinking}</pre>
            )}
          </div>
        )}

        {/* Plan Steps (Agent 执行计划) */}
        {message.planSteps && message.planSteps.length > 0 && (
          <div style={styles.planContainer}>
            <button
              style={styles.planHeader}
              onClick={() => setPlanExpanded(!planExpanded)}
            >
              <span style={{ fontSize: 12, fontWeight: 600 }}>
                📋 执行计划 ({message.planSteps.filter(s => s.status === 'done').length}/{message.planSteps.length} 完成)
              </span>
              <span style={styles.toolToggle}>{planExpanded ? '▼' : '▶'}</span>
            </button>
            {planExpanded && (
              <div style={styles.planSteps}>
                {message.planSteps.map((step, idx) => (
                  <div key={idx} style={styles.planStep}>
                    <span style={{
                      ...styles.planStepStatus,
                      color: step.status === 'done' ? CSS['--success'] :
                             step.status === 'failed' ? CSS['--error'] :
                             step.status === 'running' ? CSS['--accent'] : CSS['--text-tertiary'],
                    }}>
                      {step.status === 'done' ? '✓' : step.status === 'failed' ? '✗' : step.status === 'running' ? '⟳' : '○'}
                    </span>
                    <span style={styles.planStepText}>
                      {step.description}
                      {step.target && <span style={styles.planStepTarget}> → {step.target}</span>}
                    </span>
                    <span style={styles.planStepAction}>{step.action}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* File Changes (Agent 文件变更) */}
        {message.fileChanges && message.fileChanges.length > 0 && (
          <div style={styles.fileChangesContainer}>
            {message.fileChanges.map((fc, idx) => (
              <FileChangeCard key={idx} change={fc} />
            ))}
          </div>
        )}

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

/** 文件变更卡片 */
function FileChangeCard({ change }: { change: FileChange }) {
  const [expanded, setExpanded] = useState(false);
  const actionLabel = change.action === 'create' ? '创建' : change.action === 'delete' ? '删除' : '修改';
  const actionColor = change.action === 'create' ? CSS['--success'] : change.action === 'delete' ? CSS['--error'] : CSS['--accent'];

  return (
    <div style={styles.fileChangeCard}>
      <button style={styles.fileChangeHeader} onClick={() => setExpanded(!expanded)}>
        <span style={{ color: actionColor, marginRight: 6, fontWeight: 600 }}>{actionLabel}</span>
        <span style={styles.fileChangePath}>{change.path}</span>
        <span style={styles.toolToggle}>{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && change.diff && (
        <pre style={styles.fileChangeDiff}>{change.diff}</pre>
      )}
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
  // Agent 模式新增样式
  thinkingContainer: {
    marginBottom: 8,
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 6,
    overflow: 'hidden' as const,
    background: 'var(--bg-tertiary)',
  },
  thinkingHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    width: '100%',
    background: 'none',
    border: 'none',
    padding: '6px 10px',
    cursor: 'pointer',
    color: CSS['--text-secondary'],
    fontSize: 11,
  },
  thinkingContent: {
    margin: 0,
    padding: '8px 10px',
    fontSize: 11,
    fontFamily: 'var(--font-mono), monospace',
    color: CSS['--text-tertiary'],
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
    maxHeight: 200,
    overflow: 'auto',
    borderTop: `1px solid ${CSS['--border-color']}`,
  },
  planContainer: {
    marginBottom: 8,
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 6,
    overflow: 'hidden' as const,
    background: CSS['--bg-primary'],
  },
  planHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    width: '100%',
    background: 'none',
    border: 'none',
    padding: '6px 10px',
    cursor: 'pointer',
    color: CSS['--text-primary'],
  },
  planSteps: {
    borderTop: `1px solid ${CSS['--border-color']}`,
    padding: '4px 0',
  },
  planStep: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '4px 10px',
    fontSize: 12,
  },
  planStepStatus: {
    width: 16,
    textAlign: 'center' as const,
    fontWeight: 600,
    flexShrink: 0,
  },
  planStepText: {
    flex: 1,
    color: CSS['--text-primary'],
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  planStepTarget: {
    color: CSS['--accent'],
    fontFamily: 'var(--font-mono), monospace',
    fontSize: 11,
  },
  planStepAction: {
    fontSize: 10,
    padding: '1px 6px',
    background: 'var(--bg-tertiary)',
    borderRadius: 3,
    color: CSS['--text-secondary'],
    flexShrink: 0,
  },
  fileChangesContainer: {
    marginBottom: 8,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 4,
  },
  fileChangeCard: {
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 6,
    overflow: 'hidden' as const,
    background: CSS['--bg-primary'],
  },
  fileChangeHeader: {
    display: 'flex',
    alignItems: 'center',
    width: '100%',
    background: 'none',
    border: 'none',
    padding: '6px 10px',
    cursor: 'pointer',
    fontSize: 12,
  },
  fileChangePath: {
    flex: 1,
    textAlign: 'left' as const,
    fontFamily: 'var(--font-mono), monospace',
    fontSize: 11,
    color: CSS['--text-primary'],
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  fileChangeDiff: {
    margin: 0,
    padding: '8px 10px',
    fontSize: 10,
    fontFamily: 'var(--font-mono), monospace',
    background: 'var(--bg-secondary)',
    color: CSS['--text-primary'],
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
    maxHeight: 200,
    overflow: 'auto',
    borderTop: `1px solid ${CSS['--border-color']}`,
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
