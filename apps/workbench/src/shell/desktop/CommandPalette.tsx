/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** ⌘K 命令面板 — 全局搜索会话 + 快捷命令，全键盘可达。 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import {
  Activity,
  Briefcase,
  Code2,
  FolderOpen,
  MessageSquare,
  Plus,
  Search,
  Settings,
} from "lucide-react";

export interface PaletteThread {
  id: string;
  title: string;
  updatedAt?: number;
}

interface PaletteCommand {
  id: string;
  label: string;
  hint?: string;
  icon: ReactNode;
  run: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  threads: PaletteThread[];
  mode: "work" | "code";
  onOpenThread: (id: string) => void;
  onNewChat: () => void;
  onOpenSettings: () => void;
  onToggleMode: () => void;
  onOpenBenchmark: () => void;
  onOpenFolder: () => void;
}

export function CommandPalette(props: CommandPaletteProps) {
  const { open, onClose } = props;
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const t = window.setTimeout(() => inputRef.current?.focus(), 40);
    return () => window.clearTimeout(t);
  }, [open]);

  const commands = useMemo<PaletteCommand[]>(
    () => [
      {
        id: "new",
        label: props.mode === "work" ? "新建任务" : "新建代码会话",
        icon: <Plus size={15} />,
        run: () => props.onNewChat(),
      },
      {
        id: "toggle-mode",
        label: props.mode === "work" ? "切换到 Code" : "切换到 Work",
        hint: "产品模式",
        icon: props.mode === "work" ? <Code2 size={15} /> : <Briefcase size={15} />,
        run: () => props.onToggleMode(),
      },
      {
        id: "folder",
        label: "打开文件夹…",
        icon: <FolderOpen size={15} />,
        run: () => props.onOpenFolder(),
      },
      {
        id: "settings",
        label: "打开设置",
        icon: <Settings size={15} />,
        run: () => props.onOpenSettings(),
      },
      {
        id: "benchmark",
        label: "打开 Benchmark",
        icon: <Activity size={15} />,
        run: () => props.onOpenBenchmark(),
      },
    ],
    [props],
  );

  const q = query.trim().toLowerCase();
  const filteredCommands = useMemo(
    () => (q ? commands.filter((c) => c.label.toLowerCase().includes(q)) : commands),
    [commands, q],
  );
  const filteredThreads = useMemo(
    () =>
      (q ? props.threads.filter((t) => t.title.toLowerCase().includes(q)) : props.threads).slice(0, 8),
    [props.threads, q],
  );

  type Row =
    | { kind: "cmd"; cmd: PaletteCommand }
    | { kind: "thread"; thread: PaletteThread };
  const rows = useMemo<Row[]>(
    () => [
      ...filteredCommands.map((cmd): Row => ({ kind: "cmd", cmd })),
      ...filteredThreads.map((thread): Row => ({ kind: "thread", thread })),
    ],
    [filteredCommands, filteredThreads],
  );

  useEffect(() => {
    setCursor(0);
  }, [q]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${cursor}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  if (!open) return null;

  const pick = (row: Row) => {
    onClose();
    if (row.kind === "cmd") row.cmd.run();
    else props.onOpenThread(row.thread.id);
  };

  const onKeyDown = (e: ReactKeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const row = rows[cursor];
      if (row) pick(row);
    }
  };

  return (
    <div className="fnix-palette-overlay" role="button" tabIndex={-1} aria-label="关闭命令面板" onClick={onClose} onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div
        className="fnix-palette"
        role="dialog"
        aria-modal="true"
        aria-label="命令面板"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="fnix-palette-input-row">
          <Search size={15} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="搜索会话，或输入命令…"
            aria-label="搜索会话或命令"
          />
          <kbd>Esc</kbd>
        </div>
        <div className="fnix-palette-list" ref={listRef}>
          {rows.map((row, i) => {
            const prev = rows[i - 1];
            const group =
              !prev || prev.kind !== row.kind ? (row.kind === "cmd" ? "命令" : "会话") : null;
            const icon = row.kind === "cmd" ? row.cmd.icon : <MessageSquare size={15} />;
            const label = row.kind === "cmd" ? row.cmd.label : row.thread.title || "未命名会话";
            const hint = row.kind === "cmd" ? row.cmd.hint : undefined;
            return (
              <div key={row.kind === "cmd" ? `c-${row.cmd.id}` : `t-${row.thread.id}`}>
                {group ? <div className="fnix-palette-group">{group}</div> : null}
                <button
                  type="button"
                  data-idx={i}
                  className={`fnix-palette-item${i === cursor ? " on" : ""}`}
                  onMouseEnter={() => setCursor(i)}
                  onClick={() => pick(row)}
                >
                  <span className="fnix-palette-ico">{icon}</span>
                  <span className="fnix-palette-label">{label}</span>
                  {hint ? <span className="fnix-palette-hint">{hint}</span> : null}
                </button>
              </div>
            );
          })}
          {rows.length === 0 && <div className="fnix-palette-empty">无匹配结果</div>}
        </div>
      </div>
    </div>
  );
}
