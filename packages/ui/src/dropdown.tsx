import * as React from 'react';
import { cn } from './utils';

// 注入 dropdown 进出 keyframes(模块级,只注入一次,SSR 安全)
const __DROPDOWN_STYLE_ID = '__fnixagent_ui_dropdown_keyframes__';
if (typeof document !== 'undefined' && !document.getElementById(__DROPDOWN_STYLE_ID)) {
  const style = document.createElement('style');
  style.id = __DROPDOWN_STYLE_ID;
  style.textContent =
    '@keyframes dropdown-fade{from{opacity:0;transform:scale(0.95) translateY(-4px)}to{opacity:1;transform:scale(1) translateY(0)}}';
  document.head.appendChild(style);
}

// shadcn/ui DropdownMenu 组件族 — 纯 React 实现
// 点击触发,点击外部关闭;上下文菜单风格:min-w-[8rem] + 暗色背景 + hover 高亮

interface DropdownMenuContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const DropdownMenuContext = React.createContext<DropdownMenuContextValue | null>(null);

function useDropdownMenu(): DropdownMenuContextValue {
  const ctx = React.useContext(DropdownMenuContext);
  if (!ctx) throw new Error('DropdownMenu 子组件必须在 <DropdownMenu> 内使用');
  return ctx;
}

export interface DropdownMenuProps extends React.HTMLAttributes<HTMLDivElement> {
  // 受控开关
  open?: boolean;
  // 非受控默认开关
  defaultOpen?: boolean;
  // 开关回调
  onOpenChange?: (open: boolean) => void;
}

// DropdownMenu — 根上下文容器,管理开关状态 + 点击外部关闭
// 内容面板(DropdownMenuContent)用 absolute 贴此容器定位,因此无需触发器 ref
const DropdownMenu = React.forwardRef<HTMLDivElement, DropdownMenuProps>(
  ({ open: openProp, defaultOpen, onOpenChange, className, children, ...props }, ref) => {
    const [internalOpen, setInternalOpen] = React.useState(defaultOpen ?? false);
    const isControlled = openProp !== undefined;
    const open = isControlled ? openProp : internalOpen;
    // 容器 ref,用于点击外部关闭判定;同时合并外部传入的 forwarded ref
    const containerRef = React.useRef<HTMLDivElement | null>(null);

    const setOpen = React.useCallback(
      (next: boolean) => {
        if (!isControlled) setInternalOpen(next);
        onOpenChange?.(next);
      },
      [isControlled, onOpenChange],
    );

    // 点击外部 / ESC 关闭
    React.useEffect(() => {
      if (!open) return;
      const onClick = (e: MouseEvent) => {
        const target = e.target as Node;
        if (containerRef.current && !containerRef.current.contains(target)) {
          setOpen(false);
        }
      };
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') setOpen(false);
      };
      document.addEventListener('mousedown', onClick);
      document.addEventListener('keydown', onKey);
      return () => {
        document.removeEventListener('mousedown', onClick);
        document.removeEventListener('keydown', onKey);
      };
    }, [open, setOpen]);

    const ctx = React.useMemo<DropdownMenuContextValue>(
      () => ({ open, setOpen }),
      [open, setOpen],
    );

    // 合并内部 containerRef 与外部 forwarded ref
    const setContainerRef = (node: HTMLDivElement | null) => {
      containerRef.current = node;
      if (typeof ref === 'function') ref(node);
      else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node;
    };

    return (
      <DropdownMenuContext.Provider value={ctx}>
        <div ref={setContainerRef} className={cn('relative inline-block', className)} {...props}>
          {children}
        </div>
      </DropdownMenuContext.Provider>
    );
  },
);
DropdownMenu.displayName = 'DropdownMenu';

export interface DropdownMenuTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {}

// DropdownMenuTrigger — 点击切换菜单
const DropdownMenuTrigger = React.forwardRef<HTMLButtonElement, DropdownMenuTriggerProps>(
  ({ children, onClick, ...props }, ref) => {
    const ctx = useDropdownMenu();
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      if (e.defaultPrevented) return;
      e.stopPropagation();
      ctx.setOpen(!ctx.open);
    };

    return (
      <button ref={ref} type="button" onClick={handleClick} {...props}>
        {children}
      </button>
    );
  },
);
DropdownMenuTrigger.displayName = 'DropdownMenuTrigger';

// DropdownMenuContent — 下拉菜单面板,绝对定位贴触发器下方
const DropdownMenuContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, style, ...props }, ref) => {
    const ctx = useDropdownMenu();
    if (!ctx.open) return null;

    return (
      <div
        ref={ref}
        role="menu"
        className={cn(
          'absolute left-0 top-full z-50 mt-1 min-w-[8rem] origin-top',
          'animate-[dropdown-fade_150ms_ease-out]',
          // 使用 background + border:这两个 token 在所有 app 的 tailwind 配置中均存在
          'overflow-hidden rounded-md border border-border bg-background p-1 text-foreground shadow-md',
          className,
        )}
        style={style}
        {...props}
      >
        {children}
      </div>
    );
  },
);
DropdownMenuContent.displayName = 'DropdownMenuContent';

export interface DropdownMenuItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  // 右侧灰色快捷键提示文字(如 "⌘K")
  shortcut?: string;
  // 是否禁用
  disabled?: boolean;
}

// DropdownMenuItem — 菜单项,hover 高亮;点击后自动关闭菜单
const DropdownMenuItem = React.forwardRef<HTMLButtonElement, DropdownMenuItemProps>(
  ({ className, children, shortcut, disabled, onClick, ...props }, ref) => {
    const ctx = useDropdownMenu();
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      if (e.defaultPrevented) return;
      ctx.setOpen(false);
    };

    return (
      <button
        ref={ref}
        type="button"
        role="menuitem"
        disabled={disabled}
        onClick={handleClick}
        className={cn(
          'relative flex w-full cursor-pointer select-none items-center justify-between gap-4 rounded-sm px-2 py-1.5 text-sm outline-none',
          // hover/focus 高亮:用 secondary(在所有 app 配置中均有定义)
          'transition-colors focus:bg-secondary focus:text-secondary-foreground',
          'hover:bg-secondary hover:text-secondary-foreground',
          'disabled:pointer-events-none disabled:opacity-50',
          className,
        )}
        {...props}
      >
        <span className="flex-1 text-left">{children}</span>
        {shortcut && <span className="text-xs text-muted-foreground">{shortcut}</span>}
      </button>
    );
  },
);
DropdownMenuItem.displayName = 'DropdownMenuItem';

// DropdownMenuSeparator — 分隔线
const DropdownMenuSeparator = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} role="separator" className={cn('-mx-1 my-1 h-px bg-border', className)} {...props} />
));
DropdownMenuSeparator.displayName = 'DropdownMenuSeparator';

// DropdownMenuLabel — 分组标题
const DropdownMenuLabel = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('px-2 py-1.5 text-xs font-semibold text-muted-foreground', className)}
      {...props}
    />
  ),
);
DropdownMenuLabel.displayName = 'DropdownMenuLabel';

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
};
