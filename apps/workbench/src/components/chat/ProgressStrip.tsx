/**
 * ProgressStrip — 紧凑进度状态条，内联在 assistant 消息顶部。
 *
 * 调研证据：
 * - PatternFly "Progress Design Guidelines":
 *   "For long task sequences, progress value may be Step 1 of 6"
 *   "When to use progress bar vs. spinner: use spinner for indeterminate, progress bar for determinate"
 * - Stanford HAI: "exposing chain-of-thought reduces black-box anxiety"
 * - UX Tigers: "文字式进度比百分比更有效（步骤数不确定时）"
 *   "for multi-hour tasks, a timeline of major phases is more useful than raw percentage"
 * - Xcapit: "Step 3 of 7: Analyzing financial statements gives confidence"
 * - userpilot: "fast early progress, perception of speed never changes"
 *
 * 设计：
 * - 确定步骤数：Step N/M 格式
 * - 不确定步骤数：Step N（无分母，避免失真）
 * - 完成态：✓ + 降低不透明度
 * - 紧凑一行，不占用太多空间
 */

import { Loader2, Check } from "lucide-react";

export interface ProgressStripProps {
  /** 当前步骤号（1-based） */
  currentStep: number;
  /** 总步骤数（不确定则为 undefined，显示 indeterminate 模式） */
  totalSteps?: number;
  /** 当前步骤描述 */
  description: string;
  /** 是否完成 */
  isComplete?: boolean;
}

export default function ProgressStrip({
  currentStep,
  totalSteps,
  description,
  isComplete,
}: ProgressStripProps) {
  // 确定模式：Step N/M；不确定模式：Step N
  const stepLabel = totalSteps
    ? `Step ${currentStep}/${totalSteps}`
    : `Step ${currentStep}`;

  return (
    <div className={`cl-progress-strip ${isComplete ? "complete" : ""}`} role="status" aria-live="polite">
      {isComplete ? (
        <Check size={11} className="cl-progress-check" />
      ) : (
        <Loader2 size={11} className="cl-progress-spinner spin" />
      )}
      <span className="cl-progress-step">{stepLabel}</span>
      <span className="cl-progress-sep">·</span>
      <span className="cl-progress-desc">{description}</span>
    </div>
  );
}
