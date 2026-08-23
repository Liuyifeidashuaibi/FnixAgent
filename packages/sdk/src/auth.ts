/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * fnixagent 鉴权模块 — Phase 1.7
 *
 * 功能:
 *   ① 获取服务端 RSA-2048 公钥
 *   ② 用公钥加密密码(Web Crypto API,RSA-OAEP-SHA256)
 *   ③ 登录/注册/刷新/登出
 *   ④ 双 Token 管理(Access 2h + Refresh 7d)
 *   ⑤ 设备指纹生成(客户端 UUID 持久化)
 *   ⑥ 401 自动刷新拦截器
 */
import { ApiClient } from './client';
import type { Middleware } from 'openapi-fetch';

/** 公钥响应 */
export interface PublicKeyInfo {
  public_key: string; // PEM 格式
  key_id: string;
  algorithm: string;
  expires_at: string | null;
}

/** Token 响应(双 Token) */
export interface TokenInfo {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  expires_in: number; // Access Token 有效期(秒)
  refresh_expires_in?: number; // Refresh Token 有效期(秒)
}

/** 用户信息 */
export interface AuthUser {
  id: number;
  username: string;
  email: string;
  role: 'user' | 'admin';
  created_at: string;
}

/** Token 存储抽象(Electron 用 safeStorage,Web 用 localStorage) */
export interface TokenStorage {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
}

/** localStorage 存储(Web 环境) */
export class LocalStorageTokenStorage implements TokenStorage {
  async get(key: string): Promise<string | null> {
    return localStorage.getItem(key);
  }
  async set(key: string, value: string): Promise<void> {
    localStorage.setItem(key, value);
  }
  async delete(key: string): Promise<void> {
    localStorage.removeItem(key);
  }
}

/** Electron safeStorage 存储(通过 preload 暴露的 API) */
export class ElectronTokenStorage implements TokenStorage {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private electron: any;
  constructor() {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    this.electron = (globalThis as any).electron;
  }
  async get(key: string): Promise<string | null> {
    if (!this.electron?.secure?.get) return localStorage.getItem(key);
    return await this.electron.secure.get(key);
  }
  async set(key: string, value: string): Promise<void> {
    if (!this.electron?.secure?.set) {
      localStorage.setItem(key, value);
      return;
    }
    await this.electron.secure.set(key, value);
  }
  async delete(key: string): Promise<void> {
    if (!this.electron?.secure?.get) {
      localStorage.removeItem(key);
      return;
    }
    // safeStorage 没有 delete,用 set 空字符串等价
    await this.electron.secure.set(key, '');
  }
}

const STORAGE_KEYS = {
  accessToken: 'oa.access_token',
  refreshToken: 'oa.refresh_token',
  clientUuid: 'oa.client_uuid',
  expiresAt: 'oa.expires_at',
  username: 'oa.username',
} as const;

/**
 * 生成并持久化客户端 UUID(设备指纹)
 *
 * 首次调用生成 UUID v4,后续从存储读取。
 * 用作设备指纹,与服务端 Token 绑定。
 */
export async function getOrCreateClientUuid(
  storage: TokenStorage,
): Promise<string> {
  let uuid = await storage.get(STORAGE_KEYS.clientUuid);
  if (!uuid) {
    uuid = generateUuidV4();
    await storage.set(STORAGE_KEYS.clientUuid, uuid);
  }
  return uuid;
}

/** 生成 UUID v4 */
function generateUuidV4(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // 回退:用 getRandomValues 手动拼装
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`;
}

/**
 * 用 RSA 公钥加密密码(Web Crypto API)
 *
 * 流程:
 *   1. 解析 PEM 公钥 → DER (SPKI)
 *   2. importKey 为 CryptoKey
 *   3. RSA-OAEP-SHA256 加密
 *   4. Base64 编码输出
 */
export async function encryptPassword(
  password: string,
  publicKeyPem: string,
): Promise<string> {
  // 1. 提取 PEM 中的 Base64 内容
  const b64 = publicKeyPem
    .replace(/-----BEGIN PUBLIC KEY-----/g, '')
    .replace(/-----END PUBLIC KEY-----/g, '')
    .replace(/\s+/g, '');
  // 2. Base64 → DER bytes
  const derBytes = base64ToBytes(b64);
  // 3. 导入公钥(TS lib dom 对 Uint8Array 与 BufferSource 类型严格,需 cast)
  const cryptoKey = await crypto.subtle.importKey(
    'spki',
    derBytes as BufferSource,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  );
  // 4. 加密
  const encoded = new TextEncoder().encode(password);
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'RSA-OAEP' },
    cryptoKey,
    encoded as BufferSource,
  );
  // 5. Base64 编码
  return bytesToBase64(new Uint8Array(ciphertext));
}

/** Base64 字符串 → Uint8Array */
function base64ToBytes(b64: string): Uint8Array {
  const binStr = atob(b64);
  const bytes = new Uint8Array(binStr.length);
  for (let i = 0; i < binStr.length; i++) {
    bytes[i] = binStr.charCodeAt(i);
  }
  return bytes;
}

/** Uint8Array → Base64 字符串 */
function bytesToBase64(bytes: Uint8Array): string {
  let binStr = '';
  for (let i = 0; i < bytes.length; i++) {
    binStr += String.fromCharCode(bytes[i]);
  }
  return btoa(binStr);
}

/**
 * 鉴权管理器 — 封装登录/注册/刷新/登出/Token 管理
 *
 * 用法:
 *   const auth = new AuthManager(client, storage);
 *   await auth.login('user', 'pass');
 *   const user = await auth.getCurrentUser();
 *   await auth.logout();
 */

/** MFA Challenge 响应(登录时返回,指示需完成 MFA) */
export interface MfaChallenge {
  mfa_required: true;
  mfa_token: string;
  factors: string[];              // ['totp', 'recovery']
  expires_in: number;             // 300s
}

/**
 * MFA Required 异常 — 登录时用户启用了 MFA,需调用方捕获并引导用户完成验证。
 *
 * 用法:
 *   try {
 *     await auth.login(username, password);
 *   } catch (e) {
 *     if (e instanceof MfaRequiredError) {
 *       const mfaToken = e.mfaToken;
 *       const factors = e.factors;
 *       // 引导用户输入 TOTP / 恢复码
 *       await auth.completeMfa(mfaToken, 'totp', userInputCode);
 *     }
 *   }
 */
export class MfaRequiredError extends Error {
  readonly mfaToken: string;
  readonly factors: string[];
  readonly expiresIn: number;
  readonly remember: boolean;
  readonly username: string;

  constructor(
    mfaToken: string,
    factors: string[],
    expiresIn: number,
    remember: boolean,
    username: string,
  ) {
    super('需要完成 MFA 多因素认证');
    this.name = 'MfaRequiredError';
    this.mfaToken = mfaToken;
    this.factors = factors;
    this.expiresIn = expiresIn;
    this.remember = remember;
    this.username = username;
  }

  /** 类型守卫:判断登录响应是否为 MFA Challenge */
  static isMfaChallenge(resp: unknown): resp is MfaChallenge {
    return (
      typeof resp === 'object' &&
      resp !== null &&
      (resp as { mfa_required?: unknown }).mfa_required === true &&
      typeof (resp as { mfa_token?: unknown }).mfa_token === 'string'
    );
  }
}

export class AuthManager {
  private client: ApiClient;
  private storage: TokenStorage;
  private clientUuidPromise: Promise<string> | null = null;
  private refreshPromise: Promise<boolean> | null = null;

  constructor(client: ApiClient, storage?: TokenStorage) {
    this.client = client;
    this.storage =
      storage ??
      (typeof globalThis !== 'undefined' &&
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (globalThis as any).electron?.secure
        ? new ElectronTokenStorage()
        : new LocalStorageTokenStorage());
  }

  /** 获取客户端 UUID(缓存) */
  private async getClientUuid(): Promise<string> {
    if (!this.clientUuidPromise) {
      this.clientUuidPromise = getOrCreateClientUuid(this.storage);
    }
    return this.clientUuidPromise;
  }

  /** 从存储加载已保存的 Token */
  async loadStoredTokens(): Promise<{
    accessToken: string | null;
    refreshToken: string | null;
  }> {
    const [accessToken, refreshToken] = await Promise.all([
      this.storage.get(STORAGE_KEYS.accessToken),
      this.storage.get(STORAGE_KEYS.refreshToken),
    ]);
    if (accessToken) {
      this.client.setAccessToken(accessToken);
    }
    return { accessToken, refreshToken };
  }

  /** 登录(自动加密密码 + 设备指纹绑定)
   *
   * Phase 2.4:若用户启用了 MFA,登录会返回 mfa_required=true 而非 Token。
   * 此方法会抛出 `MfaRequiredError`,调用方应捕获并通过 `completeMfa()` 完成。
   */
  async login(
    username: string,
    password: string,
    remember = false,
  ): Promise<TokenInfo> {
    // 1. 获取公钥
    const pubKey = await this.fetchPublicKey();
    // 2. 加密密码
    const encrypted = await encryptPassword(password, pubKey.public_key);
    // 3. 获取设备指纹
    const clientUuid = await this.getClientUuid();

    // 4. 调用登录接口(可能返回 Token 或 MFA Challenge)
    const result = await this.rawLogin({
      username,
      password: encrypted,
      is_password_encrypted: true,
      client_uuid: clientUuid,
    });

    // 5. 检测 MFA Challenge
    if (MfaRequiredError.isMfaChallenge(result)) {
      throw new MfaRequiredError(
        result.mfa_token,
        result.factors,
        result.expires_in,
        remember,
        username,
      );
    }

    // 6. 持久化 Token
    await this.persistTokens(result, remember);
    if (remember) {
      await this.storage.set(STORAGE_KEYS.username, username);
    }
    return result;
  }

  /**
   * 所有者 / 管理员特殊通道登录。
   * 需服务端配置 FNIX_OWNER_TOKEN；可首次创建 admin 账号。
   */
  async ownerLogin(input: {
    username: string;
    password: string;
    ownerToken: string;
    remember?: boolean;
  }): Promise<TokenInfo> {
    const clientUuid = await this.getClientUuid();
    const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/owner/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: input.username,
        password: input.password,
        owner_token: input.ownerToken,
        client_uuid: clientUuid,
        remember: input.remember ?? true,
      }),
    });
    if (resp.status === 401) {
      throw new Error('所有者口令或密码错误');
    }
    if (resp.status === 403) {
      const text = await resp.text().catch(() => '');
      throw new Error(text || '所有者通道未启用或账号不允许');
    }
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`所有者登录失败 ${resp.status}: ${text}`);
    }
    const token = (await resp.json()) as TokenInfo;
    await this.persistTokens(token, input.remember ?? true);
    if (input.remember !== false) {
      await this.storage.set(STORAGE_KEYS.username, input.username);
    }
    return token;
  }

  /** 完成 MFA 验证(登录流程中,捕获 MfaRequiredError 后调用) */
  async completeMfa(
    mfaToken: string,
    factorType: 'totp' | 'sms' | 'email' | 'recovery',
    code: string,
    options?: { challengeId?: string; remember?: boolean },
  ): Promise<TokenInfo> {
    const clientUuid = await this.getClientUuid();
    const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/mfa/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mfa_token: mfaToken,
        factor_type: factorType,
        code,
        challenge_id: options?.challengeId,
        client_uuid: clientUuid,
      }),
    });
    if (resp.status === 401) {
      throw new Error('MFA 验证失败:验证码错误或已过期');
    }
    if (resp.status === 410) {
      throw new Error('MFA challenge 已过期,请重新登录');
    }
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`MFA 验证失败 ${resp.status}: ${text}`);
    }
    const token = (await resp.json()) as TokenInfo;
    await this.persistTokens(token, options?.remember ?? false);
    return token;
  }

  // Phase 3.0: 手机号验证码登录(国内)
  /** 发送短信验证码 */
  async sendSmsCode(phone: string): Promise<{ expiresIn: number }> {
    const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/sms/send-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone }),
    });
    if (resp.status === 429) {
      throw new Error('验证码发送过于频繁,请 60 秒后重试');
    }
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`发送验证码失败 ${resp.status}: ${text}`);
    }
    const data = await resp.json();
    return { expiresIn: data.expires_in };
  }

  /** 手机号验证码登录 */
  async loginWithSms(phone: string, code: string, remember = false): Promise<TokenInfo> {
    const clientUuid = await this.getClientUuid();
    const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/sms/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, code, client_uuid: clientUuid }),
    });
    if (resp.status === 401) {
      throw new Error('验证码错误或已过期');
    }
    if (resp.status === 404) {
      throw new Error('该手机号未注册,请先注册账号');
    }
    if (resp.status === 403) {
      throw new Error('账号已被禁用,请联系管理员');
    }
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`手机号登录失败 ${resp.status}: ${text}`);
    }
    const token = (await resp.json()) as TokenInfo;
    await this.persistTokens(token, remember);
    return token;
  }

  /** 注册 */
  async register(input: {
    username: string;
    email?: string;
    password: string;
    role?: 'user' | 'admin';
  }): Promise<AuthUser> {
    const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`注册失败 ${resp.status}: ${text}`);
    }
    return (await resp.json()) as AuthUser;
  }

  /** 刷新 Token(用 Refresh Token 换新的双 Token) */
  async refresh(): Promise<boolean> {
    // 防止并发刷新(多个 401 同时触发)
    if (this.refreshPromise) return this.refreshPromise;
    this.refreshPromise = this._doRefresh();
    try {
      return await this.refreshPromise;
    } finally {
      this.refreshPromise = null;
    }
  }

  private async _doRefresh(): Promise<boolean> {
    const refreshToken = await this.storage.get(STORAGE_KEYS.refreshToken);
    if (!refreshToken) return false;
    const clientUuid = await this.getClientUuid();
    try {
      const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          refresh_token: refreshToken,
          client_uuid: clientUuid,
        }),
      });
      if (!resp.ok) {
        // Refresh Token 失效 → 清理
        await this.clearTokens();
        return false;
      }
      const token = (await resp.json()) as TokenInfo;
      await this.persistTokens(token, true);
      return true;
    } catch {
      await this.clearTokens();
      return false;
    }
  }

  /** 登出(把 Access Token 加入黑名单) */
  async logout(): Promise<void> {
    try {
      await fetch(`${this.client['baseUrl']}/api/v1/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${await this.storage.get(STORAGE_KEYS.accessToken)}` },
      });
    } catch {
      // 忽略网络错误
    }
    await this.clearTokens();
  }

  /** 获取当前用户 */
  async getCurrentUser(): Promise<AuthUser | null> {
    const accessToken = await this.storage.get(STORAGE_KEYS.accessToken);
    if (!accessToken) return null;
    this.client.setAccessToken(accessToken);
    try {
      const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (resp.status === 401) {
        // 尝试刷新
        const ok = await this.refresh();
        if (!ok) return null;
        return this.getCurrentUser();
      }
      if (!resp.ok) return null;
      return (await resp.json()) as AuthUser;
    } catch {
      return null;
    }
  }

  /** 检查 Access Token 是否即将过期(提前 60 秒刷新) */
  async isTokenExpiringSoon(): Promise<boolean> {
    const expiresAtStr = await this.storage.get(STORAGE_KEYS.expiresAt);
    if (!expiresAtStr) return true;
    const expiresAt = parseInt(expiresAtStr, 10);
    const now = Date.now();
    return now > expiresAt - 60_000;
  }

  /** 获取公钥 */
  private async fetchPublicKey(): Promise<PublicKeyInfo> {
    const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/pubkey`);
    if (!resp.ok) {
      throw new Error(`获取公钥失败: ${resp.status}`);
    }
    return (await resp.json()) as PublicKeyInfo;
  }

  /** 原始登录接口(返回 TokenInfo 或 MFA Challenge) */
  private async rawLogin(body: {
    username: string;
    password: string;
    is_password_encrypted: boolean;
    client_uuid: string;
  }): Promise<TokenInfo | MfaChallenge> {
    const resp = await fetch(`${this.client['baseUrl']}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (resp.status === 401) {
      throw new Error('用户名或密码错误');
    }
    if (resp.status === 429) {
      throw new Error('登录尝试过多,请 15 分钟后再试');
    }
    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      throw new Error(`登录失败 ${resp.status}: ${text}`);
    }
    return (await resp.json()) as TokenInfo | MfaChallenge;
  }

  /** 持久化 Token */
  private async persistTokens(token: TokenInfo, remember: boolean): Promise<void> {
    this.client.setAccessToken(token.access_token);
    const expiresAt = Date.now() + token.expires_in * 1000;
    // remember=false 时用 sessionStorage,关闭浏览器即丢失
    // 这里简化:统一存到 storage,remember 控制是否持久化 username
    await this.storage.set(STORAGE_KEYS.accessToken, token.access_token);
    if (token.refresh_token) {
      await this.storage.set(STORAGE_KEYS.refreshToken, token.refresh_token);
    }
    await this.storage.set(STORAGE_KEYS.expiresAt, String(expiresAt));
    if (!remember) {
      // 非记住我:不持久化 refresh token(会话级)
      // 但 Electron safeStorage 没有 session 级,这里保留
    }
  }

  /**
   * 持久化外部获取的 Token(Phase 3.0)
   *
   * 用于 OAuth / SAML 等非密码登录流程:回调拿到 Token 后,
   * 调用此方法写入存储,后续即可用 getCurrentUser() / refresh() 等。
   */
  async persistExternalToken(token: TokenInfo, remember = true): Promise<void> {
    await this.persistTokens(token, remember);
  }

  /** 清理 Token */
  private async clearTokens(): Promise<void> {
    this.client.setAccessToken(null);
    await Promise.all([
      this.storage.delete(STORAGE_KEYS.accessToken),
      this.storage.delete(STORAGE_KEYS.refreshToken),
      this.storage.delete(STORAGE_KEYS.expiresAt),
    ]);
  }

  /** 安装 401 自动刷新拦截器(供 fetch 包装使用) */
  installAutoRefreshInterceptor(): void {
    const originalFetch = globalThis.fetch;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).fetch = async (
      input: RequestInfo | URL,
      init?: RequestInit,
    ): Promise<Response> => {
      const resp = await originalFetch(input, init);
      if (resp.status !== 401) return resp;
      // 尝试刷新
      const ok = await this.refresh();
      if (!ok) return resp;
      // 重放原请求(带新 Token)
      const newToken = await this.storage.get(STORAGE_KEYS.accessToken);
      if (newToken && init) {
        const headers = new Headers(init.headers);
        headers.set('Authorization', `Bearer ${newToken}`);
        return originalFetch(input, { ...init, headers });
      }
      return resp;
    };
  }

  // ---- Phase P2-01: Token 管理 API(供拦截器与外部调用) ----

  /** 获取当前 Access Token(从存储读取,可能为 null) */
  async getAccessToken(): Promise<string | null> {
    return this.storage.get(STORAGE_KEYS.accessToken);
  }

  /** 手动设置 Refresh Token(用于 OAuth/SAML 等外部登录回调) */
  async setRefreshToken(token: string | null): Promise<void> {
    if (token) {
      await this.storage.set(STORAGE_KEYS.refreshToken, token);
    } else {
      await this.storage.delete(STORAGE_KEYS.refreshToken);
    }
  }

  /** 获取当前 Refresh Token(从存储读取,可能为 null) */
  async getRefreshToken(): Promise<string | null> {
    return this.storage.get(STORAGE_KEYS.refreshToken);
  }
}

// ===========================================================================
// Phase P2-01: openapi-fetch 兼容的 Token 刷新拦截器
// ===========================================================================

/** 不应触发自动刷新的鉴权端点(避免无限循环) */
const AUTH_PATH_BLOCKLIST = [
  '/api/v1/auth/login',
  '/api/v1/auth/refresh',
  '/api/v1/auth/register',
  '/api/v1/auth/logout',
  '/api/v1/auth/mfa/verify',
  '/api/v1/auth/sms/login',
  '/api/v1/auth/ldap/login',
  '/api/v1/auth/sso/oauth/callback',
  '/api/v1/auth/sso/saml/',
];

/**
 * 创建 Token 刷新拦截器(openapi-fetch 中间件)
 *
 * 行为:
 *   - onResponse 收到 401 时,自动调用 `authManager.refresh()` 刷新双 Token
 *   - 刷新成功后用新 Access Token 重放原请求(对调用方完全透明)
 *   - 刷新失败则原样返回 401 响应
 *   - 鉴权端点(login/refresh/register 等)不触发刷新,避免无限循环
 *   - 并发 401 请求只触发一次刷新(由 AuthManager.refresh 内部去重)
 *
 * @param authManager 鉴权管理器实例
 * @param onTokenRefreshed 刷新成功后的回调(用于同步外部 client 的 Access Token)
 */
export function createAuthRefreshInterceptor(
  authManager: AuthManager,
  onTokenRefreshed?: (newAccessToken: string) => void,
): Middleware {
  // 缓存每个请求的 body 文本(用于重放,因为 Request body 流只能消费一次)
  const bodyCache = new WeakMap<Request, string>();

  return {
    async onRequest({ request }) {
      // 对带 body 的请求,提前读取并缓存(clone 不影响原请求)
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        try {
          const clone = request.clone();
          bodyCache.set(request, await clone.text());
        } catch {
          // body 读取失败(如流式上传)则不缓存,重放时降级为无 body
        }
      }
      return request;
    },

    async onResponse({ request, response }) {
      if (response.status !== 401) return response;

      // 鉴权端点不自动刷新(避免循环)
      let pathname = '';
      try {
        pathname = new URL(request.url).pathname;
      } catch {
        return response;
      }
      if (AUTH_PATH_BLOCKLIST.some((p) => pathname.startsWith(p))) {
        return response;
      }

      // 触发刷新(并发由 AuthManager 内部去重)
      const ok = await authManager.refresh();
      if (!ok) return response;

      const newToken = await authManager.getAccessToken();
      if (!newToken) return response;

      // 同步外部 client 的 token
      onTokenRefreshed?.(newToken);

      // 用新 Token 重放原请求
      const headers = new Headers(request.headers);
      headers.set('Authorization', `Bearer ${newToken}`);
      const cachedBody = bodyCache.get(request);
      const replayReq = new Request(request.url, {
        method: request.method,
        headers,
        body: cachedBody ?? null,
        // 保留 redirect 等元数据
        redirect: request.redirect,
      });
      return fetch(replayReq);
    },
  };
}
