# `@fnixagent/protocol` — 跨进程契约(单源真相)

> 所有跨进程通信的 schema / 类型 / 常量的**单一来源**。
> 任何对 IPC 协议的修改必须先改这里,然后 codegen 到各语言。

---

## 为什么需要 protocol 包?

FnixAgent 涉及 4 种语言 / 3 类 IPC 边界:

| 边界 | 语言 A | 语言 B | 协议 |
| --- | --- | --- | --- |
| WebView ↔ Tauri Core | TypeScript | Rust | Tauri IPC |
| Tauri Core ↔ Python agentd | Rust | Python | stdio JSON-RPC |
| Python agentd ↔ fnix-local | Python | Rust | stdio JSON-RPC |
| Python ↔ HTTP API Server | Python | HTTP/JSON | OpenAPI 3.1 |

**没有统一 schema 会导致**:

- ❌ 字段命名不一致 (camelCase vs snake_case)
- ❌ 类型丢失 (Python int → Rust i64?)
- ❌ 协议版本不同步
- ❌ 文档与代码分离

`@fnixagent/protocol` 用 **JSON Schema** + **代码生成** 解决这一切。

---

## 目录结构

```
packages/protocol/
├── schemas/                  # JSON Schema (单源真相)
│   ├── ipc/
│   │   ├── v1/
│   │   │   ├── chat_request.json
│   │   │   ├── chat_response.json
│   │   │   ├── memory_add_request.json
│   │   │   ├── memory_search_request.json
│   │   │   └── ...
│   │   └── common/
│   │       ├── error.json
│   │       └── pagination.json
│   ├── openapi/
│   │   └── v1.yaml            # HTTP API 规范
│   └── mcp/
│       └── v1.json            # MCP 协议 schema
├── openapi/                  # 生成的 OpenAPI 客户端
│   └── python/
└── README.md
```

---

## Schema 约定

### 1. 命名

- Schema 文件:`<domain>_<action>_<v>.json`
- 顶层字段:`snake_case`
- 枚举:`UPPER_SNAKE_CASE`
- 协议版本:`v1`, `v2`, ...(URL 形式)

### 2. 必填字段

```json
{
  "type": "object",
  "required": ["id", "method", "params"],
  "properties": {
    "id": { "type": "string", "format": "uuid" },
    "method": { "type": "string", "minLength": 1 },
    "params": { "type": "object" },
    "jsonrpc": { "type": "string", "const": "2.0" }
  }
}
```

### 3. 错误码

```json
{
  "type": "object",
  "required": ["code", "message"],
  "properties": {
    "code": {
      "type": "integer",
      "enum": [-32700, -32600, -32601, -32602, -32603, -32001, -32002]
    },
    "message": { "type": "string", "minLength": 1 },
    "data": { "type": "object" }
  }
}
```

错误码定义见 `schemas/ipc/common/error_codes.md`。

---

## 代码生成

```bash
# 安装
pnpm add -D @fnixagent/protocol-codegen

# 生成 TypeScript 类型
pnpm codegen:ts

# 生成 Python 模型 (Pydantic)
pnpm codegen:py

# 生成 Rust 类型
pnpm codegen:rust

# 生成全部
pnpm codegen:all
```

输出到:

```
apps/workbench/src/types/protocol/        # TS
src/fnixagent/protocol/                   # Python
src-tauri/src/protocol/                   # Rust
```

### 生成的代码示例

#### TypeScript

```typescript
// 自动生成
export interface ChatRequest {
  prompt: string
  provider?: string
  model?: string
  temperature?: number
  max_tokens?: number
  stream?: boolean
}

export interface ChatResponse {
  id: string
  text: string
  usage: {
    input_tokens: number
    output_tokens: number
    total_tokens: number
  }
  finish_reason: 'stop' | 'length' | 'tool_use'
}
```

#### Python (Pydantic)

```python
# 自动生成
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    prompt: str
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=100000)
    stream: bool = False

class ChatResponse(BaseModel):
    id: str
    text: str
    usage: TokenUsage
    finish_reason: Literal["stop", "length", "tool_use"]
```

#### Rust (serde)

```rust
// 自动生成
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatRequest {
    pub prompt: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u32>,
    #[serde(default)]
    pub stream: bool,
}
```

---

## 版本管理

- `schemas/ipc/v1/` 不可破坏性变更
- 新增字段:`minor` 升级,老客户端忽略
- 重命名字段:`major` 升级,新增 `v2/`
- CI 拒绝:删除已发布版本的 schema

`.github/workflows/protocol-compat.yml`:

```yaml
- name: Check schema backward compat
  run: |
    npx @apidevtools/json-schema-diff \
      packages/protocol/schemas/ipc/v1/*.json \
      origin/main --error
```

---

## 测试

### Schema 验证

```bash
pnpm test:schema
# 用 ajv 校验所有 *.json schema 合法
```

### 跨语言一致性

```bash
pnpm test:roundtrip
# 生成 → 序列化 → 反序列化 → 比对
# 在 TS / Python / Rust 三端都跑
```

### 兼容性

```bash
pnpm test:compat
# 用 v0.4 客户端发请求,v0.5 服务端能正确响应
# 用 v0.5 客户端发请求,v0.4 服务端能 graceful fallback
```

---

## 编写新协议

1. 在 `schemas/ipc/v1/` 新建 `<domain>_<action>.json`
2. 跑 `pnpm codegen:all`
3. 在生成代码中加单元测试
4. 在 `docs/adr/` 加 ADR(如架构决策)
5. 更新 `API.md` 与 `docs/INTEGRATIONS.md`

---

## 参考 / References

- [JSON Schema 规范](https://json-schema.org/)
- [OpenAPI 3.1 规范](https://spec.openapis.org/oas/v3.1.0)
- [JSON-RPC 2.0 规范](https://www.jsonrpc.org/specification)
- [MCP 协议](https://modelcontextprotocol.io/)

---

© 2024-2026 FnixAgent. All Rights Reserved.