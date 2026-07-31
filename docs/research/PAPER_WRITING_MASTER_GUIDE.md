# FnixAgent 论文写作总纲

> 编制日期:2026-08-01 ｜ 基于 4 份并行研究报告(竞品/架构/自进化/UX)+ 代码库实测
> 用途:作为论文写作的长期方向索引与素材库,随项目演进持续更新
> 项目双线定位:**真实可用的产品**(本地优先 AI Agent 工作台)+ **可发表的研究产物**(支持多篇论文)

---

## 第一部分:项目核心定位

### 1.1 一句话定位

FnixAgent 是一个**本地优先、BYOK、自进化的 AI Agent 工作台**,通过三进程桌面架构(Tauri → agentd → fnix-local)将知识拓扑图(KTG)、四阶段飞轮(MFP)、难度自适应路由(DAAO)三个机制耦合为单一闭环,同时服务代码与文档/Office 类工作。

### 1.2 差异化护城河(竞品空白验证)

基于 14 个竞品研究(Cursor/Cline/Aider/Claude Code/Codex/Continue/Trae/Qoder/Windsurf/Devin/Copilot/Replit/Bolt/v0),FnixAgent 占据的空白是:

> **本地派(Aider/Cline/Continue)不自进化;自进化派(Devin/Cursor Cloud/Qoder)云端闭源。**

FnixAgent 是唯一同时满足"本地优先 + BYOK + 自进化 + 知识图谱 + 代码&Office 双模 + 开源"六个维度的产品。

### 1.3 真实可用性证据(已验证)

- 1813 项测试全部通过(1666 单元 + 100 集成 + 25 顶层 E2E + 22 KTG 单元)
- 三进程架构已落地:Tauri 2(Rust+React)→ agentd(Python FastAPI, :8003)→ fnix-local(Rust, :8710)
- BYOK 已支持 OpenAI/Qwen/DeepSeek/GLM/Custom,经 OS Keychain 安全存储
- AG-UI 协议已接入,LangGraph 工作流已落地,checkpoint/sqlite 断点续传已实现
- 代码模式(多文件生成+diff 接受)+ 工作模式(Word/PDF/Excel/PPT)均已可用

---

## 第二部分:可发表的论文方向(分类)

基于研究底座,FnixAgent 至少可支撑 **5 个不同方向**的论文,按可行性排序:

### 方向 A:系统论文(Tool Track,主推)

**标题方向**:*FnixAgent: A Local-First Self-Evolving AI Agent Workbench with Knowledge Topology Graph*

**目标会议**:ACM FSE 2027(截稿 2026-10-02)/ ASE 2027 / TOSEM 期刊

**核心贡献**:
1. 三进程本地优先架构(Tauri+agentd+fnix-local,能力令牌隔离)
2. KTG 固定四层 schema + 权重驱动路径搜索(MUTEX 惩罚)
3. MFP 四阶段飞轮(snapshot+rollback 安全的自进化)
4. DAAO 零 LLM 路由 + HERA 闭环反馈
5. FCS 1000 任务基准 + 五信号评分

**当前进度**:论文初稿已完成(`paper/main.tex`),需补真实实验数据

**待办**:
- [ ] exp2/exp3 真实 LLM 运行替换 mock 占位
- [ ] MuSiQue/HotpotQA 公开 benchmark 报分(新增 Section 5.5)
- [ ] SWE-bench 子集对比 SWE-agent/OpenHands
- [ ] 三张 PDF 图表生成

**研究依据**:自进化研究 + 架构研究 + 竞品研究

---

### 方向 B:方法论文(Research Track,KTG 单点突破)

**标题方向**:*KTG: Weight-Driven Path Search over a Fixed-Schema Knowledge Topology Graph for Local-First Agents*

**目标会议**:NeurIPS 2027 / ICLR 2027 / ACL 2027(若拆方法)

**核心研究问题**:在本地优先约束(无大模型检索器、无云端图谱构建)下,固定 schema 知识图谱 + 权重路径搜索能否超越向量 RAG 和动态 GraphRAG?

**已有数据**:
- exp2 KTG ablation(当前 mock):full_ktg 100% hit rate / vector_rag 77.8% / graph_rag_sim 66.7% / no_ktg 0%
- 任务分数(mock):KTG 85 > Vector 67 > GraphRAG 78 > No 58

**待补强(诚实)**:
- ⚠️ KAG(arXiv:2409.13731)的 KG-DSL 规则引擎在 2wiki +19.6%、HotpotQA +33.5% F1,**表达力强于 KTG 固定 schema**
- ⚠️ 需在 MuSiQue/HotpotQA/2WikiMultiHop 公开 benchmark 上与 GraphRAG/HippoRAG/LightRAG/KAG 对比
- ⚠️ 论文需诚实说明 KTG 的固定 schema 是"为了本地优先稳定性"的工程取舍,而非表达力最优

**预期新贡献**:
- KTG 时序化(`valid_from`/`valid_to`)对抗 misevolution
- Sleep-time Compute(arXiv:2504.13171)量化 KTG 固化收益
- 与 KAG 的对比讨论(承认 KG-DSL 表达力,但强调本地优先约束下的稳定性优势)

**研究依据**:自进化研究 (b) 部分 + (e) KTG 定位

---

### 方向 C:自进化方法论文(MFP 单点突破)

**标题方向**:*MFP: A Four-Stage Self-Evolution Flywheel with Snapshot-and-Rollback Safety for LLM Agents*

**目标会议**:NeurIPS 2027 / ICML 2027 / AAAI 2027

**核心研究问题**:LLM Agent 能否在不重训模型的前提下,通过结构化知识图谱的权重演化实现持续学习?

**对标工作**:
- Voyager(arXiv:2305.16291):技能库,但仅 Minecraft 沙盒
- Reflexion(arXiv:2303.11351):反思但 ephemeral,不持久
- EvolveR(arXiv:2510.16079, ICML 2026):**离线自蒸馏+在线 RL,多跳 QA SOTA**
- Sleep-time Compute(arXiv:2504.13171, Letta):**量化离线收益,5× test-time 节省**
- ExpeL:经验学习但不修改图谱权重

**诚实诊断**:
- ⚠️ **EvolveR 在多跳 QA 上已超越 MFP**
- ⚠️ MFP 缺乏量化收益(未引用 Sleep-time Compute 理论)
- ✅ MFP 的"snapshot+rollback 安全网"和"HERA 失败率反馈"是差异化

**预期新贡献**:
- 引入 Sleep-time Compute 量化 MFP Stage 2 固化收益
- 时序化对抗 misevolution(SJTU 2026 警示)
- 与 EvolveR/ExpeL/Sleep-time Compute 的对比讨论

**研究依据**:自进化研究 (a) 部分 + (e) MFP 定位

---

### 方向 D:路由方法论文(DAAO 单点突破)

**标题方向**:*DAAO: Zero-LLM Difficulty-Aware Routing with HERA Feedback for Local-First Agents*

**目标会议**:AAAI 2027 / IJCAI 2027 / NAACL 2027

**核心研究问题**:在零额外 LLM 调用约束下,启发式难度路由 + 失败率反馈闭环能否逼近学习型路由器?

**对标工作**:
- RouteLLM(arXiv:2406.18665):成本降 2×,但需训练
- Router-R1(arXiv:2506.09033, NeurIPS 2025):RL 路由,首个多轮
- FrugalGPT:级联路由

**差异化**:
- ✅ DAAO 零 LLM 调用 + HERA 失败率闭环在路由领域**确有独特性**
- ✅ 本地优先约束下的路由是空白
- ⚠️ 需在公开 benchmark 上验证(自建 FCS 不够)

**预期新贡献**:
- HERA 闭环的消融实验(开/关反馈信号)
- 与 RouteLLM/Router-R1 在 SWE-bench 上的对比
- "零成本路由"的工程价值量化

**研究依据**:自进化研究 (d) 部分 + (e) DAAO 定位

---

### 方向 E:基准论文(FCS 单点突破)

**标题方向**:*FCS: A 1000-Task Capability Benchmark for Local-First AI Agent Workbenches*

**目标会议**:ICSE 2027 / FSE 2027 Data Track / NAACL 2027 Datasets

**核心研究问题**:如何系统评估"本地优先 + 双模(代码&Office)"Agent 工作台的能力覆盖?

**当前数据**:
- 1000 任务(9 seed + 991 generated)
- 10 能力维度(write/edit/multi_file/cli/refactor/bugfix/test_gen/api/search/heal)
- 难度 L1-L3
- schema 100% 有效
- 五信号评分(correctness/completeness/process/safety/speed)

**待补强**:
- ⚠️ 能力分布不均(write 占 83%,部分维度仅 1 任务)
- ⚠️ 全 Python,无多语言
- ⚠️ 自建自标,缺第三方验证(Cohen's κ ≥ 0.7)
- ⚠️ 难度 L4/L5 为空

**预期新贡献**:
- 补充 Java/TypeScript 任务
- 引入第三方标注者一致性检验
- 扩展 L4/L5 难度

**研究依据**:架构研究 + 竞品研究(无直接对标基准)

---

## 第三部分:论文写作通用要素

### 3.1 论文必备章节与素材库

每篇论文都需要的章节,素材统一管理:

| 章节 | 素材位置 | 状态 |
|---|---|---|
| Abstract | `paper/main.tex` | ✅ 已写 |
| Introduction | `paper/main.tex` | ✅ 已写 |
| Background | `paper/main.tex` | ✅ 已写 |
| System Design | `paper/main.tex` | ✅ 已写 |
| Implementation | `paper/main.tex` | ✅ 已写 |
| Evaluation | `paper/main.tex` | ⚠️ exp2/exp3 mock |
| Discussion | `paper/main.tex` | ✅ 已写 |
| Related Work | `paper/main.tex` | ✅ 已写 |
| Conclusion | `paper/main.tex` | ✅ 已写 |
| References | `paper/refs.bib` | ✅ 已写(30 条) |

### 3.2 通用引用文献库(已整理)

#### 自进化 Agent
- Voyager(arXiv:2305.16291,NeurIPS 2023)— Minecraft 技能库
- Reflexion(arXiv:2303.11351,NeurIPS 2023)— 言语强化
- Self-Refine(arXiv:2303.17651,NeurIPS 2023)— 自精炼
- EvolveR(arXiv:2510.16079,ICML 2026)— **离线自蒸馏+在线 RL**
- Sleep-time Compute(arXiv:2504.13171,Letta/UC Berkeley)— **离线量化**
- ExpeL — 经验学习
- AgentTuning — Agent 微调

#### 知识图谱 + LLM
- GraphRAG(arXiv:2404.16130,Microsoft)— 动态图
- HippoRAG(arXiv:2405.14831,NeurIPS 2024)— 神经生物学启发,**+20% 多跳 QA**
- LightRAG(arXiv:2410.05779,HKU)— 双层级检索
- HCG-RAG(arXiv:2607.22592)— 固定 schema 因果图
- KG-RAG(arXiv:2405.12035)— 生物医学
- KAG(arXiv:2409.13731,蚂蚁+浙大)— **KG-DSL 规则引擎,2wiki +19.6%、HotpotQA +33.5% F1**
- Cognee — Apache-2.0 GraphRAG

#### Agent 记忆系统
- MemGPT/Letta — OS 式分层自编辑
- Mem0 — 向量+图谱分层
- Zep(Graphiti)(arXiv:2501.13956)— **双时态模型,LongMemEval +18.5%**
- Supermemory — <300ms 编程 Agent
- MemClaw — 多 Agent 治理

#### LLM 路由
- RouteLLM(arXiv:2406.18665)— 成本降 2×
- Router-R1(arXiv:2506.09033,NeurIPS 2025)— RL 路由
- FrugalGPT — 级联路由

#### Agent 系统(对比基线)
- SWE-agent(arXiv:2412.16947,Princeton)
- OpenHands(arXiv:2407.16741,60k★)
- MetaGPT(arXiv:2308.00352)
- Cursor、Devin、Copilot、Replit Agent(商业对比)

#### 基准
- SWE-bench(arXiv:2310.06770)— Python issue
- LongMemEval(arXiv:2410.10813,ICLR 2025)— 500 题持续交互
- MuSiQue — 多跳推理
- HotpotQA — 多跳 QA
- 2WikiMultiHop — 双跳

#### 推理基础
- ReAct(arXiv:2210.03629,ICLR 2023)
- Chain-of-Thought(arXiv:2201.11903,NeurIPS 2022)
- Plan-and-Solve(arXiv:2305.04091,ICLR 2023)
- Toolformer(arXiv:2302.04761,NeurIPS 2023)
- ToolLLM(arXiv:2307.16789,ICLR 2024)

#### LLM 基础
- Attention Is All You Need(arXiv:1706.03762,NeurIPS 2017)
- GPT-3(arXiv:2005.14165,NeurIPS 2020)
- GPT-4 Technical Report(OpenAI 2023)

#### 基础设施
- Tauri(官方文档)
- LangChain(Chase 2022)
- AIMA(Russell & Norvig 2016)
- Local-First Software(Kleppmann,Onward! 2019)

### 3.3 通用图表库

| 图表 | 用途 | 状态 |
|---|---|---|
| architecture.pdf | Figure 1 三进程架构 | ⚠️ 待生成 |
| flywheel.pdf | Figure 2 MFP 四阶段 | ⚠️ 待生成 |
| longitudinal.pdf | Figure 3 KTG 纵向演化 | ⚠️ 待生成 |
| fcs_distribution.json | FCS 能力×难度矩阵 | ✅ 已有 |
| exp1_fcs_stats.json | FCS 1000 任务统计 | ✅ 已有 |
| exp4_longitudinal.json | 1/7/30/90 天演化 | ✅ 已有 |
| exp2_ktg_ablation.json | KTG 消融(mock) | ⚠️ 待真实运行 |
| exp3_ablation.json | MFP×DAAO 消融(mock) | ⚠️ 待真实运行 |
| mock_ablation_results.json | mock 占位 | ✅ 已有 |

### 3.4 通用复现包

- `paper/reproduction/Dockerfile` + `docker-compose.yml` — Docker 一键复现 ✅
- `paper/reproduction/eval_mock.py` — Mock 评估 ✅
- `paper/reproduction/REPRODUCE.md` — 复现协议 ✅
- `paper/experiments/run_all.py` — 实验编排 ✅

### 3.5 通用威胁有效性声明

每篇论文都应包含:

**内部有效性**:
- FCS 自建自标,非独立社区基准(对照 SWE-bench)
- LLM 依赖实验在 seed 子集跑,绝对分数有模型/温度方差,强调差异而非绝对值

**外部有效性**:
- BYOK 导致结果依赖用户所选 LLM
- 弱模型会下移所有条件,但相对贡献应保持

**构造有效性**:
- DAAO 难度估计是手工启发式,关键词词典有领域偏置

---

## 第四部分:可执行改造路线(论文配套)

按论文优先级排序的工程改造,完成一项勾选一项:

### 4.1 P0 立即(影响所有论文)

| 编号 | 任务 | 论文影响 | 代码路径 | 复杂度 |
|---|---|---|---|---|
| P0-1 | agentd 绑定 127.0.0.1 | 实现章节"安全默认" | `src/fnixagent/main.py:426,541` | 低 |
| P0-2 | 废除 .env 明文 key | 实现章节"BYOK 安全" | `core/llm/adapter.py:139-142` | 低 |
| P0-3 | 三张 PDF 图表生成 | Section 5 配图 | `paper/figures/` | 低 |

### 4.2 P1 短期(方向 A 系统论文必需)

| 编号 | 任务 | 论文影响 | 代码路径 | 复杂度 |
|---|---|---|---|---|
| P1-1 | exp2 真实 LLM 运行 | Section 5.2 RQ1 真实数据 | `paper/experiments/exp2_ktg_ablation.py` | 中 |
| P1-2 | exp3 真实 LLM 运行 | Section 5.3 RQ2 真实数据 | `paper/experiments/exp3_mfp_daao_ablation.py` | 中 |
| P1-3 | MuSiQue benchmark 接入 | Section 5.5 新增 | 新增 `paper/experiments/exp5_musique.py` | 中 |
| P1-4 | HotpotQA benchmark 接入 | Section 5.5 新增 | 新增 `paper/experiments/exp6_hotpotqa.py` | 中 |
| P1-5 | KTG 时序化 | Discussion 创新点 | `core/topology/schema.py` + `graph.py` | 中 |
| P1-6 | MFP Sleep-time 量化 | Section 5.3 量化依据 | `core/flywheel/stage2_knowledge.py` | 低 |

### 4.3 P1 短期(方向 B/C/D 方法论文)

| 编号 | 任务 | 论文影响 | 代码路径 | 复杂度 |
|---|---|---|---|---|
| P1-7 | 规则引擎补强(KG-DSL 风格) | 方向 B KTG 论文 | `core/rules/engine.py` | 中 |
| P1-8 | HERA 闭环消融实验 | 方向 D DAAO 论文 | 新增 `paper/experiments/exp7_hera_ablation.py` | 中 |
| P1-9 | SWE-bench 子集对比 | 方向 A/E | 新增 `paper/experiments/exp8_swebench.py` | 高 |

### 4.4 P2 中期(方向 E 基准论文)

| 编号 | 任务 | 论文影响 | 代码路径 | 复杂度 |
|---|---|---|---|---|
| P2-1 | FCS 补 Java/TS 任务 | 基准多语言 | `benchmarks/code/` | 中 |
| P2-2 | 第三方标注一致性 | 基准可信度 | 外部协作 | 高 |
| P2-3 | L4/L5 难度任务 | 基准完整度 | `core/code/benchmark/` | 中 |

### 4.5 P2 中期(用户体验,影响系统论文 Case Study)

| 编号 | 任务 | 论文影响 | 代码路径 | 复杂度 |
|---|---|---|---|---|
| P2-4 | ToolCallCard 重构 | Case Study UX | `apps/workbench/src/components/chat/ToolCallCard.tsx` | 中 |
| P2-5 | Composer 极简化 | Case Study UX | `apps/workbench/src/components/composer/*` | 低 |
| P2-6 | 骨架屏 | Case Study UX | 新增 `Skeleton.tsx` | 中 |
| P2-7 | User Study(10 用户/1 周) | Section 5.6 新增 | 外部协作 | 高 |

---

## 第五部分:研究底座索引

所有研究报告位置:

| 报告 | 位置 | 内容 |
|---|---|---|
| **自进化研究** | `docs/research/SELF_EVOLUTION_RESEARCH.md` | 9 个自进化工作对比 + 9 个 KG+LLM 对比 + 7 个记忆系统对比 + 5 个路由对比 + KTG/MFP/DAAO 定位 + 8 条升级建议 |
| 竞品研究 | 内联(本次对话) | 14 个竞品对比表 + MCP 生态 + 记忆系统 6 路线 + 差异化机会 |
| 架构研究 | 内联(本次对话) | Tauri/PyO3/AG-UI/Automerge/LanceDB 最佳实践 + FnixAgent 8 项痛点 |
| UX 研究 | 内联(本次对话) | 15+ 产品 UX 对比 + 10 条可执行建议 |
| 升级方案 | `docs/UPGRADE_PLAN_v2.md` | 综合方案 C(核心能力务实升级) |

---

## 第六部分:目标会议与时间线

### 6.1 主推:FSE 2027(系统论文)

- 截稿:2026-10-02
- Track:Tool Track(推荐)/ Research Track
- 时间线:
  - 2026-08:完成 Phase 0 安全 + Phase 1 实验补强
  - 2026-09-15:内审 + 修改
  - 2026-09-25:提交

### 6.2 备选:ASE 2027(吸收 FSE 审稿意见)

- 截稿:2027-03
- 同领域,可吸收 FSE 反馈

### 6.3 方法论文备选(若系统论文被拒)

- NeurIPS 2027(截稿 2027-05):拆 KTG 或 MFP 方法
- ICML 2027:拆 MFP 方法
- ICLR 2027:拆 DAAO 方法

### 6.4 期刊备选(无截稿压力)

- TOSEM(ACM Transactions on SE):系统完整性高后投
- TSE(IEEE Transactions on SE):备选

### 6.5 基准论文备选

- ICSE 2027 Data Track:FCS 基准
- NAACL 2027 Datasets:FCS 多语言扩展版

---

## 第七部分:写作原则提醒

基于用户偏好与学术规范:

### 7.1 必须诚实处理的弱点

1. **KTG vs KAG**:承认 KAG 的 KG-DSL 表达力更强,但强调 KTG 的"固定 schema + 本地优先 + 权重路径搜索"是工程取舍
2. **MFP vs EvolveR**:承认 EvolveR 在多跳 QA 已超越,但强调 MFP 的"snapshot+rollback 安全网 + HERA 闭环"在本地优先约束下的差异化
3. **FCS 样本量**:1000 任务但分布不均(write 83%),需说明采样策略
4. **七层 Intelligence**:几层未接入主路径,不夸大
5. **无公开 benchmark**:这是最大信任缺口,必须补 MuSiQue/HotpotQA

### 7.2 必须强调的差异化

1. **本地优先 + BYOK + 自进化**三联定位是竞品空白
2. **DAAO 零 LLM 调用 + HERA 失败率反馈**在路由领域独特
3. **代码 + Office 双模**避开纯编码红海
4. **三进程能力令牌隔离**的安全架构
5. **1813 项测试 + 开源 + 复现包**的工程完整性

### 7.3 论文格式要求

- ACM sigconf(acmart 文档类)
- 正文 12 页(不含参考文献)
- BibTeX + ACM Reference Format
- 三张 PDF 图(矢量格式)
- 匿名化处理(移除 GitHub URL,作者信息可保留非双盲)

### 7.4 论文写作禁忌

- ❌ 不要夸大"七层 Intelligence"为已落地
- ❌ 不要把 mock 数据当真实结果引用
- ❌ 不要回避与 EvolveR/KAG 的对比
- ❌ 不要用绝对分数(85、68),要强调相对差异
- ❌ 不要把"自进化"当营销词,要用 Sleep-time Compute 量化

---

## 第八部分:持续更新机制

本文档作为论文写作的活文档,随项目演进持续更新:

### 8.1 更新触发

- 完成一项 P0/P1/P2 任务后,勾选对应表格
- 跑出新实验数据后,补充到 3.3 图表库
- 发现新对标论文后,补充到 3.2 引用文献库
- 投稿后,根据审稿意见更新

### 8.2 关联文档

- `paper/main.tex` — 论文主文件
- `paper/refs.bib` — 参考文献
- `paper/EXPERIMENT_REPORT.md` — 实验报告
- `paper/SUBMISSION_GUIDE.md` — 投稿教程
- `docs/UPGRADE_PLAN_v2.md` — 升级方案
- `docs/research/SELF_EVOLUTION_RESEARCH.md` — 自进化研究

### 8.3 关键 arXiv 速查

| 编号 | 论文 | 用途 |
|---|---|---|
| 2510.16079 | EvolveR(ICML 2026) | MFP 主要对标 |
| 2504.13171 | Sleep-time Compute | MFP 量化依据 |
| 2409.13731 | KAG | KTG 主要对标 |
| 2406.18665 | RouteLLM | DAAO 对标 |
| 2506.09033 | Router-R1(NeurIPS 2025) | DAAO 对标 |
| 2410.10813 | LongMemEval(ICLR 2025) | 记忆评估 |
| 2405.14831 | HippoRAG(NeurIPS 2024) | KG 对比 |
| 2410.05779 | LightRAG | KG 对比 |
| 2305.16291 | Voyager | 自进化对标 |
| 2303.11351 | Reflexion | 自进化对标 |
| 2404.16130 | GraphRAG(Microsoft) | KG 对比 |
| 2310.06770 | SWE-bench | 基准对标 |
| 2412.16947 | SWE-agent | 系统对标 |
| 2407.16741 | OpenHands | 系统对标 |

---

## 结语

FnixAgent 是真实可用的产品,同时也是可发表的研究产物。本总纲整理了:

- **5 个论文方向**(系统/方法/基准,可拆可合)
- **30+ 条引用文献**(全部带 arXiv 编号)
- **20+ 项可执行改造任务**(按论文优先级排序)
- **6 个目标会议/期刊**(主推 + 备选)

不急于立即实施所有任务。本总纲是论文写作的长期索引,随项目完善持续更新。当真正写论文时,按方向选择对应章节,勾选已完成任务,补充新实验数据即可。

**当前最优先**:Phase 0 安全闭环(影响所有论文的"实现"章节可信度)+ Phase 1 实验补强(影响所有论文的 Evaluation 章节)。
