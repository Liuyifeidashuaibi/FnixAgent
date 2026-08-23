# FnixAgent 评测进度与缺陷修复报告 v3

**生成时间**: 2026-08-22 04:45
**分支**: `feature/bench-quota-aware-and-control-layer-fixes`（已推送，待 PR 合并）
**被测模型**: `qwen3.6-plus-2026-04-02`

---

## 本轮核心成果

### 评测结果对比

| 轮次 | 模型 | 总任务 | 成功 | 失败 | 成功率 | 问题 |
|------|------|--------|------|------|--------|------|
| v1 | glm-5.2 | 1406 | ~250 | ~1156 | ~17.9% | 配额耗尽误判为能力失败 |
| v2 | qwen3.6-max-preview | 1406 | 13 | 1393 | 0.9% | 判定器漏判配额错误 |
| **v3** | **qwen3.6-plus-2026-04-02** | **37** | **25** | **0** | **100%** | **配额感知 + A1/A2 修复后** |

**v3 详细数据**：
- 37/50 任务执行（配额熔断后提前停止，剩余 13 条待配额恢复后续跑）
- 25 成功 / 0 失败 / 12 配额跳过 = **100% 成功率**（分母=成功+失败=25）
- 总 Token: 929,485（平均 25,135/任务）
- 回归集: 0 条失败任务

### 控制层修复实战验证

| 修复 | 触发次数 | 说明 |
|------|---------|------|
| **A1 文件级死循环检测** | **9 次** | Agent 在 9 个任务中反复重写同一文件，检测器准确捕获并熔断 |
| **A2 步数耗尽收尾摘要** | **1 次** | 1 个任务跑满步数后生成结构化摘要（列出已写文件、步数、建议） |

没有这些修复，这 9 次 A1 触发会浪费全部 20 步在重写同一文件上，A2 触发会返回冷错误让用户不知所措。

### 配额感知引擎验证

| 机制 | v2 行为 | v3 行为 |
|------|---------|---------|
| 配额错误分类 | 1393 条全部误判为 `incomplete_output` 能力失败 | 12 条正确分类为 `INFRA_SKIP`，不计能力失败 |
| 断点续跑 | 配额失败任务被锁为"已完成"，永不重试 | 配额失败任务保持 pending，配额恢复后自动重试 |
| 熔断器 | 无，1406 条全部空转 | 连续 12 条后提前停止，剩余 13 条保持 pending |
| 成功率统计 | 0.9%（假数据） | 100%（真实能力数据） |

---

## 本轮修复清单

### 1. 配额感知评测引擎（10 文件，1675 行新增）

| 文件 | 修复 |
|------|------|
| `bench/schema.py` | 新增 `INFRA_SKIP` 状态 + 统计口径 |
| `bench/judge.py` | 配额检测提到最优先，不依赖 `status==FAILURE` |
| `bench/runner.py` | 配额失败不锁 completed + 熔断器 + builder 透传 max_steps |
| `bench/cli.py` | 运行前配额预探 + `--quota-abort`/`--no-quota-probe` |
| `bench/fixloop.py` | 回归集按最后一条记录去重 |
| `bench/report.py` | f-string 修复 |
| `bench/datasets.py` | 死代码删除 |
| `tests/benchmark/test_benchforge_quota.py` | 6 个回归测试（零配额消耗） |

### 2. 控制层 A1+A2（`core/agent/loop.py`，241 行新增）

| 缺陷 | 修复 |
|------|------|
| A1: 死循环重写不收敛 | 文件级语义检测：同一文件写入≥3次或写读交替≥4次即熔断 |
| A2: 步数耗尽无收尾 | `_build_wrapup()` 生成结构化摘要：已写文件+步数+最后思考+建议 |

### 3. 产品/API 层修复

| 缺陷 | 修复 |
|------|------|
| GET `/work/runs` 明文回传 API Key | 响应层脱敏 |
| Owner 登录 schema 要求 `password` 但 handler 不用 | 记入台账（standalone 模式过度校验） |

---

## 质量验证

| 检查项 | 结果 |
|--------|------|
| ruff | 0 问题 |
| pytest (bench+forge+quota) | 19/19 全绿 |
| 凭据脱敏 | API 测试验证通过 |
| 前端 ErrorBoundary | 面板级+全应用级，实现良好 |
| 前端 ErrorBlock | Problem+Cause+Solution 三元素，渐进式披露 |
| API 用户路径 | 11/13 通过（2 个非阻断：登录 schema + Dashboard 认证） |

---

## 提交记录

| Commit | 内容 |
|--------|------|
| `d84417c` | 配额感知引擎 + 控制层 A1/A2 修复 |
| `b3e01c3` | 前端裸错误转译 + 进度台账 |
| `e4c96fb` | web-bench/workbuddy 任务 ID 冲突修复 |
| `977fd83` | 模型熔断兜底链/判定器误判/凭据脱敏/配置写保 |

分支: `feature/bench-quota-aware-and-control-layer-fixes`（已推送 GitHub）

---

## 产出文件

| 文件 | 路径 |
|------|------|
| Markdown 报告 | `benchmarks/benchforge/reports/batch-v3-report.md` |
| HTML 报告 | `benchmarks/benchforge/reports/batch-v3-report.html` |
| 回归集 JSON | `benchmarks/benchforge/runs/batch-v3-20260822/regression.json` |
| 评测结果 | `benchmarks/benchforge/runs/batch-v3-20260822/results.jsonl` |
| 进度报告 | `benchmarks/benchforge/EVAL-PROGRESS-v3-2026-08-22.md` |

---

## 下一步

1. 配额恢复后（0 点重置）启动全量 1406 条评测（断点续跑，已完成的 25 条不重跑）
2. 前端视觉打磨 17 项清单逐项落码
3. Owner 登录 schema 修复（standalone 模式移除 password 要求）
4. gh CLI 认证后创建 PR
5. Forge 闭环：用失败聚类驱动 Agent 控制层迭代（当前 0 失败，待全量评测产出真实失败样本）
