/**
 * fnixagent API Client — 轻量 HTTP 客户端
 * Phase 1.2 将替换为 openapi-fetch 生成的类型安全 client
 */
import type {
  HealthResponse,
  LoginRequest,
  TokenPair,
  User,
  Document,
  Task,
  // AgentOS 类型
  AgentOSResponse,
  AgentOSSpawnInput,
  AgentOSKillInput,
  AgentOSExecInput,
  AgentOSLLMInput,
  AgentOSFsWriteInput,
  AgentOSMemRecallInput,
  AgentOSMemStoreInput,
  AgentOSMemSearchInput,
  AgentOSToolInvokeInput,
  AgentOSA2ASendInput,
  AgentOSSkillRunInput,
  AgentOSPolicyAddInput,
  AgentOSAuditInput,
  // Coding 类型
  CodingResponse,
  CodingIndexInput,
  CodingSearchInput,
  CodingReadInput,
  CodingWriteInput,
  CodingEditInput,
  CodingTaskInput,
  CodingMcpCallInput,
} from './types';

const DEFAULT_BASE_URL = 'http://localhost:8000';

export class ApiClient {
  private baseUrl: string;
  private accessToken: string | null = null;

  constructor(baseUrl: string = DEFAULT_BASE_URL) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /** 设置 Access Token(axios 拦截器等效) */
  setAccessToken(token: string | null) {
    this.accessToken = token;
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers = new Headers(options.headers);
    if (this.accessToken) {
      headers.set('Authorization', `Bearer ${this.accessToken}`);
    }
    if (options.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const resp = await fetch(`${this.baseUrl}${path}`, { ...options, headers });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`API ${resp.status}: ${text || resp.statusText}`);
    }
    return resp.json() as Promise<T>;
  }

  /**
   * 发起返回纯文本的请求(用于 JSON/CSV 导出等非 JSON 端点)。
   * 仍然附带 Authorization 头,但不解析 JSON。
   */
  private async requestText(
    path: string,
    options: RequestInit = {},
  ): Promise<string> {
    const headers = new Headers(options.headers);
    if (this.accessToken) {
      headers.set('Authorization', `Bearer ${this.accessToken}`);
    }
    const resp = await fetch(`${this.baseUrl}${path}`, { ...options, headers });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`API ${resp.status}: ${text || resp.statusText}`);
    }
    return resp.text();
  }

  // 健康检查
  health = {
    check: () => this.request<HealthResponse>('/health'),
  };

  // 鉴权
  auth = {
    login: (body: LoginRequest) =>
      this.request<TokenPair>('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    register: (body: { username: string; email: string; password_cipher: string }) =>
      this.request<TokenPair>('/api/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    me: () => this.request<User>('/api/v1/auth/me'),
  };

  // Phase 3.0: 手机号验证码登录(国内)
  sms = {
    /** 发送短信验证码 */
    sendCode: (phone: string) =>
      this.request<{ challenge_id: string; expires_in: number; message: string }>(
        '/api/v1/auth/sms/send-code',
        { method: 'POST', body: JSON.stringify({ phone }) },
      ),
    /** 手机号验证码登录 */
    login: (phone: string, code: string, clientUuid?: string) =>
      this.request<TokenPair>('/api/v1/auth/sms/login', {
        method: 'POST',
        body: JSON.stringify({ phone, code, client_uuid: clientUuid }),
      }),
  };

  // 文档
  documents = {
    list: (params?: { user_id?: number; doc_type?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.user_id) qs.set('user_id', String(params.user_id));
      if (params?.doc_type) qs.set('doc_type', params.doc_type);
      if (params?.limit) qs.set('limit', String(params.limit));
      const q = qs.toString();
      return this.request<Document[]>(`/api/v1/documents/list${q ? '?' + q : ''}`);
    },
    get: (id: number) => this.request<Document>(`/api/v1/documents/${id}`),
    delete: (id: number) =>
      this.request<{ deleted: boolean }>(`/api/v1/documents/${id}`, { method: 'DELETE' }),
  };

  // 任务
  tasks = {
    list: (params?: { user_id?: number; status?: string; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.user_id) qs.set('user_id', String(params.user_id));
      if (params?.status) qs.set('status', params.status);
      if (params?.limit) qs.set('limit', String(params.limit));
      const q = qs.toString();
      return this.request<Task[]>(`/api/v1/tasks/list${q ? '?' + q : ''}`);
    },
    get: (id: number) => this.request<Task>(`/api/v1/tasks/${id}`),
    cancel: (id: number) =>
      this.request<Task>(`/api/v1/tasks/${id}/cancel`, { method: 'POST' }),
  };

  // 对话(含流式/自进化/拓扑)
  chat = {
    /** 创建会话 */
    createSession: () =>
      this.request<{ session_id: number; created_at: string }>(
        '/api/v1/chat/session',
        { method: 'POST' },
      ),

    /** 非流式发送消息 */
    send: (body: {
      session_id?: number;
      user_input: string;
      context?: Record<string, unknown>;
    }) =>
      this.request<{
        session_id: number;
        message_id: number;
        response: string;
        trace_id: string;
      }>('/api/v1/chat/message', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    /**
     * 流式发送消息(SSE / NDJSON)
     * 后端返回 application/x-ndjson,每行一个 JSON:
     *   { chunk_type: "thought"|"action"|"text"|"error", content: string, done: boolean }
     *
     * 用法:
     *   for await (const chunk of client.chat.stream({ user_input: "你好" })) {
     *     console.log(chunk.chunk_type, chunk.content);
     *   }
     */
    stream: async function* (
      this: ApiClient,
      body: {
        session_id?: number;
        user_input: string;
        context?: Record<string, unknown>;
      },
    ): AsyncGenerator<ChatChunk> {
      const headers = new Headers({ 'Content-Type': 'application/json' });
      if (this.accessToken) {
        headers.set('Authorization', `Bearer ${this.accessToken}`);
      }
      const resp = await fetch(`${this.baseUrl}/api/v1/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ ...body, stream: true }),
      });
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '');
        throw new Error(`Stream ${resp.status}: ${text || resp.statusText}`);
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // 按行分割(NDJSON)
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          try {
            yield JSON.parse(trimmed) as ChatChunk;
          } catch {
            // 跳过无法解析的行
          }
        }
      }
      // 处理最后残留
      const tail = buffer.trim();
      if (tail) {
        try {
          yield JSON.parse(tail) as ChatChunk;
        } catch {
          /* 忽略 */
        }
      }
    }.bind(this),

    /** 自进化模式(非流式,返回完整飞轮闭环结果) */
    evolve: (body: {
      session_id?: number;
      user_input: string;
      context?: Record<string, unknown>;
    }) =>
      this.request<EvolveResponse>('/api/v1/chat/evolve', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    /** 拓扑统计 */
    topologyStats: () =>
      this.request<{ success: boolean; data: TopologyStats }>(
        '/api/v1/chat/topology/stats',
      ),

    /** 关闭会话 */
    closeSession: (sessionId: number) =>
      this.request<{ success: boolean }>(
        `/api/v1/chat/session/${sessionId}`,
        { method: 'DELETE' },
      ),
  };

  // 管理后台(Phase 1.8,仅 admin 角色可访问)
  admin = {
    /** 用户列表(分页 + 搜索) */
    listUsers: (params?: {
      limit?: number;
      offset?: number;
      search?: string;
    }) => {
      const qs = new URLSearchParams();
      if (params?.limit) qs.set('limit', String(params.limit));
      if (params?.offset) qs.set('offset', String(params.offset));
      if (params?.search) qs.set('search', params.search);
      const q = qs.toString();
      return this.request<AdminListResponse<AdminUser>>(
        `/api/v1/admin/users${q ? '?' + q : ''}`,
      );
    },

    /** 禁用用户 */
    disableUser: (userId: number) =>
      this.request<BaseResponse>(`/api/v1/admin/users/${userId}/disable`, {
        method: 'POST',
      }),

    /** 启用用户 */
    enableUser: (userId: number) =>
      this.request<BaseResponse>(`/api/v1/admin/users/${userId}/enable`, {
        method: 'POST',
      }),

    /** 重置密码(返回临时密码,仅此一次) */
    resetPassword: (userId: number) =>
      this.request<BaseResponse & { data: { temp_password: string } }>(
        `/api/v1/admin/users/${userId}/reset-password`,
        { method: 'POST' },
      ),

    /** 更新用户角色 */
    updateRole: (userId: number, role: 'user' | 'admin') =>
      this.request<BaseResponse>(
        `/api/v1/admin/users/${userId}/role?role=${role}`,
        { method: 'PUT' },
      ),

    /** 审计日志查询 */
    auditLogs: (params?: {
      limit?: number;
      offset?: number;
      user_id?: number;
      action?: string;
      start?: string;
      end?: string;
    }) => {
      const qs = new URLSearchParams();
      if (params?.limit) qs.set('limit', String(params.limit));
      if (params?.offset) qs.set('offset', String(params.offset));
      if (params?.user_id) qs.set('user_id', String(params.user_id));
      if (params?.action) qs.set('action', params.action);
      if (params?.start) qs.set('start', params.start);
      if (params?.end) qs.set('end', params.end);
      const q = qs.toString();
      return this.request<AdminListResponse<AdminAuditLog>>(
        `/api/v1/admin/audit-logs${q ? '?' + q : ''}`,
      );
    },

    /** 获取系统配置 */
    getConfig: () =>
      this.request<BaseResponse & {
        data: {
          hot_reloadable_keys: string[];
          current_values: Record<string, unknown>;
          settings_path: string;
        };
      }>('/api/v1/admin/config'),

    /** 更新系统配置(写回 settings.yaml,即时生效) */
    updateConfig: (updates: Record<string, unknown>) =>
      this.request<BaseResponse & { data: { updated: Record<string, unknown> } }>(
        '/api/v1/admin/config',
        {
          method: 'PATCH',
          body: JSON.stringify(updates),
        },
      ),
  };

  // Phase 2.5: 审计日志(独立路由 /api/v1/audit/*)
  audit = {
    /** 查询审计日志(分页 + 多维筛选) */
    list: (params?: {
      limit?: number;
      offset?: number;
      user_id?: number;
      action?: string;
      start?: string;
      end?: string;
      ip_address?: string;
    }) => {
      const qs = new URLSearchParams();
      if (params?.limit) qs.set('limit', String(params.limit));
      if (params?.offset) qs.set('offset', String(params.offset));
      if (params?.user_id) qs.set('user_id', String(params.user_id));
      if (params?.action) qs.set('action', params.action);
      if (params?.start) qs.set('start', params.start);
      if (params?.end) qs.set('end', params.end);
      if (params?.ip_address) qs.set('ip_address', params.ip_address);
      const q = qs.toString();
      return this.request<BaseResponse & {
        data: { items: AuditLog[]; total: number; limit: number; offset: number };
      }>(`/api/v1/audit/logs${q ? '?' + q : ''}`);
    },

    /**
     * 导出审计日志(JSON 或 CSV 格式,返回纯文本内容)。
     * 导出操作本身会被记录到审计日志。
     */
    export: (params?: {
      format?: 'json' | 'csv';
      user_id?: number;
      action?: string;
      start?: string;
      end?: string;
      limit?: number;
    }) => {
      const qs = new URLSearchParams();
      qs.set('format', params?.format ?? 'json');
      if (params?.user_id) qs.set('user_id', String(params.user_id));
      if (params?.action) qs.set('action', params.action);
      if (params?.start) qs.set('start', params.start);
      if (params?.end) qs.set('end', params.end);
      if (params?.limit) qs.set('limit', String(params.limit));
      return this.requestText(`/api/v1/audit/export?${qs.toString()}`);
    },

    /** 校验审计日志哈希链完整性(检测是否被篡改) */
    verify: () =>
      this.request<BaseResponse & {
        data: {
          is_valid: boolean;
          broken_at_id: number | null;
          message: string;
        };
      }>('/api/v1/audit/verify'),

    /** 列出所有审计动作类型(用于前端筛选下拉框) */
    listActions: () =>
      this.request<BaseResponse & { data: { items: string[] } }>(
        '/api/v1/audit/actions',
      ),
  };

  // Phase 2.1: RBAC 细粒度权限 + 组织架构
  rbac = {
    // ---- 权限查询 ----
    listPermissions: (resource?: string) => {
      const q = resource ? `?resource=${encodeURIComponent(resource)}` : '';
      return this.request<BaseResponse & { data: { items: RbacPermission[]; total: number } }>(
        `/api/v1/rbac/permissions${q}`,
      );
    },

    listPermissionsGrouped: () =>
      this.request<BaseResponse & { data: Record<string, RbacPermission[]> }>(
        '/api/v1/rbac/permissions/grouped',
      ),

    // ---- 角色 CRUD ----
    listRoles: () =>
      this.request<BaseResponse & { data: { items: RbacRole[]; total: number } }>(
        '/api/v1/rbac/roles',
      ),

    getRole: (roleId: number) =>
      this.request<BaseResponse & { data: RbacRole }>(`/api/v1/rbac/roles/${roleId}`),

    createRole: (body: {
      code: string;
      name: string;
      description?: string;
      permission_codes?: string[];
      sort_order?: number;
    }) =>
      this.request<BaseResponse & { data: RbacRole }>('/api/v1/rbac/roles', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    updateRole: (roleId: number, body: {
      name?: string;
      description?: string;
      is_active?: boolean;
      sort_order?: number;
    }) =>
      this.request<BaseResponse & { data: RbacRole }>(`/api/v1/rbac/roles/${roleId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),

    deleteRole: (roleId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/rbac/roles/${roleId}`,
        { method: 'DELETE' },
      ),

    /** 全量替换角色的权限集合 */
    setRolePermissions: (roleId: number, permissionCodes: string[]) =>
      this.request<BaseResponse & { data: RbacRole }>(
        `/api/v1/rbac/roles/${roleId}/permissions`,
        { method: 'PUT', body: JSON.stringify({ permission_codes: permissionCodes }) },
      ),

    // ---- 用户-角色分配 ----
    getUserRoles: (userId: number) =>
      this.request<BaseResponse & { data: { items: RbacRole[]; total: number } }>(
        `/api/v1/rbac/users/${userId}/roles`,
      ),

    /** 全量替换用户的角色集合 */
    setUserRoles: (userId: number, roleIds: number[]) =>
      this.request<BaseResponse & { data: { items: RbacRole[]; total: number } }>(
        `/api/v1/rbac/users/${userId}/roles`,
        { method: 'PUT', body: JSON.stringify({ role_ids: roleIds }) },
      ),

    assignRole: (userId: number, roleId: number) =>
      this.request<BaseResponse & { data: { assigned: boolean } }>(
        `/api/v1/rbac/users/${userId}/roles/${roleId}`,
        { method: 'POST' },
      ),

    revokeRole: (userId: number, roleId: number) =>
      this.request<BaseResponse & { data: { revoked: boolean } }>(
        `/api/v1/rbac/users/${userId}/roles/${roleId}`,
        { method: 'DELETE' },
      ),

    // ---- 当前用户权限 ----
    myPermissions: () =>
      this.request<BaseResponse & { data: { permissions: string[] } }>(
        '/api/v1/rbac/my-permissions',
      ),

    getUserPermissions: (userId: number) =>
      this.request<BaseResponse & { data: { permissions: string[] } }>(
        `/api/v1/rbac/users/${userId}/permissions`,
      ),

    // ---- 部门 CRUD ----
    listDepartments: () =>
      this.request<BaseResponse & { data: { items: RbacDepartment[]; total: number } }>(
        '/api/v1/rbac/departments',
      ),

    getDepartmentTree: () =>
      this.request<BaseResponse & { data: { tree: RbacDepartment[] } }>(
        '/api/v1/rbac/departments/tree',
      ),

    createDepartment: (body: {
      code: string;
      name: string;
      parent_id?: number | null;
      manager_id?: number | null;
      description?: string;
      sort_order?: number;
    }) =>
      this.request<BaseResponse & { data: RbacDepartment }>('/api/v1/rbac/departments', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    updateDepartment: (deptId: number, body: {
      name?: string;
      parent_id?: number | null;
      manager_id?: number | null;
      description?: string;
      is_active?: boolean;
      sort_order?: number;
    }) =>
      this.request<BaseResponse & { data: RbacDepartment }>(`/api/v1/rbac/departments/${deptId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),

    deleteDepartment: (deptId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/rbac/departments/${deptId}`,
        { method: 'DELETE' },
      ),

    // ---- 职位 CRUD ----
    listPositions: () =>
      this.request<BaseResponse & { data: { items: RbacPosition[]; total: number } }>(
        '/api/v1/rbac/positions',
      ),

    createPosition: (body: {
      code: string;
      name: string;
      level?: number;
      description?: string;
      sort_order?: number;
    }) =>
      this.request<BaseResponse & { data: RbacPosition }>('/api/v1/rbac/positions', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    updatePosition: (posId: number, body: {
      name?: string;
      level?: number;
      description?: string;
      is_active?: boolean;
      sort_order?: number;
    }) =>
      this.request<BaseResponse & { data: RbacPosition }>(`/api/v1/rbac/positions/${posId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),

    deletePosition: (posId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/rbac/positions/${posId}`,
        { method: 'DELETE' },
      ),
  };

  // Phase 2.2: LDAP/AD 域集成
  ldap = {
    // ---- LDAP 登录 ----
    login: (body: { username: string; password: string; client_uuid?: string }) =>
      this.request<{
        access_token: string;
        refresh_token: string;
        token_type: string;
        expires_in: number;
        refresh_expires_in: number;
      }>('/api/v1/auth/ldap/login', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    // ---- LDAP 配置管理(仅 admin) ----
    listConfigs: () =>
      this.request<BaseResponse & { data: { items: LdapConfig[]; total: number } }>(
        '/api/v1/admin/ldap/configs',
      ),

    createConfig: (body: {
      name: string;
      server_url: string;
      bind_dn: string;
      bind_password: string;
      user_search_base: string;
      user_filter?: string;
      group_search_base?: string;
      username_attribute?: string;
      email_attribute?: string;
      display_name_attribute?: string;
      use_ssl?: boolean;
      use_tls?: boolean;
      is_active?: boolean;
      sync_interval_hours?: number;
    }) =>
      this.request<BaseResponse & { data: LdapConfig }>('/api/v1/admin/ldap/configs', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    updateConfig: (configId: number, body: Partial<{
      name: string;
      server_url: string;
      bind_dn: string;
      bind_password: string;
      user_search_base: string;
      user_filter: string;
      group_search_base: string;
      username_attribute: string;
      email_attribute: string;
      display_name_attribute: string;
      use_ssl: boolean;
      use_tls: boolean;
      is_active: boolean;
      sync_interval_hours: number;
    }>) =>
      this.request<BaseResponse & { data: LdapConfig }>(
        `/api/v1/admin/ldap/configs/${configId}`,
        { method: 'PUT', body: JSON.stringify(body) },
      ),

    deleteConfig: (configId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/admin/ldap/configs/${configId}`,
        { method: 'DELETE' },
      ),

    /** 测试连通性 */
    testConfig: (configId: number) =>
      this.request<BaseResponse & { success: boolean; message?: string; error?: string }>(
        `/api/v1/admin/ldap/configs/${configId}/test`,
        { method: 'POST' },
      ),

    /** 手动触发用户同步 */
    syncUsers: (configId?: number) => {
      const q = configId ? `?config_id=${configId}` : '';
      return this.request<BaseResponse & {
        data: { results: Array<{ config_id: number; config_name: string; ok: boolean; stats?: any; error?: string }> };
      }>(`/api/v1/admin/ldap/sync${q}`, { method: 'POST' });
    },
  };

  // Phase 2.3: SSO 单点登录(OAuth2.0 / SAML)
  sso = {
    // ---- 公共:列出可用 SSO provider(供登录页渲染) ----
    listProviders: () =>
      this.request<BaseResponse & { data: { items: SsoProvider[]; total: number } }>(
        '/api/v1/auth/sso/providers',
      ),

    // ---- OAuth2.0 ----
    /** 获取授权 URL(客户端跳转到此 URL 完成用户授权) */
    getOAuthAuthorizeUrl: (body: {
      provider_code: string;
      redirect_uri?: string;
      client_uuid?: string;
    }) =>
      this.request<BaseResponse & {
        data: { authorization_url: string; state: string; provider_code: string };
      }>('/api/v1/auth/sso/oauth/authorize', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    /** OAuth 回调:用 code 换 token + 签发本地 Token */
    oauthCallback: (body: {
      provider_code: string;
      code: string;
      state?: string;
      client_uuid?: string;
    }) =>
      this.request<{
        access_token: string;
        refresh_token: string;
        token_type: string;
        expires_in: number;
        refresh_expires_in: number;
      }>('/api/v1/auth/sso/oauth/callback', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    // ---- SAML 2.0 ----
    /** SP 发起登录:生成 AuthnRequest,返回 IdP 重定向 URL */
    samlLogin: (providerCode: string, body?: { client_uuid?: string }) =>
      this.request<BaseResponse & {
        data: { redirect_url: string; state: string; provider_code: string };
      }>(`/api/v1/auth/sso/saml/${encodeURIComponent(providerCode)}/login`, {
        method: 'POST',
        body: JSON.stringify(body ?? {}),
      }),

    /** SAML ACS:解析 IdP POST 的 SAMLResponse,签发本地 Token */
    samlAcs: (providerCode: string, body: {
      saml_response: string;
      relay_state?: string;
      client_uuid?: string;
    }) =>
      this.request<{
        access_token: string;
        refresh_token: string;
        token_type: string;
        expires_in: number;
        refresh_expires_in: number;
      }>(`/api/v1/auth/sso/saml/${encodeURIComponent(providerCode)}/acs`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    // ---- SSO 配置管理(仅 admin) ----
    listConfigs: (providerType?: 'oauth' | 'saml') => {
      const q = providerType ? `?provider_type=${providerType}` : '';
      return this.request<BaseResponse & { data: { items: SsoConfig[]; total: number } }>(
        `/api/v1/admin/sso/configs${q}`,
      );
    },

    createConfig: (body: SsoConfigCreateBody) =>
      this.request<BaseResponse & { data: SsoConfig }>('/api/v1/admin/sso/configs', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    updateConfig: (configId: number, body: Partial<SsoConfigCreateBody>) =>
      this.request<BaseResponse & { data: SsoConfig }>(
        `/api/v1/admin/sso/configs/${configId}`,
        { method: 'PUT', body: JSON.stringify(body) },
      ),

    deleteConfig: (configId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/admin/sso/configs/${configId}`,
        { method: 'DELETE' },
      ),

    /** 测试 SSO 配置(校验完整性 + 库是否安装) */
    testConfig: (configId: number) =>
      this.request<BaseResponse & { success: boolean; message?: string; error?: string }>(
        `/api/v1/admin/sso/configs/${configId}/test`,
        { method: 'POST' },
      ),

    // ---- SSO 绑定关系管理 ----
    listBindings: (userId: number) =>
      this.request<BaseResponse & {
        data: {
          items: SsoBinding[];
          total: number;
          message?: string;
        };
      }>(`/api/v1/admin/sso/bindings?user_id=${userId}`),

    deleteBinding: (bindingId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/admin/sso/bindings/${bindingId}`,
        { method: 'DELETE' },
      ),
  };

  // Phase 2.4: MFA 多因素认证
  mfa = {
    // ---- 用户自助:setup / enable / disable / list ----
    /** 初始化 MFA 因子(返回 TOTP secret + QR URI) */
    setup: (body: { factor_type: 'totp' | 'sms' | 'email'; account_name?: string }) =>
      this.request<BaseResponse & {
        factor_type: string;
        secret: string;
        qr_uri: string;
        factors: string[];
      }>('/api/v1/auth/mfa/setup', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    /** 启用 MFA 因子(验证首码确认 setup,返回恢复码) */
    enable: (body: {
      factor_type: 'totp' | 'sms' | 'email';
      secret?: string;
      code: string;
      phone?: string;
      email?: string;
    }) =>
      this.request<BaseResponse & {
        data?: { recovery_codes?: string[] };
      }>('/api/v1/auth/mfa/enable', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    /** 禁用 MFA 因子(需密码二次确认) */
    disable: (body: {
      factor_id?: number;
      password: string;
      is_password_encrypted?: boolean;
    }) =>
      this.request<BaseResponse>('/api/v1/auth/mfa/disable', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    /** 列出当前用户已绑定的 MFA 因子(不含 secret) */
    listFactors: () =>
      this.request<BaseResponse & {
        data: {
          factors: MfaFactor[];
          recovery_codes_remaining: number;
          mfa_enabled: boolean;
        };
      }>('/api/v1/auth/mfa/factors'),

    /** 重新生成备用恢复码(旧码全部作废) */
    regenerateRecoveryCodes: () =>
      this.request<BaseResponse & {
        data: { recovery_codes: string[] };
      }>('/api/v1/auth/mfa/recovery-codes/regenerate', { method: 'POST' }),

    /** 发送 OTP 验证码(短信/邮箱) */
    sendCode: (body: {
      factor_type: 'sms' | 'email';
      target?: string;
      mfa_token?: string;
    }) =>
      this.request<BaseResponse & {
        data: {
          challenge_id: string;
          target: string;
          expires_in: number;
        };
      }>('/api/v1/auth/mfa/send-code', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    /** MFA 验证(登录流程中完成 MFA,换取双 Token) */
    verify: (body: {
      mfa_token: string;
      factor_type: 'totp' | 'sms' | 'email' | 'recovery';
      code: string;
      challenge_id?: string;
      client_uuid?: string;
    }) =>
      this.request<{
        access_token: string;
        refresh_token: string;
        token_type: string;
        expires_in: number;
        refresh_expires_in: number;
      }>('/api/v1/auth/mfa/verify', {
        method: 'POST',
        body: JSON.stringify(body),
      }),

    // ---- 管理员:强制策略 + 用户因子管理 ----
    listEnforcements: () =>
      this.request<BaseResponse & {
        data: { items: MfaEnforcement[]; total: number };
      }>('/api/v1/admin/mfa/enforcements'),

    upsertEnforcement: (body: {
      role: string;
      factor_type: 'totp' | 'sms' | 'email' | 'any';
      enabled: boolean;
    }) =>
      this.request<BaseResponse & { data: MfaEnforcement }>(
        '/api/v1/admin/mfa/enforcements',
        { method: 'POST', body: JSON.stringify(body) },
      ),

    deleteEnforcement: (enforcementId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/admin/mfa/enforcements/${enforcementId}`,
        { method: 'DELETE' },
      ),

    adminListUserFactors: (userId: number) =>
      this.request<BaseResponse & {
        data: {
          user_id: number;
          username: string;
          factors: MfaFactor[];
          recovery_codes_remaining: number;
          mfa_enabled: boolean;
        };
      }>(`/api/v1/admin/mfa/users/${userId}/factors`),

    adminDisableFactor: (factorId: number) =>
      this.request<BaseResponse & { data: { deleted: boolean } }>(
        `/api/v1/admin/mfa/factors/${factorId}`,
        { method: 'DELETE' },
      ),
  };

  // Phase 4.4: 后台控制面板 Dashboard
  dashboard = {
    /** 总览:核心指标一屏展示 */
    overview: () =>
      this.request<BaseResponse & { data: DashboardOverview }>('/api/v1/dashboard/overview'),

    /** 用户统计明细 */
    users: () =>
      this.request<BaseResponse & { data: DashboardUserStats }>('/api/v1/dashboard/users'),

    /** 审计统计 */
    audit: (hours = 24) =>
      this.request<BaseResponse & { data: DashboardAuditStats }>(
        `/api/v1/dashboard/audit?hours=${hours}`,
      ),

    /** 审核服务统计 */
    moderation: () =>
      this.request<BaseResponse & { data: DashboardModerationStats & ModerationConfig }>(
        '/api/v1/dashboard/moderation',
      ),

    /** 更新审核服务配置 */
    updateModerationConfig: (body: Partial<ModerationConfig>) =>
      this.request<BaseResponse & { data: { updated: string[]; current_config: ModerationConfig } }>(
        '/api/v1/dashboard/moderation/config',
        { method: 'PATCH', body: JSON.stringify(body) },
      ),

    /** 系统信息 */
    system: () =>
      this.request<BaseResponse & { data: DashboardSystemInfo }>('/api/v1/dashboard/system'),

    /** 趋势统计 */
    trends: (days = 7) =>
      this.request<BaseResponse & { data: { days: number; trends: DashboardTrendItem[] } }>(
        `/api/v1/dashboard/trends?days=${days}`,
      ),
  };

  // Phase 3.2: 用户隐私中心
  privacy = {
    /** 查看本人个人数据(已脱敏) */
    profile: () =>
      this.request<BaseResponse & { data: PrivacyProfile }>('/api/v1/privacy/profile'),

    /** 导出全部个人数据(JSON 文本,前端触发下载) */
    export: () =>
      this.requestText('/api/v1/privacy/export'),

    /** 注销账号(软删除,30 天保留期) */
    deleteAccount: (retentionDays = 30) =>
      this.request<BaseResponse & { data: { deleted_at: string; retention_days: number } }>(
        `/api/v1/privacy/delete-account?retention_days=${retentionDays}`,
        { method: 'POST' },
      ),

    /** 撤销注销(30 天内可恢复) */
    cancelDeletion: () =>
      this.request<BaseResponse>('/api/v1/privacy/cancel-deletion', { method: 'POST' }),

    /** 查询注销状态 */
    deletionStatus: () =>
      this.request<BaseResponse & { data: PrivacyDeletionStatus }>('/api/v1/privacy/deletion-status'),
  };

  // ===========================================================================
  // AgentOS 操作系统命名空间 (/api/v1/agentos/*)
  // 对接 AgentOS 内核:进程/文件/记忆/工具/A2A/技能/策略/护栏/审计
  // ===========================================================================
  agentos = {
    /** 启动 AgentOS 内核 */
    boot: () =>
      this.request<AgentOSResponse>('/api/v1/agentos/boot', { method: 'POST' }),

    /** 关闭 AgentOS 内核 */
    shutdown: () =>
      this.request<AgentOSResponse>('/api/v1/agentos/shutdown', { method: 'POST' }),

    /** 派生新进程 */
    spawn: (input: AgentOSSpawnInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/spawn', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 终止指定进程 */
    kill: (input: AgentOSKillInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/kill', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 列出所有进程 */
    ps: () => this.request<AgentOSResponse>('/api/v1/agentos/ps'),

    /** 查询进程详情 */
    info: (pid: string) =>
      this.request<AgentOSResponse>(
        `/api/v1/agentos/info/${encodeURIComponent(pid)}`,
      ),

    /** 执行系统调用 */
    exec: (input: AgentOSExecInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/exec', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 调用 LLM 推理 */
    llm: (input: AgentOSLLMInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/llm', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 读取文件内容 */
    fsRead: (path: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/fs/read', {
        method: 'POST',
        body: JSON.stringify({ path }),
      }),

    /** 写入文件 */
    fsWrite: (input: AgentOSFsWriteInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/fs/write', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 列出目录内容(默认根目录) */
    fsList: (path?: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/fs/list', {
        method: 'POST',
        body: JSON.stringify({ path: path ?? '' }),
      }),

    /** 递归创建目录 */
    fsMkdir: (path: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/fs/mkdir', {
        method: 'POST',
        body: JSON.stringify({ path }),
      }),

    /** 删除文件或目录 */
    fsDelete: (path: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/fs/delete', {
        method: 'POST',
        body: JSON.stringify({ path }),
      }),

    /** 跨层记忆召回 */
    memRecall: (input: AgentOSMemRecallInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/mem/recall', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 存储记忆条目 */
    memStore: (input: AgentOSMemStoreInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/mem/store', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 在指定层搜索记忆 */
    memSearch: (input: AgentOSMemSearchInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/mem/search', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 按 ID 遗忘记忆 */
    memForget: (memory_id: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/mem/forget', {
        method: 'POST',
        body: JSON.stringify({ memory_id }),
      }),

    /** 列出可用工具(可按进程过滤) */
    toolList: (pid?: string) => {
      const q = pid ? `?pid=${encodeURIComponent(pid)}` : '';
      return this.request<AgentOSResponse>(`/api/v1/agentos/tool/list${q}`);
    },

    /** 调用工具 */
    toolInvoke: (input: AgentOSToolInvokeInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/tool/invoke', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** A2A 能力发现(可选能力过滤) */
    a2aDiscover: (capability?: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/a2a/discover', {
        method: 'POST',
        body: JSON.stringify({ capability }),
      }),

    /** A2A 单播消息 */
    a2aSend: (input: AgentOSA2ASendInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/a2a/send', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** A2A 广播消息 */
    a2aBroadcast: (content: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/a2a/broadcast', {
        method: 'POST',
        body: JSON.stringify({ content }),
      }),

    /** 列出已加载技能 */
    skillList: () =>
      this.request<AgentOSResponse>('/api/v1/agentos/skill/list'),

    /** 加载技能目录 */
    skillLoad: (dir: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/skill/load', {
        method: 'POST',
        body: JSON.stringify({ dir }),
      }),

    /** 运行技能 */
    skillRun: (input: AgentOSSkillRunInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/skill/run', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 列出策略 */
    policyList: () =>
      this.request<AgentOSResponse>('/api/v1/agentos/policy/list'),

    /** 新增策略 */
    policyAdd: (input: AgentOSPolicyAddInput) =>
      this.request<AgentOSResponse>('/api/v1/agentos/policy/add', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 列出护栏规则 */
    guardrailList: () =>
      this.request<AgentOSResponse>('/api/v1/agentos/guardrail/list'),

    /** 查询审计日志(可限条数/动作) */
    audit: (input?: AgentOSAuditInput) => {
      const qs = new URLSearchParams();
      if (input?.limit != null) qs.set('limit', String(input.limit));
      if (input?.action) qs.set('action', input.action);
      const q = qs.toString();
      return this.request<AgentOSResponse>(
        `/api/v1/agentos/audit${q ? '?' + q : ''}`,
      );
    },

    /** 系统运行统计 */
    stats: () => this.request<AgentOSResponse>('/api/v1/agentos/stats'),

    /** 创建进程检查点 */
    checkpoint: (pid: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/checkpoint', {
        method: 'POST',
        body: JSON.stringify({ pid }),
      }),

    /** 自然语言接口(转系统调用) */
    natural: (text: string) =>
      this.request<AgentOSResponse>('/api/v1/agentos/natural', {
        method: 'POST',
        body: JSON.stringify({ text }),
      }),

    /** AgentOS 帮助文档 */
    help: () => this.request<AgentOSResponse>('/api/v1/agentos/help'),
  };

  // ===========================================================================
  // Coding 命名空间 (/api/v1/coding/*)
  // 对接代码索引/检索/读写/编辑/Git/测试/自主任务/MCP
  // ===========================================================================
  code = {
    /** 索引代码库(可指定路径与增量模式) */
    index: (input?: CodingIndexInput) =>
      this.request<CodingResponse>('/api/v1/coding/index', {
        method: 'POST',
        body: JSON.stringify(input ?? {}),
      }),

    /** 语义检索代码 */
    search: (input: CodingSearchInput) =>
      this.request<CodingResponse>('/api/v1/coding/search', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 读取文件指定行区间 */
    read: (input: CodingReadInput) =>
      this.request<CodingResponse>('/api/v1/coding/read', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 写入文件(整体覆盖) */
    write: (input: CodingWriteInput) =>
      this.request<CodingResponse>('/api/v1/coding/write', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 编辑文件(字符串替换) */
    edit: (input: CodingEditInput) =>
      this.request<CodingResponse>('/api/v1/coding/edit', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 执行 Git 命令(args 透传给 git CLI) */
    git: (args: string[]) =>
      this.request<CodingResponse>('/api/v1/coding/git', {
        method: 'POST',
        body: JSON.stringify({ args }),
      }),

    /** 运行测试(可选透传参数) */
    test: (args?: string[]) =>
      this.request<CodingResponse>('/api/v1/coding/test', {
        method: 'POST',
        body: JSON.stringify({ args: args ?? [] }),
      }),

    /** 派发自主编码任务 */
    task: (input: CodingTaskInput) =>
      this.request<CodingResponse>('/api/v1/coding/task', {
        method: 'POST',
        body: JSON.stringify(input),
      }),

    /** 获取代码库地图(可限制最大 token 数) */
    map: (maxTokens?: number) => {
      const q =
        maxTokens != null ? `?max_tokens=${encodeURIComponent(maxTokens)}` : '';
      return this.request<CodingResponse>(`/api/v1/coding/map${q}`);
    },

    /** Coding 模块帮助 */
    help: () => this.request<CodingResponse>('/api/v1/coding/help'),

    /** 列出 MCP 工具 */
    mcpTools: () => this.request<CodingResponse>('/api/v1/coding/mcp/tools'),

    /** 调用 MCP 工具 */
    mcpCall: (input: CodingMcpCallInput) =>
      this.request<CodingResponse>('/api/v1/coding/mcp/call', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
  };
}

/** 流式对话分片 */
export interface ChatChunk {
  chunk_type: 'thought' | 'action' | 'text' | 'error';
  content: string;
  done: boolean;
}

/** 自进化响应 */
export interface EvolveResponse {
  success: boolean;
  message: string;
  data: {
    answer: string;
    trace_id: string;
    task_success: boolean;
    duration_ms: number;
    tool_calls: Array<{
      name: string;
      args?: Record<string, unknown>;
      result?: unknown;
      success?: boolean;
    }>;
    concept_path: string[];
    solidified: Record<string, unknown>;
    reflected: unknown;
  };
}

/** 拓扑统计 */
export interface TopologyStats {
  topology: {
    node_count?: number;
    edge_count?: number;
    layer_count?: number;
    [k: string]: unknown;
  };
  search: Record<string, unknown>;
  is_cold_start: boolean;
}

/** 通用响应(BaseResponse) */
export interface BaseResponse {
  success: boolean;
  message?: string;
  data?: unknown;
}

/** 管理后台列表响应 */
export interface AdminListResponse<T> extends BaseResponse {
  data: {
    items: T[];
    total: number;
    limit: number;
    offset: number;
  };
}

/** 管理后台用户视图 */
export interface AdminUser {
  id: number;
  username: string;
  email: string;
  role: 'user' | 'admin';
  profile: Record<string, unknown>;
  quota_total: number;
  quota_used: number;
  created_at: string;
}

/** 审计日志条目(Phase 2.5 扩展:含 IP/UA + 哈希链字段) */
export interface AdminAuditLog {
  id: number;
  user_id: number | null;
  action: string;
  detail: Record<string, unknown>;
  trace_id: string | null;
  /** Phase 2.5: 客户端 IP */
  ip_address?: string | null;
  /** Phase 2.5: User-Agent */
  user_agent?: string | null;
  /** Phase 2.5: 前一条目的哈希(用于哈希链) */
  prev_hash?: string | null;
  /** Phase 2.5: 本条目的哈希(SHA256) */
  entry_hash?: string | null;
  created_at: string | null;
}

/**
 * Phase 2.5 审计日志条目类型(与 AdminAuditLog 等价,语义化命名)。
 * 新代码推荐使用此类型。
 */
export type AuditLog = AdminAuditLog;

/** Phase 2.5 哈希链校验结果 */
export interface AuditVerifyResult {
  is_valid: boolean;
  broken_at_id: number | null;
  message: string;
}

// ===========================================================================
// Phase 2.1 RBAC 类型
// ===========================================================================

/** 权限 */
export interface RbacPermission {
  id: number;
  code: string;
  name: string;
  resource: string;
  action: string;
  description: string;
  is_builtin: boolean;
  created_at: string | null;
}

/** 角色 */
export interface RbacRole {
  id: number;
  tenant_id: number;
  code: string;
  name: string;
  description: string;
  is_builtin: boolean;
  is_active: boolean;
  sort_order: number;
  permission_codes: string[];
  created_at: string | null;
  updated_at: string | null;
}

/** 部门 */
export interface RbacDepartment {
  id: number;
  tenant_id: number;
  code: string;
  name: string;
  parent_id: number | null;
  manager_id: number | null;
  sort_order: number;
  description: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
  children: RbacDepartment[];
}

/** 职位 */
export interface RbacPosition {
  id: number;
  tenant_id: number;
  code: string;
  name: string;
  level: number;
  description: string;
  is_active: boolean;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
}

/** LDAP 服务器配置(Phase 2.2) */
export interface LdapConfig {
  id: number;
  name: string;
  server_url: string;
  bind_dn: string;
  bind_password?: string;
  user_search_base: string;
  user_filter: string;
  group_search_base: string;
  group_filter: string;
  username_attribute: string;
  email_attribute: string;
  display_name_attribute: string;
  use_ssl: boolean;
  use_tls: boolean;
  is_active: boolean;
  sync_interval_hours: number;
  last_sync_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// ===========================================================================
// Phase 2.3 SSO 类型
// ===========================================================================

/** SSO provider(登录页用,精简字段) */
export interface SsoProvider {
  id: number;
  provider_type: 'oauth' | 'saml';
  provider_code: string;
  name: string;
  is_active: boolean;
}

/** SSO 配置(管理后台用,完整字段) */
export interface SsoConfig {
  id: number;
  provider_type: 'oauth' | 'saml';
  provider_code: string;
  name: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
  // OAuth 字段(provider_type=oauth 时)
  client_id?: string;
  redirect_uri?: string;
  scopes?: string[];
  authorize_url?: string;
  token_url?: string;
  userinfo_url?: string;
  field_mapping?: Record<string, string>;
  client_secret?: string;
  // SAML 字段(provider_type=saml 时)
  sp_entity_id?: string;
  acs_url?: string;
  idp_entity_id?: string;
  idp_sso_url?: string;
  name_id_format?: string;
  idp_x509_cert?: string;
}

/** SSO 配置创建请求体(OAuth / SAML 共用) */
export interface SsoConfigCreateBody {
  provider_type: 'oauth' | 'saml';
  provider_code: string;
  name: string;
  is_active?: boolean;
  // OAuth 必填
  client_id?: string;
  client_secret?: string;
  redirect_uri?: string;
  scopes?: string[];
  authorize_url?: string;
  token_url?: string;
  userinfo_url?: string;
  field_mapping?: Record<string, string>;
  // SAML 必填
  sp_entity_id?: string;
  acs_url?: string;
  idp_entity_id?: string;
  idp_sso_url?: string;
  idp_x509_cert?: string;
  name_id_format?: string;
}

/** SSO 绑定关系(provider_user_id ↔ local_user_id) */
export interface SsoBinding {
  id: number;
  user_id: number;
  provider_code: string;
  provider_user_id: string;
  created_at: string | null;
}

/** MFA 因子(用户已绑定) */
export interface MfaFactor {
  id: number;
  user_id: number;
  factor_type: 'totp' | 'sms' | 'email';
  enabled: boolean;
  /** TOTP 不返回;SMS 返回掩码手机号;EMAIL 返回掩码邮箱 */
  secret?: string;
  phone?: string;
  email?: string;
  created_at: string | null;
  updated_at: string | null;
}

/** MFA 强制策略(按角色) */
export interface MfaEnforcement {
  id: number;
  role: string;
  /** 要求的因子类型:any=任意一种即可 */
  factor_type: 'totp' | 'sms' | 'email' | 'any';
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

// ===========================================================================
// Phase 4.4: Dashboard 类型
// ===========================================================================

/** Dashboard 总览 */
export interface DashboardOverview {
  users: {
    total: number;
    active: number;
    disabled: number;
    pending_deletion: number;
    today_new: number;
  };
  audit: {
    last_24h_count: number;
    top_action: string | null;
    action_distribution: Record<string, number>;
  };
  moderation: {
    total_input: number;
    total_output: number;
    blocked_input: number;
    blocked_output: number;
    sanitized: number;
    avg_duration_ms: number;
    category_counts: Record<string, number>;
  };
  system: {
    version: string;
    uptime_seconds: number;
    storage_mode: string;
    python_version: string;
  };
}

/** 用户统计明细 */
export interface DashboardUserStats {
  total: number;
  by_role: Record<string, number>;
  daily_new_7d: Array<{ date: string; new_users: number }>;
  pending_deletion: number;
  disabled: number;
}

/** 审计统计 */
export interface DashboardAuditStats {
  window_hours: number;
  total_events: number;
  action_distribution: Record<string, number>;
  top_active_users: Array<{ user_id: number; count: number }>;
}

/** 审核服务统计 */
export interface DashboardModerationStats {
  total_input: number;
  total_output: number;
  blocked_input: number;
  blocked_output: number;
  sanitized: number;
  avg_duration_ms: number;
  category_counts: Record<string, number>;
}

/** 审核服务配置 */
export interface ModerationConfig {
  enabled: boolean;
  input_enabled: boolean;
  output_enabled: boolean;
  auto_sanitize: boolean;
  block_high_risk_only: boolean;
  high_risk_threshold: number;
}

/** 系统信息 */
export interface DashboardSystemInfo {
  version: string;
  uptime_seconds: number;
  uptime_human: string;
  storage_mode: string;
  python_version: string;
  environment: string;
  mode: string;
}

/** 趋势项 */
export interface DashboardTrendItem {
  date: string;
  new_users: number;
  audit_events: number;
}

// ===========================================================================
// Phase 3.2: 隐私中心类型
// ===========================================================================

/** 用户个人数据(已脱敏) */
export interface PrivacyProfile {
  id: number;
  username: string;
  email: string;
  role: string;
  created_at: string | null;
  phone: string;
  quota: {
    total: number;
    used: number;
    remaining: number;
  };
  disabled: boolean;
  deleted_at: string | null;
  hard_delete_at: string | null;
}

/** 注销状态 */
export interface PrivacyDeletionStatus {
  status: 'active' | 'pending_deletion';
  deleted_at: string | null;
  hard_delete_at: string | null;
  remaining_days: number | null;
}
