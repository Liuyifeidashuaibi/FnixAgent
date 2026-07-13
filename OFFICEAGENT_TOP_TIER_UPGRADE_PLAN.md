# OfficeAgent 顶级升级计划清单

> 本计划基于对国内外主流 AI Agent 框架的深度研究,提炼其健壮代码设计精华,结合 OfficeAgent 现状基线,给出"从能跑到顶级"的可执行升级路线。
>
> **研究范围**:
> - **国外**:MetaGPT(38K★) · AutoGen/AG2(微软,54K★) · OpenAI Agents SDK · CrewAI(41K★) · LangGraph · PydanticAI
> - **国内**:字节扣子 Coze 3.0 · 智谱 GLM-4.5/AutoGLM · 阿里 ModelScope-Agent · 阿里 Qwen-Agent/AgentScope · 百度文心智能体 · 腾讯元器 · Dify(开源) · 字节豆包
>
> **核心结论**:OfficeAgent 已具备**生产级基础设施**(策略模式推理、DAG 工具编排、三态熔断、三层记忆、安全模块),在调研框架中属中上水平。主要差距集中在三维度:**状态正确性、安全/可观测收敛、类型安全/校验**,以及办公领域特化的**项目空间化、技能市场、MCP 双向流通**。这三个维度+办公特化是"从能跑到顶级"的关键跃迁。
>
> **业务定位(已确认)**:**专注两层,不做通用扩展**。
> - **L1 Office 顶级专家层**(护城河,深度做透):Word/Excel/PPT/PDF/格式转换/文档解析/图表/模板/论文检索/引用管理
> - **L2 办公生态层**(适度覆盖):邮件/日程/会议/审批/IM 推送/项目协作/知识库
> - **明确边界**:非 Office/非办公任务(天气/航班/股票/订餐等),Agent 诚实告知"不擅长"并建议用户使用专用工具,不硬撑装会
>
> **战略原则**:先做强单 Agent(状态/安全/类型三补强),再深度做透 Office 专家能力 + 覆盖办公生态,最后按需引入多 Agent(避免过早过度工程化)。

---

## 〇、研究精华速览(借鉴来源对照)

### 国外框架精华(代码设计层)

| 框架 | 核心设计精华 | OfficeAgent 借鉴点 |
|------|------------|-------------------|
| **LangGraph** | `Annotated[T, reducer]` 显式状态合并 + Checkpoint 持久化 + Conditional Edge + Send API Map-Reduce | 显式 Reducer(消除状态覆盖隐患) · Checkpoint(长任务恢复) · 路由函数化 |
| **OpenAI Agents SDK** | 极简核心 + Handoff 一等公民 + Input/Output Guardrails + 分层 Tracing(span 层级) | 统一 Guardrail 管道 · Handoff 协议 · 分层 Span · 单一 Runner 入口 |
| **PydanticAI** | `Agent[Deps, Output]` 泛型 + `@tool` 自动 schema + output_type Pydantic 校验 + RunContext.usage | 结构化输出校验 · 泛型 Context · 装饰器自动 schema · Token 归因 |
| **MetaGPT** | SOP 显式化 + Role/Action/Environment 三元抽象 + 消息发布订阅 + Watch-Think-Act | SOP 一等公民 · 角色抽象 · Message Bus(多 Agent 阶段) |
| **AutoGen v0.4** | 异步 Actor 模型 + 类型化消息 + `@message_handler` 装饰器 + Selector GroupChat | 类型化消息分发(渐进式) · Selector 调度模式 |
| **CrewAI** | 声明式 Role(role/goal/backstory) + Task.expected_output + Flows 装饰器状态机 | 声明式角色配置 · Task 期望输出校验 · 装饰器图构建 |

### 国内框架精华(办公场景特化)

| 平台 | 核心设计精华 | OfficeAgent 借鉴点 |
|------|------------|-------------------|
| **Dify**(开源标杆) | 蜂巢架构(微服务独立扩缩) + Knowledge Pipeline + Queue-based Graph Engine + Agent 节点零逻辑+策略插件化 + 抽象工厂模型路由 | 蜂巢化 · 知识管道 · 队列图引擎 · 推理策略可插拔 |
| **Coze 3.0** | 项目空间(多人多 Agent 协作) + 技能商店 + MCP 双向流通 + 多 Agent 接力 | 项目空间化 · 组织内技能市场 · MCP 暴露 |
| **智谱 GLM-4.5** | 思考/非思考模式动态切换 + All Tools(工具下沉模型层) + AutoGLM(GUI Agent) | 推理预算动态切换 · GUI 操作能力 |
| **ModelScope-Agent** | 工具库/工具检索/工具定制三层 + Memory 与 Prompt 管理分离 | 工具检索一等公民 · 三层工具架构 |
| **Qwen-Agent/AgentScope** | Function Call + ReAct 双模式 + Actor 模型分布式 + Pipeline 可组合 | 双调用模式 · Actor 多 Agent · 协作拓扑 |
| **腾讯元器** | MCP 双向支持 + 支付/计费一等公民 + 生态分发 | MCP 标准封装 · 计费原生 · IM 分发 |
| **百度文心** | 消息节点任意插入 + 一句话生成 Agent + 质量分析闭环 | 工作流消息推送 · 低门槛创建 |
| **国内共性** | 私有化部署默认 + 合规内建 + 国产模型深度适配 | 私有化优先 · 合规底座 · 多模型路由 |

---

## 一、OfficeAgent 现状基线(对照评估)

### 已具备(生产级,无需重做)

| 模块 | 文件 | 评估 |
|------|------|------|
| 推理引擎 | `core/reasoning/base.py` | ✅ 策略模式 `ReasoningEngine` + `ReasoningContext`,支持 ReAct/Plan&Execute/Self-Reflect |
| 图状态 | `graph/state.py` | ⚠️ `AgentState(TypedDict, total=False)` LangGraph 风格,但**无显式 reducer** |
| 工具执行 | `core/tools/executor.py` | ✅ serial/parallel/DAG(Kahn)+ 权限分级 + 超时 + 步数限制 + 双线程池隔离 |
| LLM 熔断 | `core/llm/circuit.py` | ✅ 三态熔断器(CLOSED/OPEN/HALF_OPEN),per-provider,生产级 |
| 多模型路由 | `core/llm/router.py` | ✅ 多 provider + 限流 + 缓存 + 计费 |
| 三层记忆 | `core/memory/manager.py` | ✅ Short/Long/Entity + embedder |
| 安全模块 | `core/security/` | ⚠️ injection/moderation/rbac/desensitize **分散未收敛** |
| 反思纠错 | `core/reflection/` | ✅ validator + replanner |
| 飞轮自学习 | `core/flywheel/` | ✅ 四阶闭环(感知/知识/反思/爬坡) |
| 拓扑图 | `core/topology/` | ✅ 知识拓扑网络 |
| 技能系统 | `core/skills/` | ✅ protocol + scheduler + feedback + levels |
| 观测埋点 | `core/observability/metrics.py` | ⚠️ 扁平记录,非分层 Span |
| 资产加密 | `assets/` | ✅ bundle/crypto/snapshot |

### 主要差距(必须补强)

1. **状态正确性**:`AgentState` 无显式 reducer,`messages/trace/tool_results` 隐式覆盖隐患
2. **安全收敛**:`security/` 各模块分散,未形成"每次 LLM 调用前后 Guardrail 管道"
3. **类型校验**:LLM 中间输出(plan/tool_call args)无 schema 校验,静默失败风险
4. **可恢复性**:无正式 Checkpointer,长任务中断无法断点续跑
5. **可观测分层**:`trace.py` 扁平记录,无 `Trace > AgentSpan > ToolSpan/LLMSpan` 层级
6. **执行入口分散**:graph builder / reasoning reason / orchestrator lifecycle 多入口耦合
7. **办公领域特化缺失**:无项目空间、无技能市场、无 MCP 暴露、无 Knowledge Pipeline
8. **多 Agent 协作未抽象**:当前单 Agent 为主,缺 Handoff/Message Bus/角色配置

---

## 二、升级总目标(顶级 OfficeAgent 定义)

一个"顶级 OfficeAgent"应同时满足:

1. **状态正确**:显式 reducer + checkpoint,任何任务可中断/恢复/回放,零状态丢失
2. **安全收敛**:Guardrail 管道贯穿每次 LLM 调用,tripwire 触发即短路+审计
3. **类型安全**:LLM 关键输出 Pydantic 校验,失败自动重试/降级,无静默错误
4. **可观测端到端**:分层 Span(trace_id 贯穿),任一请求可 replay,瓶颈可定位
5. **Office 顶级 + 办公生态**:L1 Office 专家能力深度做透(护城河) + L2 办公生态适度覆盖 + 项目空间化 + 组织技能市场 + Knowledge Pipeline
6. **诚实边界**:非 Office/非办公任务明确告知不擅长,不硬撑,维护专业信任
7. **可插拔扩展**:推理策略/模型/工具/角色全可插拔,核心零业务逻辑
8. **合规内建**:审计/脱敏/权限/备案作为平台底座,非外挂
9. **私有化优先**:全栈可本地部署,国产模型优先,数据自管

---

## 三、分阶段升级任务清单

> **优先级说明**:P0 = 生产关键(状态/安全/类型三补强);P1 = 体验关键(可观测/恢复/入口收敛);P2 = 领域差异化(办公特化);P3 = 进阶能力(多 Agent)

---

### 阶段 P0:状态/安全/类型三补强(生产关键,2 周)

> **目标**:消除"静默失败"与"状态丢失"两大隐患,让 Agent 在生产环境可信赖。
> **借鉴核心**:LangGraph 状态合并 · OpenAI Agents SDK Guardrail · PydanticAI 类型校验

#### P0-1 显式 Reducer 状态 Schema(借鉴 LangGraph)

| 项 | 内容 |
|---|---|
| 目标 | `AgentState` 字段声明合并语义(`messages/trace/tool_results` 追加,`goal/error` 覆盖),消除 `total=False` 默认覆盖 |
| 借鉴 | LangGraph `Annotated[list, add_messages]` |
| 落点 | [graph/state.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/graph/state.py) |
| 任务 | ① 定义 reducer 注册表(`add`/`replace`/`merge_dict`/自定义);② `AgentState` 字段改 `Annotated[T, reducer]`;③ 单测覆盖:多节点返回部分更新后状态正确合并 |
| 验收 | ① 现有 graph 测试全绿;② 新增 reducer 合并单测 ≥10 用例;③ `messages` 字段在 3 节点链路后内容完整不丢 |
| 依赖 | 无 |

#### P0-2 统一 Guardrail 管道(借鉴 OpenAI Agents SDK)

| 项 | 内容 |
|---|---|
| 目标 | 把 `security/injection.py`/`moderation.py`/`desensitize.py`/`rbac.py` 收敛为 `GuardrailPipeline`,在 `LLMRouter.chat()` 前后插入 input/output guardrails,tripwire 触发即短路+审计 |
| 借鉴 | OpenAI Agents SDK `input_guardrails`/`output_guardrails` + `GuardrailResult` |
| 落点 | 新增 `core/security/pipeline.py`;改造 [llm/router.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/llm/router.py) `chat()` 方法;现有 security 模块改造为 `BaseGuardrail` 子类 |
| 任务 | ① 定义 `BaseGuardrail` 抽象(`async def check(ctx) -> GuardrailResult`);② `GuardrailPipeline` 串行执行+短路;③ 4 个现有模块改造为 guardrail;④ `LLMRouter.chat()` 前后插入管道;⑤ tripwire 触发写 `audit_logs` |
| 验收 | ① 每次 LLM 调用必经 guardrail(代码审查);② 注入攻击输入被拦截+审计落库;③ 输出含敏感词被脱敏;④ 性能开销 < 5ms/次 |
| 依赖 | 无 |

#### P0-3 LLM 输出结构化校验(借鉴 PydanticAI)

| 项 | 内容 |
|---|---|
| 目标 | 为 LLM 关键输出(Plan/ToolCallDecision/FinalAnswer)定义 Pydantic Model,`_call_llm` 后强制校验,失败触发重试/降级而非静默继续 |
| 借鉴 | PydanticAI `output_type` + 自动重试 |
| 落点 | 新增 `core/reasoning/schemas.py`;改造 [reasoning/base.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/reasoning/base.py) `_call_llm` 与各 reason 实现 |
| 任务 | ① 定义 `PlanOutput`/`ToolCallDecision`/`FinalAnswer` Pydantic Model;② `_call_llm` 增加 `output_schema` 参数,JSON 解析+校验;③ 校验失败按重试策略处理(指数退避,最多 N 次);④ N 次仍失败降级为 text 模式 + 告警 |
| 验收 | ① LLM 返回畸形 JSON 时不再静默继续;② 校验失败有重试日志;③ 降级路径有告警;④ 单测覆盖畸形输入 |
| 依赖 | 无 |

#### P0-4 结构化重试策略(补全现有容错)

| 项 | 内容 |
|---|---|
| 目标 | 区分可重试错误(超时/429/网络)与不可重试错误(参数校验/权限拒绝),前者指数退避+抖动,后者立即失败;重试策略作为 Tool metadata 字段 |
| 借鉴 | PydanticAI 重试 + CrewAI Task 级配置 |
| 落点 | [tools/protocol.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/tools/protocol.py) `ToolMetadata` 加 `retry_policy` 字段;[tools/executor.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/tools/executor.py) 执行包装 |
| 任务 | ① 定义 `RetryPolicy(max_attempts, backoff, jitter, retryable_exceptions)`;② Tool metadata 声明;③ Executor 包装执行函数;④ 工具层补熔断(高频失败工具自动熔断) |
| 验收 | ① 超时工具按策略重试;② 权限拒绝立即失败不重试;③ 工具连续失败 N 次触发熔断 |
| 依赖 | 无 |

---

### 阶段 P1:可观测/可恢复/入口收敛(体验关键,2-3 周)

> **目标**:任一请求可 replay、长任务可恢复、执行入口单一收敛。
> **借鉴核心**:LangGraph Checkpoint · OpenAI Agents SDK Tracing · 单一 Runner

#### P1-1 分层 Tracing Span(借鉴 OpenAI Agents SDK)

| 项 | 内容 |
|---|---|
| 目标 | 统一为 `Trace > AgentSpan > (ToolSpan/LLMSpan/HandoffSpan)` 层级,每 span 有 parent_id/start/end/attributes/status;复用 `flywheel/trace.py` 升级 |
| 借鉴 | OpenAI Agents SDK span 层级 + LangGraph state 快照 |
| 落点 | [observability/metrics.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/observability/metrics.py) + [flywheel/trace.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/flywheel/trace.py) |
| 任务 | ① 定义 `Span`/`Trace` 数据类;② `start_span`/`end_span` 上下文管理器;③ 在 LLM 调用/工具执行/reasoning 步骤埋点;④ trace_id 贯穿 message/tool/reflection/audit/billing;⑤ 提供 `replay(trace_id)` 接口 |
| 验收 | ① 一次请求生成完整 span 树;② `replay(trace_id)` 可还原执行流程;③ 瓶颈 span 可定位(耗时/失败);④ 与 Prometheus 指标对齐 |
| 依赖 | P0-2(Guardrail 也需埋点) |

#### P1-2 Checkpoint 持久化与回放(借鉴 LangGraph)

| 项 | 内容 |
|---|---|
| 目标 | 定义 `BaseCheckpointer` 接口,实现 `PostgresCheckpointer`,每个 superstep 后快照 state;支撑长任务中断恢复/失败回滚/replay 调试 |
| 借鉴 | LangGraph `MemorySaver`/`SqliteSaver`/`PostgresSaver` |
| 落点 | 新增 `core/checkpoint/` 目录(`base.py`/`postgres.py`/`memory.py`);复用 [adapters/db/postgres.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/adapters/db/postgres.py) |
| 任务 | ① `BaseCheckpointer` 接口(`put`/`get`/`list`/`aget_state`/`update_state`);② `PostgresCheckpointer` 实现(新增 `agent_checkpoints` 表);③ `MemoryCheckpointer` 用于测试;④ graph 每次 superstep 后自动 put;⑤ 提供 `resume_from(checkpoint_id)` API |
| 验收 | ① 长任务中断后可从最后 checkpoint 恢复;② 失败可回滚到上一 superstep;③ replay 可从任意 checkpoint 起始;④ checkpoint 表有 TTL 清理 |
| 依赖 | P0-1(显式 reducer 保证状态可序列化) |

#### P1-3 Conditional Edge 动态路由(借鉴 LangGraph)

| 项 | 内容 |
|---|---|
| 目标 | 用 `router_fn(state) -> next_node` 替代手动 `should_continue` 布尔字段,路由逻辑集中可测 |
| 借鉴 | LangGraph `add_conditional_edges` |
| 落点 | [graph/edges.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/graph/edges.py) + [graph/builder.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/graph/builder.py) |
| 任务 | ① `add_conditional_edges(node, router_fn, mapping)` API;② router_fn 接收 state 返回节点名或 `END`;③ 现有 `should_continue` 改造为 router 函数;④ 单测覆盖路由分支 |
| 验收 | ① 路由逻辑可独立测试;② 现有 graph 行为不变;③ 新增条件分支用例通过 |
| 依赖 | P0-1 |

#### P1-4 单一 Runner 入口(借鉴 OpenAI Agents SDK)

| 项 | 内容 |
|---|---|
| 目标 | 定义 `AgentRunner.run(input, context) -> RunResult` 作为对外唯一执行入口,内部协调 graph + reasoning + tools + memory + checkpoint,避免执行逻辑散落 router/service |
| 借鉴 | OpenAI Agents SDK `Runner.run()` |
| 落点 | 新增 `core/runner.py`;整合 [orchestrator/lifecycle.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/orchestrator/lifecycle.py) |
| 任务 | ① `AgentRunner` 类封装 graph/registry/checkpointer;② `run(input, context)` 统一入口;③ `RunResult` 含 answer/trace/usage/checkpoint_id;④ `chat.py` router 改为调 Runner;⑤ 保留 legacy 模式兼容 |
| 验收 | ① 所有执行路径经 Runner;② `RunResult` 含完整 trace/usage;③ 现有 API 行为不变;④ legacy 模式可切换 |
| 依赖 | P1-1, P1-2 |

#### P1-5 Token/Cost 归因(借鉴 PydanticAI)

| 项 | 内容 |
|---|---|
| 目标 | `RunContext` 携带 `usage` 累加器,每次 LLM 调用累加 input/output tokens 与成本,reasoning 结束随 `ExecutionTrace` 返回,实现成本归因到任务/用户 |
| 借鉴 | PydanticAI `RunContext.usage` |
| 落点 | [reasoning/base.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/reasoning/base.py) `ReasoningContext` 加 `usage` 字段;整合 [llm/billing.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/llm/billing.py) |
| 任务 | ① `Usage` 数据类(input_tokens/output_tokens/cost);② ReasoningContext 携带;③ LLM 调用后累加;④ RunResult 返回总 usage;⑤ 与 `billing_records` 表对齐 |
| 验收 | ① 单次任务 usage 准确;② 多次 LLM 调用累计正确;③ billing 表落库一致 |
| 依赖 | P1-1, P1-4 |

---

### 阶段 P2:Office 顶级专家 + 办公生态覆盖(护城河,4-5 周)

> **目标**:按"专注两层"定位,① 深度做透 L1 Office 专家能力(护城河)② 适度覆盖 L2 办公生态 ③ 设计诚实边界 ④ 项目空间化+技能市场+Knowledge Pipeline+蜂巢化。
> **业务架构**:
> ```
>                    ┌─────────────────────┐
>                    │  通用对话内核(LLM) │  ← 理解任意任务、规划、闲聊
>                    └──────────┬──────────┘
>                               │
>                ┌──────────────┴──────────────┐
>                ▼                             ▼
>         ┌─────────────┐              ┌─────────────┐
>         │ L1 Office   │              │ L2 办公生态 │
>         │ 专家层★护城河★              │ (适度覆盖)  │
>         ├─────────────┤              ├─────────────┤
>         │ Word/Excel/ │              │ 邮件/日程/  │
>         │ PPT/PDF/    │              │ 会议/审批/  │
>         │ 转换/解析/  │              │ IM推送/     │
>         │ 图表/模板/  │              │ 项目协作/   │
>         │ 检索/引用   │              │ 知识库      │
>         └─────────────┘              └─────────────┘
>           深度做透                      适度覆盖
> ```
> **越界处理**:非 Office/非办公任务 → Agent 诚实告知"不擅长"+建议专用工具,不硬撑
> **借鉴核心**:Coze 项目空间 · Dify 蜂巢+Knowledge Pipeline · ModelScope 工具检索 · 智谱 GLM 双模式

#### P2-1 项目空间化(借鉴 Coze 3.0)

| 项 | 内容 |
|---|---|
| 目标 | 把会话/文档/技能/审批沉淀到"项目容器",支持多人多 Agent 协作;办公天然项目制(季度报告/合同评审/会议纪要系列) |
| 借鉴 | Coze 3.0 Project Space |
| 落点 | 新增 `core/project/` 目录;新增 `projects`/`project_members`/`project_assets` 表;改造 sessions/documents 关联 project_id |
| 任务 | ① `Project` 领域模型;② CRUD API;③ 成员权限(Owner/Editor/Viewer);④ 资产关联(会话/文档/技能/审批);⑤ 前端项目空间视图 |
| 验收 | ① 可创建项目并邀请成员;② 项目内资产隔离;③ 跨项目资产不串;④ 项目可归档 |
| 依赖 | 无 |

#### P2-2 组织内技能市场(借鉴 Coze Skill)

| 项 | 内容 |
|---|---|
| 目标 | 行政/法务/财务各自封装 Skill(报销流程/合同审查/财报生成),组织内共享+成本核算;不搞个人变现,改组织内共享 |
| 借鉴 | Coze Skill Store + 现有 `core/skills/` |
| 落点 | 扩展 [core/skills/](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/skills/);新增 `skill_market`/`skill_installations` 表;前端技能市场页 |
| 任务 | ① Skill 发布/版本/审核流程;② 组织内安装/卸载;③ Skill 调用计费归因;④ Skill 权限分级(公开/部门/私有);⑤ 与现有 `skill_bindings.yaml` 整合 |
| 验收 | ① 可发布 Skill 到组织市场;② 成员可安装调用;③ 调用计费归因到发布者/调用者;④ 权限分级生效 |
| 依赖 | P2-1(技能归属项目或组织) |

#### P2-3 MCP 消费接入办公生态(借鉴腾讯元器/Coze)

| 项 | 内容 |
|---|---|
| 目标 | 通过 MCP 客户端接入办公生态第三方服务(企微/飞书/钉钉/邮件/日程 API),不自己实现每个 IM;Office 能力选择性以 MCP 暴露给内部调用 |
| 借鉴 | 腾讯元器 MCP + Coze MCP(聚焦办公生态接入,不做通用扩展市场) |
| 落点 | 新增 `core/mcp/` 目录(`client.py`/`registry.py`/`server.py`);改造 `tools/registry.py` 支持外部 MCP 注册 |
| 任务 | ① MCP Client 消费外部办公生态 MCP(企微/飞书/钉钉);② 自动注册外部 MCP 为内部 tool;③ Office 核心能力选择性 MCP 暴露(供内部子 Agent 调用);④ 鉴权(组织内 API Key);⑤ 不做通用 MCP 市场,只接办公生态 |
| 验收 | ① 可接入飞书/企微 MCP 发消息;② Office 能力可被内部调用;③ 鉴权生效;④ 拒绝非办公类 MCP 注册 |
| 依赖 | 无 |

#### P2-4 工具两层架构 + 检索(借鉴 ModelScope-Agent)

| 项 | 内容 |
|---|---|
| 目标 | 工具按 L1 Office 专家 / L2 办公生态两层分类管理 + 工具检索(按意图动态选 top-k);避免全塞 system prompt;**不做 L3 通用扩展层** |
| 借鉴 | ModelScope-Agent 工具检索(两层简化版) |
| 落点 | 改造 [tools/registry.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/tools/registry.py);新增 `tools/retriever.py`(基于 embedding 检索工具);工具 metadata 加 `layer: L1_office/L2_workspace` 字段 |
| 任务 | ① 工具元数据补 `description_embedding` + `layer` 字段;② `ToolRetriever` 按用户意图检索 top-k 工具;③ 只把 top-k 工具注入 prompt(节省 token);④ 两层来源标记(office/workspace);⑤ 组织自定义工具仅限办公生态 API |
| 验收 | ① 工具数 > 50 时 prompt 不膨胀;② 检索准确率 > 85%;③ 两层标记可追溯;④ 拒绝非办公类工具注册 |
| 依赖 | 无 |

#### P2-5 Knowledge Pipeline(借鉴 Dify 1.9.0)

| 项 | 内容 |
|---|---|
| 目标 | 办公文档预处理流水线:OCR→格式解析→分块→实体抽取→权限标记→embedding,可编排可观测 |
| 借鉴 | Dify Knowledge Pipeline |
| 落点 | 新增 `core/knowledge/pipeline.py`;扩展 [retrieval/](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/retrieval/) |
| 任务 | ① 定义 `PipelineStep` 抽象;② 实现 6 个步骤(OCR/parse/chunk/extract/permission/embed);③ YAML 声明管道;④ 步骤可观测(每步耗时/成功/失败);⑤ 与 `knowledge_chunks` 表对齐 |
| 验收 | ① 上传 docx/pdf 自动走管道;② 每步可观测;③ 管道可定制(YAML);④ 失败可重试单步 |
| 依赖 | 无 |

#### P2-6 推理策略可插拔(借鉴 Dify Agent 节点零逻辑)

| 项 | 内容 |
|---|---|
| 目标 | 推理策略(快/慢/省钱/精准/合规优先)作为可插拔策略,核心不写死推理逻辑;Agent 节点零推理逻辑 |
| 借鉴 | Dify Agent 节点 + 现有 `reasoning/selector.py` |
| 落点 | 改造 [reasoning/selector.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/reasoning/selector.py);新增 `reasoning/strategies/` |
| 任务 | ① `BaseStrategy` 抽象;② 实现 Fast/Cheap/Precise/Compliance 策略;③ 策略选择可配置(YAML/动态);④ 策略可热插拔;⑤ 与模型路由联动(合规策略强制国产备案模型) |
| 验收 | ① 策略可配置切换;② 合规策略强制国产模型;③ 策略选择有日志;④ 新策略可热加载 |
| 依赖 | P0-3 |

#### P2-7 蜂巢化部署(借鉴 Dify 蜂巢架构)

| 项 | 内容 |
|---|---|
| 目标 | 文档解析/RAG/LLM 调用/工具执行/审批网关独立部署独立扩缩容,一个慢节点不拖垮全局 |
| 借鉴 | Dify Honeycomb Architecture |
| 落点 | [deploy/docker/docker-compose.prod.yml](file:///e:/Officeagent/OFFICEAGENT/deploy/docker/docker-compose.prod.yml);[deploy/helm/](file:///e:/Officeagent/OFFICEAGENT/deploy/helm/) |
| 任务 | ① 拆分服务(doc-parser/knowledge/agent-runner/tool-executor);② 独立 HPA;③ 服务间通信用 gRPC/HTTP;④ 队列化(Celery/RabbitMQ)解耦;⑤ 独立监控面板 |
| 验收 | ① 单服务可独立扩缩;② 一个服务挂不影响其他;③ 队列积压有告警;④ 监控分服务面板 |
| 依赖 | P1-1(观测先行) |

#### P2-8 思考/非思考模式动态切换(借鉴智谱 GLM-4.5)

| 项 | 内容 |
|---|---|
| 目标 | 写邮件用非思考模式快速响应,财务分析用思考模式深度推理,单模型内动态切换;按任务复杂度路由 |
| 借鉴 | 智谱 GLM-4.5 双模式 |
| 落点 | [llm/router.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/llm/router.py);[reasoning/selector.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/reasoning/selector.py) |
| 任务 | ① 模型能力 metadata 加 `supports_think_mode`;② 路由器按任务复杂度选模式;③ 复杂度评估器(基于意图/历史);④ 成本/延迟对比看板 |
| 验收 | ① 简单任务走非思考模式延迟低;② 复杂任务走思考模式质量高;③ 模式选择有日志 |
| 依赖 | P2-6 |

#### P2-9 L1 Office 专家能力深化(护城河核心)

| 项 | 内容 |
|---|---|
| 目标 | 把现有 `business/word/converter/search` 升级为顶级 Office 专家能力:格式全覆盖 + 操作细粒度 + 端到端工作流 + 质量零损失。这是 OfficeAgent 区别于通用助手的护城河,必须做到竞品(豆包/文心/通义)做不到的深度 |
| 定位 | L1 Office 专家层(护城河,深度做透) |
| 落点 | 重组 [business/](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/business/) 为 `office/` + `research/` 子目录 |
| 任务 | ① **Word 深度**:样式/批注/目录/页眉页脚/修订/模板/文档对比;<br>② **Excel 深度**:公式/透视表/图表/数据清洗/多表合并;<br>③ **PPT 深度**:模板/排版/演讲稿/动画;<br>④ **PDF 深度**:生成/解析/表单/签名/水印;<br>⑤ **格式转换**:docx/pdf/md/html/txt/latex/odt 双向零损失;<br>⑥ **文档解析**:OCR/表格抽取/公式识别/版面分析(多模态);<br>⑦ **图表生成**:科研图/商业图/数据可视化;<br>⑧ **模板引擎**:论文/简历/报告/合同模板;<br>⑨ **论文检索**:arXiv/知网/万方 + 引用管理(BibTeX/GB-T7714) + 文献综述;<br>⑩ **端到端工作流**:搜论文→下载→总结→生成 Word→转 PDF→发邮件 一键完成 |
| 验收 | ① 格式转换零损失(样式/公式/批注保留);② 操作粒度到段落/单元格/元素级;③ 端到端工作流跑通;④ 至少 1 项能力(如 Word 修订/PDF 表单)明显优于通用助手 |
| 依赖 | 无(可与 P2 其他任务并行) |

#### P2-10 L2 办公生态覆盖(适度,不追求极致)

| 项 | 内容 |
|---|---|
| 目标 | 覆盖办公场景天然延伸的能力,做到"能用即可",不追求 OA 系统级深度;优先通过 MCP 接入第三方(飞书/企微/钉钉),减少自研 |
| 定位 | L2 办公生态层(适度覆盖,不深做) |
| 落点 | 新增 `business/workspace/` 目录(`mail/schedule/meeting/approval/im/knowledge`) |
| 任务 | ① **邮件**:起草/发送/回复/摘要(自研,轻量);<br>② **日程**:创建/查询/提醒(接日历 API);<br>③ **会议**:纪要生成/待办提取/跟进(基于 LLM);<br>④ **审批**:简单审批流/通知/记录(不建复杂 BPM);<br>⑤ **IM 推送**:企微/飞书/钉钉消息推送(走 MCP 接入,不自研 SDK);<br>⑥ **项目协作**:复用 P2-1 项目空间;<br>⑦ **知识库**:复用 P2-5 Knowledge Pipeline |
| 验收 | ① 邮件可起草发送;② IM 可推送消息;③ 会议纪要可生成;④ 审批通知可用;⑤ **明确不做的**:复杂 OA 流程/ERP/CRM 等深度业务系统 |
| 依赖 | P2-1, P2-3(MCP), P2-5(Knowledge Pipeline) |

#### P2-11 诚实边界设计(非 Office/非办公任务处理)

| 项 | 内容 |
|---|---|
| 目标 | Agent 遇到非 Office/非办公任务(天气/航班/股票/订餐/写代码等)时,诚实告知"不擅长"+建议专用工具,不硬撑装会;维护专业信任,避免用户期望错位 |
| 定位 | 跨层(意图识别 + 响应策略) |
| 落点 | 改造 [reasoning/selector.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/reasoning/selector.py);新增 `core/boundary.py`(能力边界声明);system prompt 注入能力声明 |
| 任务 | ① **能力声明**:配置文件声明 Office 强项 + 办公生态 + 明确不擅长领域;<br>② **意图评估器**:基于工具检索结果置信度判断任务是否在能力圈内;<br>③ **三类响应策略**:强项(深度执行)/ 相邻(尽力执行+提示)/ 越界(诚实告知+建议);<br>④ **system prompt 注入**:"你是 Office 专家助手,擅长文档/表格/PDF/办公协作,非办公任务请诚实告知用户";<br>⑤ **越界日志**:记录越界请求用于分析是否需要扩展能力 |
| 验收 | ① 问"帮我订机票"→ 诚实告知不擅长 + 建议;② 问"帮我写 Word"→ 深度执行;③ 问"帮我查团队日程"→ 尽力执行;④ 越界请求有日志可分析 |
| 依赖 | P2-4(工具检索提供置信度) |

---

### 阶段 P3:多 Agent 协作(进阶,按需推进)

> **目标**:在单 Agent 足够强后,按业务需求渐进引入多 Agent,避免过早过度工程化。
> **借鉴核心**:OpenAI Handoff · MetaGPT Watch-Think-Act · AutoGen Actor · AgentScope Pipeline

#### P3-1 类型化消息 + Handoff 协议(借鉴 OpenAI Agents SDK + AutoGen)

| 项 | 内容 |
|---|---|
| 目标 | 定义类型化消息(`SearchRequest`/`DocEditCommand`)替代扁平 role+content;Handoff 协议声明 `handoffs: list[AgentRef]`,LLM 输出 handoff 时 Runner 自动转接并传递 history/trace |
| 借鉴 | OpenAI Agents SDK Handoff + AutoGen 类型化消息 |
| 落点 | 改造 [core/types.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/types.py);新增 `core/handoff.py` |
| 任务 | ① 类型化消息基类;② Handoff 协议;③ Runner 集成 handoff 处理;④ context(history/trace)传递;⑤ 审计 handoff 链路 |
| 验收 | ① handoff 自动转接;② 上下文完整传递;③ handoff 链路可审计 |
| 依赖 | P1-4(Runner) |

#### P3-2 声明式角色配置(借鉴 CrewAI)

| 项 | 内容 |
|---|---|
| 目标 | `config/roles/*.yaml` 定义 role/goal/backstory/constraints/tools,ReasoningContext 启动时加载注入 system prompt,支持按用户/部门定制 |
| 借鉴 | CrewAI 声明式 Role |
| 落点 | 新增 `config/roles/`;改造 [prompt/builder.py](file:///e:/Officeagent/OFFICEAGENT/src/officeagent/core/prompt/builder.py) |
| 任务 | ① 角色 YAML schema;② 角色加载器;③ system prompt 注入;④ 按用户/部门定制;⑤ 角色版本管理 |
| 验收 | ① YAML 可定义角色;② 角色注入 prompt 生效;③ 部门定制隔离 |
| 依赖 | 无 |

#### P3-3 SOP 一等公民(借鉴 MetaGPT)

| 项 | 内容 |
|---|---|
| 目标 | 把办公流程(Word 编辑/格式转换/检索)提升为可声明、可版本化的 SOP 对象,与执行引擎分离;SOP = 有序 Action 列表 + 每步 expected_output schema |
| 借鉴 | MetaGPT SOP 显式化 |
| 落点 | 新增 `core/sop/`;新增 `config/sops/` |
| 任务 | ① `SOP`/`Action`/`ExpectedOutput` 数据类;② YAML 声明 SOP;③ SOP 执行器;④ SOP 版本管理;⑤ 与 graph 整合(SOP 可编译为子图) |
| 验收 | ① SOP 可 YAML 定义;② SOP 可执行;③ SOP 可版本化;④ SOP 编译为子图 |
| 依赖 | P1-3, P1-4 |

#### P3-4 多 Agent 消息总线(借鉴 MetaGPT + AutoGen)

| 项 | 内容 |
|---|---|
| 目标 | Role 订阅感兴趣的 Action 产出,Environment 路由消息,避免 Agent 间硬编码互调;Watch-Think-Act 生命周期 |
| 借鉴 | MetaGPT Message Bus + AutoGen Subscription |
| 落点 | 新增 `core/multiagent/`(`environment.py`/`messagebus.py`/`role.py`) |
| 任务 | ① `MessageBus` 发布订阅;② `Role` Watch-Think-Act 生命周期;③ `Environment` 路由;④ 与现有 reasoning 引擎整合(Role 内部调 reasoning);⑤ 多 Agent trace 贯穿 |
| 验收 | ① Role 可订阅;② 消息正确路由;③ 多 Agent 协作完成复杂任务;④ trace 贯穿所有 Agent |
| 依赖 | P3-1, P3-2, P3-3 |

---

## 四、关键技术决策(不可妥协)

1. **不引入 langchain 依赖**:借鉴 LangGraph 设计思想但自实现轻量版,保持 `core/types.py` 独立
2. **不绑定单一模型**:多 provider 路由是底线,合规场景强制国产备案模型
3. **不冒进多 Agent**:先做强单 Agent,多 Agent 按业务需求渐进
4. **不外挂合规**:审计/脱敏/权限作为平台底座,Guardrail 管道贯穿每次调用
5. **不放弃私有化**:全栈可本地部署,数据自管,国产模型优先
6. **不写死业务逻辑**:核心引擎零业务逻辑,办公能力以 Tool/SOP/Skill 形式注册
7. **不做通用扩展(业务定位红线)**:专注 L1 Office 顶级专家 + L2 办公生态两层,非办公任务诚实告知不擅长,不硬撑装会;拒绝通用 MCP 市场定位
8. **不浅做 Office(护城河红线)**:L1 Office 必须深度做透(格式零损失/操作细粒度/端到端工作流),做到竞品做不到的深度,这是 OfficeAgent 的存在意义

---

## 五、任务依赖关系图

```
P0-1 显式 Reducer ─┬─→ P1-2 Checkpoint
                   ├─→ P1-3 Conditional Edge
                   └─→ P1-4 Runner(依赖 P1-1, P1-2)
P0-2 Guardrail ────→ P1-1 分层 Tracing
P0-3 结构化校验 ───→ P2-6 推理策略可插拔
P0-4 重试策略 ──────→ (独立)

P1-1 Tracing ──────→ P1-5 Token 归因(依赖 P1-4)
P1-4 Runner ───────→ P3-1 Handoff

P2-1 项目空间 ─────┬─→ P2-2 技能市场
                   └─→ P2-10 办公生态(依赖 P2-3, P2-5)
P2-3 MCP ──────────→ P2-10 办公生态
P2-4 工具两层检索 ─→ P2-11 诚实边界(依赖置信度)
P2-6 推理策略 ─────→ P2-8 思考模式切换
P2-9 Office 深化 ──→ (独立,护城河核心,可与 P2 其他并行)

P3-1 Handoff ──────→ P3-4 消息总线
P3-2 角色 ─────────→ P3-4 消息总线
P3-3 SOP ──────────→ P3-4 消息总线
```

---

## 六、验收里程碑

| 里程碑 | 完成阶段 | 验收标准 |
|--------|---------|---------|
| M1 生产可信 | P0 完成 | ① 状态合并零丢失;② Guardrail 全覆盖;③ LLM 输出校验;④ 重试策略生效 |
| M2 体验可信 | P1 完成 | ① 任一请求可 replay;② 长任务可恢复;③ 单一 Runner 入口;④ 成本归因准确 |
| M3 领域差异化 | P2 完成 | ① Office 专家能力深化(至少1项优于通用助手);② 办公生态可用(邮件/IM/会议);③ 诚实边界生效(越界任务诚实告知);④ 项目空间可用;⑤ 技能市场可发布;⑥ MCP 接入办公生态;⑦ Knowledge Pipeline 跑通;⑧ 蜂巢化部署 |
| M4 多 Agent | P3 完成 | ① Handoff 协议;② 声明式角色;③ SOP 一等公民;④ 多 Agent 消息总线 |

---

## 七、风险与对策

| 风险 | 对策 |
|------|------|
| Reducer 改造引发现有 graph 行为变化 | 全量回归测试 + 渐进迁移(新字段先 reducer,老字段保持兼容) |
| Guardrail 性能开销 | 异步并行执行 + 短路优化 + 性能预算 < 5ms |
| Checkpoint 序列化大对象 | 增量快照 + 大对象引用 + TTL 清理 |
| MCP 暴露安全风险 | API Key 鉴权 + 速率限制 + 审计全量 |
| 蜂巢化拆分成本 | 渐进式:先拆 doc-parser(独立进程),验证后再拆其他 |
| 多 Agent 过早过度工程化 | P3 严格按需推进,每个 Handoff 必须有明确业务场景 |

---

## 八、与现有计划文档的关系

| 文档 | 关系 |
|------|------|
| [ARCHITECTURE.md](file:///e:/Officeagent/OFFICEAGENT/ARCHITECTURE.md) | 总体架构基线,本计划在其上补强 |
| [OFFICEAGENT_TECH_PLAN_V2.md](file:///e:/Officeagent/OFFICEAGENT/OFFICEAGENT_TECH_PLAN_V2.md) | 落地计划 v2,本计划是其"顶级升级"补充 |
| [SELF_EVOLUTION_AGENT_PLAN.md](file:///e:/Officeagent/OFFICEAGENT/SELF_EVOLUTION_AGENT_PLAN.md) | 自进化飞轮设计,本计划 P0/P1 补强其基础设施 |

本计划聚焦"借鉴顶级框架健壮代码设计",与现有计划互补,不重复已有内容。

---

## 九、研究来源

### 国外框架(代码设计借鉴)
- MetaGPT: https://github.com/geekan/MetaGPT (38K★)
- AutoGen/AG2: https://github.com/microsoft/autogen (54K★)
- OpenAI Agents SDK: https://github.com/openai/openai-agents-python
- CrewAI: https://github.com/crewAIInc/crewAI (41K★)
- LangGraph: https://github.com/langchain-ai/langgraph
- PydanticAI: https://github.com/pydantic/pydantic-ai

### 国内框架(办公场景借鉴)
- Dify(开源): https://github.com/langgenius/dify
- ModelScope-Agent: https://github.com/modelscope/modelscope-agent
- AgentScope: https://github.com/modelscope/agentscope
- Coze 3.0 / 智谱 GLM-4.5 / 百度文心 / 腾讯元器 / 字节豆包:公开技术博客

### 综合对比文章
- 《LangChain vs CrewAI vs AutoGen:三大 Agent 框架可靠性横评》
- 《2026 主流 Agent 框架全景对比》
- 《深度测评:AutoGen、CrewAI、MetaGPT 和 LangGraph 的横向对比》
- 《2026 年权威 AI Agent 平台横评》
