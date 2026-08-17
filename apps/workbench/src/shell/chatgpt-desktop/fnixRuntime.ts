/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Fnix agentd runtime clients for the ChatGPT-look shell.
 * Work → POST /api/v1/work/stream (NDJSON)
 * Codex → POST /api/v1/chat/agent (NDJSON)
 */

import { authHeaders, getFnixApiBase, syncHarnessConfig } from "../../lib/fnixBridge";
import type { AIProviderConfig } from "../../utils/providers";
import type { ChatAttachment } from "../../utils/tauri";
import { ndjsonEventToBlock, redactSensitiveText, type StructuredBlock } from "../../utils/structuredBlocks";
import { activityId, type ActivityItem } from "./activityTypes";

export type FnixLlm = {
  provider?: string;
  model?: string;
  api_key?: string;
  base_url?: string;
  temperature?: number;
};

export type CodexFileChange = {
  path: string;
  action?: string;
  diff?: string;
  content?: string;
  old_content?: string;
  preview?: boolean;
  /** 变更发生的时间戳(CanvasDock 用于版本排序) */
  timestamp?: number;
  /** 关联的 run id(CanvasDock 用于聚合版本历史) */
  runId?: string;
};

export type WorkExecMode = "ask" | "plan" | "craft";

export type WorkMission = {
  title?: string;
  workspace_kind?: string;
  work_mode?: string;
  expected_deliverables?: string[];
  [key: string]: unknown;
};

export type WorkPipelineInfo = {
  step?: number | string;
  work_mode?: string;
  workspace_kind?: string;
  reasoning_mode?: string;
  /** Heal 轮次进度（current 当前轮 / max 总轮数） */
  heal_round?: { current: number; max: number };
  [key: string]: unknown;
};

/** KTG / STP / MFP evolution snapshot from work stream. */
export type EvolutionInfo = {
  step?: string;
  reasoning_mode?: string;
  ktg_paths?: number;
  ktg_nodes?: number;
  concepts?: string[];
  ktg?: boolean;
  stp?: boolean;
  mfp?: boolean;
  memory?: { short?: number; long?: number; entity?: boolean } | boolean;
  mfp_result?: unknown;
  [key: string]: unknown;
};

type StreamHandlers = {
  onText?: (delta: string) => void;
  onStatus?: (label: string) => void;
  onArtifact?: (art: { path: string; name?: string }) => void;
  onFileChange?: (fc: CodexFileChange) => void;
  onMission?: (mission: WorkMission) => void;
  onPipeline?: (info: WorkPipelineInfo) => void;
  onEvolution?: (info: EvolutionInfo) => void;
  /** 过程可视化活动项（桌面应用 tool activity） */
  onActivity?: (item: ActivityItem) => void;
  onDone?: (payload: unknown) => void;
  onError?: (message: string) => void;
  /**
   * 结构化 block 流（AG-UI 协议对齐）— 每个后端事件转为 StructuredBlock 注入消息气泡。
   * 与 onText/onActivity/onFileChange 并行触发，消费方（useChatFlow）负责合并到消息 blocks 数组。
   * 调研：AG-UI 16 种标准事件类型 + 事件溯源 + 逐块渲染
   */
  onStructuredBlock?: (block: import("../../utils/structuredBlocks").StructuredBlock) => void;
};

function emitActivity(
  handlers: StreamHandlers,
  partial: Omit<ActivityItem, "id" | "startedAt"> & { id?: string; startedAt?: number },
) {
  handlers.onActivity?.({
    id: partial.id || activityId(),
    startedAt: partial.startedAt ?? Date.now(),
    ...partial,
  });
}

/**
 * 将 NDJSON 事件转为 StructuredBlock 并 emit 到消息气泡。
 * 基于 AG-UI 协议（16 种标准事件类型）+ 事件溯源。
 * 与 onActivity/onFileChange/onError 并行触发，消费方负责合并到消息 blocks 数组。
 */
function emitStructuredBlock(
  handlers: StreamHandlers,
  obj: Record<string, unknown>,
): void {
  if (!handlers.onStructuredBlock) return;
  const block = ndjsonEventToBlock(obj);
  if (block) handlers.onStructuredBlock(block);
}

function toolArg(args: unknown, keys: string[]): string {
  if (!args || typeof args !== "object") return "";
  const record = args as Record<string, unknown>;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function describeToolAction(name: string, args: unknown): Pick<ActivityItem, "kind" | "title" | "path" | "detail"> {
  const normalized = name.toLowerCase();
  const path = toolArg(args, ["path", "file_path", "file", "target", "source_path"]);
  const query = toolArg(args, ["query", "pattern", "regex", "search"]);
  const command = toolArg(args, ["command", "cmd", "script"]);
  const detail = typeof args === "string"
    ? redactSensitiveText(args).slice(0, 500)
    : args && typeof args === "object"
      ? redactSensitiveText(JSON.stringify(args)).slice(0, 500)
      : undefined;

  if (/grep|search|find/.test(normalized)) {
    return { kind: "read", title: query ? `搜索 “${query.slice(0, 80)}”` : "搜索项目", path: path || undefined, detail };
  }
  if (/read|open|list/.test(normalized)) {
    return { kind: "read", title: path ? `读取 ${path}` : "读取项目内容", path: path || undefined, detail };
  }
  if (/edit|patch|replace|move|rename|delete/.test(normalized)) {
    return { kind: "edit", title: path ? `修改 ${path}` : `执行 ${name}`, path: path || undefined, detail };
  }
  if (/write|create|save/.test(normalized)) {
    return { kind: "write", title: path ? `写入 ${path}` : `执行 ${name}`, path: path || undefined, detail };
  }
  if (/test|check|lint|diagnostic/.test(normalized)) {
    return { kind: "test", title: command ? `运行 ${command.slice(0, 100)}` : `运行 ${name}`, detail };
  }
  if (/shell|terminal|exec|command|run/.test(normalized)) {
    return { kind: "run", title: command ? `运行 ${command.slice(0, 100)}` : `运行 ${name}`, detail };
  }
  return { kind: "tool", title: `使用 ${name}`, path: path || undefined, detail };
}

function mapProviderType(p: AIProviderConfig): string {
  if (p.type === "gemini") return "gemini";
  if (p.type === "anthropic") return "anthropic";
  const name = (p.name || "").toLowerCase();
  if (name.includes("deepseek")) return "deepseek";
  if (name.includes("qwen") || name.includes("dashscope")) return "qwen";
  if (name.includes("glm") || name.includes("zhipu") || name.includes("z.ai")) return "glm";
  if (name.includes("ollama")) return "ollama";
  return "openai";
}

export function pickFnixLlm(
  providers: AIProviderConfig[],
  fallbackKey: string,
  fallbackProvider: string,
  fallbackModel: string,
): FnixLlm | null {
  const withKey = providers.find(
    (p) => (p.apiKey && p.apiKey.trim()) || p.name.toLowerCase().includes("ollama"),
  );
  if (withKey) {
    const model = withKey.models.find((m) => m.enabled)?.id || withKey.models[0]?.id || fallbackModel;
    return {
      provider: mapProviderType(withKey),
      model,
      api_key: withKey.apiKey?.trim() || undefined,
      base_url: withKey.baseUrl,
    };
  }
  if (fallbackKey.trim()) {
    return {
      provider: fallbackProvider || "openai",
      model: fallbackModel || "gpt-4o",
      api_key: fallbackKey.trim(),
    };
  }
  return null;
}

export async function pushLlmToHarness(llm: FnixLlm): Promise<void> {
  await syncHarnessConfig({
    provider: llm.provider,
    model: llm.model,
    base_url: llm.base_url,
    api_key: llm.api_key,
  });
}

async function readNdjsonStream(
  res: Response,
  signal: AbortSignal | undefined,
  onLine: (obj: Record<string, unknown>) => void,
): Promise<void> {
  if (!res.body) {
    const text = await res.text();
    for (const line of text.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      try {
        onLine(JSON.parse(t) as Record<string, unknown>);
      } catch {
        /* skip */
      }
    }
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    if (signal?.aborted) {
      try {
        await reader.cancel();
      } catch {
        /* ignore */
      }
      throw new DOMException("Aborted", "AbortError");
    }
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n");
    buf = parts.pop() || "";
    for (const line of parts) {
      const t = line.trim();
      if (!t) continue;
      try {
        onLine(JSON.parse(t) as Record<string, unknown>);
      } catch {
        /* skip bad line */
      }
    }
  }
  if (buf.trim()) {
    try {
      onLine(JSON.parse(buf.trim()) as Record<string, unknown>);
    } catch {
      /* ignore */
    }
  }
}

/**
 * Wrap an external AbortSignal with an idle-timeout guard. If no data is
 * received for `idleMs`, the wrapped signal aborts and `onTimeout` fires —
 * so a stalled stream (server hung, dead socket) can't hang the UI forever.
 *
 * P0-1: idle timeout 从 60s 提升到 5 分钟 — LLM 非流式调用期间 (复杂推理任务)
 * 可能 90s+ 才有响应, 60s 会误切断。后端 AgenticLoop 已加 15s 心跳, 但双保险
 * 更稳妥。业界主流工具默认也是 5 分钟以上。
 */
function createStreamGuard(
  external: AbortSignal | undefined,
  onTimeout: () => void,
  idleMs = 300_000,
): { signal: AbortSignal; touch: () => void; dispose: () => void } {
  const ctrl = new AbortController();
  let timer: number | undefined;
  const arm = () => {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      ctrl.abort();
      onTimeout();
    }, idleMs);
  };
  arm();
  const onExt = () => ctrl.abort();
  if (external) {
    if (external.aborted) ctrl.abort();
    else external.addEventListener("abort", onExt, { once: true });
  }
  return {
    signal: ctrl.signal,
    touch: arm,
    dispose: () => {
      if (timer) window.clearTimeout(timer);
      if (external) external.removeEventListener("abort", onExt);
    },
  };
}

/** Work mode — Fnix office/task pipeline (Ask / Plan / Craft). */
export async function streamWork(opts: {
  userInput: string;
  workspace?: string;
  sessionId?: string;
  workMode?: WorkExecMode;
  llm: FnixLlm;
  attachments?: ChatAttachment[];
  /** 前端技能开关：禁用的内置技能名（后端 builtin skills 注入时跳过） */
  disabledSkills?: string[];
  signal?: AbortSignal;
  handlers: StreamHandlers;
  /** Internal: override stream URL (Spec 4 resumeRun 复用流式管线) */
  _url?: string;
  /** Internal: override request body (Spec 4 resumeRun 复用流式管线) */
  _body?: Record<string, unknown>;
}): Promise<void> {
  const base = getFnixApiBase();
  const guard = createStreamGuard(opts.signal, () => {
    opts.handlers.onError?.("连接超时：流式输出超过 5 分钟无数据，请检查 agentd 或后端。");
  });
  try {
    // Spec 4: 当 _url/_body 提供时（resumeRun），复用本函数的整套 NDJSON 流式分发。
    const url = opts._url ?? `${base}/api/v1/work/stream`;
    const body = opts._body ?? {
      user_input: opts.userInput,
      workspace: opts.workspace || undefined,
      session_id: opts.sessionId || undefined,
      work_mode: opts.workMode || "craft",
      llm: opts.llm,
      attachments: opts.attachments || undefined,
      disabled_skills:
        opts.disabledSkills && opts.disabledSkills.length > 0
          ? opts.disabledSkills
          : undefined,
    };
    const res = await fetch(url, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
      signal: guard.signal,
    });

    if (!res.ok) {
      const err = await res.text().catch(() => "");
      throw new Error(err || `Work stream failed (${res.status})`);
    }

    let sawDone = false;
    let sawText = false;
    const textChunks: string[] = [];
    await readNdjsonStream(res, guard.signal, (obj) => {
      guard.touch();
      // 结构化 block 流：每个 NDJSON 事件都尝试转为 StructuredBlock 注入消息气泡
      emitStructuredBlock(opts.handlers, obj);
      const chunk = String(obj.chunk_type || obj.type || "");
    const content = obj.content;
    if (chunk === "error") {
      opts.handlers.onError?.(typeof content === "string" ? content : JSON.stringify(content));
      return;
    }
    if (chunk === "text" || chunk === "message") {
      const t = typeof content === "string" ? content : String(content ?? "");
      if (t) {
        // 后端偶发重复推送整段正文时去重
        if (textChunks.length === 1 && t === textChunks[0]) {
          return;
        }
        if (textChunks.some((c) => c.length > 80 && c === t)) {
          return;
        }
        textChunks.push(t);
        sawText = true;
        opts.handlers.onText?.(t);
      }
      return;
    }
    if (chunk === "mission" && content && typeof content === "object") {
      const mission = content as WorkMission;
      opts.handlers.onMission?.(mission);
      const title = String(mission.title || "任务");
      const mode = String(mission.work_mode || opts.workMode || "craft");
      opts.handlers.onStatus?.("正在理解任务");
      emitActivity(opts.handlers, {
        kind: "mission",
        title,
        meta: mode.toUpperCase(),
        status: "running",
      });
      return;
    }
    if (chunk === "pipeline" && content && typeof content === "object") {
      const info = content as WorkPipelineInfo;
      // heal_round: { current, max } — 提取并归一化为 number[]
      const hr = (content as { heal_round?: { current?: unknown; max?: unknown } }).heal_round;
      if (hr && typeof hr === "object") {
        const cur = typeof hr.current === "number" ? hr.current : Number(hr.current);
        const mx = typeof hr.max === "number" ? hr.max : Number(hr.max);
        info.heal_round =
          Number.isFinite(cur) && Number.isFinite(mx) ? { current: cur, max: mx } : undefined;
      } else {
        info.heal_round = undefined;
      }
      opts.handlers.onPipeline?.(info);
      const reason = String(info.reasoning_mode || "");
      const step = String(info.step ?? "");
      opts.handlers.onStatus?.("正在准备下一步操作");
      emitActivity(opts.handlers, {
        kind: "plan",
        title: reason || `Pipeline step ${step || "…"}`,
        meta: "pipeline",
        status: "running",
      });
      return;
    }
    if (chunk === "evolution" && content && typeof content === "object") {
      const evo = content as EvolutionInfo;
      opts.handlers.onEvolution?.(evo);
      const paths = typeof evo.ktg_paths === "number" ? evo.ktg_paths : 0;
      const mode = String(evo.reasoning_mode || evo.step || "ready");
      const label = `KTG ${paths} · ${mode}`;
      emitActivity(opts.handlers, {
        kind: "think",
        title: label,
        meta: "evolution",
        status: "running",
      });
      return;
    }
    if (chunk === "thought" || chunk === "thinking") {
      // Spec 2: 真实 LLM 思考内容（可折叠展示，推理过程展示）
      const label =
        typeof content === "string"
          ? content.slice(0, 120)
          : chunk;
      opts.handlers.onStatus?.(label);
      emitActivity(opts.handlers, {
        kind: "think",
        title: label || "Thinking…",
        status: "running",
        // 完整思考内容存到 detail，前端可展开
        detail: typeof content === "string" ? content : undefined,
      });
      return;
    }
    if (chunk === "action") {
      // Spec 2: 工具调用前置事件（含 name + args）
      const name =
        content && typeof content === "object"
          ? String((content as { name?: string }).name || "tool")
          : "tool";
      const actionContent = content as { args?: unknown; call_id?: unknown; tool_call_id?: unknown; id?: unknown } | null;
      const args = actionContent?.args;
      const callId = String(actionContent?.call_id || actionContent?.tool_call_id || actionContent?.id || "");
      const action = describeToolAction(name, args);
      opts.handlers.onStatus?.(action.title);
      emitActivity(opts.handlers, {
        ...action,
        ...(callId ? { id: `tool-${callId}` } : {}),
        meta: name,
        status: "running",
      });
      return;
    }
    if (chunk === "observation") {
      // Spec 2: 工具结果事件（含 success + summary）
      const obs = content as {
        success?: boolean;
        summary?: string;
        name?: string;
        duration_ms?: number;
        call_id?: unknown;
        tool_call_id?: unknown;
        id?: unknown;
      } | null;
      const ok = obs?.success !== false;
      const name = obs?.name || "tool";
      const callId = String(obs?.call_id || obs?.tool_call_id || obs?.id || "");
      const summary = redactSensitiveText(obs?.summary || "").slice(0, 200);
      opts.handlers.onStatus?.(ok ? `${name} 已完成` : `${name} 执行失败`);
      emitActivity(opts.handlers, {
        ...(callId ? { id: `tool-${callId}` } : {}),
        kind: ok ? "tool" : "error",
        title: ok ? `${name} 已完成` : `${name} 执行失败`,
        meta: name,
        status: ok ? "done" : "error",
        detail: summary || undefined,
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "tool_call") {
      // 兼容旧 chunk：若无 action 前置，也派生一个 running activity
      const name =
        content && typeof content === "object"
          ? String((content as { name?: string }).name || "tool")
          : "tool";
      const toolContent = content as { call_id?: unknown; tool_call_id?: unknown; id?: unknown } | null;
      const callId = String(toolContent?.call_id || toolContent?.tool_call_id || toolContent?.id || "");
      const action = describeToolAction(name, undefined);
      opts.handlers.onStatus?.(action.title);
      emitActivity(opts.handlers, {
        ...action,
        ...(callId ? { id: `tool-${callId}` } : {}),
        meta: name,
        status: "running",
      });
      return;
    }
    if (chunk === "tool_result") {
      // 兼容旧 chunk：若无 observation，也派生一个 done activity
      const resultContent = content as { call_id?: unknown; tool_call_id?: unknown; id?: unknown; content?: unknown; summary?: unknown } | null;
      const rawText = typeof content === "string" ? content : String(resultContent?.summary || resultContent?.content || "");
      const text = redactSensitiveText(rawText);
      const callId = String(resultContent?.call_id || resultContent?.tool_call_id || resultContent?.id || "");
      const ok = !text.startsWith("[失败]");
      opts.handlers.onStatus?.(ok ? "工具执行完成" : "工具执行失败");
      emitActivity(opts.handlers, {
        ...(callId ? { id: `tool-${callId}` } : {}),
        kind: ok ? "tool" : "error",
        title: ok ? "工具执行完成" : "工具执行失败",
        status: ok ? "done" : "error",
        detail: text.slice(0, 200) || undefined,
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "artifact" && content && typeof content === "object") {
      const art = content as { path?: string; name?: string };
      if (art.path) {
        opts.handlers.onArtifact?.({ path: art.path, name: art.name });
        emitActivity(opts.handlers, {
          kind: "write",
          title: art.name || "Artifact",
          path: art.path,
          status: "done",
          endedAt: Date.now(),
        });
      }
      return;
    }
    if (chunk === "decision_context" && content && typeof content === "object") {
      // Spec 5: 决策上下文面板 — 嵌入 ProcessTimeline 的 DecisionCard
      // content 结构：{goal, concepts[], concept_edges[], reasoning_mode, memory_short_count, memory_long_count, risks[]}
      const ctx = content as {
        goal?: string;
        concepts?: { id: string; label: string; layer: string }[];
        concept_edges?: { from: string; to: string; type: string }[];
        reasoning_mode?: string;
        memory_short_count?: number;
        memory_long_count?: number;
        risks?: { type: string; between: string[] }[];
      };
      const conceptLabels = (ctx.concepts || []).map((c) => c.label).filter(Boolean);
      const title = conceptLabels.length > 0
        ? `决策依据 · ${conceptLabels.slice(0, 3).join(" · ")}${conceptLabels.length > 3 ? ` +${conceptLabels.length - 3}` : ""}`
        : "决策依据";
      emitActivity(opts.handlers, {
        kind: "plan",
        title,
        status: "done",
        detail: JSON.stringify(ctx),
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "route_decision" && content && typeof content === "object") {
      // Spec 7+ DAAO 真路由: 路由决策可视化 + 四维闭环反馈信号
      // 显示难度/HERA命中率/最近失败率/置信度, 让用户看到"为什么选这条路径"
      const rd = content as {
        route?: string;
        max_steps?: number;
        max_reflect_rounds?: number;
        workspace_kind?: string;
        work_mode?: string;
        reason?: string;
        tool_count?: number;
        // Spec 7+ 四维闭环新字段
        difficulty_score?: number;
        hera_hit_rate?: number;
        recent_failure_rate?: number;
        confidence?: number;
        tool_subset?: string[];
        fallback?: boolean;
      };
      const route = rd.route || "react";
      const mode = (rd.work_mode || "craft").toUpperCase();
      const title = `路由决策 · ${mode} · ${route}`;
      const stepsMeta = `${rd.max_steps || "?"} 步 / ${rd.max_reflect_rounds ?? "?"} 轮反思`;
      opts.handlers.onStatus?.(`${mode} · ${route} · ${stepsMeta}`);
      // 把四维信号拼进 meta, 让 GlassProcessList RouteCard 能展示
      const signals: string[] = [];
      if (typeof rd.difficulty_score === "number") {
        signals.push(`难度 ${(rd.difficulty_score * 100).toFixed(0)}%`);
      }
      if (typeof rd.hera_hit_rate === "number") {
        signals.push(`HERA ${(rd.hera_hit_rate * 100).toFixed(0)}%`);
      }
      if (typeof rd.recent_failure_rate === "number" && rd.recent_failure_rate > 0) {
        signals.push(`失败率 ${(rd.recent_failure_rate * 100).toFixed(0)}%`);
      }
      const metaStr = signals.length > 0 ? `${stepsMeta} · ${signals.join(" · ")}` : stepsMeta;
      emitActivity(opts.handlers, {
        kind: "plan",
        title,
        meta: metaStr,
        status: "done",
        detail: JSON.stringify(rd),
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "reflection_to_skill" && content && typeof content === "object") {
      // Spec 7+ 四维闭环: VMAO 反思已写入 HERA 失败技能库
      // 让用户看到"反思经验已沉淀, 下次类似任务会召回"
      const rs = content as {
        saved?: boolean;
        round?: number;
        library_total?: number;
      };
      const round = rs.round ?? 0;
      const total = rs.library_total ?? 0;
      const title = `四维闭环 · VMAO 反思已入 HERA · 第 ${round} 轮 · 库存 ${total}`;
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: "done",
        title,
        meta: "reflection→HERA",
        status: "done",
        detail: JSON.stringify(rs),
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "critic_verdict" && content && typeof content === "object") {
      // Spec 5 独立 Critic Agent: 任务产物语义审查结论
      // 让用户看到"独立第三方审查者"对产物的结构化评价
      const cv = content as {
        passed?: boolean;
        score?: number;
        issues?: string[];
        suggestions?: string[];
      };
      const passed = cv.passed !== false;
      const score = typeof cv.score === "number" ? cv.score : 0.5;
      const scorePct = (score * 100).toFixed(0);
      const issuesCount = (cv.issues || []).length;
      const title = passed
        ? `Critic 审查通过 · score ${scorePct}%`
        : `Critic 审查未通过 · score ${scorePct}% · ${issuesCount} 个问题`;
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: passed ? "done" : "think",
        title,
        meta: passed ? "passed" : `issues:${issuesCount}`,
        status: passed ? "done" : "running",
        detail: JSON.stringify(cv),
        endedAt: passed ? Date.now() : undefined,
      });
      return;
    }
    if (chunk === "guardrail" && content && typeof content === "object") {
      // 史诗级优化: Artifact Guardrail + Reflexion 修复循环
      // 让用户看到"产物校验 + 自动修复"的过程, 提升信任度
      const gr = content as {
        passed?: boolean;
        summary?: string;
        missing?: string[];
        issues?: string[][];
        validation_count?: number;
        repair_attempt?: boolean;
        artifacts_after?: number;
      };
      const passed = gr.passed !== false;
      const isRepair = gr.repair_attempt === true;
      const missingCount = (gr.missing || []).length;
      const issuesCount = (gr.issues || []).reduce((acc, arr) => acc + (arr?.length || 0), 0);
      const title = isRepair
        ? (passed
            ? `Reflexion 修复成功 · ${gr.artifacts_after || 0} 个产物已落盘`
            : `Reflexion 修复后仍不通过 · ${missingCount} 缺失 / ${issuesCount} 问题`)
        : (passed
            ? `Guardrail 通过 · ${gr.validation_count || 0} 个产物合规`
            : `Guardrail 未通过 · ${missingCount} 缺失 / ${issuesCount} 问题`);
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: isRepair ? "think" : (passed ? "done" : "think"),
        title,
        meta: passed ? "passed" : `missing:${missingCount}`,
        status: passed ? "done" : "running",
        detail: JSON.stringify(gr),
        endedAt: passed ? Date.now() : undefined,
      });
      return;
    }
    if (chunk === "reflection" && content && typeof content === "object") {
      // Spec 6 VMAO: Reflexion 自反思 — 显示反思内容（借鉴 noahshinn/reflexion）
      const rf = content as {
        round?: number;
        reason?: string;
        reflection?: string;
        previous_failures?: { name: string; error: string; step?: number }[];
      };
      const round = rf.round || 1;
      const reason = rf.reason || "工具失败";
      const reflection = (rf.reflection || "").slice(0, 200);
      const title = `VMAO 反思 · 第 ${round} 轮 · ${reason}`;
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: "think",
        title,
        meta: `R${round}`,
        status: "running",
        detail: JSON.stringify(rf),
      });
      // 反思完成后立即标记 done
      emitActivity(opts.handlers, {
        id: `reflect-done-${round}`,
        kind: "think",
        title: `反思完成 · 第 ${round} 轮`,
        status: "done",
        detail: reflection,
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "skill_retrieved" && content && typeof content === "object") {
      // Spec 6 HERA: 技能库召回 — 显示召回的历史成功技能
      const sr = content as {
        skills?: { task_signature: string; solution_summary: string; usage_count: number; workspace_kind: string }[];
        total_in_library?: number;
      };
      const count = (sr.skills || []).length;
      const total = sr.total_in_library || 0;
      const title = count > 0
        ? `HERA 召回 · ${count} 个历史技能 · 库存 ${total}`
        : `HERA 技能库 · 库存 ${total}`;
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: "plan",
        title,
        meta: count > 0 ? `+${count}` : undefined,
        status: "done",
        detail: JSON.stringify(sr),
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "skill_saved" && content && typeof content === "object") {
      // Spec 6 HERA: 技能已固化 — 任务成功后自动捕获
      const ss = content as {
        skill_id?: string;
        task_signature?: string;
        saved?: boolean;
        library_total?: number;
      };
      const title = `HERA 固化 · 技能已保存 · 库存 ${ss.library_total || 0}`;
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: "done",
        title,
        meta: "skill",
        status: "done",
        detail: JSON.stringify(ss),
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "fewshot_retrieved" && content && typeof content === "object") {
      // Spec 6 Self-Optimizing: few-shot 示例召回（DSPy BootstrapFewShot 风格）
      const fr = content as {
        examples?: { task_signature: string; score: number; usage_count: number; workspace_kind: string; tool_sequence?: string[] }[];
        total_in_library?: number;
      };
      const count = (fr.examples || []).length;
      const total = fr.total_in_library || 0;
      const title = count > 0
        ? `Self-Optimizing 召回 · ${count} 个 few-shot 示例 · 库存 ${total}`
        : `Self-Optimizing 库 · 库存 ${total}`;
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: "plan",
        title,
        meta: count > 0 ? `+${count}` : undefined,
        status: "done",
        detail: JSON.stringify(fr),
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "fewshot_saved" && content && typeof content === "object") {
      // Spec 6 Self-Optimizing: 离线轨迹沉淀 — 成功轨迹已存为 few-shot 示例
      const fs = content as {
        example_id?: string;
        task_signature?: string;
        score?: number;
        saved?: boolean;
        library_total?: number;
      };
      const scoreStr = typeof fs.score === "number" ? ` · score ${fs.score.toFixed(2)}` : "";
      const title = `Self-Optimizing 沉淀 · 示例已保存${scoreStr} · 库存 ${fs.library_total || 0}`;
      opts.handlers.onStatus?.(title);
      emitActivity(opts.handlers, {
        kind: "done",
        title,
        meta: "fewshot",
        status: "done",
        detail: JSON.stringify(fs),
        endedAt: Date.now(),
      });
      return;
    }
    if (chunk === "done") {
      sawDone = true;
      // Only use done.result when no text chunks arrived (avoid duplicating the reply)
      if (!sawText && content && typeof content === "object") {
        const result = (content as { result?: unknown }).result;
        if (typeof result === "string" && result.trim()) {
          opts.handlers.onText?.(result);
        }
        const arts = (content as { artifacts?: unknown }).artifacts;
        if (Array.isArray(arts)) {
          for (const a of arts) {
            if (a && typeof a === "object" && (a as { path?: string }).path) {
              const art = a as { path: string; name?: string };
              opts.handlers.onArtifact?.({ path: art.path, name: art.name });
            }
          }
        }
      }
      opts.handlers.onDone?.(content);
    }
  });
    if (!sawDone) opts.handlers.onDone?.(null);
  } finally {
    guard.dispose();
  }
}

/** Codex mode — coding agent (preview/dry-run by default). */
export async function streamCodex(opts: {
  messages: { role: string; content: string }[];
  workspace: string;
  sessionId?: string;
  llm: FnixLlm;
  preview?: boolean;
  attachments?: ChatAttachment[];
  signal?: AbortSignal;
  handlers: StreamHandlers;
}): Promise<void> {
  const base = getFnixApiBase();
  const guard = createStreamGuard(opts.signal, () => {
    opts.handlers.onError?.("连接超时：流式输出超过 5 分钟无数据，请检查 agentd 或后端。");
  });
  try {
    const res = await fetch(`${base}/api/v1/chat/agent`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        messages: opts.messages,
        workspace: opts.workspace,
        session_id: opts.sessionId || undefined,
        preview: opts.preview !== false,
        llm: opts.llm,
        attachments: opts.attachments || undefined,
      }),
      signal: guard.signal,
    });

    if (!res.ok) {
      const err = await res.text().catch(() => "");
      throw new Error(err || `Codex agent failed (${res.status})`);
    }

    let sawDone = false;
    await readNdjsonStream(res, guard.signal, (obj) => {
      guard.touch();
      // 结构化 block 流：每个 NDJSON 事件都尝试转为 StructuredBlock 注入消息气泡
      emitStructuredBlock(opts.handlers, obj);
      const t = String(obj.type || "");
    if (t === "thinking") {
      const label = String(obj.content || "Thinking…").slice(0, 120);
      opts.handlers.onStatus?.(label);
      emitActivity(opts.handlers, {
        kind: "think",
        title: label,
        status: "running",
      });
      return;
    }
    if (t === "plan") {
      opts.handlers.onStatus?.("Planning…");
      emitActivity(opts.handlers, {
        kind: "plan",
        title: "Planning…",
        status: "running",
      });
      return;
    }
    if (t === "step_start") {
      const step = obj.step as { id?: unknown; step_id?: unknown; description?: string; name?: string } | undefined;
      const label = step?.description || step?.name || "执行操作";
      const stepId = String(step?.id || step?.step_id || obj.step_id || obj.id || "");
      opts.handlers.onStatus?.(label);
      emitActivity(opts.handlers, {
        ...(stepId ? { id: `step-${stepId}` } : {}),
        kind: "tool",
        title: label,
        meta: step?.name,
        status: "running",
      });
      return;
    }
    if (t === "step_end") {
      const step = obj.step as { id?: unknown; step_id?: unknown; description?: string; name?: string } | undefined;
      const stepId = String(step?.id || step?.step_id || obj.step_id || obj.id || "");
      const label = step?.description || step?.name || "操作完成";
      opts.handlers.onStatus?.(label);
      emitActivity(opts.handlers, {
        ...(stepId ? { id: `step-${stepId}` } : {}),
        kind: "tool",
        title: label,
        meta: step?.name,
        status: "done",
        endedAt: Date.now(),
      });
      return;
    }
    if (t === "file_change") {
      const fc: CodexFileChange = {
        path: String(obj.path || ""),
        action: obj.action ? String(obj.action) : undefined,
        diff: obj.diff ? String(obj.diff) : undefined,
        content: obj.content != null ? String(obj.content) : undefined,
        old_content: obj.old_content != null ? String(obj.old_content) : undefined,
        preview: obj.preview !== false,
      };
      opts.handlers.onFileChange?.(fc);
      const path = fc.path || "file";
      const action = (fc.action || "edit").toLowerCase();
      const kind =
        action.includes("read") || action === "read"
          ? "read"
          : action.includes("write") || action === "create"
            ? "write"
            : "edit";
      emitActivity(opts.handlers, {
        kind,
        title: kind === "read" ? `读取 ${path}` : kind === "write" ? `写入 ${path}` : `修改 ${path}`,
        path,
        meta: fc.action,
        status: "done",
        detail: fc.diff?.slice(0, 800),
        endedAt: Date.now(),
      });
      // 删除 onText 重复 emit：上方 emitStructuredBlock 已 emit DiffBlock 到 blocks 数组，
      // MessageBubble 在 blocks 存在时优先渲染 blocks，此 onText 累积的 markdown diff 代码块
      // 不会被显示，但会污染 assistantMsg.content（blocks 渲染失败回退时用户看到重复 diff）
      return;
    }
    if (t === "message") {
      const c = String(obj.content || "");
      if (c) opts.handlers.onText?.(c);
      return;
    }
    if (t === "done") {
      sawDone = true;
      if (obj.error) {
        opts.handlers.onError?.(String(obj.error));
      }
      opts.handlers.onDone?.(obj);
      return;
    }
    if (t === "error") {
      opts.handlers.onError?.(String(obj.content || obj.error || "error"));
    }
  });
    if (!sawDone) opts.handlers.onDone?.(null);
  } finally {
    guard.dispose();
  }
}

/** 应用预览变更到工作区. */
export async function applyCodexChanges(opts: {
  workspace: string;
  changes: CodexFileChange[];
}): Promise<{
  ok: boolean;
  applied: number;
  error?: string;
  changeset_id?: string;
  conflict?: boolean;
  failed_file?: string;
}> {
  const workspace = (opts.workspace || "").trim();
  if (!workspace) {
    return { ok: false, applied: 0, error: "需要先打开仓库" };
  }
  const payload = opts.changes
    .filter((c) => c.path?.trim())
    .map((c) => ({
      path: c.path,
      action: (c.action || "modify").toLowerCase(),
      content: c.content ?? undefined,
      old_content: c.old_content ?? undefined,
    }));
  if (payload.length === 0) {
    return { ok: true, applied: 0 };
  }

  const res = await fetch(`${getFnixApiBase()}/api/v1/chat/agent/apply`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ workspace, changes: payload }),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    return { ok: false, applied: 0, error: err || `Apply failed (${res.status})` };
  }
  const data = (await res.json()) as {
    ok?: boolean;
    applied?: number;
    error?: string;
    changeset_id?: string;
    conflict?: boolean;
    failed_file?: string;
  };
  const err = data.error || undefined;
  const conflict =
    Boolean(data.conflict) ||
    Boolean(
      err &&
        (/冲突|并发编辑|内容已变更|conflict/i.test(err) ||
          /文件已存在/.test(err)),
    );
  return {
    ok: Boolean(data.ok),
    applied: data.applied ?? 0,
    error: err,
    changeset_id: data.changeset_id,
    conflict,
    failed_file: data.failed_file || undefined,
  };
}

/** Undo a previously accepted changeset (or the latest journaled one). */
export async function rollbackCodexChanges(opts: {
  workspace: string;
  changeset_id?: string | null;
}): Promise<{ ok: boolean; error?: string; changeset_id?: string }> {
  const workspace = (opts.workspace || "").trim();
  if (!workspace) {
    return { ok: false, error: "需要先打开仓库" };
  }
  const res = await fetch(`${getFnixApiBase()}/api/v1/chat/agent/rollback`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      workspace,
      changeset_id: opts.changeset_id || undefined,
    }),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    return { ok: false, error: err || `Rollback failed (${res.status})` };
  }
  const data = (await res.json()) as {
    ok?: boolean;
    error?: string;
    changeset_id?: string;
    detail?: string;
  };
  return {
    ok: Boolean(data.ok ?? true),
    error: data.error || data.detail || undefined,
    changeset_id: data.changeset_id || opts.changeset_id || undefined,
  };
}

export async function indexHarnessWorkspace(workspace: string): Promise<boolean> {
  const path = (workspace || "").trim();
  if (!path) return false;
  try {
    const res = await fetch(`${getFnixApiBase()}/api/v1/harness/index`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: path }),
      signal: AbortSignal.timeout(60_000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ============================================================
// P0 多任务并行可视化 — Jobs API
// 对应后端 /api/v1/work/jobs 系列端点
// ============================================================

/** Job step 进度项（对应后端 _PIPELINE_STEPS） */
type WorkJobStep = {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  ts: string;
};

/** Work Job（扩展自 WorkSession，增加并行可视化字段） */
export type WorkJob = {
  id: string;
  user_id: string;
  workspace: string;
  title: string;
  description: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  trace_id: string;
  result: string;
  artifacts: { path: string; name?: string }[];
  mission: Record<string, unknown>;
  mode: string;
  progress: number;
  steps: WorkJobStep[];
  priority: number;
  error: string;
  parent_run_id: string;
  created_at: string;
  updated_at: string;
};

/** 多任务聚合统计 */
export type WorkJobStats = {
  pending: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
  total: number;
  active: number;
};

/** 后台 job 事件（NDJSON 单行） */
export type WorkJobEvent = {
  type: string;
  data: unknown;
};

type ListJobsOptions = {
  workspace?: string;
  status?: WorkJob["status"];
  limit?: number;
};

/** 列出所有 jobs（含排队/运行/完成/失败/取消） */
export async function listJobs(opts: ListJobsOptions = {}): Promise<WorkJob[]> {
  const params = new URLSearchParams();
  if (opts.workspace) params.set("workspace", opts.workspace);
  if (opts.status) params.set("status", opts.status);
  params.set("limit", String(opts.limit ?? 50));
  const url = `${getFnixApiBase()}/api/v1/work/jobs?${params.toString()}`;
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) return [];
  const data = (await res.json()) as { jobs?: WorkJob[] };
  return data.jobs ?? [];
}

/** 入队后台 job（不阻塞 SSE 连接） */
export async function enqueueJob(opts: {
  userInput: string;
  workspace?: string;
  sessionId?: string;
  llm?: FnixLlm | null;
  userId?: string;
  priority?: number;
}): Promise<{ ok: boolean; session_id?: string; status?: string; error?: string }> {
  const res = await fetch(`${getFnixApiBase()}/api/v1/work/jobs`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      user_input: opts.userInput,
      workspace: opts.workspace || undefined,
      session_id: opts.sessionId || undefined,
      llm: opts.llm || undefined,
      user_id: opts.userId || "desktop",
      priority: opts.priority ?? 10,
    }),
  });
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    return { ok: false, error: err || `enqueue failed (${res.status})` };
  }
  return (await res.json()) as { ok: boolean; session_id: string; status: string };
}

/** 取消 job（协作式：worker 在事件循环点检查） */
export async function cancelJob(
  sessionId: string,
): Promise<{ ok: boolean; status?: string; error?: string }> {
  const res = await fetch(
    `${getFnixApiBase()}/api/v1/work/jobs/${encodeURIComponent(sessionId)}/cancel`,
    { method: "POST", headers: authHeaders() },
  );
  if (!res.ok) {
    const err = await res.text().catch(() => "");
    return { ok: false, error: err || `cancel failed (${res.status})` };
  }
  return (await res.json()) as { ok: boolean; status: string };
}

/** 获取 job 事件尾部（重连用） */
export async function getJobEvents(
  sessionId: string,
  limit = 50,
): Promise<WorkJobEvent[]> {
  const res = await fetch(
    `${getFnixApiBase()}/api/v1/work/jobs/${encodeURIComponent(sessionId)}/events?limit=${limit}`,
    { headers: authHeaders() },
  );
  if (!res.ok) return [];
  const data = (await res.json()) as { events?: WorkJobEvent[] };
  return data.events ?? [];
}

/** 多任务聚合统计 */
export async function getJobStats(): Promise<WorkJobStats | null> {
  const res = await fetch(`${getFnixApiBase()}/api/v1/work/jobs/stats`, {
    headers: authHeaders(),
  });
  if (!res.ok) return null;
  const data = (await res.json()) as { stats?: WorkJobStats };
  return data.stats ?? null;
}

// ─── Spec 4: 长程任务恢复（resume_from_checkpoint）─────────────────────────
// 对标 LangGraph Checkpointer / 会话恢复机制 / 可恢复任务机制
// 后端端点:
//   GET  /api/v1/work/runs            — 列出所有 run（含 resumable 标志）
//   GET  /api/v1/work/runs/{run_id}   — 获取 run 详情 + checkpoint state + 最近 events
//   POST /api/v1/work/resume/{run_id} — 从 checkpoint 恢复，流式返回 NDJSON（同 stream 格式）

export type WorkRunStatus = "running" | "completed" | "failed" | "interrupted";

export interface WorkRunSummary {
  run_id: string;
  channel?: string;
  session_id?: string;
  status: WorkRunStatus;
  created_at?: number;
  updated_at?: number;
  meta?: Record<string, unknown>;
  resumable: boolean;
}

/**
 * 列出所有 run（含可恢复标志）。用于侧边栏「可恢复任务」section。
 */
export async function listRuns(opts: {
  status?: WorkRunStatus;
  channel?: "work" | "code";
  limit?: number;
} = {}): Promise<{ ok: boolean; runs: WorkRunSummary[]; count: number }> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  if (opts.channel) params.set("channel", opts.channel);
  if (opts.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  const url = `${getFnixApiBase()}/api/v1/work/runs${qs ? `?${qs}` : ""}`;
  try {
    const res = await fetch(url, { headers: authHeaders() });
    if (!res.ok) return { ok: false, runs: [], count: 0 };
    return (await res.json()) as { ok: boolean; runs: WorkRunSummary[]; count: number };
  } catch {
    return { ok: false, runs: [], count: 0 };
  }
}

/**
 * 从 checkpoint 恢复执行长程任务。流式返回 NDJSON events（格式同 streamWork）。
 *
 * 实现说明：复用 streamWork 的整套 NDJSON 流式分发逻辑（_url/_body override），
 * 避免重复 ~370 行 dispatch 代码。后端 /work/resume/{run_id} 的事件格式与
 * /work/stream 完全一致（thinking/action/observation/text/artifact/done/error）。
 */
export async function resumeRun(opts: {
  runId: string;
  signal?: AbortSignal;
  handlers: StreamHandlers;
}): Promise<void> {
  const base = getFnixApiBase();
  return streamWork({
    userInput: "",
    llm: {},
    handlers: opts.handlers,
    signal: opts.signal,
    _url: `${base}/api/v1/work/resume/${encodeURIComponent(opts.runId)}`,
    _body: {},
  });
}

/**
 * 用户反馈信号回流 (用户反馈信号机制)。
 *
 * 用户对 Agent 回复点 👍/👎, 信号写入 HERA SkillLibrary 的 user_feedback 字段,
 * 影响下次 retrieve_skills 召回权重:
 *   - up: 权重 *1.3 (用户验证过的可靠路径)
 *   - down: 权重 *0.2 (用户否定的路径, 优先避开)
 *   - none: 清除反馈
 *
 * 设计取舍: 前端传 user_input, 后端统一计算 task_hash (md5),
 * 避免前后端 hash 算法不一致 (浏览器 SubtleCrypto 不支持 MD5)。
 *
 * 失败静默降级 (不阻断 UI), 返回 { ok, updated }。
 */
export async function sendFeedback(opts: {
  userInput: string;
  feedback: "up" | "down" | "none";
  comment?: string;
  workspace?: string;
}): Promise<{ ok: boolean; updated: boolean }> {
  const url = `${getFnixApiBase()}/api/v1/work/feedback`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        feedback: opts.feedback,
        user_input: opts.userInput,
        comment: opts.comment || "",
        workspace: opts.workspace,
      }),
    });
    if (!res.ok) return { ok: false, updated: false };
    const data = (await res.json()) as { updated?: boolean };
    return { ok: true, updated: Boolean(data.updated) };
  } catch {
    return { ok: false, updated: false };
  }
}
