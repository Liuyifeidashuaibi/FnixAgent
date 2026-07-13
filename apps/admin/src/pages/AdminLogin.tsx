import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  auth,
  sdk,
  MfaRequiredError,
  type AuthUser,
  type SsoProvider,
} from '@officeagent/sdk';

interface AdminLoginProps {
  onLogin: (user: AuthUser) => void;
}

type LoginTab = 'password' | 'phone';

const PHONE_PATTERN = /^1[3-9]\d{9}$/;

/**
 * 管理员登录页 — 复用 SDK 的 AuthManager(RSA 加密 + 双 Token)+ SSO 单点登录入口
 *
 * Phase 2.4:支持 MFA Challenge(用户启用 MFA 时,密码校验后需输入 TOTP/恢复码)
 * Phase 3.0:新增「手机号登录」Tab(国内场景),密码登录与 SSO 保留在「账号密码」Tab
 */
export function AdminLogin({ onLogin }: AdminLoginProps) {
  const [tab, setTab] = useState<LoginTab>('password');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [providers, setProviders] = useState<SsoProvider[]>([]);
  const [ssoLoading, setSsoLoading] = useState<string | null>(null);

  // 手机号登录相关状态
  const [phone, setPhone] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [sending, setSending] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // MFA Challenge 状态
  const [mfaChallenge, setMfaChallenge] = useState<{
    mfaToken: string;
    factors: string[];
    remember: boolean;
    username: string;
  } | null>(null);
  const [mfaFactorType, setMfaFactorType] = useState<'totp' | 'recovery'>('totp');
  const [mfaCode, setMfaCode] = useState('');

  // 加载 SSO providers(若已配置则显示按钮)
  useEffect(() => {
    void (async () => {
      try {
        const resp = await sdk.sso.listProviders();
        setProviders(resp.data?.items ?? []);
      } catch {
        // 忽略(后端可能未启用 SSO)
      }
    })();
  }, []);

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

  // 管理员身份校验(登录后统一调用)
  async function ensureAdminAndProceed(): Promise<void> {
    const user = await auth.getCurrentUser();
    if (!user) throw new Error('获取用户信息失败');
    if (user.role !== 'admin') {
      await auth.logout();
      throw new Error('非管理员账号,无权访问管理后台');
    }
    onLogin(user);
  }

  // ----- 账号密码登录 -----
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await auth.login(username.trim(), password, true);
      await ensureAdminAndProceed();
    } catch (err) {
      if (err instanceof MfaRequiredError) {
        setMfaChallenge({
          mfaToken: err.mfaToken,
          factors: err.factors,
          remember: err.remember,
          username: err.username,
        });
        setMfaFactorType(err.factors.includes('totp') ? 'totp' : 'recovery');
        setMfaCode('');
        setError(null);
      } else {
        setError(err instanceof Error ? err.message : '登录失败');
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleMfaVerify(e: FormEvent) {
    e.preventDefault();
    if (!mfaChallenge) return;
    if (!mfaCode.trim()) {
      setError('请输入验证码');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await auth.completeMfa(
        mfaChallenge.mfaToken,
        mfaFactorType,
        mfaCode.trim(),
        { remember: mfaChallenge.remember },
      );
      await ensureAdminAndProceed();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'MFA 验证失败');
    } finally {
      setLoading(false);
    }
  }

  function handleMfaCancel() {
    setMfaChallenge(null);
    setMfaCode('');
    setError(null);
  }

  // ----- 手机号验证码登录 -----
  async function handleSendSmsCode() {
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

  async function handleSmsLogin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!PHONE_PATTERN.test(phone)) {
      setError('请输入正确的 11 位手机号');
      return;
    }
    if (!/^\d{6}$/.test(smsCode)) {
      setError('请输入 6 位验证码');
      return;
    }
    setLoading(true);
    try {
      await auth.loginWithSms(phone, smsCode, true);
      await ensureAdminAndProceed();
    } catch (err) {
      setError(err instanceof Error ? err.message : '手机号登录失败');
    } finally {
      setLoading(false);
    }
  }

  // ----- SSO 登录 -----
  async function handleOAuthLogin(providerCode: string) {
    setSsoLoading(providerCode);
    setError(null);
    try {
      const redirectUri = `${window.location.origin}/sso/oauth/callback`;
      const resp = await sdk.sso.getOAuthAuthorizeUrl({
        provider_code: providerCode,
        redirect_uri: redirectUri,
      });
      window.location.href = resp.data.authorization_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'SSO 登录失败');
      setSsoLoading(null);
    }
  }

  async function handleSAMLLogin(providerCode: string) {
    setSsoLoading(providerCode);
    setError(null);
    try {
      const resp = await sdk.sso.samlLogin(providerCode);
      window.location.href = resp.data.redirect_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'SAML 登录失败');
      setSsoLoading(null);
    }
  }

  const oauthProviders = providers.filter((p) => p.provider_type === 'oauth');
  const samlProviders = providers.filter((p) => p.provider_type === 'saml');

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-sm">
        <h1 className="mb-1 text-xl font-semibold">OfficeAgent 管理后台</h1>
        <p className="mb-6 text-sm text-muted-foreground">仅管理员可登录</p>

        {mfaChallenge ? (
          // ============= MFA 验证表单 =============
          <form onSubmit={handleMfaVerify} className="space-y-4">
            <div className="rounded-md bg-blue-500/10 px-3 py-2 text-sm text-blue-700">
              🔐 已启用 MFA,请输入验证码完成登录
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">验证方式</label>
              <select
                value={mfaFactorType}
                onChange={(e) => setMfaFactorType(e.target.value as 'totp' | 'recovery')}
                disabled={loading}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                {mfaChallenge.factors.includes('totp') && (
                  <option value="totp">TOTP 验证器(Google Authenticator)</option>
                )}
                {mfaChallenge.factors.includes('recovery') && (
                  <option value="recovery">备用恢复码</option>
                )}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium" htmlFor="mfa-code">
                {mfaFactorType === 'totp' ? '6 位验证码' : '恢复码(XXXX-XXXX-XXXX-XXXX)'}
              </label>
              <input
                id="mfa-code"
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                placeholder={mfaFactorType === 'totp' ? '123456' : 'ABCD-EFGH-IJKL-MNOP'}
                autoFocus
                disabled={loading}
              />
            </div>
            {error && (
              <p className="rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-500">
                ⚠️ {error}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleMfaCancel}
                disabled={loading}
                className="flex-1 rounded-md border border-border px-4 py-2 text-sm hover:bg-secondary/50 disabled:opacity-50"
              >
                返回
              </button>
              <button
                type="submit"
                disabled={loading}
                className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? '验证中...' : '验证'}
              </button>
            </div>
          </form>
        ) : (
          <>
            {/* ============= Tab 切换 ============= */}
            <div className="mb-4 flex gap-1 rounded-md bg-secondary/40 p-1">
              <button
                type="button"
                onClick={() => { setTab('password'); setError(null); }}
                className={
                  tab === 'password'
                    ? 'flex-1 rounded-md bg-background px-3 py-1.5 text-sm font-medium shadow-sm'
                    : 'flex-1 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground'
                }
              >
                账号密码
              </button>
              <button
                type="button"
                onClick={() => { setTab('phone'); setError(null); }}
                className={
                  tab === 'phone'
                    ? 'flex-1 rounded-md bg-background px-3 py-1.5 text-sm font-medium shadow-sm'
                    : 'flex-1 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground'
                }
              >
                手机号
              </button>
            </div>

            {tab === 'password' ? (
              <>
                {/* ============= 账号密码登录表单 ============= */}
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium" htmlFor="admin-username">
                      用户名
                    </label>
                    <input
                      id="admin-username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      placeholder="管理员用户名"
                      disabled={loading}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium" htmlFor="admin-password">
                      密码
                    </label>
                    <input
                      id="admin-password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      placeholder="密码"
                      disabled={loading}
                    />
                  </div>
                  {error && (
                    <p className="rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-500">
                      ⚠️ {error}
                    </p>
                  )}
                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  >
                    {loading ? '登录中...' : '登录'}
                  </button>
                </form>

                {(oauthProviders.length > 0 || samlProviders.length > 0) && (
                  <>
                    <div className="my-4 flex items-center gap-3">
                      <div className="h-px flex-1 bg-border" />
                      <span className="text-xs text-muted-foreground">或使用 SSO 登录</span>
                      <div className="h-px flex-1 bg-border" />
                    </div>

                    <div className="space-y-2">
                      {oauthProviders.map((p) => (
                        <button
                          key={`${p.provider_type}-${p.provider_code}`}
                          onClick={() => handleOAuthLogin(p.provider_code)}
                          disabled={ssoLoading !== null}
                          className="w-full rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-secondary/50 disabled:opacity-50"
                        >
                          {ssoLoading === p.provider_code ? '跳转中...' : `使用 ${p.name} 登录`}
                        </button>
                      ))}
                      {samlProviders.map((p) => (
                        <button
                          key={`${p.provider_type}-${p.provider_code}`}
                          onClick={() => handleSAMLLogin(p.provider_code)}
                          disabled={ssoLoading !== null}
                          className="w-full rounded-md border border-border bg-background px-4 py-2 text-sm hover:bg-secondary/50 disabled:opacity-50"
                        >
                          {ssoLoading === p.provider_code
                            ? '跳转中...'
                            : `使用 ${p.name} (SAML) 登录`}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </>
            ) : (
              /* ============= 手机号验证码登录表单 ============= */
              <form onSubmit={handleSmsLogin} className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="admin-phone">
                    手机号
                  </label>
                  <input
                    id="admin-phone"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value.replace(/\D/g, '').slice(0, 11))}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    placeholder="11 位手机号"
                    maxLength={11}
                    autoFocus
                    disabled={loading}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-sm font-medium" htmlFor="admin-sms-code">
                    验证码
                  </label>
                  <div className="flex gap-2">
                    <input
                      id="admin-sms-code"
                      value={smsCode}
                      onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                      placeholder="6 位验证码"
                      maxLength={6}
                      disabled={loading}
                    />
                    <button
                      type="button"
                      onClick={handleSendSmsCode}
                      disabled={
                        countdown > 0 || sending || loading || !PHONE_PATTERN.test(phone)
                      }
                      className="shrink-0 rounded-md border border-border px-3 py-2 text-sm hover:bg-secondary/50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {sending
                        ? '发送中...'
                        : countdown > 0
                          ? `${countdown}s 后重试`
                          : '发送验证码'}
                    </button>
                  </div>
                </div>
                {error && (
                  <p className="rounded-md bg-red-500/10 px-3 py-2 text-sm text-red-500">
                    ⚠️ {error}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {loading ? '登录中...' : '登录'}
                </button>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  );
}
