/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code is proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ThinkingBlock — 简洁的"思考中"状态标签（参考 Cursor/Trae）
 *
 * 设计原则：
 * - 不暴露模型内部 CoT（chain-of-thought）内容
 * - 流式时显示 spinner + 状态文字
 * - 完成后只显示一行简短摘要，不可展开
 * - 不泄露内部架构（规划/执行/审查等阶段名）
 */

import React from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import './ThinkingBlock.css';

interface Props {
  content: string;
  isStreaming?: boolean;
}

const ThinkingBlock = React.memo(function ThinkingBlock({ content, isStreaming = true }: Props) {
  // 清理内容：去掉模型内部的前缀和换行，只取干净的状态文字
  const sanitized = content
    .replace(/^\s*\(Step\s*\d+\)\s*/g, '')
    .replace(/\n+/g, ' ')
    .trim();
  let head = sanitized.slice(0, 80);
  const lastSpace = head.lastIndexOf(' ');
  if (head.length === 80 && lastSpace > 40) head = head.slice(0, lastSpace);
  const summary = head + (sanitized.length > 80 ? '…' : '');

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
        <span className="cl-thinking-label">
          {isStreaming ? '思考中' : '分析完成'}
        </span>
        {!isStreaming && summary && (
          <span className="cl-thinking-summary">{summary}</span>
        )}
      </div>
    </div>
  );
});

export default ThinkingBlock;
