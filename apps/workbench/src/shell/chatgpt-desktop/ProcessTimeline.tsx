/** Agent 执行控制台：真实动作、证据和控制，不展示原始 chain-of-thought。 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
} from "lucide-react";
import type { ActivityItem, ActivityKind } from "./activityTypes";

interface Props {
  items: ActivityItem[];
  streaming?: boolean;
  onStop?: () => void;
  onOpenDiff?: (path: string) => void;
  compact?: boolean;
}

type Filter = "all" | "files" | "commands" | "issues";

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
  if (item.kind === "mission") return false;
  if (item.meta === "evolution" || item.meta === "pipeline" || item.meta === "reflection→HERA") return false;
  if (item.title.startsWith("KTG ") || item.title.startsWith("Pipeline step")) return false;
  return true;
}

function matchesFilter(item: ActivityItem, filter: Filter): boolean {
  if (filter === "files") return ["read", "edit", "write"].includes(item.kind);
  if (filter === "commands") return item.kind === "run" || item.kind === "test";
  if (filter === "issues") return item.status === "error" || item.kind === "error";
  return true;
}

function formatElapsed(startedAt: number, endedAt: number): string {
  const seconds = Math.max(0, Math.floor((endedAt - startedAt) / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function statusText(item: ActivityItem): string {
  if (item.status === "running") return "进行中";
  if (item.status === "error") return "失败";
  if (item.status === "cancelled") return "已停止";
  if (item.status === "needs_input") return "等待操作";
  return "完成";
}

export function ProcessTimeline({
  items,
  streaming = false,
  onStop,
  onOpenDiff,
  compact,
}: Props) {
  const [open, setOpen] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [now, setNow] = useState(0);
  const bodyRef = useRef<HTMLDivElement>(null);
  const visibleItems = useMemo(() => items.filter(isUsefulActivity), [items]);
  const filteredItems = useMemo(
    () => visibleItems.filter((item) => matchesFilter(item, filter)),
    [filter, visibleItems],
  );

  useEffect(() => {
    if (!streaming) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [streaming]);

  useEffect(() => {
    if (!streaming || !open || !bodyRef.current) return;
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [items.length, open, streaming]);

  if (visibleItems.length === 0) return null;

  const running = [...visibleItems].reverse().find((item) => item.status === "running");
  const errors = visibleItems.filter((item) => item.status === "error" || item.kind === "error").length;
  const cancelled = visibleItems.some((item) => item.status === "cancelled");
  const latest = visibleItems[visibleItems.length - 1];
  const summary = running?.title || latest?.title || "执行过程";
  const fileCount = new Set(visibleItems.map((item) => item.path).filter(Boolean)).size;
  const commandCount = visibleItems.filter((item) => item.kind === "run" || item.kind === "test").length;
  const start = Math.min(...visibleItems.map((item) => item.startedAt));
  const end = Math.max(...visibleItems.map((item) => item.endedAt || now || item.startedAt));
  const rows = filteredItems.slice(-24);
  const hiddenRows = filteredItems.length - rows.length;
  const state = running ? "running" : errors ? "error" : cancelled ? "cancelled" : "done";

  return (
    <section
      className={`oai-agent-process ${state}${open ? " open" : ""}${compact ? " compact" : ""}`}
      aria-label="执行过程"
    >
      <div className="oai-agent-process-head">
        <button
          type="button"
          className="oai-agent-process-toggle"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="agent-process-events"
        >
          <span className="oai-agent-process-state" aria-hidden>
            {running ? <Loader2 size={15} className="spin" /> : errors ? <CircleAlert size={15} /> : <Check size={15} />}
          </span>
          <span className="oai-agent-process-heading">
            <span className="oai-agent-process-summary">{summary}</span>
            <span className="oai-agent-process-meta">
              {running ? "正在执行" : errors ? "执行遇到问题" : cancelled ? "已停止" : "执行完成"}
              {` · ${formatElapsed(start, end)} · ${visibleItems.length} 项操作`}
              {fileCount ? ` · ${fileCount} 个文件` : ""}
            </span>
          </span>
          <ChevronDown size={15} className="oai-agent-process-chevron" aria-hidden />
        </button>
        {streaming && onStop ? (
          <button type="button" className="oai-agent-process-stop" onClick={onStop} title="停止执行">
            <Square size={11} fill="currentColor" />
            停止
          </button>
        ) : null}
      </div>

      {open ? (
        <>
          <div className="oai-agent-process-toolbar" aria-label="筛选执行记录">
            {([
              ["all", "全部", visibleItems.length],
              ["files", "文件", fileCount],
              ["commands", "命令", commandCount],
              ["issues", "问题", errors],
            ] as const).map(([id, label, count]) => (
              <button
                key={id}
                type="button"
                className={filter === id ? "active" : ""}
                onClick={() => setFilter(id)}
                disabled={id !== "all" && count === 0}
              >
                {id === "files" ? <Files size={12} /> : null}
                {label}<span>{count}</span>
              </button>
            ))}
          </div>
          <div id="agent-process-events" className="oai-agent-process-body" ref={bodyRef} role="log" aria-live="polite">
            {hiddenRows > 0 ? <div className="oai-agent-process-hidden">更早的 {hiddenRows} 项操作已收起</div> : null}
            {rows.length > 0 ? rows.map((item) => {
              const hasDetail = Boolean(item.detail?.trim());
              const isOpen = Boolean(expanded[item.id]);
              const canOpenDiff = Boolean(item.path && onOpenDiff && (item.kind === "edit" || item.kind === "write"));
              return (
                <article key={item.id} className={`oai-agent-event ${item.status} kind-${item.kind}`}>
                  <span className="oai-agent-event-icon" aria-hidden>
                    {item.status === "running" ? <Loader2 size={14} className="spin" /> : KIND_ICON[item.kind]}
                  </span>
                  <div className="oai-agent-event-main">
                    <div className="oai-agent-event-line">
                      <span className="oai-agent-event-title">{item.title}</span>
                      <span className="oai-agent-event-status">{statusText(item)}</span>
                      <time>{formatElapsed(item.startedAt, item.endedAt || now)}</time>
                    </div>
                    {item.path ? (
                      <button
                        type="button"
                        className="oai-agent-event-path"
                        onClick={canOpenDiff ? () => onOpenDiff?.(item.path!) : undefined}
                        disabled={!canOpenDiff}
                        title={item.path}
                      >
                        {item.path}
                      </button>
                    ) : null}
                    <div className="oai-agent-event-actions">
                      {hasDetail ? (
                        <button
                          type="button"
                          onClick={() => setExpanded((prev) => ({ ...prev, [item.id]: !prev[item.id] }))}
                          aria-expanded={isOpen}
                        >
                          {isOpen ? "收起证据" : item.kind === "think" ? "查看分析摘要" : "查看输出"}
                        </button>
                      ) : null}
                      {canOpenDiff ? <button type="button" onClick={() => onOpenDiff?.(item.path!)}>查看 Diff</button> : null}
                      {item.meta && item.meta !== item.title ? <span>{item.meta}</span> : null}
                    </div>
                    {isOpen && item.detail ? <pre className="oai-agent-event-detail">{item.detail}</pre> : null}
                  </div>
                </article>
              );
            }) : <div className="oai-agent-process-empty">此筛选下暂无记录</div>}
          </div>
        </>
      ) : null}
    </section>
  );
}
