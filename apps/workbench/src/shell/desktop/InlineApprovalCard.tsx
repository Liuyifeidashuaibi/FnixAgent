/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * InlineApprovalCard — UX P0-4 HITL 内联审批卡。
 *
 * OpenCode 式落位：权限请求出现在它最该出现的位置 — 输入框上方，
 * 只在有 pending 审批时渲染，零空闲占用。批准/拒绝复用 /hitl API，
 * 与 设置→系统 的 ApprovalPanel 同源，不新增后端依赖。
 */

import { useState } from 'react';
import { Check, Loader2, ShieldAlert, X } from 'lucide-react';
import {
  approveHitlTool,
  rejectHitlTool,
  type FnixHitlToolApproval,
} from '../../lib/fnixBridge';

const RISK_LABEL: Record<string, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '严重',
};

interface Props {
  items: FnixHitlToolApproval[];
  /** 操作成功后的回调（父级刷新 pending 列表） */
  onResolved?: () => void;
}

export function InlineApprovalCard({ items, onResolved }: Props) {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (items.length === 0) return null;

  const act = async (key: string, approve: boolean) => {
    setBusyKey(key);
    setError(null);
    try {
      if (approve) await approveHitlTool(key);
      else await rejectHitlTool(key, '用户在内联审批卡中拒绝');
      onResolved?.();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="fnix-approval-inline" role="alertdialog" aria-label="待审批操作">
      <div className="fnix-approval-inline-head">
        <ShieldAlert size={14} />
        <span>
          需要你的批准 · {items.length} 项{items.length > 1 ? '待审批' : ''}
        </span>
      </div>
      {items.slice(0, 3).map((t) => (
        <div key={t.idempotency_key} className="fnix-approval-inline-row">
          <span className="fnix-approval-inline-name" title={t.tool}>
            {t.tool}
          </span>
          <span
            className={`fnix-approval-inline-risk ${RISK_LABEL[t.risk] ? t.risk : 'unknown'}`}
          >
            {RISK_LABEL[t.risk] || t.risk || '—'}
          </span>
          <button
            type="button"
            className="fnix-approval-btn ok"
            disabled={busyKey !== null}
            onClick={() => void act(t.idempotency_key, true)}
            title="批准本次工具调用"
          >
            {busyKey === t.idempotency_key ? <Loader2 size={12} className="spin" /> : <Check size={13} />}
            批准
          </button>
          <button
            type="button"
            className="fnix-approval-btn no"
            disabled={busyKey !== null}
            onClick={() => void act(t.idempotency_key, false)}
            title="拒绝本次工具调用"
          >
            <X size={13} />
            拒绝
          </button>
        </div>
      ))}
      {items.length > 3 && (
        <div className="fnix-approval-inline-more">还有 {items.length - 3} 项 — 可在 设置 → 系统 中处理</div>
      )}
      {error && <div className="fnix-approval-inline-err">{error}</div>}
    </div>
  );
}
