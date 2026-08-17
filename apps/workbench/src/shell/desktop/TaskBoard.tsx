/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * 任务面板（Kanban）— 对标 OpenAI Code 任务面板 / vibe-kanban 的开源等价实现。
 *
 * 设计来源：
 *   - OpenAI Code 的 task panel 是 Desktop 网页/桌面端的闭源 UI，无法直接取用。
 *   - 最接近的开放实现是 BloopAI/vibe-kanban（Apache-2.0，React+Tailwind+@dnd-kit 看板，
 *     列 = Backlog / In Progress / In Review / Done）。其架构依赖 Rust 后端 + git worktree +
 *     GitHub OAuth，无法整包搬入，故按其一比一的看板范式，用 fnixagent 自有 React+Tailwind+
 *     zustand+lucide 栈重实现，并接入现有 useJobsStore（零新依赖，原生 HTML5 拖拽）。
 *
 * 数据映射到看板列（fnixagent 真实 job 状态）：
 *   队列(pending) · 运行中(running) · 待评审(completed=产出就绪待用户在 StudioPanel 评审)
 *   · 失败(failed) · 已取消(cancelled)
 *
 * 交互：
 *   - 队列列内联「新建任务」输入框 → useJobsStore.enqueue 真实派发后台 agent。
 *   - 点击卡片 → 选中并在右栏看板详情（进度 / 产物 / 事件 / 取消 / 重新运行）。
 *   - 原生拖拽：队列列内拖拽重排执行优先级；将「失败/取消」卡片拖入队列 → 取消原任务并重新入队。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import { KanbanSquare, RotateCcw, Send, X } from "lucide-react";
import { useJobsStore } from "./useJobsStore";
import { TaskCard } from "./TaskCard";
import type { WorkJob } from "./fnixRuntime";
import "./taskBoard.css";

type ColId = "pending" | "running" | "review" | "failed" | "cancelled";

interface ColumnDef {
  id: ColId;
  label: string;
  /** 该列聚合的真实 job 状态 */
  statuses: WorkJob["status"][];
  /** 列头强调色（复用项目设计 token） */
  accent: string;
}

const COLUMNS: ColumnDef[] = [
  { id: "pending", label: "队列", statuses: ["pending"], accent: "var(--faint, #9ca3af)" },
  { id: "running", label: "运行中", statuses: ["running"], accent: "var(--accent, #4f46e5)" },
  { id: "review", label: "待评审", statuses: ["completed"], accent: "var(--work, #10a37f)" },
  { id: "failed", label: "失败", statuses: ["failed"], accent: "#ef4444" },
  { id: "cancelled", label: "已取消", statuses: ["cancelled"], accent: "var(--muted, #6b7280)" },
];

const STATUS_LABEL: Record<WorkJob["status"], string> = {
  pending: "排队",
  running: "运行",
  completed: "待评审",
  failed: "失败",
  cancelled: "取消",
};

function timeAgo(iso: string): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const diff = Date.now() - t;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return `${Math.floor(diff / 86_400_000)} 天前`;
}

interface Props {
  workspace?: string;
  onClose: () => void;
}

export function TaskBoard({ workspace, onClose }: Props) {
  const jobs = useJobsStore((s) => s.jobs);
  const stats = useJobsStore((s) => s.stats);
  const selectedJobId = useJobsStore((s) => s.selectedJobId);
  const events = useJobsStore((s) => s.events);
  const refresh = useJobsStore((s) => s.refresh);
  const select = useJobsStore((s) => s.select);
  const enqueue = useJobsStore((s) => s.enqueue);
  const cancel = useJobsStore((s) => s.cancel);
  const loadEvents = useJobsStore((s) => s.loadEvents);
  const startAutoPoll = useJobsStore((s) => s.startAutoPoll);
  const stopAutoPoll = useJobsStore((s) => s.stopAutoPoll);

  // 挂载时启动自动轮询；卸载停止
  useEffect(() => {
    void refresh();
    startAutoPoll();
    return () => stopAutoPoll();
  }, [refresh, startAutoPoll, stopAutoPoll]);

  // 队列列本地重排（后端无优先级写回端点，仅前端乐观排序，刷新后回退服务端顺序）
  const [pendingOrder, setPendingOrder] = useState<string[] | null>(null);

  // 拖拽态
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverCol, setDragOverCol] = useState<ColId | null>(null);
  const dragJobRef = useRef<WorkJob | null>(null);

  const jobsByCol = useMemo(() => {
    const map: Record<ColId, WorkJob[]> = {
      pending: [],
      running: [],
      review: [],
      failed: [],
      cancelled: [],
    };
    for (const j of jobs) {
      if (j.status === "pending") map.pending.push(j);
      else if (j.status === "running") map.running.push(j);
      else if (j.status === "completed") map.review.push(j);
      else if (j.status === "failed") map.failed.push(j);
      else if (j.status === "cancelled") map.cancelled.push(j);
    }
    // 队列列应用本地重排
    if (pendingOrder) {
      const byId = new Map(map.pending.map((j) => [j.id, j]));
      const ordered = pendingOrder.map((id) => byId.get(id)).filter(Boolean) as WorkJob[];
      const extra = map.pending.filter((j) => !pendingOrder.includes(j.id));
      map.pending = [...ordered, ...extra];
    }
    return map;
  }, [jobs, pendingOrder]);

  const selectedJob = useMemo(
    () => jobs.find((j) => j.id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  );

  // 选中任务时拉取事件
  useEffect(() => {
    if (selectedJobId) void loadEvents(selectedJobId, 40);
  }, [selectedJobId, loadEvents]);

  // ── 新建任务（队列列内联 composer）──
  const [draft, setDraft] = useState("");
  const [enqueueErr, setEnqueueErr] = useState("");
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  const handleEnqueue = useCallback(async () => {
    const t = draft.trim();
    if (!t) return;
    setEnqueueErr("");
    const res = await enqueue(t, { workspace: workspace || undefined, priority: 10 });
    if (res.ok) {
      setDraft("");
    } else {
      setEnqueueErr(res.error || "入队失败");
    }
  }, [draft, enqueue, workspace]);

  // ── 拖拽：队列内重排 ──
  const handleReorder = useCallback(
    (targetId: string) => {
      const job = dragJobRef.current;
      if (!job || job.status !== "pending" || !dragId) return;
      setPendingOrder((prev) => {
        const base = prev ?? jobs.filter((j) => j.status === "pending").map((j) => j.id);
        const next = base.filter((id) => id !== dragId);
        const to = next.indexOf(targetId);
        next.splice(to < 0 ? next.length : to, 0, dragId);
        return next;
      });
    },
    [dragId, jobs],
  );

  // ── 拖拽：失败/取消 → 队列 = 重新运行 ──
  const handleRerun = useCallback(
    async (job: WorkJob) => {
      await cancel(job.id);
      const res = await enqueue(job.title || job.description || "重新运行任务", {
        workspace: workspace || job.workspace || undefined,
        priority: 5,
      });
      if (!res.ok) setEnqueueErr(res.error || "重新运行失败");
    },
    [cancel, enqueue, workspace],
  );

  const onCardDragStart = (e: DragEvent<HTMLDivElement>, job: WorkJob) => {
    dragJobRef.current = job;
    setDragId(job.id);
    e.dataTransfer.effectAllowed = "move";
    try {
      e.dataTransfer.setData("text/plain", job.id);
    } catch {
      /* ignore */
    }
  };

  const onCardDragEnd = () => {
    dragJobRef.current = null;
    setDragId(null);
    setDragOverCol(null);
  };

  const onColDragOver = (e: DragEvent<HTMLElement>, col: ColId) => {
    if (!dragId) return;
    // 仅「队列」列接受拖放（重排 / 重新运行）
    if (col !== "pending") return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setDragOverCol("pending");
  };

  const onColDrop = (e: DragEvent<HTMLElement>, col: ColId) => {
    if (col !== "pending" || !dragId) return;
    e.preventDefault();
    const job = dragJobRef.current;
    if (job && job.status !== "pending") {
      void handleRerun(job);
    }
    // 落在列空白区（无具体卡片）：若是队列内拖拽，无需重排
    setDragOverCol(null);
  };

  const selectedEvents = selectedJobId ? (events[selectedJobId] ?? []) : [];

  return (
    <div className="fnix-task-board-overlay" role="dialog" aria-label="任务面板">
      {/* 顶栏 */}
      <div className="fnix-board-top">
        <div className="fnix-board-top-left">
          <KanbanSquare size={16} />
          <span className="fnix-board-title">任务面板</span>
          {stats ? (
            <span className="fnix-board-stats">
              <b>{stats.active}</b> 运行中 · <b>{stats.pending}</b> 排队 · <b>{stats.completed}</b> 待评审
            </span>
          ) : null}
        </div>
        <div className="fnix-board-top-right">
          <span className="fnix-board-hint">拖「失败/取消」卡片到「队列」可重新运行</span>
          <button type="button" className="fnix-board-close" onClick={onClose} title="关闭任务面板">
            <X size={16} />
          </button>
        </div>
      </div>

      {/* 看板主体 */}
      <div className="fnix-board-body">
        <div className="fnix-board-columns">
          {COLUMNS.map((col) => {
            const colJobs = jobsByCol[col.id];
            const isQueue = col.id === "pending";
            return (
              <section
                key={col.id}
                className={`fnix-board-col${dragOverCol === col.id ? " drag-over" : ""}`}
                onDragOver={(e) => onColDragOver(e, col.id)}
                onDragLeave={() => setDragOverCol((c) => (c === col.id ? null : c))}
                onDrop={(e) => onColDrop(e, col.id)}
              >
                <header className="fnix-board-col-head">
                  <span className="fnix-board-col-dot" style={{ background: col.accent }} />
                  <span className="fnix-board-col-label">{col.label}</span>
                  <span className="fnix-board-col-count">{colJobs.length}</span>
                </header>

                {/* 队列列：内联新建任务 composer */}
                {isQueue ? (
                  <div className="fnix-board-composer">
                    <textarea
                      ref={composerRef}
                      className="fnix-board-composer-input"
                      placeholder="描述一个任务，回车派发后台 agent…"
                      value={draft}
                      rows={2}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void handleEnqueue();
                        }
                      }}
                    />
                    <div className="fnix-board-composer-actions">
                      <button
                        type="button"
                        className="fnix-board-send"
                        disabled={!draft.trim()}
                        onClick={() => void handleEnqueue()}
                      >
                        <Send size={13} />
                        派发
                      </button>
                    </div>
                    {enqueueErr ? <div className="fnix-board-composer-err">{enqueueErr}</div> : null}
                  </div>
                ) : null}

                <div className="fnix-board-col-body">
                  {colJobs.length === 0 ? (
                    <div className="fnix-board-col-empty">
                      {isQueue ? "从上方派发新任务" : "暂无任务"}
                    </div>
                  ) : (
                    colJobs.map((job) => (
                      <div
                        key={job.id}
                        className={`fnix-board-card-wrap${dragId === job.id ? " dragging" : ""}${
                          selectedJobId === job.id ? " selected" : ""
                        }`}
                        draggable
                        onDragStart={(e) => onCardDragStart(e, job)}
                        onDragEnd={onCardDragEnd}
                        onDragOver={(e) => {
                          if (dragId && dragJobRef.current?.status === "pending") e.preventDefault();
                        }}
                        onDrop={(e) => {
                          if (dragJobRef.current?.status === "pending") {
                            e.preventDefault();
                            e.stopPropagation();
                            handleReorder(job.id);
                          }
                        }}
                        onClick={() => select(job.id)}
                      >
                        <TaskCard
                          job={job}
                          selected={selectedJobId === job.id}
                          onSelect={select}
                          onCancel={cancel}
                        />
                      </div>
                    ))
                  )}
                </div>
              </section>
            );
          })}
        </div>

        {/* 右栏：选中任务详情 */}
        {selectedJob ? (
          <aside className="fnix-board-detail" aria-label="任务详情">
            <div className="fnix-board-detail-head">
              <span className="fnix-board-col-dot" style={{ background: "var(--accent)" }} />
              <span className="fnix-board-detail-title" title={selectedJob.title}>
                {selectedJob.title || "未命名任务"}
              </span>
              <button
                type="button"
                className="fnix-board-detail-x"
                onClick={() => select(null)}
                title="关闭详情"
              >
                <X size={15} />
              </button>
            </div>

            <div className="fnix-board-detail-meta">
              <span className={`fnix-board-status-pill ${selectedJob.status}`}>
                {STATUS_LABEL[selectedJob.status]}
              </span>
              {selectedJob.mode ? <span className="fnix-board-detail-chip">{selectedJob.mode}</span> : null}
              <span className="fnix-board-detail-time">
                更新 {timeAgo(selectedJob.updated_at || selectedJob.created_at)}
              </span>
            </div>

            <div className="fnix-board-detail-progress">
              <div
                className="fnix-board-detail-progress-bar"
                style={{ width: `${Math.max(2, selectedJob.progress)}%` }}
              />
            </div>

            {selectedJob.description ? (
              <div className="fnix-board-detail-section">
                <div className="fnix-board-detail-label">描述</div>
                <div className="fnix-board-detail-desc">{selectedJob.description}</div>
              </div>
            ) : null}

            {selectedJob.artifacts.length > 0 ? (
              <div className="fnix-board-detail-section">
                <div className="fnix-board-detail-label">产物 · {selectedJob.artifacts.length}</div>
                <div className="fnix-board-detail-artifacts">
                  {selectedJob.artifacts.map((a, i) => (
                    <span key={i} className="fnix-board-detail-artifact" title={a.path}>
                      {a.name || a.path}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="fnix-board-detail-section">
              <div className="fnix-board-detail-label">事件 · {selectedEvents.length}</div>
              <div className="fnix-board-detail-events">
                {selectedEvents.length === 0 ? (
                  <div className="fnix-board-col-empty">暂无事件</div>
                ) : (
                  selectedEvents.slice(0, 20).map((ev, i) => (
                    <div key={i} className="fnix-board-event">
                      <span className="fnix-board-event-type">{ev.type}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {selectedJob.error ? (
              <div className="fnix-board-detail-error" title={selectedJob.error}>
                {selectedJob.error}
              </div>
            ) : null}

            <div className="fnix-board-detail-actions">
              {(selectedJob.status === "running" || selectedJob.status === "pending") && (
                <button
                  type="button"
                  className="fnix-board-detail-btn danger"
                  onClick={() => void cancel(selectedJob.id)}
                >
                  取消任务
                </button>
              )}
              {(selectedJob.status === "failed" || selectedJob.status === "cancelled") && (
                <button
                  type="button"
                  className="fnix-board-detail-btn"
                  onClick={() => void handleRerun(selectedJob)}
                >
                  <RotateCcw size={13} />
                  重新运行
                </button>
              )}
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
