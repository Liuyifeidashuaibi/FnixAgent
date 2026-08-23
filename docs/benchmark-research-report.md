# AI Agent 评测基准数据集技术调研报告

> **调研时间**: 2026-08-21
> **调研目标**: SWE-bench Verified、GAIA、MCP-Bench/MCP-Atlas、OSWorld 四大公开基准数据集
> **适配对象**: FnixAgent（Tauri 桌面 AI 工作台，支持文件操作、代码生成、终端命令、Craft/Plan/Ask 三种模式）

---

## 目录

1. [SWE-bench Verified](#1-swe-bench-verified)
2. [GAIA](#2-gaia)
3. [MCP-Bench / MCP-Atlas](#3-mcp-bench--mcp-atlas)
4. [OSWorld](#4-osworld)
5. [FnixAgent 适配性综合分析](#5-fnixagent-适配性综合分析)

---

## 1. SWE-bench Verified

### 1.1 项目地址和规模

| 维度                  | 数据                                   |
| --------------------- | -------------------------------------- |
| GitHub                | https://github.com/SWE-bench/SWE-bench |
| 官网/排行榜           | https://www.swebench.com/              |
| Star                  | 5.7k                                   |
| Fork                  | 948                                    |
| Commits               | 725                                    |
| 许可证                | MIT                                    |
| 发表会议              | ICLR 2024 Oral                         |
| **Verified 子集规模** | **500 个实例**（人工筛选确认可解决）   |
| Full 规模             | 2,294 个实例                           |
| Lite 规模             | 300 个实例（低成本评估）               |
| Multilingual          | 300 个实例（9 种编程语言）             |
| Multimodal            | 517 个实例（含视觉元素）               |

SWE-bench 从 12 个流行 Python 仓库（如 sympy、django、scikit-learn、matplotlib 等）的真实 GitHub Issue 和 Pull Request 中构建。Verified 子集由 OpenAI Preparedness 团队合作，经人工软件工程师确认每个问题均可解决，于 2024 年 8 月发布。

### 1.2 测试维度

SWE-bench 评测的核心能力：

- **代码库导航**：在大型代码库中定位相关文件和代码段
- **问题理解**：理解 GitHub Issue 描述的问题本质
- **多文件协调修改**：跨函数、跨类的代码修改
- **依赖管理**：理解项目依赖和 API 约束
- **向后兼容性**：修改不破坏现有功能
- **测试通过能力**：生成能通过所有单元测试的补丁

与传统代码生成基准（如 HumanEval）不同，SWE-bench 测试的是**端到端的软件工程能力**，而非单函数编码。

### 1.3 用例结构

每个测试实例是一个 JSON 对象，核心字段如下：

```json
{
  "instance_id": "owner__repo-pr_number",
  "repo": "owner/repo",
  "base_commit": "commit_hash（PR 基于的 commit SHA）",
  "problem_statement": "GitHub Issue 的完整描述文本",
  "hints_text": "Issue 中的提示信息",
  "version": "仓库包版本号",
  "created_at": "PR 创建日期",
  "patch": "标准答案补丁（diff 格式，评估时不可见）",
  "test_patch": "测试套件补丁（diff 格式，包含新增/修改的测试）",
  "FAIL_TO_PASS": ["test_case_1", "test_case_2"],
  "PASS_TO_PASS": ["test_case_3", "test_case_4"]
}
```

**字段说明**：

| 字段                | 作用                                             |
| ------------------- | ------------------------------------------------ |
| `problem_statement` | 输入给模型的 Issue 描述                          |
| `base_commit`       | 模型需要 checkout 到的代码版本                   |
| `patch`             | Ground truth 补丁（评估时不给模型看）            |
| `test_patch`        | 包含此 PR 中新增/修改的测试用例                  |
| `FAIL_TO_PASS`      | 补丁前失败、补丁后应通过的测试（验证修复正确性） |
| `PASS_TO_PASS`      | 补丁前后均应通过的测试（验证未引入回归）         |

**模型输入**：代码库（checkout 到 `base_commit`）+ `problem_statement`
**模型输出**：一个 diff 格式的补丁

### 1.4 评测方式

SWE-bench 采用 **Docker 容器化确定性评测**，流程如下：

```
1. 环境准备：基于 base_commit 构建代码库环境（三层 Docker 镜像架构）
   ├── 基础镜像：通用依赖
   ├── 环境镜像：60+ 种 Python 版本/配置
   └── 实例镜像：每个任务的具体依赖

2. 补丁应用：将模型生成的预测补丁应用到代码库

3. 测试执行：运行 FAIL_TO_PASS + PASS_TO_PASS 测试套件

4. 结果判定：
   ├── Resolved：所有 FAIL_TO_PASS 通过 AND 所有 PASS_TO_PASS 通过
   ├── Breaking Resolved：FAIL_TO_PASS 通过但有 PASS_TO_PASS 失败
   ├── Partially Resolved：部分 FAIL_TO_PASS 通过
   ├── No-Op：补丁无实质修改
   └── Regression：引入新失败
```

**成功判定**：`% Resolved` = 完全解决的实例数 / 总实例数 × 100%

**三层 Docker 架构确保评估可重复性**，结果缓存按 `run_id` + `instance_id` 索引。

### 1.5 接入方式

```bash
# 1. 安装
pip install swebench

# 2. 加载数据集
python -c "from datasets import load_dataset; ds = load_dataset('princeton-nlp/SWE-bench_Verified', split='test')"

# 3. 验证安装（跑一个 gold 实例）
swebench eval verified --gold -i sympy__sympy-20590 --run-id validate-gold

# 4. 评估预测补丁
swebench eval verified -p <path_to_predictions> --run-id <run_id> -j <num_workers>

# 5. 查看结果
swebench report <run_id> -d verified
```

**资源要求**：x86_64 机器，≥120GB 磁盘空间，≥16GB RAM，≥8 CPU 核心
**云端选项**：sb-cli（AWS）、Modal（云端容器化评估）

**数据集下载**：

| 数据集               | HuggingFace                                                    |
| -------------------- | -------------------------------------------------------------- |
| SWE-bench Verified   | https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified   |
| SWE-bench Full       | https://huggingface.co/datasets/SWE-bench/SWE-bench            |
| SWE-bench Lite       | https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite       |
| SWE-bench Multimodal | https://huggingface.co/datasets/SWE-bench/SWE-bench_Multimodal |

### 1.6 已知 Leaderboard 分数

**mini-SWE-agent 统一 harness 排行榜**（2026-02，Verified 500 实例）：

| 排名 | 模型                               | % Resolved | Avg. $ | 日期       |
| ---- | ---------------------------------- | ---------- | ------ | ---------- |
| 1    | Claude 4.5 Opus (high reasoning)   | **76.80%** | $0.75  | 2026-02-17 |
| 2    | Gemini 3 Flash (high reasoning)    | 75.80%     | $0.36  | 2026-02-17 |
| 3    | MiniMax M2.5 (high reasoning)      | 75.80%     | $0.07  | 2026-02-17 |
| 4    | Claude Opus 4.6                    | 75.60%     | $0.55  | 2026-02-17 |
| 5    | GPT-5-2 Codex                      | 72.80%     | $0.45  | 2026-02-19 |
| 6    | GLM-5 (high reasoning)             | 72.80%     | $0.53  | 2026-02-17 |
| 7    | GPT-5-2 (high reasoning)           | 72.80%     | $0.47  | 2026-02-17 |
| 8    | Claude 4.5 Sonnet (high reasoning) | 71.40%     | $0.66  | 2026-02-17 |
| 9    | Kimi K2.5 (high reasoning)         | 70.80%     | $0.15  | 2026-02-17 |
| 10   | DeepSeek V3.2 (high reasoning)     | 70.00%     | $0.45  | 2026-02-17 |
| 11   | Gemini 3 Pro                       | 69.60%     | $0.96  | 2026-02-26 |
| 12   | Claude 4.5 Haiku (high reasoning)  | 66.60%     | $0.33  | 2026-02-17 |
| 13   | GPT-5 Mini                         | 56.20%     | $0.05  | 2026-02-17 |

**其他来源分数**（CSDN 2026-03，不同 harness）：

| 模型            | 分数  |
| --------------- | ----- |
| Claude Opus 4.5 | 80.9% |
| Claude Opus 4.6 | 80.8% |
| Gemini 3.1 Pro  | 80.6% |
| MiniMax M2.5    | 80.2% |
| GPT-5.2         | 80.0% |

**历史参考**：Devin（2024-03）= 13.86%；SWE-agent（2024-04）= 12.29%

### 1.7 与 FnixAgent 的适配性

**适配度：★★★★☆（高）**

| 适配点        | 分析                                                                   |
| ------------- | ---------------------------------------------------------------------- |
| **代码生成**  | FnixAgent 的 Craft 模式天然适配——给定代码库和 Issue 描述，生成修复补丁 |
| **终端命令**  | 终端模式可用于 git checkout、文件搜索、运行测试等操作                  |
| **文件操作**  | 可读取/修改代码文件，模拟真实开发流程                                  |
| **Plan 模式** | 可用于分解复杂 Issue，规划修改方案后再执行                             |

**适配建议**：

- **直接可用的用例**：500 个 Verified 实例中的 Python 仓库修复任务。将 `problem_statement` 作为用户输入，FnixAgent 通过文件操作 + 代码生成 + 终端命令完成修复
- **需要适配的部分**：SWE-bench 的评测依赖 Docker 容器化环境和完整的测试套件。FnixAgent 可集成 `swebench` CLI 工具作为评测后端
- **轻量化方案**：可先使用 SWE-bench Lite（300 实例）进行快速验证
- **限制**：所有实例均为 Python 项目；需要 Docker 环境（Tauri 桌面端可通过调用本地 Docker 实现）

---

## 2. GAIA

### 2.1 项目地址和规模

| 维度                 | 数据                                                                  |
| -------------------- | --------------------------------------------------------------------- |
| 原始 GitHub          | https://github.com/facebookresearch/gaia （已迁移/下线，返回 404）    |
| HuggingFace 数据集   | https://huggingface.co/datasets/gaia-benchmark/GAIA                   |
| 排行榜               | https://huggingface.co/spaces/gaia-benchmark/leaderboard              |
| 发布方               | Meta、HuggingFace、AutoGPT 联合发布                                   |
| **原版规模**         | **466 道多步骤问题**                                                  |
| 难度分级             | Level 1 / Level 2 / Level 3                                           |
| 公开验证集           | 165 道题（答案公开）                                                  |
| 私有测试集           | 301 道题（答案保密，用于维护排行榜）                                  |
| **GAIA 2（动态版）** | **800 个动态场景，10 个 universes**                                   |
| GAIA 2 仓库          | https://github.com/facebookresearch/meta-agents-research-environments |

### 2.2 测试维度

GAIA 评测**通用 AI 助手的综合能力**，覆盖：

- **多步骤推理**：复杂问题需要 5-30+ 步操作链
- **工具使用**：搜索引擎、计算器、代码解释器、文件解析等
- **多模态理解**：部分问题包含图片、PDF、音视频、Excel 等附件
- **网页操作**：动态环境导航、信息提取
- **自主决策**：在不给定步骤的情况下自主规划执行路径
- **精确回答**：最终输出需要与标准答案精确匹配

**难度分级标准**：

| 级别    | 步骤数  | 工具需求   | 描述                       |
| ------- | ------- | ---------- | -------------------------- |
| Level 1 | 1-5 步  | 0-1 个工具 | 优秀 LLM 可攻克            |
| Level 2 | 5-10 步 | 多工具组合 | 需要更强推理和工具协调     |
| Level 3 | 任意长  | 任意工具   | 近乎完美的通用助手才能完成 |

### 2.3 用例结构

GAIA 使用 `metadata.jsonl`（2025 年 10 月后改为 Parquet 格式）存储问题：

```json
{
  "task_id": "任务唯一标识符",
  "Question": "问题文本（自然语言描述的复杂任务）",
  "Level": "1/2/3（难度级别）",
  "Final answer": "标准答案（验证集公开，测试集保密）",
  "file_name": "附加文件名（如 xxx.pdf, xxx.xlsx，可为空）",
  "file_path": "附加文件路径",
  "Annotator Metadata": {
    "Tools": "推荐使用的工具列表",
    "Number of steps": "参考步骤数",
    "How long did this take?": "预计耗时",
    "Steps": "参考解决步骤"
  }
}
```

**Parquet 格式更新**（2025-10）：

- `metadata.parquet`：完整分割
- `metadata.level1.parquet` / `metadata.level2.parquet` / `metadata.level3.parquet`：按级别分割
- 列保持不变：`task_id`, `Question`, `Level`, `Final answer`, `file_name`, `file_path`, `Annotator Metadata`

**模型输入**：问题文本 + 可选附加文件
**模型输出**：最终答案文本（精确匹配验证）

### 2.4 评测方式

GAIA 采用**零样本评估 + 开放式回答 + 自动评分**：

```
1. 零样本输入：不给模型任何示例，直接输入问题
2. 开放式执行：模型可自主使用工具、搜索、计算等
3. 精确匹配验证：最终输出与标准答案精确匹配
   ├── 完全匹配 → 正确
   └── 不匹配 → 错误（无部分得分）
```

**评分指标**：`pass@1`（一次尝试的正确率），按 Level 分别统计

**注意**：GAIA 仅评估最终输出结果，不评估中间过程。精确匹配适合搜索类任务，但在格式灵活性上有局限。GAIA 2 通过动态环境改进了这一点。

### 2.5 接入方式

```python
# 1. 通过 HuggingFace datasets 加载
from datasets import load_dataset

# 加载验证集（公开答案）
ds = load_dataset("gaia-benchmark/GAIA", "2023_all", split="validation")

# 按级别加载
ds_l1 = load_dataset("gaia-benchmark/GAIA", "2023_level1", split="validation")
ds_l2 = load_dataset("gaia-benchmark/GAIA", "2023_level2", split="validation")
ds_l3 = load_dataset("gaia-benchmark/GAIA", "2023_level3", split="validation")

# 2. 访问附加文件
# 附加文件与 metadata 在同一文件夹，通过 file_name 字段引用
```

**提交排行榜**：将模型在测试集上的预测结果提交到 HuggingFace Leaderboard
**GAIA 2 使用**：克隆 `meta-agents-research-environments` 仓库，按文档配置动态环境

### 2.6 已知 Leaderboard 分数

**官方排行榜数据**（HuggingFace Leaderboard，pass@1）：

| 来源/Agent                   | Level 1 | Level 2 | Level 3 | 备注                                |
| ---------------------------- | ------- | ------- | ------- | ----------------------------------- |
| **人类**                     | **92%** | **92%** | **92%** | 参考基线                            |
| GPT-4 + Plugin（2024初）     | 15%     | —       | —       | 初始基线                            |
| OpenAI（官网数据）           | 62%     | 47%     | 32%     | pass@1                              |
| AI 最高分（2024末）          | —       | —       | —       | 65.1%（综合）                       |
| 昆仑万维 Skywork Super Agent | —       | —       | —       | 82.42%（验证集，排名第五，2025-05） |
| 中兴 Co-Sight 2.0            | —       | —       | —       | 84.39%（开源榜首位，2025-09）       |
| 京东 JoyAgent 3.0            | —       | —       | —       | 77%（验证集），67%+（测试集）       |

**注意**：

- OpenAI 官网宣传分数（74/69/47）被指出夸大，GAIA 官网实际为 62/47/32
- Manus 宣称的 86.5/70.1/57.7 在 GAIA 官网不存在（验证集和测试集均未找到）
- 2025-12 Meta 收购了 Manus 开发商蝴蝶效应

### 2.7 与 FnixAgent 的适配性

**适配度：★★★★★（非常高）**

| 适配点         | 分析                                                         |
| -------------- | ------------------------------------------------------------ |
| **Plan 模式**  | GAIA 的多步骤任务天然适配 Plan 模式——先分解任务再执行        |
| **Craft 模式** | 需要代码执行（计算、数据处理）的问题可用 Craft 模式          |
| **Ask 模式**   | 需要搜索和信息检索的问题可用 Ask 模式                        |
| **文件操作**   | GAIA 的附加文件（PDF、Excel、图片）需要文件解析能力          |
| **终端命令**   | 可运行 Python 脚本进行计算、数据处理                         |
| **工具组合**   | 多工具协调是 GAIA 的核心挑战，FnixAgent 的多模式切换天然适配 |

**适配建议**：

- **直接可用的用例**：165 道公开验证集题目，涵盖 Level 1-3
- **Level 1 优先**：先从简单的 1-5 步任务开始，验证 FnixAgent 的基础能力
- **附件处理**：需要增强 PDF/Excel/图片的解析能力
- **评测集成**：实现 GAIA 的精确匹配评分器，自动化评测流程
- **优势**：GAIA 不需要 Docker 环境，适合桌面端直接运行
- **限制**：测试集答案保密，无法本地评测；需联网搜索部分问题

---

## 3. MCP-Bench / MCP-Atlas

### 3.1 项目地址和规模

MCP（Model Context Protocol）协议评测有多个基准，以下分述：

#### 3.1.1 MCP-Bench（Accenture，主基准）

| 维度             | 数据                                               |
| ---------------- | -------------------------------------------------- |
| GitHub           | https://github.com/Accenture/mcp-bench             |
| 发布方           | Accenture（埃森哲）                                |
| 发表会议         | NeurIPS 2025 Workshop / ICLR 2026 Poster           |
| **MCP 服务器数** | **28 个**代表性实时服务器                          |
| **工具总数**     | **250 个**工具                                     |
| 覆盖领域         | 金融、旅行、科学计算、学术搜索、数据库、文件系统等 |

#### 3.1.2 MCP-Atlas（Scale AI）

| 维度             | 数据                         |
| ---------------- | ---------------------------- |
| 发布方           | Scale AI                     |
| 发布时间         | 2025-12-20                   |
| **MCP 服务器数** | **36 个**                    |
| **工具总数**     | **220 种**工具               |
| 每任务工具调用   | 3-6 次                       |
| GitHub           | 未找到公开仓库（截至调研时） |

#### 3.1.3 其他 MCP 相关基准

| 基准名         | GitHub                                           | 规模                                    | 特点                 |
| -------------- | ------------------------------------------------ | --------------------------------------- | -------------------- |
| MCPBench       | https://github.com/modelscope/MCPBench           | Web Search / Database Query / GAIA 三类 | 阿里 ModelScope 出品 |
| MCPToolBench++ | https://github.com/mcp-tool-bench/MCPToolBenchPP | 4k+ MCP Servers, 45+ 类别, 1509 实例    | 大规模工具发现       |
| MCPSecBench    | https://github.com/AIS2Lab/MCPSecBench           | 安全测试                                | MCP 安全性评测       |

### 3.2 测试维度

MCP-Bench 评测的核心能力：

- **工具发现**：从大量 MCP 工具中找到正确的工具
- **工具选择**：在多个相似工具中选择最合适的
- **参数构造**：正确构造工具调用参数
- **多工具协调**：串联多个工具调用完成复杂任务
- **结果理解**：理解工具返回结果并决定下一步
- **错误恢复**：工具调用失败时的自我修正

MCP-Atlas 额外评测：

- **工具搜索效率**：GPT-5.4 的工具搜索功能将 Token 使用量减少 47%
- **MCP 图谱理解**：理解工具间关系和依赖

### 3.3 用例结构

MCP-Bench 的任务结构：

```json
{
  "task_id": "任务唯一标识",
  "query": "用户自然语言请求",
  "available_servers": ["server_1", "server_2", "..."],
  "available_tools": [
    {
      "server": "server_name",
      "tool_name": "tool_name",
      "description": "工具描述",
      "parameters": {"param1": "type", "param2": "type"}
    }
  ],
  "expected_tool_calls": [
    {"tool": "tool_name", "parameters": {...}},
    {"tool": "tool_name", "parameters": {...}}
  ],
  "expected_output": "期望的最终结果",
  "category": "single_server / multi_server"
}
```

**两类评测**：

- **单服务器任务**：仅使用一个 MCP 服务器的工具
- **多服务器任务**：需要跨多个服务器协调工具调用

### 3.4 评测方式

MCP-Bench 采用 **LLM-as-Judge** 评测方式：

```
1. 模型接收 query + 可用工具列表
2. 模型自主选择工具、构造参数、执行调用
3. 收集模型的所有工具调用和最终输出
4. 使用 o4-mini 作为 Judge 评分：
   ├── 工具选择正确性
   ├── 参数构造正确性
   ├── 调用顺序正确性
   └── 最终结果正确性
5. 综合评分 0-1
```

**评分指标**：Overall Score = 单服务器平均分 + 多服务器平均分的加权

MCP-Atlas 额外评测：

- **覆盖率**：覆盖预设声明的比例
- **Token 效率**：完成任务所需的 Token 数

### 3.5 接入方式

```bash
# MCP-Bench (Accenture)
git clone https://github.com/Accenture/mcp-bench.git
cd mcp-bench
pip install -r requirements.txt

# 配置 MCP 服务器连接
# 编辑 config.yaml 指定 MCP 服务器地址

# 运行评测
python run_benchmark.py --model <model_name> --tasks all
```

**前提条件**：

- 需要运行 28 个实时 MCP 服务器（部分为远程服务）
- 需要 API Key 访问各 MCP 服务器
- Judge 模型需要 o4-mini API

### 3.6 已知 Leaderboard 分数

**MCP-Bench 排行榜**（Overall Score，o4-mini 为 Judge）：

| 排名 | 模型                 | Overall Score |
| ---- | -------------------- | ------------- |
| 1    | GPT-5                | **0.749**     |
| 2    | o3                   | 0.715         |
| 3    | gpt-oss-120b         | 0.692         |
| 4    | Gemini-2.5-Pro       | 0.690         |
| 5    | Claude-Sonnet-4      | 0.681         |
| 6    | Qwen3-235B-A22B-2507 | 0.678         |
| 7    | GLM-4.5              | 0.668         |
| 8    | gpt-oss-20b          | 0.654         |
| 9    | Kimi-K2              | 0.629         |
| 10   | GPT-4o               | 0.595         |
| 11   | GPT-4o-mini          | 0.557         |

**MCP 相关其他基准分数**（知乎表格，2025 年底模型对比）：

| 基准                   | Gemini 3 Pro | Claude Opus | Claude Sonnet | GPT-5 |
| ---------------------- | ------------ | ----------- | ------------- | ----- |
| MCP Universe Benchmark | 50.7         | —           | 46.5          | 47.9  |
| MCP Score Benchmark    | 43.1         | —           | 33.3          | 50.9  |
| MCP Atlas Benchmark    | —            | **62.3**    | 43.8          | —     |

### 3.7 与 FnixAgent 的适配性

**适配度：★★★☆☆（中等）**

| 适配点       | 分析                                           |
| ------------ | ---------------------------------------------- |
| **MCP 协议** | 若 FnixAgent 支持 MCP 协议接入工具，则直接可用 |
| **工具选择** | Craft 模式可适配工具选择和参数构造             |
| **终端命令** | 部分 MCP 服务器可通过终端调用                  |
| **文件操作** | 文件系统类 MCP 服务器天然适配                  |

**适配建议**：

- **前提**：FnixAgent 需要先实现 MCP 客户端协议，才能接入 MCP-Bench
- **子集适配**：可选取文件系统、代码执行类 MCP 服务器对应的任务子集
- **轻量化**：MCPBench（ModelScope）的 Web Search 类任务可作为入门
- **优势**：MCP-Bench 不需要 Docker 环境，适合桌面端
- **限制**：需要运行 28 个实时 MCP 服务器；Judge 模型需要 o4-mini API；MCP-Atlas 无公开仓库
- **长期价值**：MCP 协议正在成为 Agent 工具调用标准，适配 MCP-Bench 有战略意义

---

## 4. OSWorld

### 4.1 项目地址和规模

| 维度         | 数据                                     |
| ------------ | ---------------------------------------- |
| GitHub       | https://github.com/xlang-ai/OSWorld      |
| 官网         | https://os-world.github.io/              |
| 数据查看器   | https://os-world.github.io/explorer.html |
| OSWorld 2.0  | https://osworld-v2.xlang.ai/             |
| 论文         | https://arxiv.org/abs/2404.07972         |
| Star         | 3.1k                                     |
| Fork         | 521                                      |
| Commits      | 1,464                                    |
| 许可证       | Apache 2.0                               |
| 发表会议     | NeurIPS 2024                             |
| **任务总数** | **369 个**计算机任务                     |
| 支持 OS      | Ubuntu / Windows / macOS                 |
| 任务目录     | `evaluation_examples/`                   |

### 4.2 测试维度

OSWorld 评测**多模态智能体在真实计算机环境中的开放式任务执行能力**：

- **GUI 操作**：鼠标点击、键盘输入、拖拽、滚动
- **网页应用**：Chrome、Firefox 浏览器操作
- **桌面应用**：LibreOffice（Writer/Calc/Impress）、VS Code、GIMP、Terminal
- **OS 文件 I/O**：文件创建、修改、移动、权限管理
- **跨应用工作流**：从浏览器提取信息 → 写入文档 → 发送邮件
- **视觉理解**：截图理解、UI 元素定位
- **长链条规划**：多步骤任务执行（15+ 步）

**任务领域分类**：

| 类别         | 包含领域                        | 示例                 |
| ------------ | ------------------------------- | -------------------- |
| Office       | LibreOffice Writer/Calc/Impress | 格式化文档、创建图表 |
| Daily        | Chrome、Firefox、Thunderbird    | 网页搜索、邮件发送   |
| Professional | VS Code、GIMP、Terminal         | 代码编辑、图像处理   |

### 4.3 用例结构

OSWorld 的任务存储在 `evaluation_examples/` 目录下，按领域组织：

```
evaluation_examples/
├── test_all.json                    # 所有任务索引
├── libreoffice_impress/
│   ├── a669ef01-ded5-4099-9ea9-25e99b569840/
│   │   ├── config.json              # 任务配置
│   │   └── (任务相关文件)
├── google_chrome/
├── vscode/
├── gimp/
└── ...
```

**单个任务 config.json 结构**：

```json
{
  "id": "a669ef01-ded5-4099-9ea9-25e99b569840",
  "domain": "libreoffice_impress",
  "instruction": "在当前演示文稿的第3页后插入一张新幻灯片，标题为'季度总结'，使用'标题和内容'版式",
  "config": {
    "os_type": "Ubuntu",
    "files": ["path/to/initial_file.pptx"],
    "setup_script": "setup.sh"
  },
  "evaluator": {
    "func": "check_presentation",
    "expected": {
      "slide_count": 4,
      "slide_3_title": "季度总结",
      "slide_3_layout": "Title and Content"
    },
    "result_checker": "evaluator_script.py"
  }
}
```

**模型输入**：任务指令 + 虚拟机截图（或 accessibility tree）
**模型输出**：动作序列（pyautogui 命令 / 自定义动作空间）

### 4.4 评测方式

OSWorld 采用**真实虚拟机环境中的执行式评估**：

```
1. 环境初始化：
   ├── 启动 VMware/VirtualBox/Docker 虚拟机
   ├── 加载 Ubuntu/Windows/macOS 镜像
   └── 执行 setup_script 设置初始状态

2. Agent 执行：
   ├── 模型接收任务指令 + 截图/accessibility tree
   ├── 模型输出动作（click, type, scroll, hotkey 等）
   ├── 动作在虚拟机中真实执行
   ├── 截图反馈 → 模型 → 下一步动作
   └── 循环直到完成或达到最大步数（默认 15 步）

3. 结果评估：
   ├── 执行 evaluator 中的 result_checker
   ├── 检查虚拟机最终状态是否符合预期
   ├── Binary reward：完成/未完成
   └── Partial reward（OSWorld 2.0）：按完成步骤比例评分
```

**成功判定**：任务最终状态完全匹配预期条件 → 成功

**观测模式**：

- `screenshot`：纯截图模式（测试视觉理解）
- `a11y_tree`：无障碍树模式（测试结构化理解）
- `screenshot_a11y`：混合模式

### 4.5 接入方式

OSWorld 支持多种虚拟化后端：

```bash
# 1. 克隆仓库
git clone https://github.com/xlang-ai/OSWorld
cd OSWorld

# 2. 安装依赖
pip install -r requirements.txt
# 或仅安装环境
pip install desktop-env

# 3. 配置虚拟化后端（选其一）：
#    a) VMware Workstation Pro（桌面推荐）
vmrun -T ws list  # 验证安装

#    b) Docker（服务器推荐，需 KVM 支持）
egrep -c '(vmx|svm)' /proc/cpuinfo  # 检查 KVM

#    c) AWS（大规模并行评估）
#    d) Modal（云端 VM 沙箱）
pip install 'modal>=1.5.0'
modal setup

# 4. 快速验证
python quickstart.py

# 5. 运行评测
python run.py \
    --provider_name vmware \
    --path_to_vm "Ubuntu/Ubuntu.vmx" \
    --headless \
    --observation_type screenshot \
    --model gpt-4o \
    --max_steps 15 \
    --result_dir ./results

# 6. 查看结果
python show_result.py --detailed
```

**虚拟机凭据**：Ubuntu 用户名/密码 = `user` / `password`

### 4.6 已知 Leaderboard 分数

**OSWorld 1.0 排行榜演进**：

| 时间              | 最优模型/Agent             | 分数       | 备注     |
| ----------------- | -------------------------- | ---------- | -------- |
| 2024-04（发布时） | GPT-4o / Claude-3.5-Sonnet | 12.24%     | 初始基线 |
| —                 | **人类**                   | **72.36%** | 参考基线 |
| 2025年底          | 行业最优                   | 72.6%      | 追平人类 |
| 2026-05           | —                          | 83.6%      | 超越人类 |
| 2026-08           | 实在 Agent                 | **90.2%**  | 当前最优 |

**OSWorld 1.0 具体模型分数**（知乎表格）：

| 模型          | 分数  |
| ------------- | ----- |
| Claude Opus   | 66.3% |
| Claude Sonnet | 61.4% |

**OSWorld 2.0 分数**（长 horizon 真实任务，binary/partial reward）：

| 模型                    | Binary | Partial |
| ----------------------- | ------ | ------- |
| Claude Opus 4.8 (max)   | 20.6%  | 54.8%   |
| Claude Opus 4.7 (max)   | 18.2%  | 48.9%   |
| GPT-5.5 (xhigh)         | 13.9%  | 47.5%   |
| Claude Sonnet 4.6 (max) | 10.2%  | 41.5%   |

**OSWorld-Verified**（2025-07-28 发布的修正版）：

- 修复了社区报告的多个问题
- 支持 AWS 并行评估（可将评估时间缩短至 1 小时内）
- 重新运行了模型结果并更新到官网

### 4.7 与 FnixAgent 的适配性

**适配度：★★☆☆☆（较低）**

| 适配点       | 分析                                                               |
| ------------ | ------------------------------------------------------------------ |
| **终端命令** | OSWorld 中的 Terminal 任务可部分适配                               |
| **文件操作** | OS 文件 I/O 类任务与 FnixAgent 文件操作能力匹配                    |
| **代码生成** | VS Code 任务需要代码编辑能力                                       |
| **GUI 操作** | FnixAgent 作为 Tauri 桌面应用，**不具备**操作系统级 GUI 自动化能力 |
| **多模态**   | 需要 VLM 截图理解能力，FnixAgent 可能不具备                        |

**适配建议**：

- **不适合直接接入**：OSWorld 需要完整的虚拟机环境和 GUI 自动化能力，与 FnixAgent 的定位（AI 工作台）差距较大
- **可参考的子集**：仅选取 Terminal 类和文件 I/O 类任务（约 369 个任务中的 ~15%），改造为命令行可执行版本
- **替代方案**：将 OSWorld 的任务描述提取出来，改写为"给 FnixAgent 的指令"形式，在真实桌面环境而非虚拟机中执行
- **长期价值**：如果 FnixAgent 未来增加屏幕截图和 GUI 操作能力，OSWorld 可作为完整评测基准
- **限制**：需要 VMware/VirtualBox/Docker；需要 GUI 环境；Tauri 桌面应用难以直接控制其他应用的 GUI

---

## 5. FnixAgent 适配性综合分析

### 5.1 适配度总览

| 数据集                 | 适配度 | 核心匹配点                         | 主要限制                              |
| ---------------------- | ------ | ---------------------------------- | ------------------------------------- |
| **SWE-bench Verified** | ★★★★☆  | 代码生成 + 终端 + 文件操作         | 需 Docker 环境；仅 Python 项目        |
| **GAIA**               | ★★★★★  | Plan/Craft/Ask 三模式 + 多工具协调 | 测试集答案保密；需联网搜索            |
| **MCP-Bench**          | ★★★☆☆  | 工具选择 + 参数构造                | 需实现 MCP 客户端；需运行 28 个服务器 |
| **OSWorld**            | ★★☆☆☆  | 终端 + 文件操作（子集）            | 需虚拟机 + GUI 自动化；多模态需求     |

### 5.2 推荐接入优先级

**第一优先：GAIA（验证集）**

- 最匹配 FnixAgent 的多模式设计（Plan 分解 → Craft 执行 → Ask 检索）
- 165 道公开验证集，无需特殊环境
- 覆盖面广（搜索、计算、文件处理、多步骤推理）
- 可快速验证 FnixAgent 的核心能力

**第二优先：SWE-bench Lite**

- 300 个实例，比 Verified 更轻量
- 验证 FnixAgent 的代码修复能力
- 需要集成 Docker 评测后端
- 可先手动选取部分实例验证流程

**第三优先：MCP-Bench（子集）**

- 需要先实现 MCP 客户端协议
- 可从 MCPBench（ModelScope）的 Web Search 类任务开始
- 长期战略价值高（MCP 协议标准化趋势）

**第四优先：OSWorld（Terminal 子集）**

- 仅适配 Terminal 和文件 I/O 类任务
- 需要较大改造工作
- 可作为未来 GUI 能力增强后的完整评测基准

### 5.3 FnixAgent 三模式与数据集映射

| FnixAgent 模式 | 最适配的数据集             | 典型场景                       |
| -------------- | -------------------------- | ------------------------------ |
| **Craft**      | SWE-bench、GAIA（计算类）  | 代码生成、数据处理、脚本编写   |
| **Plan**       | GAIA（Level 2/3）、OSWorld | 多步骤任务分解、复杂工作流规划 |
| **Ask**        | GAIA（搜索类）、MCP-Bench  | 信息检索、工具调用、问答       |

### 5.4 技术接入建议

1. **统一评测框架**：为 FnixAgent 构建一个统一的 benchmark runner，支持加载不同数据集、执行任务、收集结果
2. **适配器模式**：为每个数据集实现一个 adapter，负责数据格式转换、环境准备、结果收集
3. **渐进式接入**：从 GAIA Level 1 开始，逐步增加难度和数据集覆盖
4. **本地化评测**：利用 FnixAgent 的桌面端优势，在真实环境中执行任务（而非虚拟机），降低环境复杂度

---

## 附录：关键参考链接

| 资源                  | 链接                                                                  |
| --------------------- | --------------------------------------------------------------------- |
| SWE-bench GitHub      | https://github.com/SWE-bench/SWE-bench                                |
| SWE-bench 排行榜      | https://www.swebench.com/                                             |
| GAIA HuggingFace      | https://huggingface.co/datasets/gaia-benchmark/GAIA                   |
| GAIA 排行榜           | https://huggingface.co/spaces/gaia-benchmark/leaderboard              |
| GAIA 2 (Meta ARE)     | https://github.com/facebookresearch/meta-agents-research-environments |
| MCP-Bench (Accenture) | https://github.com/Accenture/mcp-bench                                |
| MCPBench (ModelScope) | https://github.com/modelscope/MCPBench                                |
| MCPToolBench++        | https://github.com/mcp-tool-bench/MCPToolBenchPP                      |
| OSWorld GitHub        | https://github.com/xlang-ai/OSWorld                                   |
| OSWorld 官网          | https://os-world.github.io/                                           |
| OSWorld 2.0           | https://osworld-v2.xlang.ai/                                          |
| OSWorld 论文          | https://arxiv.org/abs/2404.07972                                      |

---

_本报告基于 2026-08-21 的公开信息调研编写。排行榜分数会随模型迭代持续更新，建议定期查阅各数据集官网获取最新数据。_
