/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code is proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * StatusLine — 单行状态指示器（参考 Cursor/Trae/Cline）
 *
 * 设计原则：
 * - 执行中只显示一行当前操作 + 动画 spinner，不累积历史
 * - 完成后显示"已完成" + 耗时
 * - 不暴露规划/执行/审查等内部架构阶段
 * - 可点击展开查看操作记录（默认折叠）
 */

import { memo, useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Loader2, Check, CircleAlert, Square } from 'lucide-react';
import type { ActivityItem } from './activityTypes';
import './StatusLine.css';

interface Props {
  items: ActivityItem[];
  streaming?: boolean;
  onStop?: () => void;
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 1) return '<1s';
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function StatusLineInner({ items, streaming = false, onStop }: Props) {
  const [open, setOpen] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const useful = items.filter((item) => {
    if (item.kind === 'mission') return false;
    if (item.meta === 'evolution' || item.meta === 'pipeline' || item.meta === 'reflection→HERA')
      return false;
    if (item.title.startsWith('KTG ') || item.title.startsWith('Pipeline step')) return false;
    if (item.title === 'tool 已完成' && !item.path) return false;
    return true;
  });

  // 计算耗时
  useEffect(() => {
    if (!streaming || useful.length === 0) return;
    const start = Math.min(...useful.map((item) => item.startedAt));
    const timer = window.setInterval(() => setElapsed(Date.now() - start), 1000);
    return () => window.clearInterval(timer);
  }, [streaming, useful]);

  if (useful.length === 0 && !streaming) return null;

  const running = useful.find((item) => item.status === 'running');
  const hasError = useful.some((item) => item.status === 'error' || item.kind === 'error');
  const allDone = useful.every(
    (item) => item.status === 'done' || item.status === 'error' || item.status === 'cancelled',
  );

  // 状态文字
  let label: string;
  if (streaming && running) {
    label = running.title;
  } else if (hasError) {
    label = '执行遇到问题';
  } else if (allDone && useful.length > 0) {
    label = '已完成';
  } else if (streaming) {
    label = '处理中…';
  } else {
    label = '';
  }

  if (!label) return null;

  // 耗时
  let durationText = '';
  if (useful.length > 0) {
    const start = Math.min(...useful.map((item) => item.startedAt));
    if (streaming) {
      durationText = formatDuration(elapsed);
    } else {
      const end = Math.max(...useful.map((item) => item.endedAt || item.startedAt));
      durationText = formatDuration(end - start);
    }
  }

  const fileCount = new Set(useful.map((item) => item.path).filter(Boolean)).size;
  const doneCount = useful.filter(
    (item) => item.status === 'done' || item.status === 'error' || item.status === 'cancelled',
  ).length;

  return (
    <section className={`fnix-status-line${streaming ? ' streaming' : ''}${hasError ? ' error' : ''}${allDone ? ' done' : ''}`}>
      <div className="fnix-status-line-bar">
        <span className="fnix-status-line-icon" aria-hidden>
          {streaming ? (
            <Loader2 size={13} className="spin" />
          ) : hasError ? (
            <CircleAlert size={13} />
          ) : (
            <Check size={13} />
          )}
        </span>
        <span className="fnix-status-line-label">{label}</span>
        {durationText && (
          <span className="fnix-status-line-meta">
            {durationText}
            {fileCount > 0 && ` · ${fileCount} 个文件`}
            {!streaming && ` · ${doneCount}/${useful.length} 项`}
          </span>
        )}
        {streaming && onStop && (
          <button
            type="button"
            className="fnix-status-line-stop"
            onClick={onStop}
            title="停止"
          >
            <Square size={10} fill="currentColor" />
            停止
          </button>
        )}
        {useful.length > 1 && (
          <button
            type="button"
            className="fnix-status-line-toggle"
            onClick={() => setOpen(!open)}
            aria-label={open ? '收起操作记录' : '展开操作记录'}
          >
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        )}
      </div>
      {open && (
        <div className="fnix-status-line-detail">
          {useful.slice(-12).map((item) => (
            <div key={item.id} className={`fnix-status-line-item ${item.status}`}>
              <span className="fnix-status-line-item-title">{item.title}</span>
              {item.path && <span className="fnix-status-line-item-path">{item.path}</span>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export const StatusLine = memo(StatusLineInner);
