/**
 * Unified / plain 代码 diff 视图 — 支持按 hunk Accept。
 */

import { useMemo, useState, useEffect } from "react";
import { Copy, Check } from "lucide-react";
import { applySelectedHunks, splitUnifiedHunks, type DiffHunk } from "./diffHunks";
import { DIFF_PAGE_LINES } from "./windowing";

export interface DiffViewProps {
  path: string;
  diff?: string;
  content?: string;
  oldContent?: string;
  action?: string;
  maxLines?: number;
  /** When set, show per-hunk Accept controls. */
  onAcceptHunks?: (payload: {
    path: string;
    content: string;
    old_content?: string;
    action?: string;
  }) => void;
  disabled?: boolean;
}

interface DiffLine {
  type: "add" | "del" | "ctx" | "meta";
  text: string;
  oldNo?: number;
  newNo?: number;
}

function parseDiff(raw: string): DiffLine[] {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const out: DiffLine[] = [];
  let oldNo = 0;
  let newNo = 0;
  const isUnified = lines.some((l) => l.startsWith("@@") || l.startsWith("--- ") || l.startsWith("+++ "));

  if (!isUnified) {
    return lines.map((text, i) => ({
      type: "add" as const,
      text,
      newNo: i + 1,
    }));
  }

  for (const line of lines) {
    if (line.startsWith("@@")) {
      const m = line.match(/@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)/);
      if (m) {
        oldNo = Number(m[1]) - 1;
        newNo = Number(m[2]) - 1;
      }
      out.push({ type: "meta", text: line });
      continue;
    }
    if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("diff ") || line.startsWith("index ")) {
      out.push({ type: "meta", text: line });
      continue;
    }
    if (line.startsWith("+")) {
      newNo += 1;
      out.push({ type: "add", text: line.slice(1), newNo });
    } else if (line.startsWith("-")) {
      oldNo += 1;
      out.push({ type: "del", text: line.slice(1), oldNo });
    } else {
      const body = line.startsWith(" ") ? line.slice(1) : line;
      oldNo += 1;
      newNo += 1;
      out.push({ type: "ctx", text: body, oldNo, newNo });
    }
  }
  return out;
}

function countHunks(lines: DiffLine[]): { add: number; del: number; hunks: number } {
  let add = 0;
  let del = 0;
  let hunks = 0;
  for (const l of lines) {
    if (l.type === "add") add += 1;
    else if (l.type === "del") del += 1;
    else if (l.type === "meta" && l.text.startsWith("@@")) hunks += 1;
  }
  if (hunks === 0 && (add > 0 || del > 0)) hunks = 1;
  return { add, del, hunks };
}

function hunkBodyLines(hunk: DiffHunk): DiffLine[] {
  return hunk.lines.map((l) => ({
    type: l.kind === "add" ? "add" : l.kind === "del" ? "del" : "ctx",
    text: l.text,
  }));
}

export function DiffView({
  path,
  diff,
  content,
  oldContent,
  action,
  maxLines = 120,
  onAcceptHunks,
  disabled,
}: DiffViewProps) {
  const [copied, setCopied] = useState(false);
  const raw = (diff && diff.trim()) || (content && content.trim()) || "";
  const lines = useMemo(() => parseDiff(raw), [raw]);
  const stats = useMemo(() => countHunks(lines), [lines]);
  const hunks = useMemo(() => splitUnifiedHunks(raw), [raw]);
  const [accepted, setAccepted] = useState<boolean[]>(() => hunks.map(() => true));

  useEffect(() => {
    setAccepted(hunks.map(() => true));
  }, [raw, hunks.length]);

  const [limit, setLimit] = useState(maxLines);
  useEffect(() => {
    setLimit(maxLines);
  }, [raw, maxLines]);

  // 多 hunk 模式下每个 hunk 的展开状态：默认截断显示前 N 行，
  // 用户点击"展开此代码块"后该 hunk 显示全部行（原代码截断后无展开入口）
  const [expandedHunks, setExpandedHunks] = useState<Set<number>>(new Set());
  useEffect(() => {
    setExpandedHunks(new Set());
  }, [raw]);

  const canHunk =
    Boolean(onAcceptHunks) &&
    hunks.length > 0 &&
    (Boolean(oldContent) || hunks.length === 1 || Boolean(content));

  const shown = lines.slice(0, limit);
  const truncated = lines.length > limit;

  const toggleHunk = (idx: number) => {
    setAccepted((prev) => {
      const next = [...prev];
      next[idx] = !next[idx];
      return next;
    });
  };

  const acceptSelected = () => {
    if (!onAcceptHunks) return;
    const selectedCount = accepted.filter(Boolean).length;
    if (selectedCount === 0) return;

    let nextContent: string;
    if (oldContent != null && oldContent !== undefined) {
      nextContent = applySelectedHunks(oldContent, hunks, accepted);
    } else if (selectedCount === hunks.length && content) {
      nextContent = content;
    } else if (hunks.length === 1 && content) {
      nextContent = content;
    } else {
      // Fallback: join accepted additions only
      nextContent = hunks
        .filter((_, i) => accepted[i])
        .flatMap((h) => h.lines.filter((l) => l.kind === "add" || l.kind === "ctx").map((l) => l.text))
        .join("\n");
    }

    onAcceptHunks({
      path,
      content: nextContent,
      old_content: oldContent,
      action: action || "modify",
    });
  };

  return (
    <div className="oai-diffview">
      <div className="oai-diffview-h">
        <div className="oai-diffview-path" title={path}>
          <span className="act">{action || "modify"}</span>
          <span className="p">{path}</span>
        </div>
        <div className="oai-diffview-meta">
          {stats.add > 0 ? <span className="add">+{stats.add}</span> : null}
          {stats.del > 0 ? <span className="del">−{stats.del}</span> : null}
          {stats.hunks > 0 ? <span className="hunks">{stats.hunks} hunks</span> : null}
          {canHunk ? (
            <button
              type="button"
              className="oai-review-btn solid sm"
              disabled={disabled || accepted.every((a) => !a)}
              onClick={acceptSelected}
              title="确认选中的代码块"
            >
              确认代码块
            </button>
          ) : null}
          <button
            type="button"
            className="oai-ibtn sm"
            title="复制路径"
            aria-label="复制路径"
            onClick={() => {
              void navigator.clipboard.writeText(path).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1200);
              });
            }}
          >
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
        </div>
      </div>

      {canHunk && hunks.length > 1 ? (
        <div className="oai-diffview-body" role="group" aria-label={`Hunks for ${path}`}>
          {hunks.map((h, hi) => {
            const allBody = hunkBodyLines(h);
            const defaultLimit = Math.max(8, Math.floor(maxLines / hunks.length));
            const isExpanded = expandedHunks.has(hi);
            const body = isExpanded ? allBody : allBody.slice(0, defaultLimit);
            const hunkTruncated = allBody.length > defaultLimit && !isExpanded;
            return (
              <div key={hi} className={`oai-hunk${accepted[hi] ? " on" : ""}`}>
                <div className="oai-hunk-h">
                  <label className="oai-hunk-toggle">
                    <input
                      type="checkbox"
                      checked={accepted[hi] !== false}
                      disabled={disabled}
                      onChange={() => toggleHunk(hi)}
                    />
                    <span>Hunk {hi + 1}</span>
                  </label>
                  <code className="oai-hunk-meta">{h.header}</code>
                </div>
                {body.map((l, i) => (
                  <div key={i} className={`oai-dline ${l.type}`}>
                    <span className="sign">
                      {l.type === "add" ? "+" : l.type === "del" ? "−" : " "}
                    </span>
                    <code className="tx">{l.text || " "}</code>
                  </div>
                ))}
                {hunkTruncated ? (
                  <button
                    type="button"
                    className="oai-diffview-more"
                    onClick={() =>
                      setExpandedHunks((prev) => {
                        const next = new Set(prev);
                        next.add(hi);
                        return next;
                      })
                    }
                  >
                    展开此代码块（共 {allBody.length} 行，剩余 {allBody.length - body.length} 行）
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="oai-diffview-body" role="table" aria-label={`Diff ${path}`}>
          {shown.length === 0 ? (
            <div className="oai-diffview-empty">无内容</div>
          ) : (
            shown.map((l, i) => (
              <div key={i} className={`oai-dline ${l.type}`}>
                <span className="ln old">{l.type === "add" ? "" : l.oldNo ?? ""}</span>
                <span className="ln new">{l.type === "del" ? "" : l.newNo ?? ""}</span>
                <span className="sign">
                  {l.type === "add" ? "+" : l.type === "del" ? "−" : l.type === "meta" ? "" : " "}
                </span>
                <code className="tx">{l.text || " "}</code>
              </div>
            ))
          )}
          {truncated ? (
            <button
              type="button"
              className="oai-diffview-more"
              onClick={() => setLimit((n) => n + DIFF_PAGE_LINES)}
            >
              Show more lines ({lines.length - limit} remaining)
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
