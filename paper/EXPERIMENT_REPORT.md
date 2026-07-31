# FnixAgent 实验报告

> 面向项目作者，记录 FSE 2027 投稿配套实验的完整过程与结果。
> 生成日期：2026-08-01
> 论文目标：ACM FSE 2027（截稿 2026-10-02）

---

## 0. 数据真实性声明

本报告严格区分**真实数据**与 **mock / 占位数据**，以便作者判断哪些结果需要补强：

| 实验 | 数据性质 | 说明 |
|------|----------|------|
| exp1 — FCS 基准统计 | ✅ 真实数据 | 纯本地 dry-check，无 LLM 依赖，结果可直接引用 |
| exp2 — KTG Ablation | ⚠️ Mock 占位 | 检索指标为真实本地计算；任务分数为 `eval_mock.py` 占位 |
| exp3 — MFP×DAAO Ablation | ⚠️ Mock 占位 | 路由/MFP 指标为真实本地计算；任务分数为 `eval_mock.py` 占位 |
| exp4 — 纵向自进化 | ✅ 真实数据 | 纯本地模拟（seed=42），无 LLM 依赖，结果可复现且确定 |

> **关键提醒**：exp2/exp3 的 `task_score_avg` 当前为 mock 占位值（JSON 中 `placeholder: true`），
> **不可直接作为论文最终结论**。投稿前必须启动 `agentd` + LLM 运行真实实验覆盖这些数字。

---

## 1. 实验概述

本轮共运行 4 组实验，对应论文 Section 5，覆盖基准统计、消融、纵向演化三个层面：

| 实验 | 名称 | 方法 | 数据性质 | 论文章节 |
|------|------|------|----------|----------|
| exp1 | FCS 基准扩大与覆盖 | 1000 任务 dry-check 模式 | 真实 | Section 5.1 — Benchmark Scale-up & Coverage |
| exp2 | KTG 消融 | 4 配置（full_ktg / no_ktg / vector_rag / graph_rag_sim） | Mock 占位 | Section 5.2 — Knowledge Topology Graph Ablation |
| exp3 | MFP × DAAO 析因消融 | 2×2 析因（full / mfp_off / daao_off / both_off） | Mock 占位 | Section 5.3 — MFP & DAAO Factorial Ablation |
| exp4 | 纵向自进化模拟 | 模拟 1/7/30/90 天使用，12 任务/天 | 真实 | Section 5.4 — Longitudinal Self-Evolution |

实验编排脚本：`paper/experiments/run_all.py`（依次运行 exp1→exp4，单实验超时 30 分钟）。
Mock 评估脚本：`paper/reproduction/eval_mock.py`（为 exp2/exp3 生成结构一致的占位结果）。

---

## 2. 实验 1：FCS 基准统计分析（✅ 真实数据）

### 2.1 目的
扩大 Fnix Capability Suite（FCS）基准规模至 1000 任务，验证任务 schema 有效性、能力维度覆盖度与难度分布，为后续消融实验提供评测底座。

### 2.2 方法
- **模式**：dry-check（不调用 LLM，仅做 schema 校验与硬性通过预检）
- **任务来源**：9 个 seed 任务（人工编写）+ 991 个 generated 任务（模板生成）
- **基准根目录**：`E:\FNIX\FnixAgent\benchmarks\code`
- **脚本**：`paper/experiments/exp1_fcs_scale.py`

### 2.3 运行命令
```bash
python paper/experiments/exp1_fcs_scale.py
```

### 2.4 运行时间
约 672 秒（dry-check 1000 任务，CPU 密集型）。

### 2.5 结果

**总体规模**：
| 指标 | 值 |
|------|----|
| 总任务数 | 1000 |
| seed 任务 | 9 |
| generated 任务 | 991 |
| schema 有效任务 | 1000 |
| 无效任务 | 0 |
| 有效率 | **100.0%** |
| dry-check 样本 | 1000 |
| dry-check 硬性通过 | 331 |
| 有效通过率 | 33.1% |
| FCS 估算分 | 53.19 |

**10 能力维度分布**（`by_capability`）：
| 能力维度 | 任务数 |
|----------|--------|
| write | 830 |
| edit | 333 |
| multi_file | 332 |
| cli | 331 |
| bugfix | 168 |
| test_gen | 2 |
| api | 1 |
| search | 1 |
| refactor | 1 |
| heal | 1 |

**难度分布**（`by_difficulty`）：
| 难度 | 任务数 |
|------|--------|
| L1 | 498 |
| L2 | 169 |
| L3 | 333 |
| L4 | 0 |
| L5 | 0 |

**语言分布**：python 1000（当前基准全部为 Python，投稿前可考虑补充多语言以回应审稿人）。

### 2.6 数据文件
- `paper/experiments/results/exp1_fcs_stats.json` — 主结果
- `paper/figures/fcs_distribution.json` — 能力×难度分布矩阵（供绘图用）

### 2.7 论文引用
- Section 5.1 — Benchmark Scale-up & Coverage
- Table 1（基准统计表）

### 2.8 关键发现
- 1000 任务 schema 验证 100% 通过，证明任务生成管道健壮。
- 能力维度覆盖 10 维，但分布不均衡（write 占 83%，部分维度仅 1 个任务）——这是投稿前需要向审稿人解释的弱点，或补充任务以平衡分布。
- 难度集中在 L1-L3，L4/L5 为空，论文中需说明难度分级策略。

---

## 3. 实验 2：KTG Ablation（⚠️ Mock 占位）

### 3.1 目的
对比 4 种检索配置在 FCS 任务上的表现，验证知识拓扑图（KTG）相对于 Vector RAG / GraphRAG / 无检索的优势。

### 3.2 方法
- **配置**：`full_ktg` / `no_ktg` / `vector_rag` / `graph_rag_sim`
- **任务集**：9 个 seed 任务
- **当前状态**：`agentd` 未运行，`agentd_reachable: false`，`mock_llm: true`
- **脚本**：`paper/experiments/exp2_ktg_ablation.py`

### 3.3 运行命令
```bash
# 本地检索指标（无 agentd，任务分数为 null）
python paper/experiments/exp2_ktg_ablation.py --no-agent

# Mock 占位分数（结构一致，分数为 placeholder）
python paper/reproduction/eval_mock.py

# 真实运行（需启动 agentd + LLM API Key）
python -m fnixagent
python paper/experiments/exp2_ktg_ablation.py --base http://127.0.0.1:8003
```

### 3.4 当前结果（Mock 占位，`placeholder: true`）

**检索指标（真实本地计算）**：
| 配置 | 检索命中率 | 平均路径数/查询 | 平均延迟(ms) |
|------|-----------|----------------|-------------|
| full_ktg | 100.0% | 2.6 | 1.35 |
| vector_rag | 77.8% | 1.9 | 0.82 |
| graph_rag_sim | 66.7% | 1.4 | 1.91 |
| no_ktg | 0.0% | 0.0 | 0.04 |

**任务分数（Mock 占位，非科学结果）**：
| 配置 | task_score_avg | correctness_avg | completeness_avg | hard_pass_rate |
|------|----------------|-----------------|-------------------|----------------|
| full_ktg | **0.857** (85.7%) | 0.864 | 0.826 | 100.0% |
| vector_rag | 0.712 (71.2%) | 0.721 | 0.691 | 100.0% |
| graph_rag_sim | 0.652 (65.2%) | 0.657 | 0.626 | 0.0% |
| no_ktg | 0.520 (52.0%) | 0.531 | 0.491 | 0.0% |

**排序**：full_ktg (85.7) > vector_rag (71.2) > graph_rag_sim (65.2) > no_ktg (52.0)

> ⚠️ **注意**：上述任务分数由 `eval_mock.py` 生成，JSON 中每条记录均标记 `placeholder: true`。
> 检索指标（hit_rate / latency）是真实本地计算，可直接引用；任务分数**不可直接引用**。

### 3.5 数据文件
- `paper/experiments/results/exp2_ktg_ablation.json` — 本地运行结果（任务分数为 null）
- `paper/experiments/results/mock_ablation_results.json` — Mock 占位结果（含 placeholder 分数）

### 3.6 论文引用
- Section 5.2 — Knowledge Topology Graph Ablation

### 3.7 待办
- [ ] 启动 `agentd`（`python -m fnixagent`，端口 8003）
- [ ] 配置 BYOK API Key（OpenAI / Qwen / DeepSeek / GLM 任选其一，见 `.env`）
- [ ] 运行 `python paper/experiments/exp2_ktg_ablation.py --base http://127.0.0.1:8003` 获取真实任务分数
- [ ] 用真实数据替换论文 Table 与 mock 占位值
- [ ] 补充与 SWE-agent / OpenHands 的直接对比（当前缺失）

---

## 4. 实验 3：MFP × DAAO 析因消融（⚠️ Mock 占位）

### 4.1 目的
通过 2×2 析因设计（MFP 开/关 × DAAO 开/关，KTG 始终开启），验证自进化飞轮（MFP）与动态自适应编排（DAAO）各自的贡献及协同效应。

### 4.2 方法
- **设计**：2×2 析因
- **配置**：`full`（MFP+DAAO 全开）/ `mfp_off` / `daao_off` / `both_off`
- **任务集**：9 个 seed 任务
- **当前状态**：`agentd` 未运行，`mock_llm: true`
- **脚本**：`paper/experiments/exp3_mfp_daao_ablation.py`

### 4.3 运行命令
```bash
# 本地路由/MFP 指标（无 agentd，任务分数为 null）
python paper/experiments/exp3_mfp_daao_ablation.py --no-agent

# Mock 占位分数
python paper/reproduction/eval_mock.py

# 真实运行
python -m fnixagent
python paper/experiments/exp3_mfp_daao_ablation.py --base http://127.0.0.1:8003
```

### 4.4 当前结果（Mock 占位，`placeholder: true`）

**路由指标（真实本地计算）**：
| 配置 | avg_max_steps | 模式分布 | MFP 固化范式数 |
|------|---------------|----------|----------------|
| full | 14.2 | react:6 / plan_execute:3 | 2 |
| mfp_off | 14.2 | react:6 / plan_execute:3 | 0 |
| daao_off | 16.0 | react:9 | 2 |
| both_off | 16.0 | react:9 | 0 |

**任务分数（Mock 占位，非科学结果）**：
| 配置 | task_score_avg | hard_pass_rate | avg_heal_rounds | avg_steps |
|------|----------------|----------------|-----------------|-----------|
| full | **0.839** (83.9%) | 100.0% | 1.00 | 11.33 |
| daao_off | 0.735 (73.5%) | 100.0% | 1.11 | 12.67 |
| mfp_off | 0.691 (69.1%) | 11.11% | 1.00 | 13.00 |
| both_off | 0.581 (58.1%) | 0.0% | 1.22 | 14.11 |

**排序**：full (83.9) > daao_off (73.5) > mfp_off (69.1) > both_off (58.1)

**自进化增益**：
- `self_evolution_gain = 0.258`（即 full 相对 both_off 提升 25.8 个百分点，+25.8%）
- full (0.839) − both_off (0.581) = 0.258

> ⚠️ **注意**：任务分数与自进化增益均为 mock 占位值（`placeholder: true`）。
> 路由指标（avg_max_steps / mode_distribution）与 MFP 指标（patterns_solidified）是真实本地计算，可直接引用。

### 4.5 数据文件
- `paper/experiments/results/exp3_ablation.json` — 本地运行结果（任务分数为 null）
- `paper/experiments/results/mock_ablation_results.json` — Mock 占位结果（含 placeholder 分数）

### 4.6 论文引用
- Section 5.3 — MFP & DAAO Factorial Ablation

### 4.7 待办
- [ ] 启动 `agentd` + 配置 API Key
- [ ] 运行 `python paper/experiments/exp3_mfp_daao_ablation.py --base http://127.0.0.1:8003` 获取真实分数
- [ ] 用真实数据替换论文 Table 与 mock 占位值
- [ ] 验证 full > daao_off > mfp_off > both_off 的排序是否在真实运行中保持

---

## 5. 实验 4：纵向自进化模拟（✅ 真实数据）

### 5.1 目的
模拟同一用户在 1/7/30/90 天使用后，知识拓扑图（KTG）节点数、固化范式数、检索命中率与延迟的变化趋势，验证 MFP 爬坡进化阶段的长期收敛性与知识固化效果。

### 5.2 方法
- **模拟时间跨度**：1 / 7 / 30 / 90 天
- **任务强度**：12 任务/天
- **高频范式种子**：6 个（fibonacci、pytest 测试、修语法错、重构提取、CLI 问候、计算器）
- **随机种子**：42（结果可复现，两次运行 diff 应为空）
- **驱动方式**：注入模拟 TraceRecord 序列，驱动 KTG/MFP 权重演化（无 LLM）
- **脚本**：`paper/experiments/exp4_longitudinal.py`

### 5.3 运行命令
```bash
python paper/experiments/exp4_longitudinal.py --seed 42

# 可复现性校验（两次运行 diff 应为空）
python paper/experiments/exp4_longitudinal.py --seed 42
diff /tmp/run1.json paper/experiments/results/exp4_longitudinal.json
```

### 5.4 结果

**纵向演化趋势**：
| 时间跨度 | 模拟任务数 | 进化轮次 | 初始节点 | 最终节点 | L3 规则节点 | 固化范式 | 检索命中率 | 平均延迟(ms) |
|----------|-----------|---------|---------|---------|------------|----------|-----------|-------------|
| 1 天 | 12 | 1 | 17 | 18 | 6→7 | 0→1 | 33.33% | 0.188 |
| 7 天 | 84 | 1 | 17 | 23 | 6→12 | 0→6 | 33.33% | 0.022 |
| 30 天 | 360 | 4 | 17 | 23 | 6→12 | 0→6 | 33.33% | 0.021 |
| 90 天 | 1080 | 11 | 17 | 23 | 6→12 | 0→6 | 33.33% | 0.024 |

**初始拓扑**（所有 horizon 共享）：
- total_nodes: 17, active_nodes: 17, l3_rule_nodes: 6, solidified_patterns: 0, active_edges: 16

### 5.5 关键发现
1. **拓扑快速增长期在 1-7 天**：节点 17→23（+6），范式 0→6（全部固化），L3 规则节点 6→12（翻倍）。
2. **7 天后拓扑趋于稳定**：7/30/90 天的最终节点数均为 23，固化范式均为 6，说明 MFP 爬坡进化在 7 天内完成主要知识固化，之后进入收敛平台期。
3. **检索延迟亚毫秒级**：稳定后检索延迟稳定在 0.02ms 左右（0.021-0.024ms），证明 KTG 检索在节点增长后仍保持低延迟。
4. **检索命中率 33.33%**：6 个 pattern seeds 中 2 个可被检索命中（2/6=33.33%）。该命中率在所有 horizon 保持一致，说明命中主要由 pattern seeds 与拓扑匹配决定，而非规模。
5. **可复现性**：seed=42，结果确定性，两次运行 diff 为空。

> 注：命中率 33.33% 偏低，论文中需解释这是模拟环境下 pattern seeds 与拓扑冷启动匹配的局限，而非真实使用场景的表现。投稿前可考虑补充真实使用数据。

### 5.6 数据文件
- `paper/experiments/results/exp4_longitudinal.json` — 主结果（含 4 个 horizon 的完整 initial/final/delta 数据）

### 5.7 论文引用
- Section 5.4 — Longitudinal Self-Evolution
- Figure 3（`figures/longitudinal.pdf`：KTG 节点数与 L3 规则随时间变化曲线，节点 17→23、规则 0→6 后趋于平台）

---

## 6. Mock 评估结果汇总

由 `paper/reproduction/eval_mock.py`（`FNIX_MOCK_LLM=1`）生成，供无 API Key 的审稿人复现实验结构。所有任务分数均标记 `placeholder: true`，**不是科学结论**。

### 6.1 运行命令
```bash
# 设置 mock 模式
# Linux/macOS: export FNIX_MOCK_LLM=1
# Windows PowerShell: $env:FNIX_MOCK_LLM="1"

python paper/reproduction/eval_mock.py
```

### 6.2 输出文件
`paper/experiments/results/mock_ablation_results.json`，包含：
- `exp2_ktg_ablation`：4 配置检索指标 + 9 任务×4 配置的逐任务分数
- `exp3_mfp_daao_ablation`：4 配置路由/MFP 指标 + summary
- `seed_tasks`：9 个 seed 任务 ID 列表

### 6.3 确定性
Mock 结果跨运行确定（diff 为空），可复现。

### 6.4 Seed 任务清单
```
seed.api.health, seed.bugfix.subtract, seed.cli.greet,
seed.heal.syntax_error, seed.multi.calc_package, seed.refactor.extract_parse,
seed.search.fix_helper, seed.test_gen.counter, seed.write.fibonacci
```

---

## 7. 待补强实验清单

以下实验在投稿前需要完成，以应对审稿人质疑：

### 7.1 高优先级（必做）
- [ ] **exp2 真实 LLM 运行**：启动 `agentd` + 配置 BYOK API Key，运行 `exp2_ktg_ablation.py --base http://127.0.0.1:8003`，用真实任务分数替换 mock 占位值。
- [ ] **exp3 真实 LLM 运行**：同上，运行 `exp3_mfp_daao_ablation.py --base http://127.0.0.1:8003`。
- [ ] **KTG vs GraphRAG 对比强化**：当前 `graph_rag_sim` 为模拟配置，需接入真实 GraphRAG 实现做对比，避免审稿人质疑对比公平性。
- [ ] **MFP vs EvolveR 对比讨论**：论文需补充与 EvolveR 类方法的定性/定量对比。

### 7.2 中优先级（强烈建议）
- [ ] **与 SWE-agent / OpenHands 直接对比**：在 SWE-bench（或 FCS 子集）上跑 baseline，提供 head-to-head 数据。当前论文缺失此对比，是明显弱点。
- [ ] **FCS 第三方标注一致性**：引入第三方标注者对 FCS 任务做 inter-annotator agreement（如 Cohen's κ），证明基准标注质量。
- [ ] **User Study**：至少 10 用户、1 周使用，收集真实使用数据（任务完成率、KTG 增长、用户满意度），弥补 exp4 纯模拟的局限。

### 7.3 低优先级（若时间允许）
- [ ] 多语言基准（当前 FCS 全为 Python，补充 Java/TS）
- [ ] 更长时间跨度模拟（180 天/365 天），验证长期收敛性
- [ ] 不同 LLM 后端的消融（OpenAI vs Qwen vs DeepSeek vs GLM）

---

## 8. 数据文件索引

所有实验结果存放于 `paper/experiments/results/` 与 `paper/figures/`：

| 文件路径 | 产生脚本 | 实验对应 | 数据性质 | LLM 依赖 |
|----------|----------|----------|----------|----------|
| `paper/experiments/results/exp1_fcs_stats.json` | `exp1_fcs_scale.py` | exp1 | ✅ 真实 | 否 |
| `paper/experiments/results/exp2_ktg_ablation.json` | `exp2_ktg_ablation.py --no-agent` | exp2 | ⚠️ 检索真实/分数 null | 检索:否; 分数:是 |
| `paper/experiments/results/exp3_ablation.json` | `exp3_mfp_daao_ablation.py --no-agent` | exp3 | ⚠️ 路由真实/分数 null | 路由:否; 分数:是 |
| `paper/experiments/results/exp4_longitudinal.json` | `exp4_longitudinal.py` | exp4 | ✅ 真实 | 否 |
| `paper/experiments/results/all_results.json` | `run_all.py` | 全部汇总 | 混合 | — |
| `paper/experiments/results/mock_ablation_results.json` | `eval_mock.py` | exp2+exp3 mock | ⚠️ Mock 占位 | 否(mock) |
| `paper/figures/fcs_distribution.json` | `exp1_fcs_scale.py` | exp1 绘图数据 | ✅ 真实 | 否 |

### 时间戳记录
- exp4 生成时间：`2026-08-01T05:30:27`
- exp1 生成时间：`2026-08-01T05:55:53`
- mock_ablation 生成时间：`2026-08-01T06:18:06`

---

## 9. 一键复现命令

```bash
# 完整流程（mock 模式，无 API Key）
# Linux/macOS
export FNIX_MOCK_LLM=1
python paper/experiments/run_all.py              # exp1→exp4，exp2/exp3 降级为占位
python paper/reproduction/eval_mock.py           # 生成 mock 占位分数

# Windows PowerShell
$env:FNIX_MOCK_LLM="1"
python paper/experiments/run_all.py
python paper/reproduction/eval_mock.py

# 仅运行无 LLM 实验（exp1 + exp4）
python paper/experiments/run_all.py --skip exp2 exp3

# Docker 一键复现
cd paper/reproduction
docker compose build
docker compose run repro
```

结果输出目录：`paper/experiments/results/`
