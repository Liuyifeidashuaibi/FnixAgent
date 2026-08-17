/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Memoized message bubble — windowed content + idle-deferred highlight.
 */

import { memo, useEffect, useMemo, useState, createElement, type ReactNode } from "react";
import { Check, Copy, RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react";
import hljs from "highlight.js/lib/core";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import python from "highlight.js/lib/languages/python";
import json from "highlight.js/lib/languages/json";
import bash from "highlight.js/lib/languages/bash";
import type { ChatMsg } from "./useChatFlow";
import type { ChatAttachment } from "../../utils/tauri";
import type { CodexFileChange } from "./fnixRuntime";
import { RunCapsule } from "./RunCapsule";
import { softTruncate } from "./windowing";
import type { StructuredBlock } from "../../utils/structuredBlocks";
import ThinkingBlock from "../../components/chat/ThinkingBlock";
import ProgressStrip from "../../components/chat/ProgressStrip";
import ToolCallCard from "../../components/chat/ToolCallCard";
import ToolResultCard from "../../components/chat/ToolResultCard";
import DiffBlock from "../../components/chat/DiffBlock";
import { WidgetBlock } from "../../components/chat/WidgetBlock";
import ErrorBlock from "../../components/chat/ErrorBlock";

hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("js", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("ts", typescript);
hljs.registerLanguage("python", python);
hljs.registerLanguage("py", python);
hljs.registerLanguage("json", json);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("shell", bash);

function escapeHtml(body: string): string {
  return body
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
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

function renderInline(text: string): ReactNode[] {
  // Order matters: links, inline code, bold, then italics.
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|\*[^*]+\*|_[^_]+_)/g;
  const parts = text.split(pattern);
  return parts.map((part, i) => {
    if (!part) return null;
    let m: RegExpMatchArray | null;
    if ((m = part.match(/^`([^`]+)`$/))) {
      return (
        <code key={i} className="oai-inline-code">
          {m[1]}
        </code>
      );
    }
    if ((m = part.match(/^\*\*([^*]+)\*\*$/))) {
      return <strong key={i}>{m[1]}</strong>;
    }
    if ((m = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/))) {
      const url = m[2];
      const safe =
        /^https?:\/\//i.test(url) || url.startsWith("#") || url.startsWith("/") || url.startsWith("mailto:");
      return (
        <a key={i} href={url} target={safe ? "_blank" : undefined} rel={safe ? "noreferrer noopener" : undefined}>
          {m[1]}
        </a>
      );
    }
    if ((m = part.match(/^\*([^*]+)\*$/))) {
      return <em key={i}>{m[1]}</em>;
    }
    if ((m = part.match(/^_([^_]+)_$/))) {
      return <em key={i}>{m[1]}</em>;
    }
    return <span key={i}>{part}</span>;
  });
}

/**
 * Render a prose (non-code-fence) block: headings, blockquotes, ordered /
 * unordered lists, horizontal rules, and paragraphs — with inline markdown.
 */
function Prose({ text }: { text: string }): ReactNode {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let para: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  let key = 0;
  const flushPara = () => {
    if (para.length === 0) return;
    const t = para.join("\n");
    blocks.push(
      <p key={`p${key++}`} className="oai-md-p">
        {renderInline(t)}
      </p>,
    );
    para = [];
  };
  const flushList = () => {
    if (!list) return;
    const items = list.items;
    blocks.push(
      list.ordered ? (
        <ol key={`ol${key++}`} className="oai-md-list oai-md-ol">
          {items.map((it, k) => (
            <li key={k}>{renderInline(it)}</li>
          ))}
        </ol>
      ) : (
        <ul key={`ul${key++}`} className="oai-md-list">
          {items.map((it, k) => (
            <li key={k}>{renderInline(it)}</li>
          ))}
        </ul>
      ),
    );
    list = null;
  };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) {
      flushPara();
      flushList();
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushPara();
      flushList();
      const lvl = h[1].length;
      blocks.push(
        createElement(`h${Math.min(lvl + 1, 6)}`, { key: `h${key++}`, className: "oai-md-h" }, renderInline(h[2])),
      );
      continue;
    }
    const q = line.match(/^>\s?(.*)$/);
    if (q) {
      flushPara();
      flushList();
      blocks.push(
        <blockquote key={`q${key++}`} className="oai-md-quote">
          {renderInline(q[1])}
        </blockquote>,
      );
      continue;
    }
    const o = line.match(/^\d+\.\s+(.*)$/);
    if (o) {
      if (!list || !list.ordered) {
        flushPara();
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(o[1]);
      continue;
    }
    const u = line.match(/^[-*•]\s+(.*)$/);
    if (u) {
      if (!list || list.ordered) {
        flushPara();
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(u[1]);
      continue;
    }
    const hr = line.match(/^(-{3,}|\*{3,}|_{3,})$/);
    if (hr) {
      flushPara();
      flushList();
      blocks.push(<hr key={`hr${key++}`} className="oai-md-hr" />);
      continue;
    }
    para.push(line);
  }
  flushPara();
  flushList();
  return blocks;
}

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
    const ric = (window as Window & {
      requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    }).requestIdleCallback;
    if (typeof ric === "function") {
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
    <div className="oai-code">
      <div className="oai-code-h">
        <span>{lang || "code"}</span>
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
      className="oai-code-copy"
      onClick={() => {
        void navigator.clipboard.writeText(code).then(() => {
          setOk(true);
          window.setTimeout(() => setOk(false), 1400);
        });
      }}
    >
      {ok ? <Check size={12} /> : <Copy size={12} />}
      {ok ? "Copied" : "Copy"}
    </button>
  );
}

function renderContent(text: string, deferHighlight: boolean) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (part.startsWith("```")) {
      const lang = part.match(/^```(\w*)/)?.[1] || "";
      const body = part.replace(/^```\w*\n?/, "").replace(/```$/, "");
      const closed = part.endsWith("```");
      return (
        <CodeBlock
          key={i}
          lang={lang}
          body={body}
          defer={deferHighlight && closed}
        />
      );
    }
    return <Prose key={i} text={part} />;
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
  return blocks.map((block, i) => {
    switch (block.kind) {
      case "thinking":
        return (
          <ThinkingBlock
            key={`think-${i}`}
            content={block.content}
            isStreaming={live && block.isStreaming !== false}
          />
        );
      case "progress":
        return (
          <ProgressStrip
            key={`prog-${i}`}
            currentStep={block.currentStep}
            totalSteps={block.totalSteps}
            description={block.description}
            isComplete={block.isComplete}
          />
        );
      case "tool_call": {
        // 从紧随其后的 tool_result 推断 isError：AG-UI 协议中 tool_call 和 tool_result
        // 通过顺序配对（同一次工具调用的 result 紧跟在 call 后）。若 result 验证失败，
        // 对应的 tool_call 卡片应显示错误状态（红色 ❌），而非恒为成功
        const next = blocks[i + 1];
        const isError =
          next?.kind === "tool_result" && next.verificationStatus === "failed";
        return (
          <ToolCallCard
            key={`tc-${i}`}
            name={block.name}
            params={block.params}
            isComplete={block.isComplete}
            isError={isError}
          />
        );
      }
      case "tool_result":
        return (
          <ToolResultCard
            key={`tr-${i}`}
            content={block.content}
            verificationStatus={block.verificationStatus}
          />
        );
      case "diff": {
        // DiffBlock 需要 entries 数组，单文件包装
        // 消息气泡内只读展示：Accept/Reject 必须在评审面板操作，
        // 否则用户误以为点 Accept 已写盘（实际未传 onAccept，不会调用后端）
        const entries = [{
          path: block.path,
          added: block.added,
          removed: block.removed,
          diff: block.diff,
        }];
        return (
          <DiffBlock
            key={`diff-${i}`}
            entries={entries}
            onPin={onPin}
            readOnly
          />
        );
      }
      case "error":
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
      case "text":
        return (
          <div key={`text-${i}`} className="oai-asst-text">
            {renderContent(block.content, deferHighlight)}
          </div>
        );
      case "widget":
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
  });
}

function AttachmentChip({ att }: { att: ChatAttachment }) {
  if (att.type === "image") {
    const src = `data:${att.mimeType};base64,${att.base64}`;
    return (
      <a className="oai-msg-att is-image" href={src} target="_blank" rel="noreferrer noopener" title={att.name}>
        <img src={src} alt={att.name} />
        <span className="oai-msg-att-name">{att.name}</span>
      </a>
    );
  }
  return (
    <span className="oai-msg-att is-file" title={att.name}>
      <span className="oai-msg-att-ico" aria-hidden>
        📄
      </span>
      <span className="oai-msg-att-name">{att.name}</span>
    </span>
  );
}

export type MessageBubbleProps = {
  message: ChatMsg;
  isLastAssistant: boolean;
  streaming: boolean;
  status?: string | null;
  fileChanges?: CodexFileChange[];
  onOpenDiff?: (path: string) => void;
  onRegenerate?: () => void;
  copiedId: string | null;
  onCopy: (id: string, text: string) => void;
  vote?: "up" | "down";
  onVote: (id: string, v: "up" | "down") => void;
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

  if (m.role === "user") {
    return (
      <div className="oai-turn oai-turn-user">
        <div className="oai-user-bubble">
          {m.attachments && m.attachments.length > 0 ? (
            <div className="oai-msg-attachments">
              {m.attachments.map((a) => (
                <AttachmentChip key={a.id} att={a} />
              ))}
            </div>
          ) : null}
          {soft.text}
          {soft.truncated ? (
            <button type="button" className="oai-expand-msg" onClick={() => setExpanded(true)}>
              Show more
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="oai-turn oai-turn-assistant">
      <div className="oai-asst-mark" aria-hidden />
      <div className="oai-asst-body">
        {/* 结构化 block 优先渲染（AG-UI 协议对齐）。
            当 blocks 存在时，按 block 顺序渲染 thinking/progress/tool_call/diff/error/text 组件，
            而非纯文本 content。blocks 追加 only（Event Sourcing），保留完整执行轨迹。
            调研：AG-UI 16 种标准事件类型 + 逐块渲染 + 事件溯源 */}
        {m.blocks && m.blocks.length > 0 ? (
          <>
            <div className="oai-asst-blocks">
              {renderBlocks(m.blocks, live, !live, onPin, onSendPrompt, isLastAssistant ? onRegenerate : undefined)}
            </div>
            {m.content && !m.blocks.some((block) => block.kind === "text") ? (
              <div className="oai-asst-text">{renderContent(soft.text, !live)}</div>
            ) : null}
          </>
        ) : m.content ? (
          <>
            {renderContent(soft.text, !live)}
            {soft.truncated ? (
              <button type="button" className="oai-expand-msg" onClick={() => setExpanded(true)}>
                Show full message ({m.content.length.toLocaleString()} chars)
              </button>
            ) : null}
          </>
        ) : live ? (
          <div className="oai-thinking">
            <span className="oai-shimmer">{status?.trim() || "Thinking"}</span>
            <span className="oai-cursor" />
          </div>
        ) : null}

        {isLastAssistant && fileChanges && fileChanges.length > 0 ? (
          <div className="oai-capsules">
            {fileChanges.map((ch) => {
              const add = (ch.diff || "")
                .split("\n")
                .filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
              const del = (ch.diff || "")
                .split("\n")
                .filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
              const meta =
                add || del
                  ? `+${add} −${del}`
                  : ch.preview !== false
                    ? "preview"
                    : undefined;
              return (
                <RunCapsule
                  key={ch.path}
                  kind="edit"
                  title={`${ch.action === "create" ? "Created" : "Edited"} ${ch.path}`}
                  meta={meta}
                  detail={(ch.diff || ch.content || "").slice(0, 800) || undefined}
                  ok
                  onOpenDiff={onOpenDiff ? () => onOpenDiff(ch.path) : undefined}
                />
              );
            })}
          </div>
        ) : null}

        {m.content && !live ? (
          <div className="oai-actions">
            <button
              type="button"
              className="oai-ibtn sm"
              title="复制"
              onClick={() => onCopy(m.id, m.content)}
            >
              {copiedId === m.id ? <Check size={14} /> : <Copy size={14} />}
            </button>
            <button
              type="button"
              className={`oai-ibtn sm${vote === "up" ? " on" : ""}`}
              title="有帮助"
              onClick={() => onVote(m.id, "up")}
            >
              <ThumbsUp size={14} />
            </button>
            <button
              type="button"
              className={`oai-ibtn sm${vote === "down" ? " on" : ""}`}
              title="没帮助"
              onClick={() => onVote(m.id, "down")}
            >
              <ThumbsDown size={14} />
            </button>
            {isLastAssistant && onRegenerate ? (
              <button
                type="button"
                className="oai-ibtn sm"
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
