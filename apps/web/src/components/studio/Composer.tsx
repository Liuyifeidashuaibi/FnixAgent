/**
 * fnixagent Studio — Composer 对话面板
 *
 * 对标 Cursor Composer + Codex CLI:
 *   ① 消息流(用户右对齐气泡 / AI 左对齐无气泡 / 流式光标)
 *   ② 工具调用可折叠卡片
 *   ③ Agent 状态徽标
 *   ④ Markdown 渲染(标题/粗体/斜体/代码块/列表/链接)
 *   ⑤ Slash 命令(/new /undo /diff /reset /index /search /test /help /clear)
 *   ⑥ @-mention 上下文菜单(File/Folder/Codebase/Docs/Web/Terminal)
 *   ⑦ 上下文 chip 区
 *   ⑧ Enter 发送 / Shift+Enter 换行 / 流式时 Stop 按钮
 *   ⑨ 新对话按钮 + 错误重试 + 自动滚动
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import { Badge, Button } from '@fnixagent/ui';
import { sdk } from '@fnixagent/sdk';
import { useStudio } from '../../stores/studio-store';
import { genId, type AgentStatus, type ChatMessage, type ContextChipType } from '../../stores/types';
import {
  ChevronIcon,
  PaperclipIcon,
  PlusIcon,
  SendIcon,
  StopIcon,
} from './icons';

// ---- 常量 ----

const SLASH_COMMANDS: { cmd: string; desc: string }[] = [
  { cmd: '/new', desc: '开始新对话' },
  { cmd: '/undo', desc: '撤销上一步变更' },
  { cmd: '/diff', desc: '查看代码差异' },
  { cmd: '/reset', desc: '重置工作区' },
  { cmd: '/index', desc: '索引代码库' },
  { cmd: '/search', desc: '搜索代码' },
  { cmd: '/test', desc: '运行测试' },
  { cmd: '/help', desc: '显示帮助' },
  { cmd: '/clear', desc: '清空对话' },
];

const MENTION_OPTIONS: { type: ContextChipType; label: string }[] = [
  { type: 'file', label: 'File' },
  { type: 'folder', label: 'Folder' },
  { type: 'codebase', label: 'Codebase' },
  { type: 'docs', label: 'Docs' },
  { type: 'web', label: 'Web' },
  { type: 'terminal', label: 'Terminal' },
];

const AGENT_STATUS_CONFIG: Record<
  AgentStatus,
  { label: string; variant: 'secondary' | 'warning' | 'success' | 'destructive' }
> = {
  idle: { label: '空闲', variant: 'secondary' },
  planning: { label: '规划中', variant: 'warning' },
  executing: { label: '执行中', variant: 'success' },
  reviewing: { label: '审查中', variant: 'secondary' },
  awaiting_user: { label: '等待确认', variant: 'warning' },
  error: { label: '错误', variant: 'destructive' },
};

// ============================================================
// Composer 主组件
// ============================================================

export function Composer() {
  const { state, dispatch } = useStudio();
  const { messages, isStreaming, agentStatus, contextChips, composerMode } = state;
  const [input, setInput] = useState('');
  const [showSlash, setShowSlash] = useState(false);
  const [slashIndex, setSlashIndex] = useState(0);
  const [showMention, setShowMention] = useState(false);
  const [mentionIndex, setMentionIndex] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 过滤后的 slash 命令
  const filteredCommands = useMemo(() => {
    const query = input.match(/\/(\w*)$/)?.[1] ?? '';
    if (!input.endsWith('/') && !query) return SLASH_COMMANDS;
    return SLASH_COMMANDS.filter((c) =>
      c.cmd.startsWith(input.match(/\/\w*$/)?.[0] ?? '/'),
    );
  }, [input]);

  // 自动滚动到底部
  useLayoutEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // textarea 自动增高
  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [input, resizeTextarea]);

  // ---- 发送消息 ----
  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      // 插入用户消息
      dispatch({
        type: 'ADD_MESSAGE',
        message: { id: genId(), role: 'user', content: trimmed, ts: Date.now() },
      });
      dispatch({ type: 'SET_STREAMING', streaming: true });
      dispatch({ type: 'SET_AGENT_STATUS', status: 'executing' });

      const assistantId = genId();
      dispatch({
        type: 'ADD_MESSAGE',
        message: {
          id: assistantId,
          role: 'assistant',
          content: '',
          streaming: true,
          ts: Date.now(),
          agentStatus: 'executing',
        },
      });

      let buffer = '';
      const toolCalls: ChatMessage['toolCalls'] = [];
      try {
        for await (const chunk of sdk.chat.stream({ user_input: trimmed })) {
          switch (chunk.chunk_type) {
            case 'thought':
              buffer += `> 💭 ${chunk.content}\n\n`;
              break;
            case 'action':
              toolCalls.push({ name: chunk.content });
              buffer += `🔧 *调用工具: ${chunk.content}*\n\n`;
              break;
            case 'text':
              buffer += chunk.content;
              break;
            case 'error':
              buffer += `\n\n⚠️ 错误: ${chunk.content}`;
              break;
          }
          dispatch({
            type: 'UPDATE_MESSAGE',
            id: assistantId,
            patch: {
              content: buffer,
              streaming: !chunk.done,
              toolCalls: toolCalls.length ? toolCalls : undefined,
              ts: Date.now(),
            },
          });
        }
        dispatch({
          type: 'UPDATE_MESSAGE',
          id: assistantId,
          patch: {
            content: buffer || '(无内容)',
            streaming: false,
            toolCalls: toolCalls.length ? toolCalls : undefined,
            agentStatus: 'idle',
          },
        });
        dispatch({ type: 'SET_AGENT_STATUS', status: 'idle' });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        dispatch({
          type: 'UPDATE_MESSAGE',
          id: assistantId,
          patch: { content: buffer, streaming: false, error: msg, agentStatus: 'error' },
        });
        dispatch({ type: 'SET_AGENT_STATUS', status: 'error' });
      } finally {
        dispatch({ type: 'SET_STREAMING', streaming: false });
      }
    },
    [dispatch, isStreaming],
  );

  // ---- 处理 slash 命令 ----
  const executeCommand = useCallback(
    (cmd: string) => {
      setShowSlash(false);
      setInput('');
      switch (cmd) {
        case '/new':
        case '/clear':
          dispatch({ type: 'CLEAR_MESSAGES' });
          break;
        case '/diff':
          dispatch({ type: 'SET_RIGHT_PANEL', view: 'diff' });
          break;
        case '/help':
          dispatch({
            type: 'ADD_MESSAGE',
            message: {
              id: genId(),
              role: 'assistant',
              content:
                '## 可用命令\n\n' +
                SLASH_COMMANDS.map((c) => `- \`${c.cmd}\` — ${c.desc}`).join('\n'),
              ts: Date.now(),
            },
          });
          break;
        default:
          // 其他命令作为消息发送
          void send(cmd);
      }
    },
    [dispatch, send],
  );

  // ---- 处理 @-mention ----
  const addContextChip = useCallback(
    (type: ContextChipType) => {
      setShowMention(false);
      setInput((prev) => prev.replace(/@$/, ''));
      dispatch({
        type: 'ADD_CONTEXT_CHIP',
        chip: {
          id: genId(),
          type,
          value: type,
          label: `${type.charAt(0).toUpperCase() + type.slice(1)}`,
        },
      });
    },
    [dispatch],
  );

  // ---- 键盘处理 ----
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Slash 命令导航
      if (showSlash) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setSlashIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setSlashIndex((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === 'Enter') {
          e.preventDefault();
          const cmd = filteredCommands[slashIndex];
          if (cmd) executeCommand(cmd.cmd);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowSlash(false);
          return;
        }
      }
      // @-mention 导航
      if (showMention) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          setMentionIndex((i) => Math.min(i + 1, MENTION_OPTIONS.length - 1));
          return;
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault();
          setMentionIndex((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === 'Enter') {
          e.preventDefault();
          const opt = MENTION_OPTIONS[mentionIndex];
          if (opt) addContextChip(opt.type);
          return;
        }
        if (e.key === 'Escape') {
          e.preventDefault();
          setShowMention(false);
          return;
        }
      }
      // Enter 发送 / Shift+Enter 换行
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void send(input);
        setInput('');
      }
    },
    [showSlash, showMention, filteredCommands, slashIndex, mentionIndex, executeCommand, addContextChip, send, input],
  );

  // ---- 输入变化检测 slash / mention ----
  const handleInput = useCallback(
    (value: string) => {
      setInput(value);
      // 检测 / 命令(仅在行首或空格后)
      const slashMatch = value.match(/(?:^|\s)(\/\w*)$/);
      setShowSlash(!!slashMatch);
      if (slashMatch) setSlashIndex(0);
      // 检测 @ mention(仅在行首或空格后)
      const mentionMatch = value.match(/(?:^|\s)(@)$/);
      setShowMention(!!mentionMatch);
      if (mentionMatch) setMentionIndex(0);
    },
    [],
  );

  // ---- 停止流式 ----
  const handleStop = useCallback(() => {
    // SDK 流式无法中断,仅更新 UI 状态
    dispatch({ type: 'SET_STREAMING', streaming: false });
    dispatch({ type: 'SET_AGENT_STATUS', status: 'idle' });
  }, [dispatch]);

  // ---- 重试最后一条 ----
  const handleRetry = useCallback(
    (msg: ChatMessage) => {
      // 找到对应的用户消息
      const idx = messages.findIndex((m) => m.id === msg.id);
      if (idx <= 0) return;
      const userMsg = [...messages.slice(0, idx)].reverse().find((m) => m.role === 'user');
      if (userMsg) {
        // 移除失败消息
        dispatch({ type: 'UPDATE_MESSAGE', id: msg.id, patch: { error: undefined } });
        void send(userMsg.content);
      }
    },
    [messages, dispatch, send],
  );

  return (
    <div className="flex h-full flex-col bg-background">
      {/* 顶部:状态徽标 + 新对话 */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2 shrink-0">
        <Badge variant={AGENT_STATUS_CONFIG[agentStatus].variant}>
          {AGENT_STATUS_CONFIG[agentStatus].label}
        </Badge>
        <div className="flex items-center gap-1">
          <span className="text-xs text-muted-foreground capitalize">
            {composerMode}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => dispatch({ type: 'CLEAR_MESSAGES' })}
            disabled={isStreaming}
            title="新对话"
          >
            <PlusIcon width={16} height={16} />
          </Button>
        </div>
      </div>

      {/* 消息流 */}
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-auto p-4">
        {messages.map((msg) => (
          <MessageItem
            key={msg.id}
            message={msg}
            onRetry={() => handleRetry(msg)}
          />
        ))}
        {isStreaming && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary [animation-delay:200ms]" />
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary [animation-delay:400ms]" />
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div className="border-t border-border p-3 shrink-0">
        {/* 上下文 chip 区 */}
        {contextChips.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1">
            {contextChips.map((chip) => (
              <span
                key={chip.id}
                className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
              >
                <span className="text-primary">@</span>
                {chip.label}
                <button
                  type="button"
                  className="ml-0.5 text-muted-foreground hover:text-foreground"
                  onClick={() => dispatch({ type: 'REMOVE_CONTEXT_CHIP', id: chip.id })}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        {/* 输入框容器(相对定位,用于 slash/mention 浮层) */}
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => handleInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息... (Enter 发送, Shift+Enter 换行, / 命令, @ 上下文)"
            disabled={isStreaming}
            rows={1}
            className="w-full resize-none rounded-lg border border-border bg-background px-3 py-2.5 pr-12 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            style={{ minHeight: '40px', maxHeight: '160px' }}
          />

          {/* Slash 命令浮层 */}
          {showSlash && filteredCommands.length > 0 && (
            <div className="absolute bottom-full left-0 mb-1 w-64 rounded-lg border border-border bg-popover p-1 shadow-md animate-fade-in">
              {filteredCommands.map((c, i) => (
                <button
                  key={c.cmd}
                  type="button"
                  className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                    i === slashIndex ? 'bg-accent' : ''
                  }`}
                  onMouseEnter={() => setSlashIndex(i)}
                  onClick={() => executeCommand(c.cmd)}
                >
                  <span className="font-mono text-primary">{c.cmd}</span>
                  <span className="text-muted-foreground">{c.desc}</span>
                </button>
              ))}
            </div>
          )}

          {/* @-mention 浮层 */}
          {showMention && (
            <div className="absolute bottom-full left-0 mb-1 w-48 rounded-lg border border-border bg-popover p-1 shadow-md animate-fade-in">
              {MENTION_OPTIONS.map((opt, i) => (
                <button
                  key={opt.type}
                  type="button"
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors ${
                    i === mentionIndex ? 'bg-accent' : ''
                  }`}
                  onMouseEnter={() => setMentionIndex(i)}
                  onClick={() => addContextChip(opt.type)}
                >
                  <span className="text-primary">@</span>
                  <span>{opt.label}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 底部操作栏 */}
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="h-7 w-7" title="附件">
              <PaperclipIcon width={16} height={16} />
            </Button>
            <span className="text-xs text-muted-foreground">GPT-4</span>
          </div>
          {isStreaming ? (
            <Button
              variant="destructive"
              size="sm"
              className="h-7 gap-1 text-xs"
              onClick={handleStop}
            >
              <StopIcon width={14} height={14} />
              Stop
            </Button>
          ) : (
            <Button
              size="sm"
              className="h-7 w-7 p-0"
              onClick={() => {
                void send(input);
                setInput('');
              }}
              disabled={!input.trim()}
            >
              <SendIcon width={14} height={14} />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 消息项
// ============================================================

function MessageItem({
  message,
  onRetry,
}: {
  message: ChatMessage;
  onRetry: () => void;
}) {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-xl bg-primary/10 px-3.5 py-2 text-sm text-foreground">
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        </div>
      </div>
    );
  }

  // assistant 消息
  return (
    <div className="flex flex-col gap-1">
      {/* 工具调用 */}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <ToolCallsPanel toolCalls={message.toolCalls} />
      )}
      {/* 概念路径 */}
      {message.conceptPath && message.conceptPath.length > 0 && (
        <ConceptPathPanel path={message.conceptPath} />
      )}
      {/* 正文 */}
      {message.content && (
        <div className={message.streaming ? 'stream-cursor' : ''}>
          <MarkdownContent content={message.content} />
        </div>
      )}
      {/* 错误 */}
      {message.error && (
        <div className="flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-1.5">
          <span className="text-xs text-destructive">⚠️ {message.error}</span>
          <Button variant="outline" size="sm" className="h-6 text-xs" onClick={onRetry}>
            重试
          </Button>
        </div>
      )}
      {/* 元信息 */}
      <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
        {message.durationMs != null && message.durationMs > 0 && (
          <span>{message.durationMs} ms</span>
        )}
        <span>{new Date(message.ts).toLocaleTimeString()}</span>
      </div>
    </div>
  );
}

/** 工具调用可折叠卡片 */
function ToolCallsPanel({ toolCalls }: { toolCalls: NonNullable<ChatMessage['toolCalls']> }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="overflow-hidden rounded-md border border-border bg-muted/40">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-xs hover:bg-muted/60 transition-colors"
      >
        <span
          className="transition-transform"
          style={{ transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)' }}
        >
          <ChevronIcon width={12} height={12} />
        </span>
        <span className="font-medium">🔧 工具调用 ({toolCalls.length})</span>
      </button>
      {expanded && (
        <ul className="space-y-1 px-2.5 pb-2 text-xs">
          {toolCalls.map((tc, i) => (
            <li key={i} className="border-l-2 border-primary/40 pl-2">
              <div className="flex items-center gap-1">
                <span className="font-mono">{tc.name}</span>
                {tc.success === true && <span className="text-[hsl(var(--success))]">✓</span>}
                {tc.success === false && <span className="text-destructive">✗</span>}
                {tc.durationMs != null && (
                  <span className="text-[10px] text-muted-foreground">{tc.durationMs}ms</span>
                )}
              </div>
              {tc.args && (
                <pre className="mt-0.5 max-h-24 overflow-auto rounded bg-background p-1 text-[10px] text-muted-foreground">
                  {JSON.stringify(tc.args, null, 2)}
                </pre>
              )}
              {tc.result != null && (
                <pre className="mt-0.5 max-h-24 overflow-auto rounded bg-background p-1 text-[10px] text-muted-foreground">
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

/** 概念路径(evolve 模式) */
function ConceptPathPanel({ path }: { path: string[] }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="overflow-hidden rounded-md border border-primary/30 bg-primary/5">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-xs hover:bg-primary/10 transition-colors"
      >
        <span
          className="transition-transform"
          style={{ transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)' }}
        >
          <ChevronIcon width={12} height={12} />
        </span>
        <span className="font-medium">🧠 概念路径 ({path.length})</span>
      </button>
      {expanded && (
        <ol className="list-inside list-decimal space-y-0.5 px-2.5 pb-2 text-xs text-muted-foreground">
          {path.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ============================================================
// 简易 Markdown 渲染(不引入 react-markdown)
// ============================================================

/** Markdown 内容渲染 — 分割代码块与普通文本 */
function MarkdownContent({ content }: { content: string }) {
  const segments = useMemo(() => splitCodeBlocks(content), [content]);
  return (
    <div className="text-sm leading-relaxed text-foreground">
      {segments.map((seg, i) =>
        seg.type === 'code' ? (
          <CodeBlock key={i} lang={seg.lang} code={seg.content} />
        ) : (
          <InlineMarkdown key={i} text={seg.content} />
        ),
      )}
    </div>
  );
}

type Segment =
  | { type: 'text'; content: string }
  | { type: 'code'; lang: string; content: string };

/** 将内容按 ``` 代码块分割 */
function splitCodeBlocks(text: string): Segment[] {
  const segments: Segment[] = [];
  const regex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIdx) {
      segments.push({ type: 'text', content: text.slice(lastIdx, match.index) });
    }
    segments.push({
      type: 'code',
      lang: match[1] || 'plaintext',
      content: match[2].replace(/\n$/, ''),
    });
    lastIdx = regex.lastIndex;
  }
  if (lastIdx < text.length) {
    segments.push({ type: 'text', content: text.slice(lastIdx) });
  }
  return segments;
}

/** 代码块 — 语言标签 + 复制按钮 */
function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    void navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [code]);

  return (
    <div className="my-2 overflow-hidden rounded-md border border-[hsl(var(--code-border))] bg-[hsl(var(--code-bg))]">
      <div className="flex items-center justify-between border-b border-[hsl(var(--code-border))] px-3 py-1">
        <span className="text-[10px] font-medium uppercase text-muted-foreground">
          {lang}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="text-[10px] text-muted-foreground transition-colors hover:text-foreground"
        >
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="overflow-auto p-3 text-xs">
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}

/** 行内 Markdown — 转义后用正则替换,再用 dangerouslySetInnerHTML 渲染 */
function InlineMarkdown({ text }: { text: string }) {
  const html = useMemo(() => renderInlineMarkdown(text), [text]);
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

/** 行内 Markdown → HTML(先转义,再替换语法) */
function renderInlineMarkdown(text: string): string {
  // 1. 转义 HTML
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // 2. 标题
  html = html.replace(/^### (.+)$/gm, '<h3 class="text-base font-semibold mt-3 mb-1">$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2 class="text-lg font-semibold mt-3 mb-1">$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1 class="text-xl font-bold mt-3 mb-1">$1</h1>');

  // 3. 粗体 / 斜体 / 行内代码
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`([^`]+)`/g, '<code class="rounded bg-muted px-1 py-0.5 font-mono text-xs">$1</code>');

  // 4. 链接
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-primary underline">$1</a>',
  );

  // 5. 无序列表
  html = html.replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>');
  // 连续 <li> 包裹 <ul>
  html = html.replace(/(<li[^>]*>.*<\/li>\n?)+/g, (m) => `<ul class="my-1 space-y-0.5">${m}</ul>`);

  // 6. 引用块
  html = html.replace(/^&gt; (.+)$/gm, '<blockquote class="border-l-2 border-primary/40 pl-3 text-muted-foreground italic">$1</blockquote>');

  // 7. 段落分隔(双换行)
  html = html.replace(/\n\n/g, '</p><p class="my-1">');
  html = `<p class="my-1">${html}</p>`;

  // 8. 单换行 → <br>
  html = html.replace(/\n/g, '<br />');

  return html;
}
