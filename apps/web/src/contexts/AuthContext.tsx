import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { auth, type AuthUser } from '@fnixagent/sdk';

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  login: (username: string, password: string, remember: boolean) => Promise<void>;
  register: (input: {
    username: string;
    email?: string;
    password: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

/**
 * 鉴权上下文 Provider — Phase 1.7
 *
 * 启动时从存储加载 Token 并获取当前用户,
 * 若 Access Token 过期会自动通过 Refresh Token 刷新。
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 启动时加载已保存的 Token 并获取用户
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await auth.loadStoredTokens();
        const current = await auth.getCurrentUser();
        if (!cancelled) setUser(current);
      } catch (err) {
        console.warn('[auth] 启动加载失败:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (username: string, password: string, remember: boolean) => {
      setError(null);
      try {
        await auth.login(username, password, remember);
        const current = await auth.getCurrentUser();
        setUser(current);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      }
    },
    [],
  );

  const register = useCallback(
    async (input: { username: string; email?: string; password: string }) => {
      setError(null);
      try {
        await auth.register(input);
        // 注册成功后自动登录
        await auth.login(input.username, input.password, false);
        const current = await auth.getCurrentUser();
        setUser(current);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        throw err;
      }
    },
    [],
  );

  const logout = useCallback(async () => {
    await auth.logout();
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    const current = await auth.getCurrentUser();
    setUser(current);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, loading, error, login, register, logout, refreshUser }),
    [user, loading, error, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/** 使用鉴权上下文 */
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必须在 AuthProvider 内使用');
  return ctx;
}
