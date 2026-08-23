/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ToolResultCard — displays the result of a tool call.
 *
 * Visually connected to its ToolCallCard via a left-border bridge.
 * Shows the result content in a collapsible code block.
 * Displays ✅ or ⚠️ badge for verified/failed tool results.
 */

import { useState } from "react";
import { ChevronDown, ChevronRight, CheckCircle2, AlertTriangle, ShieldAlert } from "lucide-react";

interface Props {
  content: string;
  /** Verification status: "verified" = ✅, "failed" = ⚠️, undefined = no badge */
  verificationStatus?: "verified" | "failed";
}

/** Detect if the result was blocked by an architecture or security guardrail. */
function isGuardBlocked(content: string): boolean {
  return /^BLOCKED by (?:guardrail|architecture guardrail)/.test(content);
}

/** 智能折叠阈值：超过此字符数自动折叠（基于 W3C Disclosure + agentpatterns.ai head-and-tail 研究） */
const COLLAPSE_THRESHOLD = 500;
/** 折叠时显示的头部行数 */
const HEAD_LINES = 5;
/** 折叠时显示的尾部行数 */
const TAIL_LINES = 3;

/** 生成 head-and-tail 预览：前几行 + 省略提示 + 后几行（比仅头部更有效，保留结尾上下文） */
function buildPreview(lines: string[]): string {
  if (lines.length <= HEAD_LINES + TAIL_LINES + 1) return lines.join("\n");
  const head = lines.slice(0, HEAD_LINES);
  const tail = lines.slice(-TAIL_LINES);
  const hiddenCount = lines.length - HEAD_LINES - TAIL_LINES;
  return head.join("\n") + `\n\n… 隐藏 ${hiddenCount} 行 …\n\n` + tail.join("\n");
}

export default function ToolResultCard({ content, verificationStatus }: Props) {
  const [expanded, setExpanded] = useState(false);
  const lines = content.split("\n");
  const charCount = content.length;
  const isLong = charCount > COLLAPSE_THRESHOLD || lines.length > HEAD_LINES + TAIL_LINES + 2;
  const preview = isLong ? buildPreview(lines) : content;
  const hiddenLines = isLong ? lines.length - HEAD_LINES - TAIL_LINES : 0;

  // Derive verification status from content markers if not explicitly provided
  const derivedStatus = verificationStatus
    ?? (content.includes("✅ Edit verified") ? "verified"
      : content.includes("⚠️ Edit verification FAILED") || content.includes("❌ Edit verification FAILED")
        ? "failed"
        : undefined);

  const blocked = isGuardBlocked(content);

  return (
    <div className={`cl-tool-result${blocked ? " cl-tool-result--blocked" : ""}`}>
      <div className="cl-tool-result-header">
        <span className="cl-tool-result-label">
          {blocked && <ShieldAlert size={12} className="cl-tool-result-icon--blocked" />}
          结果{isLong ? ` · ${lines.length} 行 · ${(charCount / 1024).toFixed(1)}KB` : ""}
        </span>
        {blocked && (
          <span className="cl-tool-result-badge cl-tool-result-badge--blocked" title="护栏拦截了此次修改">
            <ShieldAlert size={12} /> 已拦截
          </span>
        )}
        {derivedStatus === "verified" && (
          <span className="cl-tool-result-badge cl-tool-result-badge--verified" title="修改已验证通过">
            <CheckCircle2 size={12} /> 已验证
          </span>
        )}
        {derivedStatus === "failed" && (
          <span className="cl-tool-result-badge cl-tool-result-badge--failed" title="修改验证未通过">
            <AlertTriangle size={12} /> 不一致
          </span>
        )}
        {isLong && (
          <button
            className="cl-tool-result-toggle"
            onClick={() => setExpanded(!expanded)}
            type="button"
          >
            {expanded ? (
              <><ChevronDown size={10} /> 收起</>
            ) : (
              <><ChevronRight size={10} /> 展开全部</>
            )}
          </button>
        )}
      </div>
      <div className="cl-tool-result-body">
        <pre><code>{expanded ? content : preview}</code></pre>
        {isLong && !expanded && (
          <div className="cl-tool-result-more">
            隐藏了 {hiddenLines} 行（共 {(charCount / 1024).toFixed(1)}KB）· 点击「展开全部」查看
          </div>
        )}
      </div>
    </div>
  );
}