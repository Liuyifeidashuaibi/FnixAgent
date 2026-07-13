import { Button } from '@fnixagent/ui';
import { useAuth } from '../contexts/AuthContext';

interface TopBarProps {
  theme: 'light' | 'dark';
  onToggleTheme: () => void;
}

/**
 * 顶部工具栏 — 用户头像 / 设置 / 主题切换 / 登出
 * Phase 1.7: 集成 AuthContext 显示当前用户并提供登出
 */
export function TopBar({ theme, onToggleTheme }: TopBarProps) {
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
  }

  return (
    <header className="flex items-center justify-between border-b border-border bg-background px-4 py-2 h-12 shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-lg font-bold">fnixagent</span>
      </div>
      <div className="flex items-center gap-2">
        {user && (
          <>
            <span className="text-sm text-muted-foreground">
              {user.username}
              {user.role === 'admin' && (
                <span className="ml-1 text-xs text-primary">[admin]</span>
              )}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              title="登出"
            >
              登出
            </Button>
          </>
        )}
        <Button variant="ghost" size="icon" onClick={onToggleTheme} title="切换主题">
          {theme === 'dark' ? '☀️' : '🌙'}
        </Button>
        <Button variant="ghost" size="icon" title="设置">
          ⚙️
        </Button>
      </div>
    </header>
  );
}
