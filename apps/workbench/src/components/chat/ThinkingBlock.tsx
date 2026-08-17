/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ThinkingBlock — collapsible "Thinking..." section.
 *
 * During streaming: auto-expanded, shows animated spinner + streaming content.
 * When complete: collapsed by default with a summary chevron.
 */

import React, { useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";

interface Props {
  content: string;
  isStreaming?: boolean;
}

const ThinkingBlock = React.memo(function ThinkingBlock({ content, isStreaming = true }: Props) {
  // 分析内容默认折叠：优先展示可验证行动，避免把模型内部文本包装成权威 CoT。
  const [open, setOpen] = useState(false);

  const summary = content.slice(0, 60).replace(/\n/g, " ") + (content.length > 60 ? "…" : "");

  return (
    <div className={`cl-thinking ${isStreaming ? "streaming" : "complete"}`}>
      <button
        className="cl-thinking-toggle"
        onClick={() => setOpen(!open)}
        type="button"
        aria-label={open ? "收起分析摘要" : "展开分析摘要"}
      >
        {isStreaming ? (
          <Loader2 size={12} className="spin cl-thinking-spinner" />
        ) : open ? (
          <ChevronDown size={12} />
        ) : (
          <ChevronRight size={12} />
        )}
        <span className="cl-thinking-label">{isStreaming ? "正在分析" : "分析摘要"}</span>
        {!open && !isStreaming && (
          <span className="cl-thinking-summary">{summary}</span>
        )}
      </button>
      {open && (
        <div className="cl-thinking-body">
          <p>{content}{isStreaming && <span className="cl-cursor">▍</span>}</p>
        </div>
      )}
    </div>
  );
});

export default ThinkingBlock;