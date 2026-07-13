import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from './utils';

// shadcn/ui Badge 组件 — 用于展示状态徽标
// 用法示例: RUNNING=success / ERROR=destructive / PAUSED=warning
const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground hover:bg-primary/80',
        secondary:
          'border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80',
        destructive:
          'border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80',
        outline: 'text-foreground',
        // 成功态(绿色) — 用于 RUNNING 等正常运行状态
        success:
          'border-transparent bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/25',
        // 警告态(黄色) — 用于 PAUSED 等需关注状态
        warning:
          'border-transparent bg-amber-500/15 text-amber-600 dark:text-amber-400 hover:bg-amber-500/25',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <div ref={ref} className={cn(badgeVariants({ variant }), className)} {...props} />
  ),
);
Badge.displayName = 'Badge';

export { Badge, badgeVariants };
