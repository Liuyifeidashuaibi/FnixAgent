# API / API Reference

> FnixAgent 的 Python SDK / Rust SDK / CLI / HTTP API 完整参考。

---

## 目录

- [Python SDK](#python-sdk)
- [Rust SDK](#rust-sdk)
- [TypeScript SDK](#typescript-sdk)
- [HTTP API](#http-api)
- [CLI](#cli)
- [MCP 协议](#mcp-协议)
- [OpenAPI 规范](#openapi-规范)

---

## Python SDK

**包名**:`fnixagent`
**最低 Python**:3.10
**安装**:`uv add fnixagent` 或 `pip install fnixagent`

### `Agent` 类

```python
from fnixagent import Agent, Config

agent = Agent(
    provider: str = "openai",
    model: str | None = None,
    config: Config | None = None,
    enable_memory: bool = False,
    enable_planning: bool = False,
    skills: list[str] | None = None,
    system_prompt: str | None = None,
)
```

#### 方法

##### `async run(prompt, *, skills=None, inputs=None, **kwargs) -> RunResult`

发送单轮对话。

```python
result = await agent.run(
    "用 Rust 写一个 hello world",
    skills=["code-review"],
    inputs={"language": "rust"},
    temperature=0.3,
)
```

##### `async chat(messages, **kwargs) -> Message`

多轮对话(自定义 messages)。

```python
from fnixagent import Message

result = await agent.chat([
    Message(role="system", content="你是 Rust 助手"),
    Message(role="user", content="解释所有权"),
    Message(role="assistant", content="..."),
    Message(role="user", content="举个例"),
])
```

##### `async stream(prompt, **kwargs) -> AsyncIterator[Chunk]`

流式返回。

```python
async for chunk in agent.stream("写一个长篇分析"):
    print(chunk.delta, end="", flush=True)
```

##### `async plan(goal, *, horizon="week", depth="mfp") -> Plan`

生成 STP / MFP 计划。

```python
plan = await agent.plan(
    "为 FnixAgent 添加 Docker 部署",
    horizon="week",     # week | day | session
    depth="mfp",        # mfp | stp | ktg
)
```

### `MemoryStore`

```python
from fnixagent.memory import MemoryStore, MemoryChunk

store = MemoryStore(path="~/.fnix/memory/store.sqlite")
await store.init()

# 添加
chunk = MemoryChunk(
    type="episodic",
    content="用户喜欢 Rust",
    importance=0.8,
    tags=["user:刘逸飞", "topic:language"],
)
chunk_id = await store.add(chunk)

# 检索
results = await store.search(
    query="系统编程语言",
    k=10,
    filter={"type": ["episodic", "core"]},
)

# 获取
chunk = await store.get(chunk_id)

# 删除
await store.delete(chunk_id)
```

### `Skill` 类

```python
from fnixagent import Skill

skill = await Skill.load("code-review")

result = await skill.run(
    inputs={"diff": "...", "language": "python"},
    agent=agent,   # 传入 agent 作为执行器
)

print(result.output["verdict"])
```

### `LLMClient` 抽象

```python
from fnixagent.llm import LLMClient

class MyCustomLLM(LLMClient):
    async def generate(self, prompt: str, **kwargs) -> LLMResult:
        ...

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[Chunk]:
        ...
```

---

## Rust SDK

**Crate**:`fnixagent-sdk`
**最低 Rust**:1.75

```toml
# Cargo.toml
[dependencies]
fnixagent-sdk = "0.5"
```

### 主 API

```rust
use fnixagent_sdk::{Agent, AgentConfig, Message};

#[tokio::main]
async fn main-> Result<(), Box<dyn std::error::Error>> {
    let agent = Agent::new(AgentConfig {
        provider: "local-llm".into(),
        model: Some("qwen2.5-coder:7b".into()),
        ..Default::default()
    })?;

    let response = agent.run("用 Rust 写 hello world").await?;
    println!("{}", response.text);

    Ok(())
}
```

### 流式

```rust
use futures::StreamExt;

let mut stream = agent.stream("写一篇长文").await?;
while let Some(chunk) = stream.next().await {
    print!("{}", chunk?.delta);
}
```

### 记忆

```rust
use fnixagent_sdk::memory::{MemoryStore, MemoryChunk, MemoryType};

let store = MemoryStore::new("~/.fnix/memory/store.sqlite").await?;
store.init().await?;

let chunk = MemoryChunk::new(MemoryType::Episodic, "用户喜欢 Rust")
    .with_importance(0.8);
let id = store.add(chunk).await?;

let results = store.search("系统编程语言", 10).await?;
```

---

## TypeScript SDK

**包**:`@fnixagent/sdk`

```bash
pnpm add @fnixagent/sdk
```

```typescript
import { Agent, Message } from '@fnixagent/sdk';

const agent = new Agent({
  provider: 'openai',
  model: 'gpt-4o',
});

const result = await agent.run('用 TypeScript 写 hello world');
console.log(result.text);
```

### React Hooks

```typescript
import { useAgent, useStreamingChat } from '@fnixagent/sdk/react'

function ChatPanel{
  const agent = useAgent({ provider: 'local-llm' })
  const { messages, send, isStreaming } = useStreamingChat(agent)

  return (
    <>
      {messages.map(m => <Message key={m.id} {...m} />)}
      <input
        onSubmit={(text) => send(text)}
        disabled={isStreaming}
      />
    </>
  )
}
```

---

## HTTP API

**Base URL**:`http://127.0.0.1:7891`
**协议**:HTTP/1.1 + JSON
**鉴权**:Token(可选,见 `/v1/auth/token`)

### `GET /v1/health`

```json
{ "status": "ok", "version": "0.5.0", "uptime_seconds": 3600 }
```

### `POST /v1/chat`

```bash
curl -X POST http://127.0.0.1:7891/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "用 Rust 写 hello world",
    "provider": "openai",
    "model": "gpt-4o",
    "temperature": 0.3
  }'
```

```json
{
  "id": "resp_abc123",
  "text": "fn main{ println!(\"Hello, world!\"); }",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 18,
    "total_tokens": 30
  },
  "finish_reason": "stop"
}
```

### `POST /v1/chat/stream` (SSE)

```
data: {"delta": "fn "}
data: {"delta": "main"}
data: {"delta": "{\n"}
...
data: [DONE]
```

### `POST /v1/memory/add`

```json
{
  "type": "episodic",
  "content": "用户喜欢 Rust",
  "importance": 0.8,
  "tags": ["user:刘逸飞"]
}
```

返回:

```json
{ "id": "mem_2026_08_17_001" }
```

### `POST /v1/memory/search`

```json
{
  "query": "系统编程语言",
  "k": 10,
  "filter": { "type": ["episodic"] }
}
```

### `POST /v1/skill/run`

```json
{
  "skill": "code-review",
  "inputs": { "diff": "...", "language": "python" }
}
```

### `GET /v1/skills`

列出已安装 Skill。

### `POST /v1/key/set`

```json
{ "provider": "openai", "mode": "keychain" }
```

弹出 UI 提示用户输入 Key(从不接受 HTTP body 直接传 Key)。

### `DELETE /v1/key/{provider}`

删除 Key。

### `GET /v1/metrics`

Prometheus 格式。

---

## CLI

**安装**:`fnixagent` 命令

### 全局选项

```bash
fnix [OPTIONS] <COMMAND>

Options:
  --config <PATH>     配置文件路径
  --log-level <LEVEL>  debug|info|warn|error
  --offline            强制本地 LLM
  --no-color           禁用 ANSI 颜色
  -h, --help           帮助
  -V, --version        版本
```

### 子命令

#### `fnix start`

启动 agentd。

```bash
fnix start [--foreground] [--port 7891]
```

#### `fnix stop`

停止 agentd。

#### `fnix prompt <TEXT>`

无 UI 模式发送 prompt。

```bash
fnix prompt "用 Rust 写 hello world"
```

#### `fnix key set|get|list|delete|export|import`

管理 API Key。

```bash
fnix key set --provider=openai
fnix key list
fnix key export --mode=encrypted --output ~/keystore.enc
fnix key import --input ~/keystore.enc
```

#### `fnix memory`

```bash
fnix memory add --type=episodic --content="..." --importance=0.8
fnix memory search "query"
fnix memory get <id>
fnix memory delete <id>
fnix memory list [--type=episodic]
fnix memory export --output=memories.zip
fnix memory rebuild-index
```

#### `fnix skill`

```bash
fnix skill list
fnix skill install <name>
fnix skill show <name>
fnix skill run <name> --inputs '{"k": "v"}'
fnix skill test <name>
fnix skill validate <name>
fnix skill reload <name>
```

#### `fnix doctor`

诊断。

```bash
fnix doctor              # 检查环境
fnix doctor --fix        # 自动修复
fnix doctor --collect-logs  # 收集日志包
```

#### `fnix update`

```bash
fnix update
fnix update --to v0.5.0
fnix update --check
```

#### `fnix backup|restore`

```bash
fnix backup --output ~/backup.tar.gz
fnix restore --input ~/backup.tar.gz
```

---

## MCP 协议

FnixAgent 既是 MCP **客户端**(消费其他 MCP 服务)也是 MCP **服务端**(暴露自己的能力)。

### 客户端:连接其他 MCP Server

```yaml
# config/agentd.yaml
integrations:
  mcp_servers:
    filesystem:
      command: npx
      args: ['-y', '@modelcontextprotocol/server-filesystem', '/Users/me']
      transport: stdio
    github:
      url: https://api.githubcopilot.com/mcp/
      transport: http
```

### 服务端:暴露 FnixAgent

```bash
fnix mcp serve --port 7892
```

其他 MCP 客户端(如桌面 MCP 客户端)可连接:

```json
{
  "mcpServers": {
    "fnixagent": {
      "command": "fnix",
      "args": ["mcp", "serve", "--port", "7892"]
    }
  }
}
```

可被调用的工具:

- `fnixagent.chat`
- `fnixagent.memory.search`
- `fnixagent.memory.add`
- `fnixagent.skill.run`
- `fnixagent.plan.generate`

---

## OpenAPI 规范

完整 OpenAPI 3.1 规范见 [`openapi.json`](../../openapi.json)。

可用工具:

- Swagger UI(本仓库):`make openapi-ui`
- Postman:导入 `openapi.json`
- 代码生成:`openapi-generator-cli generate -i openapi.json -g python`

---

## 错误码 / Error Codes

| 状态码 | 含义                |
| ------ | ------------------- |
| 200    | 成功                |
| 400    | 请求参数错误        |
| 401    | 未授权 / Token 无效 |
| 403    | 鉴权失败            |
| 404    | 资源不存在          |
| 409    | 冲突(版本号、并发)  |
| 422    | 业务规则校验失败    |
| 429    | 速率限制            |
| 500    | 内部错误            |
| 503    | agentd 未运行       |

错误响应:

```json
{
  "error": {
    "code": "invalid_input",
    "message": "diff 不能为空",
    "field": "diff"
  }
}
```

错误码定义见 `src/fnixagent/errors.py`。

---

## 版本兼容 / Versioning

- HTTP API 走 SemVer:`/v1/` 不会破坏
- SDK 走 SemVer:minor 可加方法,major 才破坏
- 内部 Python 模块**不**保证稳定

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.
