/**
 * Ask / Plan / Craft — Cursor/Codex 式 Composer 内小选项（非首页大卡）。
 * compact：下拉 pill；segment：三小钮（少用）。
 */

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { WorkExecMode } from "./fnixRuntime";

const MODES: {
  id: WorkExecMode;
  label: string;
  desc: string;
}[] = [
  { id: "ask", label: "Ask", desc: "解释与建议，不写盘" },
  { id: "plan", label: "Plan", desc: "先出可执行计划" },
  { id: "craft", label: "Craft", desc: "执行并落盘交付" },
];

interface Props {
  value: WorkExecMode;
  onChange: (mode: WorkExecMode) => void;
  disabled?: boolean;
  /** dropdown = Composer pill（默认）；segment = 三钮一行 */
  variant?: "dropdown" | "segment";
}

export function WorkModePicker({
  value,
  onChange,
  disabled,
  variant = "dropdown",
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = MODES.find((m) => m.id === value) || MODES[2]!;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  if (variant === "segment") {
    return (
      <div className="wb-mode-seg" role="radiogroup" aria-label="Execution mode">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={value === m.id}
            className={`wb-mode-seg-btn${value === m.id ? " on" : ""}`}
            disabled={disabled}
            title={m.desc}
            onClick={() => onChange(m.id)}
          >
            {m.label}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div className="wb-mode-dd" ref={ref}>
      <button
        type="button"
        className="wb-mode-pill"
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="listbox"
        title={current.desc}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`wb-mode-dot ${current.id}`} />
        {current.label}
        <ChevronDown size={12} />
      </button>
      {open ? (
        <div className="wb-mode-menu" role="listbox" aria-label="Ask Plan Craft">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              role="option"
              aria-selected={value === m.id}
              className={value === m.id ? "on" : undefined}
              onClick={() => {
                onChange(m.id);
                setOpen(false);
              }}
            >
              <span className="wb-mode-menu-t">
                <span className={`wb-mode-dot ${m.id}`} />
                {m.label}
              </span>
              <span className="wb-mode-menu-d">{m.desc}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function workModePlaceholder(mode: WorkExecMode): string {
  if (mode === "ask") return "输入你的问题…";
  if (mode === "plan") return "描述目标 — 我先出一版计划…";
  return "描述要构建或交付的内容…";
}

export function workModeHint(mode: WorkExecMode): string {
  if (mode === "ask") return "Ask · 只回答，不创建改文件";
  if (mode === "plan") return "Plan · 输出步骤，确认后切 Craft";
  return "Craft · 写入 .fnix/artifacts";
}
