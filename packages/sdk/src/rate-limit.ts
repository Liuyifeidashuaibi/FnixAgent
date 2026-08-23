/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * fnixagent 速率限制感知重试拦截器 — Phase P2-01
 *
 * 功能:
 *   ① 429 响应:读取 Retry-After header,等待后重试
 *   ② 最大重试次数: 3(可配置)
 *   ③ 指数退避: 1s, 2s, 4s(与 Retry-After 取较大值)
 *   ④ 正确处理 POST 等带 body 的请求(缓存 body 文本用于重放)
 *
 * 兼容 openapi-fetch 中间件接口,可直接 `client.use(createRateLimitInterceptor())`。
 */

import type { Middleware } from 'openapi-fetch';

/** 默认最大重试次数 */
const DEFAULT_MAX_RETRIES = 3;

/** 指数退避基数(毫秒):1s, 2s, 4s */
const BACKOFF_BASE_MS = 1000;

/** 退避上限(毫秒),避免 Retry-After 过大时永久阻塞 */
const MAX_WAIT_MS = 60_000;

/**
 * 解析 Retry-After header
 *
 * Retry-After 可能为:
 *   - 整数(秒):"120"
 *   - HTTP 日期:"Wed, 21 Oct 2015 07:28:00 GMT"
 *
 * @returns 需要等待的毫秒数;无法解析时返回 0
 */
function parseRetryAfter(header: string | null): number {
  if (!header) return 0;
  // 尝试解析为秒数
  const seconds = Number(header);
  if (!Number.isNaN(seconds) && seconds >= 0) {
    return seconds * 1000;
  }
  // 尝试解析为 HTTP 日期
  const date = Date.parse(header);
  if (!Number.isNaN(date)) {
    return Math.max(0, date - Date.now());
  }
  return 0;
}

/** 延迟工具(可被 mock 测试) */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 计算第 N 次重试的等待时间
 *
 * 策略:取「指数退避」与「Retry-After」的较大值,但不超过上限。
 *
 * @param retryAfterMs Retry-After header 解析出的毫秒数
 * @param attempt 当前重试次数(0 基)
 */
function computeWaitMs(retryAfterMs: number, attempt: number): number {
  const backoff = BACKOFF_BASE_MS * Math.pow(2, attempt);
  return Math.min(Math.max(retryAfterMs, backoff), MAX_WAIT_MS);
}

/**
 * 创建速率限制感知重试拦截器
 *
 * @param maxRetries 最大重试次数(默认 3)
 * @returns openapi-fetch 中间件
 *
 * 用法:
 *   ```ts
 *   client.use(createRateLimitInterceptor());
 *   ```
 */
export function createRateLimitInterceptor(maxRetries: number = DEFAULT_MAX_RETRIES): Middleware {
  // 缓存每个请求的 body 文本(Request body 流只能消费一次,重试需重建请求)
  const bodyCache = new WeakMap<Request, string>();

  return {
    async onRequest({ request }) {
      // 对带 body 的请求,提前读取并缓存(clone 不影响原请求)
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        try {
          const clone = request.clone();
          bodyCache.set(request, await clone.text());
        } catch {
          // body 读取失败则不缓存,重放时降级为无 body
        }
      }
      return request;
    },

    async onResponse({ request, response }) {
      if (response.status !== 429) return response;

      let lastResponse = response;

      for (let attempt = 0; attempt < maxRetries; attempt++) {
        // 读取 Retry-After header
        const retryAfterMs = parseRetryAfter(
          lastResponse.headers.get('Retry-After') ??
            lastResponse.headers.get('retry-after'),
        );
        const waitMs = computeWaitMs(retryAfterMs, attempt);

        await sleep(waitMs);

        // 用缓存的 body 重建请求(Headers 不可变,需创建新 Request)
        const headers = new Headers(request.headers);
        const cachedBody = bodyCache.get(request) ?? null;
        const retryReq = new Request(request.url, {
          method: request.method,
          headers,
          body: cachedBody,
          redirect: request.redirect,
        });

        try {
          lastResponse = await fetch(retryReq);
        } catch {
          // 网络错误:继续退避重试
          continue;
        }

        // 非 429 则停止重试
        if (lastResponse.status !== 429) {
          break;
        }
      }

      return lastResponse;
    },
  };
}
