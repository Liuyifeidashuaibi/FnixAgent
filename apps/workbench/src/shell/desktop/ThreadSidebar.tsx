/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code is proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Sidebar thread list — 极简版。
 * 无空间的任务排最上面，只显示任务名（不分组）。
 * 有空间的按空间分组，可展开/收起，组内按时间倒序。
 * 状态点：绿色=完成、红色=失败、橙色脉冲=进行中、灰色=空闲。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronRight, Pencil, Trash2, X } from "lucide-react";
import type { ChatThread } from "./useChatFlow";

export interface ThreadWithWorkspace extends ChatThread {
  workspace: string;
  status?: "idle" | "running" | "done" | "failed";
}

interface Props {
  threads: ThreadWithWorkspace[];
  activeId: string | null;
  hasSession: boolean;
  streaming: boolean;
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

const NO_WORKSPACE = "__fnix_desktop__";

/** 从 project_path 提取展示名 */
function workspaceLabel(ws: string): string {
  if (!ws || ws === NO_WORKSPACE) return "无空间";
  const parts = ws.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts[parts.length - 1] || ws;
}

export function ThreadSidebar({
  threads,
  activeId,
  hasSession,
  streaming,
  onOpen,
  onRename,
  onDelete,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const renameRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [focusedId, setFocusedId] = useState<string | null>(activeId);
  // 工作空间分组的展开/收起状态，默认全部展开
  const [collapsedWs, setCollapsedWs] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (editingId) renameRef.current?.focus();
  }, [editingId]);

  useEffect(() => {
    if (activeId) setFocusedId(activeId);
  }, [activeId]);

  // 分组：无空间的直接平铺 + 有空间的分组
  const { noWsThreads, wsGroups } = useMemo(() => {
    const noWs: ThreadWithWorkspace[] = [];
    const wsMap = new Map<string, ThreadWithWorkspace[]>();
    for (const t of threads) {
      const ws = t.workspace || NO_WORKSPACE;
      if (ws === NO_WORKSPACE) {
        noWs.push(t);
      } else {
        if (!wsMap.has(ws)) wsMap.set(ws, []);
        wsMap.get(ws)!.push(t);
      }
    }
    // 无空间按时间倒序
    noWs.sort((a, b) => b.updatedAt - a.updatedAt);
    // 有空间分组，每组内按时间倒序，组间按最近任务时间倒序
    const groups = Array.from(wsMap.entries())
      .map(([ws, items]) => ({
        ws,
        label: workspaceLabel(ws),
        items: items.sort((a, b) => b.updatedAt - a.updatedAt),
      }))
      .sort((a, b) => {
        const aMax = Math.max(...a.items.map((t) => t.updatedAt));
        const bMax = Math.max(...b.items.map((t) => t.updatedAt));
        return bMax - aMax;
      });
    return { noWsThreads: noWs, wsGroups: groups };
  }, [threads]);

  const toggleWs = (ws: string) => {
    setCollapsedWs((prev) => {
      const next = new Set(prev);
      if (next.has(ws)) next.delete(ws);
      else next.add(ws);
      return next;
    });
  };

  const commitRename = (id: string) => {
    const title = draft.trim();
    if (title) onRename(id, title);
    setEditingId(null);
    setDraft("");
  };

  // 键盘导航
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

  const statusDot = (s: string) => {
    if (s === "running") return "fnix-dot running";
    if (s === "failed") return "fnix-dot failed";
    if (s === "done") return "fnix-dot done";
    return "fnix-dot idle";
  };

  const renderThreadRow = (t: ThreadWithWorkspace) => {
    const on = activeId === t.id && hasSession;
    const editing = editingId === t.id;
    const isActive = streaming && activeId === t.id;
    const status = isActive ? "running" : t.status || "done";

    return (
      <div key={t.id} className={`fnix-thread-row${on ? " on" : ""}`}>
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
              aria-label="重命名任务"
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
              tabIndex={t.id === focusedId ? 0 : -1}
              role="option"
              aria-selected={on}
            >
              <span className={statusDot(status)} aria-hidden />
              <span className="fnix-thread-title">{t.title}</span>
            </button>
            <div className="fnix-thread-ops">
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

  if (threads.length === 0) return null;

  return (
    <div className="fnix-scroll" ref={listRef} onKeyDown={onKeyDownList}>
      <div role="listbox" aria-label="任务列表">
        {/* 无空间的任务 — 直接平铺，不分组 */}
        {noWsThreads.map((t) => renderThreadRow(t))}

        {/* 有空间的任务 — 分组，可展开/收起 */}
        {wsGroups.map((g) => {
          const collapsed = collapsedWs.has(g.ws);
          return (
            <div key={g.ws} className="fnix-ws-group" role="group" aria-label={g.label}>
              <button
                type="button"
                className="fnix-ws-group-h"
                onClick={() => toggleWs(g.ws)}
                aria-expanded={!collapsed}
              >
                <ChevronRight
                  size={12}
                  className={`fnix-ws-chevron${collapsed ? "" : " open"}`}
                />
                <span className="fnix-ws-group-label">{g.label}</span>
                <span className="fnix-ws-group-count">{g.items.length}</span>
              </button>
              {!collapsed && g.items.map((t) => renderThreadRow(t))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
