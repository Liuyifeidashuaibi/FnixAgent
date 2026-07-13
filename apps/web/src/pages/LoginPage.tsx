import { useState, type FormEvent } from 'react';
import { Button, Card, Input } from '@officeagent/ui';
import { useAuth } from '../contexts/AuthContext';

interface LoginPageProps {
  onSwitchToRegister: () => void;
}

/**
 * 登录页 — Phase 1.7
 *
 * 流程:
 *   1. 用户输入用户名/密码
 *   2. 前端调用 /auth/pubkey 获取 RSA 公钥
 *   3. 用公钥加密密码(RSA-OAEP-SHA256)
 *   4. POST /auth/login 携带密文密码 + 设备指纹
 *   5. 收到双 Token 后持久化(safeStorage / localStorage)
 *   6. 进入主应用
 *
 * 安全:
 *   - 密码绝不以明文形式传输
 *   - 设备指纹绑定 Token(不同设备登录互不踢)
 */
export function LoginPage({ onSwitchToRegister }: LoginPageProps) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await login(username.trim(), password, remember);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <div className="border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold">OfficeAgent 登录</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            智能办公助手 · 安全登录
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="username">
              用户名
            </label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="请输入用户名"
              autoComplete="username"
              disabled={loading}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="password">
              密码
            </label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="请输入密码"
              autoComplete="current-password"
              disabled={loading}
            />
          </div>
          <label className="flex items-center gap-2 text-sm select-none">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              disabled={loading}
              className="h-4 w-4 rounded border-border"
            />
            <span>记住我(7 天免登录)</span>
          </label>
          {error && (
            <p className="text-sm text-red-500 bg-red-500/10 rounded px-3 py-2">
              ⚠️ {error}
            </p>
          )}
          <Button type="submit" disabled={loading} className="w-full">
            {loading ? '登录中...' : '登录'}
          </Button>
          <div className="text-center text-sm text-muted-foreground">
            还没有账号?{' '}
            <button
              type="button"
              onClick={onSwitchToRegister}
              className="text-primary hover:underline"
              disabled={loading}
            >
              立即注册
            </button>
          </div>
        </form>
        <div className="border-t border-border px-6 py-3 text-xs text-muted-foreground">
          🔒 密码使用 RSA-2048 加密传输,双 Token 鉴权
        </div>
      </Card>
    </div>
  );
}
