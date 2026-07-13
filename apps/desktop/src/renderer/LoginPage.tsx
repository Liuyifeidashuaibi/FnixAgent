/**
 * OfficeAgent Desktop 登录页(Phase 3.0)
 *
 * 双 Tab 登录:
 *   - 国内:手机号 + 短信验证码(11 位中国大陆手机号)
 *   - 国外:Google OAuth(在系统浏览器中完成授权,通过 officeagent:// 协议回调)
 *
 * 登录成功后调用 onLogin 通知父组件切换到主应用视图。
 */
import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  auth,
  sdk,
  type AuthUser,
  type SsoProvider,
  type TokenInfo,
} from '@officeagent/sdk';

interface LoginPageProps {
  onLogin: (user: AuthUser) => void;
}

type TabKey = 'phone' | 'google';

const PHONE_PATTERN = /^1[3-9]\d{9}$/;

export function LoginPage({ onLogin }: LoginPageProps) {
  const [tab, setTab] = useState<TabKey>('phone');
  const [appInfo, setAppInfo] = useState('');

  useEffect(() => {
    if (window.electron) {
      setAppInfo(`v${window.electron.app.version} (${window.electron.app.platform})`);
    }
  }, []);

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <div style={styles.logo}>OA</div>
          <h1 style={styles.title}>OfficeAgent Desktop</h1>
          <p style={styles.subtitle}>{appInfo || '智能办公助手'}</p>
        </div>

        <div style={styles.tabs}>
          <button
            type="button"
            style={tab === 'phone' ? styles.tabActive : styles.tab}
            onClick={() => setTab('phone')}
          >
            手机号登录
          </button>
          <button
            type="button"
            style={tab === 'google' ? styles.tabActive : styles.tab}
            onClick={() => setTab('google')}
          >
            Google 登录
          </button>
        </div>

        {tab === 'phone' ? (
          <PhoneLoginForm onLogin={onLogin} />
        ) : (
          <GoogleLoginForm onLogin={onLogin} />
        )}

        <p style={styles.footer}>
          登录即表示同意 <a style={styles.link} href="#">用户协议</a> 与{' '}
          <a style={styles.link} href="#">隐私政策</a>
        </p>
      </div>
    </div>
  );
}

// ============================================================================
// 手机号 + 短信验证码登录(国内)
// ============================================================================

function PhoneLoginForm({ onLogin }: { onLogin: (user: AuthUser) => void }) {
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  function startCountdown() {
    setCountdown(60);
    timerRef.current = setInterval(() => {
      setCountdown((n) => {
        if (n <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          return 0;
        }
        return n - 1;
      });
    }, 1000);
  }

  async function handleSendCode() {
    setError(null);
    if (!PHONE_PATTERN.test(phone)) {
      setError('请输入正确的 11 位手机号');
      return;
    }
    setSending(true);
    try {
      await auth.sendSmsCode(phone);
      startCountdown();
    } catch (err) {
      setError(err instanceof Error ? err.message : '验证码发送失败');
    } finally {
      setSending(false);
    }
  }

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!PHONE_PATTERN.test(phone)) {
      setError('请输入正确的 11 位手机号');
      return;
    }
    if (!/^\d{6}$/.test(code)) {
      setError('请输入 6 位验证码');
      return;
    }
    setLoading(true);
    try {
      await auth.loginWithSms(phone, code, true);
      const user = await auth.getCurrentUser();
      if (!user) throw new Error('获取用户信息失败');
      onLogin(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form style={styles.form} onSubmit={handleLogin}>
      <div style={styles.field}>
        <label style={styles.label} htmlFor="phone-input">
          手机号
        </label>
        <input
          id="phone-input"
          style={styles.input}
          value={phone}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 11))}
          placeholder="请输入 11 位手机号"
          maxLength={11}
          autoFocus
          disabled={loading}
        />
      </div>

      <div style={styles.field}>
        <label style={styles.label} htmlFor="code-input">
          验证码
        </label>
        <div style={styles.codeRow}>
          <input
            id="code-input"
            style={{ ...styles.input, flex: 1 }}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="6 位验证码"
            maxLength={6}
            disabled={loading}
          />
          <button
            type="button"
            style={
              countdown > 0 || sending || !PHONE_PATTERN.test(phone)
                ? styles.codeBtnDisabled
                : styles.codeBtn
            }
            onClick={handleSendCode}
            disabled={countdown > 0 || sending || loading || !PHONE_PATTERN.test(phone)}
          >
            {sending ? '发送中...' : countdown > 0 ? `${countdown}s 后重试` : '发送验证码'}
          </button>
        </div>
      </div>

      {error && <div style={styles.error}>{error}</div>}

      <button type="submit" style={styles.submitBtn} disabled={loading}>
        {loading ? '登录中...' : '登录'}
      </button>
    </form>
  );
}

// ============================================================================
// Google OAuth 登录(国外)
// ============================================================================

function GoogleLoginForm({ onLogin }: { onLogin: (user: AuthUser) => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('');
  const [providers, setProviders] = useState<SsoProvider[]>([]);
  const unsubRef = useRef<(() => void) | null>(null);

  // 加载已配置的 OAuth provider(通常为 google / github)
  useEffect(() => {
    void (async () => {
      try {
        const resp = await sdk.sso.listProviders();
        const items = (resp.data?.items ?? []).filter(
          (p) => p.provider_type === 'oauth',
        );
        setProviders(items);
      } catch {
        // 后端可能未配置 SSO,忽略
      }
    })();
  }, []);

  // 订阅 OAuth 回调(自定义协议 officeagent://oauth/callback 触发)
  useEffect(() => {
    if (!window.electron?.oauth?.onCallback) return;
    const unsub = window.electron.oauth.onCallback(async (data) => {
      setStatus('收到授权码,正在换取 Token...');
      setError(null);
      try {
        const token: TokenInfo = await sdk.sso.oauthCallback({
          provider_code: data.provider_code,
          code: data.code,
          state: data.state,
        });
        // 复用 AuthManager 的 token 持久化(手动写入 storage)
        // oauthCallback 返回的字段与 TokenInfo 兼容
        await auth.persistExternalToken(token);
        const user = await auth.getCurrentUser();
        if (!user) throw new Error('获取用户信息失败');
        setStatus('');
        onLogin(user);
      } catch (err) {
        setStatus('');
        setError(err instanceof Error ? err.message : 'OAuth 登录失败');
        setLoading(false);
      }
    });
    unsubRef.current = unsub;
    return () => {
      if (unsubRef.current) unsubRef.current();
    };
  }, [onLogin]);

  async function handleGoogleLogin() {
    setError(null);
    setStatus('');
    // 优先使用已配置的 google provider,否则提示
    const googleProvider = providers.find(
      (p) => p.provider_code === 'google' || /google/i.test(p.name),
    );
    if (!googleProvider) {
      setError('后端尚未配置 Google OAuth。请联系管理员在管理后台「SSO 单点登录」中添加 Google provider。');
      return;
    }
    setLoading(true);
    try {
      // desktop 用 officeagent:// 自定义协议作为回调
      const redirectUri = 'officeagent://oauth/callback?provider=google';
      const resp = await sdk.sso.getOAuthAuthorizeUrl({
        provider_code: googleProvider.provider_code,
        redirect_uri: redirectUri,
      });
      const url = resp.data.authorization_url;
      // 在系统浏览器中打开授权页
      if (window.electron?.shell?.openExternal) {
        await window.electron.shell.openExternal(url);
      } else {
        // 浏览器预览环境回退:新开标签页
        window.open(url, '_blank');
      }
      setStatus('请在浏览器中完成 Google 授权,授权后将自动返回桌面应用...');
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取授权 URL 失败');
      setLoading(false);
    }
  }

  return (
    <div style={styles.form}>
      <div style={styles.googleHint}>
        点击下方按钮,将在系统浏览器中打开 Google 授权页。完成授权后,浏览器会自动跳转回桌面应用。
      </div>

      <button
        type="button"
        style={loading ? styles.googleBtnDisabled : styles.googleBtn}
        onClick={handleGoogleLogin}
        disabled={loading}
      >
        <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
          <path
            fill="#FFC107"
            d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z"
          />
          <path
            fill="#FF3D00"
            d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z"
          />
          <path
            fill="#4CAF50"
            d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z"
          />
          <path
            fill="#1976D2"
            d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.225,41.078,44,35.531,44,24C44,22.659,43.862,21.35,43.611,20.083z"
          />
        </svg>
        <span>{loading ? '等待浏览器授权...' : '使用 Google 账号登录'}</span>
      </button>

      {status && <div style={styles.statusBox}>{status}</div>}
      {error && <div style={styles.error}>{error}</div>}
    </div>
  );
}

// ============================================================================
// 样式(内联,无 CSS 框架依赖)
// ============================================================================

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
    color: '#e2e8f0',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
    padding: 16,
  },
  card: {
    width: '100%',
    maxWidth: 400,
    background: 'rgba(30, 41, 59, 0.7)',
    backdropFilter: 'blur(12px)',
    border: '1px solid rgba(148, 163, 184, 0.15)',
    borderRadius: 16,
    padding: 32,
    boxShadow: '0 20px 50px rgba(0, 0, 0, 0.4)',
  },
  header: {
    textAlign: 'center',
    marginBottom: 24,
  },
  logo: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 56,
    height: 56,
    borderRadius: 14,
    background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
    color: '#fff',
    fontWeight: 700,
    fontSize: 22,
    marginBottom: 12,
    letterSpacing: 1,
  },
  title: {
    margin: '0 0 4px',
    fontSize: 22,
    fontWeight: 600,
    color: '#f1f5f9',
  },
  subtitle: {
    margin: 0,
    fontSize: 13,
    color: '#94a3b8',
  },
  tabs: {
    display: 'flex',
    gap: 4,
    background: 'rgba(15, 23, 42, 0.6)',
    padding: 4,
    borderRadius: 10,
    marginBottom: 24,
  },
  tab: {
    flex: 1,
    padding: '10px 0',
    background: 'transparent',
    color: '#94a3b8',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 500,
    transition: 'all 0.2s',
  },
  tabActive: {
    flex: 1,
    padding: '10px 0',
    background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 600,
    boxShadow: '0 2px 8px rgba(59, 130, 246, 0.4)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  label: {
    fontSize: 13,
    color: '#cbd5e1',
    fontWeight: 500,
  },
  input: {
    width: '100%',
    padding: '10px 12px',
    background: 'rgba(15, 23, 42, 0.6)',
    border: '1px solid rgba(148, 163, 184, 0.2)',
    borderRadius: 8,
    color: '#f1f5f9',
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box' as const,
  },
  codeRow: {
    display: 'flex',
    gap: 8,
  },
  codeBtn: {
    padding: '10px 14px',
    background: 'rgba(59, 130, 246, 0.15)',
    color: '#60a5fa',
    border: '1px solid rgba(59, 130, 246, 0.4)',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    whiteSpace: 'nowrap' as const,
  },
  codeBtnDisabled: {
    padding: '10px 14px',
    background: 'rgba(100, 116, 139, 0.15)',
    color: '#64748b',
    border: '1px solid rgba(100, 116, 139, 0.2)',
    borderRadius: 8,
    cursor: 'not-allowed',
    fontSize: 13,
    whiteSpace: 'nowrap' as const,
  },
  submitBtn: {
    width: '100%',
    padding: '12px',
    background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 15,
    fontWeight: 600,
    marginTop: 4,
    boxShadow: '0 4px 12px rgba(59, 130, 246, 0.4)',
  },
  googleBtn: {
    width: '100%',
    padding: '12px',
    background: '#fff',
    color: '#1f2937',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  googleBtnDisabled: {
    width: '100%',
    padding: '12px',
    background: '#f3f4f6',
    color: '#9ca3af',
    border: '1px solid #e5e7eb',
    borderRadius: 8,
    cursor: 'not-allowed',
    fontSize: 14,
    fontWeight: 600,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  googleHint: {
    fontSize: 12,
    color: '#94a3b8',
    lineHeight: 1.6,
    padding: 10,
    background: 'rgba(59, 130, 246, 0.08)',
    border: '1px solid rgba(59, 130, 246, 0.2)',
    borderRadius: 8,
  },
  error: {
    padding: '8px 12px',
    background: 'rgba(239, 68, 68, 0.12)',
    color: '#fca5a5',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    borderRadius: 8,
    fontSize: 13,
  },
  statusBox: {
    padding: '8px 12px',
    background: 'rgba(59, 130, 246, 0.12)',
    color: '#93c5fd',
    border: '1px solid rgba(59, 130, 246, 0.3)',
    borderRadius: 8,
    fontSize: 13,
  },
  footer: {
    marginTop: 20,
    textAlign: 'center',
    fontSize: 12,
    color: '#64748b',
  },
  link: {
    color: '#60a5fa',
    textDecoration: 'none',
  },
};
