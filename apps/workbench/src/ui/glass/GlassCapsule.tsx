/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { Check, ChevronDown, ChevronRight, FileCode2, Pencil, Terminal } from "lucide-react";
import { useState } from "react";

export type GlassCapsuleKind = "read" | "edit" | "run" | "test";

export interface GlassCapsuleProps {
  kind: GlassCapsuleKind;
  title: string;
  meta?: string;
  detail?: string;
  ok?: boolean;
  defaultOpen?: boolean;
  onOpenDiff?: () => void;
}

const ICONS = {
  read: FileCode2,
  edit: Pencil,
  run: Terminal,
  test: Check,
} as const;

export function GlassCapsule({
  kind,
  title,
  meta,
  detail,
  ok = true,
  defaultOpen,
  onOpenDiff,
}: GlassCapsuleProps) {
  const [open, setOpen] = useState(Boolean(defaultOpen && detail));
  const Icon = ICONS[kind];
  return (
    <div className={`glass-capsule${ok ? " ok" : ""}`}>
      <div className="glass-capsule-h">
        <button
          type="button"
          className="glass-capsule-main"
          onClick={() => detail && setOpen((v) => !v)}
          aria-expanded={detail ? open : undefined}
        >
          <Icon size={14} />
          <span className="t">{title}</span>
          {meta ? <span className="m">{meta}</span> : null}
          {ok ? <Check size={13} className="ok-ico" /> : null}
          {detail ? open ? <ChevronDown size={14} /> : <ChevronRight size={14} /> : null}
        </button>
        {onOpenDiff ? (
          <button type="button" className="glass-capsule-diff" onClick={onOpenDiff}>
            Open diff
          </button>
        ) : null}
      </div>
      {open && detail ? <pre className="glass-capsule-body">{detail}</pre> : null}
    </div>
  );
}
