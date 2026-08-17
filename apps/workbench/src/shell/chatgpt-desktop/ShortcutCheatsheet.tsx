/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** 快捷键速查表 — 按 ? 呼出。 */

interface ShortcutCheatsheetProps {
  open: boolean;
  onClose: () => void;
}

const IS_MAC =
  typeof navigator !== "undefined" && /mac/i.test(navigator.platform || navigator.userAgent);
const MOD = IS_MAC ? "⌘" : "Ctrl";

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: "全局",
    items: [
      [`${MOD} K`, "命令面板 / 搜索会话"],
      [`${MOD} B`, "收起 / 展开侧栏"],
      [`${MOD} \\`, "收起 / 展开工作台面"],
      ["?", "快捷键速查表"],
      ["Alt /", "跳到主区域"],
      ["Esc", "关闭面板 / 审查"],
    ],
  },
  {
    title: "输入",
    items: [
      ["Enter", "发送消息"],
      ["Shift Enter", "换行"],
      [`${MOD} S`, "保存（技能编辑器内）"],
    ],
  },
  {
    title: "代码审查",
    items: [
      [`${MOD} Enter`, "接受全部变更"],
      [`${MOD} Shift Enter`, "接受当前文件"],
      [`${MOD} Z`, "撤销变更"],
    ],
  },
];

export function ShortcutCheatsheet({ open, onClose }: ShortcutCheatsheetProps) {
  if (!open) return null;
  return (
    <div className="oai-keys-overlay" role="button" tabIndex={-1} aria-label="关闭快捷键速查表" onClick={onClose} onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div
        className="oai-keys"
        role="dialog"
        aria-modal="true"
        aria-label="快捷键速查表"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="oai-keys-head">
          <span>快捷键</span>
          <button type="button" className="oai-keys-x" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>
        <div className="oai-keys-body">
          {GROUPS.map((g) => (
            <div key={g.title} className="oai-keys-group">
              <div className="oai-keys-group-t">{g.title}</div>
              {g.items.map(([keys, desc]) => (
                <div key={keys + desc} className="oai-keys-row">
                  <span className="oai-keys-desc">{desc}</span>
                  <span className="oai-keys-kbds">
                    {keys.split(" ").map((k, i) => (
                      <kbd key={i}>{k}</kbd>
                    ))}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
