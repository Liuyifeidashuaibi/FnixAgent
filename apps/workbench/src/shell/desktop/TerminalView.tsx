/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * TerminalView — 智能体执行流（右侧工作台 · 终端）
 * ============================================================
 * 把今天藏在"思考过程"抽屉里的 ActivityItem 流，以终端的形态放进工作台。
 * 范式：FnixAgent 是"智能体干活、用户验收"，所以终端是**只读执行流**，
 *       让用户实时看见智能体在做什么（调工具 / 执行命令 / 读写文件 / 出错）。
 *
 * 交互：
 *   - 流式期间自动钉底；用户向上滚即暂停跟随，出现"↓ 最新"浮动按钮
 *   - 过滤：全部 / 执行(run+test) / 工具(tool) / 错误(error)
 *   - 有 detail 的行可点击展开（工具输出 / 错误堆栈）
 *   - running 行呼吸圆点，error 红色，done 淡绿 ✓
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  ArrowDownToLine,
  Check,
  ChevronRight,
  Eye,
  Flag,
  FlaskConical,
  ListTree,
  PenLine,
  Sparkles,
  SquareTerminal,
  Wrench,
  XCircle,
} from "lucide-react";
import type { ActivityItem, ActivityKind } from "./activityTypes";

interface Props {
  activities: ActivityItem[];
  streaming: boolean;
}

type Filter = "all" | "exec" | "tool" | "error";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "全部" },
  { id: "exec", label: "执行" },
  { id: "tool", label: "工具" },
  { id: "error", label: "错误" },
];

/** 类型 → 图标 + 着色类名 */
const KIND_META: Record<ActivityKind, { icon: ReactNode; cls: string }> = {
  run: { icon: <SquareTerminal size={13} />, cls: "run" },
  test: { icon: <FlaskConical size={13} />, cls: "run" },
  tool: { icon: <Wrench size={13} />, cls: "tool" },
  edit: { icon: <PenLine size={13} />, cls: "write" },
  write: { icon: <PenLine size={13} />, cls: "write" },
  read: { icon: <Eye size={13} />, cls: "read" },
  plan: { icon: <ListTree size={13} />, cls: "think" },
  think: { icon: <Sparkles size={13} />, cls: "think" },
  mission: { icon: <Flag size={13} />, cls: "tool" },
  done: { icon: <Check size={13} />, cls: "ok" },
  error: { icon: <XCircle size={13} />, cls: "err" },
};

const pad2 = (n: number) => String(n).padStart(2, "0");
const fmtTime = (ts: number) => {
  const d = new Date(ts);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
};
const fmtElapsed = (a: ActivityItem) => {
  if (!a.endedAt) return "";
  const ms = a.endedAt - a.startedAt;
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
};

const matchFilter = (a: ActivityItem, f: Filter): boolean => {
  if (f === "all") return true;
  if (f === "exec") return a.kind === "run" || a.kind === "test";
  if (f === "tool") return a.kind === "tool";
  return a.status === "error" || a.kind === "error";
};

export function TerminalView({ activities, streaming }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showJump, setShowJump] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);

  const rows = useMemo(() => activities.filter((a) => matchFilter(a, filter)), [activities, filter]);

  // 新一轮运行开始时恢复跟随（先于自动钉底执行，保证本轮滚回底部）
  useEffect(() => {
    if (streaming) followRef.current = true;
  }, [streaming]);

  // 跟随开启时，内容增长即钉底（钉底触发 onScroll → 收回"最新"按钮）
  useEffect(() => {
    const el = scrollRef.current;
    if (el && followRef.current) el.scrollTop = el.scrollHeight;
  }, [rows, streaming]);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    followRef.current = atBottom;
    setShowJump(!atBottom);
  }, []);

  const jumpToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    followRef.current = true;
    el.scrollTop = el.scrollHeight;
    setShowJump(false);
  }, []);

  return (
    <div className="fnx-terminal">
      <div className="fnx-terminal-bar">
        <span className="fnx-terminal-title">
          执行流
          {rows.length > 0 ? <i className="fnx-terminal-count">{rows.length}</i> : null}
        </span>
        <div className="fnx-terminal-seg" role="tablist" aria-label="过滤执行流">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              role="tab"
              aria-selected={filter === f.id}
              className={`fnx-terminal-seg-btn${filter === f.id ? " on" : ""}`}
              onClick={() => setFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={scrollRef}
        className="fnx-terminal-body"
        role="log"
        aria-live="polite"
        aria-label="智能体执行流"
        onScroll={onScroll}
      >
        {rows.length === 0 ? (
          <div className="fnx-studio-empty">
            <SquareTerminal size={28} />
            <p>智能体开始工作后，执行过程会在这里实时呈现</p>
            <p className="dim">调工具 · 执行命令 · 读写文件 · 出错重试</p>
          </div>
        ) : (
          rows.map((a) => {
            const meta = KIND_META[a.kind] ?? KIND_META.tool;
            const expanded = expandedId === a.id && !!a.detail;
            return (
              <div
                key={a.id}
                className={`fnx-term-line${a.status === "running" ? " is-running" : ""}${
                  a.status === "error" ? " is-error" : ""
                }`}
              >
                <button
                  type="button"
                  className={`fnx-term-row${a.detail ? " has-detail" : ""}`}
                  onClick={() => a.detail && setExpandedId(expanded ? null : a.id)}
                  aria-expanded={a.detail ? expanded : undefined}
                >
                  <span className="fnx-term-time">{fmtTime(a.startedAt)}</span>
                  <span className={`fnx-term-ico ${meta.cls}`}>{meta.icon}</span>
                  <span className="fnx-term-text">
                    <span className="fnx-term-name">{a.title}</span>
                    {a.meta ? <span className="fnx-term-meta">{a.meta}</span> : null}
                  </span>
                  <span className="fnx-term-end">
                    {a.status === "running" ? (
                      <i className="fnx-term-pulse" aria-label="执行中" />
                    ) : a.status === "error" ? (
                      <XCircle size={12} className="fnx-term-status err" aria-label="失败" />
                    ) : a.status === "needs_input" ? (
                      <span className="fnx-term-status wait">?</span>
                    ) : (
                      <Check size={12} className="fnx-term-status ok" aria-label="完成" />
                    )}
                    {fmtElapsed(a) ? <span className="fnx-term-elapsed">{fmtElapsed(a)}</span> : null}
                    {a.detail ? (
                      <ChevronRight size={12} className={`fnx-term-chev${expanded ? " open" : ""}`} />
                    ) : null}
                  </span>
                </button>
                {expanded && a.detail ? <pre className="fnx-term-detail">{a.detail}</pre> : null}
              </div>
            );
          })
        )}
      </div>

      <button
        type="button"
        className={`fnx-terminal-jump${showJump ? " show" : ""}`}
        onClick={jumpToBottom}
        aria-hidden={!showJump}
        tabIndex={showJump ? 0 : -1}
      >
        <ArrowDownToLine size={13} />
        最新
      </button>
    </div>
  );
}
