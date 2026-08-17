/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * P0 多任务并行可视化 — JobsPanel
 *
 * 多任务并行面板：
 *   - 顶部：聚合统计（active / pending / completed / failed / total）
 *   - 中部：活跃任务卡片网格（pending / running）
 *   - 底部：历史任务折叠列表（completed / failed / cancelled）
 *
 * 风格：极简浅色，大面积留白，参考 cursor codex light 风格
 */

import { useEffect } from "react";
import { useJobsStore, useActiveJobs, useCompletedJobs } from "./useJobsStore";
import { TaskCard } from "./TaskCard";
import type { WorkJobStats } from "./fnixRuntime";

function StatPill({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`fnix-jobs-stat ${tone}`}>
      <span className="fnix-jobs-stat-value">{value}</span>
      <span className="fnix-jobs-stat-label">{label}</span>
    </div>
  );
}

function StatsRow({ stats }: { stats: WorkJobStats | null }) {
  if (!stats) return null;
  return (
    <div className="fnix-jobs-stats-row">
      <StatPill label="运行中" value={stats.active} tone="running" />
      <StatPill label="排队" value={stats.pending} tone="pending" />
      <StatPill label="完成" value={stats.completed} tone="completed" />
      <StatPill label="失败" value={stats.failed} tone="failed" />
      <StatPill label="总计" value={stats.total} tone="muted" />
    </div>
  );
}

interface Props {
  /** 折叠态（仅显示活跃任务，不显示历史） */
  compact?: boolean;
  /** 选中 job 后回调（父组件可切换到该 job 详情视图） */
  onSelectJob?: (jobId: string) => void;
}

export function JobsPanel({ compact = false, onSelectJob }: Props) {
  const jobs = useJobsStore((s) => s.jobs);
  const stats = useJobsStore((s) => s.stats);
  const selectedJobId = useJobsStore((s) => s.selectedJobId);
  const refresh = useJobsStore((s) => s.refresh);
  const select = useJobsStore((s) => s.select);
  const cancel = useJobsStore((s) => s.cancel);
  const startAutoPoll = useJobsStore((s) => s.startAutoPoll);
  const stopAutoPoll = useJobsStore((s) => s.stopAutoPoll);

  const activeJobs = useActiveJobs();
  const completedJobs = useCompletedJobs();

  // 挂载时启动自动轮询，卸载时停止
  useEffect(() => {
    void refresh();
    startAutoPoll();
    return () => stopAutoPoll();
  }, [refresh, startAutoPoll, stopAutoPoll]);

  const handleSelect = (jobId: string) => {
    select(jobId);
    onSelectJob?.(jobId);
  };

  const handleCancel = async (jobId: string) => {
    await cancel(jobId);
  };

  if (jobs.length === 0 && !stats) {
    return (
      <div className="fnix-jobs-panel empty">
        <div className="fnix-jobs-empty-hint">暂无后台任务</div>
      </div>
    );
  }

  return (
    <div className="fnix-jobs-panel">
      <div className="fnix-jobs-panel-header">
        <span className="fnix-jobs-panel-title">并行任务</span>
        <button
          className="fnix-jobs-refresh"
          onClick={() => void refresh()}
          title="刷新"
        >
          ↻
        </button>
      </div>

      <StatsRow stats={stats} />

      {activeJobs.length > 0 ? (
        <div className="fnix-jobs-section">
          <div className="fnix-jobs-section-label">
            活跃 · {activeJobs.length}
          </div>
          <div className="fnix-jobs-grid">
            {activeJobs.map((job) => (
              <TaskCard
                key={job.id}
                job={job}
                selected={selectedJobId === job.id}
                onSelect={handleSelect}
                onCancel={handleCancel}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="fnix-jobs-section empty">
          <div className="fnix-jobs-section-label">活跃</div>
          <div className="fnix-jobs-empty-hint">所有任务均已完成</div>
        </div>
      )}

      {!compact && completedJobs.length > 0 ? (
        <div className="fnix-jobs-section">
          <div className="fnix-jobs-section-label">
            历史 · {completedJobs.length}
          </div>
          <div className="fnix-jobs-grid completed">
            {completedJobs.slice(0, 30).map((job) => (
              <TaskCard
                key={job.id}
                job={job}
                selected={selectedJobId === job.id}
                onSelect={handleSelect}
                onCancel={handleCancel}
              />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
