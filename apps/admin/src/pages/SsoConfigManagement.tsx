/**
 * Phase 2.3: SSO 单点登录配置管理页
 *
 * 功能:
 *   1. SSO provider 列表(OAuth + SAML)
 *   2. 新建/编辑配置(OAuth: client_id/secret/scopes/redirect_uri;SAML: SP/IdP 元数据)
 *   3. 测试配置(校验完整性 + 库是否安装)
 *   4. 删除配置
 */
import { useEffect, useState } from 'react';
import { sdk, type SsoConfig, type SsoConfigCreateBody } from '@officeagent/sdk';
import { HasPermission } from '../contexts/PermissionContext';

type ProviderType = 'oauth' | 'saml';

export function SsoConfigManagement() {
  const [configs, setConfigs] = useState<SsoConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<SsoConfig | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [filterType, setFilterType] = useState<ProviderType | ''>('');
  const [testing, setTesting] = useState<number | null>(null);

  async function loadData() {
    try {
      setError(null);
      const resp = await sdk.sso.listConfigs(filterType || undefined);
      setConfigs(resp.data?.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, [filterType]);

  async function handleDelete(id: number, name: string) {
    if (!confirm(`确认删除 SSO 配置「${name}」?`)) return;
    try {
      await sdk.sso.deleteConfig(id);
      await loadData();
    } catch (e) {
      alert(e instanceof Error ? e.message : '删除失败');
    }
  }

  async function handleTest(id: number) {
    setTesting(id);
    try {
      const resp = await sdk.sso.testConfig(id);
      alert(resp.success ? `✅ ${resp.message ?? '配置有效'}` : `❌ ${resp.error ?? '配置无效'}`);
    } catch (e) {
      alert(`❌ 测试异常: ${e instanceof Error ? e.message : '未知错误'}`);
    } finally {
      setTesting(null);
    }
  }

  if (loading) return <div className="p-4 text-muted-foreground">加载中...</div>;
  if (error) return <div className="p-4 text-red-500">错误:{error}</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">SSO 单点登录</h2>
          <p className="text-xs text-muted-foreground">
            配置 OAuth2.0(GitHub/Google)或 SAML 2.0(Azure AD/Okta)后,用户可通过企业 IdP 直接登录
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as ProviderType | '')}
            className="rounded border border-border bg-background px-2 py-1.5 text-sm"
          >
            <option value="">全部类型</option>
            <option value="oauth">OAuth2.0</option>
            <option value="saml">SAML 2.0</option>
          </select>
          <HasPermission code="system:config">
            <button
              onClick={() => setShowCreate(true)}
              className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
            >
              + 新建配置
            </button>
          </HasPermission>
        </div>
      </div>

      {configs.length === 0 ? (
        <div className="rounded border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          暂无 SSO 配置。点击「新建配置」开始集成企业 IdP。
        </div>
      ) : (
        <div className="overflow-x-auto rounded border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary/50">
              <tr>
                <th className="px-3 py-2 text-left">名称</th>
                <th className="px-3 py-2 text-left">类型</th>
                <th className="px-3 py-2 text-left">Provider Code</th>
                <th className="px-3 py-2 text-left">关键参数</th>
                <th className="px-3 py-2 text-left">状态</th>
                <th className="px-3 py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {configs.map((c) => (
                <tr key={c.id} className="border-t border-border hover:bg-secondary/30">
                  <td className="px-3 py-2 font-medium">{c.name}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded px-1.5 py-0.5 text-xs ${
                      c.provider_type === 'oauth'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-purple-100 text-purple-700'
                    }`}>
                      {c.provider_type === 'oauth' ? 'OAuth2.0' : 'SAML 2.0'}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{c.provider_code}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {c.provider_type === 'oauth'
                      ? `client_id: ${c.client_id?.slice(0, 12) ?? '-'}...`
                      : `IdP: ${c.idp_entity_id?.slice(0, 30) ?? '-'}...`}
                  </td>
                  <td className="px-3 py-2">
                    {c.is_active ? (
                      <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs text-green-700">启用</span>
                    ) : (
                      <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">禁用</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => handleTest(c.id)}
                      disabled={testing === c.id}
                      className="mr-2 text-xs text-primary hover:underline disabled:opacity-50"
                    >
                      {testing === c.id ? '测试中...' : '测试'}
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
        <SsoConfigModal
          onClose={() => setShowCreate(false)}
          onSaved={async () => {
            setShowCreate(false);
            await loadData();
          }}
        />
      )}

      {editing && (
        <SsoConfigModal
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

interface SsoConfigModalProps {
  config?: SsoConfig;
  onClose: () => void;
  onSaved: () => void;
}

function SsoConfigModal({ config, onClose, onSaved }: SsoConfigModalProps) {
  const isEdit = !!config;
  const [providerType, setProviderType] = useState<ProviderType>(
    config?.provider_type ?? 'oauth',
  );
  const [form, setForm] = useState<Record<string, string>>({
    provider_code: config?.provider_code ?? '',
    name: config?.name ?? '',
    is_active: config?.is_active === false ? 'false' : 'true',
    // OAuth
    client_id: config?.client_id ?? '',
    client_secret: '',
    redirect_uri: config?.redirect_uri ?? '',
    scopes: (config?.scopes ?? []).join(' '),
    authorize_url: config?.authorize_url ?? '',
    token_url: config?.token_url ?? '',
    userinfo_url: config?.userinfo_url ?? '',
    field_mapping_json: JSON.stringify(config?.field_mapping ?? {}, null, 2),
    // SAML
    sp_entity_id: config?.sp_entity_id ?? '',
    acs_url: config?.acs_url ?? '',
    idp_entity_id: config?.idp_entity_id ?? '',
    idp_sso_url: config?.idp_sso_url ?? '',
    idp_x509_cert: '',
    name_id_format: config?.name_id_format ?? 'urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress',
  });
  const [submitting, setSubmitting] = useState(false);

  function update(key: string, value: string) {
    setForm({ ...form, [key]: value });
  }

  async function handleSubmit() {
    if (!form.provider_code || !form.name) {
      alert('Provider Code 与名称必填');
      return;
    }

    const body: SsoConfigCreateBody = {
      provider_type: providerType,
      provider_code: form.provider_code,
      name: form.name,
      is_active: form.is_active !== 'false',
    };

    if (providerType === 'oauth') {
      if (!isEdit && !form.client_id) { alert('client_id 必填'); return; }
      if (!isEdit && !form.client_secret) { alert('client_secret 必填'); return; }
      if (!form.redirect_uri) { alert('redirect_uri 必填'); return; }
      body.client_id = form.client_id;
      if (form.client_secret) body.client_secret = form.client_secret;
      body.redirect_uri = form.redirect_uri;
      if (form.scopes.trim()) {
        body.scopes = form.scopes.trim().split(/\s+/);
      }
      if (form.authorize_url) body.authorize_url = form.authorize_url;
      if (form.token_url) body.token_url = form.token_url;
      if (form.userinfo_url) body.userinfo_url = form.userinfo_url;
      try {
        const mapping = JSON.parse(form.field_mapping_json);
        if (typeof mapping === 'object' && mapping !== null) {
          body.field_mapping = mapping;
        }
      } catch {
        alert('field_mapping 必须为合法 JSON');
        return;
      }
    } else {
      if (!form.sp_entity_id) { alert('sp_entity_id 必填'); return; }
      if (!form.acs_url) { alert('acs_url 必填'); return; }
      if (!form.idp_entity_id) { alert('idp_entity_id 必填'); return; }
      if (!form.idp_sso_url) { alert('idp_sso_url 必填'); return; }
      if (!isEdit && !form.idp_x509_cert) { alert('idp_x509_cert 必填'); return; }
      body.sp_entity_id = form.sp_entity_id;
      body.acs_url = form.acs_url;
      body.idp_entity_id = form.idp_entity_id;
      body.idp_sso_url = form.idp_sso_url;
      if (form.idp_x509_cert) body.idp_x509_cert = form.idp_x509_cert;
      body.name_id_format = form.name_id_format;
      try {
        const mapping = JSON.parse(form.field_mapping_json);
        if (typeof mapping === 'object' && mapping !== null) {
          body.field_mapping = mapping;
        }
      } catch {
        alert('field_mapping 必须为合法 JSON');
        return;
      }
    }

    setSubmitting(true);
    try {
      if (isEdit && config) {
        await sdk.sso.updateConfig(config.id, body);
      } else {
        await sdk.sso.createConfig(body);
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
        className="max-h-[90vh] w-[680px] overflow-y-auto rounded bg-background p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-4 text-lg font-semibold">
          {isEdit ? `编辑配置:${config!.name}` : '新建 SSO 配置'}
        </h3>

        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <Field label="Provider 类型" required>
              <select
                value={providerType}
                onChange={(e) => setProviderType(e.target.value as ProviderType)}
                disabled={isEdit}
                className="input"
              >
                <option value="oauth">OAuth2.0</option>
                <option value="saml">SAML 2.0</option>
              </select>
            </Field>
            <Field label="Provider Code" required>
              <input
                value={form.provider_code}
                onChange={(e) => update('provider_code', e.target.value)}
                placeholder="github / google / azure_ad / 自定义"
                disabled={isEdit}
                className="input"
              />
            </Field>
            <Field label="显示名" required>
              <input
                value={form.name}
                onChange={(e) => update('name', e.target.value)}
                placeholder="GitHub OAuth"
                className="input"
              />
            </Field>
          </div>

          {providerType === 'oauth' ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Client ID" required={!isEdit}>
                  <input
                    value={form.client_id}
                    onChange={(e) => update('client_id', e.target.value)}
                    placeholder="OAuth App Client ID"
                    className="input"
                  />
                </Field>
                <Field label="Client Secret" required={!isEdit}>
                  <input
                    type="password"
                    value={form.client_secret}
                    onChange={(e) => update('client_secret', e.target.value)}
                    placeholder={isEdit ? '留空则不修改' : 'OAuth App Client Secret'}
                    className="input"
                  />
                </Field>
              </div>

              <Field label="Redirect URI(回调地址)" required>
                <input
                  value={form.redirect_uri}
                  onChange={(e) => update('redirect_uri', e.target.value)}
                  placeholder="https://admin.company.com/sso/oauth/callback"
                  className="input"
                />
              </Field>

              <Field label="Scopes(空格分隔,留空使用 provider 默认)">
                <input
                  value={form.scopes}
                  onChange={(e) => update('scopes', e.target.value)}
                  placeholder="read:user user:email"
                  className="input"
                />
              </Field>

              <div className="grid grid-cols-3 gap-3">
                <Field label="Authorize URL(可选)">
                  <input
                    value={form.authorize_url}
                    onChange={(e) => update('authorize_url', e.target.value)}
                    placeholder="留空使用内置预设"
                    className="input"
                  />
                </Field>
                <Field label="Token URL(可选)">
                  <input
                    value={form.token_url}
                    onChange={(e) => update('token_url', e.target.value)}
                    placeholder="留空使用内置预设"
                    className="input"
                  />
                </Field>
                <Field label="UserInfo URL(可选)">
                  <input
                    value={form.userinfo_url}
                    onChange={(e) => update('userinfo_url', e.target.value)}
                    placeholder="留空使用内置预设"
                    className="input"
                  />
                </Field>
              </div>
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Field label="SP Entity ID" required>
                  <input
                    value={form.sp_entity_id}
                    onChange={(e) => update('sp_entity_id', e.target.value)}
                    placeholder="https://admin.company.com/saml/metadata"
                    className="input"
                  />
                </Field>
                <Field label="ACS URL" required>
                  <input
                    value={form.acs_url}
                    onChange={(e) => update('acs_url', e.target.value)}
                    placeholder="https://admin.company.com/sso/saml/acs"
                    className="input"
                  />
                </Field>
              </div>

              <Field label="IdP Entity ID" required>
                <input
                  value={form.idp_entity_id}
                  onChange={(e) => update('idp_entity_id', e.target.value)}
                  placeholder="https://sts.windows.net/{tenant-id}/"
                  className="input"
                />
              </Field>

              <Field label="IdP SSO URL(单点登录服务地址)" required>
                <input
                  value={form.idp_sso_url}
                  onChange={(e) => update('idp_sso_url', e.target.value)}
                  placeholder="https://login.microsoftonline.com/.../saml2"
                  className="input"
                />
              </Field>

              <Field label="IdP X.509 证书(PEM 内容,含 BEGIN/END 行)" required={!isEdit}>
                <textarea
                  value={form.idp_x509_cert}
                  onChange={(e) => update('idp_x509_cert', e.target.value)}
                  placeholder={isEdit ? '留空则不修改' : '-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'}
                  rows={5}
                  className="input font-mono text-xs"
                />
              </Field>

              <Field label="NameID Format">
                <select
                  value={form.name_id_format}
                  onChange={(e) => update('name_id_format', e.target.value)}
                  className="input"
                >
                  <option value="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">emailAddress</option>
                  <option value="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">persistent</option>
                  <option value="urn:oasis:names:tc:SAML:2.0:nameid-format:transient">transient</option>
                  <option value="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified">unspecified</option>
                </select>
              </Field>
            </>
          )}

          <Field label="字段映射 JSON(provider 原始字段 → 标准字段)">
            <textarea
              value={form.field_mapping_json}
              onChange={(e) => update('field_mapping_json', e.target.value)}
              rows={4}
              className="input font-mono text-xs"
            />
          </Field>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active !== 'false'}
              onChange={(e) => update('is_active', e.target.checked ? 'true' : 'false')}
            />
            启用此 SSO provider
          </label>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary">取消</button>
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
