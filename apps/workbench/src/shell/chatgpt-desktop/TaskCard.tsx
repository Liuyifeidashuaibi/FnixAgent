/**
 * P0 多任务并行可视化 — TaskCard
 *
 * 单个 job 卡片：状态徽章 / 标题 / 进度条 / 9 步流水线小圆点 / 取消按钮 / 错误显示
 * 风格：极简浅色（cursor codex 风格），不用 amber 色
 */

import type { WorkJob } from "./fnixRuntime";
import "./jobsPanel.css";

const STATUS_COLOR: Record<WorkJob["status"], string> = {
  pending: "pending",
  running: "running",
  completed: "completed",
  failed: "failed",
  cancelled: "cancelled",
};

const STATUS_LABEL: Record<WorkJob["status"], string> = {
  pending: "排队",
  running: "运行",
  completed: "完成",
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
  job: WorkJob;
  selected?: boolean;
  onSelect?: (jobId: string) => void;
  onCancel?: (jobId: string) => void;
}

export function TaskCard({ job, selected = false, onSelect, onCancel }: Props) {
  const statusKey = STATUS_COLOR[job.status];
  const isActive = job.status === "running" || job.status === "pending";
  const completedSteps = job.steps.filter((s) => s.status === "completed").length;
  const totalSteps = job.steps.length || 9;

  return (
    <div
      className={`fnix-task-card ${statusKey}${selected ? " selected" : ""}`}
      onClick={() => onSelect?.(job.id)}
      role="button"
      tabIndex={0}
    >
      <div className="fnix-task-card-header">
        <span className={`fnix-task-card-dot ${statusKey}`} />
        <span className="fnix-task-card-title" title={job.title}>
          {job.title || "未命名任务"}
        </span>
        <span className="fnix-task-card-meta">{timeAgo(job.updated_at || job.created_at)}</span>
      </div>

      <div className="fnix-task-card-progress">
        <div
          className="fnix-task-card-progress-bar"
          style={{ width: `${Math.max(2, job.progress)}%` }}
        />
      </div>

      <div className="fnix-task-card-steps" title={`${completedSteps}/${totalSteps} 步`}>
        {job.steps.length === 0
          ? Array.from({ length: 9 }).map((_, i) => (
              <span key={i} className="fnix-task-step-dot pending" />
            ))
          : job.steps.map((step) => (
              <span
                key={step.key}
                className={`fnix-task-step-dot ${step.status}`}
                title={`${step.label} · ${step.status}`}
              />
            ))}
      </div>

      {job.status === "failed" && job.error ? (
        <div className="fnix-task-card-error" title={job.error}>
          {job.error.slice(0, 120)}
          {job.error.length > 120 ? "…" : ""}
        </div>
      ) : null}

      {job.artifacts.length > 0 ? (
        <div className="fnix-task-card-artifacts">
          {job.artifacts.slice(0, 3).map((a, i) => (
            <span key={i} className="fnix-task-artifact-chip" title={a.path}>
              {a.name || a.path}
            </span>
          ))}
          {job.artifacts.length > 3 ? (
            <span className="fnix-task-artifact-chip more">
              +{job.artifacts.length - 3}
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="fnix-task-card-footer">
        <span className="fnix-task-card-status-label">{STATUS_LABEL[job.status]}</span>
        {isActive ? (
          <button
            className="fnix-task-card-cancel"
            onClick={(e) => {
              e.stopPropagation();
              onCancel?.(job.id);
            }}
          >
            取消
          </button>
        ) : null}
      </div>
    </div>
  );
}
