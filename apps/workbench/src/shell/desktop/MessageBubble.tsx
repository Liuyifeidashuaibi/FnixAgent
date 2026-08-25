/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Memoized message bubble — windowed content + idle-deferred highlight.
 */

import { memo, useEffect, useMemo, useState, type ReactNode } from 'react';
import { Check, ChevronDown, ChevronRight, Copy, RefreshCw, ThumbsDown, ThumbsUp } from 'lucide-react';
import hljs from 'highlight.js/lib/core';
import javascript from 'highlight.js/lib/languages/javascript';
import typescript from 'highlight.js/lib/languages/typescript';
import python from 'highlight.js/lib/languages/python';
import json from 'highlight.js/lib/languages/json';
import bash from 'highlight.js/lib/languages/bash';
import type { ChatMsg } from './useChatFlow';
import type { ChatAttachment } from '../../utils/tauri';
import type { CodeFileChange } from './fnixRuntime';
import { RunCapsule } from './RunCapsule';
import { softTruncate } from './windowing';
import type { StructuredBlock } from '../../utils/structuredBlocks';
import ThinkingBlock from '../../components/chat/ThinkingBlock';
import ProgressStrip from '../../components/chat/ProgressStrip';
import ToolCallCard from '../../components/chat/ToolCallCard';
import ToolResultCard from '../../components/chat/ToolResultCard';
import DiffBlock from '../../components/chat/DiffBlock';
import { WidgetBlock } from '../../components/chat/WidgetBlock';
import ErrorBlock from '../../components/chat/ErrorBlock';
import { MarkdownRenderer } from './MarkdownRenderer';
import { MermaidBlock } from './MermaidBlock';

hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('js', javascript);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('ts', typescript);
hljs.registerLanguage('python', python);
hljs.registerLanguage('py', python);
hljs.registerLanguage('json', json);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('shell', bash);

function escapeHtml(body: string): string {
  return body.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function highlightCode(lang: string, body: string): string {
  try {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(body, { language: lang }).value;
    }
    return hljs.highlightAuto(body).value;
  } catch {
    return escapeHtml(body);
  }
}

/**
 * Render a prose (non-code-fence) block: headings, blockquotes, ordered /
 * unordered lists, horizontal rules, and paragraphs — with inline markdown.
 *
 * NOTE: This custom regex-based parser is kept as a fallback but is no longer
 * used in the default render path. MarkdownRenderer (react-markdown + remark-gfm)
 * is used instead for full GFM support including tables, task lists, strikethrough.
 */

function CodeBlock({ lang, body, defer }: { lang: string; body: string; defer: boolean }) {
  const [html, setHtml] = useState(() => (defer ? escapeHtml(body) : highlightCode(lang, body)));

  useEffect(() => {
    if (!defer) {
      setHtml(highlightCode(lang, body));
      return;
    }
    let cancelled = false;
    const run = () => {
      if (cancelled) return;
      setHtml(highlightCode(lang, body));
    };
    const ric = (
      window as Window & {
        requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
        cancelIdleCallback?: (id: number) => void;
      }
    ).requestIdleCallback;
    if (typeof ric === 'function') {
      const id = ric(run, { timeout: 800 });
      return () => {
        cancelled = true;
        (window as Window & { cancelIdleCallback?: (id: number) => void }).cancelIdleCallback?.(id);
      };
    }
    const t = window.setTimeout(run, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [lang, body, defer]);

  return (
    <div className="fnix-code">
      <div className="fnix-code-h">
        <span>{lang || 'code'}</span>
        <CopyCodeButton code={body} />
      </div>
      <pre>
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}

function CopyCodeButton({ code }: { code: string }) {
  const [ok, setOk] = useState(false);
  return (
    <button
      type="button"
      className="fnix-code-copy"
      onClick={() => {
        void navigator.clipboard.writeText(code).then(() => {
          setOk(true);
          window.setTimeout(() => setOk(false), 1400);
        });
      }}
    >
      {ok ? <Check size={12} /> : <Copy size={12} />}
      {ok ? 'Copied' : 'Copy'}
    </button>
  );
}

function renderContent(text: string, deferHighlight: boolean) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (part.startsWith('```')) {
      const lang = part.match(/^```(\w*)/)?.[1] || '';
      const body = part.replace(/^```\w*\n?/, '').replace(/```$/, '');
      const closed = part.endsWith('```');
      // Mermaid 分流：渲染为图表而非代码块
      if (lang.toLowerCase() === 'mermaid' && closed) {
        return <MermaidBlock key={i} code={body.replace(/\n$/, '')} />;
      }
      return <CodeBlock key={i} lang={lang} body={body} defer={deferHighlight && closed} />;
    }
    return <MarkdownRenderer key={i} content={part} />;
  });
}

/**
 * 渲染结构化 block 数组（AG-UI 协议对齐）。
 * 当消息存在 blocks 字段时，按 block 顺序渲染对应组件：
 * thinking → ThinkingBlock（可折叠思考过程）
 * progress → ProgressStrip（步骤进度条）
 * tool_call → ToolCallCard（工具调用卡片）
 * tool_result → ToolResultCard（工具结果，head-and-tail 折叠）
 * diff → DiffBlock（三态 diff 审查：pending/accepted/rejected）
 * error → ErrorBlock（严重级别错误恢复：transient/persistent/fatal）
 * text → renderContent（纯文本，支持 markdown + 代码块）
 *
 * 调研：AG-UI 16 种标准事件类型 + 逐块渲染
 */
function renderBlocks(
  blocks: StructuredBlock[],
  live: boolean,
  deferHighlight: boolean,
  onPin?: (path: string) => void,
  onSendPrompt?: (text: string) => void,
  onRetry?: () => void,
): ReactNode {
  // UX P0-3: 连续同名 tool_call ≥3 → 折叠为单行「read_file ×5」，点击展开逐条
  type Segment =
    | { kind: 'single'; block: StructuredBlock; idx: number }
    | {
        kind: 'group';
        blocks: { block: StructuredBlock; idx: number }[];
        name: string;
        totalMs: number;
      };
  const segments: Segment[] = [];
  let i = 0;
  while (i < blocks.length) {
    const b = blocks[i];
    if (b?.kind === 'tool_call') {
      let j = i;
      const group: { block: StructuredBlock; idx: number }[] = [];
      while (j < blocks.length) {
        const nb = blocks[j];
        if (
          nb?.kind === 'tool_call' &&
          (nb as { name?: string }).name === (b as { name?: string }).name
        ) {
          group.push({ block: nb, idx: j });
          j++;
        } else break;
      }
      if (group.length >= 3) {
        const totalMs = group.reduce((acc, g) => {
          const d = (g.block as { durationMs?: number }).durationMs;
          return acc + (typeof d === 'number' ? d : 0);
        }, 0);
        segments.push({ kind: 'group', blocks: group, name: (b as { name?: string }).name || 'tool', totalMs });
        i = j;
        continue;
      }
      for (const g of group) segments.push({ kind: 'single', block: g.block, idx: g.idx });
      i = j;
      continue;
    }
    segments.push({ kind: 'single', block: b!, idx: i });
    i++;
  }

  return (
    <>
      {segments.map((seg) => {
        if (seg.kind === 'group')
          return <ToolCallGroup key={`tgroup-${seg.blocks[0]?.idx ?? 0}`} seg={seg} />;
        return renderSingleBlock(
          seg.block,
          seg.idx,
          live,
          deferHighlight,
          blocks,
          onPin,
          onSendPrompt,
          onRetry,
        );
      })}
    </>
  );
}

/** UX P0-3: 同名工具折叠组 —「read_file ×5 (2.1s)」单行，点击展开逐条卡片 */
function ToolCallGroup({
  seg,
}: {
  seg: {
    blocks: { block: StructuredBlock; idx: number }[];
    name: string;
    totalMs: number;
  };
}) {
  const [open, setOpen] = useState(false);
  const n = seg.blocks.length;
  const durText =
    seg.totalMs > 0
      ? seg.totalMs < 1000
        ? `${Math.round(seg.totalMs)}ms`
        : `${(seg.totalMs / 1000).toFixed(1).replace(/\.0$/, '')}s`
      : '';
  return (
    <div className="cl-tool-group" data-open={open || undefined}>
      <button
        type="button"
        className="cl-tool-group-row"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="cl-tool-call-icon">{TOOL_GROUP_ICONS[seg.name] || TOOL_GROUP_ICONS.default}</span>
        <span className="cl-tool-group-name">{seg.name}</span>
        <span className="cl-tool-group-count">×{n}</span>
        {durText && <span className="cl-tool-call-duration">{durText}</span>}
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
      </button>
      {open && (
        <div className="cl-tool-group-items">
          {seg.blocks.map(({ block, idx }) => (
            <ToolCallCard
              key={`tg-${idx}`}
              name={block.kind === 'tool_call' ? block.name : 'tool'}
              params={block.kind === 'tool_call' ? block.params : undefined}
              isComplete={(block as { isComplete?: boolean }).isComplete !== false}
            />
          ))}
        </div>
      )}
    </div>
  );
}

const TOOL_GROUP_ICONS: Record<string, string> = {
  read_file: "📖",
  write_file: "✏️",
  execute_command: "▶️",
  search_code: "🔍",
  default: "🔧",
};

function renderSingleBlock(
  block: StructuredBlock,
  i: number,
  live: boolean,
  deferHighlight: boolean,
  blocks: StructuredBlock[],
  onPin?: (path: string) => void,
  onSendPrompt?: (text: string) => void,
  onRetry?: () => void,
): ReactNode {
  switch (block.kind) {
    case 'thinking':
      return (
        <ThinkingBlock
          key={`think-${i}`}
          content={block.content}
          isStreaming={live && block.isStreaming !== false}
        />
      );
    case 'progress':
      return (
        <ProgressStrip
          key={`prog-${i}`}
          currentStep={block.currentStep}
          totalSteps={block.totalSteps}
          description={block.description}
          isComplete={block.isComplete}
        />
      );
    case 'tool_call': {
      // 从紧随其后的 tool_result 推断 isError：AG-UI 协议中 tool_call 和 tool_result
      // 通过顺序配对（同一次工具调用的 result 紧跟在 call 后）。若 result 验证失败，
      // 对应的 tool_call 卡片应显示错误状态（红色 ❌），而非恒为成功
      const next = blocks[i + 1];
      const isError = next?.kind === 'tool_result' && next.verificationStatus === 'failed';
      return (
        <ToolCallCard
          key={`tc-${i}`}
          name={block.name}
          params={block.params}
          isComplete={block.isComplete}
          isError={isError}
          durationMs={block.durationMs}
        />
      );
    }
    case 'tool_result':
      return (
        <ToolResultCard
          key={`tr-${i}`}
          content={block.content}
          verificationStatus={block.verificationStatus}
        />
      );
    case 'diff': {
      // DiffBlock 需要 entries 数组，单文件包装
      // 消息气泡内只读展示：Accept/Reject 必须在评审面板操作，
      // 否则用户误以为点 Accept 已写盘（实际未传 onAccept，不会调用后端）
      const entries = [
        {
          path: block.path,
          added: block.added,
          removed: block.removed,
          diff: block.diff,
        },
      ];
      return <DiffBlock key={`diff-${i}`} entries={entries} onPin={onPin} readOnly />;
    }
    case 'error':
      return (
        <ErrorBlock
          key={`err-${i}`}
          title={block.title}
          detail={block.detail}
          suggestion={block.suggestion}
          toolName={block.toolName}
          severity={block.severity}
          retryCount={block.retryCount}
          maxRetries={block.maxRetries}
          onRetry={onRetry}
        />
      );
    case 'text':
      return (
        <div key={`text-${i}`} className="fnix-asst-text">
          {renderContent(block.content, deferHighlight)}
        </div>
      );
    case 'widget':
      // AI 内联可视化（动态 UI 渲染）— iframe sandbox 渲染，
      // widget 内 sendPrompt 按钮经 postMessage 回灌为新用户消息
      return (
        <WidgetBlock
          key={`widget-${block.widgetId}`}
          block={block}
          live={live}
          onSendPrompt={onSendPrompt}
        />
      );
    default:
      return null;
  }
}

function AttachmentChip({ att }: { att: ChatAttachment }) {
  if (att.type === 'image') {
    const src = `data:${att.mimeType};base64,${att.base64}`;
    return (
      <a
        className="fnix-msg-att is-image"
        href={src}
        target="_blank"
        rel="noreferrer noopener"
        title={att.name}
      >
        <img src={src} alt={att.name} />
        <span className="fnix-msg-att-name">{att.name}</span>
      </a>
    );
  }
  return (
    <span className="fnix-msg-att is-file" title={att.name}>
      <span className="fnix-msg-att-ico" aria-hidden>
        📄
      </span>
      <span className="fnix-msg-att-name">{att.name}</span>
    </span>
  );
}

export type MessageBubbleProps = {
  message: ChatMsg;
  isLastAssistant: boolean;
  streaming: boolean;
  status?: string | null;
  fileChanges?: CodeFileChange[];
  onOpenDiff?: (path: string) => void;
  onRegenerate?: () => void;
  copiedId: string | null;
  onCopy: (id: string, text: string) => void;
  vote?: 'up' | 'down';
  onVote: (id: string, v: 'up' | 'down') => void;
  /** 钉选文件到 Canvas Dock（DiffBlock 用）*/
  onPin?: (path: string) => void;
  /** widget 内 sendPrompt 按钮 → 回灌为新用户消息（dynamic-ui）*/
  onSendPrompt?: (text: string) => void;
};

function MessageBubbleInner({
  message: m,
  isLastAssistant,
  streaming,
  status,
  fileChanges,
  onOpenDiff,
  onRegenerate,
  copiedId,
  onCopy,
  vote,
  onVote,
  onPin,
  onSendPrompt,
}: MessageBubbleProps) {
  const [expanded, setExpanded] = useState(false);
  const live = streaming && isLastAssistant;
  const soft = useMemo(
    () => (expanded || live ? { text: m.content, truncated: false } : softTruncate(m.content)),
    [m.content, expanded, live],
  );

  if (m.role === 'user') {
    return (
      <div className="fnix-turn fnix-turn-user">
        <div className="fnix-user-bubble">
          {m.attachments && m.attachments.length > 0 ? (
            <div className="fnix-msg-attachments">
              {m.attachments.map((a) => (
                <AttachmentChip key={a.id} att={a} />
              ))}
            </div>
          ) : null}
          {soft.text}
          {soft.truncated ? (
            <button type="button" className="fnix-expand-msg" onClick={() => setExpanded(true)}>
              Show more
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="fnix-turn fnix-turn-assistant">
      <div className="fnix-asst-mark" aria-hidden />
      <div className="fnix-asst-body">
        {/* 结构化 block 优先渲染（AG-UI 协议对齐）。
            当 blocks 存在时，按 block 顺序渲染 thinking/progress/tool_call/diff/error/text 组件，
            而非纯文本 content。blocks 追加 only（Event Sourcing），保留完整执行轨迹。
            调研：AG-UI 16 种标准事件类型 + 逐块渲染 + 事件溯源 */}
        {m.blocks && m.blocks.length > 0 ? (
          <>
            <div className="fnix-asst-blocks">
              {renderBlocks(
                m.blocks,
                live,
                !live,
                onPin,
                onSendPrompt,
                isLastAssistant ? onRegenerate : undefined,
              )}
            </div>
            {m.content && !m.blocks.some((block) => block.kind === 'text') ? (
              <div className="fnix-asst-text">
                {renderContent(soft.text, !live)}
                {live ? <span className="fnix-cursor" aria-hidden /> : null}
              </div>
            ) : null}
          </>
        ) : m.content ? (
          <>
            {renderContent(soft.text, !live)}
            {live ? <span className="fnix-cursor" aria-hidden /> : null}
            {soft.truncated ? (
              <button type="button" className="fnix-expand-msg" onClick={() => setExpanded(true)}>
                Show full message ({m.content.length.toLocaleString()} chars)
              </button>
            ) : null}
          </>
        ) : live ? (
          <div className="fnix-thinking">
            <span className="fnix-shimmer">{status?.trim() || 'Thinking'}</span>
            <span className="fnix-cursor" />
          </div>
        ) : null}

        {isLastAssistant && fileChanges && fileChanges.length > 0 ? (
          <div className="fnix-capsules">
            {fileChanges.map((ch) => {
              const add = (ch.diff || '')
                .split('\n')
                .filter((l) => l.startsWith('+') && !l.startsWith('+++')).length;
              const del = (ch.diff || '')
                .split('\n')
                .filter((l) => l.startsWith('-') && !l.startsWith('---')).length;
              const meta =
                add || del ? `+${add} −${del}` : ch.preview !== false ? 'preview' : undefined;
              return (
                <RunCapsule
                  key={ch.path}
                  kind="edit"
                  title={`${ch.action === 'create' ? 'Created' : 'Edited'} ${ch.path}`}
                  meta={meta}
                  detail={(ch.diff || ch.content || '').slice(0, 800) || undefined}
                  ok
                  onOpenDiff={onOpenDiff ? () => onOpenDiff(ch.path) : undefined}
                />
              );
            })}
          </div>
        ) : null}

        {m.content && !live ? (
          <div className="fnix-actions">
            {/* UX P0-1/P0-6: OpenCode 式 meta 行 — tokens · 耗时 · 时间戳，hover 才显时间 */}
            <span className="fnix-msg-meta">
              {m.usage && m.usage.total > 0 ? (
                <span className="fnix-msg-meta-usage">
                  ≈{m.usage.total >= 1000
                    ? `${(m.usage.total / 1000).toFixed(1).replace(/\.0$/, '')}k`
                    : m.usage.total}{' '}
                  tok
                  {m.usage.durationMs ? (
                    <>
                      {' · '}
                      {m.usage.durationMs < 60_000
                        ? `${Math.round(m.usage.durationMs / 1000)}s`
                        : `${Math.floor(m.usage.durationMs / 60_000)}m${Math.round((m.usage.durationMs % 60_000) / 1000)}s`}
                    </>
                  ) : null}
                </span>
              ) : null}
              {m.ts ? (
                <time
                  className="fnix-msg-meta-ts"
                  dateTime={new Date(m.ts).toISOString()}
                  title={new Date(m.ts).toLocaleString()}
                >
                  {new Date(m.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </time>
              ) : null}
            </span>
            <button
              type="button"
              className="fnix-ibtn sm"
              title="复制"
              onClick={() => onCopy(m.id, m.content)}
            >
              {copiedId === m.id ? <Check size={14} /> : <Copy size={14} />}
            </button>
            <button
              type="button"
              className={`fnix-ibtn sm${vote === 'up' ? ' on' : ''}`}
              title="有帮助"
              onClick={() => onVote(m.id, 'up')}
            >
              <ThumbsUp size={14} />
            </button>
            <button
              type="button"
              className={`fnix-ibtn sm${vote === 'down' ? ' on' : ''}`}
              title="没帮助"
              onClick={() => onVote(m.id, 'down')}
            >
              <ThumbsDown size={14} />
            </button>
            {isLastAssistant && onRegenerate ? (
              <button
                type="button"
                className="fnix-ibtn sm"
                title="重新生成"
                onClick={onRegenerate}
              >
                <RefreshCw size={14} />
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleInner, (a, b) => {
  return (
    a.message.id === b.message.id &&
    a.message.content === b.message.content &&
    a.message.blocks === b.message.blocks &&
    a.isLastAssistant === b.isLastAssistant &&
    a.streaming === b.streaming &&
    a.status === b.status &&
    a.copiedId === b.copiedId &&
    a.vote === b.vote &&
    a.fileChanges === b.fileChanges &&
    a.onOpenDiff === b.onOpenDiff &&
    a.onRegenerate === b.onRegenerate &&
    // 漏比较 onPin/onSendPrompt 会导致父级 useCallback 重建时 MessageBubble 不重渲染，
    // DiffBlock/WidgetBlock 收到旧回调（如 onPin 闭包了过期的 artifacts）
    a.onPin === b.onPin &&
    a.onSendPrompt === b.onSendPrompt
  );
});
