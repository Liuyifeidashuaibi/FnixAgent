/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ApprovalPanel — HITL 人机协同审批面板。
 *
 * 展示 agentd 的待审批队列：
 *   - 工具调用：tool 名 + risk 徽章 + 时间
 *   - 流程守门（gate）：gate 类型 + context 摘要 + 时间
 * 每项支持批准 / 拒绝（拒绝可填理由），操作成功后刷新列表；空态显示「无待审批项」。
 */

import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import {
  approveHitlGate,
  approveHitlTool,
  listHitlPending,
  rejectHitlGate,
  rejectHitlTool,
  type FnixHitlPending,
} from "../../lib/fnixBridge";

/** 风险等级 → 中文徽章文案（未知等级原样展示）。 */
const RISK_LABEL: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "严重",
};

/** 风险等级 → 徽章色阶（复用 fnix-mcp-badge 现有配色）。 */
const RISK_BADGE: Record<string, string> = {
  low: "green",
  medium: "yellow",
  high: "red",
  critical: "red",
};

/** 风险等级 → 状态点颜色。 */
const RISK_DOT: Record<string, string> = {
  low: "green",
  medium: "yellow",
  high: "red",
  critical: "red",
};

/** 守门状态 → 中文徽章文案与色阶。 */
const GATE_STATUS_LABEL: Record<string, string> = {
  pending: "待审批",
  approved: "已批准",
  rejected: "已拒绝",
};
const GATE_STATUS_BADGE: Record<string, string> = {
  pending: "yellow",
  approved: "green",
  rejected: "red",
};

/** ISO 时间 → 本地化展示（解析失败时原样返回）。 */
function formatTime(ts: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
}

/** context 摘要：压平空白并截断到 96 字符。 */
function summarize(text: string): string {
  const t = (text || "").replace(/\s+/g, " ").trim();
  return t.length > 96 ? `${t.slice(0, 96)}…` : t;
}

/** 当前展开「拒绝理由」输入框的目标项。 */
type RejectTarget = { kind: "tool" | "gate"; key: string };

export function ApprovalPanel() {
  const [pending, setPending] = useState<FnixHitlPending>({
    tool_approvals: [],
    gates: [],
    auto_approve_gates: [],
  });
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actingKey, setActingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rejectTarget, setRejectTarget] = useState<RejectTarget | null>(null);
  const [reason, setReason] = useState("");

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await listHitlPending();
      if (!res.ok) {
        setError(res.error || "加载待审批列表失败");
      }
      setPending(res.pending);
    } finally {
      setBusy(false);
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  /** 统一执行批准 / 拒绝，成功后清空输入并刷新列表。 */
  const act = async (
    kind: "tool" | "gate",
    key: string,
    action: "approve" | "reject",
    text: string,
  ) => {
    setActingKey(key);
    setError(null);
    try {
      const res =
        kind === "tool"
          ? action === "approve"
            ? await approveHitlTool(key, text)
            : await rejectHitlTool(key, text)
          : action === "approve"
            ? await approveHitlGate(key, text)
            : await rejectHitlGate(key, text);
      if (!res.ok) {
        setError(res.error || (action === "approve" ? "批准失败" : "拒绝失败"));
        return;
      }
      setRejectTarget(null);
      setReason("");
      await refresh();
    } finally {
      setActingKey(null);
    }
  };

  const startReject = (target: RejectTarget) => {
    setRejectTarget(target);
    setReason("");
  };

  const confirmReject = () => {
    if (!rejectTarget || actingKey) return;
    void act(rejectTarget.kind, rejectTarget.key, "reject", reason.trim());
  };

  const isEmpty = pending.tool_approvals.length === 0 && pending.gates.length === 0;

  return (
    <div role="region" aria-label="HITL 审批">
      <div className="fnix-set-actions" style={{ marginTop: 12 }}>
        <button
          type="button"
          className="fnix-set-save ghost"
          disabled={busy}
          onClick={() => void refresh()}
        >
          {busy ? <Loader2 size={14} className="spin" /> : null}
          刷新
        </button>
        {pending.auto_approve_gates.length > 0 ? (
          <span className="fnix-field-hint">
            自动放行守门：{pending.auto_approve_gates.join("、")}
          </span>
        ) : null}
      </div>

      {error ? (
        <div className="fnix-info-card" style={{ marginTop: 12 }}>
          <b>操作失败</b>
          <span>{error}</span>
        </div>
      ) : null}

      {!loaded ? (
        <div className="fnix-loading-row">正在加载待审批列表…</div>
      ) : isEmpty ? (
        <div className="fnix-empty-card">
          <b>无待审批项</b>
          <span>agent 请求人工确认高危工具调用或流程守门时，会出现在这里。</span>
        </div>
      ) : (
        <>
          {pending.tool_approvals.length > 0 && (
            <section style={{ marginTop: 12 }}>
              <p className="fnix-field-hint">工具调用（{pending.tool_approvals.length}）</p>
              {pending.tool_approvals.map((t) => {
                const key = t.idempotency_key;
                const rejecting = rejectTarget?.kind === "tool" && rejectTarget.key === key;
                const acting = actingKey === key;
                return (
                  <div key={key}>
                    <div className="fnix-mcp-row">
                      <span
                        className={`fnix-mcp-dot ${RISK_DOT[t.risk] ?? "yellow"}`}
                        aria-hidden
                      />
                      <div className="fnix-mcp-meta">
                        <div className="fnix-mcp-head">
                          <b>{t.tool}</b>
                          <span className={`fnix-mcp-badge ${RISK_BADGE[t.risk] ?? "gray"}`}>
                            {RISK_LABEL[t.risk] ?? t.risk}
                          </span>
                        </div>
                        <span title={key}>{formatTime(t.timestamp)}</span>
                      </div>
                      <div className="fnix-mcp-actions">
                        <button
                          type="button"
                          className="fnix-set-save"
                          disabled={Boolean(actingKey)}
                          onClick={() => void act("tool", key, "approve", "")}
                        >
                          {acting && !rejecting ? <Loader2 size={14} className="spin" /> : null}
                          批准
                        </button>
                        <button
                          type="button"
                          className="fnix-set-save ghost"
                          disabled={Boolean(actingKey)}
                          onClick={() => startReject({ kind: "tool", key })}
                        >
                          拒绝
                        </button>
                      </div>
                    </div>
                    {rejecting ? (
                      <div className="fnix-key-row" style={{ marginTop: 8 }}>
                        <input
                          value={reason}
                          placeholder="拒绝理由（可选）"
                          autoFocus
                          onChange={(e) => setReason(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") confirmReject();
                          }}
                        />
                        <button
                          type="button"
                          className="fnix-set-save"
                          disabled={Boolean(actingKey)}
                          onClick={() => confirmReject()}
                        >
                          {acting ? <Loader2 size={14} className="spin" /> : null}
                          确认拒绝
                        </button>
                        <button
                          type="button"
                          className="fnix-set-save ghost"
                          disabled={Boolean(actingKey)}
                          onClick={() => setRejectTarget(null)}
                        >
                          取消
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </section>
          )}

          {pending.gates.length > 0 && (
            <section style={{ marginTop: 16 }}>
              <p className="fnix-field-hint">流程守门（{pending.gates.length}）</p>
              {pending.gates.map((g) => {
                const key = g.id;
                const rejecting = rejectTarget?.kind === "gate" && rejectTarget.key === key;
                const acting = actingKey === key;
                return (
                  <div key={key}>
                    <div className="fnix-mcp-row">
                      <span className={`fnix-mcp-dot ${RISK_DOT.high}`} aria-hidden />
                      <div className="fnix-mcp-meta">
                        <div className="fnix-mcp-head">
                          <b>{g.gate}</b>
                          <span className={`fnix-mcp-badge ${GATE_STATUS_BADGE[g.status] ?? "gray"}`}>
                            {GATE_STATUS_LABEL[g.status] ?? g.status}
                          </span>
                        </div>
                        <span title={g.context}>
                          {summarize(g.context) || "（无上下文）"}
                          {g.timestamp ? ` · ${formatTime(g.timestamp)}` : ""}
                        </span>
                      </div>
                      <div className="fnix-mcp-actions">
                        <button
                          type="button"
                          className="fnix-set-save"
                          disabled={Boolean(actingKey)}
                          onClick={() => void act("gate", key, "approve", "")}
                        >
                          {acting && !rejecting ? <Loader2 size={14} className="spin" /> : null}
                          批准
                        </button>
                        <button
                          type="button"
                          className="fnix-set-save ghost"
                          disabled={Boolean(actingKey)}
                          onClick={() => startReject({ kind: "gate", key })}
                        >
                          拒绝
                        </button>
                      </div>
                    </div>
                    {rejecting ? (
                      <div className="fnix-key-row" style={{ marginTop: 8 }}>
                        <input
                          value={reason}
                          placeholder="拒绝理由（可选）"
                          autoFocus
                          onChange={(e) => setReason(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") confirmReject();
                          }}
                        />
                        <button
                          type="button"
                          className="fnix-set-save"
                          disabled={Boolean(actingKey)}
                          onClick={() => confirmReject()}
                        >
                          {acting ? <Loader2 size={14} className="spin" /> : null}
                          确认拒绝
                        </button>
                        <button
                          type="button"
                          className="fnix-set-save ghost"
                          disabled={Boolean(actingKey)}
                          onClick={() => setRejectTarget(null)}
                        >
                          取消
                        </button>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </section>
          )}
        </>
      )}
    </div>
  );
}
