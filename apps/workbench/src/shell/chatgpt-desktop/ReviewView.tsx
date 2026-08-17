/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ReviewView — Studio Panel「评审」视图（原 ReviewPane，v2 剥离 GlassPanel 外壳）
 * Code Review：diff + 风险分级 + Reject / Accept / Undo。
 * 关闭按钮由 StudioPanel 头部统一承担，此处不再自带。
 */

import { useMemo } from "react";
import { PanelRight } from "lucide-react";
import type { CodexFileChange } from "./fnixRuntime";
import { DiffView } from "./DiffView";
import { assessReviewBatch } from "./reviewRisk";

interface Props {
  changes: CodexFileChange[];
  codeBlocks?: { lang: string; body: string }[];
  applyStatus: "idle" | "applying" | "applied" | "failed" | "undoing";
  applyMessage?: string | null;
  streaming?: boolean;
  lastChangesetId?: string | null;
  onAccept: () => void;
  onAcceptFile?: (path: string) => void;
  /** Accept a partially-merged file (selected hunks). */
  onAcceptPartial?: (change: CodexFileChange) => void;
  onUndo?: () => void;
  onReject: () => void;
  activePath?: string | null;
  onSelectPath?: (path: string) => void;
}

export function ReviewView({
  changes,
  codeBlocks = [],
  applyStatus,
  applyMessage,
  streaming,
  lastChangesetId,
  onAccept,
  onAcceptFile,
  onAcceptPartial,
  onUndo,
  onReject,
  activePath,
  onSelectPath,
}: Props) {
  const selected =
    changes.find((c) => c.path === activePath) || changes[0] || null;
  const busy = applyStatus === "applying" || applyStatus === "undoing";
  const canUndo = Boolean(lastChangesetId) && !busy && !streaming;
  const risk = useMemo(() => assessReviewBatch(changes), [changes]);
  const selectedRisk = risk.files.find((f) => f.path === selected?.path);

  return (
    <div className="fnx-review">
      {changes.length > 0 ? (
        <div className="oai-scopes" role="tablist" aria-label="已变更文件">
          {changes.map((ch) => {
            const fr = risk.files.find((f) => f.path === ch.path);
            return (
              <button
                key={ch.path}
                type="button"
                role="tab"
                aria-selected={(selected?.path || "") === ch.path}
                className={`oai-scope${(selected?.path || "") === ch.path ? " on" : ""}${
                  fr?.hasConflict ? " conflict" : ""
                }`}
                onClick={() => onSelectPath?.(ch.path)}
                title={`${ch.path}${fr ? ` · ${fr.level}: ${fr.reasons.join(", ")}` : ""}`}
              >
                {ch.path.split(/[/\\]/).pop() || ch.path}
                {fr && fr.level !== "low" ? (
                  <i className={`oai-scope-risk ${fr.level}`}>{fr.level[0]}</i>
                ) : null}
              </button>
            );
          })}
        </div>
      ) : (
        <div className="oai-scopes">
          <button type="button" className="oai-scope on">
            Last turn
          </button>
        </div>
      )}

      <div className="oai-review-body">
        {selectedRisk && (selectedRisk.level !== "low" || selectedRisk.hasConflict) ? (
          <div
            className={`oai-review-note${selectedRisk.hasConflict || selectedRisk.level === "high" ? " bad" : ""}`}
            role="status"
          >
            Risk: <strong>{selectedRisk.level}</strong>
            {" — "}
            {selectedRisk.reasons.join(" · ")}
            {selectedRisk.hasConflict ? " · resolve markers before Accept" : ""}
          </div>
        ) : null}

        {applyMessage ? (
          <div
            className={`oai-review-note${applyStatus === "failed" ? " bad" : " ok"}`}
            role="status"
          >
            {applyMessage}
          </div>
        ) : null}

        {lastChangesetId && changes.length === 0 ? (
          <div className="oai-review-note ok" role="status">
            Last changeset: <code>{lastChangesetId.slice(0, 12)}</code> — Undo 可撤销
          </div>
        ) : null}

        {changes.length === 0 ? (
          codeBlocks.length === 0 ? (
            <div className="fnx-studio-empty">
              <PanelRight size={28} strokeWidth={1.5} />
              <p>预览中的文件变更会出现在这里</p>
              <p className="dim">Accept 后写入项目目录 · Undo 按 changeset 回滚</p>
            </div>
          ) : (
            <>
              {/* codeBlocks 是 AI 回复中的 ```代码片段```，不是待审查的 diff。
                  原代码用 DiffView 渲染会把所有行当 add 行（全绿），误导用户以为是「待审查的新增」。
                  改为普通代码展示 + 明确提示。 */}
              <div className="oai-review-note" role="status">
                以下是 AI 回复中的代码片段（非待审查变更），仅供参考。
              </div>
              {codeBlocks.map((b, i) => (
                <DiffView key={i} path={b.lang || "snippet"} content={b.body} action="preview" />
              ))}
            </>
          )
        ) : selected ? (
          <DiffView
            path={selected.path}
            diff={selected.diff}
            content={selected.content}
            oldContent={selected.old_content}
            action={selected.action}
            disabled={busy || streaming}
            onAcceptHunks={
              onAcceptPartial
                ? (payload) =>
                    onAcceptPartial({
                      path: payload.path,
                      content: payload.content,
                      old_content: payload.old_content,
                      action: payload.action,
                    })
                : undefined
            }
          />
        ) : null}
      </div>

      {/* ── 沉底操作栏 ── */}
      {changes.length > 0 || canUndo ? (
        <div className="oai-review-actions foot">
          {canUndo ? (
            <button
              type="button"
              className="oai-review-btn ghost"
              disabled={!canUndo}
              onClick={() => onUndo?.()}
              title={lastChangesetId ? `撤销 ${lastChangesetId}` : "撤销"}
            >
              撤销
            </button>
          ) : (
            <button
              type="button"
              className="oai-review-btn ghost"
              disabled={busy}
              onClick={onReject}
            >
              拒绝
            </button>
          )}
          {selected && onAcceptFile && changes.length > 1 ? (
            <button
              type="button"
              className="oai-review-btn ghost"
              disabled={busy || streaming || selectedRisk?.hasConflict}
              onClick={() => onAcceptFile(selected.path)}
              title={
                selectedRisk?.hasConflict
                  ? "先解决冲突标记再确认"
                  : `确认 ${selected.path}`
              }
            >
              确认此文件
            </button>
          ) : null}
          {changes.length > 0 ? (
            <button
              type="button"
              className="oai-review-btn solid"
              disabled={busy || streaming || risk.conflictCount > 0}
              onClick={onAccept}
              title={
                risk.conflictCount > 0
                  ? "先解决冲突标记再全部确认"
                  : undefined
              }
            >
              {busy ? "写盘中…" : "全部确认"}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
