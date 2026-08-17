/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * P0 多任务并行可视化 — Jobs store (zustand)
 *
 * 管理 jobs 数组 + 自动轮询：
 *   - 有活跃 job 时高频轮询 (1.2s)
 *   - 全部空闲时低频轮询 (10s)
 *
 * 对应后端 /api/v1/work/jobs 系列端点（work_jobs.py）。
 */

import { create } from "zustand";
import {
  type WorkJob,
  type WorkJobStats,
  type WorkJobEvent,
  listJobs,
  enqueueJob,
  cancelJob,
  getJobEvents,
  getJobStats,
  type FnixLlm,
} from "./fnixRuntime";

interface JobsState {
  jobs: WorkJob[];
  stats: WorkJobStats | null;
  selectedJobId: string | null;
  loading: boolean;
  error: string;

  // 事件流（按 session_id 索引，最多保留 80 条）
  events: Record<string, WorkJobEvent[]>;

  // 自动轮询控制
  _pollTimer: number | null;
  _pollFast: boolean;

  refresh: () => Promise<void>;
  select: (jobId: string | null) => void;
  enqueue: (
    userInput: string,
    opts?: {
      workspace?: string;
      llm?: FnixLlm | null;
      priority?: number;
    },
  ) => Promise<{ ok: boolean; session_id?: string; error?: string }>;
  cancel: (jobId: string) => Promise<{ ok: boolean; error?: string }>;
  loadEvents: (jobId: string, limit?: number) => Promise<void>;

  startAutoPoll: (fast?: boolean) => void;
  stopAutoPoll: () => void;
}

const FAST_POLL_MS = 1200;
const IDLE_POLL_MS = 10_000;

function hasActive(jobs: WorkJob[]): boolean {
  return jobs.some((j) => j.status === "running" || j.status === "pending");
}

export const useJobsStore = create<JobsState>()((set, get) => {
  const scheduleNext = () => {
    const state = get();
    if (state._pollTimer != null) {
      window.clearTimeout(state._pollTimer);
    }
    const fast = state._pollFast || hasActive(state.jobs);
    const interval = fast ? FAST_POLL_MS : IDLE_POLL_MS;
    const timer = window.setTimeout(() => {
      void get().refresh().finally(() => {
        if (get()._pollTimer !== null) scheduleNext();
      });
    }, interval);
    set({ _pollTimer: timer, _pollFast: fast });
  };

  return {
    jobs: [],
    stats: null,
    selectedJobId: null,
    loading: false,
    error: "",
    events: {},
    _pollTimer: null,
    _pollFast: false,

    refresh: async () => {
      set({ loading: true, error: "" });
      try {
        const [jobs, stats] = await Promise.all([listJobs({ limit: 100 }), getJobStats()]);
        set({ jobs, stats: stats, loading: false });
      } catch (e) {
        set({ loading: false, error: String(e || "refresh failed") });
      }
    },

    select: (jobId) => set({ selectedJobId: jobId }),

    enqueue: async (userInput, opts = {}) => {
      const result = await enqueueJob({
        userInput,
        workspace: opts.workspace,
        llm: opts.llm,
        priority: opts.priority,
      });
      if (result.ok) {
        // 立即触发刷新，确保新 job 出现在列表顶部
        await get().refresh();
        // 启用高频轮询以追踪进度
        set({ _pollFast: true });
        scheduleNext();
      }
      return result;
    },

    cancel: async (jobId) => {
      const result = await cancelJob(jobId);
      if (result.ok) {
        await get().refresh();
      }
      return result;
    },

    loadEvents: async (jobId, limit = 80) => {
      try {
        const evts = await getJobEvents(jobId, limit);
        set((s) => ({ events: { ...s.events, [jobId]: evts } }));
      } catch {
        /* ignore */
      }
    },

    startAutoPoll: (fast = false) => {
      set({ _pollFast: fast });
      scheduleNext();
    },

    stopAutoPoll: () => {
      const timer = get()._pollTimer;
      if (timer != null) {
        window.clearTimeout(timer);
      }
      set({ _pollTimer: null, _pollFast: false });
    },
  };
});

/** Selectors */
export const useActiveJobs = () =>
  useJobsStore((s) => s.jobs.filter((j) => j.status === "running" || j.status === "pending"));

export const useCompletedJobs = () =>
  useJobsStore((s) =>
    s.jobs.filter((j) => ["completed", "failed", "cancelled"].includes(j.status)),
  );

export const useSelectedJob = () =>
  useJobsStore((s) => s.jobs.find((j) => j.id === s.selectedJobId) ?? null);
