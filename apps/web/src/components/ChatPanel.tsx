import { useEffect, useRef, useState } from 'react';
import { Button, Input } from '@officeagent/ui';
import { useChat, type ChatMessage, type ToolCallRecord } from '../hooks/useChat';
import { useTopologyStats } from '../hooks/useTopologyStats';
import type { ChatMode } from '../hooks/useChat';

interface ChatPanelProps {
  /** 外部回调(可选,用于把发送事件通知父组件) */
  onSendMessage?: (message: string) => void;
}

/**
 * 右侧 AI 对话面板 — Phase 1.6 完整版
 *
 * 功能:
 *   ① 消息流 UI(用户/AI/工具调用三种气泡)
 *   ② 流式输出对接 /api/v1/chat/stream (NDJSON SSE)
 *   ③ 自进化模式对接 /api/v1/chat/evolve
 *   ④ 工具调用过程可视化(展开/折叠)
 *   ⑤ 拓扑路径展示(调用 /api/v1/chat/topology/stats)
 *   ⑥ 错误重试
 */
export function ChatPanel({ onSendMessage }: ChatPanelProps) {
  const {
    messages,
    mode,
    isStreaming,
    error,
    sendMessage,
    retry,
    clear,
    setMode,
  } = useChat();
  const { stats, loading: statsLoading, error: statsError, refresh } = useTopologyStats();
  const [input, setInput] = useState('');
  const [showTopology, setShowTopology] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 新消息时自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput('');
    onSendMessage?.(text);
    await sendMessage(text);
  }

  return (
    <div className="flex h-full flex-col bg-secondary/30">
      {/* 顶部工具条:模式切换 + 拓扑 + 清空 */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2 shrink-0 gap-2">
        <ModeSwitcher mode={mode} onChange={setMode} disabled={isStreaming} />
        <div className="flex items-center gap-1">
          <Button
            variant={showTopology ? 'default' : 'ghost'}
            size="sm"
            onClick={() => {
              setShowTopology(!showTopology);
              if (!showTopology && !stats) refresh();
            }}
            title="拓扑路径统计"
          >
            拓扑
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={clear}
            disabled={isStreaming}
            title="清空对话"
          >
            清空
          </Button>
        </div>
      </div>

      {/* 拓扑统计面板(可折叠) */}
      {showTopology && (
        <TopologyPanel
          stats={stats}
          loading={statsLoading}
          error={statsError}
          onRefresh={refresh}
        />
      )}

      {/* 消息流 */}
      <div ref={scrollRef} className="flex-1 overflow-auto p-3 space-y-3">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isStreaming && (
          <div className="text-xs text-muted-foreground animate-pulse">● ● ●</div>
        )}
      </div>

      {/* 错误提示 + 重试 */}
      {error && (
        <div className="border-t border-red-500/30 bg-red-500/10 px-3 py-2 shrink-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-red-600 dark:text-red-400 truncate">
              ⚠️ {error}
            </span>
            <Button variant="outline" size="sm" onClick={retry} disabled={isStreaming}>
              重试
            </Button>
          </div>
        </div>
      )}

      {/* 输入区 */}
      <div className="border-t border-border p-3 shrink-0">
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={
              mode === 'evolve'
                ? '输入消息(自进化飞轮)... (Enter 发送)'
                : '输入消息... (Enter 发送, Shift+Enter 换行)'
            }
            className="flex-1"
            disabled={isStreaming}
          />
          <Button onClick={handleSend} disabled={isStreaming || !input.trim()}>
            {isStreaming ? '处理中...' : '发送'}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** 模式切换器 */
function ModeSwitcher({
  mode,
  onChange,
  disabled,
}: {
  mode: ChatMode;
  onChange: (m: ChatMode) => void;
  disabled: boolean;
}) {
  return (
    <div className="inline-flex rounded-md border border-border bg-muted/40 p-0.5 text-xs">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange('stream')}
        className={`px-2 py-1 rounded-sm transition-colors ${
          mode === 'stream'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:text-foreground'
        }`}
      >
        流式
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange('evolve')}
        className={`px-2 py-1 rounded-sm transition-colors ${
          mode === 'evolve'
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:text-foreground'
        }`}
      >
        自进化
      </button>
    </div>
  );
}

/** 消息气泡 */
function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';
  const isTool = message.role === 'tool';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[88%] rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : isTool
              ? 'bg-muted text-muted-foreground border border-border'
              : 'bg-secondary text-secondary-foreground border border-border'
        }`}
      >
        {/* 工具调用可视化(可展开/折叠) */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCallsPanel toolCalls={message.toolCalls} />
        )}

        {/* 概念路径(evolve 模式) */}
        {message.conceptPath && message.conceptPath.length > 0 && (
          <ConceptPathPanel path={message.conceptPath} />
        )}

        {/* 消息正文 */}
        {message.content && (
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        )}

        {/* 错误提示 */}
        {message.error && (
          <p className="mt-1 text-xs text-red-500">⚠️ {message.error}</p>
        )}

        {/* 元信息 */}
        <div className="mt-1 flex items-center gap-2 text-[10px] opacity-60">
          {message.streaming && <span className="animate-pulse">输出中...</span>}
          {message.durationMs != null && message.durationMs > 0 && (
            <span>{message.durationMs} ms</span>
          )}
          <span>{new Date(message.ts).toLocaleTimeString()}</span>
        </div>
      </div>
    </div>
  );
}

/** 工具调用可视化(可展开/折叠) */
function ToolCallsPanel({ toolCalls }: { toolCalls: ToolCallRecord[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="mb-2 border border-border/60 rounded-md bg-muted/50 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-2 py-1 text-xs hover:bg-muted"
      >
        <span className="font-medium">🔧 工具调用 ({toolCalls.length})</span>
        <span className="text-muted-foreground">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <ul className="px-2 pb-2 space-y-1 text-xs">
          {toolCalls.map((tc, i) => (
            <li key={i} className="border-l-2 border-primary/40 pl-2">
              <div className="flex items-center gap-1">
                <span className="font-mono">{tc.name}</span>
                {tc.success === true && (
                  <span className="text-green-500">✓</span>
                )}
                {tc.success === false && <span className="text-red-500">✗</span>}
              </div>
              {tc.args && (
                <pre className="mt-0.5 text-[10px] text-muted-foreground overflow-auto max-h-24">
                  {JSON.stringify(tc.args, null, 2)}
                </pre>
              )}
              {tc.result != null && (
                <pre className="mt-0.5 text-[10px] text-muted-foreground overflow-auto max-h-24">
                  {typeof tc.result === 'string'
                    ? tc.result
                    : JSON.stringify(tc.result, null, 2)}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** 概念路径展示(evolve 模式) */
function ConceptPathPanel({ path }: { path: string[] }) {
  const [expanded, setExpanded] = useState(false);
  if (path.length === 0) return null;
  return (
    <div className="mb-2 border border-primary/30 rounded-md bg-primary/5 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-2 py-1 text-xs hover:bg-primary/10"
      >
        <span className="font-medium">🧠 概念路径 ({path.length})</span>
        <span className="text-muted-foreground">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <ol className="px-2 pb-2 space-y-0.5 text-xs list-decimal list-inside">
          {path.map((p, i) => (
            <li key={i} className="text-muted-foreground">
              {p}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** 拓扑统计面板 */
function TopologyPanel({
  stats,
  loading,
  error,
  onRefresh,
}: {
  stats: ReturnType<typeof useTopologyStats>['stats'];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  return (
    <div className="border-b border-border bg-muted/30 px-3 py-2 shrink-0">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium">知识拓扑图统计</span>
        <Button variant="ghost" size="sm" onClick={onRefresh} disabled={loading}>
          {loading ? '加载中...' : '刷新'}
        </Button>
      </div>
      {error && <p className="text-xs text-red-500">⚠️ {error}</p>}
      {!stats && !loading && !error && (
        <p className="text-xs text-muted-foreground">点击刷新加载</p>
      )}
      {stats && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <StatItem
            label="节点数"
            value={String(stats.topology?.node_count ?? '-')}
          />
          <StatItem
            label="边数"
            value={String(stats.topology?.edge_count ?? '-')}
          />
          <StatItem
            label="层数"
            value={String(stats.topology?.layer_count ?? '-')}
          />
          <StatItem
            label="冷启动"
            value={stats.is_cold_start ? '是' : '否'}
          />
        </div>
      )}
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between bg-background/60 rounded px-2 py-1">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono font-medium">{value}</span>
    </div>
  );
}
