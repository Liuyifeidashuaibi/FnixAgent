/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { useEffect, useState } from "react";
import { Pause, Play, X } from "lucide-react";

export interface GlassGoalRowProps {
  title: string;
  streaming: boolean;
  startedAt: number | null;
  statusLabel?: string | null;
  onPause?: () => void;
  onClear?: () => void;
}

function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, "0")}`;
}

export function GlassGoalRow({
  title,
  streaming,
  startedAt,
  statusLabel,
  onPause,
  onClear,
}: GlassGoalRowProps) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!streaming || !startedAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [streaming, startedAt]);

  if (!title && !streaming && !statusLabel) return null;

  const elapsedLabel = startedAt ? formatElapsed(now - startedAt) : null;

  return (
    <div className={`glass-goal-row${streaming ? " live" : ""}`} aria-live="polite">
      <div className="glass-goal-main">
        <span className={`glass-goal-dot${streaming ? " run" : ""}`} />
        <div className="glass-goal-text">
          <span className="glass-goal-title" title={title}>
            {title || "任务"}
          </span>
          <span className="glass-goal-meta">
            {streaming ? "进行中" : "已完成"}
            {statusLabel ? ` · ${statusLabel}` : ""}
            {elapsedLabel ? ` · ${elapsedLabel}` : ""}
          </span>
        </div>
      </div>
      <div className="glass-goal-actions">
        {streaming && onPause ? (
          <button type="button" className="glass-goal-btn" onClick={onPause} title="暂停">
            <Pause size={13} />
            暂停
          </button>
        ) : null}
        {!streaming && onClear ? (
          <button type="button" className="glass-goal-btn" onClick={onClear} title="清除过程记录">
            <X size={13} />
            清除
          </button>
        ) : null}
        {!streaming && !onClear && onPause ? (
          <button type="button" className="glass-goal-btn" disabled title="继续">
            <Play size={13} />
            继续
          </button>
        ) : null}
      </div>
    </div>
  );
}
