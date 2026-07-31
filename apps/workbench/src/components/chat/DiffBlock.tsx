/**
 * DiffBlock — inline diff summary with per-file/per-hunk Accept/Reject.
 *
 * 调研证据：
 * - Cursor 论坛 "Bring back per-change Apply + inline diff review"（6K views, 386 likes）：
 *   "per-proposal or per-turn Apply/Reject"
 *   "Clear separation between preview/pending and applied to disk"
 * - Claude Code GitHub Issue #31395:
 *   "per-hunk accept/discard controls inline"
 *   "A summary bar shows how many hunks are pending review across all modified files"
 * - Cline: "every edit shows up as a diff you can review, modify, or revert"
 * - StackOverflow "How do IDEs like Cursor implement diff based code editing":
 *   "shows a diff, lets you accept/reject per hunk, feels like git add -p"
 *
 * 设计取舍：
 * - 对话气泡内只显示紧凑摘要条（文件名 + +/-行数 + 状态），不塞完整 diff
 * - 点击展开文件列表，每个文件可 Accept/Reject
 * - 明确区分 pending（待审查）/ applied（已接受）/ rejected（已拒绝）三状态
 */

import { useState } from "react";
import { Check, X, FileCode, ChevronRight, ChevronDown, CircleDot, Pin } from "lucide-react";

/** 单个文件的 diff 条目 */
export interface DiffEntry {
  /** 文件路径 */
  path: string;
  /** 新增行数 */
  added: number;
  /** 删除行数 */
  removed: number;
  /** diff 内容（可选，点击展开时用） */
  diff?: string;
  /** 该文件的 hunk 列表（可选，支持 per-hunk 审查） */
  hunks?: DiffHunk[];
}

/** 单个 hunk（代码块级别的变更） */
export interface DiffHunk {
  /** hunk 起始行号 */
  startLine: number;
  /** hunk 内容 */
  content: string;
}

/** 文件审查状态 */
type FileStatus = "pending" | "accepted" | "rejected";

export interface DiffBlockProps {
  /** 单文件或多文件 diff 条目 */
  entries: DiffEntry[];
  /** 接受单文件回调 */
  onAccept?: (path: string) => void;
  /** 拒绝单文件回调 */
  onReject?: (path: string) => void;
  /** 全部接受回调 */
  onAcceptAll?: () => void;
  /** 钉选文件到 Canvas Dock（对标 Cursor Canvas pin）*/
  onPin?: (path: string) => void;
  /**
   * 只读模式：用于消息气泡内的 diff 摘要展示。
   * 隐藏 Accept/Reject/AcceptAll/Pin 等动作按钮，避免用户误以为点击 Accept 已写盘
   * （实际 onAccept 未传入时不会调用后端）。改为显示「前往评审面板操作」引导。
   */
  readOnly?: boolean;
}

export default function DiffBlock({ entries, onAccept, onReject, onAcceptAll, onPin, readOnly = false }: DiffBlockProps) {
  const [expanded, setExpanded] = useState(false);
  const [fileStatuses, setFileStatuses] = useState<Record<string, FileStatus>>({});

  const totalAdded = entries.reduce((s, e) => s + e.added, 0);
  const totalRemoved = entries.reduce((s, e) => s + e.removed, 0);
  const pendingCount = entries.filter(e => fileStatuses[e.path] !== "accepted" && fileStatuses[e.path] !== "rejected").length;
  const acceptedCount = entries.filter(e => fileStatuses[e.path] === "accepted").length;

  const handleAccept = (path: string) => {
    setFileStatuses(prev => ({ ...prev, [path]: "accepted" }));
    onAccept?.(path);
  };
  const handleReject = (path: string) => {
    setFileStatuses(prev => ({ ...prev, [path]: "rejected" }));
    onReject?.(path);
  };

  return (
    <div className="cl-diff-block">
      {/* 摘要条 */}
      <div
        className="cl-diff-summary"
        onClick={() => entries.length > 1 && setExpanded(!expanded)}
        role={entries.length > 1 ? "button" : undefined}
      >
        <FileCode size={12} className="cl-diff-icon" />
        <span className="cl-diff-count">
          {entries.length === 1 ? entries[0].path : `${entries.length} files changed`}
        </span>
        <span className="cl-diff-stats">
          <span className="cl-diff-added">+{totalAdded}</span>
          <span className="cl-diff-removed">-{totalRemoved}</span>
        </span>
        {/* 状态指示器：明确区分 pending/applied */}
        {pendingCount === 0 ? (
          <span className="cl-diff-status cl-diff-status--done">
            <Check size={10} /> reviewed
          </span>
        ) : (
          <span className="cl-diff-status cl-diff-status--pending">
            <CircleDot size={10} /> {pendingCount} pending
          </span>
        )}
        {entries.length > 1 && (
          <button className="cl-diff-expand" type="button">
            {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          </button>
        )}
      </div>

      {/* 多文件展开列表 */}
      {expanded && entries.length > 1 && (
        <div className="cl-diff-files">
          {entries.map(entry => {
            const status = fileStatuses[entry.path] || "pending";
            return (
              <div key={entry.path} className={`cl-diff-file-row cl-diff-file-row--${status}`}>
                <span className="cl-diff-file-name">{entry.path}</span>
                <span className="cl-diff-file-stats">
                  <span className="cl-diff-added">+{entry.added}</span>
                  <span className="cl-diff-removed">-{entry.removed}</span>
                </span>
                {!readOnly && status === "pending" && (
                  <div className="cl-diff-file-actions">
                    {onPin && (
                      <button className="cl-diff-btn cl-diff-btn--pin" onClick={() => onPin(entry.path)} type="button" title="钉选到画布">
                        <Pin size={12} />
                      </button>
                    )}
                    <button className="cl-diff-btn cl-diff-btn--accept" onClick={() => handleAccept(entry.path)} type="button" title="Accept this file's changes">
                      <Check size={10} />
                    </button>
                    <button className="cl-diff-btn cl-diff-btn--reject" onClick={() => handleReject(entry.path)} type="button" title="Reject this file's changes">
                      <X size={10} />
                    </button>
                  </div>
                )}
                {status === "accepted" && <span className="cl-diff-badge cl-diff-badge--accept">accepted</span>}
                {status === "rejected" && <span className="cl-diff-badge cl-diff-badge--reject">rejected</span>}
              </div>
            );
          })}
          {!readOnly && pendingCount > 0 && onAcceptAll && (
            <button className="cl-diff-accept-all" onClick={onAcceptAll} type="button">
              Accept all remaining ({pendingCount})
            </button>
          )}
        </div>
      )}

      {/* 单文件：直接显示 Accept/Reject 按钮（readOnly 模式下改为引导） */}
      {!readOnly && entries.length === 1 && fileStatuses[entries[0].path] === undefined && (
        <div className="cl-diff-single-actions">
          <button className="cl-diff-btn cl-diff-btn--accept" onClick={() => handleAccept(entries[0].path)} type="button">
            <Check size={11} /> Accept
          </button>
          <button className="cl-diff-btn cl-diff-btn--reject" onClick={() => handleReject(entries[0].path)} type="button">
            <X size={11} /> Reject
          </button>
        </div>
      )}
      {readOnly && entries.length === 1 && (
        <div className="cl-diff-readonly-hint">
          摘要预览 · 在评审面板操作 Accept/Reject
        </div>
      )}

      {/* 单文件已审查后显示状态 */}
      {!readOnly && entries.length === 1 && fileStatuses[entries[0].path] && (
        <div className="cl-diff-single-status">
          {fileStatuses[entries[0].path] === "accepted" && (
            <span className="cl-diff-badge cl-diff-badge--accept">
              <Check size={10} /> applied to disk
            </span>
          )}
          {fileStatuses[entries[0].path] === "rejected" && (
            <span className="cl-diff-badge cl-diff-badge--reject">
              <X size={10} /> discarded
            </span>
          )}
        </div>
      )}
    </div>
  );
}
