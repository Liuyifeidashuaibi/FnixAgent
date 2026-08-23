/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { useEffect, useRef, type ReactNode } from 'react';
import { ArrowUp, Square, X } from 'lucide-react';
import type { ChatAttachment } from '../../utils/tauri';

export interface GlassComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop?: () => void;
  streaming: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  compact?: boolean;
  modelSlot?: ReactNode;
  leftSlot?: ReactNode;
  attachments?: ChatAttachment[];
  onRemoveAttachment?: (id: string) => void;
  className?: string;
  /** 外部禁用发送（如 Code 模式未打开仓库时） */
  sendDisabled?: boolean;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function GlassComposer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  placeholder = '输入你的问题…',
  autoFocus,
  compact,
  modelSlot,
  leftSlot,
  attachments,
  onRemoveAttachment,
  className,
  sendDisabled,
}: GlassComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) ref.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Reset to auto first so scrollHeight reflects only the current content
    // (otherwise the height can only ever grow). The textarea has no `rows`
    // attribute — JS fully owns the height to avoid attribute/effect conflict.
    el.style.height = 'auto';
    const max = 200;
    const min = compact ? 44 : 28;
    const next = Math.min(max, Math.max(min, el.scrollHeight));
    el.style.height = `${next}px`;
    el.style.overflowY = el.scrollHeight > next + 1 ? 'auto' : 'hidden';
  }, [value, compact]);

  // canSend 兼容纯附件发送：父级 sendDraft 已允许「无文本 + 有附件」通过，
  // 此处若不放开会导致发送按钮 disabled、Enter 不触发，用户无法发送纯图片/文件消息
  const hasText = value.trim().length > 0;
  const hasAttachments = !!(attachments && attachments.length > 0);
  const canSend = (hasText || hasAttachments) && !streaming && !sendDisabled;

  return (
    <div
      className={['glass-composer', compact ? 'compact' : '', className].filter(Boolean).join(' ')}
    >
      {attachments && attachments.length > 0 ? (
        <div className="fnix-attach-chips">
          {attachments.map((a) => (
            <div key={a.id} className={`fnix-attach-chip${a.type === 'image' ? ' is-image' : ''}`}>
              {a.type === 'image' ? (
                <img
                  className="fnix-attach-thumb"
                  src={`data:${a.mimeType};base64,${a.base64}`}
                  alt={a.name}
                />
              ) : (
                <span className="fnix-attach-fileico" aria-hidden>
                  📄
                </span>
              )}
              <span className="fnix-attach-meta">
                <span className="fnix-attach-name" title={a.name}>
                  {a.name}
                </span>
                <span className="fnix-attach-size">{formatSize(a.size)}</span>
              </span>
              {onRemoveAttachment ? (
                <button
                  type="button"
                  className="fnix-attach-x"
                  aria-label={`移除 ${a.name}`}
                  onClick={() => onRemoveAttachment(a.id)}
                >
                  <X size={13} />
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      <textarea
        ref={ref}
        value={value}
        placeholder={placeholder}
        aria-label={placeholder || '消息输入框'}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (canSend) onSend();
          }
        }}
      />
      <div className="glass-comp-bar">
        <div className="glass-comp-l">{leftSlot}</div>
        <div className="glass-comp-r">
          {modelSlot}
          {streaming ? (
            <button
              type="button"
              className="glass-send stop"
              onClick={onStop}
              aria-label="停止"
              title="停止"
            >
              <Square size={11} fill="currentColor" />
            </button>
          ) : (
            <button
              type="button"
              className="glass-send"
              disabled={!canSend}
              onClick={onSend}
              aria-label="发送"
            >
              <ArrowUp size={16} strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
