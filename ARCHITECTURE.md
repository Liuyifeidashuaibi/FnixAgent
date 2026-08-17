# FnixAgent 智能办公 Agent · 项目技术架构设计

> 定位：面向 **学习 / 教育 / 办公** 场景的智能 Agent，核心能力包括：论文文献检索、Word 编辑、格式转换、图表生成、PDF 生成、文档解析、学习辅助问答，并基于「任务」实现端到端自动编排。
>
> 本文档交付：① 完整技术架构 · ② 文件夹目录结构 · ③ 数据库表结构 · ④ 底层算法模块 vs 业务功能模块清单。

---

## 一、总体技术架构（分层视图）

整体采用 **7 层架构 + 调度中枢** 设计。核心原则：**底层算法引擎与业务能力解耦**——算法层（推理/记忆/工具/安全）领域无关、可复用；业务层（论文/Word/PDF/图表）是 office 领域的具体工具与工作流实现。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ① 交互层 Interaction                                                       │
│     Web 前端(React) · 企业微信/钉钉 Bot · CLI · ERP/BI 内嵌 · 开放 HTTP API  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  ② 网关层 Gateway (FastAPI + Nginx)                                          │
│     身份鉴权(JWT/OAuth2) · 多租户隔离 · 限流熔断 · 全链路 TraceId · 日志埋点 │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  ③ Agent 调度中枢 Orchestrator（生命周期总控）                                │
│   输入→鉴权→记忆检索→意图识别→任务规划→[推理-工具-反思循环]→结果校验→         │
│   生成回复→全量落库   （串起 ④ 的所有引擎）                                   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  ④ 核心算法引擎层 Core Engine（领域无关，可复用）                              │
│  ┌──────────────┬───────────────┬────────────────┬────────────────────────┐  │
│  │ LLM 基础服务 │ 三层记忆引擎   │ 规划与推理引擎  │ 反思纠错引擎            │  │
│  │ 多模型路由    │ 短期/长期/实体 │ ReAct/Plan&Exec│ 结果校验·失败重规划     │  │
│  │ 负载·限流·熔断│ 向量检索       │ /Self-Reflect  │                        │  │
│  │ Token 计费    │ 记忆过期清理   │ 模式按需切换    │                        │  │
│  ├──────────────┼───────────────┼────────────────┼────────────────────────┤  │
│  │ 工具执行平台  │ 合规与安全引擎 │ Prompt 管理引擎 │ 向量检索引擎            │  │
│  │ 元数据·沙箱   │ 敏感词·注入防护│ 分层模板·版本   │ Embedding·相似度       │  │
│  │ 串/并/分支编排│ 审核·脱敏      │ 角色/约束/格式  │ 混合检索(向量+关键词)  │  │
│  └──────────────┴───────────────┴────────────────┴────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ 🚀 顶级架构升级模块 (2026-08, 参考 EverOS/waku-agent/Darwin.skill)      │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ 记忆系统升级:                                                          │  │
│  │  • MarkdownMemoryStore — Markdown 源真相存储，人类可读可编辑            │  │
│  │  • RetrievalGate — 智能检索门控，根据查询复杂度自动决定是否检索          │  │
│  │  • MemoryConsolidator — 定期记忆提炼，自动提取关键事实并去重             │  │
│  │  • ReflectionEngine — 离线记忆进化，合并相似项、提炼模式、生成洞察       │  │
│  ├────────────────────────────────────────────────────────────────────────┤  │
│  │ 技能系统升级:                                                          │  │
│  │  • SkillEvaluator — 9 维评估器（结构/执行/失败/可执行/上下文/边界/...） │  │
│  │  • SkillEvolver — 技能进化器（棘轮机制，只保留改进自动回滚退步）         │  │
│  │  • HumanInTheLoop — 三层守关机制（高风险操作/技能进化/记忆删除确认）     │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │ 通过统一 Tool Protocol 调用
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  ⑤ 业务能力层 Business Capabilities（Office 领域工具与工作流）                │
│   论文文献检索 · 文献管理 · Word 编辑 · 格式转换 · 图表生成 · PDF 生成 ·      │
│   文档/表格/图片解析(多模态) · 学习辅助(摘要/问答/笔记) · Office 任务编排     │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  ⑥ 数据与存储层 Storage                                                      │
│   PostgreSQL(业务/实体/审计) · Milvus(长期向量) · Redis(短期会话/缓存) ·      │
│   MinIO(文件/文档对象) · Elasticsearch(全文检索·日志)                         │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────────────┐
│  ⑦ 基础设施层 Infrastructure                                                  │
│   Docker · Kubernetes(弹性扩容) · vLLM(GPU 推理) · Prometheus+Grafana(监控)  │
│   ELK(日志) · Jaeger(链路追踪) · CI/CD(GitHub Actions)                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 核心数据流（一次完整请求）

```
用户输入
  → 网关: 鉴权 + 限流 + 生成 traceId
  → 调度中枢:
      1. 安全校验(敏感词/注入检测) ─失败→ 拦截返回
      2. 短期记忆加载(滑动窗口) + 长期向量检索(召回相关历史/知识)
      3. 实体记忆读取(用户画像/当前任务上下文)
      4. 意图识别 → 选择推理模式(简单→ReAct / 复杂→Plan&Execute)
      5. 规划引擎生成子任务计划
      6. 循环: 推理 → 选择工具 → 沙箱安全执行 → 观察结果
      7. 反思引擎校验(完整性/合理性) ─不通过→ 重规划/补工具
      8. 输出审核(脱敏/合规) → 生成最终回复
      9. 短期记忆更新 + 实体记忆更新 + 文件落 MinIO + 记录落库
  → 交互层返回(流式)
```

---

## 二、技术选型一览

| 层级 | 选型 | 说明 |
|------|------|------|
| 后端语言/框架 | Python 3.11 + FastAPI | 异步、生态完善、LLM 友好 |
| LLM | 闭源：GLM/Claude/GPT；开源：Qwen2.5 / Llama3 + **vLLM** | 通过统一网关多模型路由 |
| Agent 框架 | **自研调度器**(主) + LangGraph(复杂任务流) | 高可控，关键路径自研 |
| 向量库 | Milvus(生产) / FAISS(轻量) | 长期记忆 + 文档检索 |
| 业务库 | PostgreSQL 16 | 实体/会话/任务/审计 |
| 缓存/短期记忆 | Redis 7 | 会话窗口、请求缓存 |
| 文件存储 | MinIO | 上传/生成文档对象 |
| 全文检索/日志 | Elasticsearch | 论文检索、日志聚合 |
| 代码沙箱 | Docker 容器隔离 / gVisor | 安全执行动态代码 |
| 任务队列 | Celery + Redis/RabbitMQ | 异步长任务(PDF/图表) |
| 部署 | Docker + Kubernetes | 弹性扩缩容 |
| 监控 | Prometheus + Grafana + Loki + Jaeger | 指标/日志/链路 |

---

## 三、文件夹目录结构

采用 **模块化单体（Modular Monolith）**，每个领域一个独立 package，便于未来拆为微服务。底层引擎与业务模块物理隔离。

```
FNIXAGENT/
├── ARCHITECTURE.md                 # 本架构文档
├── README.md
├── pyproject.toml                  # 依赖与项目元数据（uv/poetry）
├── docker-compose.yml              # 本地一键起 PG/Redis/Milvus/MinIO/ES
├── Dockerfile
├── .env.example
├── Makefile                        # make dev / test / lint / migrate
│
├── deploy/                         # ⑦ 部署
│   ├── docker/                     # 各服务 Dockerfile
│   ├── k8s/                        # deployment/service/ingress/hpa
│   └── helm/                       # Helm Chart
│
├── config/                         # 配置
│   ├── settings.yaml               # 全局配置
│   ├── prompts/                    # 分层 Prompt 模板(版本化)
│   │   ├── system_role.yaml
│   │   ├── react_planner.yaml
│   │   ├── plan_execute.yaml
│   │   └── reflection.yaml
│   └── security/                   # 敏感词表/黑名单/白名单
│
├── src/
│   └── fnixagent/
│       ├── __init__.py
│       ├── main.py                 # FastAPI 入口
│       ├── config.py               # 配置加载(pydantic-settings)
│       │
│       ├── api/                    # ①② 对外接口层
│       │   ├── routers/            # HTTP 路由: chat/document/task/tool
│       │   ├── deps.py             # 鉴权/限流依赖注入
│       │   ├── middleware.py       # TraceId/日志/CORS
│       │   └── schemas/            # 请求/响应 Pydantic 模型
│       │
│       ├── core/                   # ④ 核心算法引擎层(领域无关)
│       │   ├── orchestrator/       # ③ Agent 调度中枢
│       │   │   ├── scheduler.py    # 生命周期总控
│       │   │   ├── context.py      # 运行时上下文
│       │   │   └── lifecycle.py    # 请求全流程编排
│       │   │
│       │   ├── llm/                # LLM 基础服务层
│       │   │   ├── base.py         # 统一抽象接口
│       │   │   ├── providers/      # glm/openai/qwen/vllm 适配器
│       │   │   ├── router.py       # 多模型路由+负载均衡
│       │   │   ├── billing.py      # token 计费统计
│       │   │   ├── cache.py        # 请求缓存(语义/精确)
│       │   │   └── circuit.py      # 异常熔断
│       │   │
│       │   ├── memory/             # 三层记忆引擎
│       │   │   ├── short_term.py   # 短期会话(滑动窗口裁剪)
│       │   │   ├── long_term.py    # 长期向量(分块/入库/检索/过期)
│       │   │   ├── entity.py       # 实体记忆(结构化业务数据)
│       │   │   └── manager.py      # 统一记忆管理器
│       │   │
│       │   ├── reasoning/          # 规划与推理引擎
│       │   │   ├── base.py
│       │   │   ├── react.py        # ReAct 模式
│       │   │   ├── plan_execute.py # Plan&Execute 模式
│       │   │   ├── self_reflect.py # Self-Reflection 模式
│       │   │   └── selector.py     # 按任务复杂度自动选模式
│       │   │
│       │   ├── reflection/         # 反思纠错引擎
│       │   │   ├── validator.py    # 结果完整性/逻辑校验
│       │   │   └── replanner.py    # 失败重规划
│       │   │
│       │   ├── tools/              # 工具执行平台(引擎侧)
│       │   │   ├── registry.py     # 工具元数据注册中心
│       │   │   ├── protocol.py     # 统一工具协议(入参/权限/超时)
│       │   │   ├── executor.py     # 串行/并行/分支编排执行
│       │   │   └── sandbox/        # 安全沙箱
│       │   │       ├── code_sandbox.py   # 动态代码隔离执行
│       │   │       └── policy.py         # 高危拦截/网络白名单
│       │   │
│       │   ├── security/           # 合规与安全引擎
│       │   │   ├── sensitive.py    # 敏感词检测
│       │   │   ├── injection.py    # Prompt 注入防护
│       │   │   ├── moderation.py   # 输出内容审核
│       │   │   └── desensitize.py  # 数据脱敏
│       │   │
│       │   ├── prompt/             # Prompt 管理引擎
│       │   │   ├── manager.py      # 分层组装+版本管理
│       │   │   └── builder.py      # 角色/约束/工具/记忆/格式
│       │   │
│       │   └── retrieval/          # 向量检索引擎
│       │       ├── embedder.py     # Embedding 模型封装
│       │       ├── vectorstore.py  # Milvus 抽象
│       │       └── hybrid.py       # 向量+关键词混合检索
│       │
│       ├── business/               # ⑤ 业务能力层(Office 领域)
│       │   ├── search/             # 论文文献检索
│       │   │   ├── arxiv.py
│       │   │   ├── semantic_scholar.py
│       │   │   ├── cnki.py         # 知网/万方
│       │   │   └── aggregator.py
│       │   ├── literature/         # 文献管理(引用/去重/综述)
│       │   ├── word/               # Word 文档编辑(python-docx)
│       │   ├── converter/          # 格式转换(docx/pdf/md/html)
│       │   ├── chart/              # 图表生成(matplotlib/plotly/echarts)
│       │   ├── pdf/                # PDF 生成(reportlab/weasyprint/latex)
│       │   ├── parser/             # 文档解析(多模态: 表格/图片/公式)
│       │   ├── learning/           # 学习辅助(摘要/问答/笔记/抽认卡)
│       │   └── workflow/           # Office 任务编排(端到端工作流)
│       │
│       ├── adapters/               # 外部依赖适配器(防腐层)
│       │   ├── db/                 # PostgreSQL (SQLAlchemy)
│       │   ├── cache/              # Redis
│       │   ├── objectstore/        # MinIO
│       │   ├── search_engine/      # Elasticsearch
│       │   └── queue/              # Celery
│       │
│       ├── models/                 # 领域模型 + ORM 实体
│       │   ├── db/                 # SQLAlchemy 表模型
│       │   └── domain/             # 领域对象(与 ORM 解耦)
│       │
│       └── tasks/                  # 异步长任务(Celery)
│           ├── pdf_task.py
│           ├── chart_task.py
│           └── search_task.py
│
├── migrations/                     # 数据库迁移(Alembic)
│   └── versions/
│
├── scripts/                        # 运维脚本
│   ├── init_db.py
│   ├── seed_tools.py               # 灌入工具元数据
│   └── build_index.py              # 构建向量索引
│
├── tests/                          # ④ 测试(对应阶段4)
│   ├── unit/                       # 单元测试
│   │   ├── test_llm/
│   │   ├── test_memory/
│   │   ├── test_reasoning/
│   │   └── test_tools/
│   ├── integration/                # 业务场景集成测试
│   ├── e2e/                        # 端到端
│   ├── load/                       # 压力测试(locust)
│   └── security/                   # 安全/注入攻击测试
│
└── docs/                           # 文档
    ├── api/                        # OpenAPI
    ├── prompts/                    # Prompt 设计说明
    └── runbooks/                   # 运维手册
```

---

## 四、数据库表结构（PostgreSQL）

> 命名规范：表名小写蛇形复数；主键统一 `id BIGSERIAL`（或 UUID）；所有表含 `created_at` / `updated_at`；关键表软删除 `deleted_at`。

### 4.1 账号与租户

```sql
-- 租户(多租户隔离)
CREATE TABLE tenants (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(128) NOT NULL,
    plan         VARCHAR(32)  NOT NULL DEFAULT 'free',   -- free/pro/enterprise
    quota_tokens BIGINT       NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 用户
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     BIGINT NOT NULL REFERENCES tenants(id),
    username      VARCHAR(64)  NOT NULL,
    email         VARCHAR(128) UNIQUE,
    password_hash VARCHAR(255),
    role          VARCHAR(32)  NOT NULL DEFAULT 'user',  -- user/admin
    profile       JSONB        NOT NULL DEFAULT '{}',    -- 偏好/学科领域(实体记忆一部分)
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, username)
);

-- API 凭证
CREATE TABLE api_credentials (
    id           BIGSERIAL PRIMARY KEY,
    user_id      BIGINT NOT NULL REFERENCES users(id),
    api_key_hash VARCHAR(255) NOT NULL,
    scopes       TEXT[]   NOT NULL DEFAULT '{}',
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ
);
```

### 4.2 会话与消息（短期记忆持久化镜像）

```sql
-- 会话(按会话隔离记忆)
CREATE TABLE sessions (
    id         BIGSERIAL PRIMARY KEY,
    tenant_id  BIGINT NOT NULL REFERENCES tenants(id),
    user_id    BIGINT NOT NULL REFERENCES users(id),
    title      VARCHAR(255),                          -- 自动生成
    context    JSONB   NOT NULL DEFAULT '{}',         -- 当前任务上下文
    status     VARCHAR(32) NOT NULL DEFAULT 'active', -- active/closed/archived
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sessions_user ON sessions(user_id, status);

-- 消息(对话/思考/工具记录全留存,供回放与案例回流)
CREATE TABLE messages (
    id            BIGSERIAL PRIMARY KEY,
    session_id    BIGINT NOT NULL REFERENCES sessions(id),
    role          VARCHAR(16) NOT NULL,   -- user/assistant/system/tool
    content       TEXT        NOT NULL,
    content_type  VARCHAR(32) NOT NULL DEFAULT 'text', -- text/json/tool_call/thought
    parent_id     BIGINT REFERENCES messages(id),      -- 多轮树结构
    token_input   INT,                              -- 阶段4 计费
    token_output  INT,
    model         VARCHAR(64),
    trace_id      VARCHAR(64),
    metadata      JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);
```

### 4.3 任务与规划

```sql
-- 任务(用户的一个高层目标)
CREATE TABLE tasks (
    id            BIGSERIAL PRIMARY KEY,
    session_id    BIGINT NOT NULL REFERENCES sessions(id),
    user_id       BIGINT NOT NULL REFERENCES users(id),
    intent        VARCHAR(128),                    -- 意图: search_paper/edit_word/...
    reasoning_mode VARCHAR(32) NOT NULL,           -- react/plan_execute/self_reflect
    status        VARCHAR(32) NOT NULL DEFAULT 'pending', -- pending/running/succeeded/failed
    plan          JSONB NOT NULL DEFAULT '{}',      -- 规划引擎产出
    result        JSONB,                            -- 最终结果
    error         TEXT,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status);

-- 子任务步骤(Plan&Execute 拆分;ReAct 的每一步)
CREATE TABLE task_steps (
    id          BIGSERIAL PRIMARY KEY,
    task_id     BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_no     INT NOT NULL,
    description TEXT NOT NULL,
    tool_name   VARCHAR(128),                       -- 调用的工具
    status      VARCHAR(32) NOT NULL DEFAULT 'pending',
    depends_on  INT[] NOT NULL DEFAULT '{}',        -- 依赖步骤(分支/并行)
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
```

### 4.4 工具执行记录

```sql
-- 工具调用记录(可观测+计费+安全审计)
CREATE TABLE tool_executions (
    id            BIGSERIAL PRIMARY KEY,
    task_id       BIGINT REFERENCES tasks(id),
    step_id       BIGINT REFERENCES task_steps(id),
    tool_name     VARCHAR(128) NOT NULL,
    tool_version  VARCHAR(32),
    arguments     JSONB NOT NULL,                   -- 入参
    result        JSONB,                            -- 返回
    status        VARCHAR(32) NOT NULL,             -- success/failed/timeout
    error         TEXT,
    duration_ms   INT,
    sandbox_id    VARCHAR(64),                      -- 沙箱实例(代码执行类)
    permission_level VARCHAR(32) DEFAULT 'low',     -- low/middle/high
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tool_exec_task ON tool_executions(task_id);
CREATE INDEX idx_tool_exec_name_time ON tool_executions(tool_name, created_at);
```

### 4.5 工具元数据注册

```sql
-- 工具元数据(标准化工具平台)
CREATE TABLE tools (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(128) UNIQUE NOT NULL,
    description     TEXT NOT NULL,                  -- 给 LLM 看的功能描述
    category        VARCHAR(64) NOT NULL,           -- search/word/pdf/chart/...
    input_schema    JSONB NOT NULL,                 -- JSON Schema 入参
    output_schema   JSONB,
    permission_level VARCHAR(32) NOT NULL DEFAULT 'low',
    timeout_ms      INT NOT NULL DEFAULT 30000,
    rate_limit      INT,                            -- 每分钟调用上限
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    version         VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.6 文档与知识库（长期记忆 + 文件）

```sql
-- 文档(用户上传 / Agent 生成)
CREATE TABLE documents (
    id            BIGSERIAL PRIMARY KEY,
    tenant_id     BIGINT NOT NULL,
    user_id       BIGINT NOT NULL,
    name          VARCHAR(255) NOT NULL,
    doc_type      VARCHAR(32) NOT NULL,   -- paper/docx/pdf/markdown/chart
    source        VARCHAR(32) NOT NULL,   -- upload/generated/search
    object_key    VARCHAR(512),           -- MinIO 对象键
    mime_type     VARCHAR(128),
    size_bytes    BIGINT,
    checksum      VARCHAR(64),
    metadata      JSONB NOT NULL DEFAULT '{}',  -- 标题/作者/DOI/摘要
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);
CREATE INDEX idx_docs_user_type ON documents(user_id, doc_type);

-- 知识分块(向量入库的元数据,向量本体存 Milvus,用 doc_chunk_id 关联)
CREATE TABLE knowledge_chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content     TEXT NOT NULL,                     -- 原文分块
    vector_id   VARCHAR(128),                      -- Milvus 中的向量主键
    token_count INT,
    metadata    JSONB NOT NULL DEFAULT '{}',       -- 章节/页码/标题层级
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_chunks_doc ON knowledge_chunks(document_id);
```

### 4.7 实体记忆（结构化业务数据）

```sql
-- 实体记忆(用户/论文/项目等,跨会话长期持有)
CREATE TABLE entities (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    user_id     BIGINT,                            -- 可空: 全局实体
    entity_type VARCHAR(64) NOT NULL,              -- user_profile/paper/project/note
    name        VARCHAR(255) NOT NULL,
    attributes  JSONB NOT NULL DEFAULT '{}',       -- 结构化属性
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, entity_type, name)
);
CREATE INDEX idx_entities_user_type ON entities(user_id, entity_type);

-- 实体关系(知识图谱式,增强记忆关联)
CREATE TABLE entity_relations (
    id          BIGSERIAL PRIMARY KEY,
    source_id   BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id   BIGINT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation    VARCHAR(64) NOT NULL,              -- authored_by/cites/related_to
    weight      REAL NOT NULL DEFAULT 1.0,
    UNIQUE(source_id, target_id, relation)
);
```

### 4.8 反思与安全审计

```sql
-- 反思记录(失败重规划/案例回流依据)
CREATE TABLE reflection_logs (
    id           BIGSERIAL PRIMARY KEY,
    task_id      BIGINT REFERENCES tasks(id),
    step_id      BIGINT REFERENCES task_steps(id),
    check_type   VARCHAR(64) NOT NULL,             -- completeness/logic/safety
    passed       BOOLEAN NOT NULL,
    reason       TEXT,
    suggestion   TEXT,                             -- 重规划建议
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 安全审计(敏感词命中/注入尝试/越权)
CREATE TABLE audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   BIGINT NOT NULL,
    user_id     BIGINT,
    action      VARCHAR(64) NOT NULL,              -- sensitive_hit/injection_blocked/denied
    detail      JSONB NOT NULL,
    trace_id    VARCHAR(64),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Prompt 模板版本
CREATE TABLE prompt_templates (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(128) NOT NULL,
    version    VARCHAR(32) NOT NULL,
    layer      VARCHAR(32) NOT NULL,               -- role/constraint/tools/memory/format
    content    TEXT NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(name, version)
);
```

### 4.9 计费与反馈

```sql
-- Token 计费(按模型/按请求)
CREATE TABLE billing_records (
    id           BIGSERIAL PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    user_id      BIGINT NOT NULL,
    model        VARCHAR(64) NOT NULL,
    token_input  INT NOT NULL,
    token_output INT NOT NULL,
    cost         NUMERIC(12,6) NOT NULL,
    trace_id     VARCHAR(64),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 用户反馈(差评回流,阶段6迭代依据)
CREATE TABLE feedbacks (
    id         BIGSERIAL PRIMARY KEY,
    message_id BIGINT REFERENCES messages(id),
    user_id    BIGINT NOT NULL,
    rating     SMALLINT NOT NULL,      -- 1-5
    comment    TEXT,
    tags       TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

> **Milvus 侧**：collection `long_term_memory`（向量 + tenant_id/user_id/session_id 过滤字段）与 `document_vectors`，主键与 `knowledge_chunks.vector_id` 对齐。
> **Redis 侧**：`session:{id}:short_term`（List/ZSet 滑动窗口）、`llm:cache:{hash}`、`rate:{user}:{tool}`。

---

## 五、模块清单：底层算法模块 vs 业务功能模块

> **划分准则**：底层算法模块 = 领域无关的 Agent 通用能力（换个业务也能用）；业务功能模块 = office/教育场景专属的工具与工作流。两者通过统一 **Tool Protocol** 与 **Orchestrator** 解耦。

### 5.1 底层算法模块（Core Engine，`src/fnixagent/core/`）

| 模块 | 职责 | 关键产出 | 复用性 |
|------|------|----------|--------|
| **调度中枢 Orchestrator** | 串联全生命周期，总控流程编排 | `scheduler.py` 7 步流水线 | 通用 |
| **LLM 基础服务** | 多模型路由、负载均衡、限流、Token 计费、请求缓存、异常熔断 | 统一 `LLMClient` 抽象 | 通用 |
| **三层记忆引擎** | 短期(滑动窗口)/长期(向量)/实体(结构化) 记忆的读写与过期清理 | `MemoryManager` | 通用 |
| **规划与推理引擎** | ReAct / Plan&Execute / Self-Reflection 三模式按需切换 | `ReasoningEngine` + `selector` | 通用 |
| **反思纠错引擎** | 结果完整性/逻辑校验，失败自动重规划、补工具 | `Validator` + `Replanner` | 通用 |
| **工具执行平台** | 工具元数据管理、串/并/分支编排、安全沙箱 | `ToolRegistry` + `Executor` | 通用 |
| **安全沙箱** | 动态代码隔离执行、高危命令拦截、网络白名单、文件读写限制 | `code_sandbox` | 通用 |
| **合规与安全引擎** | 敏感词、Prompt 注入防护、输出审核、脱敏 | `SecurityEngine` | 通用 |
| **Prompt 管理引擎** | 分层模板(角色/约束/工具/记忆/格式)、版本管理 | `PromptManager` | 通用 |
| **向量检索引擎** | Embedding、相似度检索、向量+关键词混合检索 | `RetrievalEngine` | 通用 |

### 5.2 业务功能模块（Business，`src/fnixagent/business/`）

每个业务模块对外暴露为「标准化工具」，注册进 `ToolRegistry`，由引擎层按需调用。

| 模块 | 业务能力 | 对应工具示例 | 依赖 |
|------|----------|--------------|------|
| **论文文献检索 search** | arXiv / Semantic Scholar / 知网万方 检索、去重、聚合 | `search_paper`、`search_by_doi` | ES + 各 API |
| **文献管理 literature** | 引用格式化(BibTeX/GB-T7714)、文献综述生成、相关性分析 | `format_citation`、`gen_literature_review` | LLM + 结构化 |
| **Word 编辑 word** | 创建/修改 docx、查找替换、样式/目录/页眉页脚、批注修订 | `create_docx`、`edit_docx`、`apply_style` | python-docx |
| **格式转换 converter** | docx↔pdf↔md↔html↔txt 双向转换 | `convert_document` | pandoc / libreoffice |
| **图表生成 chart** | 柱/折线/饼/散点/热力图、数据可视化、Excel 图表 | `generate_chart`、`plot_from_table` | matplotlib/plotly |
| **PDF 生成 pdf** | 报告/简历/海报/学术论文 PDF（含 LaTeX 路线） | `generate_pdf_report`、`latex_compile` | reportlab/weasyprint |
| **文档解析 parser** | PDF/Word/图片 表格抽取、OCR、公式识别（多模态） | `extract_tables`、`ocr_image` | unpdf/paddle |
| **学习辅助 learning** | 论文摘要、问答、笔记生成、抽认卡、概念图 | `summarize`、`qa_doc`、`make_flashcards` | LLM + 记忆 |
| **Office 任务编排 workflow** | 端到端：搜论文→下载→总结→生成 Word→转 PDF 等组合工作流 | 复合工具 / Plan 模板 | 编排引擎 |

### 5.3 辅助层

| 层 | 模块 | 说明 |
|----|------|------|
| **接口层 api** | HTTP 路由、鉴权、限流、流式 SSE | 对外唯一入口 |
| **适配层 adapters** | DB/Cache/ObjectStore/ES/Queue 防腐封装 | 隔离基础设施变更 |
| **异步任务 tasks** | PDF 编译、大图表、批量检索等长任务 | Celery |
| **模型层 models** | ORM 实体 + 领域对象 | 与业务解耦 |

---

## 六、对应开发阶段的落点（阶段1→6 映射）

| 阶段 | 工作内容 | 落在哪些模块 |
|------|----------|--------------|
| 1 需求规划 | 能力清单、风险边界、架构文档 | 本文档 + `config/` |
| 2 核心模块开发 | LLM/记忆/工具/规划/反思/安全 | `core/llm`、`core/memory`、`core/tools`、`core/reasoning`、`core/reflection`、`core/security` |
| 3 调度整合 | 主调度中枢 + 分层 Prompt | `core/orchestrator`、`core/prompt` |
| 4 全量测试 | 单元/集成/调参/压测安全 | `tests/*` |
| 5 线上部署 | HTTP API、多端对接、容器化 | `api/`、`deploy/` |
| 6 运维迭代 | 监控、案例回流、能力扩展 | 监控配置 + `feedbacks`/`reflection_logs` |

---

## 七、关键设计决策小结

1. **引擎与业务解耦**：`core/` 不 import `business/`；业务以「工具」形式注册，引擎只认 Tool Protocol。换行业只需新增 `business/` 模块。
2. **推理模式可插拔**：`reasoning/selector.py` 依据任务复杂度/工具数自动选 ReAct 或 Plan&Execute，Self-Reflection 作为校验层叠加。
3. **记忆三层分工**：短期管 token 预算、长期管跨会话知识、实体管结构化业务事实，由 `MemoryManager` 统一注入 Prompt。
4. **安全纵深**：网关鉴权 → 输入安全引擎 → 工具权限分级 → 沙箱隔离 → 输出审核 → 审计落库，六道关卡。
5. **全链路可观测**：traceId 贯穿 message/tool/reflection/audit/billing，任一请求可完整回放，支撑阶段6案例回流。
