# AgentTeams 演示指南

> 一条命令体验 FnixAgent 的多角色协作：`python demos/agent_teams_demo.py`
>
> 自动模式：检测到 `.env` 中的 API Key 即用真实 LLM；否则回退离线 Mock（`--mock` 强制）。

## 场景

主 Agent 接到任务「调研并评审快速排序资料」，拆解为三个子任务并行派发：

| 任务 | 角色 | 职责 |
|---|---|---|
| T1 | researcher | 快排分治思想与复杂度调研 |
| T2 | researcher | 快排 vs 归并对比 |
| T3 | critic | 对 T1/T2 材料交叉评审（ISSUES/SCORE/VERDICT） |

## 执行流程

```
主循环(AgenticLoop)
   │ team_fan_out(tasks=[T1,T2,T3])
   ▼
AgentTeam.fan_out() ── 创建共享任务清单 tasks.json (3×pending)
   │ asyncio.gather + Semaphore(3)
   ├─▶ worker[T1] SubagentManager(role=researcher) ── 认领→执行→黑板 T1.md→complete
   ├─▶ worker[T2] 同上(并行)                        ── 认领→执行→黑板 T2.md→complete
   └─▶ worker[T3] SubagentManager(role=critic)      ── 认领→评审→黑板 T3.md→complete
   ▼
双账本结算: note_wave() → progress ledger 五问判定
返回: {results[], stats{completed:3/3}, wave, progress}
```

## 实测输出（Mock 模式节选）

```
[PASS] [T1] researcher success
   └ [Mock 结论] 针对「用要点说明快排的分治思想与复杂度」...
   └ 黑板文档: T1.md (status=success)
[PASS] [T2] researcher success
[PASS] [T3] critic     success

共享任务清单: {"total": 3, "by_status": {"completed": 3}, "completed_ratio": 1.0}

进度账本(Magentic 式五问):
{
 "is_request_satisfied": true,
 "is_in_loop": false,
 "is_progress_being_made": true,
 "stall_counter": 0,
 "recommendation": "全部任务完成, 可汇合收尾"
}
```

## 关键机制速览

- **角色白名单代码层强制**：researcher 只读、coder 可写但过 ToolPolicy/HITL 门、critic 零工具
- **工人是叶子**：工人注册表不含任何团队工具 → 无嵌套团队（对齐 Claude Code 红线）
- **结构化交接**：每个工人结论落 `outputs/T*.md`（frontmatter 含 task_id/role/status/duration），主 Agent 与后续任务按路径引用，不做自由对话
- **失败语义**：可重试错误退回 pending；终态错误标 failed 并投递 lead 信箱（`team_read_inbox` 消费）
- **卡死自愈**：连续无进展波次 >2 时 progress.recommendation 提示主 Agent 重规划（Magentic-One 阈值）

## 在真实 Work 任务中使用

Work 主循环已注册团队工具，直接对主 Agent 说：

> 「先派两个 researcher 分别调研 X 和 Y，然后基于发现让 coder 写实现，最后让 critic 评审」

主 LLM 会调用 `team_fan_out` 编排整个流程。
