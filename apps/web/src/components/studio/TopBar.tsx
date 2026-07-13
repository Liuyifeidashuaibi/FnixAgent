/**
 * fnixagent Studio — 顶栏 (Cursor 风格)
 *
 * 左:Logo + IDE/SOLO 模式切换
 * 中:面包屑(workspace 名 > 当前文件路径)
 * 右:Composer 模式 Tab + Review Changes 按钮 + 主题切换 + 用户 + 设置
 */
import { Badge, Button } from '@fnixagent/ui';
import { useAuth } from '../../contexts/AuthContext';
import { useStudio } from '../../stores/studio-store';
import type { ComposerMode } from '../../stores/types';
import {
  DiffIcon,
  MoonIcon,
  SettingsIcon,
  SunIcon,
  UserIcon,
} from './icons';

const COMPOSER_MODES: ComposerMode[] = ['ask', 'edit', 'agent'];
const MODE_LABELS: Record<ComposerMode, string> = {
  ask: 'Ask',
  edit: 'Edit',
  agent: 'Agent',
};

interface TopBarProps {
  /** 点击 Review Changes 时触发 */
  onReviewChanges?: () => void;
  /** 切换主题回调 */
  onToggleTheme?: () => void;
}

/** 顶栏 — 48px 高,浅色 border-b */
export function TopBar({ onReviewChanges, onToggleTheme }: TopBarProps) {
  const { state, dispatch } = useStudio();
  const { user } = useAuth();
  const { mode, composerMode, theme, activeFile, pendingDiff } = state;

  // 待确认变更数量
  const pendingCount =
    pendingDiff?.filter((c) => c.status === 'pending').length ?? 0;

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border bg-background px-3">
      {/* 左:Logo + 模式切换 */}
      <div className="flex items-center gap-3">
        <span className="text-sm font-semibold text-foreground">
          fnixagent
        </span>
        {/* IDE / SOLO Segmented Control */}
        <div className="inline-flex rounded-md border border-border bg-secondary/40 p-0.5 text-xs">
          {(['ide', 'solo'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => dispatch({ type: 'SET_MODE', mode: m })}
              className={`rounded px-2.5 py-1 font-medium transition-colors ${
                mode === m
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {m === 'ide' ? 'IDE' : 'SOLO'}
            </button>
          ))}
        </div>
      </div>

      {/* 中:面包屑 */}
      <div className="flex min-w-0 flex-1 items-center justify-center px-4">
        <span className="truncate text-xs text-muted-foreground">
          workspace
          {activeFile ? (
            <>
              <span className="mx-1">›</span>
              <span className="text-foreground/70">{activeFile}</span>
            </>
          ) : null}
        </span>
      </div>

      {/* 右:Composer 模式 + 操作 */}
      <div className="flex items-center gap-2">
        {/* Composer 模式 Tab */}
        <div className="inline-flex items-center rounded-md border border-border bg-secondary/40 p-0.5 text-xs">
          {COMPOSER_MODES.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => dispatch({ type: 'SET_COMPOSER_MODE', mode: m })}
              className={`rounded px-2.5 py-1 font-medium transition-colors ${
                composerMode === m
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {MODE_LABELS[m]}
            </button>
          ))}
        </div>

        {/* Review Changes 按钮 */}
        <Button
          variant="outline"
          size="sm"
          className="relative h-7 gap-1.5 text-xs"
          onClick={onReviewChanges}
        >
          <DiffIcon width={14} height={14} />
          <span>Review</span>
          {pendingCount > 0 && (
            <Badge variant="default" className="ml-0.5 h-4 px-1 text-[10px]">
              {pendingCount}
            </Badge>
          )}
        </Button>

        {/* 主题切换 */}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onToggleTheme}
          title="切换主题"
        >
          {theme === 'dark' ? (
            <SunIcon width={16} height={16} />
          ) : (
            <MoonIcon width={16} height={16} />
          )}
        </Button>

        {/* 用户头像 */}
        <div
          className="flex h-7 w-7 items-center justify-center rounded-full bg-secondary text-muted-foreground"
          title={user?.username ?? '用户'}
        >
          <UserIcon width={16} height={16} />
        </div>

        {/* 设置 */}
        <Button variant="ghost" size="icon" className="h-7 w-7" title="设置">
          <SettingsIcon width={16} height={16} />
        </Button>
      </div>
    </header>
  );
}
