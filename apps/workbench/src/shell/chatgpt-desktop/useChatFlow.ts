/**
 * Fnix Work / Codex flow via agentd (ChatGPT-look shell).
 * Work → /api/v1/work/stream · Codex → /api/v1/chat/agent
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
  applyCodexChanges,
  indexHarnessWorkspace,
  pickFnixLlm,
  pushLlmToHarness,
  resumeRun,
  rollbackCodexChanges,
  streamCodex,
  streamWork,
  type CodexFileChange,
  type EvolutionInfo,
  type WorkExecMode,
  type WorkMission,
  type WorkPipelineInfo,
} from "./fnixRuntime";
import { getFnixApiBase } from "../../lib/fnixBridge";
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

function mergeFileChanges(prev: CodexFileChange[], incoming: CodexFileChange[]): CodexFileChange[] {
  const map = new Map<string, CodexFileChange>();
  for (const ch of prev) {
    if (ch.path) map.set(ch.path, ch);
  }
  for (const ch of incoming) {
    if (ch.path) map.set(ch.path, { ...map.get(ch.path), ...ch });
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

function parseDoneChanges(payload: unknown): CodexFileChange[] {
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
      } satisfies CodexFileChange;
    })
    .filter(Boolean) as CodexFileChange[];
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
): "work" | "codex" {
  if (mode === "codex") return "codex";
  if (workMode !== "craft" || workspace === FALLBACK_WORKSPACE) return "work";
  return looksLikeRepoCode(userInput) ? "codex" : "work";
}

function uid(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function titleFrom(text: string) {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length <= 48 ? t || "新任务" : `${t.slice(0, 48)}…`;
}

/**
 * 创建流式输出所需的本地状态闭包（buf + RAF + assistantId 引用）。
 * send / resume 共享同一套 flush / appendText / finalize 实现，避免 ~70 行重复。
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
  const flushStreamBuf = () => {
    const buffered = streamBufRef.current;
    const aid = streamAssistantIdRef.current;
    streamBufRef.current = "";
    streamRafRef.current = null;
    if (!buffered || !aid) return;
    commitMessages(
      messagesRef.current.map((m) => (m.id === aid ? { ...m, content: m.content + buffered } : m)),
    );
  };

  const appendText = (delta: string) => {
    if (!delta) return;
    streamBufRef.current += delta;
    if (streamRafRef.current !== null) return;
    streamRafRef.current = requestAnimationFrame(flushStreamBuf);
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
    if (streamRafRef.current !== null) {
      cancelAnimationFrame(streamRafRef.current);
      streamRafRef.current = null;
    }
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
    setFileChanges: (updater: (prev: CodexFileChange[]) => CodexFileChange[]) => void;
    setStatus: (s: string | null) => void;
    setError: (e: string | null) => void;
    setGoalTitle: (t: string) => void;
    setEvolutionHistory: (updater: (prev: EvolutionRecord[]) => EvolutionRecord[]) => void;
    evolutionRef: { current: EvolutionInfo | null };
    missionRef: { current: WorkMission | null };
    goalStartedAtRef: { current: number | null };
    runStore: { setStatus: (s: string) => void; setError: (e: string | null) => void };
    reviewStore: { setPending: (c: CodexFileChange[]) => void };
    /** send 模式下过滤 "Something went wrong" 前缀文本，resume 不过滤 */
    suppressSomethingPrefix?: boolean;
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
  } = opts;

  return {
    onText: local.appendText,
    onStructuredBlock: local.appendStructuredBlock,
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
    onFileChange: (fc: CodexFileChange) => {
      setFileChanges((prev) => {
        const next = mergeFileChanges(prev, [fc]);
        reviewStore.setPending(next);
        return next;
      });
      setStatus(`Preview: ${fc.path || "file"}`);
    },
    onError: (message: string) => {
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
        setFileChanges((prev) => {
          const next = mergeFileChanges(prev, doneChanges);
          reviewStore.setPending(next);
          return next;
        });
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
  const [fileChanges, setFileChanges] = useState<CodexFileChange[]>([]);
  const [applyStatus, setApplyStatus] = useState<ApplyStatus>("idle");
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [lastChangesetId, setLastChangesetId] = useState<string | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [goalTitle, setGoalTitle] = useState<string>("");
  const [goalStartedAt, setGoalStartedAt] = useState<number | null>(null);
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
      const rec: ChatSessionRecord = {
        id,
        project_path: storageKey,
        title,
        provider: opts.providerName,
        model: opts.model,
        messages: JSON.stringify(msgs),
        token_count: 0,
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

      const llm = pickFnixLlm(opts.providers, opts.apiKey, opts.providerName, opts.model);
      if (!llm?.api_key && llm?.provider !== "ollama") {
        setError("请先在「设置」中配置 API Key（BYOK），再发送。");
        return;
      }

      if (opts.mode === "codex" && workspace === FALLBACK_WORKSPACE) {
        setError("请先在左侧打开一个仓库，再发送代码修改任务。");
        return;
      }

      const backend = pickChatBackend(opts.mode, workMode, workspace, trimmed);
      if (backend === "codex" && workspace === FALLBACK_WORKSPACE) {
        setError("请先在左侧打开一个仓库，再执行代码修改。");
        return;
      }

      setError(null);
      setStatus("Connecting…");
      useRunStore.getState().start("Connecting…");
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
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
      };
      const assistantId = uid("a");
      const assistantMsg: ChatMsg = { id: assistantId, role: "assistant", content: "" };
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
        // send 模式：后端可能已写入 "Something went wrong: ..." 占位，跳过追加避免重复
        suppressSomethingPrefix: true,
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
          await streamCodex({
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

        // If stream finished with empty assistant, leave a hint
        const cur = messagesRef.current.find((m) => m.id === assistantId);
        if (cur && !cur.content.trim() && !ac.signal.aborted) {
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
    [activeId, opts, persist, streaming, workMode, workspace, commitMessages],
  );

  /**
   * Spec 4: 从 checkpoint 恢复长程任务。
   *
   * 对标 OpenAI Codex `codex resume --last` / Cursor checkpoints recover。
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
      };
      const systemNote: ChatMsg = {
        id: uid("s"),
        role: "user",
        content: `(系统：恢复中断的任务 ${shortId}，无需重新输入)`,
      };
      const nextMsgs = [systemNote, assistantMsg];
      commitMessages(nextMsgs);
      const title = `恢复: ${shortId}`;
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
        // resume 模式：不重复追加 ⚠️ 错误提示（后端未写入 "Something went wrong" 占位）
        suppressSomethingPrefix: false,
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
    async (paths?: string[], overrides?: CodexFileChange[]) => {
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
        const result = await applyCodexChanges({ workspace, changes: selected });
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
    async (change: CodexFileChange) => {
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
      const result = await rollbackCodexChanges({
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
