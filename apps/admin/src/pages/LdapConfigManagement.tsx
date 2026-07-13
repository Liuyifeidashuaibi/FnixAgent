/**
 * Phase 2.2: LDAP/AD 域集成配置页
 *
 * 功能:
 *   1. LDAP 配置列表(名称/服务器/状态/最后同步时间)
 *   2. 新建/编辑配置(服务地址、Bind DN、搜索基准、属性映射等)
 *   3. 测试连通性(服务账号 bind)
 *   4. 手动触发用户同步
 */
import { useEffect, useState } from 'react';
import { sdk, type LdapConfig } from '@fnixagent/sdk';
import { HasPermission } from '../contexts/PermissionContext';

export function LdapConfigManagement() {
  const [configs, setConfigs] = useState<LdapConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<LdapConfig | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [testing, setTesting] = useState<number | null>(null);

  async function loadData() {
    try {
      setError(null);
      const resp = await sdk.ldap.listConfigs();
      setConfigs(resp.data?.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  async function handleDelete(id: number, name: string) {
    if (!confirm(`确认删除 LDAP 配置「${name}」?`)) return;
    try {
      await sdk.ldap.deleteConfig(id);
      await loadData();
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function handleTest(id: number) {
    setTesting(id);
    try {
      const resp = await sdk.ldap.testConfig(id);
      alert(resp.success ? '✅ 连接成功' : `❌ 连接失败: ${resp.error ?? '未知错误'}`);
    } catch (e) {
      alert(`❌ 测试异常: ${e instanceof Error ? e.message : '未知错误'}`);
    } finally {
      setTesting(null);
    }
  }

  async function handleSync(id: number) {
    setSyncing(id);
    try {
      const resp = await sdk.ldap.syncUsers(id);
      const result = resp.data?.results?.[0];
      if (result?.ok && result.stats) {
        const s = result.stats;
        alert(`✅ 同步完成\n总计: ${s.total_ldap_users}\n新建: ${s.created}\n更新: ${s.updated}\n跳过: ${s.skipped}`);
      } else {
        alert(`❌ 同步失败: ${result?.error ?? '未知错误'}`);
      }
      await loadData(); // 刷新 last_sync_at
    } catch (e) {
      alert(`❌ 同步异常: ${e instanceof Error ? e.message : '未知错误'}`);
    } finally {
      setSyncing(null);
    }
  }

  if (loading) return <div className="p-4 text-muted-foreground">加载中...</div>;
  if (error) return <div className="p-4 text-red-500">错误:{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">LDAP / AD 域集成</h2>
          <p className="text-xs text-muted-foreground">
            配置企业 LDAP 服务器后,域账号可直接登录,用户信息按 24h 间隔自动同步
          </p>
        </div>
        <HasPermission code="system:config">
          <button
            onClick={() => setShowCreate(true)}
            className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
          >
            + 新建配置
          </button>
        </HasPermission>
      </div>

      {configs.length === 0 ? (
        <div className="rounded border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          暂无 LDAP 配置。点击「新建配置」开始集成企业域账号。
        </div>
      ) : (
        <div className="overflow-x-auto rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50">
              <tr>
                <th className="px-3 py-2 text-left">名称</th>
                <th className="px-3 py-2 text-left">服务器</th>
                <th className="px-3 py-2 text-left">Bind DN</th>
                <th className="px-3 py-2 text-left">状态</th>
                <th className="px-3 py-2 text-left">最后同步</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {configs.map((c) => (
                <tr key={c.id} className="border-t border-border hover:bg-secondary/30">
                  <td className="px-3 py-2 font-medium">{c.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{c.server_url}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{c.bind_dn}</td>
                  <td className="px-3 py-2">
                    {c.is_active ? (
                      <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">启用</span>
                    ) : (
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">禁用</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {c.last_sync_at ? new Date(c.last_sync_at).toLocaleString('zh-CN') : '从未同步'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => handleTest(c.id)}
                      disabled={testing === c.id}
                      className="mr-2 text-xs text-primary hover:underline disabled:opacity-50"
                    >
                      {testing === c.id ? '测试中...' : '测试'}
                    </button>
                    <button
                      onClick={() => handleSync(c.id)}
                      disabled={syncing === c.id}
                      className="mr-2 text-xs text-primary hover:underline disabled:opacity-50"
                    >
                      {syncing === c.id ? '同步中...' : '同步'}
                    </button>
                    <HasPermission code="system:config">
                      <button
                        onClick={() => setEditing(c)}
                        className="mr-2 text-xs text-primary hover:underline"
                      >
                        编辑
                      </button>
                    </HasPermission>
                    <HasPermission code="system:config">
                      <button
                        onClick={() => handleDelete(c.id, c.name)}
                        className="text-xs text-red-500 hover:underline"
                      >
                        删除
                      </button>
                    </HasPermission>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <LdapConfigModal
          onClose={() => setShowCreate(false)}
          onSaved={async () => {
            setShowCreate(false);
            await loadData();
          }}
        />
      )}

      {editing && (
        <LdapConfigModal
          config={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await loadData();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 配置编辑弹窗
// ---------------------------------------------------------------------------

interface LdapConfigModalProps {
  config?: LdapConfig;
  onClose: () => void;
  onSaved: () => void;
}

function LdapConfigModal({ config, onClose, onSaved }: LdapConfigModalProps) {
  const isEdit = !!config;
  const [form, setForm] = useState({
    name: config?.name ?? '',
    server_url: config?.server_url ?? 'ldap://',
    bind_dn: config?.bind_dn ?? '',
    bind_password: '', // 编辑时不回显密码
    user_search_base: config?.user_search_base ?? '',
    user_filter: config?.user_filter ?? '(objectClass=person)',
    group_search_base: config?.group_search_base ?? '',
    username_attribute: config?.username_attribute ?? 'sAMAccountName',
    email_attribute: config?.email_attribute ?? 'mail',
    display_name_attribute: config?.display_name_attribute ?? 'displayName',
    use_ssl: config?.use_ssl ?? false,
    use_tls: config?.use_tls ?? true,
    is_active: config?.is_active ?? true,
    sync_interval_hours: config?.sync_interval_hours ?? 24,
  });
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm({ ...form, [key]: value });
  }

  async function handleSubmit() {
    if (!form.name || !form.server_url || !form.bind_dn || !form.user_search_base) {
      alert('名称、服务器地址、Bind DN、用户搜索基准为必填');
      return;
    }
    if (!isEdit && !form.bind_password) {
      alert('新建配置时 Bind 密码必填');
      return;
    }
    setSubmitting(true);
    try {
      // 仅在填了密码时才传 bind_password
      const body: Record<string, unknown> = { ...form };
      if (!form.bind_password) delete body.bind_password;

      if (isEdit && config) {
        await sdk.ldap.updateConfig(config.id, body);
      } else {
        await sdk.ldap.createConfig(body as any);
      }
      onSaved();
    } catch (e) {
      alert(e instanceof Error ? e.message : '保存失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-[640px] overflow-y-auto rounded bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold">
          {isEdit ? `编辑配置:${config!.name}` : '新建 LDAP 配置'}
        </h3>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label="配置名称" required>
              <input
                value={form.name}
                onChange={(e) => update('name', e.target.value)}
                placeholder="企业 AD"
                className="input"
              />
            </Field>
            <Field label="同步间隔(小时)">
              <input
                type="number"
                value={form.sync_interval_hours}
                onChange={(e) => update('sync_interval_hours', Number(e.target.value))}
                min={1}
                max={168}
                className="input"
              />
            </Field>
          </div>

          <Field label="服务器地址" required>
            <input
              value={form.server_url}
              onChange={(e) => update('server_url', e.target.value)}
              placeholder="ldap://dc.company.com:389 或 ldaps://dc.company.com:636"
              className="input"
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Bind DN(服务账号)" required>
              <input
                value={form.bind_dn}
                onChange={(e) => update('bind_dn', e.target.value)}
                placeholder="CN=svc_ldap,OU=Service,DC=company,DC=com"
                className="input"
              />
            </Field>
            <Field label="Bind 密码" required={!isEdit}>
              <input
                type="password"
                value={form.bind_password}
                onChange={(e) => update('bind_password', e.target.value)}
                placeholder={isEdit ? '留空则不修改' : ''}
                className="input"
              />
            </Field>
          </div>

          <Field label="用户搜索基准 DN" required>
            <input
              value={form.user_search_base}
              onChange={(e) => update('user_search_base', e.target.value)}
              placeholder="OU=Users,DC=company,DC=com"
              className="input"
            />
          </Field>

          <Field label="用户过滤器">
            <input
              value={form.user_filter}
              onChange={(e) => update('user_filter', e.target.value)}
              placeholder="(objectClass=person)"
              className="input"
            />
          </Field>

          <Field label="组搜索基准 DN(可选)">
            <input
              value={form.group_search_base}
              onChange={(e) => update('group_search_base', e.target.value)}
              placeholder="OU=Groups,DC=company,DC=com"
              className="input"
            />
          </Field>

          <div className="grid grid-cols-3 gap-3">
            <Field label="用户名属性">
              <input
                value={form.username_attribute}
                onChange={(e) => update('username_attribute', e.target.value)}
                placeholder="sAMAccountName"
                className="input"
              />
            </Field>
            <Field label="邮箱属性">
              <input
                value={form.email_attribute}
                onChange={(e) => update('email_attribute', e.target.value)}
                placeholder="mail"
                className="input"
              />
            </Field>
            <Field label="显示名属性">
              <input
                value={form.display_name_attribute}
                onChange={(e) => update('display_name_attribute', e.target.value)}
                placeholder="displayName"
                className="input"
              />
            </Field>
          </div>

          <div className="flex items-center gap-6 pt-2">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.use_ssl}
                onChange={(e) => update('use_ssl', e.target.checked)}
              />
              使用 SSL (ldaps://)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.use_tls}
                onChange={(e) => update('use_tls', e.target.checked)}
              />
              使用 STARTTLS
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => update('is_active', e.target.checked)}
              />
              启用
            </label>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary">
            取消
          </button>
          <button onClick={handleSubmit} disabled={submitting} className="btn-primary">
            {submitting ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium text-muted-foreground">
        {label} {required && <span className="text-red-500">*</span>}
      </label>
      {children}
    </div>
  );
}
