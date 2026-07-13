# 顶级自进化 Agent · 完整落地计划（KTG + STP + MFP + LangGraph）

> 本文档为**执行前计划**,不含实现代码。覆盖:架构总览 · 技术校准 · 四大模块深度设计 · 文件结构 · 7 天落地排期 · 复用清单 · 风险评估 · 留存资产。

---

## 第〇部分:技术选型现实校准（必读）

在进入设计前,先对原始需求中的技术选型做务实校准,确保计划可执行:

| 原始需求 | 现实校准 | 最终方案 |
|----------|----------|----------|
| `langchain-skills` 官方仓库 | 该仓库**实际不存在**(LangChain 官方无此独立项目) | **自研 Skills 调度系统**,复用现有 `ToolRegistry` + `ToolExecutor`,扩展权重/优先级/拓扑绑定语义 |
| DeepSeek-MoE-V4 | MoE 系列开源权重版本为 V2/V2.5;"V4"不存在 | 接入 **DeepSeek API**(兼容 OpenAI),模型名 `deepseek-chat`/`deepseek-coder`;本地部署可选 DeepSeek-V2.5 权重 |
| "彻底抛弃 RAG" | 纯拓扑推理在冷启动期无数据会导致空图 | **拓扑为主(逻辑路径推理)+ 向量为辅(冷启动召回)**,飞轮成熟后向量权重趋零 |
| LangGraph 有状态循环 | 现有 7 步流水线天然同构 | LangGraph 作为编排内核,7 步映射为图节点 |
| 四阶飞轮全自动 | 三阶/四阶需 LLM 调用,成本与延迟非零 | 一二阶实时,三四阶后台异步(每日/每 N 次对话触发) |
| 现有 OfficeAgent 代码 | 已有 LLM 路由/工具执行/记忆/反思/安全等成熟实现 | **5 模块直接复用 + 5 模块改造 + 1 模块替换**(详见第八部分) |

**关键前提修复**:现有 `LLMResponse` 缺 `tool_calls` 字段,但 `openai_compat.py` 已向其传该参数 → function calling 场景会 `TypeError`。Day 1 必须修复。

---

## 第一部分:五层固化架构总览

```
┌─────────────────────────────────────────────────────────┐
│  ⑤ 自进化飞轮层 (MFP)                                    │
│     飞轮1 感知执行环 · 飞轮2 知识固化环                   │
│     飞轮3 元反思修正环 · 飞轮4 爬坡进化环                  │
├─────────────────────────────────────────────────────────┤
│  ④ 结构化记忆层                                           │
│     知识拓扑图(KTG) + 短期状态记忆 + 长期权重记忆          │
├─────────────────────────────────────────────────────────┤
│  ③ 推理决策层                                             │
│     DeepSeek 核心 LLM 推理 + ReAct/Plan&Execute 策略      │
├─────────────────────────────────────────────────────────┤
│  ② 状态编排层 (核心)                                      │
│     LangGraph 有状态循环引擎 + Skills 技能池(STP)         │
├─────────────────────────────────────────────────────────┤
│  ① 接入层                                                 │
│     用户输入 · 工具回调 · 系统事件                         │
└─────────────────────────────────────────────────────────┘
```

**固化原则**:五层层级永久固定,不可增删、不可重排。层间只允许相邻层通信(②↔③,③↔④,④↔⑤),禁止跨层调用。

---

## 第二部分:模块一 · 知识拓扑网络（KTG）深度设计

### 2.1 固定四层层级结构（永久不变）

| 层级 | 名称 | 职责 | 节点示例 |
|------|------|------|----------|
| L1 | 根目标 | Agent 全局能力定位 | "智能办公助手" |
| L2 | 概念层 | 对应大类 Skills | "论文检索"、"文档编辑"、"格式转换" |
| L3 | 规则层 | 技能调用前置条件/约束/优先级 | "检索需先确认领域"、"PDF 转换需源文件<50MB" |
| L4 | 事实执行层 | 具体执行案例/最优参数 | "arXiv 查询 cs.AI 返回 10 篇按相关性排序" |

**固化规则**:四层层级永久固定,新增节点必须归属某一层,不允许新增层。

### 2.2 六类固定节点类型

| 类型 | 所属层 | 字段 | 说明 |
|------|--------|------|------|
| `GOAL` | L1 | id, name, description | 根目标节点 |
| `CONCEPT` | L2 | id, name, skill_binding, weight | 概念节点,绑定技能 |
| `RULE` | L3 | id, name, precondition, constraint, priority | 规则节点 |
| `FACT` | L4 | id, name, content, source, confidence | 事实执行节点 |
| `CONSTRAINT` | L3 | id, name, rule_type, threshold | 约束节点(规则子类) |
| `INFERENCE` | L3 | id, name, from_node, to_node, reasoning | 推理链路节点 |

**固化规则**:节点类型固定为 6 类,不允许新增类型。

### 2.3 六类固定因果边关系

| 边类型 | 语义 | 方向 | 权重语义 |
|--------|------|------|----------|
| `CAUSAL` | A 导致 B | A→B | 因果强度 |
| `DEPENDS_ON` | A 依赖 B | A→B | 依赖必要性 |
| `DERIVES` | A 推导出 B | A→B | 推导置信度 |
| `CONTAINS` | A 包含 B | A→B | 包含权重(恒 1.0) |
| `PRECONDITION` | A 是 B 的前置 | A→B | 前置必要性 |
| `MUTEX` | A 与 B 互斥 | A↔B | 互斥强度(恒 -1.0,降权) |

**固化规则**:边类型固定为 6 类,不允许新增。

### 2.4 固定权重体系（参数固化）

| 参数 | 值 | 说明 |
|------|----|------|
| `INITIAL_WEIGHT` | 0.5 | 新节点/边初始权重 |
| `SINGLE_INCREMENT` | +0.02 | 单次有效推理路径增量 |
| `SUCCESS_BONUS` | +0.05 | 技能执行成功奖励 |
| `FAILURE_PENALTY` | -0.08 | 失败惩罚 |
| `DAILY_DECAY` | 0.999 | 每日衰减系数 |
| `DEPRECATE_THRESHOLD` | 0.05 | 低于此值标记废弃 |
| `CONFIDENCE_INIT` | 0.3 | 新节点初始置信度 |
| `MAX_WEIGHT` | 1.0 | 权重上限 |
| `MIN_WEIGHT` | 0.0 | 权重下限(非负) |

**固化规则**:以上参数固化,运行期不可修改,仅通过飞轮自动调节节点/边权重。

### 2.5 权重优先推理路径算法（替代向量相似度）

```
算法: TopologyPathSearch(query, ktg)
输入: 用户查询, 知识拓扑图
输出: 推理路径(节点序列)

1. 意图解析: LLM 从 query 提取关键词 → 匹配 L2 概念节点(按权重降序)
2. 路径展开: 从匹配的 L2 节点出发,沿 DEPENDS_ON/PRECONDITION 边向下展开
3. 权重排序: 对每条候选路径,计算路径权重 = Π(边权重) × Σ(节点置信度)
4. 约束过滤: 检查路径上的 CONSTRAINT 节点,剔除不满足条件的路径
5. 互斥排除: 若路径含 MUTEX 边,降权 0.5
6. 返回: 权重最高的 Top-K 路径(K=3)
```

**冷启动兜底**:拓扑图空时,回退到向量召回(BM25 + embedding)填充候选,但权重标记为"低置信(0.1)"。

### 2.6 增量写入逻辑（只增不删不覆盖）

| 操作 | 规则 |
|------|------|
| 新增节点 | 永远 `INSERT`,从不 `UPDATE` 已有节点内容 |
| 新增边 | 同上,若同源同目标的边已存在,新增一条平行边(不覆盖旧边权重) |
| 权重更新 | 不修改旧边,而是新增一条"权重修正边"(带时间戳) |
| 删除 | **永久禁止物理删除**;仅标记 `deprecated=True`(权重降至 0.01) |

**版本化**:每个节点/边带 `version` 与 `created_at`,支持任意时间点拓扑快照回放。

### 2.7 节点元数据自动更新

| 字段 | 更新时机 | 更新逻辑 |
|------|----------|----------|
| `confidence` | 每次推理路径命中该节点 | `confidence += 0.02`,上限 1.0 |
| `use_count` | 每次命中 | `use_count += 1` |
| `freshness` | 每日爬坡任务 | `freshness = 0.999 × freshness`(衰减);命中时重置为 1.0 |
| `last_used_at` | 每次命中 | 更新为当前时间戳 |

### 2.8 KTG 留存资产清单

| 资产 | 说明 | 存储格式 |
|------|------|----------|
| 拓扑结构 Schema | 四层 + 六节点 + 六边的固定定义 | YAML(版本化) |
| 初始骨架结构 | L1 根目标 + L2 概念层的初始拓扑 | JSON Graph |
| 私有节点库 | 全部对话沉淀的节点(只增不删) | JSONL(追加写) |
| 私有因果边库 | 全部推理产生的边(只增不删) | JSONL(追加写) |
| 权重数据集 | 每个节点/边的权重/置信度/使用频次快照 | JSONL(时间序列) |

---

## 第三部分:模块二 · 技能-拓扑突触协议（STP）深度设计

### 3.1 L2 概念节点与技能池绑定映射

```
CONCEPT 节点 ──bind──> Skill(技能)
    │                      │
    │ weight=0.8           │ priority=0.8(由拓扑权重换算)
    ↓                      ↓
  拓扑推理路径          Skills 调度器
```

**绑定规则**:
- 每个 L2 `CONCEPT` 节点**一对一绑定**一个 Skill
- 绑定关系存储在 `CONCEPT.skill_binding` 字段
- 一个 Skill 可被多个 CONCEPT 节点绑定(多对一)

### 3.2 拓扑边权重 → 技能调用优先级换算

```
技能优先级 = Σ(绑定该技能的 CONCEPT 节点权重 × 路径命中系数)

路径命中系数:
  - 当前推理路径经过该 CONCEPT: 1.0
  - 路径未经过但同属 L2 兄弟节点: 0.3
  - 完全无关: 0.0
```

**调度逻辑**:Skills 调度器按优先级降序选择 Top-K 技能,加载到推理上下文。

### 3.3 技能执行结果反向更新拓扑权重

```
反馈算法:
  技能执行成功:
    绑定 CONCEPT 节点 weight += SUCCESS_BONUS(+0.05)
    推理路径上的边 weight += SINGLE_INCREMENT(+0.02)
    CONCEPT.confidence += 0.02
  技能执行失败:
    绑定 CONCEPT 节点 weight += FAILURE_PENALTY(-0.08)
    推理路径上的边 weight -= 0.03
    若 weight < DEPRECATE_THRESHOLD(0.05): 标记 deprecated
```

**双向正反馈**:拓扑权重高 → 技能优先级高 → 被选中概率高 → 执行成功 → 拓扑权重更高。

### 3.4 三级技能权限体系

| 级别 | 名称 | 权限 | 示例 |
|------|------|------|------|
| `BASIC` | 基础技能 | 只读,无副作用 | 搜索、查询、解析 |
| `REASONING` | 推理技能 | 读写,可调用 LLM | 生成、转换、翻译 |
| `META` | 元反思技能 | 可修改拓扑权重/节点 | 知识萃取、元反思、爬坡优化 |

**权限校验**:只有 `META` 级技能可写入 KTG;`BASIC`/`REASONING` 只读 KTG。

### 3.5 禁用向量检索、强制拓扑推理协议

```python
# 伪代码(计划,不执行)
def retrieve_context(query, ktg, vector_store):
    # 强制:优先拓扑推理
    paths = ktg.search(query)  # 权重优先路径搜索
    if paths and paths[0].weight > 0.3:
        return paths  # 拓扑命中,直接返回
    # 兜底:仅当拓扑空或低置信时,向量召回
    if not paths or paths[0].weight < 0.1:
        return vector_store.search(query)  # 冷启动兜底
    return paths  # 拓扑低置信但仍返回(标记低置信)
```

**协议固化**:向量召回仅作为冷启动兜底,飞轮成熟后(拓扑节点 > 100)可配置关闭。

### 3.6 跨平台通用技能调度（脱离 LangGraph 原生规则）

现有 `ToolRegistry` + `ToolExecutor` 已具备注册/执行/并行/DAG/沙箱能力,STP 在其上扩展:

| 扩展点 | 现有 | STP 新增 |
|--------|------|----------|
| 元数据 | `ToolMetadata`(name/desc/category/schema) | + `skill_level`(BASIC/REASONING/META) + `topology_binding`(CONCEPT 节点 ID) + `priority`(动态权重) |
| 调度 | 按名称查找 | 按**拓扑权重换算的优先级**自动选择 Top-K |
| 反馈 | 无 | 执行结果**反向更新**拓扑权重(成功加/失败减) |
| 编排 | DAG 拓扑排序 | + 拓扑路径驱动的技能组合推荐 |

**跨平台**:STP 调度逻辑独立于 LangGraph,定义为纯 Python 接口,可迁移至任意编排框架。

### 3.7 STP 留存资产清单

| 资产 | 说明 |
|------|------|
| 技能拓扑绑定协议文档 | L2→Skill 绑定规则 + 换算公式 |
| 概念-技能映射关系表 | 每个 CONCEPT 节点绑定的 Skill |
| 技能优先级权重参数 | 动态权重值(随飞轮更新) |
| 双向反馈算法规则 | 成功/失败的权重增减规则(固化) |

---

## 第四部分:模块三 · 四阶进化飞轮（MFP）深度设计

### 4.1 飞轮整体闭环

```
用户使用 → 飞轮1 执行推理 → 飞轮2 沉淀知识 → 飞轮3 自我纠错 → 飞轮4 全局优化 → 下次更聪明
         ↑实时              ↑实时              ↑准实时            ↑后台异步
         无限循环 · 复利增长 · 永久进化
```

### 4.2 飞轮 1:感知执行环（实时）

**触发**:每次用户对话

**运行逻辑**:
1. LangGraph 捕获用户输入,初始化全局 State(消息列表、技能列表、拓扑路径、迭代次数)
2. STP 技能路由:根据任务类型,按拓扑权重匹配最优技能组合
3. LLM 基于知识拓扑权重路径推理(非随机 RAG 碎片)
4. 执行工具、输出结果
5. **完整保存本次全链路推理轨迹**(轨迹格式见下)

**轨迹存储格式(只对内开放,禁止外部修改)**:
```
TraceRecord {
  trace_id: str(UUID)
  timestamp: ISO8601
  user_input: str
  intent: str(LLM 解析的意图)
  topology_paths: list[Path](命中的拓扑路径)
  skills_invoked: list[{name, args, result, success, duration_ms}]
  reasoning_steps: list[{thought, action, observation}]
  final_answer: str
  llm_usage: {prompt_tokens, completion_tokens}
  duration_ms: int
  success: bool
}
```

**核心特性**:有状态可回溯、可暂停、可重试;技能按需调用,不冗余加载。

### 4.3 飞轮 2:知识固化环（实时,对话结束后触发）

**触发**:每次对话结束

**运行逻辑**:
1. 读取本次 `TraceRecord`
2. **过滤规则**(自动剔除垃圾):
   - 剔除:临时话术("你好"/"谢谢")、无实质推理的对话、执行失败的轨迹
   - 保留:新概念、新规则、新因果关系、新执行约束、新事实
3. **知识萃取**(LLM 提取):
   - 输入:TraceRecord
   - LLM Prompt: "从以下推理轨迹中提取:① 新概念 ② 新规则 ③ 新因果关系 ④ 新事实 ⑤ 新约束。仅输出结构化 JSON。"
   - 输出:标准化节点/边定义
4. **增量写入拓扑**:
   - 新节点:`INSERT`,初始权重 0.5,置信度 0.3
   - 新边:`INSERT`,初始权重 0.5
   - 本次有效推理路径上的现有节点/边:权重 +0.02

**彻底解决痛点**:普通 Agent 对话结束=知识清空;本 Agent 每次使用永久升级大脑结构。

### 4.4 飞轮 3:元反思修正环（准实时,每 N 次对话触发）

**触发**:每 5 次对话 或 用户显式反馈"不对"

**运行逻辑**:
1. 独立元 Agent 读取:最近 5 条 TraceRecord + 当前知识拓扑子图
2. **三维评估**:

| 评估维度 | 指标 | 判定阈值 |
|----------|------|----------|
| 推理路径质量 | 路径权重 vs 平均值 | 低于均值 50% → 降权 |
| 技能匹配准确率 | 成功调用率 | < 60% → 调整优先级 |
| 知识完整性 | 是否存在知识缺口 | LLM 判定缺失 → 补全 |

3. **自动权重调节**:
   - 有效路径:权重 +0.03(强化)
   - 无效路径:权重 -0.05(弱化)
   - 错误路径:标记 `deprecated=True`,权重降至 0.01(永久降级)
4. **自动补充拓扑缺失知识节点**:
   - LLM 分析"哪些应该有但没有的节点"
   - 新增节点,初始置信度 0.2(低于正常 0.3,需后续验证)

### 4.5 飞轮 4:爬坡进化环（后台异步,每日触发）

**触发**:每日定时任务(或每 100 次对话)

**运行逻辑**:
1. 后台常驻任务:批量分析全部历史 TraceRecord
2. **自动总结**:
   - 高频任务范式(出现 ≥ 3 次的相似任务模式)
   - 常用推理链路(权重 Top-10 路径)
   - 高频技能组合(经常一起调用的技能)
3. **自动优化三件套**:
   - 重构知识拓扑薄弱链路(低权重但高频使用的路径 → 权重提升)
   - 调整 Skills 调用优先级权重(高频成功技能 → 优先级提升)
   - 沉淀专属任务思维范式(高频范式固化为 L3 规则节点)
4. **全局旧知识自动衰减**:
   - 所有节点 `freshness × 0.999`
   - `freshness < 0.3` 且 `use_count < 5` 的节点:权重 × 0.95
   - 连续 30 天未命中的节点:标记 `stale=True`(不删除,仅降权)

### 4.6 MFP 留存资产清单

| 资产 | 说明 |
|------|------|
| 四阶飞轮闭环运行规则 | 永久固定的触发条件 + 执行逻辑 |
| 轨迹采集标准化格式 | TraceRecord Schema(JSON Schema) |
| 知识萃取筛选标准 | 保留/剔除规则(固化) |
| 元反思评估阈值 | 三维评估的判定阈值(固化) |
| 奖惩权重规则 | 强化/弱化/废弃的增减值(固化) |
| 离线全局优化迭代规则 | 每日爬坡任务的执行逻辑(固化) |

---

## 第五部分:模块四 · 跨平台通用资产规范

### 5.1 三套通用固定接口

| 接口 | 签名 | 说明 |
|------|------|------|
| 资产加载 | `load_assets(path: str) -> AssetsBundle` | 启动时加载全部留存资产 |
| 增量更新 | `append_asset(asset: NodeOrEdgeOrTrace, path: str) -> None` | 追加写,不修改旧数据 |
| 飞轮触发 | `trigger_flywheel(stage: int, context: dict) -> FlywheelResult` | 触发指定阶飞轮 |

### 5.2 资产完全解耦规则

- 资产文件格式:**JSON/JSONL/YAML**(纯文本,不依赖任何框架)
- 资产读写:**不 import** LangGraph/LangChain/FastAPI/任何模型 SDK
- 资产结构:由 JSON Schema 定义,跨平台通用

### 5.3 版本增量备份机制

- 每次飞轮执行后,对拓扑图做**快照**(带时间戳)
- 保留最近 30 天每日快照 + 全部周快照
- 快照格式:JSON Graph(节点+边+权重)

### 5.4 资产私有化加密存储

- 资产文件 AES-256 加密,密钥由用户密码派生(PBKDF2)
- 密钥不落盘,仅内存持有
- 跨设备同步时,加密文件传输,解密在本地

### 5.5 跨平台资产留存清单

| 资产 | 说明 |
|------|------|
| 跨平台通用接入标准协议 | 三接口定义 + 解耦规则 |
| 资产备份&迭代版本规范 | 快照策略 + 保留策略 |
| 个人专属资产加密密钥 | 用户密码派生,不落盘 |

---

## 第六部分:文件结构规划

```
OFFICEAGENT/
├── src/officeagent/
│   ├── core/                          # 复用现有(5 模块直接复用)
│   │   ├── config.py                  # 复用 + 追加 LangGraphConfig/TopologyConfig
│   │   ├── types.py                   # 复用 + 追加 KTG/STP/MFP 类型
│   │   ├── exceptions.py              # 复用
│   │   ├── llm/                       # 复用 + 新增 DeepSeekProvider
│   │   ├── memory/                    # 复用(短期记忆作状态记忆)
│   │   ├── tools/                     # 复用 + 扩展为 Skills(加权重/优先级)
│   │   ├── reasoning/                 # 改造:包装为 LangGraph node
│   │   ├── reflection/                # 改造:升级为元反思环
│   │   ├── security/                  # 复用
│   │   ├── prompt/                    # 复用
│   │   ├── retrieval/                 # 替换:向量检索 → 知识拓扑
│   │   ├── orchestrator/              # 改造:7 步流水线 → LangGraph 图
│   │   ├── topology/                  # 【新建】知识拓扑网络(KTG)
│   │   │   ├── __init__.py
│   │   │   ├── schema.py              # 四层 + 六节点 + 六边 Schema
│   │   │   ├── graph.py               # 拓扑图数据结构(节点/边/权重)
│   │   │   ├── search.py              # 权重优先推理路径算法
│   │   │   ├── weights.py             # 权重体系(初始值/增量/衰减)
│   │   │   └── store.py               # 增量写入存储(只增不删)
│   │   ├── skills/                    # 【新建】技能-拓扑突触协议(STP)
│   │   │   ├── __init__.py
│   │   │   ├── protocol.py            # 技能拓扑绑定协议
│   │   │   ├── scheduler.py           # 拓扑权重驱动的技能调度
│   │   │   ├── feedback.py            # 执行结果反向更新拓扑
│   │   │   └── levels.py              # 三级权限体系(BASIC/REASONING/META)
│   │   └── flywheel/                  # 【新建】四阶进化飞轮(MFP)
│   │       ├── __init__.py
│   │       ├── stage1_perception.py   # 飞轮1:感知执行环(轨迹采集)
│   │       ├── stage2_knowledge.py    # 飞轮2:知识固化环(萃取+写入)
│   │       ├── stage3_reflection.py   # 飞轮3:元反思修正环(三维评估)
│   │       ├── stage4_climbing.py     # 飞轮4:爬坡进化环(每日优化)
│   │       └── trace.py               # 轨迹记录格式与存储
│   ├── graph/                         # 【新建】LangGraph 编排层
│   │   ├── __init__.py
│   │   ├── state.py                   # 全局 State 定义
│   │   ├── nodes.py                   # 图节点(7 步映射)
│   │   ├── edges.py                   # 条件边(路由/循环/终止)
│   │   └── builder.py                 # 图装配(节点+边+编译)
│   ├── assets/                        # 【新建】跨平台通用资产
│   │   ├── __init__.py
│   │   ├── bundle.py                  # 资产包加载/保存
│   │   ├── crypto.py                  # 加密存储
│   │   └── snapshot.py                # 版本快照
│   ├── api/                           # 复用现有(微调)
│   ├── business/                      # 复用现有(技能化)
│   ├── services/                      # 改造:build_scheduler → build_graph
│   ├── adapters/                      # 复用现有
│   └── models/                        # 复用现有
├── assets/                            # 【新建】留存资产目录(加密)
│   ├── topology/                      # 拓扑图快照
│   ├── traces/                        # 推理轨迹
│   └── snapshots/                     # 版本快照
├── config/
│   ├── topology_schema.yaml           # 【新建】KTG 固定 Schema
│   ├── skill_bindings.yaml            # 【新建】STP 绑定关系
│   ├── flywheel_rules.yaml            # 【新建】MFP 飞轮规则
│   └── ...
└── tests/
    ├── unit/test_topology/            # 【新建】KTG 测试
    ├── unit/test_skills/              # 【新建】STP 测试
    ├── unit/test_flywheel/            # 【新建】MFP 测试
    └── integration/test_e2e_evolution.py  # 【新建】飞轮闭环测试
```

---

## 第七部分:7 天落地排期

### Day 1:环境搭建 + Bug 修复

| 任务 | 产出 |
|------|------|
| 安装 `langgraph`、`langchain-core`、`langchain-openai` | requirements.txt 更新 |
| 新增 `DeepSeekProvider(OpenAICompatibleProvider)` | providers/deepseek.py |
| 修复 `LLMResponse.tool_calls` 字段缺失 | types.py 补字段 |
| 扩展 `ToolMetadata` 增加 `skill_level`/`topology_binding`/`priority` | tools/protocol.py |
| 新增 `TopologyConfig`/`SkillsConfig`/`FlywheelConfig` | config.py |
| 新增 KTG/STP/MFP 相关类型 | types.py |

### Day 2:知识拓扑网络(KTG)核心

| 任务 | 产出 |
|------|------|
| 定义四层 + 六节点 + 六边 Schema | topology/schema.py |
| 实现拓扑图数据结构(节点/边/权重) | topology/graph.py |
| 实现增量写入存储(只增不删) | topology/store.py |
| 实现权重体系(初始值/增量/衰减) | topology/weights.py |
| 实现权重优先推理路径算法 | topology/search.py |
| KTG 单元测试 | tests/unit/test_topology/ |

### Day 3:技能-拓扑突触协议(STP)

| 任务 | 产出 |
|------|------|
| 实现技能拓扑绑定协议 | skills/protocol.py |
| 实现三级权限体系 | skills/levels.py |
| 实现拓扑权重驱动的技能调度 | skills/scheduler.py |
| 实现执行结果反向更新拓扑 | skills/feedback.py |
| STP 单元测试 | tests/unit/test_skills/ |

### Day 4:LangGraph 编排层 + 飞轮 1/2

| 任务 | 产出 |
|------|------|
| 定义全局 State | graph/state.py |
| 7 步流水线映射为图节点 | graph/nodes.py |
| 条件边(路由/循环/终止) | graph/edges.py |
| 图装配与编译 | graph/builder.py |
| 飞轮 1:感知执行环(轨迹采集) | flywheel/stage1_perception.py |
| 飞轮 2:知识固化环(萃取+写入) | flywheel/stage2_knowledge.py |

### Day 5:飞轮 3/4 + 元反思

| 任务 | 产出 |
|------|------|
| 飞轮 3:元反思修正环(三维评估) | flywheel/stage3_reflection.py |
| 打通 SelfReflectEngine ↔ Replanner ↔ KTG | reflection/ 改造 |
| 飞轮 4:爬坡进化环(每日优化) | flywheel/stage4_climbing.py |
| 轨迹记录格式与存储 | flywheel/trace.py |
| MFP 单元测试 | tests/unit/test_flywheel/ |

### Day 6:跨平台资产 + 加密 + 快照

| 任务 | 产出 |
|------|------|
| 资产包加载/保存 | assets/bundle.py |
| AES-256 加密存储 | assets/crypto.py |
| 版本快照机制 | assets/snapshot.py |
| 飞轮闭环集成测试 | tests/integration/test_e2e_evolution.py |

### Day 7:全链路联调 + 闭环自测

| 任务 | 产出 |
|------|------|
| services/service.py 重写为 `build_graph()` | 图装配根 |
| API 层接入 LangGraph(graph.invoke 替代 scheduler.process) | api/routers/chat.py |
| 全量测试(现有 111 + 新增) | 全绿 |
| 飞轮闭环验证(模拟 10 轮对话,验证拓扑增长) | 集成测试通过 |

---

## 第八部分:现有代码复用清单

| 模块 | 状态 | 复用方式 |
|------|------|----------|
| `core/config.py` | ✅ 直接复用 | 追加 TopologyConfig/SkillsConfig/FlywheelConfig 域 |
| `core/types.py` | ✅ 直接复用 | 追加 KTG/STP/MFP 类型;修复 LLMResponse.tool_calls |
| `core/exceptions.py` | ✅ 直接复用 | 追加 TopologyError/SkillError/FlywheelError |
| `core/llm/` | ✅ 直接复用 | 新增 DeepSeekProvider;路由/熔断/限流/缓存/计费零改造 |
| `core/security/` | ✅ 直接复用 | 安全引擎零改造 |
| `core/memory/short_term.py` | 🔧 改造复用 | 滑动窗口/裁剪/O(1)计数复用,扩展承载 State |
| `core/memory/entity.py` | 🔧 改造复用 | 实体白名单机制复用,作为 KTG 节点来源之一 |
| `core/tools/` | 🔧 改造复用 | 注册/执行/并行/DAG/沙箱复用,扩展 Skills 语义 |
| `core/reasoning/` | 🔧 改造复用 | 策略模式保留,reason() 包装为 LangGraph node |
| `core/reflection/` | 🔧 改造复用 | Validator/Replanner 复用,升级为元反思,打通 SelfReflect 断层 |
| `core/orchestrator/` | 🔧 改造复用 | 7 步映射为节点,Context 转 State,process() 改 graph.invoke |
| `core/retrieval/` | 🔄 替换 | 扁平向量检索 → 知识拓扑;抽象接口 + RRF 融合算法保留作兜底 |
| `services/storage.py` | ✅ 直接复用 | 4 类 Store 零改造 |
| `services/service.py` | 🔧 改造复用 | build_scheduler → build_graph;_create_llm_providers 加 DeepSeek |
| `api/routers/` | 🔧 改造复用 | chat.py 接入 graph.invoke;其余零改造 |
| `business/` | 🔧 改造复用 | 工具函数复用,补充 SkillMetadata 绑定 |
| `adapters/` | ✅ 直接复用 | DB/Cache 适配器零改造 |
| `models/` | ✅ 直接复用 | ORM/领域模型零改造 |

---

## 第九部分:技术风险与缓解策略

| 风险 | 等级 | 缓解策略 |
|------|------|----------|
| `langchain-skills` 仓库不存在 | 🟡 中 | 自研 Skills 系统,复用现有 ToolRegistry,设计为可插拔 |
| LangGraph 学习曲线 | 🟡 中 | 现有 7 步流水线天然同构,迁移路径清晰 |
| DeepSeek API 成本 | 🟡 中 | 飞轮 3/4 异步执行;缓存复用;Mock 模式开发 |
| 拓扑冷启动空图 | 🟠 高 | 向量召回兜底;初始骨架预置 L1+L2;飞轮 2 快速填充 |
| LLM 萃取质量不稳定 | 🟠 高 | 双层校验(规则+LLM);低置信节点标记;飞轮 3 修正 |
| 增量写入导致图膨胀 | 🟡 中 | 每日衰减;废弃标记;快照压缩(合并同源修正边) |
| 加密密钥丢失 | 🔴 高 | 密钥恢复短语(助记词);密钥不落盘 |
| 四阶飞轮成本累积 | 🟡 中 | 飞轮 4 每日一次;飞轮 3 每 5 次对话;可配置频率 |

---

## 第十部分:最终留存资产汇总

### 10.1 个人永久不可复刻的 AI 财富

| # | 资产 | 唯一性来源 |
|---|------|------------|
| 1 | 个人专属因果知识拓扑大脑 | 独一无二的思维结构 + 权重数据(只增不删) |
| 2 | 独家技能-拓扑神经调度协议 | 私有路由逻辑(拓扑权重→技能优先级→反向反馈) |
| 3 | 独家四阶自进化飞轮闭环 | 私有生长规则(感知→固化→反思→爬坡) |
| 4 | 全套跨平台通用迁移标准 | 可复用至所有 AI 项目(三接口 + 解耦 + 加密) |
| 5 | 全程迭代沉淀的个人 AI 思维范式数据库 | 高频范式固化为 L3 规则节点 |

### 10.2 资产目录结构

```
assets/                          # 加密存储
├── topology/
│   ├── schema.yaml              # 固定 Schema(永久不变)
│   ├── skeleton.json            # 初始骨架(L1+L2)
│   ├── nodes.jsonl              # 全部节点(追加写)
│   ├── edges.jsonl              # 全部边(追加写)
│   └── snapshots/               # 每日快照
│       ├── 2026-07-03.json
│       └── ...
├── traces/
│   └── traces.jsonl             # 全部推理轨迹(追加写)
├── skills/
│   ├── bindings.yaml            # 概念-技能映射表
│   └── priorities.json          # 技能优先级权重
├── flywheel/
│   ├── rules.yaml               # 飞轮规则(固化)
│   └── history.jsonl            # 飞轮执行历史
└── meta/
    ├── encryption.key.enc       # 加密密钥(用户密码派生)
    └── version.json             # 资产版本信息
```

---

## 第十一部分:执行前确认事项

在开始 Day 1 执行前,需确认以下决策:

1. **DeepSeek 接入方式**:API 调用(需 `DEEPSEEK_API_KEY`)还是本地部署(DeepSeek-V2.5 权重)?
2. **拓扑图存储**:纯 JSONL 文件(简单,适合单机)还是图数据库 Neo4j(适合大规模)?
3. **飞轮 3/4 触发频率**:默认(5 次/每日)还是自定义?
4. **加密策略**:是否启用 AES-256 加密(开发期可关闭)?
5. **现有 API 兼容**:是否保留现有 `/api/v1/chat` 接口(推荐保留,内部改调 graph.invoke)?

---

*计划版本:1.0 · 生成日期:2026-07-03 · 待确认后进入执行阶段*
