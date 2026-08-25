/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ToolCallCard — visual card for a tool invocation.
 *
 * Shows the tool name with an icon, optional collapsible params,
 * and a status indicator (loading spinner, success checkmark, or error ❌).
 * UX P0-3: 完成后右侧追加耗时小字（`1.2s`），OpenCode 式一行紧凑渲染。
 */

import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Loader2, X } from "lucide-react";

interface Props {
  name: string;
  params?: string;
  isComplete: boolean;
  isError?: boolean;
  /** UX P0-3: 工具耗时（毫秒）— 完成后右侧显示 `1.2s` */
  durationMs?: number;
}

const TOOL_ICONS: Record<string, string> = {
  read_file: "📖",
  write_file: "✏️",
  execute_command: "▶️",
  search_code: "🔍",
  default: "🔧",
};

const TOOL_ACTION_LABELS: Record<string, string> = {
  read_file: "Reading file",
  write_file: "Writing file",
  execute_command: "Running command",
  search_code: "Searching codebase",
  default: "Running tool",
};

function parseParamsLabel(params: string): string {
  try {
    const parsed = JSON.parse(params);
    if (parsed.path) return parsed.path;
    if (parsed.command) return parsed.command.slice(0, 50);
    return JSON.stringify(parsed).slice(0, 50);
  } catch {
    return params.replace(/\n/g, " ").slice(0, 50);
  }
}

/** 毫秒 → 紧凑耗时（OpenCode 式：<1s 显示 ms，其余 s，一位小数） */
function formatDuration(ms?: number): string {
  if (ms === undefined || !Number.isFinite(ms) || ms < 0) return "";
  if (ms < 1000) return `${Math.max(1, Math.round(ms))}ms`;
  const s = ms / 1000;
  return `${s < 60 ? s.toFixed(1).replace(/\.0$/, "") : Math.round(s)}s`;
}

export default function ToolCallCard({ name, params, isComplete, isError, durationMs }: Props) {
  const [paramsOpen, setParamsOpen] = useState(false);
  const icon = TOOL_ICONS[name] || TOOL_ICONS.default;
  const label = TOOL_ACTION_LABELS[name] || TOOL_ACTION_LABELS.default;
  const paramsLabel = params ? parseParamsLabel(params) : "";
  const durationText = isComplete && !isError ? formatDuration(durationMs) : "";

  return (
    <div
      className={`cl-tool-call ${isComplete ? "complete" : "loading"} ${isError ? "error" : ""}`}
    >
      <div className="cl-tool-call-header">
        <span className="cl-tool-call-icon">{icon}</span>
        <span className="cl-tool-call-label">{label}</span>
        {paramsLabel && (
          <span className="cl-tool-call-target">{paramsLabel}</span>
        )}
        {durationText && <span className="cl-tool-call-duration">{durationText}</span>}
        <span className="cl-tool-call-status">
          {isError ? (
            <X size={12} className="cl-tool-error-icon" />
          ) : isComplete ? (
            <Check size={12} className="cl-tool-check" />
          ) : (
            <Loader2 size={12} className="spin" />
          )}
        </span>
        {params && (
          <button
            className="cl-tool-call-toggle"
            onClick={(e) => { e.stopPropagation(); setParamsOpen(!paramsOpen); }}
            type="button"
          >
            {paramsOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        )}
      </div>
      {paramsOpen && params && (
        <div className="cl-tool-call-params">
          <pre><code>{params}</code></pre>
        </div>
      )}
    </div>
  );
}
