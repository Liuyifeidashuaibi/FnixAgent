import * as React from 'react';
import { cn } from './utils';

// 注入 indeterminate 模式所需 keyframes(模块级,只注入一次,SSR 安全)
const __PROGRESS_STYLE_ID = '__officeagent_ui_progress_keyframes__';
if (typeof document !== 'undefined' && !document.getElementById(__PROGRESS_STYLE_ID)) {
  const style = document.createElement('style');
  style.id = __PROGRESS_STYLE_ID;
  style.textContent =
    '@keyframes progress-indeterminate{0%{transform:translateX(-100%)}100%{transform:translateX(400%)}}';
  document.head.appendChild(style);
}

// shadcn/ui Progress 组件 — 受控 value (0-100)
// 通过 CSS 变量 --progress-value 传递进度百分比
// 当 value 为 undefined 或 null 时,显示 indeterminate(不定)动画

export interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  // 当前进度值 0-100;不传则进入 indeterminate 模式
  value?: number | null;
  // 进度条最大值,默认 100
  max?: number;
}

const Progress = React.forwardRef<HTMLDivElement, ProgressProps>(
  ({ className, value, max = 100, style, ...props }, ref) => {
    // 计算 0-100 之间的百分比
    const clamped = typeof value === 'number' ? Math.min(100, Math.max(0, (value / max) * 100)) : null;
    const isIndeterminate = clamped === null;

    return (
      <div
        ref={ref}
        role="progressbar"
        aria-valuenow={value ?? undefined}
        aria-valuemin={0}
        aria-valuemax={max}
        className={cn(
          'relative h-2 w-full overflow-hidden rounded-full bg-secondary',
          className,
        )}
        style={
          {
            // 通过 CSS 变量暴露当前进度,便于自定义样式
            '--progress-value': clamped !== null ? `${clamped}%` : '0%',
            ...style,
          } as React.CSSProperties
        }
        {...props}
      >
        {isIndeterminate ? (
          // 不定模式 — 一个左右滑动的亮色块
          <div className="absolute inset-0">
            <div className="h-full w-1/3 animate-[progress-indeterminate_1.5s_ease-in-out_infinite] rounded-full bg-primary" />
          </div>
        ) : (
          // 受控模式 — 宽度由 CSS 变量驱动,带过渡动画
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
            style={{ width: `var(--progress-value)` }}
          />
        )}
      </div>
    );
  },
);
Progress.displayName = 'Progress';

export { Progress };
