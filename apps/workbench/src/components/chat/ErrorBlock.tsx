/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ErrorBlock — inline error display with recovery actions.
 *
 * 调研证据：
 * - agentic-design.ai "Error Recovery Patterns": Problem + Cause + Solution 三元素结构
 *   "Use three-element structure: Problem + Cause + Solution with progressive disclosure"
 * - aiuxdesign.guide "Error Recovery & Graceful Degradation":
 *   "Every error needs an exit, not just an apology"
 *   "Make 'try again' actually different" — 重试需改变条件
 * - aiuxplayground.com "Error Recovery Strategies":
 *   "Show the failure, the recovery action being attempted, and remaining retry budget"
 * - dev.to "7 Patterns That Stop Your AI Agent":
 *   "classify the error first and route to the appropriate recovery strategy"
 *
 * 设计：
 * - Problem（标题）: 用户语言描述问题，不显示 stack trace
 * - Cause（诊断，可选）: 渐进式披露，默认隐藏技术详情
 * - Solution（按钮）: 重试/跳过/人工接管，根据错误类型显示不同组合
 */

import { useState } from "react";
import { AlertTriangle, RotateCcw, SkipForward, UserCog, ChevronDown, ChevronRight, Info } from "lucide-react";

/** 错误严重级别（决定显示策略） */
export type ErrorSeverity = "transient" | "persistent" | "fatal";

/** 错误类型 → 决定显示哪些恢复按钮 */
export interface ErrorBlockProps {
  /** Problem: 错误标题（用户语言，非 stack trace） */
  title: string;
  /** Cause: 错误诊断/原因（可选，渐进式披露） */
  detail?: string;
  /** Solution: 修复建议（可选，显示在诊断下方） */
  suggestion?: string;
  /** 出错的工具名 */
  toolName?: string;
  /** 错误严重级别：transient=瞬时(可重试) / persistent=持续(需换策略) / fatal=致命(需人工) */
  severity?: ErrorSeverity;
  /** 已重试次数 */
  retryCount?: number;
  /** 最大重试次数 */
  maxRetries?: number;
  /** 重试回调 */
  onRetry?: () => void;
  /** 跳过回调 */
  onSkip?: () => void;
  /** 人工接管回调 */
  onTakeOver?: () => void;
  /** 是否正在重试中 */
  isRetrying?: boolean;
}

export default function ErrorBlock({
  title,
  detail,
  suggestion,
  toolName,
  severity = "transient",
  retryCount = 0,
  maxRetries = 3,
  onRetry,
  onSkip,
  onTakeOver,
  isRetrying,
}: ErrorBlockProps) {
  const [detailOpen, setDetailOpen] = useState(false);

  // 根据严重级别决定显示哪些按钮（基于 dev.to "classify the error first" 研究）
  const showRetry = severity === "transient" && retryCount < maxRetries;
  const showSkip = severity !== "fatal";
  const showTakeOver = severity === "persistent" || severity === "fatal";
  const retriesExhausted = retryCount >= maxRetries;

  return (
    <div className={`cl-error-block cl-error-block--${severity}`}>
      <div className="cl-error-header">
        <AlertTriangle size={13} className="cl-error-icon" />
        <span className="cl-error-title">{title}</span>
        {toolName && <span className="cl-error-tool">{toolName}</span>}
        {retriesExhausted && (
          <span className="cl-error-retries-exhausted">retries exhausted</span>
        )}
        {detail && (
          <button
            className="cl-error-toggle"
            onClick={() => setDetailOpen(!detailOpen)}
            type="button"
            title="Show diagnostics"
          >
            {detailOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        )}
      </div>
      {detailOpen && detail && (
        <div className="cl-error-detail">
          <div className="cl-error-detail-label">
            <Info size={10} /> Diagnostics
          </div>
          <pre><code>{detail}</code></pre>
          {suggestion && (
            <div className="cl-error-suggestion">
              <strong>Suggestion:</strong> {suggestion}
            </div>
          )}
        </div>
      )}
      <div className="cl-error-actions">
        {showRetry && onRetry && (
          <button
            className="cl-error-btn cl-error-btn--retry"
            onClick={onRetry}
            disabled={isRetrying}
            type="button"
          >
            <RotateCcw size={11} />
            {isRetrying ? "Retrying…" : `Retry${retryCount > 0 ? ` (${retryCount}/${maxRetries})` : ""}`}
          </button>
        )}
        {showSkip && onSkip && (
          <button
            className="cl-error-btn cl-error-btn--skip"
            onClick={onSkip}
            type="button"
          >
            <SkipForward size={11} />
            Skip
          </button>
        )}
        {showTakeOver && onTakeOver && (
          <button
            className="cl-error-btn cl-error-btn--takeover"
            onClick={onTakeOver}
            type="button"
          >
            <UserCog size={11} />
            Take over
          </button>
        )}
      </div>
    </div>
  );
}
