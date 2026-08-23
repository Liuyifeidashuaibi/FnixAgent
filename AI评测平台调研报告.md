# AI 评测云平台调研报告：Confident AI 与 Braintrust

> 调研时间：2026-08-21 ｜ 调研目标：评估两个云评测平台的评测能力、接入方式、可视化与定价，并给出 FnixAgent 后端 API 的接入方案。

---

## 一、平台速览对比

| 维度     | Confident AI（DeepEval 云平台）                              | Braintrust                                                     |
| -------- | ------------------------------------------------------------ | -------------------------------------------------------------- |
| 定位     | LLM 评测 + 可观测性 + 红队 + 治理一体化                      | 评测优先的 AI 可观测性平台                                     |
| 开源关系 | DeepEval 框架（Apache-2.0，16.7k★）的官方云版本              | 专有平台；SDK 与 autoevals 开源（Apache-2.0）                  |
| 核心强项 | 40+ 研究级指标、Agent 轨迹评测、CI/CD 门禁、红队             | trace 摄取量大、工作流评测、CI 质量门禁、Loop agent            |
| 接入方式 | `@observe` 装饰器 / AI Connections（HTTP 无代码）/ MCP / SDK | tracing SDK（Python/TS/Java/Rust）/ auto-instrument / Eval API |
| 可视化   | trace 树、span 级指标、回归对比、仪表盘                      | trace 树、score 聚合、自定义图表、topics 模式发现              |
| 免费额度 | $0 永久：2 座位 / 1 项目 / 5 次测试每周 / 1GB-月 trace       | $0 永久：$10 credits / 1GB / 10k scores / 14 天留存            |
| 付费起步 | Starter $200/月                                              | Pro $249/月                                                    |
| 自托管   | 企业版支持（AWS/Azure/GCP/VPC）                              | 混合选项 / 企业版 on-prem                                      |
| 合规     | SOC2 Type II、HIPAA、GDPR                                    | SOC2 Type II、可选 BAA（HIPAA）                                |

---

## 二、平台一：Confident AI（DeepEval 云平台）

### 1. 平台地址和定位

- **官网**：https://confident-ai.com
- **应用入口**：https://app.confident-ai.com
- **文档**：https://www.confident-ai.com/docs
- **定位**：由 DeepEval 开源框架创始团队构建的「企业级 AI 评测与可观测性平台」。口号是「Where AI Quality is Standardized, Not Improvised」——把不同团队的生产 trace 统一转化为测试用例、用评测验证、在上线前拦截漏洞。覆盖评测（Evaluations）、可观测性（Observability）、红队（Red Teaming）、AI 治理（Governance）四大产品线，自称服务 500+ 家 AI 公司（含 Panasonic、Toshiba、Samsung、BCG、Epic Games 等）。

### 2. 核心功能

- **LLM 评测**：30+ 单轮指标 + 15+ 多轮指标（均来自 DeepEval），含 G-Eval、Faithfulness、Answer Relevancy、Hallucination、Contextual Recall 等；支持自定义 G-Eval（自然语言定义标准）和 code-eval（确定性代码指标）。
- **Agent 轨迹评测**：TaskCompletionMetric、StepEfficiencyMetric、ToolCorrectnessMetric、ArgumentCorrectnessMetric、PlanQualityMetric、PlanAdherenceMetric 等 Agent 专项指标。
- **无代码评测工作流**：通过 AI Connections 直接对 HTTP/流式端点发起评测（官方称「Postman for AI apps」），支持自定义请求头/密钥鉴权与响应预处理转换器。
- **多轮对话模拟**：Chat simulations，10 分钟模拟数千轮对话，输出 pass rate、平均轮次、幻觉率等。
- **数据集管理**：云端 golden 数据集、从生产 trace 自动策展、定时运行、版本快照、合成数据生成。
- **生产可观测性**：trace 摄取、在线评测/分类、实时告警、延迟与成本追踪。
- **红队**：基于 DeepTeam 框架，对齐 OWASP Top 10 for Agentic Applications 2026（ASI01 Goal Hijack、ASI02 Tool Misuse 等风险类别），产出 PDF 风险评估报告。
- **Prompt 版本管理**：git 风格分支/合并/审批/PR，可设 eval 门禁。
- **CI/CD 集成**：`deepeval test run` 接入 CI，指标低于阈值即阻断构建。

### 3. 接入方式：如何上传 Agent trace / 接入自定义 Agent

Confident AI 提供四条接入路径，对 FnixAgent 这类「自定义 HTTP Agent」最友好：

- **路径 A · `@observe` 装饰器（推荐用于代码内嵌）**：在 Python 代码中用 `@observe(type="agent"|"llm"|"tool"|"retriever"|"custom")` 标记组件，调用时自动采集 trace 上传云端。可用 `update_current_span(attributes=..., test_case=LLMTestCase(...))` 绑定输入输出与评测用例，trace 结束自动触发在线指标。

  ```python
  from deepeval.tracing import observe, update_current_span
  from deepeval.test_case import LLMTestCase

  @observe(type="agent", available_tools=["work_stream"])
  def fnix_agent(user_input: str) -> str:
      output = call_fnix_work_stream(user_input)  # 你的 HTTP 调用
      update_current_span(test_case=LLMTestCase(input=user_input, actual_output=output))
      return output
  ```

- **路径 B · AI Connections（无代码 HTTP 评测，最适合 FnixAgent）**：在平台配置一个 HTTP endpoint（含 method、URL、body 模板、鉴权头），平台直接对端点发起请求并评测返回。FnixAgent 的 `POST /api/v1/work/stream` 可配置为该 endpoint，配合响应转换器解析 NDJSON。

- **路径 C · 自定义 LLM 作为评测裁判**：继承 `DeepEvalBaseLLM` 包装任意模型 API，让指标用你自己的模型打分。

- **路径 D · MCP server / API**：Confident AI 全平台 API 化，可用 `confidentai` Python SDK 或 MCP server 在 Cursor/Claude Code 中直接拉数据集、跑评测、查 trace。

安装与登录：

```bash
pip install -U deepeval
deepeval login   # 粘贴 Confident AI API Key，测试结果自动上云
```

### 4. 可视化能力

- **trace 树展示**：完整的 trace 树（如 `agent.run → retrieval.search → rerank → tool.call → llm.generate → final.answer`），每个 span 显示类型、延迟、token、成本、输入输出。
- **对比分析**：测试运行间回归对比（regression testing），prompt/模型版本间 side-by-side 比较；AI arena 对 prompt 与 app 对打。
- **仪表盘**：生产 trace 监控面板（P50 延迟、平均质量、当日告警数），失败用例自动归类。
- **数据集视图**：从 trace 自动策展的评测数据集，按失败类型/边缘场景分类。

### 5. 定价模式

| 计划       | 月费   | 核心额度                                                                                | 关键限制                                         |
| ---------- | ------ | --------------------------------------------------------------------------------------- | ------------------------------------------------ |
| Free       | $0     | 完整评测套件 + tracing + prompt 版本 + 云数据集                                         | 2 座位、1 项目、5 次测试/周、1 GB-月 trace       |
| Starter    | $200   | 无代码评测工作流、自定义指标、在线评测、标注队列、chat 模拟、实时告警、完整 Project API | 不限座位、5 项目、5 GB-月 trace（超出 $1/GB-月） |
| Team       | $2,000 | 指标/数据集版本、git prompt 工作流、RBAC、SOC2、SSO                                     | 不限项目、75 GB-月 trace                         |
| Enterprise | 定制   | On-Prem 部署、自定义数据驻留、HIPAA、红队/治理模块                                      | 不限 trace、不限在线指标                         |

- trace 计费是市场最低之一：$1/GB-月，比同类低 3 倍+，留存时长不限。
- 评测裁判模型 token 费用约 $0.05/M 输入、$0.40/M 输出（随模型变动）。

### 6. 与开源框架的关系

- **Confident AI = DeepEval 的官方云版本**。DeepEval（Apache-2.0，GitHub 16.7k★）是开源评测框架，本地/CI 跑测试；Confident AI 在其上叠加协作、数据集管理、tracing、监控、仪表盘。
- 另有 **DeepTeam**（Apache-2.0，2.1k★）为开源红队框架，对应云端的 Red Teaming 模块。
- 关系明确：DeepEval 本地免费、可私有化；Confident AI 提供团队协作与生产可观测性增值。

---

## 三、平台二：Braintrust

### 1. 平台地址和定位

- **官网**：https://www.braintrust.dev（注意：`usebraintrust.com` 是另一家 HR/自动化公司，勿混淆）
- **文档**：https://www.braintrust.dev/docs
- **GitHub**：https://github.com/braintrustdata
- **定位**：以「评测优先」切入工程师工作流的 AI 可观测性平台。三大支柱——Observe（追踪）、Evaluate（评测）、Discover（模式发现）。2026 年是该赛道最大融资轮次之一支持的平台，自称是「评测优先商业」阵营代表。

### 2. 核心功能

- **追踪（Observe）**：框架无关的 SDK 自动捕获 LLM 调用、工具调用、应用逻辑；spans 类型含 `task`/`llm`/`function`/`tool`/`eval`/`score`/`classifier`。底层 Brainstore 数据库支持数百万条复杂 trace 的高效查询。
- **评测（Evaluate）**：对数据集跑实验，prompt/模型 side-by-side 对比；评分支持 LLM-as-judge（autoevals）、代码评分器、人工评分；版本化数据集；快速 prompt 工程 playground。
- **自动化（Automation）**：Topics 自动发现任务/问题/情感模式；continuous online scoring 捕捉回归；quality gates 阻断劣化发布。
- **Loop agent**：内置 AI agent，可自动跑评测、生成测试用例、迭代 prompt。
- **AI 代理（proxy）**：免费 AI 代理简化多 provider 访问、自动缓存降本，即使无账号可用。

### 3. 接入方式：如何上传 Agent trace / 接入自定义 Agent

- **自动埋点（auto-instrumentation）**：SDK 自动追踪 OpenAI/Anthropic 等主流 provider 调用，无需逐调用改代码。
- **手动 tracing（最适合 FnixAgent 这类自定义 HTTP Agent）**：用 `braintrust` SDK 的 `Logger`/`tracer` 手动打 span。对非 LLM provider 的自定义 Agent，手动埋点把每次 `work/stream` 调用打成一个 trace，内部 NDJSON 事件打成子 span。

  ```python
  import braintrust
  from braintrust import Span

  logger = braintrust.init_logger(project="fnixagent")
  with logger.start_span("fnix_work_stream", type="task") as span:
      span.log(input={"user_input": q, "work_mode": "craft"})
      output, events = call_fnix_work_stream(q)   # 你的 HTTP 调用 + NDJSON 解析
      for ev in events:                           # 把 thought/action/observation 打成子 span
          with span.start_span(ev["chunk_type"], type="function") as sub:
              sub.log(input=ev["content"])
      span.log(output=output)
  ```

- **Eval API**：用 `braintrust.Eval` 定义 dataset + task + scorers 跑离线评测实验，结果进 experiments。
- **SDK 多语言**：Python、TypeScript、Java、Rust 均有官方 SDK。
- **集成生态**：LangChain、LangGraph、CrewAI、Vercel AI SDK、Pydantic AI、DSPy 等，OpenAI/Anthropic/Gemini/Bedrock/Azure 等 provider。

### 4. 可视化能力

- **trace 检视**：实时检视每条 trace 的 prompt、response、tool call，可搜索数百万日志，追踪延迟/成本/质量。
- **对比分析**：experiments 对比 prompt 与模型版本；saved table views、custom columns、custom trace views。
- **自定义图表**：Pro 起可用 custom metrics、score 聚合、usage 数据构建图表与仪表盘（Starter 不含）。
- **Topics 模式发现**：自动聚类生产 trace 中的任务模式、问题、情感，无需预先定义。

### 5. 定价模式

| 计划       | 月费 | 核心额度                                                                              | 关键限制                                          |
| ---------- | ---- | ------------------------------------------------------------------------------------- | ------------------------------------------------- |
| Starter    | $0   | $10 model credits、1 GB 数据、10k scores、14 天留存                                   | 不限用户/项目/数据集/实验/playground              |
| Pro        | $249 | $249 credits、5 GB 数据、50k scores、30 天留存、custom charts、environments、优先支持 | 超出数据 $3/GB、scores $1.50/1k、留存 $0.50/GB-月 |
| Enterprise | 定制 | 自定义留存/导出、RBAC、SAML SSO、DPA/BAA、on-prem/托管部署、SLA                       | —                                                 |

- 计费维度：model credits（Topics 等内置 AI 功能 + 无自定义 key 的内置模型）、processed data（GB）、scores（LLM-as-judge/autoevals/代码评分器产出）。
- 符合条件初创可获 6–12 个月免费 Pro。

### 6. 与开源框架的关系

- **Braintrust 平台本身专有（非开源）**，但生态开源：
  - `braintrust-sdk-python` / `braintrust-sdk-javascript` / `-java` / `-rust`：tracing 与 evals 库，Apache-2.0。
  - `autoevals`：基于最佳实践的 AI 输出快速评测库，Apache-2.0，964★。
  - `braintrust-proxy`：AI 代理，MIT。
- 与 DeepEval 不同：Braintrust 没有一个对等的「开源评测框架」作为云版本的底座；它的开源部分是 SDK 与工具，平台核心闭源。

---

## 四、两平台选型建议

| 场景                                         | 推荐                                   | 理由                                                    |
| -------------------------------------------- | -------------------------------------- | ------------------------------------------------------- |
| 需要丰富研究级指标 + Agent 轨迹评测 + 红队   | Confident AI                           | 40+ 指标、Agent 专项指标、DeepTeam 红队，评测深度更强   |
| 重生产 trace 摄取量 + CI 质量门禁 + 模式发现 | Braintrust                             | Brainstore 大规模 trace、quality gates、Topics 自动聚类 |
| 预算敏感、要本地/CI 免费                     | 两者均可用 Free；DeepEval 开源可纯本地 | DeepEval Apache-2.0 本地零成本                          |
| 团队协作 + 非工程师参与评测                  | Confident AI                           | 无代码 AI Connections、标注队列、chat 模拟对 PM/QA 友好 |
| 多语言 SDK（Java/Rust/TS）                   | Braintrust                             | 官方四语言 SDK；Confident AI 主打 Python/TS             |
| 数据驻留/自托管硬需求                        | 两者企业版均支持                       | Confident AI 全 on-prem；Braintrust 混合/on-prem        |

---

## 五、FnixAgent 技术栈与 API 结构

### 技术栈

- **前端**：Tauri 2 + React 19（桌面应用）
- **后端**：Python + FastAPI + LangGraph
- **默认端口**：8003（`http://127.0.0.1:8003`，见 `src/fnixagent/main.py:226`）
- **两种模式**：`work/stream`（NDJSON 流式，9 步流水线主路径）与 `chat/agent`（对话模式，输出格式与 work/stream 一致）
- **work_mode**：`ask`（问一问）/ `plan`（想一想）/ `craft`（做一做，默认）

### 核心 API：`POST /api/v1/work/stream`

**请求体**（`WorkStreamRequest`，见 `src/fnixagent/api/routers/work.py:48`）：

| 字段              | 类型                 | 说明                                                                            |
| ----------------- | -------------------- | ------------------------------------------------------------------------------- |
| `user_input`      | str（必填，1–20000） | 用户输入                                                                        |
| `work_mode`       | str                  | ask / plan / craft（默认 craft）                                                |
| `llm`             | LlmOverride \| null  | BYOK 对象：provider / model / api_key / base_url / temperature / use_server_key |
| `workspace`       | str \| null          | 工作目录                                                                        |
| `session_id`      | str \| null          | 会话 ID                                                                         |
| `user_id`         | str \| null          | 用户 ID                                                                         |
| `disabled_skills` | list[str] \| null    | 禁用的内置技能名                                                                |

**响应**：`application/x-ndjson` 流，每行一个 JSON：

```json
{ "chunk_type": "thought", "content": "...", "done": false, "trace_id": "..." }
```

**chunk_type 事件类型**（见 `work.py` 的 `_ndjson` 调用）：

| chunk_type         | 含义                          |
| ------------------ | ----------------------------- |
| `guardrail`        | 输入安全拦截结果              |
| `evolution`        | 任务演化/意图理解             |
| `decision_context` | 决策上下文                    |
| `mission`          | 任务 schema                   |
| `pipeline`         | 流水线阶段                    |
| `thought`          | 推理思考                      |
| `action`           | 工具/动作调用                 |
| `observation`      | 动作结果观察                  |
| `artifact`         | 产出文件（docx/xlsx/code 等） |
| `text`             | 最终文本（通常 done=true）    |
| `done`             | 完成事件                      |
| `error`            | 错误                          |

---

## 六、推荐接入方案

FnixAgent 是「HTTP NDJSON 流式 Agent」，不是标准 OpenAI 兼容端点，因此不能直接被评测框架当作 LLM provider 调用。接入的核心是写一个**适配器**：调用 `/api/v1/work/stream` → 逐行解析 NDJSON → 聚合成 `{最终输出, 事件轨迹, artifacts}` → 喂给评测框架。

### 适配器：FnixAgent 客户端（三方案共用）

```python
# fnix_adapter.py
import json, httpx

FNIX_URL = "http://127.0.0.1:8003/api/v1/work/stream"

def call_fnix(user_input: str, work_mode: str = "craft",
              llm: dict | None = None) -> dict:
    """调用 FnixAgent work/stream，解析 NDJSON，返回聚合结果。"""
    payload = {"user_input": user_input, "work_mode": work_mode}
    if llm:
        payload["llm"] = llm
    events, final_text, artifacts, trace_id = [], "", [], ""
    with httpx.Client(timeout=300) as c:
        with c.stream("POST", FNIX_URL, json=payload) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                ev = json.loads(line)
                events.append(ev)
                trace_id = ev.get("trace_id", trace_id)
                ct = ev["chunk_type"]
                if ct == "text":
                    final_text = str(ev["content"])
                elif ct == "artifact":
                    artifacts.append(ev["content"])
    return {
        "output": final_text,
        "events": events,
        "artifacts": artifacts,
        "trace_id": trace_id,
    }
```

### 方案 A · 接入 DeepEval / Confident AI（推荐首选）

**理由**：DeepEval 的 AI Connections 无代码 HTTP 评测 + Agent 轨迹指标，与 FnixAgent 的 HTTP 流式端点天然契合；免费额度够原型验证。

**A1 · 无代码方式（AI Connections）**：在 Confident AI 配置 endpoint = `POST http://127.0.0.1:8003/api/v1/work/stream`，body 模板填 `{"user_input": "{{input}}", "work_mode": "craft"}`，用响应转换器从 NDJSON 提取 `text` 事件的 content 作为 actual_output，即可对数据集跑评测。

**A2 · 代码方式（@observe + Agent 指标）**：

```python
# eval_fnix_deepeval.py
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (TaskCompletionMetric, ToolCorrectnessMetric,
                              StepEfficiencyMetric, GEval, AnswerRelevancyMetric)
from deepeval.tracing import observe, update_current_span
from fnix_adapter import call_fnix

@observe(type="agent", available_tools=["work_stream"])
def fnix_run(user_input: str) -> str:
    res = call_fnix(user_input, work_mode="craft")
    # 把 NDJSON 事件轨迹作为 retrieval_context / 附加信息
    update_current_span(test_case=LLMTestCase(
        input=user_input,
        actual_output=res["output"],
        # 可把 thought/action/observation 拼成轨迹上下文供轨迹指标评估
    ))
    return res["output"]

metrics = [
    TaskCompletionMetric(threshold=0.7, evaluation_model="gpt-4o"),
    ToolCorrectnessMetric(threshold=0.8),
    StepEfficiencyMetric(threshold=0.5, minimum_steps=2),
    AnswerRelevancyMetric(threshold=0.7),
]

cases = [
    LLMTestCase(input="用 Rust 写一个 hello world 并保存到 main.rs", actual_output=fnix_run("...")),
    # ... 更多用例
]
evaluate(test_cases=cases, metrics=metrics)
# 运行: deepeval test run eval_fnix_deepeval.py
# 结果自动上云 Confident AI，可在 trace 树查看每个 span 指标
```

**BYOK 注意**：DeepEval 指标默认用 OpenAI 打分；FnixAgent 本身是 BYOK。评测裁判模型与被测 Agent 模型应分离——让 DeepEval 用一个独立 LLM（如 gpt-4o）当裁判，FnixAgent 用用户自带 key 跑任务，避免「自评自」偏差。

### 方案 B · 接入 Braintrust

**理由**：Braintrust 的手动 tracing + Eval API 适合把 FnixAgent 的 NDJSON 事件打成结构化 span 树，可视化轨迹细节，并用 quality gates 做 CI 门禁。

```python
# eval_fnix_braintrust.py
import braintrust
from fnix_adapter import call_fnix

braintrust.init(project="fnixagent-eval")
logger = braintrust.init_logger(project="fnixagent-eval")

def fnix_task(input_data: dict) -> str:
    q = input_data["user_input"]
    res = call_fnix(q, work_mode=input_data.get("work_mode", "craft"))
    # 把整次调用打成一个 trace，NDJSON 事件打成子 span
    with logger.start_span("fnix_work_stream", type="task") as span:
        span.log(input={"user_input": q})
        for ev in res["events"]:
            with span.start_span(ev["chunk_type"],
                                 type="tool" if ev["chunk_type"] == "action" else "function") as sub:
                sub.log(input=ev["content"])
        span.log(output=res["output"],
                 metadata={"artifacts": res["artifacts"], "trace_id": res["trace_id"]})
    return res["output"]

# 离线评测实验
braintrust.Eval(
    "fnixagent-eval",
    data=[{"input": "用 Rust 写 hello world", "expected": "fn main() { println!(\"Hello\"); }"}],
    task=lambda d: fnix_task({"user_input": d["input"]}),
    scores=[braintrust.scores.ExactMatch(),  # 或用 autoevals 的 Levenshtein / LLMClassifier
            ],
)
```

**评分器选择**：用 `autoevals`（`Factuality`、`Levenshtein`、`LLMClassifier` 等）对 FnixAgent 输出打分；也可写自定义代码评分器检查 artifacts 是否生成。

### 方案 C · 接入 EvalScope（补充）

- **定位差异**：EvalScope（魔搭社区/通义实验室，包名 `evalscope`）偏重**模型能力 benchmark**（MMLU、C-Eval、GSM8K、BFCL-v3、τ-bench 等标准数据集）与推理性能压测，含 Arena 对战模式。它不是 trace 可观测平台，对「自定义 HTTP Agent 的轨迹级评测」支持较弱。
- **接入思路**：实现自定义模型后端——把 FnixAgent 包装成一个符合 EvalScope 调用接口的 model（继承其 model 抽象或用 API backend），让 EvalScope 把标准数据集的 query 喂给 `call_fnix()`，取 `output` 作为模型回复参与 benchmark 打分。
- **适用场景**：若目标是把 FnixAgent 作为一个「模型」放进标准 benchmark 排名对比，用 EvalScope；若目标是评测 FnixAgent 自身的 Agent 行为质量（规划/工具调用/完成度），用 DeepEval 或 Braintrust 更合适。
- **局限**：EvalScope 对 NDJSON 流式事件轨迹、BYOK、生产 trace 监控无原生支持，需较多自定义适配。

### 接入方案选型小结

| 需求                                                 | 首选方案                                            |
| ---------------------------------------------------- | --------------------------------------------------- |
| 评测 FnixAgent 的 Agent 行为质量（规划/工具/完成度） | 方案 A（DeepEval）—— Agent 专项指标最全             |
| 可视化 NDJSON 事件轨迹 + CI 质量门禁                 | 方案 B（Braintrust）—— 手动 span 树 + quality gates |
| 把 FnixAgent 放进标准 benchmark 排名                 | 方案 C（EvalScope）—— 标准数据集对比                |
| 快速原型、零代码验证                                 | 方案 A1（Confident AI AI Connections）              |
| 生产监控 + trace 自动转测试集                        | Confident AI 在线评测 + auto-curate                 |

---

## 七、落地建议（实操路线）

1. **先跑通方案 A2**：本地装 DeepEval，写 `fnix_adapter.py` + `eval_fnix_deepeval.py`，准备 10–20 个核心场景用例，跑 `deepeval test run`，`deepeval login` 后结果上云 Confident AI 查看 trace 树与指标。免费额度即可起步。
2. **补充方案 B 做轨迹可视化**：对重点用例用 Braintrust 手动打 span，把 thought/action/observation/artifact 展开成 span 树，定位 Agent 执行瓶颈（哪步慢、哪步工具选错）。
3. **BYOK 分离裁判**：评测裁判模型固定用一个强模型（gpt-4o / claude），FnixAgent 被测侧用用户自带 key，保证评测一致性与可复现。
4. **建数据集**：把生产 trace 中失败的 case 沉淀成 golden 数据集（Confident AI auto-curate 或 Braintrust dataset），形成回归测试基线。
5. **接 CI**：用 DeepEval 的 `deepeval test run` 作为 PR 门禁，或 Braintrust quality gates，指标低于阈值阻断合并。

---

_报告完。所有定价与功能信息来源于两平台官网（2026-08-21 抓取）及 GitHub 仓库；FnixAgent API 结构来源于项目源码 `src/fnixagent/api/routers/work.py` 与 `main.py`。_
