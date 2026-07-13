import { useEffect, useState } from 'react';
import { auth, type AuthUser } from '@fnixagent/sdk';
import { AdminLogin } from './pages/AdminLogin';
import { Dashboard } from './pages/Dashboard';
import { UserManagement } from './pages/UserManagement';
import { AuditLogs } from './pages/AuditLogs';
import { SystemConfig } from './pages/SystemConfig';
import { RoleManagement } from './pages/RoleManagement';
import { DepartmentManagement } from './pages/DepartmentManagement';
import { PositionManagement } from './pages/PositionManagement';
import { LdapConfigManagement } from './pages/LdapConfigManagement';
import { SsoConfigManagement } from './pages/SsoConfigManagement';
import { MfaManagement } from './pages/MfaManagement';
import { ModerationConfigPage } from './pages/ModerationConfigPage';
import { PermissionProvider, usePermissions } from './contexts/PermissionContext';

type Tab =
  | 'dashboard'
  | 'users'
  | 'roles'
  | 'departments'
  | 'positions'
  | 'ldap'
  | 'sso'
  | 'mfa'
  | 'moderation'
  | 'logs'
  | 'config';

interface NavItem {
  key: Tab;
  label: string;
  icon: string;
  perm?: string;
  group: 'overview' | 'access' | 'security' | 'system';
}

const NAV_ITEMS: NavItem[] = [
  // 总览
  { key: 'dashboard', label: '控制面板', icon: 'M', group: 'overview' },
  // 访问控制
  { key: 'users', label: '用户管理', icon: 'U', perm: 'user:read', group: 'access' },
  { key: 'roles', label: '角色管理', icon: 'R', perm: 'role:read', group: 'access' },
  { key: 'departments', label: '部门管理', icon: 'D', perm: 'department:read', group: 'access' },
  { key: 'positions', label: '职位管理', icon: 'P', perm: 'position:read', group: 'access' },
  // 安全
  { key: 'ldap', label: 'LDAP/AD', icon: 'L', perm: 'system:config', group: 'security' },
  { key: 'sso', label: 'SSO 单点登录', icon: 'S', perm: 'system:config', group: 'security' },
  { key: 'mfa', label: 'MFA 多因素', icon: 'M', perm: 'system:config', group: 'security' },
  { key: 'moderation', label: '内容审核', icon: 'C', perm: 'system:config', group: 'security' },
  // 系统
  { key: 'logs', label: '审计日志', icon: 'A', perm: 'system:audit_log', group: 'system' },
  { key: 'config', label: '系统配置', icon: 'X', perm: 'system:config', group: 'system' },
];

const GROUP_LABELS: Record<string, string> = {
  overview: '总览',
  access: '访问控制',
  security: '安全策略',
  system: '系统',
};

/**
 * fnixagent 管理后台根组件
 *
 * Phase 4.2:侧边栏 + 极简设计,核心操作直达
 */
export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await auth.loadStoredTokens();
        const current = await auth.getCurrentUser();
        if (!cancelled) setUser(current);
      } catch {
        /* 忽略 */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 暗色模式切换
  useEffect(() => {
    if (dark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [dark]);

  async function handleLogin(u: AuthUser) {
    setUser(u);
  }

  async function handleLogout() {
    await auth.logout();
    setUser(null);
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
          加载中...
        </div>
      </div>
    );
  }

  if (!user) {
    return <AdminLogin onLogin={handleLogin} />;
  }

  if (user.role !== 'admin') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-surface">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-xl text-destructive">
          ⛔
        </div>
        <p className="text-lg font-medium">403 Forbidden</p>
        <p className="text-sm text-muted-foreground">
          账号 {user.username} 无管理员权限
        </p>
        <button onClick={handleLogout} className="btn-secondary mt-2">
          退出登录
        </button>
      </div>
    );
  }

  return (
    <PermissionProvider>
      <AdminShell user={user} dark={dark} onToggleDark={() => setDark((v) => !v)} onLogout={handleLogout} />
    </PermissionProvider>
  );
}

function AdminShell({
  user,
  dark,
  onToggleDark,
  onLogout,
}: {
  user: AuthUser;
  dark: boolean;
  onToggleDark: () => void;
  onLogout: () => void;
}) {
  const { hasPermission } = usePermissions();
  const visibleItems = NAV_ITEMS.filter((t) => !t.perm || hasPermission(t.perm));
  const [tab, setTab] = useState<Tab>('dashboard');

  // 当前 tab 无权限时回退
  const currentItem = visibleItems.find((t) => t.key === tab);
  const currentTab = currentItem ? tab : (visibleItems[0]?.key ?? 'dashboard');

  // 分组
  const grouped: Record<string, NavItem[]> = {};
  for (const item of visibleItems) {
    if (!grouped[item.group]) grouped[item.group] = [];
    grouped[item.group].push(item);
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      {/* 侧边栏 */}
      <aside className="flex w-56 flex-col bg-sidebar text-sidebar-foreground">
        {/* Logo */}
        <div className="flex h-14 items-center gap-2 px-5">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-white">
            OA
          </div>
          <span className="text-sm font-semibold">fnixagent</span>
        </div>

        {/* 导航 */}
        <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-3">
          {(['overview', 'access', 'security', 'system'] as const).map((group) => {
            const items = grouped[group] || [];
            if (items.length === 0) return null;
            return (
              <div key={group} className="space-y-1">
                <div className="px-3 py-1 text-[10px] font-medium uppercase tracking-wider text-sidebar-foreground/40">
                  {GROUP_LABELS[group]}
                </div>
                {items.map((item) => (
                  <button
                    key={item.key}
                    onClick={() => setTab(item.key)}
                    className={currentTab === item.key ? 'nav-item-active w-full' : 'nav-item w-full'}
                  >
                    <span className="flex h-5 w-5 items-center justify-center rounded text-xs font-medium">
                      {item.icon}
                    </span>
                    <span className="flex-1 text-left">{item.label}</span>
                  </button>
                ))}
              </div>
            );
          })}
        </nav>

        {/* 用户信息 */}
        <div className="border-t border-sidebar-hover px-3 py-3">
          <div className="flex items-center gap-2 px-2 py-1.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/20 text-xs font-medium text-primary">
              {user.username.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="truncate text-xs font-medium">{user.username}</div>
              <div className="truncate text-[10px] text-sidebar-foreground/50">{user.role}</div>
            </div>
          </div>
        </div>
      </aside>

      {/* 主区域 */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* 顶部栏 */}
        <header className="flex h-14 items-center justify-between border-b border-border bg-background px-6">
          <h1 className="text-sm font-medium">
            {visibleItems.find((t) => t.key === currentTab)?.label ?? '控制面板'}
          </h1>
          <div className="flex items-center gap-2">
            <button
              onClick={onToggleDark}
              className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-surface-2 hover:text-foreground"
              title={dark ? '切换到亮色' : '切换到暗色'}
            >
              {dark ? '☀' : '🌙'}
            </button>
            <button
              onClick={onLogout}
              className="btn-ghost h-8 px-3 text-xs"
            >
              退出
            </button>
          </div>
        </header>

        {/* 内容区 */}
        <main className="flex-1 overflow-auto bg-surface p-6">
          {currentTab === 'dashboard' && <Dashboard />}
          {currentTab === 'users' && <UserManagement />}
          {currentTab === 'roles' && <RoleManagement />}
          {currentTab === 'departments' && <DepartmentManagement />}
          {currentTab === 'positions' && <PositionManagement />}
          {currentTab === 'ldap' && <LdapConfigManagement />}
          {currentTab === 'sso' && <SsoConfigManagement />}
          {currentTab === 'mfa' && <MfaManagement />}
          {currentTab === 'moderation' && <ModerationConfigPage />}
          {currentTab === 'logs' && <AuditLogs />}
          {currentTab === 'config' && <SystemConfig />}
        </main>
      </div>
    </div>
  );
}
