/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Sidebar thread list — search, open, rename, delete.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, MessageSquare, Pencil, Pin, Plus, RotateCcw, Search, Trash2, X } from "lucide-react";
import type { ChatThread } from "./useChatFlow";
import { listRuns, type WorkRunStatus, type WorkRunSummary } from "./fnixRuntime";

type Group = { label: string; items: ChatThread[] };

interface Props {
  groups: Group[];
  activeId: string | null;
  hasSession: boolean;
  streaming: boolean;
  emptyHint: string;
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  /** Spec 4: 点击可恢复任务时的回调（触发 resume_from_checkpoint） */
  onResumeRun?: (runId: string) => void;
  /** Spec 4: 外部通知刷新可恢复任务列表（如任务结束/失败后） */
  resumeRefreshSignal?: number;
  /** L1: 已置顶的会话 ID 列表 */
  pinnedThreadIds?: string[];
  /** L1: 置顶/取消置顶回调 */
  onTogglePin?: (id: string) => void;
  /** L3: 空态「新任务」引导按钮回调 */
  onNewChat?: () => void;
}

/** 从 run.meta 提取展示标题（可恢复任务机制 的 run 列表） */
function runTitle(meta: Record<string, unknown> | undefined, runId: string): string {
  const u = meta?.user_input;
  if (typeof u === "string" && u.trim()) {
    const first = u.split("\n")[0].trim();
    return first.length > 40 ? first.slice(0, 40) + "…" : first;
  }
  return runId.slice(0, 8);
}

/** 相对时间格式化（宋韵风：极简） */
function timeAgo(ts: number | undefined): string {
  if (!ts) return "";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`;
  return `${Math.floor(diff / 86400)}天前`;
}

/** Spec 4: 可恢复任务 section — 可恢复任务机制 / Code `code resume --last` */
function ResumableRuns({
  onResume,
  disabled,
  refreshSignal,
}: {
  onResume: (runId: string) => void;
  disabled: boolean;
  refreshSignal: number;
}) {
  const [runs, setRuns] = useState<WorkRunSummary[]>([]);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void listRuns({ limit: 20 }).then((res) => {
      if (cancelled) return;
      // 只展示可恢复的（interrupted/failed/running 但非当前活跃）
      const resumable = (res.runs || []).filter(
        (r) => r.resumable && r.status !== "running",
      );
      setRuns(resumable.slice(0, 8));
    });
    return () => {
      cancelled = true;
    };
  }, [refreshSignal]);

  if (runs.length === 0) return null;

  const statusDot = (s: WorkRunStatus) => {
    // 宋韵风：细线点 + 语义色（青灰/赭石/墨色）
    if (s === "failed") return "run-dot failed";
    if (s === "interrupted") return "run-dot interrupted";
    return "run-dot";
  };

  return (
    <div className="fnix-thread-group fnix-resumable-group">
      <button
        type="button"
        className="fnix-thread-group-h fnix-resumable-h"
        onClick={() => setExpanded((v) => !v)}
        aria-label={expanded ? "折叠可恢复任务" : "展开可恢复任务"}
      >
        <span className={`fnix-resumable-arrow${expanded ? " open" : ""}`}>›</span>
        可恢复任务
        <span className="fnix-resumable-count">{runs.length}</span>
      </button>
      {expanded &&
        runs.map((r) => (
          <div key={r.run_id} className="fnix-thread-row fnix-resumable-row">
            <button
              type="button"
              className="fnix-thread flat"
              onClick={() => onResume(r.run_id)}
              disabled={disabled}
              title={`恢复任务 · ${runTitle(r.meta, r.run_id)} · ${r.status}`}
            >
              <span className={statusDot(r.status)} aria-hidden />
              <RotateCcw size={13} className="fnix-thread-ico" />
              <span className="fnix-thread-title">{runTitle(r.meta, r.run_id)}</span>
              <span className="fnix-resumable-time">{timeAgo(r.updated_at)}</span>
            </button>
          </div>
        ))}
    </div>
  );
}

export function ThreadSidebar({
  groups,
  activeId,
  hasSession,
  streaming,
  emptyHint,
  onOpen,
  onRename,
  onDelete,
  onResumeRun,
  resumeRefreshSignal = 0,
  pinnedThreadIds = [],
  onTogglePin,
  onNewChat,
}: Props) {
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const renameRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  /** L6: roving tabindex — 记忆最后聚焦的会话；Tab 回到列表时恢复焦点 */
  const [focusedId, setFocusedId] = useState<string | null>(activeId);

  useEffect(() => {
    if (editingId) renameRef.current?.focus();
  }, [editingId]);

  // 打开会话后焦点跟随（activeId 变化 → focusedId 同步）
  useEffect(() => {
    if (activeId) setFocusedId(activeId);
  }, [activeId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return groups;
    return groups
      .map((g) => ({
        ...g,
        items: g.items.filter((t) => t.title.toLowerCase().includes(q)),
      }))
      .filter((g) => g.items.length > 0);
  }, [groups, query]);

  const total = groups.reduce((n, g) => n + g.items.length, 0);

  /** L1: 从过滤结果中分离置顶 / 非置顶 */
  const pinnedSet = useMemo(() => new Set(pinnedThreadIds), [pinnedThreadIds]);
  const pinnedItems = useMemo(() => {
    const all = filtered.flatMap((g) => g.items);
    return all.filter((t) => pinnedSet.has(t.id));
  }, [filtered, pinnedSet]);
  const unpinnedGroups = useMemo(
    () => filtered.map((g) => ({ ...g, items: g.items.filter((t) => !pinnedSet.has(t.id)) })).filter((g) => g.items.length > 0),
    [filtered, pinnedSet],
  );

  /** L6: 有效聚焦 id — focusedId 失效（删除/过滤后不在列表）时回落到首个可见会话，
   *  保证列表始终有一个 tab stop（W3C listbox：始终恰好一个 option 在 tab 序列）*/
  const effectiveFocusedId = useMemo(() => {
    if (focusedId) {
      const exists =
        pinnedItems.some((t) => t.id === focusedId) ||
        unpinnedGroups.some((g) => g.items.some((t) => t.id === focusedId));
      if (exists) return focusedId;
    }
    return pinnedItems[0]?.id ?? unpinnedGroups[0]?.items[0]?.id ?? null;
  }, [focusedId, pinnedItems, unpinnedGroups]);

  const commitRename = (id: string) => {
    const title = draft.trim();
    if (title) onRename(id, title);
    setEditingId(null);
    setDraft("");
  };

  /** L6: 键盘导航 — ↑↓ 在会话行间移动焦点，Home/End 跳首尾，Enter 打开（button 默认行为）。
   *  roving tabindex：仅聚焦行 tabIndex=0，其余 -1，Tab 键不逐个穿过列表 */
  const onKeyDownList = (e: React.KeyboardEvent) => {
    const root = listRef.current;
    if (!root) return;
    const buttons = Array.from(
      root.querySelectorAll<HTMLButtonElement>('.fnix-thread[data-id]'),
    );
    if (buttons.length === 0) return;
    const currentIndex = buttons.findIndex((b) => b === document.activeElement);
    switch (e.key) {
      case "ArrowDown":
      case "ArrowUp": {
        e.preventDefault();
        let nextIndex: number;
        if (currentIndex === -1) {
          nextIndex = 0;
        } else {
          nextIndex = e.key === "ArrowDown" ? currentIndex + 1 : currentIndex - 1;
          if (nextIndex < 0) nextIndex = buttons.length - 1;
          if (nextIndex >= buttons.length) nextIndex = 0;
        }
        buttons[nextIndex]?.focus();
        break;
      }
      case "Home":
        e.preventDefault();
        buttons[0]?.focus();
        break;
      case "End":
        e.preventDefault();
        buttons[buttons.length - 1]?.focus();
        break;
    }
  };

  /** 渲染单条会话行（置顶区与时间分组共用） */
  const renderThreadRow = (t: ChatThread, pinned: boolean) => {
    const on = activeId === t.id && hasSession;
    const editing = editingId === t.id;
    return (
      <div key={t.id} className={`fnix-thread-row${on ? " on" : ""}${pinned ? " pinned" : ""}`}>
        {editing ? (
          <form
            className="fnix-thread-rename"
            onSubmit={(e) => {
              e.preventDefault();
              commitRename(t.id);
            }}
          >
            <input
              ref={renameRef}
              value={draft}
              aria-label="重命名会话"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setEditingId(null);
                  setDraft("");
                }
              }}
            />
            <button type="submit" className="fnix-ibtn sm" title="保存" aria-label="保存名称">
              <Check size={13} />
            </button>
            <button
              type="button"
              className="fnix-ibtn sm"
              title="取消"
              aria-label="取消重命名"
              onClick={() => {
                setEditingId(null);
                setDraft("");
              }}
            >
              <X size={13} />
            </button>
          </form>
        ) : (
          <>
            <button
              type="button"
              className={`fnix-thread flat${on ? " on" : ""}`}
              data-id={t.id}
              onClick={() => onOpen(t.id)}
              onFocus={() => setFocusedId(t.id)}
              tabIndex={t.id === effectiveFocusedId ? 0 : -1}
              role="option"
              aria-selected={on}
            >
              <MessageSquare
                size={14}
                className={`fnix-thread-ico${streaming && activeId === t.id ? " run" : ""}`}
              />
              <span className="fnix-thread-title">{t.title}</span>
            </button>
            <div className="fnix-thread-ops">
              {onTogglePin && (
                <button
                  type="button"
                  className="fnix-ibtn sm"
                  title={pinned ? "取消置顶" : "置顶"}
                  aria-label={pinned ? `取消置顶 ${t.title}` : `置顶 ${t.title}`}
                  onClick={() => onTogglePin(t.id)}
                >
                  <Pin size={12} className={pinned ? "filled" : ""} />
                </button>
              )}
              <button
                type="button"
                className="fnix-ibtn sm"
                title="重命名"
                aria-label={`重命名 ${t.title}`}
                onClick={() => {
                  setEditingId(t.id);
                  setDraft(t.title);
                }}
              >
                <Pencil size={12} />
              </button>
              <button
                type="button"
                className="fnix-ibtn sm danger"
                title="删除"
                aria-label={`删除 ${t.title}`}
                onClick={() => {
                  if (window.confirm(`确定删除「${t.title}」吗？`)) onDelete(t.id);
                }}
              >
                <Trash2 size={12} />
              </button>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <>
      <div className="fnix-nav" style={{ paddingTop: 0 }}>
        {searchOpen || query ? (
          <div className="fnix-side-search">
            <Search size={14} />
            <input
              ref={searchRef}
              value={query}
              placeholder="按标题筛选…"
              aria-label="筛选会话"
              onChange={(e) => setQuery(e.target.value)}
              onBlur={() => {
                if (!query) setSearchOpen(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setQuery("");
                  setSearchOpen(false);
                }
              }}
            />
            <button
              type="button"
              className="fnix-ibtn sm"
              title="清除"
              aria-label="清除搜索"
              onClick={() => {
                setQuery("");
                setSearchOpen(false);
              }}
            >
              <X size={13} />
            </button>
          </div>
        ) : (
          <button
            type="button"
            className="fnix-nav-search"
            onClick={() => {
              setSearchOpen(true);
              window.setTimeout(() => searchRef.current?.focus(), 0);
            }}
            aria-label="搜索会话"
          >
            <Search size={15} />
            <span>搜索会话</span>
            <kbd>{navigator.platform?.includes("Mac") ? "⌘K" : "Ctrl+K"}</kbd>
          </button>
        )}
      </div>

      <div className="fnix-scroll" ref={listRef} onKeyDown={onKeyDownList}>
        {total === 0 && (
          <div className="fnix-side-empty">
            <MessageSquare size={22} />
            <p>{emptyHint}</p>
            {onNewChat ? (
              <button type="button" className="fnix-side-empty-cta" onClick={onNewChat}>
                <Plus size={14} /> 新任务
              </button>
            ) : null}
          </div>
        )}
        {total > 0 && filtered.length === 0 ? (
          <div className="fnix-side-hint">
            没有匹配「{query}」的会话
            <button
              type="button"
              className="fnix-side-hint-link"
              onClick={() => {
                setQuery("");
                setSearchOpen(false);
              }}
            >
              清除搜索
            </button>
          </div>
        ) : null}

        {/* listbox 仅包裹会话分组,空态/提示等 UI 留在外层,
            满足 aria-required-children(listbox 子元素须为 option/group) */}
        <div role="listbox" aria-label="会话列表">
          {/* L1: 置顶区 — 仅当有置顶项时渲染 */}
          {pinnedItems.length > 0 && (
            <div
              className="fnix-thread-group fnix-pinned-group"
              role="group"
              aria-label="置顶"
            >
              <div className="fnix-thread-group-h" role="presentation">
                置顶
              </div>
              {pinnedItems.map((t) => renderThreadRow(t, true))}
            </div>
          )}

          {unpinnedGroups.map((g) => (
            <div key={g.label} className="fnix-thread-group" role="group" aria-label={g.label}>
              {(unpinnedGroups.length > 1 || g.label !== "今天") && (
                <div className="fnix-thread-group-h" role="presentation">
                  {g.label}
                </div>
              )}
              {g.items.map((t) => renderThreadRow(t, false))}
            </div>
          ))}
        </div>

        {/* Spec 4: 可恢复任务 section — 中断/失败的长程任务可一键 resume */}
        {onResumeRun && (
          <ResumableRuns
            onResume={onResumeRun}
            disabled={streaming}
            refreshSignal={resumeRefreshSignal}
          />
        )}
      </div>
    </>
  );
}
