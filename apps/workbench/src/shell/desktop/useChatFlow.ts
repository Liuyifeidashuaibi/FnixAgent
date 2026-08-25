/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Fnix Work / Code flow via agentd (Desktop-look shell).
 * Work → /api/v1/work/stream · Code → /api/v1/chat/agent
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { AIProviderConfig } from "../../utils/providers";
import { loadDisabledSkillNames, type ChatAttachment } from "../../utils/tauri";
import type { StructuredBlock } from "../../utils/structuredBlocks";
import { appendBlock } from "../../utils/structuredBlocks";
import {
  initChatDb,
  saveChatSession,
  loadChatSessions,
  loadChatSession,
  deleteChatSession,
  type ChatSessionRecord,
} from "../../services/persistence/chatDb";
import {
  applyCodeChanges,
  indexHarnessWorkspace,
  pickFnixLlm,
  pushLlmToHarness,
  resumeRun,
  rollbackCodeChanges,
  streamCode,
  streamWork,
  type CodeFileChange,
  type EvolutionInfo,
  type RunTokenUsage,
  type WorkExecMode,
  type WorkMission,
  type WorkPipelineInfo,
} from "./fnixRuntime";
import { getFnixApiBase, listHitlPending } from "../../lib/fnixBridge";
import { useReviewStore } from "./reviewStore";
import { useRunStore } from "./runStore";
import { canApplyReview, canUndoReview } from "./shellFsm";
import type { ShellMode } from "./shellTypes";
import { assessArtifactQuality } from "./artifactMeta";
import {
  finishRunning,
  upsertActivity,
  type ActivityItem,
} from "./activityTypes";

/** 把后端返回的裸技术错误转译为用户可行动的指引文案。
 * 原文仍保留在 activity/控制台中供诊断，此处只优化面向用户的表述。
 */
export function humanizeErrorMessage(raw: string): string {
  const msg = String(raw || "");
  if (!msg) return msg;
  if (/insufficient_quota|Free quota exhausted|HTTP 40[13]/i.test(msg)) {
    return "模型配额已耗尽或鉴权失败：请在设置中更换有效模型或 Key（已自动尝试兜底模型链）。";
  }
  if (/Too Many Requests|HTTP 429/i.test(msg)) {
    return "模型服务限流中，系统已自动重试；若持续失败请稍后重试或切换模型。";
  }
  if (/任务超时|TimeoutError/i.test(msg)) {
    return "任务执行超时：可将大任务拆分，或稍后重试。";
  }
  return msg;
}

export type EvolutionRecord = {
  evolution: EvolutionInfo;
  durationMs: number;
  missionTitle: string;
  timestamp: number;
};

export type ChatRole = "user" | "assistant";
export type { ShellMode };
export type { WorkExecMode };

export interface ChatMsg {
  id: string;
  role: ChatRole;
  content: string;
  attachments?: ChatAttachment[];
  /**
   * 结构化 block 数组（AG-UI 协议对齐）。
   * 当存在时，MessageBubble 按 block 渲染；不存在时回退到 content 纯文本。
   * 追加 only（Event Sourcing），不修改已有 block。
   */
  blocks?: StructuredBlock[];
  /** UX P0-6: 创建时间（epoch ms）— 气泡角标显示 HH:mm */
  ts?: number;
  /** UX P0-1: 本轮 assistant 回复的 token 用量与耗时（气泡右下 meta 行，OpenCode 式）*/
  usage?: { total: number; cached?: number; durationMs?: number };
}

export interface ChatThread {
  id: string;
  title: string;
  updatedAt: number;
}

export interface ArtifactRef {
  path: string;
  name?: string;
  /** Epoch ms when first seen in this turn */
  createdAt?: number;
  source?: "work_stream" | "craft" | "import";
  quality?: "ready" | "check" | "unknown";
}

export type ApplyStatus = "idle" | "applying" | "applied" | "failed" | "undoing";

function mergeFileChanges(prev: CodeFileChange[], incoming: CodeFileChange[]): CodeFileChange[] {
  const map = new Map<string, CodeFileChange>();
  for (const ch of prev) {
    if (ch.path) map.set(ch.path, ch);
  }
  for (const ch of incoming) {
    if (!ch.path) continue;
    const existing = map.get(ch.path);
    if (!existing) {
      map.set(ch.path, ch);
      continue;
    }
    // P1-2: 智能合并 — content/diff/old_content 优先取非空值，避免后到的 change 丢失字段
    map.set(ch.path, {
      path: ch.path,
      action: ch.action || existing.action,
      content: ch.content ?? existing.content,  // 非空覆盖（undefined 不覆盖）
      diff: ch.diff || existing.diff,           // 非空覆盖（空字符串不覆盖）
      old_content: ch.old_content ?? existing.old_content,
      preview: ch.preview !== false,
      timestamp: ch.timestamp ?? existing.timestamp,
      runId: ch.runId ?? existing.runId,
    });
  }
  return [...map.values()];
}

function normArtifactKey(path: string): string {
  let p = path.trim().replace(/\\/g, "/").toLowerCase();
  const idx = p.indexOf(".fnix/artifacts/");
  if (idx >= 0) p = p.slice(idx);
  return p;
}

function mergeArtifacts(prev: ArtifactRef[], incoming: ArtifactRef): ArtifactRef[] {
  const stamped: ArtifactRef = {
    ...incoming,
    createdAt: incoming.createdAt ?? Date.now(),
    source: incoming.source ?? "work_stream",
    quality: incoming.quality ?? assessArtifactQuality(incoming.path),
  };
  const key = normArtifactKey(stamped.path);
  if (!key) return prev;
  const base = key.split("/").pop() || key;
  // 去掉与 incoming 等价或「被 incoming 更具体的全路径所涵盖」的旧条目：
  //   - 完全相同 key → 丢弃（稍后用 stamped 覆盖）
  //   - 旧条目是 basename、incoming 是全路径且以该 basename 结尾 → 丢弃旧条目，保留更具体的全路径
  const filtered = prev.filter((a) => {
    const k = normArtifactKey(a.path);
    if (k === key) return false;
    if (key.includes("/") && !k.includes("/") && key.endsWith("/" + k)) return false;
    return true;
  });
  // 若已有等价/更具体的条目（同 key，或旧条目是全路径、incoming 是 basename 且被其涵盖），则不重复添加
  const alreadyCovered = filtered.some((a) => {
    const k = normArtifactKey(a.path);
    return k === key || (k.includes("/") && !key.includes("/") && k.endsWith("/" + base));
  });
  if (alreadyCovered) return filtered;
  return [...filtered, stamped];
}

function parseDoneChanges(payload: unknown): CodeFileChange[] {
  if (!payload || typeof payload !== "object") return [];
  const raw = (payload as { changes?: unknown }).changes;
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (!item || typeof item !== "object") return null;
      const o = item as Record<string, unknown>;
      const path = String(o.path || "").trim();
      if (!path) return null;
      return {
        path,
        action: o.action ? String(o.action) : undefined,
        diff: o.diff ? String(o.diff) : undefined,
        content: o.content != null ? String(o.content) : undefined,
        old_content: o.old_content != null ? String(o.old_content) : undefined,
        preview: o.preview !== false,
      } satisfies CodeFileChange;
    })
    .filter(Boolean) as CodeFileChange[];
}

const FALLBACK_WORKSPACE = "__fnix_desktop__";

/** Craft + 已 Open project：仓库级改码走 CodingAgent（与 Work 同一 Chat）。 */
function looksLikeRepoCode(text: string): boolean {
  const t = text.toLowerCase();
  if (t.includes(".fnix/artifacts")) return false;
  const artifactHints = ["网站", "index.html", "mbti", "静态", "landing", "网页", "style.css", "script.js"];
  if (artifactHints.some((h) => t.includes(h))) return false;
  const repoHints = [
    "bug", "fix", "refactor", "仓库", "源码", "pytest", "接口", "模块", "函数",
    "subtract", "calc.py", "test_", "math_utils",
  ];
  if (repoHints.some((h) => t.includes(h))) return true;
  return /\.(py|ts|tsx|js|go|rs|java)\b/i.test(text);
}

function pickChatBackend(
  mode: ShellMode,
  workMode: WorkExecMode,
  workspace: string,
  userInput: string,
): "work" | "code" {
  if (mode === "code") return "code";
  if (workMode !== "craft" || workspace === FALLBACK_WORKSPACE) return "work";
  return looksLikeRepoCode(userInput) ? "code" : "work";
}

function uid(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function titleFrom(text: string) {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length <= 48 ? t || "新任务" : `${t.slice(0, 48)}…`;
}

/**
 * 创建流式输出所需的本地状态闭包。
 * send / resume 共享同一套 appendText / finalize 实现。
 *
 * 自然流式：后端 chunk 到达就立即追加到 DOM，零人为延迟。
 * LLM 的生成速度就是用户看到的显示速度——和 Cursor/ChatGPT 一样。
 * 闪烁光标在 streaming 期间显示在文字末尾，提示"还在生成"。
 */
interface StreamLocalState {
  flushStreamBuf: () => void;
  appendText: (delta: string) => void;
  appendStructuredBlock: (block: StructuredBlock) => void;
  finalize: () => void;
  cancelRaf: () => void;
}

function createStreamLocalState(
  commitMessages: (next: ChatMsg[]) => void,
  messagesRef: { current: ChatMsg[] },
  streamBufRef: { current: string },
  streamRafRef: { current: number | null },
  streamAssistantIdRef: { current: string | null },
): StreamLocalState {
  // RAF 批处理：多个 chunk 在同一帧内到达时只 commit 一次，避免高频 React re-render
  let rafId: number | null = null;

  const flushStreamBuf = () => {
    const buffered = streamBufRef.current;
    const aid = streamAssistantIdRef.current;
    streamBufRef.current = "";
    streamRafRef.current = null;
    rafId = null;
    if (!buffered || !aid) return;
    commitMessages(
      messagesRef.current.map((m) => {
        if (m.id !== aid) return m;
        // 正文开始上屏 = 思考阶段结束：把仍在 streaming 的 thinking 块收尾为
        // 「分析完成」（Trae/Cursor 行为），避免出现「转圈块 + 正文同时滚动」
        const patch: Partial<ChatMsg> = { content: m.content + buffered };
        if (m.blocks?.some((b) => b.kind === "thinking" && b.isStreaming !== false)) {
          patch.blocks = m.blocks.map((b) =>
            b.kind === "thinking" && b.isStreaming !== false
              ? { ...b, isStreaming: false, isComplete: true }
              : b,
          );
        }
        return { ...m, ...patch };
      }),
    );
  };

  const appendText = (delta: string) => {
    if (!delta) return;
    const aid = streamAssistantIdRef.current;
    if (!aid) return;
    // RAF 帧批处理：chunk 先进缓冲，下一帧统一 commit 到 React。
    // 同一帧内到达的多个 chunk 合并为一次 re-render（渲染风暴根治），
    // 文字依然 16ms 内上屏——LLM 生成速度 = 用户看到速度，无卡顿无等待。
    // 段落分隔由后端控制：在 _stream_completion_summary 开头发 \n\n，
    // _build_review_message 前由后端加 \n\n 前缀
    streamBufRef.current += delta;
    if (rafId === null) {
      rafId = requestAnimationFrame(() => flushStreamBuf());
      streamRafRef.current = rafId;
    }
  };

  const appendStructuredBlock = (block: StructuredBlock) => {
    const aid = streamAssistantIdRef.current;
    if (!aid) return;
    commitMessages(
      messagesRef.current.map((m) => {
        if (m.id !== aid) return m;
        const prevBlocks = m.blocks || [];
        return { ...m, blocks: appendBlock(prevBlocks, block) };
      }),
    );
  };

  const cancelRaf = () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    streamRafRef.current = null;
  };

  const finalize = () => {
    cancelRaf();
    flushStreamBuf();
    const aid = streamAssistantIdRef.current;
    if (aid) {
      commitMessages(
        messagesRef.current.map((m) => {
          if (m.id !== aid || !m.blocks || m.blocks.length === 0) return m;
          const finalizedBlocks = m.blocks.map((b) =>
            b.kind === "thinking" || b.kind === "progress"
              ? { ...b, isStreaming: false, isComplete: b.kind === "progress" ? true : b.isComplete }
              : b,
          );
          return { ...m, blocks: finalizedBlocks };
        }),
      );
    }
  };

  return { flushStreamBuf, appendText, appendStructuredBlock, finalize, cancelRaf };
}

/**
 * 创建统一的 stream handlers（onText/onStructuredBlock/onStatus/onArtifact/...）。
 * send / resume 的 handlers 仅 onError 行为不同：
 *   - send: 前置 "Something went wrong" 文本时跳过追加（避免重复）
 *   - resume: 始终追加
 */
function createStreamHandlers(
  opts: {
    local: StreamLocalState;
    setArtifacts: (updater: (prev: ArtifactRef[]) => ArtifactRef[]) => void;
    setMission: (m: WorkMission | null) => void;
    setPipeline: (p: WorkPipelineInfo | null) => void;
    setHealRound: (h: { current: number; max: number } | null) => void;
    setEvolution: (updater: (prev: EvolutionInfo | null) => EvolutionInfo | null) => void;
    setActivities: (updater: (prev: ActivityItem[]) => ActivityItem[]) => void;
    setFileChanges: (updater: (prev: CodeFileChange[]) => CodeFileChange[]) => void;
    setStatus: (s: string | null) => void;
    setError: (e: string | null) => void;
    setGoalTitle: (t: string) => void;
    setEvolutionHistory: (updater: (prev: EvolutionRecord[]) => EvolutionRecord[]) => void;
    evolutionRef: { current: EvolutionInfo | null };
    missionRef: { current: WorkMission | null };
    goalStartedAtRef: { current: number | null };
    runStore: { setStatus: (s: string) => void; setError: (e: string | null) => void };
    reviewStore: { setPending: (c: CodeFileChange[]) => void };
    /** UX P0-1: 本轮 usage 累加器（onDone 时读取并写入气泡） */
    lastUsageRef?: { current: RunTokenUsage | null };
    /** UX P0-1: assistant 消息 id ref（onDone 时定位气泡） */
    streamAssistantIdRef?: { current: string | null };
    commitMessages: (next: ChatMsg[]) => void;
    messagesRef: { current: ChatMsg[] };
    /** send 模式下过滤 "Something went wrong" 前缀文本，resume 不过滤 */
    suppressSomethingPrefix?: boolean;
    /** UX P0-1: 本轮 token 累计接收器（send/resume 各自持有累加器 ref） */
    onUsage?: (u: RunTokenUsage) => void;
  },
) {
  const {
    local,
    setArtifacts,
    setMission,
    setPipeline,
    setHealRound,
    setEvolution,
    setActivities,
    setFileChanges,
    setStatus,
    setError,
    setGoalTitle,
    setEvolutionHistory,
    evolutionRef,
    missionRef,
    goalStartedAtRef,
    runStore,
    reviewStore,
    suppressSomethingPrefix = false,
    lastUsageRef,
    streamAssistantIdRef: assistantIdRef,
    commitMessages,
    messagesRef,
  } = opts;

  return {
    onText: local.appendText,
    onStructuredBlock: local.appendStructuredBlock,
    // UX P0-1: done.usage → 累加器（气泡 meta 行 + Composer 会话累计的数据源）
    onUsage: (u: RunTokenUsage) => opts.onUsage?.(u),
    onStatus: (label: string) => {
      setStatus(label);
      runStore.setStatus(label);
    },
    onArtifact: (art: ArtifactRef) =>
      setArtifacts((prev) => mergeArtifacts(prev, art)),
    onMission: (m: WorkMission) => {
      setMission(m);
      if (m.title) setGoalTitle(String(m.title));
    },
    onPipeline: (p: WorkPipelineInfo) => {
      setPipeline(p);
      setHealRound(p.heal_round ?? null);
    },
    onEvolution: (e: EvolutionInfo) =>
      setEvolution((prev) => ({ ...(prev || {}), ...e })),
    onActivity: (item: ActivityItem) => {
      setActivities((prev) => upsertActivity(prev, item));
    },
    onFileChange: (fc: CodeFileChange) => {
      // BUG-8 fix: Move reviewStore.setPending outside the setFileChanges updater.
      // React 18 may invoke state updaters during render; calling zustand set()
      // inside an updater triggers a synchronous re-render of DesktopApp (which
      // subscribes to useReviewStore), producing the "Cannot update a component
      // while rendering a different component" warning.
      let merged: CodeFileChange[] = [];
      setFileChanges((prev) => {
        merged = mergeFileChanges(prev, [fc]);
        return merged;
      });
      // Defer to microtask so the zustand set() runs after React's render phase.
      Promise.resolve().then(() => reviewStore.setPending(merged));
      setStatus(`Preview: ${fc.path || "file"}`);
    },
    onError: (rawMessage: string) => {
      const message = humanizeErrorMessage(rawMessage);
      setError(message);
      // 同步 runStore.error：FnixStatusBar / 其他订阅 runStore 的组件依赖此字段显示错误，
      // 原代码仅 setError(本地) 不调 runStore.setError，导致状态栏看不到错误反馈
      runStore.setError(message);
      setActivities((prev) =>
        upsertActivity(prev, {
          id: `err-${Date.now()}`,
          kind: "error",
          title: message.slice(0, 160),
          status: "error",
          startedAt: Date.now(),
          endedAt: Date.now(),
        }),
      );
      // send 模式下后端若已写入 "Something went wrong: ..." 占位则不再追加
      const prefix = suppressSomethingPrefix && message.startsWith("Something") ? "" : `\n\n⚠️ ${message}`;
      if (prefix) local.appendText(prefix);
    },
    onDone: (payload: unknown) => {
      const doneChanges = parseDoneChanges(payload);
      if (doneChanges.length) {
        let merged: CodeFileChange[] = [];
        setFileChanges((prev) => {
          merged = mergeFileChanges(prev, doneChanges);
          return merged;
        });
        // Defer to microtask so the zustand set() runs after React's render phase.
        Promise.resolve().then(() => reviewStore.setPending(merged));
      }
      // UX P0-1: 把本轮 usage + 耗时写入 assistant 气泡 meta 行（OpenCode 式小字）
      const aid = assistantIdRef?.current;
      const u = lastUsageRef?.current;
      const startedAt = goalStartedAtRef.current;
      if (aid && u) {
        commitMessages(
          messagesRef.current.map((m) =>
            m.id === aid
              ? {
                  ...m,
                  usage: {
                    total: m.usage?.total ?? u.total_tokens,
                    cached: u.cached_tokens,
                    durationMs: startedAt ? Date.now() - startedAt : undefined,
                  },
                }
              : m,
          ),
        );
      }
      setActivities((prev) => finishRunning(prev, "done"));
      setEvolutionHistory((prev) => {
        const last = evolutionRef.current;
        if (!last) return prev;
        const dur = goalStartedAtRef.current ? Date.now() - goalStartedAtRef.current : 0;
        const rec: EvolutionRecord = {
          evolution: last,
          durationMs: dur,
          missionTitle: String(missionRef.current?.title || ""),
          timestamp: Date.now(),
        };
        return [...prev, rec].slice(-20);
      });
      setStatus(null);
      local.finalize();
    },
  };
}

export function useChatFlow(opts: {
  workspace: string;
  providers: AIProviderConfig[];
  apiKey: string;
  providerName: string;
  model: string;
  mode: ShellMode;
  /** WorkBuddy：ask | plan | craft */
  workMode?: WorkExecMode;
}) {
  const workspace = (opts.workspace || "").trim() || FALLBACK_WORKSPACE;
  const storageKey = `${workspace}::${opts.mode}`;
  const workMode = opts.workMode || "craft";
  // opts 是每次渲染新建的对象，用 ref 保持最新引用，避免作为 useCallback 依赖导致 send 每次重建
  const optsRef = useRef(opts);
  optsRef.current = opts;
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactRef[]>([]);
  const [mission, setMission] = useState<WorkMission | null>(null);
  const [pipeline, setPipeline] = useState<WorkPipelineInfo | null>(null);
  const [healRound, setHealRound] = useState<{ current: number; max: number } | null>(null);
  const [evolution, setEvolution] = useState<EvolutionInfo | null>(null);
  const [evolutionHistory, setEvolutionHistory] = useState<EvolutionRecord[]>([]);
  const [fileChanges, setFileChanges] = useState<CodeFileChange[]>([]);
  const [applyStatus, setApplyStatus] = useState<ApplyStatus>("idle");
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [lastChangesetId, setLastChangesetId] = useState<string | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [goalTitle, setGoalTitle] = useState<string>("");
  const [goalStartedAt, setGoalStartedAt] = useState<number | null>(null);
  // UX P0-1: 会话累计 token（OpenCode 式 — Composer 旁一枚小字，点击无操作纯展示）
  const [sessionUsage, setSessionUsage] = useState(0);
  const lastUsageRef = useRef<RunTokenUsage | null>(null);
  // UX P0-4: 流式期间轮询 /hitl/pending 的待审批数（>0 时 Composer 上方出现内联审批卡）
  const [pendingApprovals, setPendingApprovals] = useState<
    import('../../lib/fnixBridge').FnixHitlToolApproval[]
  >([]);
  const abortRef = useRef<AbortController | null>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  const evolutionRef = useRef<EvolutionInfo | null>(null);
  evolutionRef.current = evolution;
  const missionRef = useRef<WorkMission | null>(null);
  missionRef.current = mission;
  const goalStartedAtRef = useRef<number | null>(null);
  goalStartedAtRef.current = goalStartedAt;
  /**
   * Update messages AND keep messagesRef in sync synchronously.
   * (React does not run the setState updater immediately, so reading
   * messagesRef.current right after a plain setMessages would be stale — which
   * would make our single persist() call lose the last streamed delta.)
   */
  const commitMessages = useCallback((next: ChatMsg[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);
  const streamBufRef = useRef("");
  const streamRafRef = useRef<number | null>(null);
  const streamAssistantIdRef = useRef<string | null>(null);

  const persist = useCallback(
    async (id: string, title: string, msgs: ChatMsg[]) => {
      // UX P0-1: 持久化真实累计 token（原硬编码 0），供会话列表/统计使用
      const tokens = msgs.reduce((acc, m) => acc + (m.usage?.total || 0), 0);
      const rec: ChatSessionRecord = {
        id,
        project_path: storageKey,
        title,
        provider: opts.providerName,
        model: opts.model,
        messages: JSON.stringify(msgs),
        token_count: tokens,
        cost: 0,
        created_at: Date.now(),
        updated_at: Date.now(),
      };
      try {
        await saveChatSession(rec);
      } catch {
        /* db optional in browser */
      }
      setThreads((prev) => {
        const next = [{ id, title, updatedAt: Date.now() }, ...prev.filter((t) => t.id !== id)];
        return next.sort((a, b) => b.updatedAt - a.updatedAt);
      });
    },
    [opts.model, opts.providerName, storageKey],
  );

  useEffect(() => {
    setActiveId(null);
    setMessages([]);
    setError(null);
    setStatus(null);
    setArtifacts([]);
    setMission(null);
    setPipeline(null);
    setHealRound(null);
    setEvolution(null);
    setFileChanges([]);
    setApplyStatus("idle");
    setApplyMessage(null);
    setActivities([]);
    setGoalTitle("");
    setGoalStartedAt(null);
    // UX P0-1: 会话切换重置累计
    setSessionUsage(0);
    lastUsageRef.current = null;
    void (async () => {
      try {
        await initChatDb();
        const rows = await loadChatSessions(storageKey, 80);
        setThreads(
          rows.map((r) => ({
            id: r.id,
            title: r.title || "新任务",
            updatedAt: r.updated_at,
          })),
        );
        // 自动恢复最近一条会话（仅当有真实 workspace 时）
        if (rows.length > 0 && workspace !== FALLBACK_WORKSPACE) {
          try {
            const last = rows[0]!;
            const row = await loadChatSession(last.id, storageKey);
            if (row) {
              const parsed = JSON.parse(row.messages || "[]") as ChatMsg[];
              setActiveId(last.id);
              setMessages(Array.isArray(parsed) ? parsed : []);
            }
          } catch {
            /* 静默：恢复失败不阻塞 UI */
          }
        }
      } catch {
        setThreads([]);
      }
    })();
  }, [storageKey, workspace]);

  // Cleanup on unmount — abort active stream and cancel RAF to prevent leaks
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (streamRafRef.current !== null) {
        cancelAnimationFrame(streamRafRef.current);
        streamRafRef.current = null;
      }
    };
  }, []);

  // UX P0-4: HITL 内联审批 — 流式期间轮询待审批队列（OpenCode 式：权限请求在最需要的位置出现）。
  // 仅流式时轮询（3s），空闲时不产生任何请求；失败静默降级为无审批卡。
  useEffect(() => {
    if (!streaming) return;
    let alive = true;
    const poll = () => {
      listHitlPending()
        .then((res) => {
          if (alive) setPendingApprovals(res.pending?.tool_approvals || []);
        })
        .catch(() => {
          /* 后端离线/旧版本无此接口 — 静默 */
        });
    };
    poll();
    const id = window.setInterval(poll, 3000);
    return () => {
      alive = false;
      window.clearInterval(id);
      // 流式结束后清空审批卡（异步回调内 setState，不触发级联渲染警告）
      window.setTimeout(() => setPendingApprovals([]), 0);
    };
  }, [streaming]);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setStreaming(false);
    setError(null);
    setStatus(null);
    setArtifacts([]);
    setMission(null);
    setPipeline(null);
    setHealRound(null);
    setEvolution(null);
    setFileChanges([]);
    setApplyStatus("idle");
    setApplyMessage(null);
    setActivities([]);
    setGoalTitle("");
    setGoalStartedAt(null);
    // UX P0-1: 新会话清零累计
    setSessionUsage(0);
    lastUsageRef.current = null;
    setActiveId(null);
    setMessages([]);
  }, []);

  const openThread = useCallback(
    async (id: string) => {
      abortRef.current?.abort();
      setStreaming(false);
      setError(null);
      setStatus(null);
      setArtifacts([]);
      setMission(null);
      setPipeline(null);
      setHealRound(null);
      setEvolution(null);
      setFileChanges([]);
      setApplyStatus("idle");
      setApplyMessage(null);
      setActivities([]);
      setGoalTitle("");
      setGoalStartedAt(null);
      setActiveId(id);
      try {
        const row = await loadChatSession(id, storageKey);
        if (!row) {
          setMessages([]);
          return;
        }
        const parsed = JSON.parse(row.messages || "[]") as ChatMsg[];
        setMessages(Array.isArray(parsed) ? parsed : []);
      } catch {
        setMessages([]);
      }
    },
    [storageKey],
  );

  const deleteThread = useCallback(
    async (id: string) => {
      try {
        await deleteChatSession(id, storageKey);
      } catch {
        /* ignore */
      }
      setThreads((prev) => prev.filter((t) => t.id !== id));
      if (activeId === id) newChat();
    },
    [activeId, newChat, storageKey],
  );

  const renameThread = useCallback(
    async (id: string, title: string) => {
      const next = title.replace(/\s+/g, " ").trim() || "新任务";
      setThreads((prev) =>
        prev.map((t) => (t.id === id ? { ...t, title: next, updatedAt: Date.now() } : t)),
      );
      try {
        const row = await loadChatSession(id, storageKey);
        if (row) {
          await saveChatSession({
            ...row,
            title: next,
            updated_at: Date.now(),
          });
          return;
        }
        if (activeId === id && messagesRef.current.length) {
          await persist(id, next, messagesRef.current);
        }
      } catch {
        /* browser / db optional */
      }
    },
    [activeId, persist, storageKey],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    useRunStore.getState().requestStop();
    setStreaming(false);
    setStatus(null);
    setActivities((prev) => finishRunning(prev, "cancelled"));
    useRunStore.getState().finish(false);
  }, []);

  const send = useCallback(
    async (text: string, attachments?: ChatAttachment[]) => {
      const trimmed = text.trim();
      if ((!trimmed && (!attachments || attachments.length === 0)) || streaming) return;
      const runPhase = useRunStore.getState().phase;
      if (runPhase === "streaming" || runPhase === "stopping") return;

      const llm = pickFnixLlm(optsRef.current.providers, optsRef.current.apiKey, optsRef.current.providerName, optsRef.current.model);
      if (!llm?.api_key && llm?.provider !== "ollama") {
        setError("请先在「设置」中配置 API Key（BYOK），再发送。");
        return;
      }

      if (optsRef.current.mode === "code" && workspace === FALLBACK_WORKSPACE) {
        setError("请先在左侧打开一个仓库，再发送代码修改任务。");
        return;
      }

      const backend = pickChatBackend(optsRef.current.mode, workMode, workspace, trimmed);
      if (backend === "code" && workspace === FALLBACK_WORKSPACE) {
        setError("请先在左侧打开一个仓库，再执行代码修改。");
        return;
      }

      setError(null);
      setStatus("正在连接…");
      useRunStore.getState().start("正在连接…");
      setArtifacts([]);
      setMission(null);
      setPipeline(null);
      setHealRound(null);
      setEvolution(null);
      setFileChanges([]);
      setApplyStatus("idle");
      setApplyMessage(null);
      useReviewStore.getState().clearPending();
      setActivities([]);
      setGoalTitle(titleFrom(trimmed));
      setGoalStartedAt(Date.now());

      let threadId = activeId;
      if (!threadId) {
        threadId = uid("chat");
        setActiveId(threadId);
      }

      const userMsg: ChatMsg = {
        id: uid("u"),
        role: "user",
        content: trimmed,
        ts: Date.now(),
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
      };
      const assistantId = uid("a");
      // P0-4: 发送后立即在 assistant 消息中插入 thinking 占位 block
      // 让用户马上看到"正在思考"的反馈，而非空白等待
      const initialBlock: StructuredBlock = {
        kind: "thinking",
        content: "正在分析你的需求…",
        isStreaming: true,
        isComplete: false,
      };
      const assistantMsg: ChatMsg = {
        id: assistantId,
        role: "assistant",
        content: "",
        ts: Date.now(),
        blocks: [initialBlock],
      };
      // UX P0-1: 每轮重置 usage 累加器
      lastUsageRef.current = null;
      const nextMsgs = [...messagesRef.current, userMsg, assistantMsg];
      commitMessages(nextMsgs);
      const title = titleFrom(trimmed);
      void persist(threadId, title, nextMsgs);

      const ac = new AbortController();
      abortRef.current = ac;
      setStreaming(true);
      streamBufRef.current = "";
      streamAssistantIdRef.current = assistantId;
      if (streamRafRef.current !== null) {
        cancelAnimationFrame(streamRafRef.current);
        streamRafRef.current = null;
      }

      // 共享流式本地状态 + handlers（与 resume 同源，避免重复实现）
      const local = createStreamLocalState(
        commitMessages,
        messagesRef,
        streamBufRef,
        streamRafRef,
        streamAssistantIdRef,
      );
      const handlers = createStreamHandlers({
        local,
        setArtifacts,
        setMission,
        setPipeline,
        setHealRound,
        setEvolution,
        setActivities,
        setFileChanges,
        setStatus,
        setError,
        setGoalTitle,
        setEvolutionHistory,
        evolutionRef,
        missionRef,
        goalStartedAtRef,
        runStore: useRunStore.getState(),
        reviewStore: useReviewStore.getState(),
        // UX P0-1: 累加器 + 气泡定位（onDone 写入 meta 行）
        lastUsageRef,
        streamAssistantIdRef,
        commitMessages,
        messagesRef,
        // send 模式：后端可能已写入 "Something went wrong: ..." 占位，跳过追加避免重复
        suppressSomethingPrefix: true,
        onUsage: (u) => {
          const prev = lastUsageRef.current;
          lastUsageRef.current = prev
            ? {
                total_tokens: prev.total_tokens + u.total_tokens,
                prompt_tokens: prev.prompt_tokens + u.prompt_tokens,
                completion_tokens: prev.completion_tokens + u.completion_tokens,
                cached_tokens: prev.cached_tokens + u.cached_tokens,
              }
            : u;
          // Reflexion 多轮会多次 done → 全部累加进会话总量
          setSessionUsage((n) => n + u.total_tokens);
        },
      });

      try {
        void pushLlmToHarness(llm);
        if (workspace !== FALLBACK_WORKSPACE) {
          void indexHarnessWorkspace(workspace);
        }

        if (backend === "work") {
          // 前端技能开关 → 后端 builtin skills 注入过滤（失败时不阻塞发送）
          const disabledSkills = await loadDisabledSkillNames().catch(() => []);
          await streamWork({
            userInput: trimmed,
            workspace: workspace === FALLBACK_WORKSPACE ? undefined : workspace,
            sessionId: threadId,
            workMode,
            llm,
            attachments: attachments && attachments.length > 0 ? attachments : undefined,
            disabledSkills,
            signal: ac.signal,
            handlers,
          });
        } else {
          const history = nextMsgs
            .filter((m) => m.id !== assistantId)
            .map((m) => ({ role: m.role, content: m.content }));
          await streamCode({
            messages: history,
            workspace,
            sessionId: threadId,
            llm,
            preview: true,
            attachments: attachments && attachments.length > 0 ? attachments : undefined,
            signal: ac.signal,
            handlers,
          });
        }

        // If stream finished with empty assistant AND no structured blocks, leave a hint.
        // When blocks exist (thinking/diff/progress etc.), the assistant "spoke" through
        // structured content — not a text-only failure.
        const cur = messagesRef.current.find((m) => m.id === assistantId);
        if (cur && !cur.content.trim() && !(cur.blocks && cur.blocks.length > 0) && !ac.signal.aborted) {
          commitMessages(
            messagesRef.current.map((m) =>
              m.id === assistantId ? { ...m, content: "（无文本输出 — 请检查模型与 agentd 日志）" } : m,
            ),
          );
        }
      } catch (e) {
        if ((e as Error)?.name !== "AbortError") {
          let msg = String((e as Error)?.message || e);
          if (/failed to fetch|networkerror|load failed/i.test(msg)) {
            msg =
              `无法连接 agentd（${getFnixApiBase()}）。请确认 Settings 为 Ready，或重启桌面端后再试。原错误: ${msg}`;
          }
          setError(msg);
          useRunStore.getState().setError(msg);
          commitMessages(
            messagesRef.current.map((m) =>
              m.id === assistantId ? { ...m, content: m.content || `Something went wrong: ${msg}` } : m,
            ),
          );
        }
      } finally {
        local.cancelRaf();
        local.flushStreamBuf();
        const aborted = ac.signal.aborted;
        setStreaming(false);
        setStatus(null);
        useRunStore.getState().reset();
        setActivities((prev) => finishRunning(prev, aborted ? "cancelled" : "done"));
        abortRef.current = null;
        streamAssistantIdRef.current = null;
        // Persist exactly once (covers success, abort, and error paths).
        void persist(threadId!, title, messagesRef.current);
      }
    },
    [activeId, persist, streaming, workMode, workspace, commitMessages],
  );

  /**
   * Spec 4: 从 checkpoint 恢复长程任务。
   *
   * 会话恢复机制 / 可恢复任务机制 recover。
   * 不需要 user_input — 后端从 checkpoint 重建 LLM 上下文后继续执行。
   *
   * UX:
   *   - 创建新 thread（标题 "恢复: <run_id 截短>"），保留原 thread 不动
   *   - 添加 system note 告知用户这是恢复的任务
   *   - 流式接收 thinking/action/observation/text，与 send 完全一致
   */
  const resume = useCallback(
    async (runId: string) => {
      if (streaming) return;
      const runPhase = useRunStore.getState().phase;
      if (runPhase === "streaming" || runPhase === "stopping") return;

      setError(null);
      setStatus("恢复任务中…");
      useRunStore.getState().start("恢复任务中…");
      setArtifacts([]);
      setMission(null);
      setPipeline(null);
      setHealRound(null);
      setEvolution(null);
      setFileChanges([]);
      setApplyStatus("idle");
      setApplyMessage(null);
      useReviewStore.getState().clearPending();
      setActivities([]);
      setGoalTitle(`恢复: ${runId.slice(0, 8)}`);
      setGoalStartedAt(Date.now());

      // 新建 thread 用于恢复任务（不污染原 thread）
      const threadId = uid("chat");
      setActiveId(threadId);
      const shortId = runId.slice(0, 8);
      const assistantId = uid("a");
      const assistantMsg: ChatMsg = {
        id: assistantId,
        role: "assistant",
        content: `▸ 从 checkpoint 恢复任务 ${shortId}…\n\n`,
        ts: Date.now(),
      };
      const systemNote: ChatMsg = {
        id: uid("s"),
        role: "user",
        content: `(系统：恢复中断的任务 ${shortId}，无需重新输入)`,
        ts: Date.now(),
      };
      const nextMsgs = [systemNote, assistantMsg];
      commitMessages(nextMsgs);
      const title = `恢复: ${shortId}`;
      void persist(threadId, title, nextMsgs);
      // UX P0-1: 每轮重置 usage 累加器
      lastUsageRef.current = null;

      const ac = new AbortController();
      abortRef.current = ac;
      setStreaming(true);
      streamBufRef.current = "";
      streamAssistantIdRef.current = assistantId;
      if (streamRafRef.current !== null) {
        cancelAnimationFrame(streamRafRef.current);
        streamRafRef.current = null;
      }

      // 共享流式本地状态 + handlers（与 send 同源，避免重复实现）
      const local = createStreamLocalState(
        commitMessages,
        messagesRef,
        streamBufRef,
        streamRafRef,
        streamAssistantIdRef,
      );
      const handlers = createStreamHandlers({
        local,
        setArtifacts,
        setMission,
        setPipeline,
        setHealRound,
        setEvolution,
        setActivities,
        setFileChanges,
        setStatus,
        setError,
        setGoalTitle,
        setEvolutionHistory,
        evolutionRef,
        missionRef,
        goalStartedAtRef,
        runStore: useRunStore.getState(),
        reviewStore: useReviewStore.getState(),
        // UX P0-1: 累加器 + 气泡定位（onDone 写入 meta 行）
        lastUsageRef,
        streamAssistantIdRef,
        commitMessages,
        messagesRef,
        // resume 模式：不重复追加 ⚠️ 错误提示（后端未写入 "Something went wrong" 占位）
        suppressSomethingPrefix: false,
        onUsage: (u) => {
          const prev = lastUsageRef.current;
          lastUsageRef.current = prev
            ? {
                total_tokens: prev.total_tokens + u.total_tokens,
                prompt_tokens: prev.prompt_tokens + u.prompt_tokens,
                completion_tokens: prev.completion_tokens + u.completion_tokens,
                cached_tokens: prev.cached_tokens + u.cached_tokens,
              }
            : u;
          setSessionUsage((n) => n + u.total_tokens);
        },
      });

      try {
        await resumeRun({ runId, signal: ac.signal, handlers });

        // If stream finished with empty assistant, leave a hint
        const cur = messagesRef.current.find((m) => m.id === assistantId);
        if (cur && !cur.content.trim() && !ac.signal.aborted) {
          commitMessages(
            messagesRef.current.map((m) =>
              m.id === assistantId ? { ...m, content: "（恢复失败 — 请检查 agentd 日志或 run_id 是否存在）" } : m,
            ),
          );
        }
      } catch (e) {
        if ((e as Error)?.name !== "AbortError") {
          let msg = String((e as Error)?.message || e);
          if (/failed to fetch|networkError|load failed/i.test(msg)) {
            msg = `无法连接 agentd（${getFnixApiBase()}）。原错误: ${msg}`;
          }
          setError(msg);
          useRunStore.getState().setError(msg);
          commitMessages(
            messagesRef.current.map((m) =>
              m.id === assistantId ? { ...m, content: m.content || `恢复失败: ${msg}` } : m,
            ),
          );
        }
      } finally {
        local.cancelRaf();
        local.flushStreamBuf();
        const aborted = ac.signal.aborted;
        setStreaming(false);
        setStatus(null);
        useRunStore.getState().reset();
        setActivities((prev) => finishRunning(prev, aborted ? "cancelled" : "done"));
        abortRef.current = null;
        streamAssistantIdRef.current = null;
        void persist(threadId, title, messagesRef.current);
      }
    },
    [streaming, persist, commitMessages],
  );

  const regenerate = useCallback(async () => {
    if (streaming) return;
    const msgs = messagesRef.current;
    let end = msgs.length;
    while (end > 0 && msgs[end - 1]?.role === "assistant") end -= 1;
    if (end === 0 || msgs[end - 1]?.role !== "user") return;
    const lastUser = msgs[end - 1]!.content;
    const kept = msgs.slice(0, end - 1);
    commitMessages(kept);
    await send(lastUser);
  }, [send, streaming, commitMessages]);

  const clearFileChanges = useCallback((feedback?: string) => {
    setFileChanges([]);
    setApplyStatus("idle");
    // 支持传入反馈文案：原代码恒为 null，用户点"拒绝"后无任何提示，
    // 误以为没点中。传入 feedback 时显示在 ReviewPane 顶部 note
    setApplyMessage(feedback ?? null);
    useReviewStore.getState().clearPending();
  }, []);

  const clearGoal = useCallback(() => {
    setActivities([]);
    setGoalTitle("");
    setGoalStartedAt(null);
    setStatus(null);
  }, []);

  const applyFileChanges = useCallback(
    async (paths?: string[], overrides?: CodeFileChange[]) => {
      if (workspace === FALLBACK_WORKSPACE) {
        setError("请先 Open project，再 Accept 变更。");
        return;
      }
      const review = useReviewStore.getState();
      const run = useRunStore.getState();
      if (
        !canApplyReview({
          runPhase: run.phase,
          applyStatus: review.applyStatus,
          streaming,
        })
      ) {
        setApplyMessage("流式输出或 Apply 进行中，请稍后再 Accept。");
        return;
      }
      const selected =
        overrides && overrides.length
          ? overrides
          : paths && paths.length
            ? fileChanges.filter((c) => paths.includes(c.path))
            : fileChanges;
      if (selected.length === 0) {
        setApplyMessage("没有待应用的变更。");
        return;
      }
      setApplyStatus("applying");
      setApplyMessage(null);
      setError(null);
      useReviewStore.getState().setApplyStatus("applying");
      try {
        const result = await applyCodeChanges({ workspace, changes: selected });
        if (!result.ok) {
          const raw = result.error || "写盘失败";
          const conflict = Boolean(result.conflict);
          const fileHint = result.failed_file ? ` · ${result.failed_file}` : "";
          const note = conflict
            ? `磁盘冲突：文件已被外部修改${fileHint}。变更仍保留在 Review，请重新打开文件或刷新基线后再 Accept。`
            : raw;
          setApplyStatus("failed");
          setApplyMessage(note);
          setError(note);
          useReviewStore.getState().setApplyStatus("failed", note);
          // Keep pending changes on conflict so user can retry after resolving disk drift.
          return;
        }
        const cs = result.changeset_id || null;
        setLastChangesetId(cs);
        useReviewStore.getState().setChangesetId(cs);
        setApplyStatus("applied");
        const note = cs
          ? `已写入 ${result.applied} 个文件 · changeset ${cs.slice(0, 8)}`
          : `已写入 ${result.applied} 个文件`;
        setApplyMessage(note);
        useReviewStore.getState().setApplyStatus("applied", note);
        const appliedPaths = new Set(selected.map((s) => s.path));
        const remain = fileChanges.filter((c) => !appliedPaths.has(c.path));
        setFileChanges(remain);
        useReviewStore.getState().setPending(remain);
      } catch (e) {
        const msg = String((e as Error)?.message || e);
        setApplyStatus("failed");
        setApplyMessage(msg);
        setError(msg);
        useReviewStore.getState().setApplyStatus("failed", msg);
      }
    },
    [fileChanges, streaming, workspace],
  );

  const applyPartialFileChange = useCallback(
    async (change: CodeFileChange) => {
      await applyFileChanges(undefined, [change]);
    },
    [applyFileChanges],
  );

  const undoLastApply = useCallback(async () => {
    if (workspace === FALLBACK_WORKSPACE) {
      setError("请先 Open project，再 Undo。");
      return;
    }
    const review = useReviewStore.getState();
    const run = useRunStore.getState();
    if (
      !canUndoReview({
        runPhase: run.phase,
        applyStatus: review.applyStatus,
        streaming,
        lastChangesetId,
      })
    ) {
      setApplyMessage(
        !lastChangesetId
          ? "没有可撤销的 changeset。"
          : "流式输出或 Apply 进行中，请稍后再 Undo。",
      );
      return;
    }
    setApplyStatus("undoing");
    setApplyMessage("正在 Undo…");
    useReviewStore.getState().setApplyStatus("undoing", "正在 Undo…");
    try {
      const result = await rollbackCodeChanges({
        workspace,
        changeset_id: lastChangesetId,
      });
      if (!result.ok) {
        setApplyStatus("failed");
        setApplyMessage(result.error || "撤销失败");
        setError(result.error || "撤销失败");
        useReviewStore.getState().setApplyStatus("failed", result.error || "撤销失败");
        return;
      }
      setApplyStatus("idle");
      setApplyMessage(`已撤销 changeset ${lastChangesetId!.slice(0, 8)}`);
      setLastChangesetId(null);
      useReviewStore.getState().setChangesetId(null);
      useReviewStore.getState().setApplyStatus("idle", `已撤销`);
    } catch (e) {
      const msg = String((e as Error)?.message || e);
      setApplyStatus("failed");
      setApplyMessage(msg);
      setError(msg);
      useReviewStore.getState().setApplyStatus("failed", msg);
    }
  }, [lastChangesetId, streaming, workspace]);

  return {
    threads,
    activeId,
    messages,
    streaming,
    status,
    error,
    artifacts,
    mission,
    pipeline,
    healRound,
    evolution,
    evolutionHistory,
    activities,
    goalTitle,
    goalStartedAt,
    fileChanges,
    applyStatus,
    applyMessage,
    lastChangesetId,
    workspace,
    workMode,
    // UX P0-1: 会话累计 tokens（OpenCode 式小字展示）
    sessionUsage,
    // UX P0-4: 流式期间的待审批队列（内联审批卡数据源）
    pendingApprovals,
    newChat,
    openThread,
    deleteThread,
    renameThread,
    send,
    regenerate,
    stop,
    resume,
    setError,
    applyFileChanges,
    applyPartialFileChange,
    undoLastApply,
    clearFileChanges,
    clearGoal,
  };
}
