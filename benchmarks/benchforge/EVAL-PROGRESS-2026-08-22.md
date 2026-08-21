# FnixAgent 全量编码 Agent 基准评测 —— 进度与缺陷台账

- 报告时间：2026-08-22 03:25
- 被测系统：FnixAgent（Tauri 前端 + FastAPI 后端 + AgenticLoop）
- 评测子系统：BenchForge（`src/fnixagent/bench/`，约 1840 行）
- 熔炉子系统：FnixForge（`src/fnixagent/core/forge/`，13 项单测全过）

---

## 一、任务总览

| 事项 | 状态 |
|---|---|
| 六大数据集获取与接入 | 5/6 完成（1406 题）；GAIA 166 题为 HF 门控数据集，无 token 无法拉取，已按规则记为 fetch_error 不中断 |
| 基准评测全量跑通 | **v2 进行中**（修复 ID 冲突后重启，产物目录 `benchmarks/benchforge/runs/fullrun-v2-20260822`，断点续跑） |
| 前端模拟用户实测 | 进行中（hello.txt 任务全链路验证通过） |
| 熔炉锻打闭环 | 子系统健康（13/13 单测），suite=core 19 题 / smoke 3 题就绪，待 v2 失败聚类后驱动修复 |
| 统计报告 + 回归集 | 待 v2 完成后由 `fnixagent bench report / fix` 自动生成 Markdown/HTML/回归集 JSON |

## 二、模型配额事件（本次最大外部障碍）

阿里云 MaaS 工作区（`ws-6d3gio8qx49xqswm.cn-beijing`）各模型为**免费配额制**，耗尽即 HTTP 403 `insufficient_quota`：

| 时间点 | 事件 | 影响 |
|---|---|---|
| 02:11 | glm-5.2 配额耗尽 | fullrun-20260822 中 1384/1406 题秒败，结果**作废** |
| 02:42 | kimi-k2.6 配额耗尽（重试轮） | fullrun-kimi 结果**作废** |
| 03:03 | qwen3.7-max-preview 配额耗尽 | 交互任务首次失败一次；bench 靠兜底链自动续跑 |

为根治此问题实现了**模型熔断兜底链**（见 D4）：任一模型命中鉴权/配额类终态错误，自动切换下一可用模型，评测与交互链路共用同一机制。当前有效模型池：`qwen3.6-max-preview → qwen3.6-flash-2026-04-16 → qwen3.6-plus-2026-04-02 → qwen3.5-plus（→ qwen3.7-max-preview，已耗）`。

## 三、缺陷台账（已修复并验证）

| ID | 级别 | 问题 | 修复 |
|---|---|---|---|
| D1 | 高 | standalone 未指定工作区时产物写进应用安装目录 | 11 处路由改用 `~/.fnix/workspaces/default`；端到端验证：hello.txt 落点正确、仓库根无污染 |
| D2 | 中 | 分析摘要直接泄露模型原始英文推理链 | 摘要去 (Step N) 前缀+词界截断；展开区加“与行为未必一致”免责 |
| D4 | 高 | 模型配额/鉴权失败=调用即死，无兜底 | LLMAdapter 熔断兜底链（读 `~/.fnix/config.toml model_fallbacks` 或 `LLM_MODEL_FALLBACKS`），bench 实测 34+ 次自动切换续跑 |
| D5 | 高 | 4xx 错误只报 HTTP 状态码，看不到 insufficient_quota 根因 | provider 错误附服务端错误简述（160 字符截断） |
| D7 | 高(安全) | `GET /work/runs` 响应明文回传 API Key | 响应层脱敏 `api_key=***redacted***`（存储层保留供 resume 使用） |
| D8 | 中 | 前端把裸 HTTP/provider 错误直接扔给用户 | `useChatFlow.humanizeErrorMessage`：配额/限流/超时转译为可行动指引 |
| D9 | 高(数据正确性) | web-bench 684 题只有 21 个唯一任务 ID | task_id 加 `project--` 前缀；修复后 684 唯一 |
| D10 | 高(数据正确性) | workbuddy 269 题只有 255 唯一 ID | subset 前缀+硬去重序号；修复后 269 唯一 |
| D11 | 高 | judge golden-match 用 substring 判定 SWE/Prototype 长标准答案 | 仅 GAIA 式短答案（≤160 字符单行）走 golden-match；vibe 30 + prototypebench 121 + swe 300 = 451 题的全量误判消除 |
| D12 | 中 | judge 把“模型配额耗尽”错算成 Agent 能力失败 | 检测 insufficient_quota/HTTP 40x 归入 other（基础设施错误） |
| D13 | 中 | write_config_toml 全量重写，PUT /config 会冲掉 model_fallbacks 等未知键 | 改为 read-modify-write 保键 |

历史修复（上一会话）：D3 产物双写关系已厘清、D6 ThinkingBlock 缺样式已补齐。

## 四、前端视觉体检（已记录，待排期打磨）

截图审查发现 6 类共约 17 项视觉问题：顶栏提示与关闭按钮不对齐、任务标题截断、图标风格/选卡样式不统一、“Self-Optimizing 沉淀”信息层级不清、Craft/模型选择器为系统默认样式、分区间距节奏不一。全部记录在案，优先级低于功能与数据正确性缺陷。

## 五、真实失败样本暴露的 Agent 控制层问题（v1 作废轮/冒烟中捕获）

| 编号 | 现象 | 初判根因 | 归属模块 |
|---|---|---|---|
| A1 | 反复 read/rewrite 同一 index.html 20+ 次不收敛，耗尽 25 步 | 规划无收敛判据，edit_file 失败后缺少换策略 | core/agent/loop（有“死循环熔断止损”但只熔断给 crash） |
| A2 | 达到 max_steps 后最终回复只是“I'll create a complete HTML file…”进行中说辞 | 步数耗尽缺“强制收尾+提交当前产物”逻辑 | core/agent/loop |
| A3 | Agent 断言“已包含该功能”而不实际执行添加按钮改动 | 需求理解偏差（LLM 判定样本） | 提示词/工作流层 |
| A4 | 轨迹记录 tool_args 为空 `{}` | 观测层未回填工具参数 | bench/runner 观测 |

## 六、运行产物索引

- v1 作废轮（保留作对比证据）：`benchmarks/benchforge/runs/fullrun-20260822/`（glm 配额耗尽）、`fullrun-kimi-20260822/`（kimi 配额耗尽）
- 冒烟验证：`benchmarks/benchforge/runs/smoke-qwen37-01/`（3/3 成功，真实 agent 轨迹 + tokens 36k-71k）
- 当前进行中：`benchmarks/benchforge/runs/fullrun-v2-20260822/` + `fullrun-v2.log`
- 数据集缓存：`benchmarks/benchforge/datasets/`
- 前端体检截图：本会话输出目录 `output/fnix-ui-main.png`

## 七、合规声明

本流程仅用于优化 FnixAgent 控制层（Runtime/MCP/记忆/Workflow）与产品质量；所有 prompt 原样传入、不抽样不过滤；**未用于任何基座模型 SFT 微调**。
