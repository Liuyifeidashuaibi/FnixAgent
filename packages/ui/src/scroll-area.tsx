import * as React from 'react';
import { cn } from './utils';

// shadcn/ui ScrollArea 组件 — 简化实现
// 通过 div + overflow-auto + 自定义滚动条样式实现,支持垂直/水平滚动
// 注:滚动条样式通过 Tailwind 任意值类名 + webkit-scrollbar 实现

export interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  // 滚动方向,默认 vertical(同时支持水平和垂直时使用 both)
  orientation?: 'vertical' | 'horizontal' | 'both';
}

const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ className, orientation = 'vertical', children, ...props }, ref) => {
    // 根据方向决定 overflow 策略
    const overflowClass =
      orientation === 'vertical'
        ? 'overflow-y-auto overflow-x-hidden'
        : orientation === 'horizontal'
          ? 'overflow-x-auto overflow-y-hidden'
          : 'overflow-auto';

    return (
      <div
        ref={ref}
        className={cn(
          'relative',
          // 自定义 webkit 滚动条样式 — 细窄、半透明、圆角
          '[&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar]:h-2',
          '[&::-webkit-scrollbar-track]:bg-transparent',
          '[&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [&::-webkit-scrollbar-thumb]:hover:bg-muted-foreground/40',
          // Firefox 滚动条
          '[scrollbar-width:thin] [scrollbar-color:hsl(var(--border))_transparent]',
          overflowClass,
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);
ScrollArea.displayName = 'ScrollArea';

export { ScrollArea };
