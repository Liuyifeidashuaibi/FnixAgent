# FnixAgent 产品升级方案

## 一、现状客观评估

FnixAgent 后端有 200+ Python 模块，覆盖面极广但深度参差不齐。

### 已有功能清单

| 模块 | 文件 | 成熟度 | 说明 |
|------|------|--------|------|
| **Agent Kernel** | core/agent/kernel.py, loop.py | production | Agent 执行内核，含 sandbox/vfs/shell |
| **Knowledge Topology Graph** | core/topology/ | production | KTG 四层拓扑图 + 权重路径搜索 |
| **MFP 自进化飞轮** | core/flywheel/ | alpha | 四阶段：感知→固化→反思→爬山 |
| **技能系统** | core/skills/ | production | 加载/注册/调度/市场/安装器 |
| **MCP Server** | core/mcp/server.py | production | MCP 协议服务器 |
| **Checkpoint** | core/checkpoint/ | production | SQLite/Postgres/Memory 三后端 |
| **Office 文档** | office/ | production | Word(58KB)/PPT(29KB)/Excel(22KB)/PDF(27KB) |
| **记忆系统** | core/memory/ | alpha | 短期+长期+实体记忆 |
| **IM 集成** | business/workspace/im.py | alpha | 12KB，基础 IM 能力 |
| **邮件** | business/workspace/mail.py | alpha | 17KB，邮件收发 |
| **日程** | business/workspace/schedule.py | alpha | 16KB，日程管理 |
| **会议** | business/workspace/meeting.py | alpha | 会议管理 |
| **安全/RBAC** | core/security/ | production | RBAC + 审计 + 沙箱 + DLP |
| **代码工具** | core/code/ | production | Git/Diff/Indexer + 代码审查/调试/测试 |
| **推理引擎** | core/reasoning/ | alpha | ReAct + 反思 + 策略选择 |
| **LLM 路由** | core/llm/ | production | 多 provider + 限流 + 熔断 + 缓存 |
| **任务看板** | 前端 TaskBoard.tsx | production | 5 列 Kanban + 拖拽 + 9 步流水线 |
| **OpsMem 记忆服务** | ops-memory-mcp/ | alpha | 三层时间记忆 + MCP 2026-07-28 |
| **工作流引擎** | tasks/pipeline.py | alpha | 任务 DSL + 路由 + 验证 |

### 与竞品差距分析

| 维度 | FnixAgent | AutoClaw | QClaw | 差距 |
|------|-----------|----------|-------|------|
| **内置技能数** | ~15 个代码技能 | 50+ 技能（文档/分析/浏览器/IM） | 10+ 自动化技能 | **P0 差距** |
| **技能市场** | core/skills/market.py 存在但无内容 | ClawdHub 技能市场 | 简单技能列表 | **P1 差距** |
| **持久记忆** | core/memory/ + OpsMem | MEMORY.md + 每日笔记 + 长期记忆 | 基础会话历史 | **FnixAgent 理论更强但未打通** |
| **IM 渠道** | im.py 存在但未接入前端 | 飞书/微信/钉钉/Telegram/Signal/QQ | WhatsApp/Telegram | **P0 差距** |
| **浏览器自动化** | 无 | 内置 browser-agent skill | 内置 | **P0 缺失** |
| **定时任务** | scheduler/priority_queue.py 存在但前端无入口 | cron 工具 + 心跳系统 | 基础定时 | **P1 差距** |
| **文档生成** | office/ 模块完整 | PDF/DOCX/PPT/XLSX/HTML | 无 | **FnixAgent 占优** |
| **代码能力** | core/code/ 完整 | 无（不是编码产品） | 无 | **FnixAgent 占优** |
| **自进化** | MFP 飞轮 + 智能进化 | hermes-evolution skill | 无 | **FnixAgent 占优** |
| **多模型** | BYOK 全模型 | BYOK + 智谱模型 | 固定模型 | **FnixAgent 占优** |
| **数据隐私** | 全本地 | 全本地 | 本地 | **持平** |
| **产品成熟度** | alpha（功能多但未打通） | production（开箱即用） | production | **P0 差距** |

## 二、升级方案（按优先级）

### P0：必须补齐的差距（达到竞品基线）

#### 1. 浏览器自动化模块
- **现状**：完全缺失
- **方案**：新增 `core/browser/` 模块，基于 Playwright Python 实现浏览器自动化
- **功能**：打开网页、搜索、填表、截图、采集内容、社交媒体操作
- **前端**：BrowserView.tsx 已存在（占位），需要接入真实浏览器控制
- **预计工作量**：3-5 天

#### 2. IM 渠道集成打通
- **现状**：后端 im.py 存在(12KB)但前端无入口，未接入任何渠道
- **方案**：
  - 后端：完善 im.py，接入飞书/钉钉/Telegram Webhook
  - 前端：在 ChatGptDesktopApp 侧边栏添加 IM 渠道管理入口
  - 消息路由：IM 消息 → agent kernel → IM 回复
- **预计工作量**：5-7 天

#### 3. 内置技能包扩充
- **现状**：只有代码相关技能（review/debug/test）
- **方案**：新增 20+ 通用技能：
  - 文档类：PPT 生成、Word 报告、Excel 数据分析、PDF 合并/拆分
  - 研究类：深度调研、网页摘要、竞品分析、论文审稿
  - 自动化类：定时摘要、邮件处理、文件整理、批量重命名
  - 创意类：海报设计、信息图、思维导图、流程图
- **格式**：每个技能一个 SKILL.md + 执行脚本
- **预计工作量**：7-10 天

#### 4. 产品打磨：开箱即用体验
- **现状**：需要手动配置 API key、启动后端、安装依赖
- **方案**：
  - OnboardingWizard 已存在，完善首次使用引导
  - 自动检测本地 Ollama 模型
  - 一键启动后端 agentd
  - 默认配置：qwen-plus + Ollama fallback
- **预计工作量**：3-5 天

### P1：应该有的增强（超越竞品）

#### 5. 持久记忆系统打通
- **现状**：core/memory/ 和 OpsMem 两个记忆系统并存但未打通
- **方案**：
  - 统一记忆接口：core/memory/manager.py 作为唯一入口
  - 短期记忆 → 会话内上下文（已有）
  - 长期记忆 → MEMORY.md + OpsMem 语义层（需打通）
  - 实体记忆 → KTG 拓扑图（已有）
  - 前端：侧边栏添加"记忆"入口，可视化浏览/搜索记忆
- **预计工作量**：5-7 天

#### 6. 定时任务前端化
- **现状**：后端 scheduler/priority_queue.py 存在，前端无入口
- **方案**：
  - 前端：TaskBoard 新增"定时任务"tab
  - 后端：新增 `/api/v1/schedule` 端点，支持 cron 表达式
  - 功能：定时执行技能、定时摘要、定时提醒
- **预计工作量**：3-5 天

#### 7. 技能市场激活
- **现状**：core/skills/market.py 存在(25KB)但无内容
- **方案**：
  - 本地技能目录：`.fnix/skills/` 下扫描 SKILL.md
  - 在线技能市场：从 GitHub/Gitee 拉取技能包
  - 前端：SkillManager.tsx 已存在，完善技能浏览/安装/启用/禁用
  - 技能格式：SKILL.md + 可选 Python 脚本
- **预计工作量**：5-7 天

### P2：差异化优势强化（超越所有竞品）

#### 8. 多 Agent 协作
- **现状**：core/orchestrator/ 存在但未启用
- **方案**：
  - 主 Agent 可派发子 Agent（类似 AutoClaw 的 subagent）
  - 子 Agent 独立上下文，完成后汇报
  - 前端：TaskBoard 显示多 Agent 状态
- **预计工作量**：7-10 天

#### 9. 自进化可视化
- **现状**：MFP 飞轮存在但用户看不到
- **方案**：
  - 前端：新增"进化面板"展示 KTG 增长曲线、权重变化、技能学习历史
  - 后端：暴露 `/api/v1/evolution/history` 端点
- **预计工作量**：3-5 天

#### 10. 代码 + 办公双模式无缝切换
- **现状**：Work/Codex 两种模式存在但记忆不共享
- **方案**：
  - KTG 知识拓扑跨模式共享
  - 代码会话中学到的规则自动应用到文档撰写
  - 前端：模式切换时保留上下文
- **预计工作量**：5-7 天

## 三、执行优先级

| 优先级 | 任务 | 工作量 | 影响 |
|--------|------|--------|------|
| **P0-1** | 浏览器自动化 | 3-5天 | 补齐最大功能缺口 |
| **P0-2** | IM 渠道集成 | 5-7天 | 补齐第二大缺口 |
| **P0-3** | 内置技能包扩充 | 7-10天 | 从15→35+技能 |
| **P0-4** | 开箱即用体验 | 3-5天 | 降低使用门槛 |
| **P1-5** | 持久记忆打通 | 5-7天 | 核心差异化 |
| **P1-6** | 定时任务前端化 | 3-5天 | 自动化能力 |
| **P1-7** | 技能市场激活 | 5-7天 | 生态建设 |
| **P2-8** | 多 Agent 协作 | 7-10天 | 超越竞品 |
| **P2-9** | 自进化可视化 | 3-5天 | 差异化展示 |
| **P2-10** | 代码+办公双模式 | 5-7天 | 独特定位 |

**总计**：P0 需 18-27 天，P1 需 13-19 天，P2 需 15-22 天

## 四、FnixAgent 的独特优势（应保持并强化）

1. **KTG 知识拓扑图**：唯一用图结构做知识管理的 AI agent（竞品都是平面向量检索）
2. **MFP 自进化飞轮**：唯一能从执行轨迹中学习并改进的 agent（竞品都是静态的）
3. **代码 + 办公双模式**：唯一同时支持编码和办公的 agent（竞品要么纯编码要么纯办公）
4. **BYOK 全模型**：唯一支持任意模型的 agent（竞品都绑定特定模型）
5. **全本地数据**：与 AutoClaw 持平，优于 QClaw 的云端模式
6. **Office 文档生成**：最完整的文档生成能力（Word/PPT/Excel/PDF）

## 五、建议的产品定位调整

不变：**Local-first AI 工作台**

强化：**"能学习的 AI 工作台"** — 强调 MFP 自进化是核心差异化
- AutoClaw 定位："开箱即用的 AI 助手"（技能多但不学习）
- QClaw 定位："远程桌面自动化"（能控制 PC 但不编码）
- FnixAgent 定位："**会进化的 AI 工作台** — 用得越多越懂你"

副标题：编码 + 办公 + 自进化，全本地隐私优先