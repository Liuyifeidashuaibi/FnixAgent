import * as React from 'react';
import { createPortal } from 'react-dom';
import { cn } from './utils';

// shadcn/ui Dialog 组件族 — 模态弹窗
// 不使用 Radix Portal,改用 react-dom 的 createPortal 自实现
// 支持 ESC 关闭、点击外部关闭、锁定 body 滚动、进出动画(fade + scale)

interface DialogContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

function useDialog(): DialogContextValue {
  const ctx = React.useContext(DialogContext);
  if (!ctx) throw new Error('Dialog 子组件必须在 <Dialog> 内使用');
  return ctx;
}

export interface DialogProps {
  // 受控开关
  open?: boolean;
  // 非受控默认开关
  defaultOpen?: boolean;
  // 开关变化回调
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

// Dialog — 根上下文提供者(不渲染任何 DOM)
const Dialog = ({ open: openProp, defaultOpen, onOpenChange, children }: DialogProps) => {
  const [internalOpen, setInternalOpen] = React.useState(defaultOpen ?? false);
  const isControlled = openProp !== undefined;
  const open = isControlled ? openProp : internalOpen;

  const setOpen = React.useCallback(
    (next: boolean) => {
      if (!isControlled) setInternalOpen(next);
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  const ctx = React.useMemo<DialogContextValue>(() => ({ open, setOpen }), [open, setOpen]);

  return <DialogContext.Provider value={ctx}>{children}</DialogContext.Provider>;
};
Dialog.displayName = 'Dialog';

export interface DialogTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

// DialogTrigger — 点击触发打开弹窗
const DialogTrigger = React.forwardRef<HTMLButtonElement, DialogTriggerProps>(
  ({ children, onClick, ...props }, ref) => {
    const ctx = useDialog();
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      if (!e.defaultPrevented) ctx.setOpen(true);
    };

    return (
      <button ref={ref} type="button" onClick={handleClick} {...props}>
        {children}
      </button>
    );
  },
);
DialogTrigger.displayName = 'DialogTrigger';

// DialogClose — 点击触发关闭弹窗
const DialogClose = React.forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
  ({ children, onClick, ...props }, ref) => {
    const ctx = useDialog();
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      if (!e.defaultPrevented) ctx.setOpen(false);
    };

    return (
      <button ref={ref} type="button" onClick={handleClick} {...props}>
        {children}
      </button>
    );
  },
);
DialogClose.displayName = 'DialogClose';

export interface DialogContentProps extends React.HTMLAttributes<HTMLDivElement> {
  // 是否禁用点击外部关闭,默认 false
  disableOutsideClick?: boolean;
}

// DialogContent — 弹窗主体内容,使用 createPortal 渲染到 document.body
const DialogContent = React.forwardRef<HTMLDivElement, DialogContentProps>(
  ({ className, children, disableOutsideClick = false, ...props }, ref) => {
    const ctx = useDialog();
    const [mounted, setMounted] = React.useState(false);
    const [visible, setVisible] = React.useState(false);

    // 仅在浏览器环境下挂载(SSR 安全)
    React.useEffect(() => {
      setMounted(true);
    }, []);

    // open 切换时,触发进入/退出动画 + 锁定 body 滚动
    React.useEffect(() => {
      if (!mounted) return;
      if (ctx.open) {
        // 进入:下一帧设置 visible 触发动画
        document.body.style.overflow = 'hidden';
        const id = window.requestAnimationFrame(() => setVisible(true));
        return () => window.cancelAnimationFrame(id);
      }
      // 退出:立即开始淡出
      setVisible(false);
      document.body.style.overflow = '';
    }, [ctx.open, mounted]);

    // ESC 关闭
    React.useEffect(() => {
      if (!ctx.open) return;
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') ctx.setOpen(false);
      };
      document.addEventListener('keydown', onKey);
      return () => document.removeEventListener('keydown', onKey);
    }, [ctx.open, ctx]);

    // 卸载时还原 body overflow
    React.useEffect(() => {
      return () => {
        document.body.style.overflow = '';
      };
    }, []);

    if (!mounted || !ctx.open) return null;

    return createPortal(
      <div
        className="fixed inset-0 z-50 flex items-center justify-center p-4"
        role="dialog"
        aria-modal="true"
      >
        {/* 背景遮罩 — blur + fade */}
        <div
          aria-hidden="true"
          onClick={() => {
            if (!disableOutsideClick) ctx.setOpen(false);
          }}
          className={cn(
            'absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity duration-200',
            visible ? 'opacity-100' : 'opacity-0',
          )}
        />
        {/* 内容卡片 — scale + fade */}
        <div
          ref={ref}
          className={cn(
            'relative z-10 w-full max-w-lg rounded-lg border bg-background p-6 shadow-lg',
            'transition-all duration-200',
            visible ? 'opacity-100 scale-100' : 'opacity-0 scale-95',
            className,
          )}
          {...props}
        >
          {children}
        </div>
      </div>,
      document.body,
    );
  },
);
DialogContent.displayName = 'DialogContent';

// DialogHeader — 标题区
const DialogHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col space-y-1.5 text-left', className)} {...props} />
  ),
);
DialogHeader.displayName = 'DialogHeader';

// DialogFooter — 底部操作区
const DialogFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)}
      {...props}
    />
  ),
);
DialogFooter.displayName = 'DialogFooter';

// DialogTitle — 标题
const DialogTitle = React.forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h2
      ref={ref}
      className={cn('text-lg font-semibold leading-none tracking-tight', className)}
      {...props}
    />
  ),
);
DialogTitle.displayName = 'DialogTitle';

// DialogDescription — 副标题/描述
const DialogDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
));
DialogDescription.displayName = 'DialogDescription';

export {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
  DialogClose,
};
