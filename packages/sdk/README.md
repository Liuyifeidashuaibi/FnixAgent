# `@fnixagent/sdk`

> FnixAgent 的官方 TypeScript SDK。
> 用于在 Node.js / 浏览器 / VS Code 扩展中集成 FnixAgent 能力。

---

## 安装

```bash
pnpm add @fnixagent/sdk
# 或
npm install @fnixagent/sdk
```

**前置**:

- Node.js 20+
- 浏览器:Chrome 100+, Firefox 100+, Safari 15+
- VS Code:1.85+

---

## 快速开始

```typescript
import { Agent } from '@fnixagent/sdk'

// 创建 agent
const agent = new Agent({
  provider: 'openai',
  model: 'gpt-4o',
  apiKey: process.env.OPENAI_API_KEY,
})

// 单轮对话
const result = await agent.run('用 TypeScript 写 hello world')
console.log(result.text)

// 流式
for await (const chunk of agent.stream('写一篇长文')) {
  process.stdout.write(chunk.delta)
}
```

---

## API 概览

### `Agent` 类

```typescript
new Agent(config: AgentConfig): Agent

interface AgentConfig {
  provider: 'openai' | 'anthropic' | 'deepseek' | 'ollama' | 'custom'
  model?: string
  apiKey?: string
  baseUrl?: string
  systemPrompt?: string
  temperature?: number
  maxTokens?: number
  enableMemory?: boolean
  enablePlanning?: boolean
  skills?: string[]
}
```

### 方法

| 方法 | 描述 |
| --- | --- |
| `run(prompt, options?)` | 单轮对话 |
| `stream(prompt, options?)` | 流式对话 |
| `chat(messages, options?)` | 多轮对话 |
| `plan(goal, options?)` | 生成 STP / MFP |
| `memory.add(chunk)` | 添加记忆 |
| `memory.search(query)` | 检索记忆 |
| `skill.run(name, inputs)` | 运行 Skill |
| `key.set(provider, key)` | 设置 API Key |
| `key.list()` | 列出已配置的 Key |

---

## React Hooks

```typescript
import { AgentProvider, useAgent, useChat, usePlan } from '@fnixagent/sdk/react'

function App() {
  return (
    <AgentProvider config={{ provider: 'ollama', model: 'qwen2.5-coder:7b' }}>
      <ChatPanel />
    </AgentProvider>
  )
}

function ChatPanel() {
  const agent = useAgent()
  const { messages, send, isStreaming, cancel } = useChat(agent)

  return (
    <div>
      {messages.map((m) => <Message key={m.id} {...m} />)}
      <input onSubmit={send} />
      {isStreaming && <button onClick={cancel}>取消</button>}
    </div>
  )
}
```

可用 hooks:

| Hook | 用途 |
| --- | --- |
| `useAgent()` | 拿到当前 Agent |
| `useChat(agent)` | 对话状态管理 |
| `usePlan(agent)` | 任务规划 |
| `useMemory(agent)` | 记忆操作 |
| `useSkills(agent)` | Skill 管理 |
| `useStreaming(agent)` | 流式响应 |

---

## VS Code 扩展

```typescript
// extension.ts
import * as vscode from 'vscode'
import { Agent } from '@fnixagent/sdk'
import { VscodeIntegration } from '@fnixagent/sdk/vscode'

export function activate(context: vscode.ExtensionContext) {
  const agent = new Agent({
    provider: 'openai',
    enableMemory: true,
  })

  const integration = new VscodeIntegration(agent, context)

  context.subscriptions.push(
    vscode.commands.registerCommand('fnixagent.review', () =>
      integration.reviewSelection()
    )
  )
}
```

---

## 浏览器(受限)

⚠️ 浏览器中不能直接连 LLM(API Key 会暴露),必须通过后端代理:

```typescript
import { Agent } from '@fnixagent/sdk'

const agent = new Agent({
  baseUrl: '/api/fnixagent',   // 后端代理
  provider: 'openai',
})

const result = await agent.run('hello')
```

后端代理参考 [`examples/12_headless_cli.py`](../../EXAMPLES.md#12-无-ui-命令行模式)。

---

## 类型定义

完整类型见 [API.md](../../API.md#typescript-sdk)。

自动生成,源文件在 `packages/protocol/schemas/`。

---

## 错误处理

```typescript
import { AgentError, RateLimitError, NetworkError } from '@fnixagent/sdk'

try {
  await agent.run('hello')
} catch (e) {
  if (e instanceof RateLimitError) {
    console.log('频率限制,等待', e.retryAfter, '秒')
  } else if (e instanceof NetworkError) {
    console.log('网络错误')
  } else if (e instanceof AgentError) {
    console.log('Agent 错误:', e.message, e.code)
  }
}
```

错误类型:

| 错误 | HTTP | 含义 |
| --- | --- | --- |
| `AgentError` | 500 | 通用 |
| `RateLimitError` | 429 | 速率限制 |
| `NetworkError` | 503 | 网络/agentd 未运行 |
| `AuthError` | 401 | API Key 错误 |
| `ValidationError` | 400 | 参数错误 |

---

## 测试

```bash
pnpm test
# 用 vitest
```

Mock:

```typescript
import { Agent } from '@fnixagent/sdk'

class MockAgent extends Agent {
  async run(prompt: string) {
    return { text: 'mock response', usage: { ... } }
  }
}
```

---

## 浏览器 polyfill

```typescript
// fetch / WebSocket / AbortController 在 Node 18+ 自带
// 不需要额外 polyfill
```

---

## 参考 / References

- [`API.md`](../../API.md)
- [`@fnixagent/protocol`](../protocol/README.md)
- [examples/](../../EXAMPLES.md)

---

© 2024-2026 FnixAgent. All Rights Reserved.