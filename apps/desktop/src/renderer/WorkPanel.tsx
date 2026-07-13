/**
 * WorkPanel.tsx — Work Mode 面板（Office Agent 任务）
 *
 * 功能：
 *   - 快速操作按钮（生成周报、分析 Excel、创建 PPT、转换 PDF、文档摘要）
 *   - 自定义任务输入
 *   - NDJSON 流式响应解析
 *   - 任务历史记录与状态展示
 *   - 浅色主题风格（Cursor/Codex）
 */
import { useEffect, useRef, useState } from 'react';

const API_BASE = 'http://localhost:8000';

export interface WorkTask {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: string;
  timestamp: number;
}

export interface WorkPanelProps {
  visible: boolean;
}

interface QuickAction {
  id: string;
  label: string;
  icon: string;
  prompt: string;
}

const QUICK_ACTIONS: QuickAction[] = [
  { id: 'weekly-report', label: '生成周报', icon: '📊', prompt: '请帮我生成一份本周工作周报' },
  { id: 'analyze-excel', label: '分析 Excel', icon: '📈', prompt: '请帮我分析这份 Excel 表格数据' },
  { id: 'create-ppt', label: '创建 PPT', icon: '🖥️', prompt: '请帮我创建一份演示文稿' },
  { id: 'convert-pdf', label: '转换 PDF', icon: '📄', prompt: '请帮我转换 PDF 文档' },
  { id: 'doc-summary', label: '文档摘要', icon: '📝', prompt: '请帮我生成文档摘要' },
];

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

const STATUS_CONFIG: Record<WorkTask['status'], { label: string; color: string; bg: string }> = {
  pending: { label: '等待中', color: CSS['--text-tertiary'], bg: CSS['--bg-tertiary'] },
  running: { label: '执行中', color: CSS['--accent'], bg: CSS['--accent-light'] },
  completed: { label: '已完成', color: CSS['--success'], bg: 'rgba(34, 197, 94, 0.08)' },
  failed: { label: '失败', color: CSS['--error'], bg: 'rgba(220, 38, 38, 0.08)' },
};

export function WorkPanel({ visible }: WorkPanelProps) {
  const [tasks, setTasks] = useState<WorkTask[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [input, setInput] = useState('');
  const tasksEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    if (tasksEndRef.current) {
      tasksEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [tasks]);

  // 输入框自动增高
  const adjustTextareaHeight = () => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const minHeight = 44;
    const maxHeight = 120;
    const newHeight = Math.min(Math.max(ta.scrollHeight, minHeight), maxHeight);
    ta.style.height = `${newHeight}px`;
  };

  useEffect(() => {
    adjustTextareaHeight();
  }, [input]);

  // 执行任务（NDJSON 流式调用）
  async function submitTask(prompt: string, title: string) {
    if (!prompt.trim() || isStreaming) return;

    const taskId = `t-${Date.now()}`;
    const task: WorkTask = {
      id: taskId,
      title,
      description: prompt,
      status: 'running',
      timestamp: Date.now(),
    };

    setTasks((prev) => [...prev, task]);
    setInput('');
    setIsStreaming(true);

    try {
      const response = await fetch(`${API_BASE}/api/v1/agentos/natural`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt,
          stream: true,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`Request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullResult = '';

      const processLine = (line: string) => {
        line = line.trim();
        if (!line) return;
        try {
          const data = JSON.parse(line);
          if (data.content) {
            fullResult += data.content;
            setTasks((prev) =>
              prev.map((t) =>
                t.id === taskId ? { ...t, result: fullResult, status: 'running' as const } : t,
              ),
            );
          }
          if (data.done) {
            setTasks((prev) =>
              prev.map((t) =>
                t.id === taskId
                  ? { ...t, result: fullResult, status: 'completed' as const }
                  : t,
              ),
            );
          }
          if (data.error) {
            throw new Error(data.error);
          }
        } catch (e) {
          if (e instanceof SyntaxError) {
            console.warn('Failed to parse NDJSON line:', line, e);
          } else {
            throw e;
          }
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

      // 如果流结束但未标记 done，标记为完成
      setTasks((prev) =>
        prev.map((t) =>
          t.id === taskId && t.status === 'running'
            ? { ...t, status: 'completed' as const }
            : t,
        ),
      );
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e);
      setTasks((prev) =>
        prev.map((t) =>
          t.id === taskId
            ? { ...t, result: `❌ ${errorMsg}`, status: 'failed' as const }
            : t,
        ),
      );
    } finally {
      setIsStreaming(false);
    }
  }

  function handleQuickAction(action: QuickAction) {
    submitTask(action.prompt, action.label);
  }

  function handleSend() {
    const text = input.trim();
    if (!text) return;
    submitTask(text, '自定义任务');
  }

  function handleClear() {
    if (isStreaming) return;
    setTasks([]);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  if (!visible) return null;

  return (
    <div style={styles.container}>
      {/* 标题栏 */}
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.headerIcon}>⚡</span>
          <span style={styles.headerTitle}>Work Mode</span>
          <span style={styles.headerSubtitle}>OFFICE AGENT</span>
        </div>
        {tasks.length > 0 && (
          <button
            style={styles.clearBtn}
            onClick={handleClear}
            disabled={isStreaming}
            title="清空任务历史"
          >
            清空
          </button>
        )}
      </div>

      {/* 快速操作按钮区 */}
      <div style={styles.quickActions}>
        <div style={styles.quickActionsLabel}>快速操作</div>
        <div style={styles.quickActionsRow}>
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action.id}
              style={styles.quickActionBtn}
              onClick={() => handleQuickAction(action)}
              disabled={isStreaming}
              title={action.prompt}
            >
              <span style={styles.quickActionIcon}>{action.icon}</span>
              <span style={styles.quickActionLabel}>{action.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 任务历史区 */}
      <div style={styles.tasksContainer}>
        {tasks.length === 0 ? (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>📋</div>
            <p style={styles.emptyTitle}>开始你的 Office 任务</p>
            <p style={styles.emptySubtitle}>
              选择一个快速操作或输入自定义任务来开始
            </p>
          </div>
        ) : (
          tasks.map((task) => (
            <TaskCard key={task.id} task={task} />
          ))
        )}
        <div ref={tasksEndRef} />
      </div>

      {/* 底部输入区 */}
      <div style={styles.inputContainer}>
        <div style={styles.inputRow}>
          <textarea
            ref={inputRef}
            style={styles.textarea}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="描述你的 Office 任务，例如：帮我分析这份 Excel 报表..."
            disabled={isStreaming}
            rows={1}
          />
          <button
            style={{
              ...styles.sendBtn,
              opacity: input.trim() && !isStreaming ? 1 : 0.4,
              cursor: input.trim() && !isStreaming ? 'pointer' : 'default',
            }}
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
          >
            ↑
          </button>
        </div>
      </div>

      {/* 流式动画 */}
      {isStreaming && <StreamingCursorStyle />}
    </div>
  );
}

function TaskCard({ task }: { task: WorkTask }) {
  const statusCfg = STATUS_CONFIG[task.status];
  const [expanded, setExpanded] = useState(task.status === 'running');

  useEffect(() => {
    if (task.status === 'running') {
      setExpanded(true);
    }
  }, [task.status]);

  return (
    <div style={styles.taskCard}>
      <div style={styles.taskHeader}>
        <div style={styles.taskTitleRow}>
          <span style={styles.taskIcon}>
            {task.status === 'running' ? '⏳' : task.status === 'completed' ? '✅' : task.status === 'failed' ? '❌' : '⏸️'}
          </span>
          <span style={styles.taskTitle}>{task.title}</span>
        </div>
        <div style={styles.taskHeaderRight}>
          <span
            style={{
              ...styles.statusBadge,
              color: statusCfg.color,
              background: statusCfg.bg,
            }}
          >
            {statusCfg.label}
          </span>
          <span style={styles.taskTime}>
            {new Date(task.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </span>
          {task.result && (
            <button
              style={styles.expandBtn}
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? '收起' : '展开'}
            </button>
          )}
        </div>
      </div>
      <div style={styles.taskDescription}>{task.description}</div>
      {expanded && task.result && (
        <div style={styles.taskResult}>
          <pre style={styles.taskResultPre}>{task.result}</pre>
        </div>
      )}
    </div>
  );
}

function StreamingCursorStyle() {
  const id = 'workpanel-streaming-cursor-keyframe';
  if (typeof document !== 'undefined' && !document.getElementById(id)) {
    const style = document.createElement('style');
    style.id = id;
    style.textContent = `
      @keyframes workPanelBlink {
        0%, 50% { opacity: 1; }
        51%, 100% { opacity: 0; }
      }
      @keyframes workPanelFadeIn {
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
  // 标题栏
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 40,
    borderBottom: `1px solid ${CSS['--border-color']}`,
    background: CSS['--bg-secondary'],
    padding: '0 12px',
    flexShrink: 0,
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  },
  headerIcon: {
    fontSize: 16,
  },
  headerTitle: {
    fontSize: 13,
    fontWeight: 700,
    color: CSS['--text-primary'],
  },
  headerSubtitle: {
    fontSize: 10,
    color: CSS['--text-tertiary'],
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
  },
  clearBtn: {
    padding: '4px 12px',
    border: `1px solid ${CSS['--border-color']}`,
    background: 'transparent',
    color: CSS['--text-secondary'],
    borderRadius: 4,
    fontSize: 12,
    cursor: 'pointer',
  },
  // 快速操作
  quickActions: {
    padding: '12px 12px 8px',
    flexShrink: 0,
  },
  quickActionsLabel: {
    fontSize: 11,
    fontWeight: 600,
    color: CSS['--text-tertiary'],
    textTransform: 'uppercase' as const,
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  quickActionsRow: {
    display: 'flex',
    flexWrap: 'wrap' as const,
    gap: 6,
  },
  quickActionBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 8,
    background: CSS['--bg-primary'],
    cursor: 'pointer',
    fontSize: 13,
    color: CSS['--text-primary'],
    transition: 'all 0.15s',
    whiteSpace: 'nowrap' as const,
  },
  quickActionIcon: {
    fontSize: 14,
  },
  quickActionLabel: {
    fontWeight: 500,
  },
  // 任务列表
  tasksContainer: {
    flex: 1,
    overflowY: 'auto' as const,
    padding: '8px 12px',
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 8,
  },
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: CSS['--text-tertiary'],
    animation: 'workPanelFadeIn 0.3s ease-out',
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 12,
    opacity: 0.4,
  },
  emptyTitle: {
    margin: '0 0 8px',
    fontSize: 16,
    color: CSS['--text-secondary'],
  },
  emptySubtitle: {
    margin: 0,
    fontSize: 13,
    color: CSS['--text-tertiary'],
  },
  // 任务卡片
  taskCard: {
    border: `1px solid ${CSS['--border-color']}`,
    borderRadius: 8,
    background: CSS['--bg-primary'],
    overflow: 'hidden',
    animation: 'workPanelFadeIn 0.2s ease-out',
  },
  taskHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    background: CSS['--bg-secondary'],
    gap: 8,
  },
  taskTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flex: 1,
    minWidth: 0,
  },
  taskIcon: {
    fontSize: 14,
    flexShrink: 0,
  },
  taskTitle: {
    fontSize: 13,
    fontWeight: 600,
    color: CSS['--text-primary'],
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  },
  taskHeaderRight: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    flexShrink: 0,
  },
  statusBadge: {
    fontSize: 11,
    fontWeight: 600,
    padding: '2px 8px',
    borderRadius: 10,
    whiteSpace: 'nowrap' as const,
  },
  taskTime: {
    fontSize: 11,
    color: CSS['--text-tertiary'],
    whiteSpace: 'nowrap' as const,
  },
  expandBtn: {
    padding: '2px 8px',
    border: `1px solid ${CSS['--border-color']}`,
    background: 'transparent',
    color: CSS['--text-secondary'],
    borderRadius: 4,
    fontSize: 11,
    cursor: 'pointer',
  },
  taskDescription: {
    padding: '8px 12px',
    fontSize: 13,
    color: CSS['--text-secondary'],
    lineHeight: 1.5,
    borderBottom: `1px solid ${CSS['--border-color']}`,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
  },
  taskResult: {
    padding: '8px 12px',
    background: CSS['--bg-primary'],
  },
  taskResultPre: {
    margin: 0,
    padding: '8px 12px',
    background: CSS['--bg-secondary'],
    borderRadius: 6,
    fontSize: 12,
    fontFamily: CSS['--font-mono'],
    color: CSS['--text-primary'],
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
    wordBreak: 'break-word' as const,
    maxHeight: 300,
    overflowY: 'auto' as const,
  },
  // 输入区
  inputContainer: {
    borderTop: `1px solid ${CSS['--border-color']}`,
    flexShrink: 0,
  },
  inputRow: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: 8,
    padding: 12,
  },
  textarea: {
    flex: 1,
    minHeight: 44,
    maxHeight: 120,
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
};

export default WorkPanel;