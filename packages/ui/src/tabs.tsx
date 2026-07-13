import * as React from 'react';
import { cn } from './utils';

// 注入自定义动画 keyframes(模块级,只注入一次,SSR 安全)
const __TABS_STYLE_ID = '__fnixagent_ui_tabs_keyframes__';
if (typeof document !== 'undefined' && !document.getElementById(__TABS_STYLE_ID)) {
  const style = document.createElement('style');
  style.id = __TABS_STYLE_ID;
  style.textContent =
    '@keyframes tab-underline{from{opacity:0;transform:translateY(2px)}to{opacity:1;transform:translateY(0)}}@keyframes tab-fade{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}';
  document.head.appendChild(style);
}

// shadcn/ui Tabs 组件族 — 受控/非受控两用
// 下划线风格:TabsList 横向 + TabsTrigger 选中态用 primary 色下划线

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

// 使用 tabs context;若不在 Tabs 内使用则抛错
function useTabs(): TabsContextValue {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error('Tabs 子组件必须在 <Tabs> 内使用');
  return ctx;
}

export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  // 受控值
  value?: string;
  // 非受控默认值
  defaultValue?: string;
  // 值变化回调
  onValueChange?: (value: string) => void;
}

const Tabs = React.forwardRef<HTMLDivElement, TabsProps>(
  ({ value: valueProp, defaultValue, onValueChange, className, children, ...props }, ref) => {
    // 内部状态用于非受控模式
    const [internalValue, setInternalValue] = React.useState(defaultValue ?? '');
    const isControlled = valueProp !== undefined;
    const value = isControlled ? valueProp : internalValue;

    const setValue = React.useCallback(
      (next: string) => {
        if (!isControlled) setInternalValue(next);
        onValueChange?.(next);
      },
      [isControlled, onValueChange],
    );

    const ctx = React.useMemo<TabsContextValue>(() => ({ value, setValue }), [value, setValue]);

    return (
      <TabsContext.Provider value={ctx}>
        <div ref={ref} className={cn('w-full', className)} {...props}>
          {children}
        </div>
      </TabsContext.Provider>
    );
  },
);
Tabs.displayName = 'Tabs';

// TabsList — 横向布局容器,底部为下划线轨道
const TabsList = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      role="tablist"
      className={cn(
        'inline-flex h-auto w-full items-center gap-1 border-b border-border',
        className,
      )}
      {...props}
    />
  ),
);
TabsList.displayName = 'TabsList';

export interface TabsTriggerProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  // 该触发器对应的标签值
  value: string;
}

// TabsTrigger — 单个标签按钮,选中时显示 primary 色下划线 + 文字高亮
const TabsTrigger = React.forwardRef<HTMLButtonElement, TabsTriggerProps>(
  ({ className, value, children, ...props }, ref) => {
    const ctx = useTabs();
    const selected = ctx.value === value;

    return (
      <button
        ref={ref}
        type="button"
        role="tab"
        aria-selected={selected}
        data-state={selected ? 'active' : 'inactive'}
        onClick={() => ctx.setValue(value)}
        className={cn(
          'relative inline-flex items-center justify-center whitespace-nowrap px-3 py-2 text-sm font-medium transition-colors',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          'disabled:pointer-events-none disabled:opacity-50',
          // 选中态:文字用 primary 色 + 底部下划线;border-b-2 贴合 List 底边
          selected
            ? 'text-primary'
            : 'text-muted-foreground hover:text-foreground',
          className,
        )}
        {...props}
      >
        {children}
        {/* 选中下划线 — 带 fade-in + slide-up 动画 */}
        {selected && (
          <span
            aria-hidden="true"
            className="absolute bottom-0 left-0 right-0 -mb-px h-0.5 bg-primary animate-[tab-underline_200ms_ease-out]"
          />
        )}
      </button>
    );
  },
);
TabsTrigger.displayName = 'TabsTrigger';

export interface TabsContentProps extends React.HTMLAttributes<HTMLDivElement> {
  // 该面板对应的标签值
  value: string;
}

// TabsContent — 标签内容面板,仅当前选中时显示,带淡入动画
const TabsContent = React.forwardRef<HTMLDivElement, TabsContentProps>(
  ({ className, value, children, ...props }, ref) => {
    const ctx = useTabs();
    const selected = ctx.value === value;
    if (!selected) return null;

    return (
      <div
        ref={ref}
        role="tabpanel"
        className={cn(
          'mt-2 animate-[tab-fade_200ms_ease-out]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);
TabsContent.displayName = 'TabsContent';

export { Tabs, TabsList, TabsTrigger, TabsContent };
