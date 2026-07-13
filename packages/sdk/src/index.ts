/**
 * @officeagent/sdk — OfficeAgent TypeScript API Client
 *
 * 双 client 模式:
 *   - sdk: 手写轻量 client(Phase 1.1,覆盖核心端点,无构建依赖)
 *   - typedSdk: openapi-fetch 类型安全 client(Phase 1.2,全部 49 端点,端到端类型推导)
 *
 * 生成命令: pnpm gen:api (从后端 openapi.json 重新生成类型)
 */
export { ApiClient } from './client';
export type {
  HealthResponse,
  User,
  LoginRequest,
  TokenPair,
  Document,
  Task,
  // AgentOS 类型 (/api/v1/agentos/*)
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
  // Coding 类型 (/api/v1/coding/*)
  CodingResponse,
  CodingIndexInput,
  CodingSearchInput,
  CodingReadInput,
  CodingWriteInput,
  CodingEditInput,
  CodingTaskInput,
  CodingMcpCallInput,
} from './types';
export type {
  ChatChunk,
  EvolveResponse,
  TopologyStats,
  BaseResponse,
  AdminListResponse,
  AdminUser,
  AdminAuditLog,
  AuditLog,
  AuditVerifyResult,
  RbacPermission,
  RbacRole,
  RbacDepartment,
  RbacPosition,
  LdapConfig,
  SsoProvider,
  SsoConfig,
  SsoConfigCreateBody,
  SsoBinding,
  MfaFactor,
  MfaEnforcement,
  // Phase 4.4: Dashboard
  DashboardOverview,
  DashboardUserStats,
  DashboardAuditStats,
  DashboardModerationStats,
  ModerationConfig,
  DashboardSystemInfo,
  DashboardTrendItem,
  // Phase 3.2: 隐私中心
  PrivacyProfile,
  PrivacyDeletionStatus,
} from './client';

// Phase 1.7: 鉴权模块(RSA 加密 + 双 Token + 设备指纹)
export {
  AuthManager,
  LocalStorageTokenStorage,
  ElectronTokenStorage,
  encryptPassword,
  getOrCreateClientUuid,
  MfaRequiredError,
  // Phase P2-01: openapi-fetch 兼容的 Token 刷新拦截器
  createAuthRefreshInterceptor,
} from './auth';
export type {
  PublicKeyInfo,
  TokenInfo,
  AuthUser,
  TokenStorage,
  MfaChallenge,
} from './auth';

// Phase P2-01: 速率限制感知重试拦截器(429 退避重试)
export { createRateLimitInterceptor } from './rate-limit';

// Phase P2-01: SSE 流式响应封装
export { parseSSEStream, streamChat } from './sse';
export type { SSEEvent, StreamChatBody, StreamChatOptions } from './sse';

// Phase 1.2: 类型安全 client(基于 openapi-fetch + 自动生成 schema)
export { createTypedClient, typedSdk } from './typed-client';
export type { paths, components } from './generated/schema';

// ---- 默认实例(单例,供前端直接 import) ----
import { ApiClient } from './client';
import { AuthManager } from './auth';
import { createTypedClient } from './typed-client';
import { createRateLimitInterceptor } from './rate-limit';
import { createAuthRefreshInterceptor } from './auth';
import { streamChat as streamChatFn } from './sse';
import type { StreamChatBody } from './sse';

export const sdk = new ApiClient();
export const auth = new AuthManager(sdk);

// ===========================================================================
// Phase P2-01: 增强型 SDK 工厂
// ===========================================================================

const SDK_DEFAULT_BASE_URL = 'http://localhost:8000';

/**
 * 创建增强型 OfficeAgent SDK 实例
 *
 * 在 createTypedClient 基础上预装两个拦截器:
 *   ① 速率限制拦截器(429 → 按 Retry-After + 指数退避重试)
 *   ② Token 刷新拦截器(401 → 自动刷新双 Token 并透明重放请求)
 *
 * 同时提供 streamChat(SSE 流式对话)与 setRefreshToken(外部登录回调)入口。
 *
 * @param baseUrl API 基地址(默认 http://localhost:8000)
 *
 * 用法:
 *   ```ts
 *   const oa = createOfficeAgentSDK('http://localhost:8000');
 *   await oa.auth.login('user', 'pass');
 *   // 普通请求(401/429 自动处理)
 *   const { data } = await oa.client.GET('/api/v1/auth/me');
 *   // 流式对话
 *   for await (const evt of oa.streamChat({ user_input: '你好' })) {
 *     console.log(evt.event, evt.data);
 *   }
 *   ```
 */
export function createOfficeAgentSDK(baseUrl?: string) {
  const url = (baseUrl ?? SDK_DEFAULT_BASE_URL).replace(/\/$/, '');

  // 类型安全 client(openapi-fetch)
  const { client, setAccessToken: setTypedToken } = createTypedClient(url);

  // 手写轻量 client(AuthManager 内部依赖:baseUrl + setAccessToken)
  const apiClient = new ApiClient(url);
  const authManager = new AuthManager(apiClient);

  // 当前 Access Token 缓存(供 streamChat 使用,与 typed client 同步)
  let currentAccessToken: string | null = null;

  /** 同步更新 typed client / 手写 client / 本地缓存的 Access Token */
  const setAccessToken = (token: string | null) => {
    currentAccessToken = token;
    setTypedToken(token);
    apiClient.setAccessToken(token);
  };

  /** 设置 Refresh Token(用于 OAuth/SAML 等外部登录回调) */
  const setRefreshToken = (token: string | null) =>
    authManager.setRefreshToken(token);

  // 初始化:从存储加载已保存的 Token(异步,不阻塞工厂返回)
  void authManager.loadStoredTokens().then(({ accessToken }) => {
    if (accessToken) setAccessToken(accessToken);
  });

  // 预装拦截器(顺序:rate-limit 先于 auth-refresh)
  //   onResponse 执行顺序 = 注册顺序:rate-limit 先处理 429,auth-refresh 再处理 401
  client.use(createRateLimitInterceptor());
  client.use(
    createAuthRefreshInterceptor(authManager, (newToken) => setAccessToken(newToken)),
  );

  return {
    /** openapi-fetch 类型安全 client(已预装拦截器) */
    client,
    /** AuthManager 实例(登录/注册/刷新/登出) */
    auth: authManager,
    /** 设置 Access Token(同步到 typed client 与手写 client) */
    setAccessToken,
    /** 设置 Refresh Token(用于外部登录回调) */
    setRefreshToken,
    /** SSE 流式对话(已绑定 baseUrl 与 token) */
    streamChat: (body: StreamChatBody) =>
      streamChatFn(
        { client, setAccessToken },
        body,
        { baseUrl: url, getAccessToken: () => currentAccessToken },
      ),
  };
}
