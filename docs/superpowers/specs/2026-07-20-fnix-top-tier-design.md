# FnixAgent 顶级能力设计方案（方案 D — 融合顶级）

**日期**：2026-07-20
**作者**：FnixAgent Team
**状态**：Spec（待用户审查 → writing-plans）
**关联**：[FnixAgent-完整计划总汇](file:///C:/Users/liuyi/Desktop/FnixAgent-完整计划总汇.md)、[项目记忆五大壁垒](file:///c:/Users/liuyi/.trae-cn/memory/projects/-e-FNIX-FnixAgent/project_memory.md)

---

## 0. 背景与目标

用户要求："确保项目内所有设计部分都可以真实的发挥作用 + 上网用 DDG 查询大量 agent 能力提升、产品质量、UX、过程可视化资料 + 对标 ChatGPT/Cursor/Trae + 自己思考其他可提升方向 + 设计一个非常顶级的方案"。

用户最终决策："吸收可以吸收的优势 + 发扬我的优势 + 打造顶级能力"。

本方案据此设计为三层结构：激活 → 选择性吸收 → 强化壁垒。

---

## 1. 项目盘点结论

### 1.1 P0 — 核心承诺未兑现

| # | 问题 | 证据 |
|---|---|---|
| 1 | `/api/v1/chat/*` 旁路 9 步流水线 | [chat.py](file:///e:/FNIX/FnixAgent/src/fnixagent/api/routers/chat.py) `_build_agent_loop_for_stream()` 直接构造 AgenticLoop，无 KTG/STP/MFP/mission/evolution |
| 2 | MCP / Skills / Memory 三套 API 路由全缺失 | 无 `routers/{mcp,skills,memory}.py`；[MemoryExplorer.tsx](file:///e:/FNIX/FnixAgent/apps/workbench/src/components/MemoryExplorer.tsx) 存在但主壳不渲染 |
| 3 | fnix-evolution Rust crate 编译失败 | `error[E0432]: unresolved import crate::synthesis / criteria_evolver` |

### 1.2 P1 — Dead code 影响可信度

| # | 模块 | 状态 |
|---|---|---|
| 4 | DurableExecutionManager | 仅 `core/agent/` 内部互引用，主路径走 RunCheckpointStore |
| 5 | MemoryOS | 仅 `core/intelligence/` 3 文件互引用，主路径用 MemoryManager |
| 6 | EvolutionMaster | 仅作 `ImportError` fallback，主路径优先 MFP |
| 7 | pyo3-bridge | `rust_ext/probe.py` 只做存在性探测，未调用任何 Rust 函数 |

### 1.3 P2 — 前端清理

| # | 模块 | 状态 |
|---|---|---|
| 8 | ModelPicker / OpenAiGlyph / runStore | 主壳未直接使用 |

---

## 2. 调研要点（7 篇关键文章）

| 来源 | 关键洞察 | 是否吸收 |
|---|---|---|
| OpenAI Codex agent loop | 协调用户/模型/工具三者；App Server 双向 JSON-RPC，原生 streaming progress / tool use / approvals / diffs | ✅ Spec 2 过程可视化 |
| Taskade Reflection Loop | 内在自我批评失败（coherence trap）；grounded reflection 才有效；独立 Critic Agent > self-reflection | ✅ Spec 5 Reflection |
| Claude Code Compaction | context 有限工作记忆；compaction 时 load-bearing state 要 by design 存活 | ✅ Spec 4 长程任务 |
| ByteDance DeerFlow | 长程 SuperAgent 4 支柱：isolated sandboxes / persistent memory / delegated sub-agent / modular skill library | ✅ Spec 4 长程任务 |
| Cursor Agent Mode 2026 | 子代理 + Plan Mode + /multitask + Cloud Agents + Worktrees；Composer stateless 是痛点 | ⚠️ Spec 6 部分吸收 |
| CLAUSE + KG-Agent（神经符号） | context construction 作为 sequential decision；三代理框架；stateful API + RL 导航动态知识图 | ✅ Spec 5 神经符号 |
| ChatGPT Canvas vs Claude Artifacts | Canvas = 协同编辑环境；Artifacts = side panel 预览；Claude 总是重写，ChatGPT 增量更好 | ✅ Spec 3 Artifact Canvas |

**对标优势中不吸收的项**：
- ❌ Cursor Cloud Agents VM — 与 Fnix 本地优先原则矛盾
- ❌ Cursor Worktrees — 与 Fnix `.fnix/artifacts` 模型冲突

---

## 3. 方案 D 三层架构

### 第一层：激活（必做基石）

让现有所有设计真正发挥作用。详见 Spec 1。

### 第二层：选择性吸收对标优势

| # | 对标 | 吸收 | 理由 | Spec |
|---|---|---|---|---|
| 2.1 | Codex | ✅ streaming token + tool call card + diff 即时预览 + 思考链折叠 | 过程可见性是真需求 | Spec 2 |
| 2.2 | ChatGPT Canvas | ✅ Work Results 升级为协同编辑 Canvas | 用户能改产物价值高 | Spec 3 |
| 2.3 | Claude Code | ✅ Compaction + 跨会话摘要 + load-bearing state by design | 长程任务核心 | Spec 4 |
| 2.4 | Reflexion 论文 | ✅ 独立 Critic Agent 替代裸 self-reflect | grounded reflection 已证实有效 | Spec 5 |
| 2.5 | Cursor /multitask | ⚠️ 部分吸收（已有 work_jobs，强化并行可视化） | 多任务并行已有半成品 | Spec 6 |
| 2.6 | Cursor Cloud Agents VM | ❌ 不吸收 | Fnix 本地优先原则 | — |
| 2.7 | Cursor Worktrees | ❌ 不吸收 | 与 .fnix/artifacts 模型冲突 | — |

### 第三层：发扬 Fnix 独有壁垒

项目记忆里的五大不可替代壁垒全数强化。

| # | 壁垒 | 实现 | Spec |
|---|---|---|---|
| 3.1 | 8h 长程 | resume_from_checkpoint 全链路 + DeerFlow 级 memory graph + 8h 任务进度可视化 | Spec 4 |
| 3.2 | 代码图谱 | fnix-pdg Rust crate 通过 pyo3 真正接入 + PDG 力导向图前端可视化 | Spec 5 |
| 3.3 | 四维闭环 | DAAO + VMAO + HERA + Self-Optimizing 真触发（非 dead code） | Spec 7 |
| 3.4 | 神经符号 | KTG → CLAUSE 式 dynamic context construction（三代理：expander / navigator / critic） | Spec 5 |
| 3.5 | Rust 原生 | fnix-se workspace 编译通过 + pyo3-bridge 接入热点（PDG/AST/vector） | Spec 1 + Spec 5 |

**UI 差异化**：过程可视化走极简新中式宋韵风（不抄 ChatGPT 灰圆角，做留白 + 青灰 + 细线轴）。

---

## 4. Sub-specs 拆分（按优先级）

| Spec | 范围 | 优先级 | 状态 |
|---|---|---|---|
| **Spec 1** | 第一层激活（1.1-1.8 全部） | P0 最优先 | 本文档详述 |
| Spec 2 | 过程可视化升级（2.1 + 3.5 UI 差异化） | P1 | 骨架 |
| Spec 3 | Artifact Canvas（2.2） | P1 | 骨架 |
| Spec 4 | 长程任务 + Compaction + Checkpoint resume（2.3 + 3.1） | P1 | 骨架 |
| Spec 5 | Reflection Loop + 神经符号 PDG（2.4 + 3.4 + 3.2） | P2 | 骨架 |
| Spec 6 | 多任务并行可视化（2.5） | P2 | 骨架 |
| Spec 7 | 四维闭环真触发（3.3） | P2 | 骨架 |

每个 sub-spec 走独立 design → plan → 实现循环。本文档详述 Spec 1，其他 Spec 仅留骨架待后续展开。

---

# Spec 1 — 激活层详细设计

## S1.1 总体目标

让项目宣称的所有设计真正发挥作用：8 项摆设/半生效/缺失全部接通主流程或清理。

## S1.2 子项设计与文件级改动

### S1.2.1 chat.py 复用 work_pipeline 9 步

**当前问题**：[chat.py](file:///e:/FNIX/FnixAgent/src/fnixagent/api/routers/chat.py) `_build_agent_loop_for_stream()` 直接构造 AgenticLoop，旁路 KTG/STP/MFP/mission/evolution。

**设计**：
- `/api/v1/chat/stream` 改为调 `work_pipeline.run_work_stream(work_mode="ask")`
- 保留 chat 现有 schema（user_id, message, attachments 等），内部转 work_pipeline 入参
- chat 模式与 work 模式区别仅在 `work_mode`：chat=ask，work=user 指定
- 保留 `/api/v1/chat/messages` 等非流式接口不变

**改动文件**：
- `src/fnixagent/api/routers/chat.py` — 重写 `_build_agent_loop_for_stream` 为 `run_work_stream` 包装
- 测试：`tests/api/test_chat.py` 验证 evolution chunk 出现

**验证**：
- `curl -N -X POST /api/v1/chat/stream` 流式响应中包含 `evolution` chunk
- chat 模式跑任务后 EvolutionPanel 显示 KTG/STP/MFP 数据

### S1.2.2 MCP HTTP 路由

**当前问题**：MCP server 仅 CLI 启动，无 HTTP API 暴露已连接 server。

**设计**：
- 新增 `src/fnixagent/api/routers/mcp.py`
- 3 个端点：
  - `GET /api/v1/mcp/servers` — 已连接 server 列表 + 状态
  - `GET /api/v1/mcp/servers/{id}/tools` — 某 server 工具列表
  - `POST /api/v1/mcp/servers/refresh` — 重新加载 mcp.json
- 复用 `harness.config.attach_mcp_tools_to_registry` 的内部状态
- `main.py:290` 附近 `include_router(mcp_router)`

**改动文件**：
- `src/fnixagent/api/routers/mcp.py` — 新建
- `src/fnixagent/main.py` — 注册路由
- `src/fnixagent/harness/config.py` — 暴露 `list_mcp_servers()` 函数

**验证**：
- `curl /api/v1/mcp/servers` 返回 JSON 数组
- 前端 OaiSettings MCP section 显示已连接 server

### S1.2.3 Skills HTTP 路由

**当前问题**：[core/skills/market.py](file:///e:/FNIX/FnixAgent/src/fnixagent/core/skills/market.py) 实现完整 draft→review→publish，但无 API。

**设计**：
- 新增 `src/fnixagent/api/routers/skills.py`
- 6 个端点：
  - `GET /api/v1/skills` — 已发布技能列表
  - `GET /api/v1/skills/drafts` — 草稿列表
  - `POST /api/v1/skills/draft` — 创建草稿
  - `POST /api/v1/skills/{id}/submit` — 提交审核
  - `POST /api/v1/skills/{id}/approve` — 审核通过
  - `POST /api/v1/skills/{id}/deprecate` — 废弃

**改动文件**：
- `src/fnixagent/api/routers/skills.py` — 新建
- `src/fnixagent/main.py` — 注册路由
- `src/fnixagent/core/skills/market.py` — 暴露 `SkillMarket` 单例

**验证**：
- `curl /api/v1/skills` 返回技能列表
- 通过 API 走完 draft→submit→approve 全流程

### S1.2.4 Memory HTTP 路由 + 前端挂载

**当前问题**：MemoryManager 仅内部使用，[MemoryExplorer.tsx](file:///e:/FNIX/FnixAgent/apps/workbench/src/components/MemoryExplorer.tsx) 存在但主壳不渲染。

**设计**：
- 新增 `src/fnixagent/api/routers/memory.py`
- 4 个端点：
  - `GET /api/v1/memory/short` — 短期记忆列表（带分页）
  - `GET /api/v1/memory/long` — 长期记忆列表
  - `GET /api/v1/memory/entities` — 实体记忆
  - `POST /api/v1/memory/search` — 语义搜索
- 前端：在 [OaiSettings.tsx](file:///e:/FNIX/FnixAgent/apps/workbench/src/shell/chatgpt-desktop/OaiSettings.tsx) 新增 "Memory" section，渲染 MemoryExplorer

**改动文件**：
- `src/fnixagent/api/routers/memory.py` — 新建
- `src/fnixagent/main.py` — 注册路由
- `src/fnixagent/core/memory/manager.py` — 暴露查询方法
- `apps/workbench/src/shell/chatgpt-desktop/OaiSettings.tsx` — 新增 Memory section
- `apps/workbench/src/lib/fnixBridge.ts` — 新增 `fetchMemoryList()` 等函数

**验证**：
- `curl /api/v1/memory/short` 返回记忆列表
- 浏览器 Settings → Memory section 显示记忆条目

### S1.2.5 删 dead code

**清单**：
- 删 `src/fnixagent/core/agent/durable.py` + 清理 `core/agent/{types,kernel,__init__}.py` 内引用
- 删 `src/fnixagent/core/intelligence/memory_os.py` + 清理 `core/intelligence/{evolution_master,__init__}.py` 引用（与 S1.2.7 协同）
- 删 `fnix-se/crates/fnix-ui/` 整个目录 + `fnix-se/Cargo.toml` 移除成员
- 删 `fnix-se/crates/fnix-scheduler/` 整个目录（已 exclude 但目录还在）

**验证**：
- `tsc -b` 通过
- `cargo check --workspace` 通过
- `python -m pytest tests/` 通过
- `Grep "DurableExecutionManager"` 应 0 结果
- `Grep "MemoryOS"` 应 0 结果（除注释）

### S1.2.6 修 fnix-evolution Rust crate

**当前问题**：`error[E0432]: unresolved import crate::synthesis / criteria_evolver`

**设计**：
- 读 `fnix-se/crates/fnix-evolution/src/closed_loop.rs` 看实际 import
- 二选一：
  - 补 `synthesis.rs` 和 `criteria_evolver.rs` 模块文件
  - 或删 `closed_loop.rs` 的 import + 占位实现

**改动文件**：
- `fnix-se/crates/fnix-evolution/src/lib.rs` 或 `closed_loop.rs`
- 验证：`cargo check -p fnix-evolution` 通过

### S1.2.7 EvolutionMaster 二选一

**当前问题**：[evolution_master.py](file:///e:/FNIX/FnixAgent/src/fnixagent/core/intelligence/evolution_master.py) 仅作 `ImportError` fallback。

**设计**：合并到 MFP
- 读 EvolutionMaster 实际逻辑
- 若与 MFP 重叠 → 删 EvolutionMaster，把独有逻辑合并到 `core/flywheel/reflection.py` 或 `climbing.py`
- 若有独有价值 → 接入 `AgenticLoop._run_evolution_cycle()` 作为主路径，MFP 作 fallback

**改动文件**：
- `src/fnixagent/core/intelligence/evolution_master.py` — 删或重构
- `src/fnixagent/core/agent/loop.py:878` — 调整 `_run_evolution_cycle` 逻辑

**验证**：
- chat 模式跑任务后 MFP 数据正常显示
- 无 ImportError fallback 路径

### S1.2.8 pyo3-bridge 真接入或删

**当前问题**：[rust_ext/probe.py](file:///e:/FNIX/FnixAgent/src/fnixagent/core/rust_ext/probe.py) 只做存在性探测。

**设计**：删 probe，留接口
- 删 `src/fnixagent/core/rust_ext/probe.py`
- 保留 `rust_ext/__init__.py` 作占位
- 写 `rust_ext/README.md` 说明"pyo3 接入留待 Spec 5 神经符号 PDG 一起做"

**改动文件**：
- `src/fnixagent/core/rust_ext/probe.py` — 删
- `src/fnixagent/core/rust_ext/__init__.py` — 简化为空占位

**验证**：
- `python -c "from fnixagent.core.rust_ext import *"` 不报错
- 主流程不受影响

## S1.3 错误处理

- 每个 API 路由统一 `HTTPException(status_code=4xx, detail=str(e))`
- chat.py 改造时保留旧路径作 `?legacy=1` query 参数 1 周（向后兼容）
- 删 dead code 前先 `Grep` 全项目引用，确认无遗漏

## S1.4 测试策略

- **后端**：`tests/api/test_chat.py` / `test_mcp.py` / `test_skills.py` / `test_memory.py` 各加 3-5 个用例
- **前端**：tsc -b 通过 + 手动浏览器验收 Memory section
- **Rust**：`cargo check --workspace` + `cargo test -p fnix-evolution`
- **端到端**：跑一次 chat 模式任务，验证 evolution chunk 出现

## S1.5 完成定义

- 8 项全部完成
- 所有宣称的能力运行时真的会触发（grep + 运行时验证）
- 无 dead code（`Grep "DurableExecutionManager"` 应 0 结果）
- fnix-evolution `cargo check` 通过
- chat 模式跑任务能看到 KTG/STP/MFP 数据

---

# Spec 2-7 骨架（待 Spec 1 完成后展开）

## Spec 2 — 过程可视化升级
- streaming token + tool call card + diff 即时预览 + 思考链折叠
- 极简新中式宋韵风（留白 + 青灰 #4a6fa5 + 细线轴）
- 不抄 ChatGPT 灰圆角

## Spec 3 — Artifact Canvas
- Work Results 面板升级为协同编辑 Canvas
- 支持 HTML/CSS/JS/Mermaid/Markdown 实时预览
- 增量编辑（不重写整个文件）

## Spec 4 — 长程任务 + Compaction + Checkpoint resume
- resume_from_checkpoint 全链路
- Compaction 时 load-bearing state by design 存活
- DeerFlow 级 memory graph
- 8h 任务进度可视化

## Spec 5 — Reflection Loop + 神经符号 PDG
- 独立 Critic Agent（替代裸 self-reflect）
- Reflexion 轨迹记忆
- KTG → CLAUSE 式 dynamic context construction（三代理：expander / navigator / critic）
- fnix-pdg Rust crate 通过 pyo3 接入 Python

## Spec 6 — 多任务并行可视化
- work_jobs 强化（已有半成品）
- 多任务并行面板（Cursor /multitask 式）

## Spec 7 — 四维闭环真触发
- DAAO（执行前路由）
- VMAO（执行中重规划）
- HERA（持续演进）
- Self-Optimizing（离线预优化）
- 当前全是 dead code，要真正接入主流程

---

## 附录 A：调研文章清单

1. [OpenAI Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/) — 2026-01-23
2. [Self-Improving AI Agents: Reflection Loop](https://www.taskade.com/blog/self-improving-ai-agents-reflection) — 2026-06-29
3. [Claude Code Compaction Guide](https://hidekazu-konishi.com/entry/claude_code_compaction_and_long_session_guide.html) — 2026-06-14
4. [ByteDance DeerFlow 长程 Agent](https://ai-master.dev/en/article/deerflow-de-bytedance-lagent-open-source-qui-recherche-code-et-cree-sur-le-long)
5. [Cursor Agent Mode 2026](https://shtruzel.ru/articles/cursor-agent-mode-kak-ispolzovat-2026)
6. [CLAUSE: Agentic Neuro-Symbolic KG Reasoning](https://arxiv.org/abs/2509.21035)
7. [KG-Agent: A Neuro-Symbolic Paradigm](https://www.emergentmind.com/topics/kg-agent)

## 附录 B：项目盘点完整清单

详见 brainstorming 阶段的 search subagent 报告（保存于对话历史）。

摆设：
1. DurableExecutionManager
2. MemoryOS
3. fnix-ui（Rust wgpu GUI）
4. fnix-scheduler（Rust 已 exclude）

半生效：
1. /api/v1/chat/* 旁路 9 步流水线
2. MCP server 无 HTTP 路由
3. Skill Marketplace 无 API 暴露
4. Memory 无 API 暴露
5. EvolutionMaster 仅 ImportError fallback
6. ModelPicker / OpenAiGlyph / runStore
7. fnix-se Rust workspace 编译失败
8. pyo3-bridge 未接入 Python 主流程
9. AgentScheduler 仅 legacy 模式

缺失：
1. routers/mcp.py
2. routers/memory.py
3. routers/skills.py
4. routers/agents.py（独立 CRUD）
5. MemoryExplorer 主壳渲染
