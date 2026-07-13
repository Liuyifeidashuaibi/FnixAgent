import { useEffect, useState } from 'react';
import { sdk, type MfaEnforcement, type MfaFactor } from '@fnixagent/sdk';
import { HasPermission } from '../contexts/PermissionContext';

/**
 * MFA 多因素认证管理页(Phase 2.4)
 *
 * 功能:
 *   1. 强制策略管理(按角色):管理员可配置哪些角色必须开 MFA
 *   2. 用户 MFA 因子查询:按用户 ID 查看已绑定的因子,可强制禁用
 */
export function MfaManagement() {
  return (
    <HasPermission code="system:config">
      <div className="space-y-6">
        <EnforcementSection />
        <UserFactorsSection />
      </div>
    </HasPermission>
  );
}

// =========================================================================
// 强制策略管理
// =========================================================================

function EnforcementSection() {
  const [items, setItems] = useState<MfaEnforcement[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    role: '',
    factor_type: 'totp' as 'totp' | 'sms' | 'email' | 'any',
    enabled: true,
  });

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.mfa.listEnforcements();
      setItems(resp.data?.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate() {
    if (!form.role.trim()) {
      setError('角色名不能为空');
      return;
    }
    setError(null);
    try {
      await sdk.mfa.upsertEnforcement({
        role: form.role.trim(),
        factor_type: form.factor_type,
        enabled: form.enabled,
      });
      setShowForm(false);
      setForm({ role: '', factor_type: 'totp', enabled: true });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '创建失败');
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('确认删除此强制策略?')) return;
    try {
      await sdk.mfa.deleteEnforcement(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function handleToggle(item: MfaEnforcement) {
    try {
      await sdk.mfa.upsertEnforcement({
        role: item.role,
        factor_type: item.factor_type,
        enabled: !item.enabled,
      });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : '更新失败');
    }
  }

  return (
    <section className="rounded-lg border border-border bg-background p-4">
      <header className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">MFA 强制策略</h2>
          <p className="text-xs text-muted-foreground">
            配置哪些角色必须开启 MFA(登录时若未开启会被引导设置)
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground hover:opacity-90"
        >
          {showForm ? '取消' : '+ 新增策略'}
        </button>
      </header>

      {error && (
        <div className="mb-3 rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {showForm && (
        <div className="mb-3 rounded border border-border bg-secondary/30 p-3">
          <div className="flex flex-wrap gap-3">
            <label className="flex flex-col text-xs">
              <span className="mb-1 text-muted-foreground">角色名</span>
              <input
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                placeholder="admin / finance / ..."
                className="w-40 rounded border border-border bg-background px-2 py-1 text-sm"
              />
            </label>
            <label className="flex flex-col text-xs">
              <span className="mb-1 text-muted-foreground">要求因子</span>
              <select
                value={form.factor_type}
                onChange={(e) =>
                  setForm({ ...form, factor_type: e.target.value as typeof form.factor_type })
                }
                className="rounded border border-border bg-background px-2 py-1 text-sm"
              >
                <option value="any">任意(any)</option>
                <option value="totp">TOTP</option>
                <option value="sms">短信</option>
                <option value="email">邮箱</option>
              </select>
            </label>
            <label className="flex items-end gap-2 text-xs">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              />
              <span>启用</span>
            </label>
            <button
              onClick={handleCreate}
              className="self-end rounded bg-primary px-3 py-1 text-sm text-primary-foreground hover:opacity-90"
            >
              保存
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="py-8 text-center text-sm text-muted-foreground">加载中...</div>
      ) : items.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          暂无强制策略,点「+ 新增策略」配置
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-2 pr-3">角色</th>
              <th className="py-2 pr-3">要求因子</th>
              <th className="py-2 pr-3">状态</th>
              <th className="py-2 pr-3">更新时间</th>
              <th className="py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b border-border/50">
                <td className="py-2 pr-3 font-medium">{item.role}</td>
                <td className="py-2 pr-3">
                  <code className="rounded bg-secondary px-1.5 py-0.5 text-xs">
                    {item.factor_type}
                  </code>
                </td>
                <td className="py-2 pr-3">
                  <button
                    onClick={() => handleToggle(item)}
                    className={`rounded px-2 py-0.5 text-xs ${
                      item.enabled
                        ? 'bg-green-100 text-green-700'
                        : 'bg-secondary text-muted-foreground'
                    }`}
                  >
                    {item.enabled ? '已启用' : '已禁用'}
                  </button>
                </td>
                <td className="py-2 pr-3 text-xs text-muted-foreground">
                  {item.updated_at ?? '-'}
                </td>
                <td className="py-2">
                  <button
                    onClick={() => handleDelete(item.id)}
                    className="text-xs text-destructive hover:underline"
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

// =========================================================================
// 用户因子查询
// =========================================================================

function UserFactorsSection() {
  const [userId, setUserId] = useState('');
  const [data, setData] = useState<{
    user_id: number;
    username: string;
    factors: MfaFactor[];
    recovery_codes_remaining: number;
    mfa_enabled: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch() {
    const id = parseInt(userId, 10);
    if (!id) {
      setError('请输入有效的用户 ID');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await sdk.mfa.adminListUserFactors(id);
      setData(resp.data ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : '查询失败');
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleDisableFactor(factorId: number) {
    if (!confirm('确认强制禁用此 MFA 因子?(用户登录可能受影响)')) return;
    try {
      await sdk.mfa.adminDisableFactor(factorId);
      if (data) {
        await handleSearch();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '禁用失败');
    }
  }

  return (
    <section className="rounded-lg border border-border bg-background p-4">
      <header className="mb-3">
        <h2 className="text-lg font-semibold">用户 MFA 因子查询</h2>
        <p className="text-xs text-muted-foreground">
          按用户 ID 查看已绑定的 MFA 因子,可强制禁用(应急用,如用户设备丢失)
        </p>
      </header>

      <div className="mb-3 flex gap-2">
        <input
          type="number"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="输入用户 ID"
          className="w-40 rounded border border-border bg-background px-2 py-1 text-sm"
        />
        <button
          onClick={handleSearch}
          disabled={loading}
          className="rounded bg-primary px-3 py-1 text-sm text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {loading ? '查询中...' : '查询'}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {data && (
        <div>
          <div className="mb-3 rounded border border-border bg-secondary/30 p-3 text-sm">
            <div className="flex flex-wrap gap-4">
              <span>
                用户:
                <strong className="ml-1">{data.username}</strong>
                <span className="ml-2 text-xs text-muted-foreground">ID: {data.user_id}</span>
              </span>
              <span>
                MFA 状态:
                {data.mfa_enabled ? (
                  <span className="ml-1 rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
                    已启用
                  </span>
                ) : (
                  <span className="ml-1 rounded bg-secondary px-2 py-0.5 text-xs text-muted-foreground">
                    未启用
                  </span>
                )}
              </span>
              <span>
                剩余恢复码:
                <strong className="ml-1">{data.recovery_codes_remaining}</strong>
              </span>
            </div>
          </div>

          {data.factors.length === 0 ? (
            <div className="py-4 text-center text-sm text-muted-foreground">
              该用户未绑定任何 MFA 因子
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-border text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-2 pr-3">ID</th>
                  <th className="py-2 pr-3">类型</th>
                  <th className="py-2 pr-3">绑定信息</th>
                  <th className="py-2 pr-3">状态</th>
                  <th className="py-2 pr-3">绑定时间</th>
                  <th className="py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {data.factors.map((f) => (
                  <tr key={f.id} className="border-b border-border/50">
                    <td className="py-2 pr-3 text-xs text-muted-foreground">{f.id}</td>
                    <td className="py-2 pr-3">
                      <code className="rounded bg-secondary px-1.5 py-0.5 text-xs uppercase">
                        {f.factor_type}
                      </code>
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      {f.factor_type === 'sms' && f.phone}
                      {f.factor_type === 'email' && f.email}
                      {f.factor_type === 'totp' && <span className="text-muted-foreground">-</span>}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`rounded px-2 py-0.5 text-xs ${
                          f.enabled
                            ? 'bg-green-100 text-green-700'
                            : 'bg-secondary text-muted-foreground'
                        }`}
                      >
                        {f.enabled ? '启用' : '禁用'}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {f.created_at ?? '-'}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => handleDisableFactor(f.id)}
                        className="text-xs text-destructive hover:underline"
                      >
                        强制禁用
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
