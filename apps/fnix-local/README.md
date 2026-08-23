# `fnix-local` — Rust 本地沙箱 sidecar

> 本地工具执行的最后一道防线。提供工作区索引、代码符号检索、文件读取和
> 受限命令执行能力，所有端点（除 `/health`）均需通过能力令牌认证。

---

## 它是什么?

`fnix-local` 是一个用 Rust (axum 0.8) 编写的 HTTP sidecar 进程，
作为 Python `agentd` 的本地伴侣服务运行。

核心职责:

- **工作区索引** — 遍历代码目录，提取符号摘要，持久化为 PDG summary
- **上下文检索** — 基于符号名称的朴素匹配，返回相关代码片段
- **受限命令执行** — 黑名单过滤 + 超时熔断 + 路径逃逸防护
- **文件读取** — 支持偏移/分页，路径逃逸拦截
- **能力令牌认证** — fail-closed，无令牌则拒绝一切访问

---

## 进程模型

```
Tauri Desktop Shell
    │
    │ spawn (env: FNIX_CAPABILITY_TOKEN)
    ├── fnix-local (Rust, axum HTTP :8710)
    │       │
    │       │ x-fnix-capability header 验证
    │       │
    │       ├── POST /v1/index   — 工作区索引
    │       ├── GET  /v1/context — 符号检索
    │       ├── POST /v1/run     — 命令执行
    │       └── GET  /v1/read    — 文件读取
    │
    └── Python agentd (FastAPI :8000)
            │
            │ HTTP → fnix-local (携带 capability token)
```

---

## 安全模型

### 能力令牌 (Capability Token)

所有端点（除 `/health`）都需要 `x-fnix-capability` header 匹配本地能力令牌。

令牌解析优先级（fail-closed，永不返回空值）:

1. 环境变量 `FNIX_CAPABILITY_TOKEN`（由 Tauri Shell 注入）
2. `~/.fnix/local_capability_token` 文件（持久化，供共存的 agentd 发现）
3. 自动生成 UUIDv4 并持久化到上述文件

> **注意**: 当前使用直接字符串比较。UUIDv4 携带 122 位熵，足以抵御猜测攻击。

### 命令执行安全

`POST /v1/run` 采用**黑名单 + 路径逃逸防护**策略（非白名单）:

- 拦截危险模式: `rm -rf /`, `rm -rf \\`, `del /f`, `format`, `mkfs`, `shutdown`, `reboot`, `../`, `..\\`
- 超时上限 600 秒（可配置，默认 60s）
- 工作目录必须在工作区内（canonicalize + strip_prefix 校验）

### 文件读取安全

`GET /v1/read` 通过 `safe_join` 防止路径遍历攻击:

- 工作区路径 canonicalize 后作为根
- 请求路径 canonicalize 后必须以根为前缀

---

## API 端点

| 端点          | 方法 | 描述                 | 认证     |
| ------------- | ---- | -------------------- | -------- |
| `/health`     | GET  | 健康检查             | 无       |
| `/v1/index`   | POST | 索引工作区           | 能力令牌 |
| `/v1/context` | GET  | 查询符号/上下文      | 能力令牌 |
| `/v1/run`     | POST | 执行 shell 命令      | 能力令牌 |
| `/v1/read`    | GET  | 读取文件（支持分页） | 能力令牌 |

### 索引示例

```bash
curl -X POST http://127.0.0.1:8710/v1/index \
  -H "x-fnix-capability: <token>" \
  -H "Content-Type: application/json" \
  -d '{"workspace": "/path/to/project", "force": false}'
```

响应:

```json
{
  "ok": true,
  "session_id": "a1b2c3d4e5f6a1b2",
  "workspace": "/path/to/project",
  "stats": {
    "total_files": 120,
    "indexed_files": 45,
    "skipped_files": 75,
    "total_symbols": 38,
    "duration_sec": 0.12
  }
}
```

### 上下文查询示例

```bash
curl "http://127.0.0.1:8710/v1/context?workspace=/path/to/project&query=login&top_k=8" \
  -H "x-fnix-capability: <token>"
```

### 命令执行示例

```bash
curl -X POST http://127.0.0.1:8710/v1/run \
  -H "x-fnix-capability: <token>" \
  -H "Content-Type: application/json" \
  -d '{"workspace": "/path/to/project", "command": "cargo test", "timeout": 120}'
```

---

## 配置

通过环境变量配置（无配置文件）:

| 变量                    | 默认值                            | 说明         |
| ----------------------- | --------------------------------- | ------------ |
| `FNIX_LOCAL_HOST`       | `127.0.0.1`                       | 监听地址     |
| `FNIX_LOCAL_PORT`       | `8710`                            | 监听端口     |
| `FNIX_CAPABILITY_TOKEN` | 自动生成                          | 能力令牌     |
| `FNIX_HOME`             | `~/.fnix`                         | 令牌文件目录 |
| `RUST_LOG`              | `fnix_local=info,tower_http=warn` | 日志级别     |

CORS 白名单固定为本地源:
`http://127.0.0.1:5175`, `http://localhost:5175`,
`http://127.0.0.1:1420`, `http://localhost:1420`,
`tauri://localhost`, `https://tauri.localhost`

---

## 索引策略

索引器遍历工作区目录树（使用 `walkdir`），跳过:
`.git/`, `node_modules/`, `target/`, `dist/`

对以下扩展名的文件提取符号:
`rs`, `py`, `ts`, `tsx`, `js`, `jsx`, `go`, `java`, `c`, `cpp`, `h`, `cs`, `md`, `json`, `yaml`, `yml`, `toml`

符号提取规则: 扫描前 200 行，匹配 `fn `, `pub fn `, `class `, `def `, `export function `, `export async function ` 开头的行。最多保留 150 个符号。

索引结果持久化到 `<workspace>/.fnix/index/pdg_summary.json`。

---

## 开发

```bash
# 开发运行
cargo run

# 测试
cargo test

# Release 构建
cargo build --release
# 产物: target/release/fnix-local (Linux/Mac) 或 fnix-local.exe (Win)
```

---

## 依赖

```toml
[dependencies]
axum = "0.8"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
tower-http = { version = "0.6", features = ["cors"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
uuid = { version = "1", features = ["v4"] }
walkdir = "2"
```

---

## 已知局限

- **黑名单 vs 白名单**: 命令执行使用黑名单而非白名单，无法完全防止新型攻击模式。
  未来可考虑迁移到白名单 + 路径正则方案。
- **无资源限额**: 当前未实现 setrlimit / seccomp 等系统级资源限制。
  超时是唯一的资源防护手段。
- **朴素匹配**: 上下文检索使用 `contains` 字符串匹配，非语义向量检索。
  适合小规模工作区，大规模代码库需替换为向量索引方案。
- **单实例**: 索引存储在进程内存 + 本地 JSON 文件，不支持多实例共享。

---

## 参考

- [axum](https://github.com/tokio-rs/axum)
- [tokio](https://tokio.rs/)
- [walkdir](https://docs.rs/walkdir)
- OpenAPI spec: `packages/protocol/openapi/fnix-local-v1.yaml`
- Python fallback: `src/fnixagent/local/sidecar_app.py`

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.
