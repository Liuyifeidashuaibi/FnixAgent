/**
 * fnixagent 类型安全 API Client — 基于 openapi-fetch
 * 利用 openapi-typescript 生成的 schema 实现端到端类型安全
 */
import createClient from 'openapi-fetch';
import type { paths } from './generated/schema';

export type { paths, components } from './generated/schema';

const DEFAULT_BASE_URL = 'http://localhost:8000';

export function createTypedClient(baseUrl: string = DEFAULT_BASE_URL) {
  const client = createClient<paths>({ baseUrl });

  // 注入 Access Token 拦截器(等效 axios 拦截器)
  let accessToken: string | null = null;
  client.use({
    onRequest({ request }) {
      if (accessToken) {
        request.headers.set('Authorization', `Bearer ${accessToken}`);
      }
      return request;
    },
  });

  return {
    client,
    setAccessToken: (token: string | null) => {
      accessToken = token;
    },
  };
}

// 默认实例(单例)
export const typedSdk = createTypedClient();
