# Spec 2-7 评估与实施计划

> 日期: 2026-07-30
> 依据: Phase 1 全面代码审计 + DDG/WebSearch 深研(Cursor 2026 / Claude Code / AG-UI / Vercel Streamdown / Anthropic Effective Harnesses / Cursor Bugbot Learning / Reflexion 论文 / CLAUSE / KG-Agent / Aider / Cline / DeerFlow)
> 原则: 以真实用户体验和工具效率为根本评估标准,识别真需求与过度设计

---

## 一、执行摘要

经过对项目当前状态的全面审计与业界顶级方案的对比研究,核心结论如下:

**项目实际完成度远超设计文档描述**。2026-07-20/21 两份设计文档中规划的 Spec 2/3 在代码中已完整实现(虽文件名与文档不符,但功能更完整)。Spec 4/5/6/7 的核心能力也大部分真实落地,仅存在若干真实差距和部分过度设计。

**真正需要做的工作不多,但都很关键**:
- 三处真实功能差距(影响用户体验)
- 四处过度设计裁剪(降低维护成本和认知负担)
- 五处测试盲区补全(保障生产可靠性)

**核心判断**: 不应继续堆叠新框架,而应**收敛、补全、裁剪**。当前项目的最大风险不是"能力不够",而是"能力过多但未对齐、未测试、未接入主路径"。

---

## 二、各 Spec 评估结论

### Spec 2: 过程可视化 — 已满足,无需额外实现

**现状诊断**:
- `structuredBlocks.ts` 已实现 8 种 block kind(thinking/progress/tool_call/tool_result/diff/error/text/widget),完整对齐 AG-UI 协议核心语义
- `ThinkingBlock` 可折叠(progressive disclosure,对标 Claude Code)
- `ToolCallCard` 含 isError 推断(从后续 tool_result 配对推断)
- `ToolResultCard` head-and-tail 折叠(对标 Claude Code)
- `DiffBlock` 三态审查(pending/accepted/rejected)
- `ErrorBlock` 严重级别恢复(transient/persistent/fatal)
- `WidgetBlock` iframe sandbox(对标 Trae dynamic-ui)
- `ProcessTimeline` 执行控制台(4 种过滤器)

**对比业界**: Cursor 2026 / Claude Code / AG-UI 协议的核心可视化能力(思考链折叠、工具调用卡、diff 预览、错误恢复)均已覆盖。Vercel Streamdown 的 streaming token 鲁棒性是 P2 边缘场景,当前 react-markdown 流式表现尚可。

**结论**: 设计文档想要的 streaming token + tool call card + diff 即时预览 + 思考链折叠**均已实现**。极简新中式宋韵风是审美偏好,非 UX/效率需求,根据"功能必须评估真实必要"原则不做。

**动作**: 无。仅在文档中标记 Spec 2 为"已满足"。

---

### Spec 3: Artifact Canvas — 已满足,无需额外实现

**现状诊断**:
- `ArtifactCanvas.tsx` 是真实渲染层(文件注释明示 "Spec 3: ArtifactCanvas — 产物画布")
- `CanvasView.tsx` 是外壳,在 `ChatGptDesktopApp.tsx:1132`(Work 模式)和 `:1279`(Code 模式)两处使用
- 与 `WidgetBlock` / `BrowserView` / `MarkdownRenderer` / `MermaidBlock` 有清晰的边界划分(注释明示:ArtifactCanvas = 磁盘产物可编辑可持久化;WidgetBlock = 即时 HTML 沙盒;MermaidBlock = 主线程渲染)
- `ResultsView.tsx:6` 注释 "Spec 3: Preview tab 升级为真正的 ArtifactCanvas 内联预览"

**对比业界**: ChatGPT Canvas 的协作编辑、Claude Artifacts 的增量更新均已覆盖。

**结论**: 已完整集成,无需额外实现。

**动作**: 无。仅在文档中标记 Spec 3 为"已满足"。

---

### Spec 4: 长程任务 + Compaction + Checkpoint Resume — 核心已对齐业界,缺三件套

**现状诊断**:

| 能力 | 状态 | 证据 |
|------|------|------|
| 15s 心跳 | ✅ 已实现 | `loop.py:787-835` 严格 15s asyncio 心跳 |
| Compaction 四层 | ✅ 超出业界 | L1 LLM summary + L2 boundary-aware sliding window + L3 deterministic truncate + 三级 escalation(`compaction.py:642-754`),Claude Code 仅单层 |
| 软/硬阈值异步 | ✅ 超出业界 | `BackgroundCompactor` τsoft=50K/τhard=80K(`compaction.py:775-948`) |
| cache-safe forking | ✅ 已对齐 | `compaction.py:215-262` 复用父 messages prefix |
| Checkpoint 三层存储 | ✅ 已实现 | 内存 dict + Redis(可选) + JSONL/SQLite(`manager.py:155-162`) |
| 双表 schema WAL | ✅ 已实现 | `sqlite.py:54-86` checkpoints + writes 表 |
| resume_from_checkpoint | ✅ 全栈打通 | `loop.py:618-722` + `engine.py:131-266` + `work.py:843-1034` API |
| Reflexion 修复循环 | ✅ 已实现 | `work_pipeline.py:1255-1288` 从 checkpoint 重建 repair_resume_from |
| Flywheel KTG/STP/MFP | ✅ 真触发 | `work_agent.py:236-289` run_mfp_after_task 真调用 |

**三个真实差距**(对比 Claude Code TodoWrite / Cursor web dashboard / Anthropic harness):

**差距 1: load-bearing state 外化** — 必要
- 当前 compaction summary 虽保留 4 项关键信息,但 LLM 生成 summary 有损,长程任务(8h+)累积多次 compaction 后会丢失关键决策
- Claude Code 用 TodoWrite 写 `.claude/todos.json`,compaction 后通过 system-reminder 重新注入
- **建议**: 把 `traces.jsonl` 已有的 tool_calls + artifacts 路径,显式外化为 `.fnix/todos.json`,compaction 后通过 system prompt 重新注入

**差距 2: 多步进度可视化** — 必要
- `loop.py:749-756` 已发出 `step_start`/`step_end` 事件,但前端 `GlassGoalRow` 只是单一任务行+计时器,不渲染多步进度
- 长程任务用户最焦虑"进行到哪一步了,还要多久"
- **建议**: 扩展 `GoalProgressRow` 或新增 `StepProgressStrip.tsx`,消费 step_start/step_end 事件,显示 `Step 3/10 · 思考中`

**差距 3: 跨 session run 历史回看** — 必要
- 后端 `RunCheckpointStore` 三表(runs/run_events/run_checkpoints)已就绪,API `GET /work/runs` 已实现
- 前端缺"历史 run 列表 + 时间轴回放"组件
- **建议**: 新增 `RunHistoryDrawer.tsx`,调用 `GET /work/runs` 渲染列表,点击进入事件时间轴

**应避免的过度设计**(对比 DeerFlow / Cursor):
- Docker-based isolated sandbox — 本地桌面定位不需要
- 远程 cloud workspace — 与本地优先定位不符
- 多 repo 支持 — 单 workspace 已覆盖 95% 场景
- Web dashboard — IDE 内嵌体验即可

**动作**: 实施三件套(load-bearing state 外化 + 多步进度可视化 + 跨 session run 历史回看)

---

### Spec 5: Reflection Loop + 神经符号 PDG — 核心真实,框架有夸大

**现状诊断**:

| 能力 | 状态 | 证据 |
|------|------|------|
| VMAO Reflexion | ✅ 真触发 | `loop.py:1148-1187` 连续 2 次失败触发,最多 3 轮 |
| CriticAgent(独立第三方) | ✅ 真触发 | `critic.py` + `work_pipeline.py:1378-1420`,仅 craft 模式 |
| SelfReflectEngine | ⚠️ 几乎不用 | `reflector.py` 真实现,但 selector 默认走 FastStrategy |
| MetaReflectionFlywheel | ✅ 真触发 | `flywheel/reflection.py` 每 5 次对话调整 KTG 权重 |
| ReflectionManager 6 评估器 | ❌ 未接入 | `reflection/manager.py` 已写好但 grep 不到生产调用 |
| KTG 4 层拓扑(神经符号) | ✅ 真实现 | `topology/` 真神经符号,替代向量召回 |
| PyO3 PDG | ❌ 占位包 | `rust_ext/__init__.py:3` 自承"留待 Spec 5" |
| 真 PDG(fnix-se) | ⚠️ sidecar 模式 | 在姊妹项目,sidecar 离线即降级 |

**七层 Intelligence 框架真实性**:

| 层 | 模块 | 真实状态 |
|---|------|---------|
| L0 ContinuousCollector | 14 个采集器 | ❌ 死代码,`integration.py` 不引用 |
| L1 LoopEngine | NudgeEngine | ✅ 真触发 |
| L2 GeneticEvolver | 遗传进化 | ❌ trivial_fitness 占位,`integration.py:300-301` 明示"仅验证管线连通" |
| L3 EvolutionGuard | 退化检测 | ✅ 真触发(但基线硬编码) |
| L4 SynthesisEngine | 综合引擎 | ❌ `integration.py` 完全未 import |
| L5 IntelligenceMemoryManager | 记忆层 | ✅ 真触发 |
| L6 SkillMarketplace | 技能市场 | ✅ 真触发(但与 HERA 职责重叠) |
| L7 SelfJudge | 自审判 | ⚠️ 真触发但分数硬编码(`self_judge.py:636-646`) |

**对比业界**:
- Reflexion 论文(NeurIPS 2023)三角色 Actor/Evaluator/Self-Reflection 已在 VMAO 落地
- Cursor / Claude Code 无独立 Critic,依赖模型自纠 — 项目 CriticAgent 是差异化能力
- CLAUSE 神经符号 KG 三代理(expander/navigator/critic)比项目 KTG 复杂一个量级,但项目 KTG 更可解释更便宜
- KG-Agent 走 LLM-as-controller 实时探索,项目走预先固定拓扑+权重传播,路线不同各有取舍

**真需求**(保留并加强):
1. VMAO Reflexion — 直接修复用户体感的工具失败循环
2. KTG 4 层拓扑 — 真实替代向量召回,有测试
3. MetaReflectionFlywheel — 真 trace 驱动的神经符号反馈
4. CriticAgent(craft 模式)— 真实盲点修复,但需补测试 + 修 fail-safe

**过度设计**(裁剪或降级):
1. **L0 ContinuousCollector** 14 个采集器 — 死代码,删除或明确为 AgentOS 子系统
2. **L2 GeneticEvolver** — trivial_fitness 永远跑不出有用结果,删除或改为真实 fitness_fn
3. **L4 SynthesisEngine** — `integration.py` 完全未 import,删除
4. **L7 SelfJudge 硬编码分数** — `judge_evolution_cycle` 用硬编码 0.8/0.6,审判结论基本预设,改为真实 LLM-as-Judge 或删除
5. **ReflectionManager 6 评估器** — 已写好但未接入,删除或接入主路径
6. **PyO3 PDG 占位包** — 自承认是占位,真 PDG 在姊妹项目,诚实降级为"sidecar 模式,非 Python 内嵌"

**CriticAgent fail-safe 漏洞**:
- `critic.py:280-286` JSON 解析全失败时返回 `passed=True, score=0.5` — 即"Critic 自己坏掉时假装通过"
- 违背"独立第三方审查"承诺
- **建议**: 解析失败应返回 `passed=False` 或显式 `error` 字段

**动作**:
1. 裁剪 L0/L2/L4(删除死代码)
2. 修复 CriticAgent fail-safe + 补测试
3. L7 改为真实 LLM-as-Judge 或诚实降级
4. ReflectionManager 要么接入要么删除
5. PyO3 PDG 文档诚实降级

---

### Spec 6: 多任务并行可视化 — 真实运行,与主 Composer 解耦

**现状诊断**:

| 能力 | 状态 | 证据 |
|------|------|------|
| work_jobs worker_loop | ✅ 真实运行 | `work_jobs.py:332` Semaphore + `:357` create_task,`main.py:217-220` lifespan 启动 |
| PriorityTaskQueue | ✅ 真实 | `core/scheduler/priority_queue.py:100` |
| BYOK 友好背压 | ✅ 合理 | 默认 2 并发,上限 16,`FNIX_MAX_CONCURRENT_JOBS` 可调 |
| JobsPanel + TaskCard | ✅ 真实工作 | `useJobsStore.ts:55-56` 自动轮询 1.2s/10s |
| /api/v1/work/jobs 完整 API | ✅ 齐全 | enqueue/list/cancel/stats/active/events |
| 主 Composer 接入 jobs | ❌ 解耦 | `useJobsStore.enqueue` 存在但主聊天流不调用,主 Composer 走同步 `/work/stream` |
| git worktree 隔离 | ❌ 缺失 | 无 worktree,并发任务共享 workspace 有冲突风险 |
| worker_loop 并行测试 | ❌ 盲区 | `test_work_jobs_enqueue.py` 只测入队,不测并行/Semaphore/cancel |

**两个 AgentScheduler 命名冲突**:
- `core/agent/scheduler.py`(401 行 OS 风格 CFS 调度器)— 服务 AgentKernel 路径,主路径不走
- `core/orchestrator/scheduler.py`(legacy 单请求编排器)— 与 work_pipeline 功能重叠,`main.py:120` 自承 legacy
- 同名同姓增加认知负担

**对比业界**:
- Cursor /multitask(2026-04):拆分单一请求为子代理 + worktree 隔离
- Cursor Worktrees:每个任务独立 git 分支
- Claude Code:git worktree 隔离并行 agent
- **Aider(重要参照)**:明确不做 subagents/并行,一次一个对话,40K+ stars 验证了单线程可靠性路线

**对本地优先工具的评估**:
- 办公场景(写周报/PPT/转 PDF):并行价值低,用户通常一次一个任务
- 编码场景(多模块并行):并行价值高,但需 worktree 隔离
- BYOK 限制:免费档位 RPM 有限,4 并发 × 9 步会触发 429,默认 2 并发是合理自然背压

**Cursor /multitask 不适合直接照搬**:
- 模型不匹配(Fnix 是队列模式不是子代理拆分)
- 隔离缺失(无 worktree)
- 场景错位(Fnix 主场景是办公不是多模块代码并行)

**真需求**:
1. 主 Composer 与 jobs 队列接入 — 用户应能从主聊天"发送到后台"或"中途转后台"
2. worker_loop 并行行为测试覆盖 — 当前是测试盲区
3. (可选)git worktree 隔离 — 若要进入编码并行场景

**过度设计**:
1. `core/agent/scheduler.py` OS 风格调度器 — 服务 AgentOS,与 Work 解耦,主路径不走,认知负担
2. `core/orchestrator/scheduler.py` legacy 编排器 — 与 work_pipeline 重叠
3. 两个 AgentScheduler 同名冲突

**动作**:
1. 在主 Composer 加"发送到后台"入口(最小改动)
2. 补 worker_loop 并行测试
3. 重命名两个 AgentScheduler 消除冲突(或删除 legacy)
4. worktree 隔离标记为 P2(看产品是否要进入编码并行)

---

### Spec 7: 四维闭环真触发 — DAAO/VMAO/HERA 真实,缺用户反馈信号

**现状诊断**:

| 维度 | 状态 | 触发点 |
|------|------|--------|
| DAAO | ✅ 真路由 | `daao_router.py:99-194` 难度评估 + 真反馈回路(HERA 命中率 → max_reflect_rounds) |
| VMAO | ✅ 真触发 | `loop.py:1139-1226` Reflexion + CriticAgent |
| HERA | ✅ 真捕获+真召回 | `library.py:78-228` Jaccard + workspace_kind 加分 + 时间衰减 |
| Self-Optimizing | ✅ 真沉淀+真注入 | `self_optimizing.py:118-307` DSPy BootstrapFewShot 精简版 |

**真实闭环**: HERA 命中率 → DAAO 路由 → VMAO 反思 → HERA 失败技能沉淀 → Self-Optimizing few-shot 注入

**核心短板**:

**短板 1: 缺用户反馈信号回路** — 核心差距
- HERA 只基于任务自动 success/failure 捕获,没有"用户对 Agent 回复的 reaction/reply"输入通道
- Cursor Bugbot Learning(2026-04)的核心创新正是把"开发者是否 acted on Bugbot's report"作为训练信号:50K PRs,resolution rate 78.13%(行业第一)
- FnixAgent 完全没有这一层
- **建议**: 在前端消息流加轻量反馈(👍/👎/回复),反馈信号写入 HERA 影响 skill 评分

**短板 2: DAAO tool_subset 空壳**
- `daao_router.py:123,129,135,142,149,155,161` 所有分支 tool_subset 都是空 list
- 宣称的"工具子集筛选"是空壳
- **建议**: 要么实现真实工具子集筛选,要么从文档诚实降级

**短板 3: HERA 失败技能捕获不完整**
- `library.py:131` `add_new_skill` 在 `success=False` 时直接返回 None
- 失败技能几乎不入库,导致 `compute_recent_failure_rate` 长期接近 0,DAAO 反馈回路实际失效
- 只有 VMAO reflection 路径在 `work_pipeline.py:1167-1173` 写入失败技能才部分补救
- **建议**: 修复 add_new_skill 允许失败技能入库(标记 success=False)

**短板 4: Self-Optimizing 与 HERA 重叠**
- 两套存储/两套召回/两套去重,实际收益边际递减
- prompt 注入时(`work_pipeline.py:837 + 965`)HERA block + Self-Optimizing block 都追加,导致 prompt 膨胀
- **建议**: 合并为"HERA + 完整 trace 字段"

**测试盲区**:
- 无 `test_self_optimizing.py`
- 无 `test_daao_router.py`
- 无 `test_hera_skill_library.py`
- 无 `test_vmao_reflexion.py`
- 无 `test_critic_agent.py`

**对比 Anthropic Effective Harnesses**:
- Anthropic 用 initializer + coding agent 分工 + `feature_list.json`(200+ features)+ git 进度追踪 + Puppeteer 端到端测试
- FnixAgent 有 checkpoint/resume 基础设施,但缺 feature_list 级进度追踪
- **建议**: 对齐 Anthropic 加 feature_list.json + git 进度追踪(P2,看是否要进入 8h+ 任务场景)

**动作**:
1. 加用户反馈信号回路(👍/👎/回复 → HERA 评分) — P0
2. 修复 HERA 失败技能捕获 — P0
3. 合并 Self-Optimizing 与 HERA — P1
4. 补全 DAAO/VMAO/HERA/Self-Optimizing/CriticAgent 单元测试 — P0
5. DAAO tool_subset 要么实现要么诚实降级 — P1
6. feature_list + git 进度追踪(对标 Anthropic) — P2

---

## 三、真需求 vs 过度设计 汇总

### 真需求(应实施)

| # | 需求 | Spec | 优先级 | 理由 |
|---|------|------|--------|------|
| R1 | load-bearing state 外化(.fnix/todos.json) | Spec 4 | P0 | compaction summary 有损是已知痛点,长程任务累积丢失关键决策 |
| R2 | 多步进度可视化(StepProgressStrip) | Spec 4 | P0 | 长程任务用户最焦虑"进行到哪一步了" |
| R3 | 跨 session run 历史回看(RunHistoryDrawer) | Spec 4 | P0 | 后端已就绪,前端缺组件 |
| R4 | 用户反馈信号回路(👍/👎/回复 → HERA) | Spec 7 | P0 | 对标 Cursor Bugbot,核心差距 |
| R5 | 修复 HERA 失败技能捕获 | Spec 7 | P0 | DAAO 反馈回路实际失效 |
| R6 | 修复 CriticAgent fail-safe 漏洞 | Spec 5 | P0 | "Critic 自己坏掉时假装通过"违背承诺 |
| R7 | 主 Composer 与 jobs 队列接入 | Spec 6 | P1 | useJobsStore.enqueue 存在但未被 UI 调用 |
| R8 | 合并 Self-Optimizing 与 HERA | Spec 7 | P1 | 消除重叠,减少 prompt 膨胀 |
| R9 | 裁剪 L0/L2/L4 死代码 | Spec 5 | P1 | 降低维护成本和认知负担 |
| R10 | 补全 5 处测试盲区 | Spec 5/7 | P0 | 保障生产可靠性 |
| R11 | 重命名/删除两个 AgentScheduler | Spec 6 | P1 | 消除同名冲突 |
| R12 | L7 SelfJudge 改为真实 LLM-as-Judge 或降级 | Spec 5 | P2 | 当前硬编码分数无意义 |
| R13 | ReflectionManager 接入或删除 | Spec 5 | P2 | 已写好但未接入 |
| R14 | DAAO tool_subset 实现或降级 | Spec 7 | P2 | 当前空壳 |
| R15 | git worktree 隔离 | Spec 6 | P2 | 编码并行场景前提 |
| R16 | feature_list + git 进度追踪 | Spec 7 | P2 | 对标 Anthropic 8h+ 任务 |

### 过度设计(应裁剪或诚实降级)

| # | 项目 | 处理方式 |
|---|------|---------|
| O1 | L0 ContinuousCollector 14 个采集器 | 删除(死代码) |
| O2 | L2 GeneticEvolver | 删除(trivial_fitness 占位) |
| O3 | L4 SynthesisEngine | 删除(integration.py 未 import) |
| O4 | PyO3 PDG 占位包 | 文档诚实降级为"sidecar 模式" |
| O5 | `core/agent/scheduler.py` OS 风格调度器 | 明确为 AgentOS 子系统,与 Work 解耦 |
| O6 | `core/orchestrator/scheduler.py` legacy 编排器 | 删除(与 work_pipeline 重叠) |
| O7 | 极简新中式宋韵风 | 不做(审美偏好非效率需求) |
| O8 | Docker sandbox | 不做(本地桌面定位) |
| O9 | 远程 cloud workspace | 不做(与本地优先不符) |
| O10 | Web dashboard | 不做(IDE 内嵌即可) |
| O11 | 多 repo 支持 | 不做(单 workspace 已覆盖 95%) |

---

## 四、推荐实施路线

### 阶段一:P0 核心补全(真需求 + 测试)

**目标**: 补齐影响用户体验的核心差距 + 保障生产可靠性

**任务清单**:
- R1 load-bearing state 外化(.fnix/todos.json + compaction 后重新注入)
- R2 多步进度可视化(StepProgressStrip.tsx 消费 step_start/step_end)
- R3 跨 session run 历史回看(RunHistoryDrawer.tsx 调用 GET /work/runs)
- R4 用户反馈信号回路(前端 👍/👎/回复 + 后端写入 HERA 评分)
- R5 修复 HERA 失败技能捕获(add_new_skill 允许 success=False)
- R6 修复 CriticAgent fail-safe(解析失败返回 passed=False 或 error 字段)
- R10 补全 5 处测试盲区(test_critic_agent / test_daao_router / test_hera_skill_library / test_vmao_reflexion / test_self_optimizing)

**验证**: 每项任务完成后跑对应单测 + 集成测试

### 阶段二:P1 收敛与裁剪

**目标**: 消除重叠和死代码,降低维护成本

**任务清单**:
- R7 主 Composer 与 jobs 队列接入(Composer 加"发送到后台"按钮)
- R8 合并 Self-Optimizing 与 HERA(统一存储和召回)
- R9 裁剪 L0/L2/L4 死代码 + O4 PyO3 PDG 文档降级
- R11 重命名/删除两个 AgentScheduler

**验证**: 裁剪后跑全套测试确保无回归

### 阶段三:P2 增强(可选,看产品方向)

**目标**: 对齐业界顶级方案,进入更复杂场景

**任务清单**:
- R12 L7 SelfJudge 改为真实 LLM-as-Judge 或诚实降级
- R13 ReflectionManager 接入主路径或删除
- R14 DAAO tool_subset 实现真实工具子集筛选或文档降级
- R15 git worktree 隔离(若进入编码并行场景)
- R16 feature_list + git 进度追踪(若进入 8h+ 任务场景)

---

## 五、技术选型与实施架构

### R1 load-bearing state 外化

**技术选型**: JSON 文件 + system prompt 注入(对标 Claude Code TodoWrite)

**架构**:
- 后端: `core/agent/todos.py` 新增 `TodoStore`,在 `loop.py` turn 边界写入 `.fnix/todos.json`
- compaction 后: `compaction.py` 的 `preserve_details` 提示词追加 "reload .fnix/todos.json"
- 前端: `GoalProgressRow` 可选展示 todos 进度

### R2 多步进度可视化

**技术选型**: 消费已有 step_start/step_end 事件,新增 React 组件

**架构**:
- 前端: `StepProgressStrip.tsx` 新组件,从 `useChatFlow` 的 activities 提取 step 事件
- 渲染: `Step 3/10 · 思考中` + 进度条
- 集成: `ChatGptDesktopApp.tsx` 在消息流顶部或 GoalProgressRow 下方

### R3 跨 session run 历史回看

**技术选型**: 复用已有 GET /work/runs API + 新增 React 抽屉组件

**架构**:
- 前端: `RunHistoryDrawer.tsx` 新组件
- 数据: `fnixRuntime.ts` 新增 `listRuns()` / `getRunEvents(runId)` 封装
- 集成: `ChatGptDesktopApp.tsx` 左栏底部或顶部加"历史"入口

### R4 用户反馈信号回路

**技术选型**: 轻量前端反馈组件 + HERA 评分加权

**架构**:
- 前端: `MessageBubble.tsx` 消息底部加 👍/👎/回复按钮(悬停显示)
- 后端: `api/routers/work.py` 新增 `POST /work/feedback` 端点
- HERA: `library.py` `add_new_skill` 新增 `user_feedback` 字段,召回时 `score = base * (1 + 0.3 * positive - 0.5 * negative)`

### R5 修复 HERA 失败技能捕获

**技术选型**: 最小改动

**架构**:
- `library.py:131` 移除 `if not success: return None`
- 失败技能标记 `success=False` 入库,7 天去重仍适用
- `compute_recent_failure_rate` 现在能拿到真实失败率

### R6 修复 CriticAgent fail-safe

**技术选型**: 最小改动

**架构**:
- `critic.py:280-286` 解析失败时返回 `passed=False, score=0.0, error="parse_failed"`
- 调用方 `work_pipeline.py:1378-1420` 检查 `verdict.error` 字段,有 error 时降级为"跳过 Critic"而非"假装通过"

### R10 测试盲区补全

**技术选型**: pytest + 纯本地逻辑(无 LLM/网络依赖)

**架构**:
- `tests/unit/test_critic_agent.py` — mock LLM 返回,验证 verdict 解析 + fail-safe
- `tests/unit/test_daao_router.py` — 验证难度评估 + 路由决策 + 反馈回路
- `tests/unit/test_hera_skill_library.py` — 验证 add/retrieve/去重/时间衰减 + 失败技能
- `tests/unit/test_vmao_reflexion.py` — 验证连续失败触发 + max_rounds 限制
- `tests/unit/test_self_optimizing.py` — 验证 extract_examples/retrieve/score

---

## 六、风险与依赖

**风险**:
1. R9 裁剪 L0/L2/L4 可能影响 `intelligence/__init__.py` 的导出契约 — 需先 grep 确认无外部依赖
2. R8 合并 Self-Optimizing 与 HERA 可能破坏 prompt 注入格式 — 需逐步迁移
3. R4 用户反馈信号回路需要前端 UI 改动 — 需确保不破坏现有消息流布局

**依赖**:
- 无外部依赖(所有任务都在现有技术栈内)
- 无新依赖引入(遵循 project_memory "前端组件应避免添加新依赖")

---

## 七、验证策略

**单测**: 每个 R 任务完成后跑对应单测
**集成**: P0 完成后跑 `tests/integration/` 全套
**E2E**: P0 完成后跑 `scripts/e2e-work-modes.py` + `scripts/e2e-work-golden.py`
**前端**: P0 完成后跑 `apps/workbench` 的 `pnpm test` + `pnpm typecheck`
**最终**: 所有完成后跑 `pytest -q` + `pnpm test` + `pnpm typecheck` 全套验证

---

## 八、与设计文档的对齐说明

本评估发现 2026-07-20/21 两份设计文档存在以下与实际代码不符的描述:

| 文档描述 | 实际情况 |
|---------|---------|
| StreamdownRenderer.tsx | 实际是 MarkdownRenderer.tsx(功能完整) |
| ExecutionStory.tsx | 实际是 ProcessTimeline.tsx + structuredBlocks.ts |
| RightPanel.tsx 三模式 | Work/Code 是左栏模式切换,Review 是 Code 模式右栏 tab |
| 16 个内置 Skill | 后端实际 35 个,前端动态拉取 |
| fnix-se/crates/fnix-evolution | 该目录在当前代码库不存在 |

**建议**: 后续设计文档应以实际代码为基准,避免文件名/结构的不准确描述。本评估文档已基于实际代码审计,所有文件路径和行号均为真实证据。
