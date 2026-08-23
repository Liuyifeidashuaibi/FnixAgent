# FnixAgent 评测进度与产品成熟化台账 — v4（2026-08-22）

## 评测结果总览

| 批次 | 模型 | 执行 | 成功 | 失败 | infra_skip | 成功率 | 说明 |
|---|---|---|---|---|---|---|---|
| v1 | glm-5.2 | 1406 | ~250 | ~1156 | 0 | ~17.9% | 配额耗尽误判为能力失败 |
| v2 | qwen3.6-max-preview | 1406 | 13 | 1393 | 0 | 0.9% | 判定器漏判配额错误 |
| v3 | qwen3.6-plus-2026-04-02 | 37 | 25 | 0 | 12 | 100% | 配额感知+A1/A2 修复后 |
| v4 | qwen3.7-max-2026-05-17 | 60 | 46 | 6 | 8 | 88.5% | 含 4 条 429 误判（B7 已修） |

**v4 修正后（B7 重判）**：真实能力失败 2 条（bom--task-8 死循环、calculator--task-9 工具错误），
均为 B5/B6 修复前的次生症状。**真实成功率 46/48 = 95.8%**。

## 本轮修复（B5-B7，控制层）

### B5 — 工具幂等缓存工作区串号（重大）
- **现象**：web-bench 并发任务中 task-8 的 `ls` 输出指向 task-7 的工作区目录
- **根因**：`ToolPolicy` 全局单例幂等缓存（key=sha256(tool+args)，TTL 120s），只读工具 `ls({})`
  结果含绝对路径被缓存；task-7 执行后 task-8 相同调用命中缓存，拿到错误目录内容
- **修复**：
  - `should_cache_result()`：READ 类工具不写缓存、不读缓存（结果上下文相关）
  - `ls`/`ll` 风险分类修正为 READ（原默认 WRITE 导致参与缓存）
  - `remember_success(tool_name)` 双保险拦截
- **验证**：`tests/benchmark/test_tool_policy_read_cache.py` 9 条全绿

### B6 — web-bench 项目级工作区隔离错误
- **现象**：calculator--task-N 找不到 init 创建的基础文件，glob 全空
- **根因**：web-bench 每项目 20 任务有顺序依赖（init 建文件→task-N 修改），
  runner 却给每任务独立空工作区
- **修复**：`_PROJECT_SHARED_DATASETS={"web-bench"}` 同项目共享工作区目录
  （文件级继承，对话上下文仍独立）+ 项目内串行锁 + init 优先排序
- **验证**：`tests/benchmark/test_bench_project_workspace.py` 5 条全绿

### B7 — 判定器漏判 HTTP 429 限流
- **现象**：4 条 HTTP 429 限流任务被误判为 incomplete_output 能力失败
- **根因**：`_INFRA_PAT` 只匹配 401/403/404，缺 429/rate limit
- **修复**：补充 429/rate limit/too many requests/throttl 模式
- **验证**：`tests/benchmark/test_judge_ratelimit.py` 6 条全绿 + 重判 v4 修正 4 条误判

## Forge 熔炉闭环（首次完整运行）

- 回归集：`benchmarks/benchforge/runs/batch-v4-20260822/regression.json`（6 条，B7 后 2 真失败）
- 聚类：incomplete_output 5 条 + mcp_call_error 1 条
- LLM 根因诊断：`fix-diagnosis.md`（qwen-turbo 生成，方向与实证吻合）
- 闭环验证：B5/B6/B7 修复均从真实失败样本驱动，回归测试锁定

## 待办

- [ ] qwen3.7-max 配额恢复后：batch-v5 验证 B5/B6/B7 修复效果（web-bench 项目链）
- [ ] 修复后重跑回归集（断点续跑自动跳过已成功任务）
- [ ] git 仓库分支损坏修复后提交本轮代码（已备份至 .tmp/git_backup_0822/）
- [ ] 前端视觉打磨剩余项
