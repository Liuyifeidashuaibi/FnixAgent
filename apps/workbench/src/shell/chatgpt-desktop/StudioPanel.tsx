/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * StudioPanel — 右侧统一工作台面（三栏布局 v2）
 * ============================================================
 * 将原 CanvasDock / WorkResults / ReviewPane 三个各自为政的右侧面板
 * 收敛为单一面板 + Tab 视图切换：
 *   - 画布 Canvas：钉选产物预览 / 编辑 / 版本时间轴（Work + Codex）
 *   - 结果 Results：产物 / 文件 / 变更 / 预览（Work deliver）
 *   - 评审 Review：diff 分级评审 + Accept/Reject/Undo（Codex）
 *
 * 交互：
 *   - 左缘拖拽手柄调宽（320px – 72vw），双击复位 420px，宽度持久化
 *   - 隐藏式多视图挂载：切 tab 不丢失各视图内部状态
 *   - 开/关面板 220ms 滑入，prefers-reduced-motion 降级
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { PanelRightClose } from "lucide-react";
import type { StudioTab } from "./sessionStore";

export interface StudioTabDef {
  id: StudioTab;
  label: string;
  /** 前置图标（14px lucide），提升多 tab 识别度 */
  icon?: ReactNode;
  /** 计数徽章（钉选数 / 产物数 / 变更数），0 不显示 */
  badge?: number;
  /** 评审风险色点 */
  dot?: "low" | "medium" | "high";
  /** 运行中呼吸点（终端 tab 在智能体执行时点亮）*/
  live?: boolean;
}

interface Props {
  tabs: StudioTabDef[];
  tab: StudioTab;
  onTabChange: (tab: StudioTab) => void;
  onClose: () => void;
  /** 全部可挂载视图；未提供的 tab 不渲染 */
  views: Partial<Record<StudioTab, ReactNode>>;
}

const WIDTH_KEY = "fnix-studio-w";
const DEFAULT_W = 420;
const MIN_W = 320;
const MAX_VW = 0.72;

function clampWidth(w: number): number {
  const max = Math.max(MIN_W, Math.round(window.innerWidth * MAX_VW));
  return Math.max(MIN_W, Math.min(w, max));
}

function loadWidth(): number {
  try {
    const n = Number.parseInt(localStorage.getItem(WIDTH_KEY) ?? "", 10);
    return Number.isFinite(n) && n >= MIN_W ? Math.min(n, 1600) : DEFAULT_W;
  } catch {
    return DEFAULT_W;
  }
}

export function StudioPanel({ tabs, tab, onTabChange, onClose, views }: Props) {
  const [width, setWidth] = useState<number>(loadWidth);
  const [resizing, setResizing] = useState(false);
  const asideRef = useRef<HTMLElement>(null);

  // 宽度持久化（拖拽中也写，开销可忽略）
  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      /* ignore */
    }
  }, [width]);

  const onGripPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = asideRef.current?.getBoundingClientRect().width ?? DEFAULT_W;
    setResizing(true);
    document.body.classList.add("fnx-studio-resizing");
    const onMove = (ev: PointerEvent) => {
      setWidth(clampWidth(startW + (startX - ev.clientX)));
    };
    const onUp = () => {
      setResizing(false);
      document.body.classList.remove("fnx-studio-resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

  const onGripDoubleClick = useCallback(() => setWidth(DEFAULT_W), []);

  return (
    <aside
      ref={asideRef}
      className="fnx-studio"
      style={{ width: `${width}px` }}
      aria-label="工作台面"
    >
      <div
        className={`fnx-studio-grip${resizing ? " active" : ""}`}
        role="separator"
        aria-orientation="vertical"
        aria-label="调整面板宽度"
        title="拖拽调整宽度 · 双击复位"
        onPointerDown={onGripPointerDown}
        onDoubleClick={onGripDoubleClick}
      />
      <header className="fnx-studio-head">
        <div className="fnx-studio-tabs" role="tablist" aria-label="工作台面视图">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              title={t.label}
              className={`fnx-studio-tab${tab === t.id ? " on" : ""}`}
              onClick={() => onTabChange(t.id)}
            >
              {t.icon ? <i className="fnx-studio-tab-ico">{t.icon}</i> : null}
              {t.label}
              {t.badge ? <i className="fnx-studio-badge">{t.badge}</i> : null}
              {t.live ? <i className="fnx-studio-live" title="智能体执行中" /> : null}
              {t.dot ? <i className={`fnx-studio-dot ${t.dot}`} title={`风险 ${t.dot}`} /> : null}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="oai-ibtn sm"
          title="收起面板 (Ctrl+\)"
          onClick={onClose}
        >
          <PanelRightClose size={15} />
        </button>
      </header>
      <div className="fnx-studio-body">
        {tabs.map((t) =>
          views[t.id] != null ? (
            <div
              key={t.id}
              className="fnx-studio-view"
              role="tabpanel"
              aria-label={t.label}
              hidden={tab !== t.id}
            >
              {views[t.id]}
            </div>
          ) : null,
        )}
      </div>
    </aside>
  );
}
