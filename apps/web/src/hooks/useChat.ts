import { useCallback, useRef, useState } from 'react';
import { sdk, type ChatChunk, type EvolveResponse } from '@fnixagent/sdk';

/** 对话模式 */
export type ChatMode = 'stream' | 'evolve';

/** 工具调用记录 */
export interface ToolCallRecord {
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
  success?: boolean;
}

/** 单条消息 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  /** 流式标记:正在输出中 */
  streaming?: boolean;
  /** 工具调用列表(assistant 消息可附带) */
  toolCalls?: ToolCallRecord[];
  /** 概念路径(evolve 模式) */
  conceptPath?: string[];
  /** 耗时(ms) */
  durationMs?: number;
  /** 错误信息 */
  error?: string;
  /** 时间戳 */
  ts: number;
}

/** 生成简单唯一 ID */
function genId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * 对话 Hook — 管理消息列表 / 流式输出 / 自进化 / 错误重试
 *
 * 模式:
 *   - "stream"  : 调用 /api/v1/chat/stream (NDJSON 流式)
 *   - "evolve"  : 调用 /api/v1/chat/evolve (一次性返回完整飞轮闭环结果)
 */
export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: '你好!我是 fnixagent,你的智能办公助手。有什么可以帮你的?',
      ts: Date.now(),
    },
  ]);
  const [mode, setMode] = useState<ChatMode>('stream');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionIdRef = useRef<number | undefined>(undefined);
  // 保留最后一条用户输入,便于失败后重试
  const lastInputRef = useRef<string>('');

  /** 追加/更新消息(按 id) */
  const upsertMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === msg.id);
      if (idx === -1) return [...prev, msg];
      const next = [...prev];
      next[idx] = { ...next[idx], ...msg };
      return next;
    });
  }, []);

  /** 流式发送(NDJSON) */
  const sendStream = useCallback(
    async (userInput: string) => {
      const assistantId = genId();
      // 先插入空的 assistant 消息占位
      upsertMessage({
        id: assistantId,
        role: 'assistant',
        content: '',
        streaming: true,
        ts: Date.now(),
      });

      let buffer = '';
      const toolCalls: ToolCallRecord[] = [];
      try {
        for await (const chunk of sdk.chat.stream({
          session_id: sessionIdRef.current,
          user_input: userInput,
        })) {
          handleChunk(chunk, assistantId, (text) => {
            buffer += text;
            upsertMessage({
              id: assistantId,
              role: 'assistant',
              content: buffer,
              streaming: !chunk.done,
              toolCalls: toolCalls.length ? toolCalls : undefined,
              ts: Date.now(),
            });
          }, (tc) => toolCalls.push(tc));
        }
        // 流结束
        upsertMessage({
          id: assistantId,
          role: 'assistant',
          content: buffer || '(无内容)',
          streaming: false,
          toolCalls: toolCalls.length ? toolCalls : undefined,
          ts: Date.now(),
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        upsertMessage({
          id: assistantId,
          role: 'assistant',
          content: buffer,
          streaming: false,
          error: msg,
          ts: Date.now(),
        });
        setError(msg);
      }
    },
    [upsertMessage],
  );

  /** 自进化发送(一次性) */
  const sendEvolve = useCallback(
    async (userInput: string) => {
      const assistantId = genId();
      upsertMessage({
        id: assistantId,
        role: 'assistant',
        content: '⟳ 自进化飞轮处理中...',
        streaming: true,
        ts: Date.now(),
      });
      try {
        const resp: EvolveResponse = await sdk.chat.evolve({
          session_id: sessionIdRef.current,
          user_input: userInput,
        });
        if (!resp.success) {
          throw new Error(resp.message || '自进化处理失败');
        }
        const d = resp.data;
        upsertMessage({
          id: assistantId,
          role: 'assistant',
          content: d.answer || '(无答案)',
          streaming: false,
          toolCalls: d.tool_calls?.length ? d.tool_calls : undefined,
          conceptPath: d.concept_path?.length ? d.concept_path : undefined,
          durationMs: d.duration_ms,
          ts: Date.now(),
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        upsertMessage({
          id: assistantId,
          role: 'assistant',
          content: '',
          streaming: false,
          error: msg,
          ts: Date.now(),
        });
        setError(msg);
      }
    },
    [upsertMessage],
  );

  /** 处理一个流式分片 */
  function handleChunk(
    chunk: ChatChunk,
    _id: string,
    appendText: (t: string) => void,
    pushTool: (tc: ToolCallRecord) => void,
  ) {
    switch (chunk.chunk_type) {
      case 'thought':
        // 思考步骤以引用块形式追加
        appendText(`> 💭 ${chunk.content}\n\n`);
        break;
      case 'action':
        // 工具调用 — 加入 toolCalls,文本流里也标注
        pushTool({ name: chunk.content });
        appendText(`🔧 *调用工具: ${chunk.content}*\n\n`);
        break;
      case 'text':
        appendText(chunk.content);
        break;
      case 'error':
        appendText(`\n\n⚠️ 错误: ${chunk.content}`);
        break;
    }
  }

  /** 发送消息(根据当前模式分发) */
  const sendMessage = useCallback(
    async (userInput: string) => {
      const text = userInput.trim();
      if (!text || isStreaming) return;
      setError(null);
      lastInputRef.current = text;
      // 插入用户消息
      setMessages((prev) => [
        ...prev,
        { id: genId(), role: 'user', content: text, ts: Date.now() },
      ]);
      setIsStreaming(true);
      try {
        if (mode === 'evolve') {
          await sendEvolve(text);
        } else {
          await sendStream(text);
        }
      } finally {
        setIsStreaming(false);
      }
    },
    [isStreaming, mode, sendEvolve, sendStream],
  );

  /** 重试最后一条消息 */
  const retry = useCallback(async () => {
    if (!lastInputRef.current || isStreaming) return;
    // 移除最后一条 assistant 消息(可能是错误的)
    setMessages((prev) => {
      if (prev.length && prev[prev.length - 1].role === 'assistant') {
        return prev.slice(0, -1);
      }
      return prev;
    });
    await sendMessage(lastInputRef.current);
  }, [isStreaming, sendMessage]);

  /** 清空对话 */
  const clear = useCallback(() => {
    sessionIdRef.current = undefined;
    lastInputRef.current = '';
    setError(null);
    setMessages([
      {
        id: 'welcome',
        role: 'assistant',
        content: '你好!我是 fnixagent,你的智能办公助手。有什么可以帮你的?',
        ts: Date.now(),
      },
    ]);
  }, []);

  return {
    messages,
    mode,
    isStreaming,
    error,
    sendMessage,
    retry,
    clear,
    setMode,
    setSessionId: (id: number | undefined) => {
      sessionIdRef.current = id;
    },
  };
}
