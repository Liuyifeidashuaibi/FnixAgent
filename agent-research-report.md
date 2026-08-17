# Agent 设计方案综合研究报告

> 研究日期: 2026-08-17
> 覆盖 11 个 GitHub 仓库/用户，聚焦 Agent 架构、记忆系统、技能系统、多Agent协作等核心设计

---

## 目录

1. [各仓库核心分析](#1-各仓库核心分析)
2. [Agent 架构模式对比](#2-agent-架构模式对比)
3. [记忆系统设计对比](#3-记忆系统设计对比)
4. [技能系统设计对比](#4-技能系统设计对比)
5. [多Agent协作模式](#5-多agent协作模式)
6. [值得吸收的设计亮点](#6-值得吸收的设计亮点)
7. [对 FnixAgent 的建议](#7-对-fnixagent-的建议)

---

## 1. 各仓库核心分析

### 1.1 CodePilot (op7418/CodePilot)
**定位**: 多模型 AI Agent 桌面客户端
**技术栈**: Electron 40 + Next.js 16 (App Router) + SQLite (WAL) + Claude Agent SDK

**核心设计**:
- **多Provider支持**: 17+ AI 提供商，支持对话中切换模型不丢上下文
- **IM Bridge 系统**: 将 Telegram/飞书/Discord/QQ/WeChat 连接到桌面 Agent 会话
  - Channel Adapter 适配器模式 + Channel Router 消息路由
  - Permission Broker 权限请求转 IM 内联按钮
  - Delivery Layer 消息分片 + 速率限制
- **Assistant Workspace**: soul.md / user.md / claude.md / memory.md 人格文件体系
- **Generative UI**: AI 创建交互式仪表盘和可视化组件
- **Sub-agent 系统**: 多模型 Sub-agent，durable lifecycle (running → settling → terminal)
- **52 个 REST 端点**: 完整的 API 层设计
- **错误分类**: 16 类结构化错误 + Provider 诊断引擎（5 探针 + 修复动作）
- **任务调度**: Cron 表达式和间隔调度，持久化

**值得吸收**:
- Bridge 子系统架构（IM → Agent 的完整链路）
- Provider 诊断引擎设计
- Sub-agent durable lifecycle 状态机
- 错误分类体系

---

### 1.2 DeerFlow (bytedance/deer-flow) ⭐ 重磅
**定位**: 开源 Super Agent Harness（字节跳动）
**技术栈**: Python + LangChain + Docker Sandbox

**核心设计**:
- **Super Agent 架构**: 编排 Sub-agents + Memory + Sandbox 完成复杂任务
- **Skills & Tools**: 可扩展技能系统 + MCP Server 集成
- **Claude Code 集成**: 通过 ACP (Agent Communication Protocol) 接入
- **Session Goals**: 会话级目标设定与追踪
- **Context Engineering**: 
  - 手动上下文压缩 (Manual Context Compaction)
  - Checkpoint 机制（delta channel mode + snapshot frequency）
  - Checkpoint 缓存（memory/redis 后端）
- **Sub-Agents**: 
  - 可配置最大并发数 (subagents.max_total_per_run)
  - ACP Agent 集成（Codex CLI, Claude Code OAuth, MiniMax Code）
- **Sandbox**: Docker 容器化安全执行环境
- **Long-Term Memory**: 持久化记忆系统
- **Scheduled Tasks**: 定时任务
- **多 Tracing 支持**: LangSmith / Langfuse / Monocle
- **IM Channels**: 多渠道消息网关
- **配置系统**: config.yaml + .env，make setup 交互式向导
- **vLLM 集成**: 支持本地部署推理模型，处理 thinking 字段

**值得吸收**:
- Super Agent 编排模式（Sub-agents + Memory + Sandbox 三位一体）
- Context Engineering 的 Checkpoint 机制
- ACP 协议集成多种 Coding Agent
- 配置向导 + doctor 诊断模式
- Support Bundle 问题诊断方案

---

### 1.3 Raven (EverMind-AI/Raven) ⭐ 重磅
**定位**: Memory-first, Self-improving Agent Harness
**技术栈**: Python + React/Ink TUI + EverOS

**核心设计**:
- **EverOS Memory**: 持久化用户记忆 + Agent记忆 + 世界知识
  - 跨会话记忆
  - Markdown 源文件 + SQLite + LanceDB 三层存储
- **Context Engine**: 
  - 显式 Token 预算
  - 统一上下文组装管线
- **Proactivity 系统**: 
  - Sentinel 观察（主动发现需要处理的事项）
  - 调度工作
  - Nudge 策略（推动机制）
  - 延迟决策
- **SkillForge**: 
  - 内置/工作区/EverOS/镜像技能
  - 检索 + 反馈 + 进化
- **Evolver**: 
  - 可复现的评估循环
  - 改进 Agent 和可复用流程
- **Agent Templates**: 可分享的专业化数字工人模板
- **Deep Research**: MiroThinker 多源深度研究
- **Tracing**: 本地追踪仪表盘
  - Span 存储为 audit-spans.log
  - 版本化语义合约
- **12 个 Gateway 适配器**: Telegram/Slack/Discord/WhatsApp/Matrix/飞书/企微/QQ/钉钉/Email/WeChat

**架构分层**:
```
CLI / TUI / Messaging Gateways
         ↓
   TUI-RPC / Spine
         ↓
    Agent Loop
  +-------+-------+
  |       |       |
Providers Tools  Subagents
  |       |       |
  +--- Context Engine ---+
         |
  +------+------+
  |             |
EverOS Memory  SkillForge
  |             |
  +--- Proactivity + Evolver
```

**值得吸收**:
- Proactivity 系统（Sentinel + Nudge + 调度）
- Context Engine 的 Token 预算和统一组装管线
- Evolver 自我进化循环
- Tracing Standard API（本地可检查的追踪标准）
- Agent Templates 概念

---

### 1.4 waku-agent (ShenSeanChen/waku-agent) ⭐ 教学级
**定位**: Local-first AI Agent Harness（教学导向，代码可读）
**技术栈**: Python + SQLite + FTS5

**核心设计**:
- **The Loop (~95行 Python)**: 极简 Agent 循环
  ```python
  while not done:
      response = llm(messages, tools)  # reason
      if response wants tools:
          results = run(tool_calls)     # act
          messages += results           # observe
      else:
          done                          # reply
  ```
- **Memory 三支柱**:
  - **Semantic Memory**: 持久化事实、用户画像
  - **Episodic Memory**: 日期事件、历史对话
  - **Procedural Memory**: SKILL.md，行为模式
- **Retrieval Gate**: 智能判断是否需要检索记忆（避免不必要的检索开销）
- **Consolidation**: 每 N 次对话后自动 consolidate → 提炼事实
- **Eval 系统**:
  - 确定性测试 (Deterministic)
  - LLM-as-Judge 评估
  - Release Gate（发布门控）
- **Dashboard**: 本地 Web 仪表盘，实时可视化 Agent 运行
  - Overview / Gateway / Loop / Graph / Memory / Tools / Data / Ops 标签页
  - 实时 SQLite 浏览器
- **Graph Workflows**: 当任务需要结构化时的 ~200 行扩展
- **MEMORY.md + state.db 双存储**: 可查询源在 state.db（FTS5），同时生成人类可读的 MEMORY.md 镜像

**值得吸收**:
- Retrieval Gate（检索门控）设计——不是每次都检索，而是智能判断
- Memory Consolidation 机制——定期提炼事实
- Eval 系统（确定性 + LLM-as-Judge 双轨）
- Dashboard 实时可视化 Agent 运行状态
- 95行极简 Loop 设计哲学

---

### 1.5 alchaincyf (花叔) ⭐ Skill 生态
**核心项目矩阵**:

#### 女娲.skill (nuwa-skill) - 思维蒸馏
- 蒸馏任何人的认知框架（心智模型 + 决策启发式 + 表达DNA）
- 五层提取: 表达DNA → 心智模型 → 决策启发式 → 反模式 → 诚实边界
- 六路并行采集 + 三重验证提炼
- 基于 Agent Skills 协议，50+ runtime 兼容
- 15个官方 Skill，全部通过独立双Agent盲测

#### 达尔文.skill (darwin-skill) - Skill 自进化 ⭐
- **9维度评估体系**: 结构质量 + 实际效果
  - 失败模式编码 (Failure Mechanism Encoding)
  - 可执行具体性 (Actionable Specificity)
  - 高风险行动黑名单 (High-Risk Action Blacklist)
- **棘轮机制**: 只保留改进，自动回滚退步
- **5阶段优化循环**: 基线评估 → 单维度优化 → 测试 → 回归测试 → 确认
- **Human-in-the-Loop**: 关键阶段强制暂停等用户确认
- **反例黑名单 8 条**: 包括"同一个AI又改又评"（LLM自评仅46.4%准确率）
- 吸收微软 SkillLens + SkillOpt 论文

#### FanBox - Coding Agent 驾驶舱
- 文件浏览 + 终端 + 预览三合一
- Agent 改动实时可视化（文件卡片发光呼吸）
- 会话回放（像刷视频一样拖时间轴）
- 项目记忆（历史会话 + 改动文件 + 触发过的skill）
- Skills 透视（本机所有 agent skills 一个视图）

**值得吸收**:
- 女娲的思维蒸馏方法论（五层提取 + 六路采集 + 三重验证）
- 达尔文的 Skill 自进化机制（9维评估 + 棘轮 + Human-in-the-Loop）
- FanBox 的 Agent 改动可视化设计
- Agent Skills 协议生态

---

### 1.6 cyfyifanchen (EverMind-AI) ⭐ 记忆系统
**核心项目**:

#### EverOS - 通用 Agent 记忆层 ⭐⭐
- **Markdown 源真相**: 可读、可编辑、可 diff、可 Git 版本化
- **本地三层栈**: Markdown + SQLite + LanceDB（无需 MongoDB/ES/Redis）
- **正交检索**: 按 user_id / agent_id / app_id / project_id / session_id 检索
- **Knowledge Wiki**: 可编辑的 Markdown 知识页面 + 分类 + CRUD API
- **Reflection**: 离线记忆进化（合并 episode 聚类 + 精炼 profile/skill）
- **级联 Watcher**: 编辑 .md 文件自动同步索引

#### HyperMem - 超图层次记忆
- 基于超图 (Hypergraph) 的层次记忆架构
- 通过超边 (Hyperedges) 捕获高阶关联
- Topic / Event / Fact 三层组织

#### MSA - Memory Sparse Attention
- 可扩展的端到端可训练潜在记忆框架
- 支持 100M token 上下文

**值得吸收**:
- EverOS 的 Markdown-first 记忆设计（源真相 + 索引分离）
- Reflection 机制（离线记忆进化）
- 正交检索维度设计
- Knowledge Wiki 与记忆的整合

---

### 1.7 tao12345666333/amcp ⭐ 实战型
**定位**: 开箱即用的 Coding Agent Runtime
**技术栈**: Python + FastAPI + Telegram Bot

**核心设计**:
- **多表面**: CLI / HTTP/WebSocket API / Telegram / Cron/Systemd/K8s
- **Primary/Subagent 架构**:
  - coder (Primary): 全能力编码 Agent
  - explorer (Subagent): 只读快速探索
  - planner (Subagent): 只读规划分析
  - focused_coder (Subagent): 聚焦实现
- **Memory 系统**:
  - MEMORY.md: 策展的长期事实
  - HISTORY.md: 追加式活动历史
  - memory.db: SQLite FTS5 持久化事实 + 情景事件
  - SOUL.md / IDENTITY.md: 人格与身份
- **Skills 系统**: 
  - 内置技能 (skill-creator, session-cleanup, heartbeat, networked-research)
  - 多级发现: 内置 → 用户 → Home → 项目
  - 支持 Cron 和事件触发自动执行
- **Slash Commands**: TOML 定义的快捷命令
  - `{{args}}` 占位符 + `!{shell}` 注入 + `@{file}` 文件注入
- **Durable Execution Timeline**: 每会话 2000 条事件元数据
- **Hooks & Event Bus**: 事件驱动扩展

**值得吸收**:
- 多表面统一运行时设计
- Primary/Subagent 类型化架构
- Durable Execution Timeline（可审计的执行时间线）
- Slash Commands 的 TOML 定义模式
- Skills 的多级发现机制

---

### 1.8 prex-quant (wcq-glhf)
**定位**: 量化回测 API 客户端
**Agent 相关性**: 低。主要是 API 协议文档和调用示例。
- 自然语言策略回测（NL → 因子规则 → 回测）
- 异步任务模式（提交 → 轮询 → 获取结果）

**可参考**: 自然语言到结构化策略的转换模式、异步任务报告生成

---

### 1.9 OpenPencil (ZSeven-W/openpencil) ⭐ 设计Agent
**定位**: 开源 AI 原生矢量设计工具
**技术栈**: Rust + WebAssembly + CanvasKit

**核心设计**:
- **Concurrent Agent Teams**: 
  - 编排器将复杂页面分解为空间子任务
  - 多 Agent 并行工作（hero/features/footer 同时流式生成）
  - Per-member Canvas 指示器
- **MCP Server**: 一键安装到 Claude Code/Codex/OpenCode 等
- **Multi-Model Intelligence**: 
  - 自动适配模型能力（Claude 完整提示 / GPT-4o 禁思考 / 小模型简化提示）
  - Model Capability Profiles
- **Design-as-Code**: .op 文件是 JSON，可 Git diff
- **分层设计工作流**: design_skeleton → design_content → design_refine
- **Anti-slop**: 跨生成多样性追踪，避免重复AI输出
- **Style Guides**: 标签模糊匹配应用视觉风格

**值得吸收**:
- Concurrent Agent Teams（并行 Agent 团队 + 空间分解）
- Model Capability Profiles（按模型能力自动适配提示）
- 分层工作流（skeleton → content → refine）
- Anti-slop 多样性追踪

---

### 1.10 OpenMinis ⭐ 移动端Agent
**定位**: 跨平台 AI Agent App（iOS/Android）
**技术栈**: Swift/SwiftUI (iOS) + Kotlin/Compose (Android) + Linux Sandbox

**核心设计**:
- **On-device Linux Shell**: 
  - iOS: iSH (ARM64 fork) 用户态 Linux 模拟
  - Android: PRoot 用户态 chroot
  - Alpine Linux minirootfs
- **Device Integration**: Health/Calendar/Reminders/Contacts/HomeKit/Bluetooth/Clipboard/Media/Alarms 作为 Agent 工具
- **Browser Automation**: Agent 可浏览和交互网页
- **Skills & Memory**: 可扩展技能 + 跨会话语义记忆
- **Workspaces**: 独立上下文组织，minis://workspace/ 寻址
- **Native Offloads**: 重型/平台特定工作交给原生代码
- **Skill 兼容性**: Claude/Codex/OpenClaw/Hermes 的 skill 可直接运行

**值得吸收**:
- 设备集成作为 Agent 工具的设计模式
- On-device Sandbox 安全执行
- Native Offloads（Agent → 原生代码卸载）
- 跨平台 Skill 兼容性设计

---

### 1.11 Kun (KunAgent/Kun) ⭐ 工作台
**定位**: 本地优先 AI Agent 工作台
**技术栈**: Node.js 22 + Electron + TUI

**核心设计**:
- **双模式**: 
  - Code 模式: 软件交付（文件编辑/终端/Git/Diff/测试/审查 + Design 画布）
  - Work 模式: 写作/整理/文档分析/演示
- **GUI + TUI 共享运行时**: 同一 kun serve 运行时共享线程/目标/计划/审批/后台任务
- **从目标到验收**: 澄清目标 → 形成计划 → 执行协作 → 检查证据 → 交付
- **Design 模式**: 同一 Code 任务中切换 Design 画布
- **Loops / Hooks / MCP / Skills / Extensions**: 完整扩展体系
- **Provider 生态**: ChatGPT/Claude/Gemini/Ollama/DeepSeek/Kimi/GLM/Qwen/MiniMax/MiMo

**值得吸收**:
- Code + Work + Design 三模式统一
- GUI + TUI 共享运行时（不是两套割裂会话）
- 目标驱动的工作流（目标 → 计划 → 执行 → 证据 → 交付）
- Design 画布嵌入 Code 任务

---

## 2. Agent 架构模式对比

| 项目 | 循环模式 | 编排模式 | 执行环境 |
|------|---------|---------|---------|
| CodePilot | SDK SSE 流 | 单Agent + Sub-agent | 本地桌面 |
| DeerFlow | LangChain Agent | Super Agent (多Sub-agent编排) | Docker Sandbox |
| Raven | Agent Loop + Spine | Agent Loop + Subagents + Proactivity | Sandbox |
| waku-agent | 95行 while loop | Loop + Graph workflows | 本地 |
| amcp | Primary/Subagent | 类型化 Agent 分工 | 本地/远程服务器 |
| OpenPencil | Orchestrator | Concurrent Agent Teams | 本地 Rust 核心 |
| OpenMinis | Agent + Tools | 单Agent + 设备工具 | On-device Linux |
| Kun | Goal → Plan → Execute | 单Agent + 多模式 | 本地 Electron |

**关键趋势**:
1. **从单Agent到Super Agent**: DeerFlow 和 Raven 代表了从单Agent到编排多Agent的趋势
2. **Loop vs Graph**: waku-agent 明确区分了 Loop（简单循环）和 Graph（结构化工作流）
3. **Primary/Subagent 类型化**: amcp 的 coder/explorer/planner/focused_coder 分工模式

---

## 3. 记忆系统设计对比

| 项目 | 存储层 | 记忆分类 | 特色机制 |
|------|--------|---------|---------|
| CodePilot | SQLite (WAL) | 会话 + 任务 | soul.md/user.md/claude.md/memory.md |
| DeerFlow | Checkpoint + DB | 长期记忆 | Checkpoint delta + snapshot |
| Raven | Markdown + SQLite + LanceDB | 用户/Agent/世界知识 | Reflection (离线进化) |
| waku-agent | SQLite + FTS5 | Semantic/Episodic/Procedural | Retrieval Gate + Consolidation |
| EverOS | Markdown + SQLite + LanceDB | 用户/Agent/应用/项目/会话 | 级联Watcher + Knowledge Wiki |
| amcp | MEMORY.md + HISTORY.md + memory.db | 长期/活动/事实+情景 | FTS5 全文搜索 |
| OpenMinis | 本地存储 | 跨会话语义记忆 | 设备集成记忆 |

**关键趋势**:
1. **Markdown-first**: Raven/EverOS/waku-agent 都采用 Markdown 作为源真相
2. **三层存储**: Markdown(人类可读) + SQLite(可查询) + Vector/LanceDB(语义检索)
3. **Retrieval Gate**: waku-agent 的智能检索门控（不是每次都检索）
4. **Reflection/Consolidation**: 离线记忆提炼进化

---

## 4. 技能系统设计对比

| 项目 | 技能格式 | 发现机制 | 进化机制 |
|------|---------|---------|---------|
| CodePilot | Skills 页面 | skills.sh 市场 | 手动 |
| DeerFlow | 可扩展 Skills | 配置加载 | 手动 |
| Raven | SkillForge | 内置/工作区/EverOS/镜像 | Evolver 自动进化 |
| waku-agent | SKILL.md | 目录加载 | 手动 |
| 女娲/达尔文 | SKILL.md (Agent Skills 协议) | 50+ runtime 兼容 | 达尔文 9维自进化 |
| amcp | SKILL.md + YAML frontmatter | 内置→用户→Home→项目 | Cron/事件触发 |
| OpenMinis | SKILL.md | 目录加载 | 手动 |
| Kun | Skills + Extensions | 项目级 + 全局 | 手动 |

**关键趋势**:
1. **Agent Skills 协议**: 正在成为跨 runtime 标准（50+ 兼容）
2. **Skill 自进化**: 达尔文的 9 维评估 + 棘轮机制是最成熟的方案
3. **多级发现**: amcp 的 内置→用户→Home→项目 优先级链

---

## 5. 多Agent协作模式

### 5.1 DeerFlow: Super Agent 编排
```
Super Agent
  ├── Sub-agent A (研究)
  ├── Sub-agent B (编码)
  ├── Sub-agent C (写作)
  ├── Memory (共享记忆)
  └── Sandbox (安全执行)
```

### 5.2 OpenPencil: Concurrent Agent Teams
```
Orchestrator
  ├── 空间分解 → 子任务A (hero区域)
  ├── 空间分解 → 子任务B (features区域)
  └── 空间分解 → 子任务C (footer区域)
  → 多 Agent 并行流式生成
```

### 5.3 amcp: Primary/Subagent 类型化
```
Primary (coder)
  ├── explorer (只读探索)
  ├── planner (只读规划)
  └── focused_coder (聚焦实现)
```

### 5.4 CodePilot: Multi-Model Sub-agent
```
Main Agent (Model A)
  ├── Sub-agent (Model B) - 不同模型
  └── Sub-agent (Model C) - 不同模型
  → durable lifecycle: running → settling → terminal
```

---

## 6. 值得吸收的设计亮点

### 🏆 Tier 1 - 必须吸收

1. **EverOS 的 Markdown-first 记忆架构**
   - Markdown 源真相 + SQLite 索引 + Vector 语义检索
   - 级联 Watcher（编辑文件自动同步）
   - Reflection 离线记忆进化
   - 正交检索维度（user/agent/app/project/session）

2. **达尔文 Skill 自进化系统**
   - 9维评估体系（含失败模式编码、可执行具体性、高风险黑名单）
   - 棘轮机制（只保留改进）
   - Human-in-the-Loop 三层守关
   - 独立评委（避免自评偏差）

3. **waku-agent 的 Retrieval Gate + Consolidation**
   - 智能判断是否需要检索（节省 token）
   - 定期 Consolidation 提炼事实
   - 双轨 Eval（确定性 + LLM-as-Judge）

4. **DeerFlow 的 Context Engineering**
   - Checkpoint 机制（delta + snapshot）
   - 手动上下文压缩
   - ACP 协议集成多种 Coding Agent

### 🥈 Tier 2 - 强烈建议

5. **Raven 的 Proactivity 系统**
   - Sentinel 观察（主动发现事项）
   - Nudge 策略（推动机制）
   - 延迟决策

6. **amcp 的 Durable Execution Timeline**
   - 每会话 2000 条事件元数据
   - 可审计的执行时间线
   - 中断后可检查

7. **OpenPencil 的 Concurrent Agent Teams**
   - 空间分解 + 并行流式生成
   - Model Capability Profiles（按模型适配提示）
   - Anti-slop 多样性追踪

8. **CodePilot 的 IM Bridge 系统**
   - Channel Adapter + Router + Permission Broker + Delivery Layer
   - 完整的 IM → Agent 链路

### 🥉 Tier 3 - 可选参考

9. **女娲的思维蒸馏方法论**
   - 五层提取（表达DNA → 心智模型 → 决策启发式 → 反模式 → 诚实边界）
   - 六路并行采集 + 三重验证

10. **Kun 的 GUI + TUI 共享运行时**
    - 同一运行时双界面
    - 目标驱动工作流

11. **OpenMinis 的设备集成**
    - 设备能力作为 Agent 工具
    - Native Offloads

12. **FanBox 的 Agent 改动可视化**
    - 文件卡片发光呼吸
    - 会话回放

---

## 7. 对 FnixAgent 的建议

基于以上研究，以下是按优先级排列的建议：

### 架构层面

1. **采用 Super Agent 编排模式**
   - 参考 DeerFlow 的 Sub-agents + Memory + Sandbox 三位一体
   - 实现 Primary/Subagent 类型化分工（参考 amcp）
   - 支持多模型 Sub-agent（参考 CodePilot）

2. **实现 Context Engineering**
   - Checkpoint 机制（delta + snapshot）
   - 手动/自动上下文压缩
   - Token 预算和统一上下文组装管线（参考 Raven）

3. **Durable Execution Timeline**
   - 可审计的执行时间线
   - 中断后恢复和检查

### 记忆系统

4. **三层记忆存储**
   - Markdown 源真相（人类可读可编辑）
   - SQLite + FTS5（可查询）
   - Vector 索引（语义检索）

5. **Retrieval Gate**
   - 智能判断是否需要检索
   - 减少不必要的 token 消耗

6. **Memory Consolidation + Reflection**
   - 定期提炼事实
   - 离线记忆进化

### 技能系统

7. **Agent Skills 协议兼容**
   - 兼容 50+ runtime 的 SKILL.md 格式
   - 多级技能发现（内置→用户→项目）

8. **Skill 自进化**
   - 参考达尔文的 9 维评估 + 棘轮机制
   - Human-in-the-Loop 关键节点

### 交互层面

9. **IM Bridge 系统**
   - 多渠道消息网关
   - Channel Adapter 适配器模式

10. **Proactivity 系统**
    - Sentinel 主动观察
    - 调度工作 + Nudge 策略

### 可视化

11. **Agent 运行 Dashboard**
    - 参考 waku-agent 的实时可视化
    - 参考 FanBox 的改动追踪

---

## 附录: 关键链接

| 项目 | URL | Stars |
|------|-----|-------|
| CodePilot | https://github.com/op7418/CodePilot | - |
| DeerFlow | https://github.com/bytedance/deer-flow | Trending #1 |
| Raven | https://github.com/EverMind-AI/Raven | 3.5k |
| waku-agent | https://github.com/ShenSeanChen/waku-agent | - |
| EverOS | https://github.com/EverMind-AI/EverOS | 12.1k |
| 女娲.skill | https://github.com/alchaincyf/nuwa-skill | ~20k |
| 达尔文.skill | https://github.com/alchaincyf/darwin-skill | - |
| FanBox | https://github.com/alchaincyf/fanbox | - |
| amcp | https://github.com/tao12345666333/amcp | 33 |
| OpenPencil | https://github.com/ZSeven-W/openpencil | - |
| OpenMinis | https://github.com/OpenMinis/OpenMinis | - |
| Kun | https://github.com/KunAgent/Kun | - |
| prex-quant | https://github.com/wcq-glhf/prex-quant | - |
