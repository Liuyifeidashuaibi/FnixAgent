# FnixAgent 智能办公 Agent · 项目开发文档

> 面向**学习/教育/办公**场景的智能 Agent,核心能力:论文文献检索、Word 编辑、格式转换、图表生成、PDF 生成、文档解析、学习辅助问答,基于「任务」实现端到端自动编排。
>
> 本文档涵盖:① 模块说明 · ② API 接口入参出参 · ③ 部署操作步骤。

---

## 一、项目概述

### 1.1 技术栈

| 层级 | 技术选型 |
|------|----------|
| Web 框架 | FastAPI 0.104 + Uvicorn |
| 数据校验 | Pydantic 2.5 / pydantic-settings |
| ORM | SQLAlchemy 2.0(DeclarativeBase) |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| 向量库 | Milvus(混合检索) |
| 对象存储 | MinIO |
| 搜索引擎 | Elasticsearch 8 |
| LLM | GLM / OpenAI / Qwen(OpenAI 兼容接口) |
| 鉴权 | JWT(HS256,纯标准库实现) |
| 容器化 | Docker / Docker Compose |
| 测试 | pytest + pytest-asyncio + FastAPI TestClient |

### 1.2 七层架构

```
① 交互层  →  ② 网关层  →  ③ 调度中枢  →  ④ 核心引擎  →  ⑤ 业务能力  →  ⑥ 存储层  →  ⑦ 基础设施
```

核心设计原则:**底层算法引擎与业务能力解耦**——`core/` 不 import `business/`,业务以「工具」形式注册,引擎只认 Tool Protocol。

---

## 二、模块说明

### 2.1 目录结构

```
FNIXAGENT/
├── src/fnixagent/           # 主源码
│   ├── main.py                # FastAPI 主入口
│   ├── core/                  # 核心算法引擎(领域无关,可复用)
│   │   ├── config.py          # 全局配置(CoreConfig 数据类)
│   │   ├── types.py           # 领域类型(Message/Entity/ToolCall/LLMResponse)
│   │   ├── exceptions.py      # 统一异常体系
│   │   ├── text.py            # 文本工具(token 估算/分句)
│   │   ├── mathops.py         # 数值计算(向量运算/统计)
│   │   ├── llm/               # LLM 基础服务
│   │   ├── memory/            # 三层记忆引擎
│   │   ├── tools/             # 工具执行平台
│   │   ├── reasoning/         # 规划与推理引擎
│   │   ├── reflection/        # 反思纠错引擎
│   │   ├── security/          # 合规与安全引擎
│   │   ├── orchestrator/      # Agent 调度中枢
│   │   ├── prompt/            # Prompt 管理引擎
│   │   └── retrieval/         # 向量检索引擎
│   ├── api/                   # HTTP API 层
│   │   ├── schemas/models.py  # Pydantic 请求/响应模型
│   │   └── routers/           # 路由(auth/chat/documents/tasks/tools)
│   ├── business/              # 业务能力层(Office 领域工具)
│   │   ├── search/            # 论文检索(arXiv/Semantic Scholar)
│   │   ├── word/              # Word 编辑
│   │   └── converter/         # 格式转换
│   ├── services/              # 服务层(桥接核心引擎与 API)
│   │   ├── service.py         # AgentScheduler 构建与单例
│   │   └── storage.py         # 业务存储(User/Document/Task/ApiKey Store)
│   ├── adapters/              # 基础设施适配器
│   │   ├── db/postgres.py     # PostgreSQL 适配器
│   │   └── cache/redis.py     # Redis 适配器
│   └── models/                # 数据模型
│       ├── db/models.py       # SQLAlchemy ORM 实体
│       └── domain/entities.py # 领域对象(dataclass)
├── config/                    # 配置文件
│   ├── settings.yaml          # 全局配置
│   ├── prompts/*.yaml         # Prompt 模板
│   └── security/*.yaml        # 安全配置(敏感词)
├── tests/                     # 测试
├── deploy/docker/             # 部署(Dockerfile)
├── docker-compose.yml         # 容器编排
├── Makefile                   # 构建命令
├── requirements.txt           # 依赖清单
└── .env.example               # 环境变量模板
```

### 2.2 核心引擎模块(`core/`)

#### 2.2.1 LLM 基础服务(`core/llm/`)

| 文件 | 职责 | 关键类/函数 |
|------|------|-------------|
| `base.py` | LLM Provider 抽象基类 | `BaseLLMProvider`(抽象方法 `_do_chat`/`_do_stream`)、`LLMRequest` |
| `router.py` | 多模型路由 | `LLMRouter`(加权/轮询/故障转移策略)、`RouteStrategy` 枚举 |
| `providers/openai_compat.py` | OpenAI 兼容 Provider | `OpenAICompatibleProvider`、`GLMProvider`、`OpenAIProvider`、`QwenProvider`、`MockLLMProvider` |
| `cache.py` | 响应缓存 | `LLMCache`(基于 prompt 哈希) |
| `circuit.py` | 熔断器 | `CircuitBreaker`(closed/open/half-open 三态) |
| `rate_limiter.py` | 限流器 | `TokenBucketRateLimiter`(令牌桶算法) |
| `billing.py` | Token 计费 | `BillingTracker`(按模型计价) |

**路由策略**:
- `WEIGHTED`:按权重分配(默认)
- `ROUND_ROBIN`:轮询
- `FAILOVER`:主备切换

**Provider 优先级**:GLM(weight=2.0) > OpenAI(weight=1.0) > Qwen(weight=1.0) > Mock(无 API Key 时回退)

#### 2.2.2 三层记忆引擎(`core/memory/`)

| 文件 | 层级 | 职责 | 关键类 |
|------|------|------|--------|
| `short_term.py` | 短期 | 滑动窗口对话历史(token 预算裁剪) | `ShortTermMemory`(`add`/`get_messages`/`clear`) |
| `long_term.py` | 长期 | 向量化语义记忆(跨会话检索) | `LongTermMemory`(`add`/`search`/`cleanup_expired`) |
| `entity.py` | 实体 | 结构化业务事实(用户画像/论文/项目) | `EntityMemory`(`upsert`/`get`/`list_by_type`) |
| `manager.py` | 统一管理 | 组合三层,注入 Prompt | `MemoryManager`(`save`/`load_context`/`search`) |

**安全(OWASP ASI06 记忆投毒防护)**:
- 实体类型白名单:`user_profile`/`paper`/`project`/`note`/`task`/`document`/`knowledge`
- 字段白名单:每种实体类型仅允许预定义字段

#### 2.2.3 工具执行平台(`core/tools/`)

| 文件 | 职责 | 关键类/函数 |
|------|------|-------------|
| `protocol.py` | 工具协议 | `ToolMetadata`(name/description/category/input_schema)、`validate_arguments()` |
| `registry.py` | 工具注册中心 | `ToolRegistry`(`register`/`get`/`has`/`list_tools`/`list_for_llm`/`unregister`) |
| `executor.py` | 工具执行器 | `ToolExecutor`(`execute(ToolCall) -> ToolResult`,DAG 编排) |
| `sandbox/code_sandbox.py` | 代码沙箱 | 隔离执行用户代码 |
| `sandbox/policy.py` | 沙箱策略 | 资源限制/权限分级 |

**工具权限分级**:`LOW`(只读)/`MIDDLE`(读写)/`HIGH`(系统操作)

#### 2.2.4 规划与推理引擎(`core/reasoning/`)

| 文件 | 模式 | 职责 | 关键类 |
|------|------|------|--------|
| `react.py` | ReAct | 思考-行动-观察循环 | `ReActReasoning` |
| `plan_execute.py` | Plan & Execute | 先规划再分步执行 | `PlanExecuteReasoning` |
| `self_reflect.py` | Self-Reflect | 自我反思校验 | `SelfReflectReasoning` |
| `selector.py` | 自动选择 | 依据任务复杂度选模式 | `ReasoningSelector` |
| `base.py` | 抽象基类 | 统一接口 | `BaseReasoning` |

**选择策略**:
- 简单任务(单工具)→ ReAct
- 复杂任务(多工具/多步)→ Plan & Execute
- 高质量要求 → 叠加 Self-Reflect

#### 2.2.5 反思纠错引擎(`core/reflection/`)

| 文件 | 职责 | 关键类 |
|------|------|--------|
| `validator.py` | 结果校验 | `ResultValidator`(完整性/逻辑性/安全性检查) |
| `replanner.py` | 失败重规划 | `Replanner`(`replan()`,最多 `max_replans` 次) |

#### 2.2.6 合规与安全引擎(`core/security/`)

| 文件 | 职责 | 关键类 |
|------|------|--------|
| `engine.py` | 安全引擎入口 | `SecurityEngine`(`check_input`/`review_output`) |
| `sensitive.py` | 敏感词检测 | `SensitiveDetector`(基于 `config/security/sensitive_words.yaml`) |
| `injection.py` | 注入防护 | `InjectionGuard`(Prompt Injection 检测) |
| `moderation.py` | 内容审核 | `ContentModerator`(违规内容识别) |
| `desensitize.py` | 脱敏 | `Desensitizer`(手机号/邮箱/身份证脱敏) |

**安全纵深六道关卡**:网关鉴权 → 输入安全引擎 → 工具权限分级 → 沙箱隔离 → 输出审核 → 审计落库

#### 2.2.7 Agent 调度中枢(`core/orchestrator/`)

| 文件 | 职责 | 关键类 |
|------|------|--------|
| `context.py` | 上下文容器 | `OrchestratorContext`(注入全部引擎引用) |
| `lifecycle.py` | 生命周期 | `Lifecycle`(7 步流水线) |
| `scheduler.py` | 调度入口 | `AgentScheduler`(`process() -> AgentResponse`) |

**生命周期 7 步**:
1. `_step1_security` 输入安全检查
2. `_step2_memory_load` 记忆检索
3. `_step3_reasoning_select` 推理模式选择
4. `_step4_execute` 推理-工具-反思循环
5. `_step5_validate` 结果校验
6. `_step6_security_review` 输出审核
7. `_step7_save` 全量落库

#### 2.2.8 Prompt 管理引擎(`core/prompt/`)

| 文件 | 职责 | 关键类 |
|------|------|--------|
| `manager.py` | 模板管理 | `PromptManager`(分层模板/版本控制) |
| `builder.py` | Prompt 构建 | `PromptBuilder`(role/constraint/tools/memory/format 分层) |

#### 2.2.9 向量检索引擎(`core/retrieval/`)

| 文件 | 职责 | 关键类 |
|------|------|--------|
| `embedder.py` | Embedding | `BaseEmbedder`、`HashingEmbedder`(无依赖回退) |
| `vectorstore.py` | 向量存储 | `InMemoryVectorStore`(内存回退) |
| `hybrid.py` | 混合检索 | `HybridRetriever`(向量 + 关键词) |

### 2.3 API 层(`api/`)

#### 2.3.1 请求/响应模型(`api/schemas/models.py`)

通用响应:
- `BaseResponse`: `success`/`message`/`data`/`error`
- `ErrorResponse`: `success=False`/`error`/`detail`/`code`

业务模型:见各模块接口说明。

#### 2.3.2 路由(`api/routers/`)

| 文件 | 前缀 | 端点数 | 说明 |
|------|------|--------|------|
| `auth.py` | `/api/v1/auth` | 9 | 用户鉴权管理 |
| `chat.py` | `/api/v1/chat` | 6 | Agent 对话 |
| `documents.py` | `/api/v1/documents` | 8 | 文档管理 |
| `tasks.py` | `/api/v1/tasks` | 12 | 任务管理 |
| `tools.py` | `/api/v1/tools` | 8 | 工具管理 |

### 2.4 业务能力层(`business/`)

| 模块 | 工具 | 说明 |
|------|------|------|
| `search/arxiv.py` | `search_arxiv`/`search_semantic_scholar`/`search_paper` | arXiv Atom XML 解析 + 跨源去重 + 排序 |
| `word/editor.py` | `create_doc`/`edit_doc`/`format_doc` | Word 文档编辑(python-docx) |
| `converter/format_converter.py` | `convert_format` | 格式转换(PDF/DOCX/TXT/Markdown) |

### 2.5 服务层(`services/`)

| 文件 | 职责 | 关键函数 |
|------|------|----------|
| `service.py` | 调度器构建 | `build_scheduler()`、`get_scheduler()`、`reset_scheduler()` |
| `storage.py` | 业务存储 | `UserStore`/`ApiKeyStore`/`DocumentStore`/`TaskStore`(内存实现,线程安全) |

**存储特性**:
- 密码哈希:PBKDF2-HMAC-SHA256,100000 轮迭代
- 文档落盘:`data/uploads/<id>_<filename>`
- 任务生命周期:`pending → running → succeeded/failed/cancelled`

### 2.6 数据模型(`models/`)

#### ORM 实体(`models/db/models.py`)

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| `tenants` | 租户 | id/name/plan/quota_tokens |
| `users` | 用户 | id/tenant_id/username/email/password_hash/role/profile |
| `api_credentials` | API 凭证 | id/user_id/api_key_hash/scopes/expires_at |
| `sessions` | 会话 | id/user_id/title/context/status |
| `messages` | 消息 | id/session_id/role/content/content_type/trace_id |
| `tasks` | 任务 | id/session_id/intent/reasoning_mode/status/plan/result |
| `task_steps` | 任务步骤 | id/task_id/step_no/description/tool_name/status |
| `tool_executions` | 工具执行 | id/task_id/tool_name/arguments/result/status/duration_ms |
| `tools` | 工具元数据 | id/name/description/category/input_schema/permission_level |
| `documents` | 文档 | id/user_id/name/doc_type/source/object_key/checksum |
| `knowledge_chunks` | 知识分块 | id/document_id/chunk_index/content/vector_id |
| `entities` | 实体记忆 | id/tenant_id/entity_type/name/attributes |
| `entity_relations` | 实体关系 | source_id/target_id/relation/weight |
| `reflection_logs` | 反思记录 | id/task_id/check_type/passed/reason/suggestion |
| `audit_logs` | 安全审计 | id/tenant_id/user_id/action/detail/trace_id |
| `prompt_templates` | Prompt 模板 | id/name/version/layer/content/is_active |
| `billing_records` | 计费 | id/user_id/model/token_input/token_output/cost |
| `feedbacks` | 用户反馈 | id/message_id/rating/comment/tags |

### 2.7 基础设施适配器(`adapters/`)

| 文件 | 职责 | 关键类 |
|------|------|--------|
| `db/postgres.py` | PostgreSQL | `DatabaseAdapter`(`session()`/`add`/`query`/`get_by_id`/`update`/`delete`) |
| `cache/redis.py` | Redis | `RedisAdapter`(`get`/`set`/`delete`/`expire`) |

---

## 三、API 接口入参出参

### 3.1 通用说明

- **Base URL**: `http://localhost:8000/api/v1`
- **认证**: 除 `/auth/register`、`/auth/login` 外,需 `Authorization: Bearer <token>` 头
- **Content-Type**: `application/json`(上传文件为 `multipart/form-data`)
- **错误响应**: `{"success": false, "error": "...", "detail": "...", "trace_id": "..."}`

### 3.2 鉴权接口(`/auth`)

#### POST `/auth/register` — 注册用户

**入参**:
```json
{
  "username": "string (3-64 字符,必填)",
  "email": "string (可选,最长 128)",
  "password": "string (6-128 字符,必填)",
  "role": "string (user|admin,默认 user)"
}
```

**出参**(`200`):
```json
{
  "id": 1,
  "username": "alice",
  "email": "alice@example.com",
  "role": "user",
  "created_at": "2026-07-03T12:00:00"
}
```

**错误**: `409` 用户名/邮箱已存在 · `422` 参数校验失败

---

#### POST `/auth/login` — 用户登录

**入参**:
```json
{"username": "alice", "password": "secret123"}
```

**出参**(`200`):
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

**错误**: `401` 用户名或密码错误

---

#### GET `/auth/me` — 获取当前用户

**入参**: 无(需 Bearer Token)

**出参**(`200`): 同 register 响应

---

#### POST `/auth/logout` — 登出

**出参**(`200`): `{"success": true, "message": "Logged out"}`

---

#### PUT `/auth/profile` — 更新用户画像

**入参**(body):
```json
{"research_area": "NLP", "timezone": "Asia/Shanghai"}
```

**出参**(`200`): `{"success": true, "message": "Profile updated", "data": {...}}`

---

#### GET `/auth/quota` — 查询 Token 配额

**出参**(`200`):
```json
{
  "user_id": 1,
  "total_quota": 100000,
  "used_quota": 5000,
  "remaining_quota": 95000
}
```

---

#### POST `/auth/apikey` — 创建 API Key

**出参**(`200`):
```json
{
  "id": 1,
  "api_key": "sk-fnixagent-xxxxx",
  "scopes": ["chat"],
  "created_at": "2026-07-03T12:00:00",
  "expires_at": "2027-07-03T12:00:00"
}
```

> 注意:明文 `api_key` 仅返回一次。

---

#### DELETE `/auth/apikey/{key_id}` — 吊销 API Key

**出参**(`200`): `{"success": true, "message": "API Key revoked"}`

**错误**: `404` Key 不存在或无权操作

---

#### GET `/auth/apikey/list` — 列出 API Key

**出参**(`200`): API Key 列表(不含明文)
```json
[{"id": 1, "scopes": ["chat"], "created_at": "...", "expires_at": "...", "revoked": false}]
```

### 3.3 对话接口(`/chat`)

#### POST `/chat/session` — 创建会话

**入参**:
```json
{"title": "论文检索会话", "context": {}}
```

**出参**(`200`):
```json
{"id": "abc123def456", "title": "论文检索会话", "status": "active", "created_at": "...", "updated_at": "..."}
```

---

#### POST `/chat/message` — 发送消息(非流式)

**入参**:
```json
{
  "session_id": 1,
  "user_input": "帮我搜索 NLP 相关论文",
  "context": {},
  "stream": false
}
```

**出参**(`200`):
```json
{
  "session_id": 1,
  "message_id": 0,
  "response": "已找到 3 篇相关论文...",
  "trace_id": "trace-xxx",
  "duration_ms": 1234.5,
  "stats": {"reasoning_mode": "react", "iterations": 2, "tool_calls": 1, "tokens": {...}}
}
```

---

#### POST `/chat/stream` — 流式对话

**入参**: 同 `/chat/message`

**出参**(`application/x-ndjson` 流):
```
{"chunk_type":"thought","content":"思考中...","done":false}
{"chunk_type":"action","content":"search_paper","done":false}
{"chunk_type":"text","content":"最终答案","done":true}
```

---

#### GET `/chat/session/{session_id}/history` — 会话历史

**出参**(`200`): 消息列表
```json
[{"id": 0, "session_id": 1, "role": "user", "content": "...", "content_type": "text", "created_at": "..."}]
```

---

#### DELETE `/chat/session/{session_id}` — 关闭会话

**出参**(`200`): `{"success": true, "message": "Session closed"}`

---

#### GET `/chat/session/{session_id}/context` — 会话上下文

**出参**(`200`):
```json
{"success": true, "data": {"session_id": 1, "tool_count": 7, "available_tools": [...], "llm_providers": [...]}}
```

### 3.4 文档接口(`/documents`)

#### POST `/documents/upload` — 上传文档

**入参**(`multipart/form-data`):
- `file`: 文件(必填)
- `metadata`: JSON 元数据(可选)

**出参**(`200`):
```json
{
  "id": 1,
  "name": "paper.pdf",
  "doc_type": "pdf",
  "source": "upload",
  "object_key": "1_paper.pdf",
  "created_at": "2026-07-03T12:00:00"
}
```

**自动类型识别**: pdf/docx/markdown/chart/table

---

#### POST `/documents/create` — 创建文档记录

**入参**:
```json
{"name": "report.pdf", "doc_type": "pdf", "metadata": {}}
```

**出参**: 同 upload(来源为 `generated`)

---

#### GET `/documents/list` — 文档列表

**查询参数**: `user_id`(可选) · `doc_type`(可选) · `limit`(默认 50)

**出参**(`200`): DocumentResponse 列表

---

#### GET `/documents/{document_id}` — 查询文档

**出参**(`200`): DocumentResponse · **错误**: `404` 不存在

---

#### POST `/documents/{document_id}/process` — 处理文档

**入参**:
```json
{
  "document_id": 1,
  "operation": "summarize",
  "params": {"target_format": "docx"}
}
```

**支持的 operation**: `summarize`/`extract_tables`/`convert`/`extract_text`/`translate`

**出参**(`200`):
```json
{"success": true, "message": "...", "data": {"document_id": 1, "operation": "summarize", "summary": "..."}}
```

---

#### DELETE `/documents/{document_id}` — 删除文档(软删除)

**出参**(`200`): `{"success": true, "message": "Document deleted"}`

---

#### GET `/documents/{document_id}/download` — 下载文档

**出参**(`200`): 文件流(`FileResponse`,带 `Content-Disposition`)

---

#### GET `/documents/{document_id}/metadata` — 文档元数据

**出参**(`200`):
```json
{
  "id": 1, "name": "paper.pdf", "doc_type": "pdf", "source": "upload",
  "object_key": "1_paper.pdf", "mime_type": "application/pdf",
  "size_bytes": 1024, "checksum": "sha256hex...",
  "created_at": "...", "metadata": {}, "user_id": 0, "deleted": false
}
```

### 3.5 任务接口(`/tasks`)

#### POST `/tasks/` 或 `/tasks/create` — 创建任务

**入参**:
```json
{"session_id": 1, "intent": "论文检索", "reasoning_mode": "react"}
```

`reasoning_mode`: `react`/`plan_execute`/`self_reflect`(默认 `react`)

**出参**(`200`):
```json
{
  "id": 1, "session_id": 1, "intent": "论文检索", "reasoning_mode": "react",
  "status": "pending", "created_at": "...", "started_at": null, "finished_at": null
}
```

---

#### GET `/tasks/list` — 任务列表

**查询参数**: `user_id`(可选) · `status`(可选) · `limit`(默认 50)

**出参**(`200`): TaskResponse 列表

---

#### GET `/tasks/{task_id}` — 查询任务

**出参**(`200`): TaskResponse · **错误**: `404` 不存在

---

#### GET `/tasks/{task_id}/status` — 任务状态

**出参**(`200`):
```json
{"task_id": 1, "status": "running", "progress": 0.5, "current_step": 2, "total_steps": 4}
```

---

#### GET `/tasks/{task_id}/steps` — 任务步骤

**出参**(`200`):
```json
[{"step_no": 1, "description": "搜索论文", "tool_name": "search_paper", "status": "success", "started_at": "...", "finished_at": "...", "result": null, "error": ""}]
```

---

#### POST `/tasks/{task_id}/steps` — 添加步骤

**查询参数**: `description`(必填) · `tool_name`(可选)

**出参**(`200`): `{"step_no": 1, "description": "...", "tool_name": "...", "status": "pending"}`

---

#### POST `/tasks/{task_id}/start` — 启动任务

**前置**: 任务状态必须为 `pending`

**出参**(`200`): TaskResponse(status=`running`) · **错误**: `409` 状态不允许

---

#### POST `/tasks/{task_id}/complete` — 标记完成

**入参**(body,可选):
```json
{"answer": "任务结果数据"}
```

**出参**(`200`): TaskResponse(status=`succeeded`)

---

#### POST `/tasks/{task_id}/fail` — 标记失败

**查询参数**: `error`(必填)

**出参**(`200`): TaskResponse(status=`failed`)

---

#### POST `/tasks/{task_id}/cancel` — 取消任务

**前置**: 任务状态为 `pending`/`running`

**出参**(`200`): `{"success": true, "message": "任务 X 已取消"}` · **错误**: `409` 已完成无法取消

---

#### POST `/tasks/{task_id}/retry` — 重试任务

**效果**: 重置状态为 `pending`,清空步骤状态

**出参**(`200`): TaskResponse(status=`pending`)

### 3.6 工具接口(`/tools`)

#### POST `/tools/register` — 注册工具

**入参**:
```json
{
  "name": "my_tool",
  "description": "工具功能描述",
  "category": "search",
  "input_schema": {"type": "object", "properties": {...}},
  "output_schema": {},
  "permission_level": "low",
  "timeout_ms": 30000,
  "rate_limit": null
}
```

**出参**(`200`): `{"id": 0, "name": "...", "description": "...", "category": "...", "enabled": true, "version": "1.0.0"}`

---

#### GET `/tools/list` — 工具列表

**查询参数**: `category`(可选)

**出参**(`200`): ToolResponse 列表

---

#### GET `/tools/{tool_name}` — 工具详情

**出参**(`200`): ToolResponse · **错误**: `404` 不存在

---

#### POST `/tools/execute` — 执行工具

**入参**:
```json
{"tool_name": "search_arxiv", "arguments": {"query": "NLP"}, "task_id": null, "step_id": null}
```

**出参**(`200`):
```json
{"execution_id": 0, "tool_name": "search_arxiv", "status": "success", "result": {...}, "duration_ms": 123.45, "error": null}
```

---

#### PUT `/tools/{tool_name}/enable` — 启用工具

**出参**(`200`): `{"success": true, "message": "Tool X enabled"}`

---

#### PUT `/tools/{tool_name}/disable` — 禁用工具

**出参**(`200`): `{"success": true, "message": "Tool X disabled"}`

---

#### GET `/tools/{tool_name}/schema` — 工具 Schema

**出参**(`200`):
```json
{"name": "...", "description": "...", "input_schema": {...}, "output_schema": {...}, "permission_level": "low", "timeout_ms": 30000, "rate_limit": null}
```

---

#### GET `/tools/{tool_name}/stats` — 工具统计

**出参**(`200`): `{"tool_name": "...", "registered": true, "category": "..."}`

### 3.7 根路由

| 方法 | 路径 | 说明 | 出参 |
|------|------|------|------|
| GET | `/` | 服务信息 | `{"name": "FnixAgent", "version": "1.0.0", "status": "running", "docs": "/docs"}` |
| GET | `/health` | 健康检查 | `{"status": "healthy", "service": "fnixagent", "uptime": "..."}` |
| GET | `/stats` | 运行统计 | `{"llm": {...}, "memory": {...}, "tools": {"count": N}}` |
| GET | `/docs` | Swagger UI | 交互式 API 文档 |

---

## 四、部署操作步骤

### 4.1 环境要求

- **Python**: 3.11+
- **Docker**: 20.10+(容器化部署)
- **Docker Compose**: 2.0+(编排)
- **操作系统**: Linux / macOS / Windows

### 4.2 方式一:本地开发部署(无需 Docker)

#### 步骤 1:克隆项目

```bash
git clone <repo-url> FnixAgent
cd FnixAgent
```

#### 步骤 2:创建虚拟环境并安装依赖

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

#### 步骤 3:配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`,关键配置:

```env
# LLM(至少配置一个,否则使用 Mock 模式)
GLM_API_KEY=your_glm_api_key
# OPENAI_API_KEY=...
# QWEN_API_KEY=...

# JWT 密钥(生产环境必须修改)
JWT_SECRET_KEY=your_strong_secret_here

# 数据库(可选,未配置时使用内存存储)
POSTGRES_PASSWORD=your_postgres_password
REDIS_PASSWORD=your_redis_password
```

#### 步骤 4:初始化数据库(可选)

```bash
# 启动 PostgreSQL(可选,未配置时服务仍可运行,使用内存存储)
# docker run -d --name pg -p 5432:5432 -e POSTGRES_PASSWORD=your_password postgres:16

# 创建表结构
python scripts/init_db.py

# 导入种子工具数据
python scripts/seed_tools.py
```

#### 步骤 5:启动服务

```bash
# 方式 A:Makefile
make dev

# 方式 B:直接运行
python src/fnixagent/main.py

# 方式 C:uvicorn 热重载
uvicorn fnixagent.main:app --host 0.0.0.0 --port 8000 --reload
```

> 注意:需设置 `PYTHONPATH=src`(Windows: `$env:PYTHONPATH = "src"`)

#### 步骤 6:验证

```bash
curl http://localhost:8000/health
# {"status": "healthy", "service": "fnixagent", ...}

# 访问 API 文档
open http://localhost:8000/docs
```

### 4.3 方式二:Docker Compose 完整部署(推荐生产)

#### 步骤 1:配置环境变量

```bash
cp .env.example .env
# 编辑 .env,填写所有密钥
```

#### 步骤 2:启动全部服务

```bash
# 启动(PostgreSQL + Redis + Milvus + MinIO + Elasticsearch + 应用)
docker-compose up -d

# 查看状态
docker-compose ps

# 查看应用日志
docker-compose logs -f fnixagent
```

#### 步骤 3:初始化数据库(首次部署)

```bash
# 在容器内执行
docker exec fnixagent-app python scripts/init_db.py
docker exec fnixagent-app python scripts/seed_tools.py
```

#### 步骤 4:验证

```bash
curl http://localhost:8000/health
```

#### 步骤 5:停止与清理

```bash
# 停止(保留数据)
docker-compose down

# 停止并删除数据卷(慎用)
docker-compose down -v --remove-orphans
```

### 4.4 方式三:Docker 单镜像构建

```bash
# 构建镜像
docker build -t fnixagent:latest -f deploy/docker/Dockerfile .

# 运行(需外部依赖:PostgreSQL/Redis 等)
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/config:/app/config \
  fnixagent:latest
```

### 4.5 Makefile 命令速查

| 命令 | 说明 |
|------|------|
| `make install` | 安装依赖 |
| `make dev` | 启动开发服务 |
| `make test` | 运行测试(带覆盖率) |
| `make lint` | 代码检查(flake8 + black) |
| `make migrate` | 数据库迁移 |
| `make seed` | 导入种子数据 |
| `make docker-up` | Docker Compose 启动 |
| `make docker-down` | Docker Compose 停止 |
| `make docker-clean` | Docker 完全清理(含数据卷) |
| `make build` | 构建 Docker 镜像 |
| `make run` | 运行 Docker 容器 |
| `make logs` | 查看应用日志 |
| `make clean` | 清理缓存文件 |

### 4.6 测试

```bash
# 运行全部测试
make test
# 或
python -m pytest tests/ -v

# 运行特定模块测试
python -m pytest tests/unit/test_api/ -v      # API 路由测试
python -m pytest tests/unit/test_llm/ -v      # LLM 路由测试
python -m pytest tests/integration/ -v        # 集成测试

# 设置 PYTHONPATH(若未安装为包)
$env:PYTHONPATH = "src"  # Windows
export PYTHONPATH=src    # Linux/macOS
```

**当前测试覆盖**:105 个测试通过(40 核心 + 65 API)。

### 4.7 生产部署清单

| 检查项 | 说明 |
|--------|------|
| □ 修改 JWT_SECRET_KEY | 生产环境必须使用强随机密钥 |
| □ 配置 LLM API Key | 至少配置一个(GLM/OpenAI/Qwen) |
| □ 配置数据库密码 | PostgreSQL/Redis/MinIO 密码 |
| □ 启用 HTTPS | Nginx 反向代理配置 TLS |
| □ 配置 CORS | 限制 `allow_origins` 为可信域名 |
| □ 启用监控 | Prometheus + Grafana + Jaeger |
| □ 数据备份 | 配置 PostgreSQL/MinIO 定期备份 |
| □ 日志收集 | 配置日志轮转与集中收集 |
| □ 资源限制 | Docker 容器 CPU/内存限制 |
| □ 健康检查 | 配置 `/health` 探针 |

### 4.8 常见问题

**Q: 启动时报 `No module named 'fnixagent'`?**
A: 设置 `PYTHONPATH=src`,或将 `src/fnixagent` 安装为包(`pip install -e .`)。

**Q: 无 LLM API Key 能否运行?**
A: 可以。系统自动回退到 `MockLLMProvider`,返回基于规则的简单响应,适用于开发测试。

**Q: 无 PostgreSQL 能否运行?**
A: 可以。`services/storage.py` 提供内存存储实现,所有业务功能可用,但数据不持久化。

**Q: 如何切换 LLM Provider?**
A: 在 `.env` 中配置对应的 API Key(`GLM_API_KEY`/`OPENAI_API_KEY`/`QWEN_API_KEY`),重启服务即可。优先级:GLM > OpenAI > Qwen > Mock。

**Q: 文档上传到哪里?**
A: 默认落盘到 `data/uploads/` 目录。生产环境可对接 MinIO(配置 `MINIO_ENDPOINT`)。

---

## 五、开发约定

### 5.1 代码规范

- **语言**: 代码注释与文档使用中文
- **类型注解**: 全部函数使用类型注解(`from __future__ import annotations`)
- **docstring**: 模块/类/函数三级 docstring 齐全
- **格式化**: `black`(行宽 88)
- **检查**: `flake8` + `mypy`

### 5.2 分层依赖原则

```
api/ → services/ → core/ + business/
                    ↓
                  adapters/ → models/
```

- `core/` **不 import** `business/`(引擎与业务解耦)
- `business/` 以「工具」形式注册到 `ToolRegistry`,引擎只认 Tool Protocol
- `api/` 只调用 `services/`,不直接访问 `core/`

### 5.3 新增业务工具

1. 在 `business/<domain>/` 创建工具函数,实现 `ToolMetadata` + 执行函数
2. 在 `business/<domain>/__init__.py` 中编写 `register_xxx_tools(registry)` 函数
3. 在 `services/service.py` 的 `_register_business_tools()` 中调用注册函数
4. 重启服务,工具自动注册到调度器

### 5.4 测试规范

- 单元测试:`tests/unit/<module>/`
- 集成测试:`tests/integration/`
- API 测试:使用 FastAPI `TestClient`
- 每个 `test_*.py` 文件开头通过 `sys.path.insert` 确保 `src` 在路径中
- 测试夹具(fixture)负责重置全局单例(`reset_scheduler`/`reset_stores`)

---

*文档版本:1.0 · 最后更新:2026-07-03*
