/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * CanvasView — Studio Panel「画布」视图（原 CanvasDock，v2 剥离外壳）
 * ============================================================
 * 作为 StudioPanel 的子视图渲染（不再自带 aside 框架 / 关闭按钮 / 开关逻辑）：
 *   - 多文件钉选（最多 8 个，tab 切换，状态来自 sessionStore.pinnedArtifacts）
 *   - 版本时间轴（从 fileChanges reconstruct 历史版本）
 *   - inline edit 入口（选中代码 → 自然语言修改 → DiffEditor 预览）
 *   - 复用 ArtifactCanvas 渲染层
 */

import { useMemo, useState } from "react";
import { Pin, X, History, Sparkles, Trash2 } from "lucide-react";
import { ArtifactCanvas } from "./ArtifactCanvas";
import { useSessionStore } from "./sessionStore";
import type { CodexFileChange } from "./fnixRuntime";

export interface CanvasVersionNode {
  /** 文件路径 */
  path: string;
  /** 操作类型 */
  action: "write_file" | "edit_file" | "create_file" | "apply_diff" | string;
  /** 时间戳（ms） */
  timestamp: number;
  /** run_id（关联哪次执行） */
  runId?: string;
  /** diff 内容（可选，用于查看变更） */
  diff?: string;
}

interface Props {
  /** 当前 workspace 路径 */
  workspace?: string;
  /** API base */
  apiBase: string;
  /** file changes 流（用于 reconstruct 版本时间轴）*/
  fileChanges?: CodexFileChange[];
  /** inline edit 回调（由父级注入 LLM 调用）*/
  onInlineEdit?: (path: string, instruction: string) => Promise<void>;
}

export function CanvasView({ workspace, apiBase, fileChanges = [], onInlineEdit }: Props) {
  const { pinnedArtifacts, unpinArtifact, clearPinnedArtifacts } = useSessionStore();
  const [activeIdx, setActiveIdx] = useState(0);
  const [showHistory, setShowHistory] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editInstruction, setEditInstruction] = useState("");
  const [editBusy, setEditBusy] = useState(false);

  // 安全边界：activeIdx 不能超出 pinnedArtifacts
  const safeIdx = Math.min(activeIdx, pinnedArtifacts.length - 1);
  const activePath = pinnedArtifacts[safeIdx] || null;

  // 按路径聚合 fileChanges，得到当前文件的版本历史
  const versions: CanvasVersionNode[] = useMemo(() => {
    if (!activePath) return [];
    return fileChanges
      .filter((c) => c.path === activePath)
      .map((c) => ({
        path: c.path,
        action: c.action || "edit_file",
        timestamp: c.timestamp || 0,
        runId: c.runId,
        diff: c.diff,
      }))
      .sort((a, b) => a.timestamp - b.timestamp);
  }, [activePath, fileChanges]);

  // 空状态：统一语言（StudioPanel 框架内渲染，不再返回独立 aside）
  if (pinnedArtifacts.length === 0) {
    return (
      <div className="fnx-canvas">
        <div className="fnx-studio-empty">
          <Pin size={28} strokeWidth={1.5} />
          <p>将消息中的产物 📌 钉选到画布</p>
          <p className="dim">支持 HTML · Markdown · 代码 · 图片多格式预览</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fnx-canvas">
      {/* ── 顶部 tab 栏 ── */}
      <header className="oai-canvas-head">
        <div className="oai-canvas-tabs" role="tablist">
          {pinnedArtifacts.map((p, i) => {
            const name = p.replace(/[/\\]+$/, "").split(/[/\\]/).pop() || p;
            return (
              <button
                key={p}
                type="button"
                role="tab"
                aria-selected={safeIdx === i}
                className={`oai-canvas-tab${safeIdx === i ? " on" : ""}`}
                onClick={() => setActiveIdx(i)}
                title={p}
              >
                <Pin size={11} />
                <span className="oai-canvas-tab-name">{name}</span>
                <span
                  className="oai-canvas-tab-close"
                  role="button"
                  tabIndex={0}
                  aria-label={`取消钉选 ${name}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    unpinArtifact(p);
                    if (i <= safeIdx) setActiveIdx(Math.max(0, safeIdx - 1));
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.stopPropagation();
                      unpinArtifact(p);
                      if (i <= safeIdx) setActiveIdx(Math.max(0, safeIdx - 1));
                    }
                  }}
                >
                  <X size={11} />
                </span>
              </button>
            );
          })}
        </div>
        <div className="oai-canvas-head-actions">
          <button
            type="button"
            className="oai-ibtn sm"
            title="版本时间轴"
            onClick={() => setShowHistory((v) => !v)}
          >
            <History size={14} />
          </button>
          <button
            type="button"
            className="oai-ibtn sm"
            title="清除全部钉选"
            onClick={() => {
              clearPinnedArtifacts();
              setActiveIdx(0);
            }}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </header>

      {/* ── 画布主体 ── */}
      <div className="oai-canvas-body">
        {activePath ? (
          <ArtifactCanvas
            artifact={{ path: activePath }}
            apiBase={apiBase}
            workspace={workspace}
          />
        ) : (
          <div className="fnx-studio-empty">
            <Pin size={28} strokeWidth={1.5} />
            <p>将消息中的产物 📌 钉选到画布</p>
          </div>
        )}
      </div>

      {/* ── inline edit 工具条（仅当父级注入 onInlineEdit 时显示）── */}
      {activePath && onInlineEdit && (
        <div className="oai-canvas-editbar">
          {editing ? (
            <div className="oai-canvas-edit-input">
              <Sparkles size={13} />
              <input
                type="text"
                placeholder="选中代码后，用自然语言描述修改…"
                value={editInstruction}
                disabled={editBusy}
                onChange={(e) => setEditInstruction(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && editInstruction.trim() && !editBusy) {
                    setEditBusy(true);
                    onInlineEdit(activePath, editInstruction.trim())
                      .catch(() => {})
                      .finally(() => {
                        setEditBusy(false);
                        setEditing(false);
                        setEditInstruction("");
                      });
                  }
                  if (e.key === "Escape") {
                    setEditing(false);
                    setEditInstruction("");
                  }
                }}
              />
              <button
                type="button"
                className="oai-ibtn sm"
                onClick={() => {
                  setEditing(false);
                  setEditInstruction("");
                }}
              >
                <X size={12} />
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="oai-canvas-edit-trigger"
              onClick={() => setEditing(true)}
            >
              <Sparkles size={13} />
              <span>用 AI 修改</span>
            </button>
          )}
        </div>
      )}

      {/* ── 版本时间轴 ── */}
      {showHistory && (
        <div className="oai-canvas-history">
          <div className="oai-canvas-history-head">
            <span>版本时间轴</span>
            <span className="dim">{versions.length} 个版本</span>
          </div>
          {versions.length === 0 ? (
            <div className="oai-canvas-history-empty">本次会话暂无历史版本</div>
          ) : (
            <ol className="oai-canvas-timeline">
              {versions.map((v, i) => (
                <li key={i} className="oai-canvas-version">
                  <span className="oai-canvas-version-dot" />
                  <div className="oai-canvas-version-info">
                    <div className="oai-canvas-version-action">{v.action}</div>
                    <div className="oai-canvas-version-time">
                      {new Date(v.timestamp).toLocaleString()}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
