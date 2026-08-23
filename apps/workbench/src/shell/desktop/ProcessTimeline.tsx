/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** Agent 执行控制台：真实动作、证据和控制，不展示原始 chain-of-thought。 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  BrainCircuit,
  Check,
  ChevronDown,
  CircleAlert,
  FileCode2,
  Files,
  FlaskConical,
  Loader2,
  Search,
  Square,
  SquareTerminal,
  Wrench,
} from 'lucide-react';
import type { ActivityItem, ActivityKind } from './activityTypes';

interface Props {
  items: ActivityItem[];
  streaming?: boolean;
  onStop?: () => void;
  onOpenDiff?: (path: string) => void;
  compact?: boolean;
}

type Filter = 'all' | 'files' | 'commands' | 'issues';

const KIND_ICON: Record<ActivityKind, ReactNode> = {
  plan: <BrainCircuit size={14} />,
  think: <BrainCircuit size={14} />,
  tool: <Wrench size={14} />,
  read: <Search size={14} />,
  edit: <FileCode2 size={14} />,
  write: <FileCode2 size={14} />,
  test: <FlaskConical size={14} />,
  run: <SquareTerminal size={14} />,
  mission: <BrainCircuit size={14} />,
  done: <Check size={14} />,
  error: <CircleAlert size={14} />,
};

function isUsefulActivity(item: ActivityItem): boolean {
  if (item.kind === 'mission') return false;
  if (item.meta === 'evolution' || item.meta === 'pipeline' || item.meta === 'reflection→HERA')
    return false;
  if (item.title.startsWith('KTG ') || item.title.startsWith('Pipeline step')) return false;
  // 过滤无信息量的 "tool 已完成" 条目：这些是 observation 事件 obs.name 为空时的回退标题，
  // 对应的工具活动已通过 action 事件展示（如"使用 ls"、"写入 index.html"等）。
  if (item.title === 'tool 已完成' && !item.path) return false;
  return true;
}

function matchesFilter(item: ActivityItem, filter: Filter): boolean {
  if (filter === 'files') return ['read', 'edit', 'write'].includes(item.kind);
  if (filter === 'commands') return item.kind === 'run' || item.kind === 'test';
  if (filter === 'issues') return item.status === 'error' || item.kind === 'error';
  return true;
}

function formatElapsed(startedAt: number, endedAt: number): string {
  const ms = Math.max(0, endedAt - startedAt);
  const seconds = Math.floor(ms / 1000);
  if (seconds < 1) return '<1s';
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

/**
 * LiveDuration: self-contained 1s timer for elapsed time display.
 * Extracted from ProcessTimeline to prevent parent re-renders every second
 * (BUG-021 fix). Only this small component re-renders, not the entire tree.
 */
function LiveDuration({
  startedAt,
  endedAt,
  streaming,
}: {
  startedAt: number;
  endedAt?: number;
  streaming?: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (endedAt || !streaming) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [endedAt, streaming]);
  const end = endedAt || now;
  return <>{formatElapsed(startedAt, end)}</>;
}

function statusText(item: ActivityItem): string {
  if (item.status === 'running') return '进行中';
  if (item.status === 'error') return '失败';
  if (item.status === 'cancelled') return '已停止';
  if (item.status === 'needs_input') return '等待操作';
  return '完成';
}

export function ProcessTimeline({ items, streaming = false, onStop, onOpenDiff, compact }: Props) {
  const [open, setOpen] = useState(true);
  const [filter, setFilter] = useState<Filter>('all');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [showAll, setShowAll] = useState(false);
  const [atBottom, setAtBottom] = useState(true);
  const bodyRef = useRef<HTMLDivElement>(null);
  const visibleItems = useMemo(() => items.filter(isUsefulActivity), [items]);
  const filteredItems = useMemo(
    () => visibleItems.filter((item) => matchesFilter(item, filter)),
    [filter, visibleItems],
  );

  // BUG-021 fix: removed 1-second setInterval that caused full-tree re-renders.
  // Duration display is now handled by <LiveDuration> child components with
  // their own isolated timers.

  // 智能粘底滚动：用户上滚查看历史时不强制拉回底部（参考 Cline/OpenHands）。
  // 仅在 atBottom 时自动跟随，避免用户阅读历史时被流式追加打断。
  const lastItem = visibleItems[visibleItems.length - 1];
  const lastSig = lastItem
    ? `${lastItem.status}:${(lastItem.detail ?? '').length}:${lastItem.endedAt ?? 0}`
    : '';
  const handleScroll = useCallback(() => {
    if (!bodyRef.current) return;
    const el = bodyRef.current;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAtBottom(distance < 40);
  }, []);
  const scrollToBottom = useCallback(() => {
    if (!bodyRef.current) return;
    bodyRef.current.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' });
    setAtBottom(true);
  }, []);
  useEffect(() => {
    if (!streaming || !open || !bodyRef.current || !atBottom) return;
    const el = bodyRef.current;
    const raf = window.requestAnimationFrame(() => {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    });
    return () => window.cancelAnimationFrame(raf);
  }, [items.length, lastSig, open, streaming, atBottom]);

  if (visibleItems.length === 0) return null;

  const running = [...visibleItems].reverse().find((item) => item.status === 'running');
  const errors = visibleItems.filter(
    (item) => item.status === 'error' || item.kind === 'error',
  ).length;
  const cancelled = visibleItems.some((item) => item.status === 'cancelled');
  const latest = visibleItems[visibleItems.length - 1];
  const state = running ? 'running' : errors ? 'error' : cancelled ? 'cancelled' : 'done';
  // 标题逻辑：运行中显示当前活动，完成/出错显示整体状态而非最后活动名
  // （最后活动名往往是「Self-Optimizing 沉淀」等内部步骤，对用户无意义）
  const summary = running?.title || (state === 'done' ? '执行完成' : state === 'error' ? '执行遇到问题' : state === 'cancelled' ? '已停止' : latest?.title || '执行过程');
  const fileCount = new Set(visibleItems.map((item) => item.path).filter(Boolean)).size;
  const commandCount = visibleItems.filter(
    (item) => item.kind === 'run' || item.kind === 'test',
  ).length;
  const start = Math.min(...visibleItems.map((item) => item.startedAt));
  // For the summary line, compute end from items; live updates handled by LiveDuration below.
  const end = Math.max(...visibleItems.map((item) => item.endedAt || item.startedAt));
  const rows = showAll ? filteredItems : filteredItems.slice(-24);
  const hiddenRows = filteredItems.length - rows.length;
  const doneCount = visibleItems.filter(
    (item) => item.status === 'done' || item.status === 'error' || item.status === 'cancelled',
  ).length;

  return (
    <section
      className={`fnix-agent-process ${state}${open ? ' open' : ''}${compact ? ' compact' : ''}`}
      aria-label="执行过程"
    >
      <div className="fnix-agent-process-head">
        <button
          type="button"
          className="fnix-agent-process-toggle"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="agent-process-events"
        >
          <span className="fnix-agent-process-state" aria-hidden>
            {running ? (
              <Loader2 size={15} className="spin" />
            ) : errors ? (
              <CircleAlert size={15} />
            ) : (
              <Check size={15} />
            )}
          </span>
          <span className="fnix-agent-process-heading">
            <span className="fnix-agent-process-summary">{summary}</span>
            <span className="fnix-agent-process-meta">
              {running ? '正在执行' : errors ? '执行遇到问题' : cancelled ? '已停止' : '执行完成'}
              {' · '}
              <LiveDuration
                startedAt={start}
                endedAt={running ? undefined : end}
                streaming={streaming}
              />
              {' · '}
              {doneCount}/{visibleItems.length} 项完成
              {fileCount ? ` · ${fileCount} 个文件` : ''}
            </span>
          </span>
          <ChevronDown size={15} className="fnix-agent-process-chevron" aria-hidden />
        </button>
        {streaming && onStop ? (
          <button
            type="button"
            className="fnix-agent-process-stop"
            onClick={onStop}
            title="停止执行"
          >
            <Square size={11} fill="currentColor" />
            停止
          </button>
        ) : null}
      </div>

      {open ? (
        <>
          <div className="fnix-agent-process-toolbar" aria-label="筛选执行记录">
            {(
              [
                ['all', '全部', visibleItems.length],
                ['files', '文件', fileCount],
                ['commands', '命令', commandCount],
                ['issues', '问题', errors],
              ] as const
            ).map(([id, label, count]) => (
              <button
                key={id}
                type="button"
                className={filter === id ? 'active' : ''}
                onClick={() => setFilter(id)}
                disabled={id !== 'all' && count === 0}
              >
                {id === 'files' ? <Files size={12} /> : null}
                {label}
                <span>{count}</span>
              </button>
            ))}
          </div>
          <div
            id="agent-process-events"
            className="fnix-agent-process-body"
            ref={bodyRef}
            role="log"
            aria-live="polite"
            onScroll={handleScroll}
          >
            {hiddenRows > 0 ? (
              <button
                type="button"
                className="fnix-agent-process-hidden"
                onClick={() => setShowAll(true)}
                title="展开全部操作记录"
              >
                更早的 {hiddenRows} 项操作已收起 · 点击展开
              </button>
            ) : null}
            {rows.length > 0 ? (
              rows.map((item) => {
                const hasDetail = Boolean(item.detail?.trim());
                const isOpen = hasDetail && (expanded[item.id] !== undefined ? expanded[item.id] : item.status === 'running');
                const canOpenDiff = Boolean(
                  item.path && onOpenDiff && (item.kind === 'edit' || item.kind === 'write'),
                );
                return (
                  <article
                    key={item.id}
                    className={`fnix-agent-event ${item.status} kind-${item.kind}`}
                  >
                    <span className="fnix-agent-event-icon" aria-hidden>
                      {item.status === 'running' ? (
                        <Loader2 size={14} className="spin" />
                      ) : (
                        KIND_ICON[item.kind]
                      )}
                    </span>
                    <div className="fnix-agent-event-main">
                      <div className="fnix-agent-event-line">
                        <span className="fnix-agent-event-title">{item.title}</span>
                        <span className="fnix-agent-event-status">{statusText(item)}</span>
                        <time>
                          <LiveDuration
                            startedAt={item.startedAt}
                            endedAt={item.endedAt}
                            streaming={streaming}
                          />
                        </time>
                      </div>
                      {item.path ? (
                        <button
                          type="button"
                          className="fnix-agent-event-path"
                          onClick={canOpenDiff ? () => onOpenDiff?.(item.path!) : undefined}
                          disabled={!canOpenDiff}
                          title={item.path}
                        >
                          {item.path}
                        </button>
                      ) : null}
                      <div className="fnix-agent-event-actions">
                        {hasDetail ? (
                          <button
                            type="button"
                            onClick={() =>
                              setExpanded((prev) => ({ ...prev, [item.id]: !prev[item.id] }))
                            }
                            aria-expanded={isOpen}
                          >
                            {isOpen
                              ? '收起证据'
                              : item.kind === 'think'
                                ? '查看分析摘要'
                                : '查看输出'}
                          </button>
                        ) : null}
                        {canOpenDiff ? (
                          <button type="button" onClick={() => onOpenDiff?.(item.path!)}>
                            查看 Diff
                          </button>
                        ) : null}
                        {item.meta && item.meta !== item.title ? <span>{item.meta}</span> : null}
                      </div>
                      {isOpen && item.detail ? (
                        <pre className="fnix-agent-event-detail">{item.detail}</pre>
                      ) : null}
                    </div>
                  </article>
                );
              })
            ) : (
              <div className="fnix-agent-process-empty">此筛选下暂无记录</div>
            )}
            {streaming && !atBottom ? (
              <button
                type="button"
                className="fnix-agent-process-back-latest"
                onClick={scrollToBottom}
                title="回到最新"
              >
                回到最新
              </button>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
