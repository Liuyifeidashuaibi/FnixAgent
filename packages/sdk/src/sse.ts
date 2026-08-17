/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * fnixagent SSE 流式响应封装 — Phase P2-01
 *
 * 功能:
 *   ① 自动解析 text/event-stream 格式
 *   ② 提供 async generator 接口,逐事件 yield
 *   ③ 正确处理跨 chunk 的部分事件(TCP 分包边界)
 *   ④ 兼容 \n / \r\n / \r 三种行尾
 *   ⑤ streamChat():直接用 fetch 发起流式对话,解析 SSE 事件
 */
import type { createTypedClient } from './typed-client';

/**
 * SSE 事件
 *
 * 对应 SSE 规范中的一个 event 块(以空行分隔)。
 * - `event`: 事件类型(如 "message"、"thought"、"action")
 * - `data`: 事件数据(多行 data 字段以 \n 拼接)
 * - `id`: 事件 ID(用于断线重连 Last-Event-ID)
 */
export interface SSEEvent {
  event?: string;
  data: string;
  id?: string;
}

/**
 * 流式对话请求体(对应后端 ChatRequest schema)
 */
export interface StreamChatBody {
  /** 会话 ID(可选,不传则新建会话) */
  session_id?: number | null;
  /** 用户输入 */
  user_input: string;
  /** 上下文(可选) */
  context?: Record<string, unknown> | null;
}

/**
 * streamChat 依赖的外部上下文
 */
export interface StreamChatOptions {
  /** API 基地址(如 http://localhost:8000) */
  baseUrl: string;
  /** 获取当前 Access Token 的函数(用于鉴权) */
  getAccessToken: () => string | null;
  /** 可选的 AbortSignal,用于取消订阅 */
  signal?: AbortSignal;
}

/**
 * 解析单个 SSE 事件块(不含尾部空行)
 *
 * SSE 行格式:`field: value`(冒号后可有可选空格)
 * 支持字段:event / data / id / retry(忽略)
 * 以 `:` 开头的行为注释(忽略)
 * 多行 data 以 \n 拼接
 *
 * @returns 解析出的事件;若块内无有效内容则返回 null
 */
function parseSSEBlock(raw: string): SSEEvent | null {
  const lines = raw.split(/\r\n|\r|\n/);
  let event: string | undefined;
  const dataParts: string[] = [];
  let id: string | undefined;
  let hasContent = false;

  for (const line of lines) {
    // 空行在事件块内部不应出现(事件以空行分隔),但容错跳过
    if (line === '') continue;
    // 注释行
    if (line.startsWith(':')) continue;

    const colonIdx = line.indexOf(':');
    const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
    // 冒号后若有一个前导空格,需去掉(SSE 规范)
    let value = colonIdx === -1 ? '' : line.slice(colonIdx + 1);
    if (value.startsWith(' ')) value = value.slice(1);

    switch (field) {
      case 'event':
        event = value;
        hasContent = true;
        break;
      case 'data':
        dataParts.push(value);
        hasContent = true;
        break;
      case 'id':
        id = value;
        hasContent = true;
        break;
      case 'retry':
        // retry 字段用于指示客户端重连间隔,此处忽略
        break;
      default:
        // 未知字段:按规范忽略
        break;
    }
  }

  if (!hasContent) return null;
  return {
    event,
    data: dataParts.join('\n'),
    id,
  };
}

/**
 * 解析 SSE 流(从 Response.body 读取并逐事件 yield)
 *
 * 实现要点:
 *   - 维护缓冲区,仅在遇到完整事件(以空行分隔)时 yield
 *   - 正确处理 TCP 分包:chunk 边界可能落在事件中间,缓冲拼接后再解析
 *   - 兼容 \n / \r\n / \r 行尾;若缓冲区末尾是孤立 \r(可能是 \r\n 前半),
 *     保留到下一个 chunk 拼接后再处理
 *   - 流结束后 flush 残留缓冲区
 *
 * @param response fetch 返回的 Response(需有 body 可读流)
 *
 * 用法:
 *   ```ts
 *   const resp = await fetch(url);
 *   for await (const evt of parseSSEStream(resp)) {
 *     console.log(evt.event, evt.data);
 *   }
 *   ```
 */
export async function* parseSSEStream(
  response: Response,
): AsyncGenerator<SSEEvent> {
  if (!response.body) {
    throw new Error('SSE 流解析失败:Response.body 为空(环境不支持 ReadableStream)');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 若缓冲区以 \r 结尾,可能是 \r\n 的前半部分(跨 chunk),
      // 暂不处理末尾的 \r,保留到下次拼接
      let trailing = '';
      if (buffer.endsWith('\r')) {
        trailing = '\r';
        buffer = buffer.slice(0, -1);
      }

      // 标准化行尾:\r\n → \n,残余 \r → \n
      buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

      // 按空行(\n\n)分割为事件块
      const blocks = buffer.split('\n\n');
      // 最后一块是不完整的(无尾部 \n\n),保留到缓冲区
      buffer = (blocks.pop() ?? '') + trailing;

      for (const block of blocks) {
        const evt = parseSSEBlock(block);
        if (evt) yield evt;
      }
    }

    // flush decoder(写出残余字节)
    buffer += decoder.decode();

    // 处理残留缓冲区(流末尾可能有一个未以空行结尾的事件)
    if (buffer.length > 0) {
      buffer = buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
      const blocks = buffer.split('\n\n');
      for (const block of blocks) {
        const evt = parseSSEBlock(block);
        if (evt) yield evt;
      }
    }
  } finally {
    // 释放 reader 锁,允许外部 cancel 流
    try {
      reader.releaseLock();
    } catch {
      // reader 已被释放或取消,忽略
    }
  }
}

/**
 * 发起流式对话(SSE)
 *
 * 直接用 fetch 发起 POST 请求到 `/api/v1/chat/stream`,解析 SSE 事件流。
 * 不经过 openapi-fetch(因为 openapi-fetch 会缓冲整个响应,不支持流式)。
 *
 * @param typedClient 类型安全 client 实例(仅用于类型上下文,不实际调用)
 * @param body 请求体(自动注入 stream: true)
 * @param options baseUrl + getAccessToken + 可选 signal(用于取消)
 *
 * 用法:
 *   ```ts
 *   for await (const evt of streamChat(sdk, { user_input: '你好' }, opts)) {
 *     if (evt.event === 'message') {
 *       console.log(evt.data);
 *     }
 *   }
 *   ```
 */
export async function* streamChat(
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _typedClient: ReturnType<typeof createTypedClient>,
  body: StreamChatBody,
  options: StreamChatOptions,
): AsyncGenerator<SSEEvent> {
  const { baseUrl, getAccessToken, signal } = options;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };
  const token = getAccessToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const resp = await fetch(`${baseUrl}/api/v1/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`流式对话请求失败 ${resp.status}: ${text || resp.statusText}`);
  }
  if (!resp.body) {
    throw new Error('流式对话失败:服务端未返回可读流(检查是否支持 SSE)');
  }

  yield* parseSSEStream(resp);
}
