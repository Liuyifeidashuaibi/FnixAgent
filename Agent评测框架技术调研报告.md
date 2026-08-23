# Agent 评测框架技术调研报告

> 调研时间：2026年8月21日
> 调研对象：DeepEval、AgentBench、EvalScope、LangSmith SDK、AgentEvals
> 数据来源：GitHub 官方页面、官方文档、技术博客

---

## 总览对比

| 维度              | DeepEval              | AgentBench           | EvalScope         | LangSmith SDK    | AgentEvals         |
| ----------------- | --------------------- | -------------------- | ----------------- | ---------------- | ------------------ |
| GitHub Stars      | 16,742                | ~3,369               | 3,238             | 1,000            | 703                |
| 维护活跃度        | 非常活跃              | 停更（2025.02）      | 非常活跃          | 非常活跃         | 活跃               |
| 核心定位          | LLM/Agent单元测试框架 | LLM-as-Agent学术基准 | 一站式模型评测    | LLM可观测性+评估 | Agent轨迹评估      |
| pytest原生        | 是                    | 否                   | 否（CLI）         | 是               | 是                 |
| LLM-as-judge      | 是（G-Eval）          | 否                   | 部分              | 是               | 是（核心）         |
| Trace能力         | 是（@observe）        | 有限                 | 是（agent_trace） | 是（@traceable） | 否（评估已有轨迹） |
| 非LangChain Agent | 友好                  | 不友好               | 友好              | 友好             | 友好               |

---

## 一、DeepEval

### 1.1 项目地址和 Star 数

| 属性     | 值                                       |
| -------- | ---------------------------------------- |
| GitHub   | https://github.com/confident-ai/deepeval |
| Stars    | 16,742                                   |
| Forks    | 1,637                                    |
| License  | Apache-2.0                               |
| 语言     | Python (>=3.9)                           |
| 最新更新 | 2026年7月9日                             |
| 维护方   | Confident AI                             |

### 1.2 核心能力

DeepEval 是一个 Pytest 原生的 LLM 评估框架，定位为"LLM 应用的单元测试工具"。核心能力覆盖：

- **RAG 评估**：Faithfulness、Answer Relevancy、Contextual Recall/Precision、RAGAS
- **Agent 评估**：Task Completion、Tool Correctness、Step Efficiency、Plan Quality/Adherence
- **对话评估**：Role Adherence、Knowledge Retention、Conversation Completeness
- **多模态评估**：Text、Image、Audio 均为一等公民
- **Red Teaming**：通过姊妹项目 DeepTeam 进行 50+ 安全漏洞检测
- **合成数据集生成**：使用进化技术自动生成测试用例
- **基准测试**：内置 MMLU、HellaSwag、GSM8K 等标准基准

### 1.3 接入方式

DeepEval 对非 LangChain 体系的 Python Agent 提供了友好的接入方式，主要通过 `@observe` 装饰器手动标注 Agent 组件：

```python
from deepeval.tracing import observe
from deepeval.test_case import LLMTestCase

# 标记工具组件
@observe(type="tool")
def search_flights(origin, destination, date):
    return [{"flight": "CA1234", "price": 500}]

# 标记推理层组件
@observe(type="reasoning")
def parse_and_plan(user_input):
    return {"task": "book_flight", "steps": ["search", "compare", "book"]}

# 标记 Agent 主组件
@observe(type="agent")
def travel_agent(user_input):
    plan = parse_and_plan(user_input)
    flights = search_flights(plan["origin"], plan["destination"], plan["date"])
    return {"order_id": "ORD123456", "status": "confirmed"}
```

支持的 span 类型：`agent`、`tool`、`reasoning`、`llm`、`retriever`、`guardrail`。

此外，DeepEval 还提供了以下框架的原生集成：

- **OpenAI**：通过 `wrap_openai` 客户端包装器
- **LangChain/LangGraph**：通过回调处理器
- **LlamaIndex**：评估 RAG 应用
- **CrewAI**：评估多 Agent 系统
- **Pydantic AI**：类型安全验证
- **Anthropic**：通过客户端包装器评估 Claude 应用

### 1.4 指标体系

DeepEval 内置 50+ 研究背书的指标，分为以下几类：

**传统 LLM 指标**：

| 指标                 | 计算方式               | 说明                          |
| -------------------- | ---------------------- | ----------------------------- |
| G-Eval               | LLM-as-judge + CoT     | 通用评估，支持自定义 criteria |
| Answer Relevancy     | LLM + NLP 模型         | 答案与问题的相关性            |
| Faithfulness         | LLM 提取事实主张并验证 | 答案是否忠实于上下文          |
| Contextual Recall    | NLP 匹配               | 检索到的上下文覆盖度          |
| Contextual Precision | NLP 排序               | 检索结果排序质量              |
| Hallucination        | LLM + NLP              | 幻觉检测                      |
| Summarization        | LLM-as-judge           | 摘要质量                      |
| Toxicity / Bias      | 分类模型               | 毒性和偏见检测                |

**Agent 专用指标**：

| 指标                      | 计算方式       | 说明             |
| ------------------------- | -------------- | ---------------- |
| TaskCompletionMetric      | LLM-as-judge   | 任务是否完成     |
| ToolCorrectnessMetric     | 规则匹配 + LLM | 工具选择是否正确 |
| StepEfficiencyMetric      | 规则计算       | 执行步骤效率     |
| ArgumentCorrectnessMetric | LLM-as-judge   | 工具参数是否正确 |
| PlanQualityMetric         | LLM-as-judge   | 规划质量         |
| PlanAdherenceMetric       | LLM-as-judge   | 执行是否遵循计划 |

所有指标返回 0-1 分值并提供评分理由。阈值可通过 `threshold` 参数配置。

### 1.5 Trace 能力

**支持。** 通过 `@observe` 装饰器实现全链路追踪：

- 自动采集各组件的输入、输出和执行逻辑
- 支持 `update_current_span()` 动态更新 span 属性
- 自动构建嵌套的 span 树（agent → reasoning → tool → llm）
- 与 Confident AI 平台集成，提供可视化 trace 视图
- 支持生产环境实时追踪

### 1.6 LLM-as-judge

**支持，是核心能力。** 通过 G-Eval 实现：

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams

custom_metric = GEval(
    name="Custom Metric",
    criteria="Evaluate whether the output is concise and accurate",
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
    model="gpt-4o",  # 可配置任意 LLM
    threshold=0.7
)
```

- 支持 `evaluation_model` 参数配置 judge 模型（gpt-4o、claude-3-haiku 等）
- 使用 chain-of-thought + form-filling 降低随机性
- 提供 DAG（有向无环图）指标实现客观多步条件评分
- QAG（Question-Answer Generation）用于闭式、参考基础的评分

### 1.7 CI 集成

**完全支持，这是 DeepEval 的核心设计理念。**

```python
# pytest 原生集成
from deepeval import assert_test
from deepeval.metrics import TaskCompletionMetric
from deepeval.test_case import LLMTestCase
import pytest

@pytest.mark.parametrize("test_case", test_cases)
def test_agent(test_case: LLMTestCase):
    my_ai_agent(test_case.input)  # 自动捕获执行 trace
    assert_test(metrics=[TaskCompletionMetric(threshold=0.7)])
```

CLI 命令：`deepeval test run tests/test_agent.py`

- 与任何 CI/CD 环境兼容（GitHub Actions、GitLab CI 等）
- 支持参数化测试
- 支持批量数据集评估
- 结果可上传至 Confident AI 平台

### 1.8 优缺点总结

**优点**：

- 指标体系最丰富（50+），覆盖 RAG、Agent、对话、安全全场景
- pytest 原生集成，CI/CD 友好
- `@observe` 装饰器对非 LangChain Agent 友好
- LLM-as-judge（G-Eval）成熟且可配置
- 社区活跃（16.7k Stars），Thoughtworks 技术雷达推荐
- 支持多模态评估

**缺点**：

- LLM-as-judge 评估有 API 成本
- 部分高级功能（可视化报告、数据集管理）依赖 Confident AI 平台
- 配置项较多，学习曲线中等
- DAG 等高级指标配置较复杂

---

## 二、AgentBench

### 2.1 项目地址和 Star 数

| 属性     | 值                                  |
| -------- | ----------------------------------- |
| GitHub   | https://github.com/THUDM/AgentBench |
| Stars    | ~3,369                              |
| Forks    | 249                                 |
| License  | Apache 2.0                          |
| 发表     | ICLR 2024                           |
| 最新更新 | 2025年2月8日                        |
| 维护方   | 清华大学 THUDM 团队                 |

### 2.2 核心能力

AgentBench 是首个系统性评测 LLM 作为 Agent 能力的基准，发表于 ICLR 2024。核心能力：

- **8 个评测环境**，覆盖 Agent 在不同场景下的自主操作能力：
  - Operating System (OS)：在 Linux 终端执行任务
  - Database (DB)：SQL 查询与数据库操作
  - Knowledge Graph (KG)：知识图谱推理
  - Digital Card Game (DCG)：策略博弈
  - Lateral Thinking Puzzles (LTP)：侧向思维推理
  - House-Holding (HH)：基于 ALFWorld 的家务模拟
  - Web Shopping (WS)：基于 WebShop 的网购模拟
  - Web Browsing (WB)：基于 Mind2Web 的网页浏览
- 提供 Dev 和 Test 两个数据集分割
- 多轮交互评测（Test 集需约 13k 次生成）

### 2.3 接入方式

AgentBench 的接入方式偏学术研究导向，对自定义 Agent 的支持有限：

- **LLM 接入**：通过配置文件指定 LLM API（支持 OpenAI、Claude、本地模型等）
- **自定义 Agent**：需要修改源码，实现 Agent 接口适配器
- **非 LangChain 体系**：不友好。AgentBench 本身不依赖 LangChain，但其架构设计面向 LLM 评测而非自定义 Agent 接入
- 接入自定义 Python Agent 需要深入理解框架内部结构，适配成本较高

### 2.4 指标体系

AgentBench 使用基于规则的评分，不使用 LLM-as-judge：

| 指标              | 计算方式       | 说明                                 |
| ----------------- | -------------- | ------------------------------------ |
| 成功率 (SR)       | 规则判定       | 任务是否完成（各环境有特定成功条件） |
| 加权平均得分 (OA) | 8 环境加权平均 | 综合评分，各环境权重不同             |
| 交互效率          | 统计           | 平均交互轮次                         |
| 错误容忍度        | 统计           | 处理边界情况的能力                   |

各环境权重示例：Webshop (30.7)、KG (13.9) 对最终评分影响最大。

### 2.5 Trace 能力

**有限支持。**

- 记录多轮交互的完整对话轨迹
- 提供 trajectory dataset 用于行为克隆训练
- 不提供实时的 Trace 可视化或 span 级别的细粒度追踪
- 轨迹数据以文件形式存储，需手动分析

### 2.6 LLM-as-judge

**不支持。** AgentBench 使用各环境特定的规则评分（如 SQL 查询是否返回正确结果、OS 命令是否成功执行等），不使用 LLM 进行主观评判。

### 2.7 CI 集成

**不直接支持。**

- 通过命令行启动评测任务（`python -m agentbench`）
- 无 pytest 集成
- 可通过 shell 脚本集成到 CI，但需要额外开发
- 评测结果以 JSON/CSV 输出，需自行处理

### 2.8 优缺点总结

**优点**：

- 学术权威性高（ICLR 2024 收录）
- 8 个环境覆盖面广，评测维度全面
- 标准化基准，适合模型横向对比
- 规则评分客观可复现

**缺点**：

- 项目已停止维护（最后更新 2025年2月）
- 不适合自定义 Agent 评测（面向 LLM 评测设计）
- 接入门槛高，需修改源码
- 不支持 LLM-as-judge
- 无 pytest/CI 原生集成
- 无实时 Trace 可视化
- 环境部署复杂（需 Docker、数据库等）

---

## 三、EvalScope

### 3.1 项目地址和 Star 数

| 属性     | 值                                      |
| -------- | --------------------------------------- |
| GitHub   | https://github.com/modelscope/evalscope |
| Stars    | 3,238                                   |
| Forks    | 449                                     |
| License  | Apache-2.0                              |
| 最新更新 | 2026年8月（非常活跃）                   |
| 维护方   | 魔搭社区 (ModelScope)                   |

### 3.2 核心能力

EvalScope 是魔搭社区打造的一站式大模型评测框架，覆盖三大能力域：

- **模型能力评估**：100+ 内置评测基准（MMLU、C-Eval、GSM8K、AIME、SWE-bench 等）
- **推理性能压测**：TTFT、TPOT、throughput 等性能指标
- **结果可视化**：React + Vite 新版 Web 界面

**Agent 评测模式（2026年5月新增）**：

- 多轮 AgentLoop，支持 function_calling/react/swe_bench_* 策略
- 可插拔工具（bash、python_exec、submit）
- local/docker 沙箱环境
- 逐步记录 agent_trace

**外部 Agent 桥接（2026年5月新增）**：

- 直接评估 Claude Code、Codex 等 CLI Agent
- 透明转发 LLM 流量，记录完整 trajectory
- 通过 `@register_runner` 支持自定义 runner

**其他能力**：

- RAG 评测（MTEB 2.x + RAGAS 0.4.x）
- MCP Server 支持
- 多模态评测（VLM）
- 代码评测（HumanEval、LiveCodeBench、SWE-bench 系列）
- Agent Skill（自然语言驱动评测）

### 3.3 接入方式

EvalScope 提供多种接入方式：

**命令行方式**：

```bash
evalscope eval \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --datasets gsm8k arc \
  --limit 5
```

**Python API**：

```python
from evalscope.run import run_task
from evalscope.config import TaskConfig

task_cfg = TaskConfig(
    model='Qwen/Qwen2.5-0.5B-Instruct',
    datasets=['gsm8k', 'arc'],
    limit=5
)
run_task(task_cfg=task_cfg)
```

**Agent 评测模式**：

```python
from evalscope.config import NativeAgentConfig

# 配置 Agent 评测
agent_config = NativeAgentConfig(
    strategy="function_calling",  # 或 react, swe_bench_*
    tools=["bash", "python_exec", "submit"],
    environment="local",  # 或 docker
)
```

**外部 Agent 桥接**：

```python
from evalscope.register import register_runner

@register_runner("my_custom_agent")
class MyAgentRunner:
    def run(self, task_input):
        # 调用你的自定义 Agent
        return agent_response
```

- 对非 LangChain 体系友好，通过 `@register_runner` 可接入任意 Python Agent
- 支持 OpenAI API、Anthropic API、本地模型等多种推理后端

### 3.4 指标体系

EvalScope 的指标体系覆盖准确率和性能两个维度：

**准确率指标**：

| 指标     | 计算方式 | 说明                   |
| -------- | -------- | ---------------------- |
| Accuracy | 规则匹配 | 标准准确率             |
| pass@k   | 统计     | k 次采样中至少一次通过 |
| vote@k   | 多数投票 | k 次采样中多数通过     |
| pass^k   | 严格通过 | k 次采样全部通过       |

**性能指标**：

| 指标       | 说明                  |
| ---------- | --------------------- |
| TTFT       | Time To First Token   |
| TPOT       | Time Per Output Token |
| Throughput | 吞吐量（TPM/TPS）     |

**Agent 指标**：

- agent_trace：逐步记录 Agent 执行轨迹
- 任务完成率
- 工具调用正确性

**内置基准**：100+ 评测基准覆盖文本理解、数学推理、代码生成、多模态、RAG、Agent 等领域。

### 3.5 Trace 能力

**支持。**

- Agent 评测模式下自动记录 `agent_trace`
- 每个样本的 agent_trace 在 dashboard 的 Predictions tab 中逐步渲染
- 外部 Agent 桥接模式下记录完整 LLM 流量轨迹
- 支持 Trie agentic trace replay（用于性能基准测试）

### 3.6 LLM-as-judge

**部分支持。**

- RAG 评测模块使用 RAGAS（含 LLM-as-judge 组件）
- 大部分基准使用规则评分
- 不像 DeepEval 那样提供通用的 LLM-as-judge 框架
- 评估器可自定义，但需要额外开发

### 3.7 CI 集成

**间接支持。**

- 命令行工具可集成到 CI 脚本
- 支持 HTML 格式可视化报告生成
- 评测进度追踪
- 无 pytest 原生集成
- 可通过 `evalscope eval` 命令在 CI 中调用

### 3.8 优缺点总结

**优点**：

- 非常活跃（2026年8月仍在持续更新）
- 功能最全面：模型评测 + 性能压测 + Agent 评测 + RAG 评测
- 100+ 内置基准，开箱即用
- 外部 Agent 桥接支持 Claude Code、Codex 等
- MCP Server 支持
- 中文文档和社区支持好
- React + Vite 新版可视化界面

**缺点**：

- Agent 评测模式较新（2026年5月才推出），成熟度待验证
- 配置复杂，参数众多
- 主要面向模型评测，Agent 评测是附加功能
- 无 pytest 原生集成
- LLM-as-judge 支持有限

---

## 四、LangSmith / LangSmith SDK

### 4.1 项目地址和 Star 数

| 属性     | 值                                            |
| -------- | --------------------------------------------- |
| GitHub   | https://github.com/langchain-ai/langsmith-sdk |
| Stars    | 1,000                                         |
| Forks    | 282                                           |
| License  | MIT                                           |
| Commits  | 3,026                                         |
| 最新更新 | 2026年7月30日                                 |
| 维护方   | LangChain 团队                                |

> 注意：SDK 的 Star 数不能反映 LangSmith 平台的用户量。LangChain 主仓库有 128k+ Stars，LangSmith 作为其官方可观测性平台，实际用户基数远大于 SDK Star 数。

### 4.2 核心能力

LangSmith 是 LangChain 官方的 LLM 应用可观测性平台，SDK 提供以下核心能力：

- **追踪 (Tracing)**：记录每次 LLM 调用的输入、输出、耗时、Token 用量
- **调试 (Debugging)**：可视化 Agent 执行流程，快速定位问题节点
- **监控 (Monitoring)**：生产环境持续观测应用性能与质量
- **评估 (Evaluation)**：创建测试数据集、运行批量评估、对比版本效果
- **数据集管理**：管理测试用例和评估数据
- **提示词管理**：版本化提示词管理
- **Annotation Queue**：人工标注队列

### 4.3 接入方式

LangSmith SDK 对非 LangChain 应用非常友好，提供两种核心接入方式：

**方式一：`@traceable` 装饰器**

```python
import openai
from langsmith import traceable

client = openai.Client()

@traceable  # 自动追踪此函数
def pipeline(user_input: str):
    result = client.chat.completions.create(
        messages=[{"role": "user", "content": user_input}],
        model="gpt-4o"
    )
    return result.choices[0].message.content

pipeline("Hello, world!")
```

**方式二：`wrap_openai` 包装器**

```python
import openai
from langsmith.wrappers import wrap_openai

client = wrap_openai(openai.Client())

# 所有 OpenAI 调用自动被追踪
client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4o"
)
```

**环境变量配置**：

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=ls_...
export LANGSMITH_WORKSPACE_ID=<your-workspace-id>
```

- 完全不依赖 LangChain 框架，支持任何 Python LLM 应用
- `@traceable` 可标注任意 Python 函数，自动构建嵌套 trace
- 支持 `name`、`tags`、`metadata` 参数定制 trace
- JavaScript/TypeScript SDK 同样可用

### 4.4 指标体系

LangSmith 的评估体系通过 `StringEvaluator` 和自定义评估器实现：

**内置评估器**（通过 LangChain evaluation 模块）：

- 字符串匹配评估器
- 嵌入相似度评估器
- LLM-as-judge 评估器
- JSON 评估器
- 准确率/精确率评估器

**自定义评估器**：

```python
from langsmith.evaluation import StringEvaluator

def create_custom_evaluator():
    def quality_check(run_input, run_output, reference):
        # 自定义评分逻辑
        return {"score": 0.85, "comment": "Good response"}
    return StringEvaluator(
        evaluation_name="quality",
        grading_function=quality_check
    )
```

**评估运行**：

```python
from langsmith import Client

client = Client()
# 在数据集上运行评估
client.run_on_dataset(
    dataset_name="my_dataset",
    llm_or_chain_factory=my_agent,
    evaluation=evaluators,
    project_name="agent-eval-v1"
)
```

**后置指标计算**：

```python
# 对已有测试结果计算新指标，无需重新运行模型
client.compute_test_metrics(
    project_name="agent-eval-v1",
    evaluators=new_evaluators
)
```

### 4.5 Trace 能力

**核心能力，非常强大。**

- `@traceable` 自动追踪函数调用链，构建嵌套 trace 树
- 记录每次调用的：输入、输出、耗时、Token 用量、错误信息
- 支持标签 (`tags`) 和元数据 (`metadata`) 分类
- 生产环境采样率可配置（如 10%）
- 可视化 trace 视图（在 LangSmith 平台上）
- 支持选择性追踪（过滤不需要的数据）
- 支持异步追踪

### 4.6 LLM-as-judge

**支持。**

- LangChain evaluation 模块提供 LLM-as-judge 评估器
- 可配置 judge 模型
- 支持自定义评估 prompt
- 可通过 `RunEvalConfig` 配置批量评估

```python
from langchain.evaluation import RunEvalConfig
from langchain.smith import run_on_dataset

evaluation_config = RunEvalConfig(
    evaluators=[
        RunEvalConfig.LabeledCriteria("helpfulness"),
        RunEvalConfig.LabeledCriteria("correctness"),
    ],
    custom_evaluators=[my_custom_evaluator],
)
```

### 4.7 CI 集成

**支持。**

- 支持 pytest 集成
- `run_on_dataset` 函数可在测试中调用
- 结果可导出 CSV
- API 支持程序化访问
- 可与 GitHub Actions 等 CI 系统集成

### 4.8 优缺点总结

**优点**：

- 追踪能力业界最强，可视化好
- 对非 LangChain 应用友好（`@traceable` + `wrap_openai`）
- 评估 + 追踪 + 监控一体化
- 支持生产环境监控
- Python + JavaScript 双语言 SDK
- 数据集管理和版本对比功能
- 后置指标计算（无需重跑模型）

**缺点**：

- 需要 LangSmith 平台账号（SaaS 服务，免费版有限制）
- SDK Star 数较低（但实际用户量大）
- 评估能力不如 DeepEval 专业（指标体系不如其丰富）
- 离线使用受限（核心功能依赖平台）
- 自定义评估器需较多开发工作

---

## 五、AgentEvals

> **说明**：经过全面搜索，"Agent-Eval-Harness" 并非一个特定的知名 GitHub 项目名称。经过调研，最符合该定位的是 LangChain 官方维护的 **agentevals**（https://github.com/langchain-ai/agentevals），这是一个专注于 Agent 轨迹评估的开源库。此外，社区中还存在 canwhite/AgentEval（基于 HTTP 代理的流量捕获评估工具）和 AgentEvalHQ/AgentEval（.NET 生态评估框架）。本节以 langchain-ai/agentevals 为主要分析对象。

### 5.1 项目地址和 Star 数

| 属性     | 值                                         |
| -------- | ------------------------------------------ |
| GitHub   | https://github.com/langchain-ai/agentevals |
| Stars    | 703                                        |
| Forks    | 54                                         |
| License  | MIT                                        |
| Commits  | 244                                        |
| 最新更新 | 2026年7月                                  |
| 维护方   | LangChain 团队                             |
| 语言     | Python + TypeScript                        |

### 5.2 核心能力

AgentEvals 是 LangChain 官方的 Agent 轨迹评估库，专注于评估 Agent 执行过程中的中间步骤（trajectory）：

- **轨迹匹配评估**：strict / unordered / subset / superset 四种匹配模式
- **轨迹 LLM-as-judge**：使用 LLM 评估轨迹合理性
- **图轨迹评估**：针对 LangGraph 等图结构 Agent 的评估
- **工具参数匹配**：exact / ignore / subset / superset + 自定义匹配器
- **Python + TypeScript 双语言支持**
- **与 LangSmith 深度集成**

### 5.3 接入方式

AgentEvals 对非 LangChain 体系 Agent 非常友好。接入方式是将 Agent 的执行轨迹格式化为 OpenAI 消息列表：

```python
from agentevals.trajectory.llm import create_trajectory_llm_as_judge, TRAJECTORY_ACCURACY_PROMPT

# 创建评估器
trajectory_evaluator = create_trajectory_llm_as_judge(
    prompt=TRAJECTORY_ACCURACY_PROMPT,
    model="openai:o3-mini",
)

# 将 Agent 轨迹格式化为消息列表
outputs = [
    {"role": "user", "content": "What is the weather in SF?"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "SF"}',
                }
            }
        ],
    },
    {"role": "tool", "content": "It's 80 degrees and sunny in SF."},
    {"role": "assistant", "content": "The weather in SF is 80 degrees and sunny."},
]

# 评估
eval_result = trajectory_evaluator(outputs=outputs)
# {'key': 'trajectory_accuracy', 'score': True, 'comment': '...'}
```

- 不需要 Agent 使用 LangChain 或任何特定框架
- 只要能输出 OpenAI 消息格式的轨迹即可评估
- 也支持 LangChain `BaseMessage` 格式
- 安装：`pip install agentevals`

### 5.4 指标体系

AgentEvals 提供两类核心评估器：

**轨迹匹配评估器**（规则型）：

| 模式      | 说明                   | 适用场景             |
| --------- | ---------------------- | -------------------- |
| strict    | 相同顺序、相同工具调用 | 确保工具调用顺序固定 |
| unordered | 相同工具调用，顺序不限 | 允许灵活调用顺序     |
| subset    | 轨迹包含参考轨迹的子集 | 确保关键工具被调用   |
| superset  | 轨迹包含参考轨迹的超集 | 确保未调用额外工具   |

**工具参数匹配模式**：

| 模式            | 说明                         |
| --------------- | ---------------------------- |
| exact           | 参数完全匹配（默认）         |
| ignore          | 忽略参数，只匹配工具名       |
| subset/superset | 参数子集/超集匹配            |
| 自定义匹配器    | 为特定工具定义自定义比较函数 |

```python
# 自定义工具参数匹配示例
evaluator = create_trajectory_match_evaluator(
    trajectory_match_mode="strict",
    tool_args_match_mode="exact",
    tool_args_match_overrides={
        "get_weather": lambda x, y: x["city"].lower() == y["city"].lower()
    }
)
```

**轨迹 LLM-as-judge 评估器**（LLM 型）：

- 返回 `score`（boolean 或 float）和 `comment`/`reasoning`
- 支持 `continuous` 模式（0-1 浮点评分）
- 支持 `choices` 参数（限定可选分值）
- 支持 `system` prompt 和 `few_shot_examples`

**图轨迹评估器**：

- 针对图结构 Agent（如 LangGraph）
- 评估节点访问路径而非消息序列
- 提供 `extract_langgraph_trajectory_from_thread` 工具函数
- 支持 LLM-as-judge 和严格匹配两种模式

### 5.5 Trace 能力

**本身不记录 Trace。** AgentEvals 的定位是评估已有的轨迹，而非记录轨迹。

- 输入是 Agent 的执行轨迹（消息列表或图轨迹）
- 需要配合 LangSmith 的 `@traceable` 或其他追踪工具使用
- 与 LangSmith 集成后可在平台上查看 trace 并运行评估

### 5.6 LLM-as-judge

**核心支持。**

```python
from agentevals.trajectory.llm import create_trajectory_llm_as_judge, TRAJECTORY_ACCURACY_PROMPT

evaluator = create_trajectory_llm_as_judge(
    prompt=TRAJECTORY_ACCURACY_PROMPT,  # 预置提示词
    model="openai:o3-mini",              # judge 模型
    continuous=False,                     # 二元评分（默认）
    # continuous=True,                    # 0-1 浮点评分
    # choices=[0.0, 0.5, 1.0],           # 限定可选分值
    # system="You are an expert...",     # 系统提示
    # few_shot_examples=[...],           # 少样本示例
)
```

- 预置 `TRAJECTORY_ACCURACY_PROMPT` 和 `TRAJECTORY_ACCURACY_PROMPT_WITH_REFERENCE`
- 支持自定义 prompt（通过变量注入）
- 支持有/无参考轨迹两种评估模式
- 可配置 judge 模型（默认使用 LangChain chat model 集成）
- 也支持直接使用 OpenAI client

### 5.7 CI 集成

**支持。**

- 支持 pytest 集成（Python）
- 支持 Vitest/Jest 集成（TypeScript）
- 与 LangSmith 的 `evaluate` 函数集成
- 可在 CI 中作为测试断言使用

```python
# pytest 集成示例
from agentevals.trajectory.llm import create_trajectory_llm_as_judge

def test_agent_trajectory():
    evaluator = create_trajectory_llm_as_judge(
        prompt=TRAJECTORY_ACCURACY_PROMPT,
        model="openai:o3-mini",
    )
    result = evaluator(outputs=agent_trajectory)
    assert result["score"] is True
```

### 5.8 优缺点总结

**优点**：

- 专注于 Agent 轨迹评估，填补了"过程评估"空白
- 对非 LangChain Agent 友好（仅需消息格式轨迹）
- LLM-as-judge 灵活可配置
- 四种轨迹匹配模式 + 工具参数自定义匹配
- 图轨迹评估支持 LangGraph
- Python + TypeScript 双语言
- MIT 协议，轻量易集成

**缺点**：

- Star 数较少（703），社区规模小
- 功能单一（只评估轨迹，不记录 trace、不管理数据集）
- 依赖 LangChain 生态（LLM 调用默认通过 LangChain）
- 无内置指标体系（需自行组合评估器）
- 无可视化报告
- 无合成数据集生成

---

## 六、综合对比与选型建议

### 6.1 按使用场景选型

| 场景                    | 推荐框架       | 理由                                 |
| ----------------------- | -------------- | ------------------------------------ |
| Agent 单元测试 + CI/CD  | **DeepEval**   | pytest 原生、指标丰富、@observe 追踪 |
| LLM 模型能力基准评测    | **EvalScope**  | 100+ 基准、性能压测、活跃维护        |
| 生产环境可观测性 + 监控 | **LangSmith**  | 追踪能力最强、监控一体化             |
| Agent 轨迹过程评估      | **AgentEvals** | 专注轨迹、LLM-as-judge 灵活          |
| 学术研究/模型横向对比   | **AgentBench** | ICLR 权威、8 环境覆盖（但已停更）    |

### 6.2 非 LangChain Agent 接入难度对比

| 框架       | 接入难度 | 方式                                  |
| ---------- | -------- | ------------------------------------- |
| DeepEval   | 低       | `@observe` 装饰器标注任意 Python 函数 |
| LangSmith  | 低       | `@traceable` 装饰器 + `wrap_openai`   |
| AgentEvals | 低       | 将轨迹格式化为消息列表即可            |
| EvalScope  | 中       | `@register_runner` 注册自定义 runner  |
| AgentBench | 高       | 需修改源码，适配框架内部结构          |

### 6.3 关键能力矩阵

| 能力         | DeepEval     | AgentBench  | EvalScope      | LangSmith    | AgentEvals     |
| ------------ | ------------ | ----------- | -------------- | ------------ | -------------- |
| 50+ 内置指标 | 是           | 否（8环境） | 是（100+基准） | 部分         | 否（轨迹专用） |
| LLM-as-judge | 是（G-Eval） | 否          | 部分           | 是           | 是（核心）     |
| Trace 记录   | 是           | 有限        | 是             | 是（最强）   | 否             |
| pytest 集成  | 是           | 否          | 否             | 是           | 是             |
| CI/CD 友好   | 是           | 否          | 间接           | 是           | 是             |
| 生产监控     | 否           | 否          | 否             | 是           | 否             |
| 多模态       | 是           | 否          | 是             | 部分         | 否             |
| 性能压测     | 否           | 否          | 是             | 否           | 否             |
| 可视化报告   | 是（平台）   | 否          | 是（Web）      | 是（平台）   | 否             |
| 免费离线使用 | 是           | 是          | 是             | 否（需平台） | 是             |

### 6.4 组合使用建议

实际项目中，单一框架往往难以覆盖所有需求。推荐以下组合方案：

**方案一：DeepEval + LangSmith**

- DeepEval 负责 Agent 单元测试和 CI 评估
- LangSmith 负责生产环境追踪和监控
- 两者都支持 `@traceable`/`@observe` 装饰器，可共存

**方案二：EvalScope + AgentEvals**

- EvalScope 负责模型能力基准评测和性能压测
- AgentEvals 负责自定义 Agent 的轨迹质量评估
- 适合需要全面评测模型 + Agent 的团队

**方案三：DeepEval 独立使用**

- DeepEval 自带评估 + 追踪 + pytest 集成
- 适合中小团队快速上手，无需多框架整合

---

## 附录：数据来源说明

| 框架          | 数据来源                                                                 |
| ------------- | ------------------------------------------------------------------------ |
| DeepEval      | GitHub 页面 (16,742 Stars)、官方文档 deepeval.com、Thoughtworks 技术雷达 |
| AgentBench    | GitHub 页面、CSDN 技术博客 (3,369 Stars)、ICLR 2024 论文                 |
| EvalScope     | GitHub 页面 (3,238 Stars)、官方 README、魔搭社区文档                     |
| LangSmith SDK | GitHub 页面 (1,000 Stars)、官方文档 docs.smith.langchain.com             |
| AgentEvals    | GitHub 页面 (703 Stars)、官方 README                                     |

> 所有 Star 数据均来自 2026年8月 GitHub 页面实时数据。AgentBench 的 Star 数据来源于第三方技术博客引用（~3,369），因其 GitHub 页面未直接展示精确数字。
