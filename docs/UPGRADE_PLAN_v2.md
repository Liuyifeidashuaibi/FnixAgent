# FnixAgent 升级方案 v2.0(基于 2025-2026 全网深度研究)

> 编制日期:2026-08-01 ｜ 依据:4 份并行研究报告(竞品/架构/自进化/UX)+ 代码库实测
> 适用范围:产品 + 论文双线交付 ｜ 原则:务实可行、不摇摆、后端免费、核心能力优先

研究底座见 `docs/research/SELF_EVOLUTION_RESEARCH.md` 及三份并行研究报告(竞品/架构/UX)。本方案不重复研究结论,直接产出可执行决策。

---

## 一、当前现状诊断

### 1.1 项目定位清晰度

| 维度 | 现状 | 评估 |
|---|---|---|
| 产品定位 | "本地优先 + BYOK + 自进化"三联 | ✅ **竞品空白**(本地派 Aider/Cline/Continue 不自进化;自进化派 Devin/Cursor Cloud 闭源云端) |
| 论文定位 | FSE 2027 Tool/Research Track | ✅ 但需诚实处理与 EvolveR/KAG/Router-R1 的关系 |
| 商业定位 | 模糊 | ⚠️ 需明确:个人/小团队免费工作台 |

### 1.2 核心机制对照最新研究(诚实诊断)

| 机制 | FnixAgent | 2025-2026 最新对标 | 差距判断 |
|---|---|---|---|
| **KTG** 固定四层 + 权重路径 | MUTEX 惩罚、Top-K=3、纯 Python | KAG(arXiv:2409.13731)KG-DSL 规则引擎,2wiki +19.6%、HotpotQA +33.5% F1 | ⚠️ **KAG 的 KG-DSL 比 KTG 固定 schema 表达力更强**;KTG 未在任何公开 benchmark 报分 |
| **MFP** 四阶段爬坡 | snapshot+rollback 安全 | EvolveR(arXiv:2510.16079,ICML 2026)离线自蒸馏+在线 RL,多跳 QA SOTA;Sleep-time Compute(arXiv:2504.13171)量化离线收益(5× test-time 节省) | ⚠️ **EvolveR 在多跳 QA 上已超越 MFP**;MFP 缺乏量化收益(未引用 Sleep-time Compute) |
| **DAAO** 零 LLM + HERA 闭环 | 路由 0 token 成本 | RouteLLM(arXiv:2406.18665)成本降 2×;Router-R1(arXiv:2506.09033)RL 路由 | ✅ **"零 LLM 调用 + 失败率反馈闭环"在路由领域确有差异化**;但需公开 benchmark 验证 |
| **记忆系统** | KTG 单一来源,无时序 | Zep(Graphiti)双时态模型 LongMemEval +18.5%;Letta 分层自编辑;Mem0 向量+图谱分层 | ⚠️ **KTG 缺时序性,无法表达"事实何时成立/失效"**; misevolution(SJTU 2026 警示)无防御 |
| **公开 benchmark** | 仅自建 FCS | MuSiQue/HotpotQA/2WikiMultiHop/LongMemEval/SWE-bench 全空白 | ⚠️ **最大信任缺口** — 自建基准无第三方验证 |

### 1.3 工程层关键问题(基于代码实测)

| 编号 | 问题 | 证据 | 严重度 |
|---|---|---|---|
| **E1** | agentd 默认绑 `0.0.0.0:8003` | `main.py:426` `host = args.host or server_cfg.get("host", "0.0.0.0")` | 🔴 高 — 本地优先却对外暴露,违反 Kleppmann 原则 6"默认安全" |
| **E2** | BYOK 双路径并存 | `adapter.py:139` 走 `.env` 明文 + `harness/secrets.py` 走 keychain | 🔴 高 — 明文落盘风险 |
| **E3** | 协议双跳开销 | Tauri → agentd(HTTP) → fnix-local(HTTP) | 🟡 中 — 延迟+复杂度叠加 |
| **E4** | 架构文档与实现分裂 | `ARCHITECTURE.md` 写 Milvus/PG/Redis(云端),实际桌面是 SQLite/文件 | 🟡 中 — 误导选型 |
| **E5** | 向量存储未本地优先化 | 桌面形态向量方案未定型 | 🟡 中 — 本地优先知识库落不了地 |
| **E6** | CRDT 缺位 | 无 Yjs/Automerge | 🟢 低 — 多端协同空白(非当前优先) |
| **E7** | Python 分发体积大 | PyInstaller 打包 agentd | 🟢 低 — 与 Tauri 轻量理念相悖(后期) |
| **E8** | 沙箱跨平台不均 | `agentos/sandbox.py` + `syscall.py`,Windows/macOS 弱 | 🟡 中 |

### 1.4 前端关键问题(基于用户偏好对照)

| 编号 | 问题 | 证据 | 严重度 |
|---|---|---|---|
| **U1** | ToolCallCard 暴露技术细节 | `ToolCallCard.tsx` 显示工具名+params,英文"Reading file" | 🔴 高 — 与"隐藏技术过程"偏好直接冲突 |
| **U2** | Composer 未极简化 | 含 modelSlot 等底栏元素 | 🟡 中 |
| **U3** | AI 回复结构化未完成 | `utils/structuredBlocks.ts` 已存在但未全面接入 | 🟡 中 |
| **U4** | 缺骨架屏 | 工具等待期无 placeholder | 🟡 中 |
| **U5** | Checkpoint 回滚入口未暴露 | 后端 `core/checkpoint/` 有,前端无入口 | 🟡 中 |
| **U6** | Skills 入口暴露 | ChatHead 有 skills 按钮 | 🟡 中 |
| **U7** | glass blur 偏重 | `--glass-blur: 18px`,2026 glassmorphism 退潮 | 🟢 低 |

### 1.5 已对齐 2026 主流的部分(应保持)

- Tauri 2 + Rust + React 栈 ✅
- AG-UI 协议接入(`core/ag_ui/mapper.py`)✅
- LangGraph 工作流(`graph/builder.py`)✅
- checkpoint/sqlite(`core/checkpoint/sqlite.py`)✅
- keyring crate OS Keychain(`secure.rs`)✅
- fnix-local 迁 Rust ✅
- glass 设计语言基础 + a11y 降级 ✅
- 无账号、BYOK、状态全本地 ✅

---

## 二、方案对比(三条升级路径)

### 方案 A:**保守加固**(只修不增)

- 范围:仅修 E1/E2/U1 三项 P0 问题 + 论文图表补全
- 优点:零风险、立即可交付
- 缺点:核心能力与最新研究差距不缩小,论文无新贡献
- 适合:论文已基本完成、只求投稿的场景
- 评估:**不够**,用户明确要求"项目不只是为了论文"

### 方案 B:**全面跃迁**(推倒重来)

- 范围:引入 KAG、Cognee、Letta、Zep、Automerge、PyO3 全套
- 优点:全面对标 2026 SOTA
- 缺点:**违反"不摇摆"原则**,引入效果未验证的新技术,工作量爆炸,有失败风险
- 评估:**否决**,违反用户偏好

### 方案 C:**核心能力务实升级**(推荐)

- 范围:**安全闭环(P0)+ 自进化可信化(P1)+ UX 极简化(P1)+ 论文图表演示补全(P2)**
- 优点:每项都有 2025-2026 论文依据,每项都有可执行代码路径,后端全免费
- 缺点:不解决多端协同(本就不是当前优先)
- 评估:**采纳**

---

## 三、推荐方案:核心能力务实升级 v2.0

### 3.1 战略目标(三层)

| 层 | 目标 | 衡量标准 |
|---|---|---|
| L1 工程 | 修复所有 P0 问题,达到"下载即用、安全默认" | E1/E2/U1 修复,安装即跑通 |
| L2 能力 | 自进化可信化,核心机制在公开 benchmark 有数据 | MuSiQue/HotpotQA 报分;引入 Sleep-time Compute 量化 |
| L3 体验 | 前端满足极简偏好,隐藏所有技术过程 | ToolCallCard 重构完成、Composer 三要素、骨架屏 |

### 3.2 不做清单(明确边界,避免摇摆)

- ❌ 不引入 Cognee/Letta/Zep(记忆系统重构,效果未验证)
- ❌ 不引入 Automerge 多端协同(本就不是当前优先)
- ❌ 不引入 PyO3 全栈重写(协议双跳开销可接受,优先级低于自进化可信化)
- ❌ 不引入 Docker/Firecracker 沙箱(桌面分发过重)
- ❌ 不做云端 Background Agent(违反本地优先)
- ❌ 不引入 A2A 多 Agent 协作(单 Agent 已足够)

---

## 四、技术选型(后端全免费)

### 4.1 安全闭环(P0)

| 决策 | 选型 | 依据 | 替代方案 |
|---|---|---|---|
| agentd 绑定地址 | 桌面 profile 强制 `127.0.0.1`,cloud profile 保留 `0.0.0.0` | Kleppmann 原则 6 默认安全 | — |
| BYOK 单一来源 | 废除 `.env` 明文 key,所有 key 经 keychain → Tauri 注入 agentd 内存 | secure.rs 已就绪 | 保留 `.env.example` 作模板 |
| 短时能力令牌 | 复用现有 `CapabilityMiddleware`,扩展为 LLM 调用代理(可选) | main.py 已有 | 不做(增加复杂度) |

### 4.2 自进化可信化(P1)

| 决策 | 选型 | 依据 | 复杂度 |
|---|---|---|---|
| 公开 benchmark | 接入 MuSiQue + HotpotQA + 2WikiMultiHop(全开源,免费) | 自进化研究 8 条建议之一 | 中 |
| 时序化 KTG | 给 KTG 节点加 `valid_from`/`valid_to` 双时态字段(借鉴 Zep Graphiti) | 对抗 misevolution(SJTU 2026 警示) | 中 |
| 规则引擎补强 | 扩展现有 `core/rules/engine.py`,加 KG-DSL 风格的规则推理(不引入 KAG 全栈) | KAG(arXiv:2409.13731)启发 | 中 |
| Sleep-time 量化 | 在 MFP Stage 2 固化阶段记录"离线耗时 vs 在线节省",引用 Sleep-time Compute(arXiv:2504.13171) | 量化 MFP 收益 | 低 |
| SWE-bench 子集 | 跑 SWE-bench Verified 500 题(免费,公开) | 与 SWE-agent/OpenHands 对比 | 高(可选) |

### 4.3 本地存储(P1)

| 决策 | 选型 | 依据 | 替代 |
|---|---|---|---|
| 主存储 | **SQLite + sqlite-vec**(已用 SQLite,加 sqlite-vec 扩展) | 纯 C 无依赖,零服务,完美本地优先 | LanceDB(Rust 核心) |
| 向量索引 | sqlite-vec(主)+ 可选 LanceDB(进阶) | 与 fnix-local 同语言 | FAISS |
| 嵌入模型 | bge-m3 经 Ollama 本地(免费),云端 embedding API 降级 | 多语言+多功能 | nomic-embed |
| 文档分档 | `ARCHITECTURE.md` 拆为 `ARCHITECTURE_DESKTOP.md`(SQLite)+ `ARCHITECTURE_CLOUD.md`(Milvus/PG) | 修复 E4 文档分裂 | — |

### 4.4 前端极简化(P1)

| 决策 | 选型 | 依据 |
|---|---|---|
| 工具调用展示 | ToolCallCard 重构为"行为摘要胶囊",默认折叠 | Cursor 胶囊化、ChatGPT 完全隐藏 |
| Composer | 仅保留对话框+附件+发送,modelSlot 移入"更多"菜单 | Raycast/ChatGPT 三要素 |
| AI 回复 | 接入 `utils/structuredBlocks.ts`,关键点/思路/过程分段渲染 | 用户偏好 |
| 骨架屏 | 新增 `Skeleton.tsx`,工具等待期投递 | Vercel Generative UI 铁律 |
| 主题 | 锁定亮色默认,blur 从 18px 降至 10-12px | 用户白底偏好 + 2026 趋势 |
| 检查点回滚 | ReviewView 暴露"恢复到此版本"按钮 | Cursor Checkpoint |
| Skills 隐藏 | SkillManager 移入设置二级 | ChatGPT 隐藏技术栈 |

### 4.5 协议与工作流(P2)

| 决策 | 选型 | 依据 |
|---|---|---|
| Agent 通信 | AG-UI 协议(已接入)+ 补 `StateDelta`(JSON Patch)增量同步 | AG-UI 2025 规范 |
| 长任务 | 对齐 LangGraph `interrupt/Command` 语义,实现"暂停-人审-续传" | LangGraph 容错三件套 |
| 沙箱 | 维持现有 OS 级方案,Windows 补 Job Object、macOS 补 Seatbelt | 桌面适配 |
| MCP 协议 | 按 2026-07-28 无状态规范接入新 MCP Server(废除 Session ID) | MCP 规范更新 |

### 4.6 论文与复现(P2)

| 决策 | 选型 | 依据 |
|---|---|---|
| 图表生成 | Python matplotlib 生成 architecture.pdf/flywheel.pdf/longitudinal.pdf | SUBMISSION_GUIDE.md |
| 实验补强 | exp2/exp3 真实 LLM 运行替换 mock 占位(BYOK,免费) | EXPERIMENT_REPORT.md 待办 |
| 公开 benchmark | MuSiQue/HotpotQA 报分作为 Section 5.5 新增 | 自进化研究建议 |
| 复现包 | 维持现有 `paper/reproduction/` Docker 一键复现 | 已就绪 |

---

## 五、实施架构

### 5.1 目标架构(演进后)

```
Desktop (Tauri 2, Rust+React)
   │  OS Keychain(keyring,唯一 BYOK 源)· PTY
   ↕  AG-UI 事件流(SSE + StateDelta JSON Patch)  ← 单一协议
fnix-agentd (Python FastAPI, 127.0.0.1:8003 only)
   │  LangGraph + interrupt/Command · MFP 四阶段(时序化)
   │  checkpoint/sqlite · sqlite-vec 向量索引 · core/rules(规则引擎)
   ↕  HTTP(维持,不重写为 PyO3)
fnix-local (Rust, :8710)
      SQLite + sqlite-vec(关系+向量,本地优先)
      OS 级沙箱(Seatbelt/Bubblewrap/Job Object)
      bge-m3 经 Ollama(嵌入,可选)

存储:SQLite(关系+向量,本地优先) + 文件(技能/产物/记忆)
配置:.env.example(模板,不存 key)+ keychain(运行时)
```

### 5.2 实施路线图(按优先级)

#### Phase 0:安全闭环(立即,1-2 天)

| 任务 | 代码路径 | 复杂度 | 依赖 |
|---|---|---|---|
| 0.1 agentd 桌面 profile 强制 `127.0.0.1` | `src/fnixagent/main.py:426,541` + `core/profile.py` | 低 | 无 |
| 0.2 BYOK 单一来源:废除 `.env` 明文 key 读取 | `core/llm/adapter.py:139-142` 改为只走 `harness/secrets.py` | 低 | 0.1 |
| 0.3 验证 keychain → Tauri → agentd 注入链路 | `secure.rs` + `main.py` 启动参数 | 低 | 0.2 |
| 0.4 文档:更新 `INSTALL.md` 说明 BYOK 流程 | `docs/INSTALL.md` | 低 | 0.3 |

#### Phase 1:前端极简化(短期,3-5 天)

| 任务 | 代码路径 | 复杂度 | 依赖 |
|---|---|---|---|
| 1.1 ToolCallCard 重构为行为摘要胶囊 | `apps/workbench/src/components/chat/ToolCallCard.tsx` | 中 | 无 |
| 1.2 Composer 极简化(三要素) | `apps/workbench/src/components/composer/*` | 低 | 无 |
| 1.3 AI 回复结构化接入 | `apps/workbench/src/utils/structuredBlocks.ts` + MarkdownRenderer | 中 | 无 |
| 1.4 骨架屏组件 | 新增 `apps/workbench/src/components/ui/Skeleton.tsx` | 中 | 无 |
| 1.5 亮色默认 + blur 降低 | `apps/workbench/src/ui/glass/tokens.css` | 低 | 无 |
| 1.6 Checkpoint 回滚入口 | `apps/workbench/src/components/review/ReviewView.tsx` | 中 | 后端 checkpoint 已就绪 |
| 1.7 Skills 入口移入设置 | `apps/workbench/src/components/chat/ChatHead.tsx` | 低 | 无 |

#### Phase 2:自进化可信化(中期,1-2 周)

| 任务 | 代码路径 | 复杂度 | 依赖 |
|---|---|---|---|
| 2.1 KTG 时序化(`valid_from`/`valid_to`) | `core/topology/schema.py` + `graph.py` + `store.py` | 中 | 无 |
| 2.2 规则引擎补强(KG-DSL 风格) | `core/rules/engine.py`(已存在,扩展) | 中 | 无 |
| 2.3 MFP Sleep-time 量化 | `core/flywheel/stage2_knowledge.py` + `stage4_climbing.py` | 低 | 2.1 |
| 2.4 MuSiQue benchmark 接入 | 新增 `paper/experiments/exp5_musique.py` | 中 | 2.1 |
| 2.5 HotpotQA benchmark 接入 | 新增 `paper/experiments/exp6_hotpotqa.py` | 中 | 2.1 |
| 2.6 exp2/exp3 真实 LLM 运行替换 mock | `paper/experiments/exp2_ktg_ablation.py` + `exp3_*.py` | 中 | Phase 0 |

#### Phase 3:存储与协议(P2,可选)

| 任务 | 代码路径 | 复杂度 | 依赖 |
|---|---|---|---|
| 3.1 sqlite-vec 接入 | `core/checkpoint/sqlite.py` + 新增向量索引层 | 中 | 无 |
| 3.2 文档拆分 DESKTOP/CLOUD | `ARCHITECTURE.md` → 拆分 | 低 | 无 |
| 3.3 AG-UI StateDelta 补齐 | `core/ag_ui/mapper.py` | 中 | 无 |
| 3.4 LangGraph interrupt/Command 对齐 | `core/run/engine.py` + `checkpoint/` | 中 | 无 |
| 3.5 沙箱跨平台补齐 | `core/agentos/sandbox.py` + `syscall.py` | 中 | 无 |

#### Phase 4:论文图表与实验(与 Phase 2 并行)

| 任务 | 代码路径 | 复杂度 | 依赖 |
|---|---|---|---|
| 4.1 architecture.pdf 生成 | `paper/figures/`(draw.io 或 matplotlib) | 低 | 无 |
| 4.2 flywheel.pdf 生成 | 同上 | 低 | 无 |
| 4.3 longitudinal.pdf 生成 | `paper/figures/` + matplotlib 读取 exp4 数据 | 低 | 无 |
| 4.4 Section 5.5 新增公开 benchmark | `paper/main.tex` | 中 | 2.4/2.5 |

### 5.3 不变更清单(保持现状)

- 三进程架构(Tauri + agentd + fnix-local)— 方向正确
- Tauri 2 + Rust + React + TypeScript 栈
- LangGraph + AG-UI + checkpoint
- keyring crate OS Keychain
- glass 设计语言基础
- 无账号、BYOK、状态全本地

---

## 六、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 时序化 KTG 破坏现有 1813 项测试 | 中 | 高 | 加 schema 迁移脚本,旧数据 `valid_to=null` 表示永久有效 |
| MuSiQue/HotpotQA 分数低于预期 | 高 | 中 | 论文诚实报告,强调"本地 BYOK 约束下的相对提升"而非绝对 SOTA |
| 规则引擎补强引入复杂度 | 中 | 中 | 不引入 KAG 全栈,只扩展 `core/rules/engine.py` 现有结构 |
| Phase 1 前端改动引入 regression | 中 | 中 | 维持现有测试套件,新增 UX 单元测试 |
| Phase 3 可选任务被无限延展 | 高 | 低 | Phase 3 标记为"可选",论文投稿前不强制完成 |

---

## 七、成功标准

### 7.1 工程层(Phase 0)

- [ ] agentd 桌面 profile 默认 `127.0.0.1`,从外部无法访问
- [ ] `.env` 中不再存储 API key,所有 key 经 keychain
- [ ] 现有 1813 项测试 100% 通过

### 7.2 体验层(Phase 1)

- [ ] ToolCallCard 默认折叠为胶囊,不显示工具名/params
- [ ] Composer 仅含对话框+附件+发送
- [ ] AI 回复按关键点/思路/过程分段
- [ ] 工具等待期显示骨架屏
- [ ] 默认亮色,blur ≤ 12px

### 7.3 能力层(Phase 2)

- [ ] KTG 节点支持 `valid_from`/`valid_to`
- [ ] MuSiQue/HotpotQA 报分(相对值,不强求 SOTA)
- [ ] MFP 固化阶段记录 Sleep-time 量化数据
- [ ] exp2/exp3 真实 LLM 数据替换 mock 占位

### 7.4 论文层(Phase 4)

- [ ] 三个 PDF 图表生成
- [ ] Section 5.5 新增公开 benchmark 数据
- [ ] `paper/main.pdf` 可编译生成

---

## 八、执行优先级总览

```
P0(立即):Phase 0 安全闭环 → Phase 4.1-4.3 图表
P1(短期):Phase 1 前端极简化(并行)
P1(短期):Phase 2 自进化可信化(并行)
P2(可选):Phase 3 存储与协议(论文投稿前不强制)
P2(可选):Phase 4.4 论文新增 benchmark(依赖 2.4/2.5)
```

**关键路径**:Phase 0 → Phase 2.6(exp2/exp3 真实运行)→ Phase 4.4(论文新增)

**并行路径**:Phase 1(前端)+ Phase 2.1-2.5(自进化)+ Phase 4.1-4.3(图表)

---

## 附录:研究底座索引

- `docs/research/SELF_EVOLUTION_RESEARCH.md` — 自进化 agent 与 KG 最新进展(260 行)
- 竞品研究报告(内联)— 14 个竞品对比 + MCP 生态 + 记忆系统 6 路线
- 架构研究报告(内联)— Tauri/PyO3/AG-UI/Automerge/LanceDB 最佳实践 + FnixAgent 8 项痛点
- UX 研究报告(内联)— 15+ 产品 UX 对比 + 10 条可执行建议

关键 arXiv 编号(均已交叉验证):
- EvolveR: 2510.16079(ICML 2026)
- Sleep-time Compute: 2504.13171(Letta/UC Berkeley)
- KAG: 2409.13731(蚂蚁+浙大)
- RouteLLM: 2406.18665
- Router-R1: 2506.09033(NeurIPS 2025)
- LongMemEval: 2410.10813(ICLR 2025)
- HippoRAG: 2405.14831(NeurIPS 2024)
- LightRAG: 2410.05779
- Voyager: 2305.16291
