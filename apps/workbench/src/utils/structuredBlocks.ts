/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Structured event blocks — AG-UI 协议对齐的结构化消息块。
 *
 * 调研证据：
 * - AG-UI 协议（AG-UI 协议，16 种标准事件类型）：
 *   RunStarted/RunFinished/RunError/StepStarted/StepFinished/
 *   TextMessageStart/Content/End/ToolCallStart/Args/End/Result/
 *   StateSnapshot/StateDelta/MessagesSnapshot/ActivitySnapshot/ActivityDelta
 * - 事件溯源：Action/Observation 事件不可变、可重放、可审计
 * - 逐块渲染：block-by-block 渲染（thinking/tool_use/tool_result/text）
 *
 * 设计：
 * - 后端 RunEvent（AG-UI 兼容信封）→ 前端 StructuredBlock 一对一映射
 * - 消息气泡按 blocks 数组顺序渲染，每种 block 对应独立组件
 * - blocks 不可变（Event Sourcing），追加 only，不修改已有 block
 * - 兼容旧纯文本消息（无 blocks 字段时回退到 content 渲染）
 */

// ── Block Types ───────────────────────────────────────────────────────────

export type StructuredBlockKind =
  | "thinking"        // AG-UI ReasoningMessageContent / 后端 thinking 事件
  | "progress"        // AG-UI StepStarted / 后端 step_start 事件
  | "tool_call"       // AG-UI ToolCallStart / 后端 action/tool_call 事件
  | "tool_result"     // AG-UI ToolCallResult / 后端 observation/tool_result 事件
  | "diff"            // AG-UI Custom(file_change) / 后端 file_change 事件
  | "error"           // AG-UI RunError / 后端 error 事件
  | "text"            // AG-UI TextMessageContent / 后端 text/message 事件
  | "widget";         // AG-UI Custom(widget) / 后端 widget 事件 — AI 内联可视化

// ── Block Interfaces ──────────────────────────────────────────────────────

export interface ThinkingBlock {
  kind: "thinking";
  content: string;
  /** 是否正在流式(未完成) */
  isStreaming?: boolean;
  /** 是否已完成(useChatFlow 收尾时读取,标记思考块光标停止) */
  isComplete?: boolean;
}

export interface ProgressBlock {
  kind: "progress";
  /** 当前步骤号（1-based） */
  currentStep: number;
  /** 总步骤数（不确定则为 undefined） */
  totalSteps?: number;
  /** 步骤描述 */
  description: string;
  /** 是否完成 */
  isComplete?: boolean;
}

export interface ToolCallBlock {
  kind: "tool_call";
  name: string;
  /** 工具参数（JSON 字符串或对象） */
  params: string;
  /** 是否完成（参数已全部到达） */
  isComplete: boolean;
}

export interface ToolResultBlock {
  kind: "tool_result";
  content: string;
  /** 验证状态 */
  verificationStatus?: "verified" | "failed";
}

export interface DiffBlock {
  kind: "diff";
  /** 文件路径 */
  path: string;
  /** 新增行数 */
  added: number;
  /** 删除行数 */
  removed: number;
  /** diff 内容 */
  diff?: string;
  /** 操作类型：create/write/edit/delete */
  action?: string;
}

export interface ErrorBlock {
  kind: "error";
  /** Problem: 错误标题（用户语言） */
  title: string;
  /** Cause: 错误诊断（可选） */
  detail?: string;
  /** Solution: 修复建议（可选） */
  suggestion?: string;
  /** 出错的工具名 */
  toolName?: string;
  /** 严重级别 */
  severity?: "transient" | "persistent" | "fatal";
  /** 已重试次数 */
  retryCount?: number;
  /** 最大重试次数 */
  maxRetries?: number;
}

export interface TextBlock {
  kind: "text";
  content: string;
  /** 是否正在流式 */
  isStreaming?: boolean;
}

/**
 * WidgetBlock — AI 内联可视化（动态 UI 渲染）
 *
 * 调研：
 * - 动态 UI 渲染：模型写 SVG/HTML，PureShowWidget 工具在对话流内渲染
 * - Claude Inline Visualizations：Settings → Visuals 开关，HTML/SVG 即时渲染
 * - 内联产物：iframe sandbox + 严格 CSP（connect-src 'none' 防数据外传）
 *
 * 安全：前端 WidgetBlock.tsx 用 iframe sandbox="allow-scripts"（不加 allow-same-origin）
 * + 严格 CSP + DOMPurify 三层防御。后端仅透传 code，不做任何渲染。
 *
 * 与 ArtifactCanvas 的边界：
 * - WidgetBlock = 过程数据（内存中的 chart spec / table data，一次性）
 * - ArtifactCanvas = 磁盘产物（文件，可编辑可持久化）
 */
export interface WidgetBlock {
  kind: "widget";
  /** 唯一标识（用于 appendBlock 同 id 更新） */
  widgetId: string;
  /** 类型标签：chart / table / flow / decision / mechanism / custom */
  widgetType: string;
  /** 完整 SVG/HTML 代码（含 <style>） */
  code: string;
  /** inline=对话流内（默认），panel=独立面板 */
  mode: "inline" | "panel";
  /** 渲染状态 */
  state?: "ready" | "error";
  /** 步骤号 */
  step?: number;
}

export type StructuredBlock =
  | ThinkingBlock
  | ProgressBlock
  | ToolCallBlock
  | ToolResultBlock
  | DiffBlock
  | ErrorBlock
  | TextBlock
  | WidgetBlock;

// ── NDJSON 事件 → StructuredBlock 转换 ────────────────────────────────────

/** 在任何工具参数进入 UI 或会话持久化前隐藏常见凭据。 */
export function redactSensitiveText(value: string): string {
  return value
    .replace(/("(?:api[_-]?key|token|access[_-]?token|password|passwd|secret|authorization|cookie)"\s*:\s*")[^"]*(")/gi, "$1[REDACTED]$2")
    .replace(/\b(Bearer\s+)[A-Za-z0-9._~+/=-]+/gi, "$1[REDACTED]")
    .replace(/\b(sk-[A-Za-z0-9_-]{12,})\b/g, "[REDACTED]");
}

/**
 * 将后端 NDJSON 事件转为 StructuredBlock（或 null 如果事件不产生 block）。
 *
 * 后端事件类型（RunEvent.to_work_dict() / to_code_ndjson()）：
 * - thinking → ThinkingBlock
 * - step_start → ProgressBlock
 * - step_end → ProgressBlock (isComplete=true)
 * - action/tool_call → ToolCallBlock
 * - observation/tool_result → ToolResultBlock
 * - file_change → DiffBlock
 * - error → ErrorBlock
 * - text/message → TextBlock
 */
export function ndjsonEventToBlock(
  obj: Record<string, unknown>,
): StructuredBlock | null {
  const type = String(obj.type || obj.chunk_type || "");
  const data = obj.data ?? obj.content ?? obj;

  switch (type) {
    case "thinking":
    case "thought": {
      const content = typeof data === "string" ? data : String(data ?? "");
      if (!content) return null;
      return { kind: "thinking", content, isStreaming: true };
    }

    case "step_start": {
      // Code 模式把真实步骤放在 obj.step；当 data 回退为整个 obj 时不能误把信封当步骤。
      const stepRaw = (typeof obj.step === "object" && obj.step)
        ? obj.step as Record<string, unknown>
        : (data !== obj && typeof data === "object" && data)
          ? data as Record<string, unknown>
          : {};
      const desc = String(stepRaw.description || stepRaw.name || "Step…");
      const stepNum = Number(stepRaw.step || stepRaw.index || 0);
      const total = Number(stepRaw.total || stepRaw.totalSteps || 0);
      return {
        kind: "progress",
        currentStep: stepNum > 0 ? stepNum : 1,
        totalSteps: total > 0 ? total : undefined,
        description: desc,
        isComplete: false,
      };
    }

    case "step_end": {
      const stepRaw = (typeof obj.step === "object" && obj.step)
        ? obj.step as Record<string, unknown>
        : (data !== obj && typeof data === "object" && data)
          ? data as Record<string, unknown>
          : {};
      const desc = String(stepRaw.description || stepRaw.name || "Step done");
      const stepNum = Number(stepRaw.step || stepRaw.index || 0);
      const total = Number(stepRaw.total || stepRaw.totalSteps || 0);
      return {
        kind: "progress",
        currentStep: stepNum > 0 ? stepNum : 1,
        totalSteps: total > 0 ? total : undefined,
        description: desc,
        isComplete: true,
      };
    }

    case "action":
    case "tool_call": {
      const d = (typeof data === "object" && data) ? data as Record<string, unknown> : {};
      const name = String(d.name || "tool");
      const args = d.args ?? d.params ?? d.arguments;
      const params = redactSensitiveText(typeof args === "string"
        ? args
        : args ? JSON.stringify(args) : "");
      return { kind: "tool_call", name, params, isComplete: true };
    }

    case "observation":
    case "tool_result": {
      const d = (typeof data === "object" && data) ? data as Record<string, unknown> : {};
      const summary = String(d.summary || d.content || "");
      const success = d.success !== false;
      return {
        kind: "tool_result",
        content: redactSensitiveText(summary || (typeof data === "string" ? data : "")),
        verificationStatus: success ? "verified" : "failed",
      };
    }

    case "file_change": {
      const d = (typeof data === "object" && data) ? data as Record<string, unknown> : {};
      const path = String(obj.path || d.path || "");
      const action = String(obj.action || d.action || "edit");
      const diff = String(obj.diff || d.diff || "");
      // 从 diff 内容统计 +/- 行数
      const lines = diff.split("\n");
      let added = 0;
      let removed = 0;
      for (const line of lines) {
        if (line.startsWith("+") && !line.startsWith("+++")) added++;
        else if (line.startsWith("-") && !line.startsWith("---")) removed++;
      }
      return { kind: "diff", path, added, removed, diff, action };
    }

    case "error": {
      const msg = typeof data === "string" ? data : String(((data as Record<string, unknown>)?.message ?? data) ?? "");
      // 启发式判断严重级别
      const lower = msg.toLowerCase();
      let severity: "transient" | "persistent" | "fatal" = "transient";
      if (/api key|unauthorized|401|invalid.*key|fatal|cannot continue/i.test(lower)) {
        severity = "fatal";
      } else if (/timeout|eaddrinuse|port.*occupied|already in use|persistent/i.test(lower)) {
        severity = "persistent";
      }
      return {
        kind: "error",
        title: msg.slice(0, 200),
        severity,
      };
    }

    case "text":
    case "message": {
      const content = typeof data === "string" ? data : String(data ?? "");
      if (!content) return null;
      return { kind: "text", content, isStreaming: true };
    }

    case "widget": {
      // Spec: inline widget — AI 调用 show_widget 工具时后端 emit
      // data: { widgetId, widgetType, code, mode, step }
      const d = (typeof data === "object" && data) ? data as Record<string, unknown> : {};
      const widgetId = String(d.widgetId || `widget_${Date.now()}`);
      const widgetType = String(d.widgetType || "custom");
      const code = String(d.code || "");
      const mode = (d.mode === "panel" ? "panel" : "inline") as "inline" | "panel";
      const step = typeof d.step === "number" ? d.step : undefined;
      if (!code) return null;
      return {
        kind: "widget",
        widgetId,
        widgetType,
        code,
        mode,
        state: "ready",
        step,
      };
    }

    default:
      return null;
  }
}

// ── Block 合并策略 ────────────────────────────────────────────────────────

/**
 * 将新 block 追加到现有 blocks 数组，应用合并规则：
 * - 连续的 text block 合并（流式追加）
 * - 连续的 thinking block 合并（流式追加）
 * - progress block 更新最后一个同步骤的 block（不新增）
 * - 其他 block 直接追加
 */
export function appendBlock(
  blocks: StructuredBlock[],
  newBlock: StructuredBlock,
): StructuredBlock[] {
  if (blocks.length === 0) return [newBlock];

  const last = blocks[blocks.length - 1];

  // text block 流式合并
  if (newBlock.kind === "text" && last.kind === "text") {
    return [
      ...blocks.slice(0, -1),
      { ...last, content: last.content + newBlock.content, isStreaming: newBlock.isStreaming },
    ];
  }

  // thinking block 流式合并
  if (newBlock.kind === "thinking" && last.kind === "thinking") {
    return [
      ...blocks.slice(0, -1),
      { ...last, content: last.content + newBlock.content, isStreaming: newBlock.isStreaming },
    ];
  }

  // progress block 始终替换最后一个 progress block（单一进度条更新 UX）
  // 设计：单一 "Thinking..." 指示器更新，不堆叠多个进度条
  // 审计轨迹保留在后端 RunEngine 事件日志（SQLite persist），前端只展示当前步骤
  if (newBlock.kind === "progress" && last.kind === "progress") {
    return [
      ...blocks.slice(0, -1),
      newBlock, // 替换（step_end 标记完成 / step_start 更新到新步骤）
    ];
  }

  // widget block 同 widgetId 时更新（AI 修正图表），否则追加新 widget
  if (newBlock.kind === "widget" && last.kind === "widget"
      && last.widgetId === newBlock.widgetId) {
    return [
      ...blocks.slice(0, -1),
      newBlock,
    ];
  }

  return [...blocks, newBlock];
}
