import { useState, type FormEvent } from 'react';
import { Button, Card, Input } from '@fnixagent/ui';
import { useAuth } from '../contexts/AuthContext';

interface RegisterPageProps {
  onSwitchToLogin: () => void;
}

/**
 * 注册页 — Phase 1.7
 *
 * 字段:用户名 / 邮箱 / 密码 / 确认密码
 * 校验:用户名 3-64 位 / 邮箱格式 / 密码 6-128 位 / 两次密码一致
 */
export function RegisterPage({ onSwitchToLogin }: RegisterPageProps) {
  const { register } = useAuth();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function validate(): string | null {
    if (!username.trim()) return '请输入用户名';
    if (username.trim().length < 3 || username.trim().length > 64) {
      return '用户名需 3-64 位';
    }
    if (!/^[a-zA-Z0-9_\u4e00-\u9fa5]+$/.test(username.trim())) {
      return '用户名仅支持字母/数字/下划线/中文';
    }
    if (email && !/^[\w.+-]+@[\w-]+\.[\w.-]+$/.test(email)) {
      return '邮箱格式不正确';
    }
    if (!password) return '请输入密码';
    if (password.length < 6 || password.length > 128) {
      return '密码需 6-128 位';
    }
    if (password !== confirm) return '两次密码不一致';
    return null;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await register({
        username: username.trim(),
        email: email.trim() || undefined,
        password,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <div className="border-b border-border px-6 py-4">
          <h1 className="text-xl font-semibold">注册 fnixagent 账号</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            创建账号,开始智能办公
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="reg-username">
              用户名
            </label>
            <Input
              id="reg-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="3-64 位,字母/数字/下划线/中文"
              autoComplete="username"
              disabled={loading}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="reg-email">
              邮箱(可选)
            </label>
            <Input
              id="reg-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              autoComplete="email"
              disabled={loading}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="reg-password">
              密码
            </label>
            <Input
              id="reg-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="6-128 位"
              autoComplete="new-password"
              disabled={loading}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="reg-confirm">
              确认密码
            </label>
            <Input
              id="reg-confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="再次输入密码"
              autoComplete="new-password"
              disabled={loading}
            />
          </div>
          {error && (
            <p className="text-sm text-red-500 bg-red-500/10 rounded px-3 py-2">
              ⚠️ {error}
            </p>
          )}
          <Button type="submit" disabled={loading} className="w-full">
            {loading ? '注册中...' : '注册'}
          </Button>
          <div className="text-center text-sm text-muted-foreground">
            已有账号?{' '}
            <button
              type="button"
              onClick={onSwitchToLogin}
              className="text-primary hover:underline"
              disabled={loading}
            >
              返回登录
            </button>
          </div>
        </form>
        <div className="border-t border-border px-6 py-3 text-xs text-muted-foreground">
          🔒 密码使用 Argon2id 哈希存储,客户端 RSA 加密传输
        </div>
      </Card>
    </div>
  );
}
