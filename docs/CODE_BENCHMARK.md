# Fnix Code Benchmark（FCS）— 千级工程任务评估

## 目标

用 **~1000 个可重复、可自动判分的写码工程任务**，系统测量 Fnix Code Agent 在真实仓库场景下的能力，并输出 **Fnix Code Score（FCS）** 与分维度雷达，用于迭代优化。

对标思路：OfficeBench 声明式 checks + SpreadsheetBench 多用例 + HumanEval/SWE-bench 的「任务→验收」闭环，但覆盖 **read / write / edit / search / test / heal / multi-file / git** 全链路。

## 能力维度（10 轴 × 5 难度 ≈ 1000 任务）

| 能力 ID | 说明 | 典型验收 |
|---------|------|----------|
| `write` | 新建模块/文件 | file_exists + compile + pytest |
| `edit` | 精准替换/修 bug | file_contains + pytest |
| `bugfix` | 从失败测试修复 | pytest 先 fail 后 pass |
| `test_gen` | 补测试 | coverage / pytest 新增用例 |
| `refactor` | 重命名/抽函数 | 行为不变 + pytest |
| `search` | 先 search 再改 | 改对文件 |
| `multi_file` | 跨文件特性 | 多 path checks |
| `api` | FastAPI/Flask 端点 | httpx / pytest |
| `cli` | argparse/click | stdout_equals |
| `heal` | 编译/测试失败后自愈 | heal_rounds + 最终 pass |

**难度 L1–L5**：单文件 ≤30 行 → 多模块 → 跨目录 → 需 search → 需 2+ heal 轮。

## 任务 JSON Schema

见 [`benchmarks/code/schema/task.schema.json`](../benchmarks/code/schema/task.schema.json)。

核心字段：`id`, `prompt`, `capability[]`, `difficulty`, `language`, `setup`, `checks[]`, `timeout_s`, `tags[]`。

## 评分（单任务 0–100）

```
task_score = 0.50 * correctness + 0.20 * completeness + 0.15 * process + 0.10 * safety + 0.05 * speed
```

| 子分 | 含义 |
|------|------|
| **correctness** | 所有 `required: true` checks 通过 → 100，否则 0（可配置 partial） |
| **completeness** | 可选 checks 加权通过率 |
| **process** | 步数/工具调用在预算内；多余 heal 扣分 |
| **safety** | 无 stub 写入、无越界路径、preview 可 Accept |
| **speed** | `elapsed <= timeout_s` 满分，超时线性衰减 |

**Hard pass**：correctness = 100 且 safety ≥ 80。

## 总分 FCS

```
FCS = Σ (task_score × difficulty_weight) / Σ difficulty_weight
difficulty_weight: L1=1, L2=1.2, L3=1.5, L4=2, L5=2.5
```

分报告：`reports/fcs-{date}.md` + `reports/fcs-{date}.json`（按 capability / difficulty 聚合）。

## 目录

```
benchmarks/code/
  schema/task.schema.json
  manifest.json              # 1000 任务索引（generator 产出）
  seed/                      # 人工精选 ~40
  generated/                 # 模板生成 ~960
  templates/                 # 生成器模板

src/fnixagent/core/code/benchmark/
  schema.py checks.py runner.py scorer.py generator.py report.py

scripts/
  generate-code-tasks.py     # 生成 manifest + generated/
  run-code-benchmark.py      # 跑 N 任务并出分
```

## 运行

```bash
# 1. 生成 1000 任务清单（首次）
python scripts/generate-code-tasks.py --count 1000

# 2. 离线判分（仅 checks，不调用 LLM）— 验证任务包
python scripts/run-code-benchmark.py --dry-checks --limit 50

# 3. 对 agentd 跑 benchmark（需 API + agentd）
python scripts/run-code-benchmark.py --base http://127.0.0.1:8003 --limit 20 --tag smoke

# 4. 全量（耗时数小时，建议 CI nightly）
python scripts/run-code-benchmark.py --limit 1000 --parallel 4
```

## 优化闭环

1. **按 capability 最低分** → 补 prompt / heal / tools
2. **process 低** → 减无效 search、加强 plan
3. **safety 低** → stub 规则、preview 强制
4. **regression** → manifest 锁定 seed 子集为 CI gate（≥40 任务）

## 与现有测试关系

| 现有 | FCS 关系 |
|------|----------|
| `tests/test_coding_e2e.py` | 单元/集成冒烟 |
| `scripts/e2e-code-projects.py` | 2 个 live agent 场景 → 升级为 `bugfix`/`multi_file` seed |
| `BenchmarkRunner.ts` | Code Review 准确率；FCS 管 **写码交付** |

## 全链路测试（前端触发）

从 Workbench **Composer** 或 **Settings → Diagnostics** 一键跑系统级基准：

| 入口 | 说明 |
|------|------|
| Composer | `/benchmark` · `全链路测试` |
| 侧栏 | **System test** |
| Settings | Diagnostics → 打开全链路测试面板 |

### 测试阶段

| 阶段 | 层 |
|------|-----|
| `frontend.ping` / `frontend.harness` | 浏览器 → agentd |
| `infra.health` / `infra.harness_status` | agentd 进程 |
| `work.engine` | Work 流水线 |
| `harness.workspace` / `harness.config` | ~/.fnix + BYOK |
| `code.apply` / `code.sessions` | DiffEngine + session |
| `fcs.manifest` 或 `fcs.smoke` | 千级任务包 / LLM 冒烟 |
| `llm.connectivity` | 可选 LLM ping |

### API

```
POST /api/v1/benchmark/run   # NDJSON: stage | done
GET  /api/v1/benchmark/suites
```

请求体：`{ include_llm, fcs_limit, fcs_tag, workspace, client_stages[] }`

响应 `done.report`：`overall_score`, `by_category`, `recommendations`, `fcs`

### 优化

面板底部 **优化建议** 按失败阶段与低分维度给出下一步（修 agentd、补 API Key、跑 FCS 等）。
