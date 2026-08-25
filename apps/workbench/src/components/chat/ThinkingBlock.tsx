/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ThinkingBlock — 简洁的"思考中"状态标签（参考 Cursor/Trae）
 *
 * 设计原则：
 * - 流式时显示 spinner + 状态文字
 * - 完成后显示一行简短摘要，默认收起（OpenCode 式克制：思考默认折叠）
 * - UX P0-2: 点击可展开完整推理文本 + 「复制思考」；不改变默认收起的视觉密度
 */

import React, { useMemo, useState } from 'react';
import { Check, ChevronDown, ChevronRight, Copy, Loader2, Sparkles } from 'lucide-react';
import './ThinkingBlock.css';

interface Props {
  content: string;
  isStreaming?: boolean;
}

const ThinkingBlock = React.memo(function ThinkingBlock({ content, isStreaming = true }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  // 清理内容：去掉模型内部的前缀和换行，只取干净的状态文字
  const sanitized = useMemo(
    () =>
      content
        .replace(/^\s*\(Step\s*\d+\)\s*/g, '')
        .replace(/\n+/g, ' ')
        .trim(),
    [content],
  );
  let head = sanitized.slice(0, 80);
  const lastSpace = head.lastIndexOf(' ');
  if (head.length === 80 && lastSpace > 40) head = head.slice(0, lastSpace);
  const summary = head + (sanitized.length > 80 ? '…' : '');
  // 心跳/占位文本没有展开价值 — 不给展开箭头
  const expandable =
    !isStreaming &&
    sanitized.length > 0 &&
    !/^仍在思考中/.test(sanitized) &&
    !/^正在分析你的需求/.test(sanitized);

  return (
    <div className={`cl-thinking ${isStreaming ? 'streaming' : 'complete'}`}>
      <div className="cl-thinking-bar">
        <span className="cl-thinking-icon" aria-hidden>
          {isStreaming ? (
            <Loader2 size={12} className="spin cl-thinking-spinner" />
          ) : (
            <Sparkles size={12} />
          )}
        </span>
        <span className="cl-thinking-label">{isStreaming ? '思考中' : '分析完成'}</span>
        {!isStreaming && summary && !expanded && (
          <span className="cl-thinking-summary">{summary}</span>
        )}
        {expandable && (
          <button
            type="button"
            className="cl-thinking-toggle"
            aria-expanded={expanded}
            aria-label={expanded ? '收起思考过程' : '展开思考过程'}
            title={expanded ? '收起思考过程' : '展开思考过程'}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        )}
      </div>
      {expandable && expanded && (
        <>
          <div className="cl-thinking-full" role="region" aria-label="思考过程全文">
            {content}
          </div>
          <button
            type="button"
            className="cl-thinking-copy"
            onClick={() => {
              void navigator.clipboard.writeText(content).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1400);
              });
            }}
          >
            {copied ? <Check size={11} /> : <Copy size={11} />}
            {copied ? '已复制' : '复制思考'}
          </button>
        </>
      )}
    </div>
  );
});

export default ThinkingBlock;
