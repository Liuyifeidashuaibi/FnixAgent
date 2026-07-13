import * as React from 'react';
import { cn } from './utils';

// 注入 tooltip 淡入 keyframes(模块级,只注入一次,SSR 安全)
const __TOOLTIP_STYLE_ID = '__officeagent_ui_tooltip_keyframes__';
if (typeof document !== 'undefined' && !document.getElementById(__TOOLTIP_STYLE_ID)) {
  const style = document.createElement('style');
  style.id = __TOOLTIP_STYLE_ID;
  style.textContent =
    '@keyframes tooltip-fade{from{opacity:0;transform:scale(0.96)}to{opacity:1;transform:scale(1)}}';
  document.head.appendChild(style);
}

// shadcn/ui Tooltip 组件族 — 纯 React + CSS 实现
// 支持 hover 延迟(300ms 进, 100ms 出)、自动定位、暗色背景 + 箭头

type TooltipSide = 'top' | 'bottom' | 'left' | 'right';

interface TooltipContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  side: TooltipSide;
}

const TooltipContext = React.createContext<TooltipContextValue | null>(null);

// TooltipProvider — 全局配置(预留扩展,当前用于包裹延迟设置)
interface TooltipProviderProps extends React.HTMLAttributes<HTMLDivElement> {
  // 进入延迟(ms),默认 300
  delayDuration?: number;
  // 离开延迟(ms),默认 100
  skipDelayDuration?: number;
}

const TooltipProvider = React.forwardRef<HTMLDivElement, TooltipProviderProps>(
  ({ children, ...props }, ref) => (
    <div ref={ref} {...props}>
      {children}
    </div>
  ),
);
TooltipProvider.displayName = 'TooltipProvider';

export interface TooltipProps extends React.HTMLAttributes<HTMLDivElement> {
  // 弹出方向,默认 top
  side?: TooltipSide;
  // 进入延迟(ms),默认 300
  delayDuration?: number;
  // 离开延迟(ms),默认 100
  skipDelayDuration?: number;
  // 受控开关
  open?: boolean;
  // 开关回调
  onOpenChange?: (open: boolean) => void;
}

// Tooltip — 单个 tooltip 容器,管理 open 状态与延迟
const Tooltip = React.forwardRef<HTMLDivElement, TooltipProps>(
  (
    {
      side = 'top',
      delayDuration = 300,
      skipDelayDuration = 100,
      open: openProp,
      onOpenChange,
      className,
      children,
      ...props
    },
    ref,
  ) => {
    const [internalOpen, setInternalOpen] = React.useState(false);
    const isControlled = openProp !== undefined;
    const open = isControlled ? openProp : internalOpen;
    const showTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
    const hideTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

    const clearTimers = React.useCallback(() => {
      if (showTimer.current) clearTimeout(showTimer.current);
      if (hideTimer.current) clearTimeout(hideTimer.current);
      showTimer.current = null;
      hideTimer.current = null;
    }, []);

    const setOpen = React.useCallback(
      (next: boolean) => {
        if (!isControlled) setInternalOpen(next);
        onOpenChange?.(next);
      },
      [isControlled, onOpenChange],
    );

    const show = React.useCallback(() => {
      clearTimers();
      showTimer.current = setTimeout(() => setOpen(true), delayDuration);
    }, [clearTimers, delayDuration, setOpen]);

    const hide = React.useCallback(() => {
      clearTimers();
      hideTimer.current = setTimeout(() => setOpen(false), skipDelayDuration);
    }, [clearTimers, skipDelayDuration, setOpen]);

    React.useEffect(() => clearTimers, [clearTimers]);

    const ctx = React.useMemo<TooltipContextValue>(
      () => ({ open, setOpen, side }),
      [open, setOpen, side],
    );

    return (
      <TooltipContext.Provider value={ctx}>
        <div
          ref={ref}
          className={cn('relative inline-flex', className)}
          onMouseEnter={show}
          onMouseLeave={hide}
          onFocus={show}
          onBlur={hide}
          {...props}
        >
          {children}
        </div>
      </TooltipContext.Provider>
    );
  },
);
Tooltip.displayName = 'Tooltip';

function useTooltip(): TooltipContextValue {
  const ctx = React.useContext(TooltipContext);
  if (!ctx) throw new Error('Tooltip 子组件必须在 <Tooltip> 内使用');
  return ctx;
}

// TooltipTrigger — 触发元素(直接渲染子元素)
const TooltipTrigger = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div ref={ref} className={cn('inline-flex', className)} {...props}>
      {children}
    </div>
  ),
);
TooltipTrigger.displayName = 'TooltipTrigger';

// TooltipContent — 浮层内容,根据 side 自动定位
const TooltipContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, style, ...props }, ref) => {
    const ctx = useTooltip();
    if (!ctx.open) return null;

    // 根据 side 计算定位 + 箭头位置
    const positionClass =
      ctx.side === 'top'
        ? 'bottom-full left-1/2 -translate-x-1/2 mb-2'
        : ctx.side === 'bottom'
          ? 'top-full left-1/2 -translate-x-1/2 mt-2'
          : ctx.side === 'left'
            ? 'right-full top-1/2 -translate-y-1/2 mr-2'
            : 'left-full top-1/2 -translate-y-1/2 ml-2';

    // 箭头定位(三角形通过 border 实现) — 颜色与内容背景一致(zinc-900)
    const arrowClass =
      ctx.side === 'top'
        ? 'left-1/2 top-full -translate-x-1/2 -mt-px border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-zinc-900'
        : ctx.side === 'bottom'
          ? 'left-1/2 bottom-full -translate-x-1/2 -mb-px border-l-4 border-r-4 border-b-4 border-l-transparent border-r-transparent border-b-zinc-900'
          : ctx.side === 'left'
            ? 'top-1/2 left-full -translate-y-1/2 -ml-px border-t-4 border-b-4 border-r-4 border-t-transparent border-b-transparent border-r-zinc-900'
            : 'top-1/2 right-full -translate-y-1/2 -mr-px border-t-4 border-b-4 border-l-4 border-t-transparent border-b-transparent border-l-zinc-900';

    return (
      <div
        ref={ref}
        role="tooltip"
        className={cn(
          'absolute z-50 animate-[tooltip-fade_150ms_ease-out]',
          // 暗色背景 + 白色文字 — 使用 zinc 色板保证在亮/暗主题下均为深色
          'rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-zinc-50 shadow-md',
          'pointer-events-none',
          positionClass,
          className,
        )}
        style={style}
        {...props}
      >
        {children}
        {/* 箭头 */}
        <span aria-hidden="true" className={cn('absolute h-0 w-0', arrowClass)} />
      </div>
    );
  },
);
TooltipContent.displayName = 'TooltipContent';

export { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent };
