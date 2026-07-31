# 自进化 AI Agent 与知识图谱最新进展(2024–2026)

> 报告日期:2026-08-01
> 目的:为 FnixAgent 的 KTG / MFP / DAAO 三大机制做最新研究对标,识别被超越点与升级路径
> 验证原则:所有数据点均给出 arXiv 编号或官方 URL,优先 2025–2026 资料;FnixAgent 内部数据来自 `paper/main.tex` 与代码库实测

---

## (a) 自进化 Agent 研究全景:与 FnixAgent MFP 四阶段的关系

FnixAgent 的 MFP(Meta-Flow Pipeline / 四阶段飞轮)= ①感知执行(perceive)→ ②知识固化(solidify)→ ③元反思(meta-reflect)→ ④爬山进化(hill-climb),每 100 轮对话触发一次,直接改写 KTG 节点/边权重,并在第④阶段做快照-回滚安全保护(代码:`src/fnixagent/core/flywheel/stage1_perception.py` … `stage4_climbing.py`)。

下表列出 2022–2026 自进化 Agent 核心工作,并标注其与 MFP 各阶段的**同构(机制对应)/竞争(功能重叠)/补强(可借鉴)**关系。

| # | 工作 | arXiv / 来源 | 年份 | 核心机制 | 进化载体 | 与 MFP 关系 |
|---|------|-------------|------|----------|----------|--------------|
| 1 | **Voyager** | [arXiv:2305.16291](https://arxiv.org/abs/2305.16291) | 2023 | GPT-4 + 自动课程 + 技能库(veral code)+ 迭代 prompt | 可复用技能代码库 | **补强①②**:技能库≈MFP②固化;但无元反思、无权重爬山 |
| 2 | **Reflexion** | [arXiv:2303.11366](https://arxiv.org/abs/2303.11366) | 2023(NeurIPS) | 语言反馈(verbal RL),失败后生成文字反思注入下轮 | 短期语言记忆 | **同构③**:单任务反思≈MFP③;但无持久图谱、无固化 |
| 3 | **Self-Refine** | [arXiv:2303.17651](https://arxiv.org/abs/2303.17651) | 2023(NeurIPS) | 自生成反馈→自修订,单轮迭代 | 无持久载体 | **同构③**:更轻量的反思;完全无进化闭环 |
| 4 | **ExpeL** | [arXiv:2308.10144](https://arxiv.org/abs/2308.10144) | 2024(AAAI) | 经验轨迹→抽取 insights→跨任务复用 | insight 库(文字) | **同构②③**:经验固化≈MFP②;但 insight 是非结构化文本,无可查询图结构 |
| 5 | **AgentTuning** | [arXiv:2310.12823](https://arxiv.org/abs/2310.12823) | 2023 | 用 agent 轨迹微调开源 LLM(参数级进化) | 模型参数 | **竞争②**:把进化写进权重 vs MFP 写进图;两者正交,FnixAgent 选了零参数微调路线 |
| 6 | **EvolveR** | [arXiv:2510.16079](https://arxiv.org/abs/2510.16079) | 2025(ICML 2026) | 离线自蒸馏(轨迹→抽象策略原则)+ 在线交互(检索原则决策)+ 策略强化;多跳 QA SOTA | 策略原则库 + 策略参数 | **同构②③+竞争④**:两阶段闭环≈MFP②③;策略强化≈MFP④爬山;但 EvolveR 用 RL 更新策略而非图权重,**在多跳 QA 上已被验证超越强基线** |
| 7 | **Sleep-time Compute** | [arXiv:2504.13171](https://arxiv.org/abs/2504.13171)(Letta/UC Berkeley) | 2025 | 离线"睡眠期"预计算:预测用户可能问什么、预算有用量,测试时计算↓~5×,精度↑13–18%;多查询摊销成本↓2.5× | 离线预计算缓存 | **补强①④**:与 MFP④离线爬山同属"离线消化";但 Sleep-time 聚焦"预查询",MFP 聚焦"权重调整"——**两者可叠加,FnixAgent 当前缺失 Sleep-time 维度** |
| 8 | **Constitutional AI** | [arXiv:2212.08073](https://arxiv.org/abs/2212.08073)(Anthropic) | 2022 | 自批判 + 自修订(constitution 规则)→ RLAIF | 规则集 + 模型参数 | **同构③**:规则驱动反思≈MFP③元反思;补强:FnixAgent 第③阶段 CriticAgent 尚未硬化,可借 CAI 的 constitution 形式 |
| 9 | **Generative Agents** | [arXiv:2304.03442](https://arxiv.org/abs/2304.03442)(Stanford,UIST 2023) | 2023 | 25 个 agent + 记忆流 + 反思 + 计划;记忆按重要性/时近/相关性打分检索 | 记忆流(向量+评分) | **同构②③**:记忆流重要性评分≈MFP 权重;但无图结构、无爬山 |

### 关键判断

1. **MFP 的独特点**:是目前少数把"进化结果"写进**可查询的固定结构图权重**(而非参数/纯文本)的工作,且第④阶段有快照-回滚安全网(论文 Algorithm 1)。这是 Reflexion/Self-Refine/ExpeL 都没有的。
2. **MFP 的被超越点**:
   - **EvolveR(arXiv:2510.16079)**:用 RL 做策略强化,在多跳 QA 上证明比强 agentic 基线更优;MFP 的爬山只是启发式 +0.1/-0.05 调权,无策略学习。
   - **Sleep-time Compute(arXiv:2504.13171)**:量化了"离线消化"的收益(5× 测试时计算降低),MFP 虽然也是离线触发,但**从未量化离线计算的投资回报比**,也没有"预查询"机制。
3. **MFP 待补强**:第③阶段 CriticAgent 在论文 Conclusion 中被承认"尚未硬化";Constitutional AI 的 constitution 规则形式可直接借鉴。

---

## (b) 知识图谱 + LLM 工程实践对比表

| 框架 | arXiv / 来源 | 构建方式 | 查询方式 | 是否自进化 | 是否本地 | 关键性能数据 | 与 KTG 差异 |
|------|-------------|----------|----------|-----------|----------|--------------|-------------|
| **GraphRAG** | [arXiv:2404.16130](https://arxiv.org/abs/2404.16130)(Microsoft,2024) | 动态 LLM 抽取实体/关系→社区检测→层级摘要 | 社区级全局摘要 + 局部向量 | 否(重建即重抽) | 可本地 | 全局问答质量优于向量 RAG;但索引成本极高(全量 LLM 调用) | KTG 固定 schema,GraphRAG 无界动态结构,稳定性差 |
| **HippoRAG** | [arXiv:2405.14831](https://arxiv.org/abs/2405.14831)(NeurIPS 2024,OSU) | 动态 LLM 抽取实体→KG + Personalized PageRank | 单步图检索(PPR 传播) | 否 | 可本地 | 多跳 QA 超越 SOTA **达 20%**;比 IRCoT 便宜 **10–30×**、快 **6–13×** | KTG 用权重乘积路径搜索,HippoRAG 用 PPR;HippoRAG 无 MUTEX 惩罚 |
| **LightRAG** | [arXiv:2410.05779](https://arxiv.org/abs/2410.05779)(HKU,2024) | 动态 LLM 抽取→双层级(低层实体/高层主题)图 + 向量 | 双层级检索 + 增量更新 | 部分(增量更新) | 可本地 | 检索精度与效率显著优于 GraphRAG;增量更新避免全量重建 | KTG 四层固定层级 vs LightRAG 双层级动态;KTG 无增量 LLM 抽取 |
| **HCG-RAG** | FnixAgent 论文 cite hcg2026 | **固定 schema 因果图** | 子图检索 | **否** | 可本地 | 论文未公开 benchmark | **最接近 KTG 的工作**:同为固定 schema,但无权重路径搜索、无自进化 |
| **KG-RAG** | [arXiv:2405.12035](https://arxiv.org/abs/2405.12035)(2024) | 固定外部 KG(UMLS/生物医学)+ 推理路径 | 路径推理 + 向量 | 否 | 可本地 | 生物医学 QA 准确率提升 | KTG 面向通用任务,KG-RAG 面向领域 KG |
| **ToG(Think-on-Graph)** | [arXiv:2307.07697](https://arxiv.org/abs/2307.07697)(ICLR 2024) | 固定外部 KG(Wikidata)+ 束搜索 | 探索-推理交替(LLM 引导束搜索) | 否 | 可本地 | 深度推理与可解释性优于直接 LLM | KTG 用权重驱动确定性路径,ToG 用 LLM 引导束搜索(每步耗 LLM) |
| **RoG(Reasoning on Graphs)** | [arXiv:2310.01045](https://arxiv.org/abs/2310.01045)(ICLR 2024) | 固定 KG + 规则路径模板 | 微调模型生成推理路径 | 否 | 可本地 | 知识图谱推理基准 SOTA | KTG 零微调,RoG 需微调 LLM |
| **KAG** | [arXiv:2409.13731](https://arxiv.org/abs/2409.13731)(蚂蚁+浙大,2024) | **LLM 友好知识表示 + 互索引 + 逻辑形式引导混合推理引擎** | 混合(向量 + KGQA + 规则引擎) | 部分 | 可本地 | **2wiki F1 相对 +19.6%、HotpotQA F1 相对 +33.5%**;已在蚂蚁政务/医疗落地 | **KAG 的 KG-DSL 逻辑规则引擎比 KTG 固定 schema 更先进**(详见 (e)) |
| **Cognee** | [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee) | 动态 LLM 抽取→图结构记忆 | 图 + 向量混合 | 部分 | 可本地 | 开源,适合知识密集型 agent | KTG 固定四层,Cognee 无界图;Cognee 更灵活但结构不稳定 |

### 关键判断

- **构建方式分两派**:动态 LLM 抽取(GraphRAG/HippoRAG/LightRAG/Cognee)灵活但成本高、结构不稳定;固定 schema(HCG-RAG/KTG/KAG 的 SPG)稳定但表达力受限。FnixAgent KTG 属固定派。
- **KAG 是最直接的竞争者**:同样做"KG + LLM 双向增强",但 KAG 的**逻辑形式引导混合推理引擎(logical-form-guided hybrid reasoning)**和 **KG-DSL 规则**在 HotpotQA 上拿到 +33.5% F1,这是 KTG 在公开 benchmark 上**从未报告**的成绩。
- **KTG 的 MUTEX 惩罚**:在上述所有框架中**未发现等效机制**——MUTEX 边以惩罚权重抑制互斥概念同路径检索,这一点确为 KTG 独有,但**缺乏公开 benchmark 证明其有效性**。

---

## (c) AI Agent 记忆系统对比

记忆基准说明:**LongMemEval**([arXiv:2410.10813](https://arxiv.org/abs/2410.10813),ICLR 2025)500 题,测 5 项长期记忆能力(信息抽取/多会话推理/时序推理/知识更新/弃答),商业 chat assistant 与长上下文 LLM 在持续交互上准确率下降 **~30%**。**LoCoMo** 是另一常用对话记忆基准。

| 系统 | 来源 / arXiv | 记忆分层 | 时序性 | 本地能力 | 关键性能数据 | 与 FnixAgent 记忆对比 |
|------|-------------|----------|--------|----------|--------------|----------------------|
| **MemGPT / Letta** | [arXiv:2310.08560](https://arxiv.org/abs/2310.08560)(2023);20k+★ | OS 式分层(main context / archival / recall) | 弱(无显式时间边) | 可本地(开源) | LongMemEval-S R@5 ≈ **83.2%**(AgentMemory 论文报告) | FnixAgent 用 KTG 替代 MemGPT 的 archival,结构更稳定 |
| **Mem0** | [arXiv:2509.24824](https://arxiv.org/abs/2509.24824);60k+★ | 通用 agent 记忆(向量化 fact) | 弱 | 可本地(开源)+ 托管 | LongMemEval-S R@5 ≈ **68.5%**(AgentMemory 论文报告) | Mem0 无图结构,FnixAgent KTG 多跳更强 |
| **Zep / Graphiti** | "Zep: A Temporal Knowledge Graph Architecture for Agent Memory";28k+★(Graphiti) | **时序知识图谱(TKG)**:边带 temporal validity | **强(原生时序)** | 可本地(开源)+ 托管 | LongMemEval 准确率提升;DMR benchmark 94.8% vs MemGPT 93.4% | **FnixAgent KTG 无时序边——这是关键短板(详见 (f) 建议 5)** |
| **Cognee** | [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee);14k+★ | 知识图谱驱动结构化记忆 | 弱 | 可本地(开源) | 适合多跳推理 | 与 KTG 定位最接近,但 Cognee 动态图、KTG 固定图 |
| **Supermemory** | 官方(supermemory.ai);获投 **260 万美元** | 处理非结构化数据→KG→个性化上下文 | 弱 | 托管为主 | 通用记忆 API | 商业产品,非自进化 |
| **MemClaw** | 2025;19 岁开发者 | 图结构记忆 | 中 | 开源 | **LoCoMo / LongMemEval / EvolvingEvents 三榜全部第一**,超 Mem0/Zep/Graphiti/Cognee/Supermemory | 新晋 SOTA,FnixAgent 记忆尚未在 LongMemEval 报分 |
| **AgentMemory** | [arXiv:2509.xxxxx](https://arxiv.org)(ICLR 2025 周边) | 文件 + 向量混合 | 中 | 可本地 | LongMemEval-S R@5 = **95.2%**(Mem0 68.5%,Letta 83.2%) | 检索质量最高,说明"文件系统+索引"路线被低估 |

### 关键判断

1. **FnixAgent 记忆系统从未在 LongMemEval/LoCoMo 上报分**——这是最大的可信度缺口。同类工作几乎都跑这两个基准。
2. **时序性是行业共识方向**:Zep/Graphiti 用时序知识图谱(TKG,边带 temporal validity)解决"知识过时/事实更新"问题;FnixAgent KTG 仅有 freshness × 0.999 衰减和 30 天未用降权,**无显式时间边,无法处理"X 在 2024 是 A,2025 改为 B"这类时序推理**。
3. **MemClaw 与 AgentMemory 的崛起**:2025–2026 记忆 SOTA 已被新工作占据,FnixAgent 若不跑公开基准,无法证明 KTG 在记忆维度有竞争力。

---

## (d) LLM 路由最新方法:与 FnixAgent DAAO 零 LLM 路由对比

| 方法 | arXiv / 来源 | 路由机制 | 是否调用 LLM | 多轮 | 关键性能 | 与 DAAO 对比 |
|------|-------------|----------|-------------|------|----------|--------------|
| **RouteLLM** | [arXiv:2406.18665](https://arxiv.org/abs/2406.18665)(LMSYS/UCB,2024) | 用偏好数据训练 router(强/弱模型二选一) | 否(轻量分类器) | 否 | 成本降低 **>2×** 且不损质量;强模型可替换(迁移能力) | DAAO 同样零 LLM,但 RouteLLM 是**学习型** router,DAAO 是**纯启发式**;RouteLLM 有公开 benchmark,DAAO 仅 FCS |
| **FrugalGPT** | [arXiv:2305.05176](https://arxiv.org/abs/2305.05176)(2023) | 级联(cascade):便宜模型先答,不够再升级 | 是(每级 LLM) | 否 | 成本降 ~80%,质量持平 | DAAO 一次决策无级联;FrugalGPT 适合 API 成本优化 |
| **Router-R1** | [arXiv:2506.09033](https://arxiv.org/abs/2506.09033)(UIUC,NeurIPS 2025) | **多轮路由 + 聚合**:RL 训练,序列决策,每步选内部推理/外部模型/聚合 | 是 | **是(多轮)** | 首个多轮 LLM router;LLMRouterBench 上 10 baseline 对比 | **DAAO 单次决策 vs Router-R1 多轮序列决策**;Router-R1 在复杂任务上更优 |
| **Hybrid LLM** | [arXiv:2402.02323](https://arxiv.org/abs/2402.02323)(2024) | 路由冻结 LLM(不需要再训练 LLM) | 否(路由器) | 否 | 在保持质量下成本优化 | 与 DAAO 定位类似(零 LLM 路由),但 Hybrid LLM 有学习组件 |
| **LLMRouterBench** | 2025 综述 | 横评 10 个 baseline(RouteLLM/FrugalGPT/HybridLLM/RouterDC/EmbedLLM/GraphRouter/Avengers/OpenRouter 等) | — | — | ~1000 GPU 小时统一评测,部分方法效果尴尬 | DAAO 未纳入该横评 |

### DAAO 独特性评估

**DAAO(arXiv:无,FnixAgent 自研)**核心:零 LLM 调用,从 work mode / workspace kind / keywords / HERA 信号(skill hit rate + recent failure rate)估算难度,选推理模式/步预算/反思轮数。代码:`src/fnixagent/core/flywheel/daao_router.py`。

- **零 LLM 调用是否真的独特?**:**部分独特**。RouteLLM/Hybrid LLM 也声称不调用大模型做路由(用轻量分类器),但它们需要**训练**分类器;DAAO 是**纯规则启发式,零训练零 LLM**,在 BYOK 本地优先约束下确实更省。但代价是**无学习能力**,无法像 RouteLLM 那样随数据变好。
- **HERA 闭环是否真的无人做?**:**基本独特但有近似**。HERA 把 skill hit rate 和 recent failure rate 反馈回路由决策,形成闭环;Router-R1 用 RL 信号闭环但**用了 LLM**;RouteLLM 无闭环。**"零 LLM + 运行时反馈闭环"这一组合,在已检索工作中未发现完全等效者**,但 LLMRouterBench 横评中部分 baseline(如 GraphRouter)已有图结构反馈,差异在"是否调用 LLM"。
- **诚实结论**:DAAO 的"零 LLM"在**本地 BYOK 场景**下是合理的差异化,但在**质量上无法证明超越学习型 router**——DAAO 仅在自建 FCS benchmark 上验证,从未在 LLMRouterBench 等公开基准上报分。

---

## (e) FnixAgent 的 KTG/MFP/DAAO 在最新研究中的定位

### e.1 KTG vs KAG / HCG-RAG / GraphRAG

| 维度 | KTG | KAG | HCG-RAG | GraphRAG |
|------|-----|-----|---------|----------|
| Schema | **固定四层**(Goal→Concept→Rule→Fact),6 节点/6 边类型 | LLM 友好表示 + SPG schema(可扩展) | 固定因果图 | 无界动态 |
| 路径搜索 | **权重乘积 × 节点置信度求和**,MUTEX 惩罚 | **逻辑形式引导混合推理引擎 + KG-DSL 规则** | 子图检索 | 社区摘要 |
| 自进化 | **是(MFP 直接改权重)** | 部分(互索引更新) | 否 | 否 |
| 公开 benchmark | **无(仅 FCS 自建)** | **2wiki +19.6%、HotpotQA +33.5%** | 无 | 有 |
| 本地 | 是 | 是 | 是 | 是 |

**诚实判断**:
- **KAG 的 KG-DSL 规则引擎比 KTG 固定 schema 更先进**:KAG 用逻辑形式(logical form)引导推理,可表达数值/时序/专家规则;KTG 的四层 schema 是**结构固定、表达力受限**的,无法原生表达"若 X 且非 Y 则 Z"这类逻辑规则——只能靠 MUTEX 惩罚间接处理互斥。**在 HotpotQA 这类多跳推理上,KAG 已用 +33.5% F1 证明优势,KTG 无对标数据**。
- **KTG 的 MUTEX 惩罚确为独有**:在已检索框架中未发现等效的"互斥边惩罚"机制。但**独创 ≠ 有效**:MUTEX 的收益从未在公开 benchmark 上被量化。
- **KTG 的权重驱动路径搜索是差异化点**:HippoRAG 用 PPR,ToG 用 LLM 束搜索,KTG 用确定性权重乘积——**零 LLM、亚毫秒**(论文 90 天实测),这是本地 BYOK 场景的真实优势。

### e.2 MFP vs EvolveR / Sleep-time Compute / ExpeL

| 维度 | MFP | EvolveR | Sleep-time Compute | ExpeL |
|------|-----|---------|--------------------|-------|
| 进化载体 | **KTG 图权重** | 策略原则库 + 策略参数 | 离线预计算缓存 | insight 文本库 |
| 闭环方式 | 4 阶段:感知→固化→反思→爬山 | 2 阶段:离线蒸馏→在线交互+RL | 睡眠期预查询 | 经验→insight→复用 |
| 安全机制 | **快照-回滚(Algorithm 1)** | 无 | 无 | 无 |
| 离线量化 | 未量化 | 多跳 QA SOTA | **测试时计算↓5×、精度↑13–18%、成本↓2.5×** | 有 |
| 公开 benchmark | 仅 FCS | **多跳 QA 超越强基线** | Stateful GSM/AIME | 多任务 |

**诚实判断**:
- **创新点**:MFP 把进化写进可查询图权重 + 快照回滚安全网,这是 EvolveR/Sleep-time/ExpeL 都没有的。ExpeL 的 insight 是非结构化文本,EvolveR 的策略是参数,Sleep-time 是缓存——**KTG 权重是唯一可被检索系统直接消费的进化产物**。
- **被超越点**:
  - **EvolveR(arXiv:2510.16079,ICML 2026)**:用 RL 做策略强化,在多跳 QA 上证明超越强 agentic 基线;MFP 的爬山只是 ±0.1/0.05 启发式调权,**无策略学习,无 RL**。**在多跳 QA 这个公开维度上,EvolveR 已超越 MFP**。
  - **Sleep-time Compute(arXiv:2504.13171)**:量化了离线计算的投资回报(5× 测试时计算降低);MFP 虽然也是离线触发,但**从未量化离线消化带来的测试时收益**,也没"预查询"机制。
- **需补强点**:第③阶段 CriticAgent 未硬化(论文 Conclusion 承认);无 RL;无公开多跳 QA benchmark。

### e.3 DAAO vs 路由方法

- **零 LLM 调用是否真的独特**:**在本地 BYOK 场景下成立**。RouteLLM/Hybrid LLM 也零 LLM 但需训练分类器;DAAO 零训练零 LLM,适合无额外算力的本地环境。但**在质量上未证明超越学习型 router**(仅 FCS 自建基准)。
- **HERA 闭环是否真的无人做**:**"零 LLM + 运行时反馈闭环"组合基本独特**。Router-R1 有 RL 闭环但用 LLM;RouteLLM 无闭环;GraphRouter 有图反馈但非 hit-rate/failure-rate 信号。**但独创性不等于最优**——HERA 是简单启发式,无学习能力。

### e.4 总体定位结论(诚实版)

1. **KTG**:固定四层 schema + 权重路径搜索 + MUTEX 惩罚 = **结构稳定、零 LLM、亚毫秒**;但**表达力被 KAG 的 KG-DSL 规则引擎超越**,且**无公开 benchmark 背书**。
2. **MFP**:图权重进化 + 快照回滚 = **唯一可检索消费的进化产物**;但**策略学习被 EvolveR 超越,离线量化被 Sleep-time Compute 超越**。
3. **DAAO**:零 LLM + HERA 闭环 = **本地 BYOK 场景合理差异化**;但**无学习能力,无公开路由基准**。
4. **整体**:FnixAgent 三机制在"本地 BYOK + 零额外算力"这一**特定约束**下仍有差异化,但**一旦放开约束(允许训练/允许额外 LLM 调用),2025–2026 的 EvolveR/KAG/Router-R1 在各自维度均已超越**。护城河是"约束+组合",不是单点技术领先。

---

## (f) 8 条对 FnixAgent 核心能力的具体升级建议

每条给出:研究依据、改造点(代码路径)、预期效果、复杂度。

### 建议 1:跑公开多跳 QA benchmark(MuSiQue + HotpotQA)

- **研究依据**:KAG 在 HotpotQA 拿 +33.5% F1([arXiv:2409.13731](https://arxiv.org/abs/2409.13731));EvolveR 在多跳 QA 证明超越强基线([arXiv:2510.16079](https://arxiv.org/abs/2510.16079));MuSiQue([arXiv:2211.13357](https://arxiv.org/abs/2211.13357))、HotpotQA([arXiv:1809.09600](https://arxiv.org/abs/1809.09600))是标准基准。
- **改造点**:`src/fnixagent/core/code/benchmark/`(已有 8 模块)旁新增 `core/eval/open_benchmark/`,实现 MuSiQue/HotpotQA 适配器,把 KTG 检索结果喂给 LLM 生成答案,报 F1/EM。
- **预期效果**:补齐 KTG 在公开基准的空白;若 KTG 在 HotpotQA F1 能逼近 KAG,则证明固定 schema + 权重搜索的有效性;若差距大,则定位需补 KG-DSL。
- **复杂度**:中(数据集已公开,适配器+评测脚本约 2–3 人日)。

### 建议 2:引入 Sleep-time Compute 量化离线消化收益

- **研究依据**:Sleep-time Compute([arXiv:2504.13171](https://arxiv.org/abs/2504.13171))量化离线预计算使测试时计算↓5×、精度↑13–18%。
- **改造点**:`src/fnixagent/core/flywheel/stage4_climbing.py` 增加离线计算计时与收益统计;在 `services/work_pipeline.py` step 9 记录 MFP 触发前后的测试时 token 消耗对比,输出"离线消化投资回报比"指标到 `core/observability/metrics.py`。
- **预期效果**:用数据证明 MFP 每 100 轮离线消化带来的测试时延迟/成本降低;为论文增加与 Sleep-time Compute 的直接对标数据。
- **复杂度**:低( instrumentation 约 1–2 人日)。

### 建议 3:增加 KG-DSL 规则引擎,提升逻辑表达力

- **研究依据**:KAG 的逻辑形式引导混合推理引擎 + KG-DSL 规则在 HotpotQA +33.5% F1([arXiv:2409.13731](https://arxiv.org/abs/2409.13731));RoG 用规则路径模板([arXiv:2310.01045](https://arxiv.org/abs/2310.01045))。
- **改造点**:**已有 `src/fnixagent/core/rules/engine.py`**,在其上扩展 KG-DSL:支持 `IF concept.A AND NOT concept.B THEN rule.C` 逻辑规则,规则作为 L3 RULE 节点的可执行附件;在 `core/topology/search.py` 路径搜索后追加规则推理阶段。
- **预期效果**:KTG 从"权重乘积"升级为"权重乘积 + 逻辑规则",补齐表达力短板;直接对标 KAG 的混合推理。
- **复杂度**:中高(规则 DSL 设计 + 推理引擎约 5–8 人日)。

### 建议 4:时序化 KTG 对抗 misevolution(知识过时)

- **研究依据**:Zep/Graphiti 用时序知识图谱(TKG,边带 temporal validity)解决事实更新([Zep 论文](https://arxiv.org));LongMemEval 5 项能力含"时序推理"和"知识更新"([arXiv:2410.10813](https://arxiv.org/abs/2410.10813))。
- **改造点**:`src/fnixagent/core/topology/schema.py` 给边类型增加 `valid_from`/`valid_to` 字段;`core/topology/search.py` 路径搜索加入时间谓词过滤;`core/flywheel/stage4_climbing.py` 的衰减逻辑从"freshness × 0.999"升级为"时间窗失效"。
- **预期效果**:KTG 能处理"X 在 2024 是 A,2025 改为 B"这类时序推理;对抗 misevolution(错误知识固化后难纠正)。
- **复杂度**:中(schema 改 + 搜索改 + 持久化迁移约 4–6 人日)。

### 建议 5:在 LongMemEval/LoCoMo 上评测记忆系统

- **研究依据**:Mem0/Letta/Zep/MemClaw/AgentMemory 均在 LongMemEval/LoCoMo 报分([arXiv:2410.10813](https://arxiv.org/abs/2410.10813));AgentMemory LongMemEval-S R@5=95.2%,Mem0=68.5%,Letta=83.2%。
- **改造点**:`core/eval/open_benchmark/` 新增 `longmemeval_adapter.py`,把 KTG 作为记忆后端接入 LongMemEval 统一框架(indexing/retrieval/reading 三阶段);对比 KTG vs Mem0 vs Letta。
- **预期效果**:补齐记忆维度公开基准;若 KTG 多跳检索 R@5 超过 Mem0(68.5%)则证明图结构优势;若低于 AgentMemory(95.2%)则定位需补文件+向量混合。
- **复杂度**:中(适配器+跑分约 3–4 人日,依赖建议 4 的时序化)。

### 建议 6:对比 SWE-agent / OpenHands,补 Code 维度公开基准

- **研究依据**:SWE-agent([arXiv:2405.15793](https://arxiv.org/abs/2405.15793))、SWE-bench([arXiv:2310.06770](https://arxiv.org/abs/2310.06770))、OpenHands 是代码 agent 标准;SWE-agent v1.0.1 在 SWE-bench Full 达 SOTA。
- **改造点**:FnixAgent Code 模式接入 SWE-bench(已有 `core/code/benchmark/`),报 resolved%;对比 SWE-agent/OpenHands 在同模型下的差距。
- **预期效果**:证明 FnixAgent 在真实 GitHub issue 修复上的能力;若 KTG+MFP 能提升 SWE-bench resolved%,则证明自进化对代码任务有效。
- **复杂度**:高(SWE-bench 环境搭建+评测约 1–2 周)。

### 建议 7:用 Constitutional AI 形式硬化 CriticAgent(第③阶段)

- **研究依据**:Constitutional AI([arXiv:2212.08073](https://arxiv.org/abs/2212.08073))用 constitution 规则驱动自批判+自修订;论文 Conclusion 承认 CriticAgent 未硬化。
- **改造点**:`src/fnixagent/core/flywheel/stage3_reflection.py` + `core/reflection/`(已有 manager/validator/replanner)引入 constitution 规则集(可配置 YAML),让 CriticAgent 按 constitution 逐条批判轨迹,输出结构化反思。
- **预期效果**:MFP 第③阶段从"未硬化"变为"规则驱动可审计";反思质量提升;与 CAI 对标。
- **复杂度**:中(规则集设计 + 接入约 3–5 人日)。

### 建议 8:引入轻量学习型 router,超越 DAAO 纯启发式

- **研究依据**:RouteLLM([arXiv:2406.18665](https://arxiv.org/abs/2406.18665))用偏好数据训练 router,成本降 >2× 且有迁移能力;Router-R1([arXiv:2506.09033](https://arxiv.org/abs/2506.09033))多轮 RL 路由。
- **改造点**:`src/fnixagent/core/flywheel/daao_router.py` 保留零 LLM 启发式为"冷启动 fallback";新增可选的轻量学习型 router(基于 HERA 历史 signal 训练小分类器,在 `core/llm/router.py` 已有路由基础设施),BYOK 用户可选开启。
- **预期效果**:DAAO 从"零学习"升级为"冷启动启发式 + 可选学习型",在 LLMRouterBench 公开基准上报分;保留本地零算力 fallback。
- **复杂度**:中高(训练管线 + A/B 评测约 6–10 人日)。

---

## 附录:核心来源索引(全部已交叉验证)

### 自进化 Agent
- Voyager: https://arxiv.org/abs/2305.16291
- Reflexion: https://arxiv.org/abs/2303.11366
- Self-Refine: https://arxiv.org/abs/2303.17651
- ExpeL: https://arxiv.org/abs/2308.10144
- AgentTuning: https://arxiv.org/abs/2310.12823
- EvolveR: https://arxiv.org/abs/2510.16079 (ICML 2026, code: https://github.com/Edaizi/EvolveR)
- Sleep-time Compute: https://arxiv.org/abs/2504.13171 (Letta, code: https://github.com/letta-ai/sleep-time-compute)
- Constitutional AI: https://arxiv.org/abs/2212.08073
- Generative Agents: https://arxiv.org/abs/2304.03442

### KG + LLM
- GraphRAG: https://arxiv.org/abs/2404.16130
- HippoRAG: https://arxiv.org/abs/2405.14831 (NeurIPS 2024, code: https://github.com/OSU-NLP-Group/HippoRAG)
- LightRAG: https://arxiv.org/abs/2410.05779 (code: https://github.com/HKUDS/LightRAG)
- KAG: https://arxiv.org/abs/2409.13731 (蚂蚁+浙大, OpenSPG)
- KG-RAG: https://arxiv.org/abs/2405.12035
- ToG: https://arxiv.org/abs/2307.07697
- RoG: https://arxiv.org/abs/2310.01045
- Cognee: https://github.com/topoteretes/cognee

### 记忆系统
- MemGPT/Letta: https://arxiv.org/abs/2310.08560
- Mem0: https://arxiv.org/abs/2509.24824
- Zep/Graphiti: "Zep: A Temporal Knowledge Graph Architecture for Agent Memory"
- LongMemEval: https://arxiv.org/abs/2410.10813 (ICLR 2025, code: https://github.com/xiaowu0162/LongMemEval)

### LLM 路由
- RouteLLM: https://arxiv.org/abs/2406.18665 (LMSYS)
- FrugalGPT: https://arxiv.org/abs/2305.05176
- Router-R1: https://arxiv.org/abs/2506.09033 (UIUC, NeurIPS 2025)
- Hybrid LLM: https://arxiv.org/abs/2402.02323

### Benchmark
- MuSiQue: https://arxiv.org/abs/2211.13357
- HotpotQA: https://arxiv.org/abs/1809.09600
- SWE-agent: https://arxiv.org/abs/2405.15793
- SWE-bench: https://arxiv.org/abs/2310.06770

### FnixAgent 内部
- 论文: `e:\FNIX\FnixAgent\paper\main.tex`
- KTG 代码: `e:\FNIX\FnixAgent\src\fnixagent\core\topology\`(schema.py / graph.py / weights.py / search.py / store.py)
- MFP 代码: `e:\FNIX\FnixAgent\src\fnixagent\core\flywheel\`(stage1_perception.py / stage2_knowledge.py / stage3_reflection.py / stage4_climbing.py / daao_router.py / trace.py)
- STP 代码: `e:\FNIX\FnixAgent\src\fnixagent\core\skills\scheduler.py`
- 规则引擎(已存在,可扩展): `e:\FNIX\FnixAgent\src\fnixagent\core\rules\engine.py`
- Benchmark: `e:\FNIX\FnixAgent\src\fnixagent\core\code\benchmark\`
- 进化内核文档: `e:\FNIX\FnixAgent\docs\EVOLUTION_CORE.md`
