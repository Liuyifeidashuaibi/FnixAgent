---
adr_id: 0004
title: 三层任务图模型 (KTG-STP-MFP)
status: Accepted
date: 2026-08-15
deciders: FnixAgent Core Team
consulted: Research WG
informed: All contributors
supersedes: null
superseded_by: null
tags: [architecture, planning, graph]
---

# ADR-0004: 三层任务图模型 (KTG / STP / MFP)

## Context (背景)

Agent 在执行复杂任务时需要多层规划:

1. **长期目标层**:用户今年的 OKR / 大方向
2. **中短期计划层**:本周要完成的里程碑
3. **执行流层**:当前要走的 N 步工具调用链

单一扁平任务列表 (To-Do List) 难以表达:

- 任务间的**依赖关系** (DAG)
- 任务的**时间跨度** (跨周 vs 跨分钟)
- 任务的**抽象层级** (战略 vs 战术 vs 操作)

候选方案:

| 方案 | 层级 | 依赖图 | 评价 |
| --- | --- | --- | --- |
| **KTG + STP + MFP** | 3 层 | 每层独立 DAG | 表达力强 |
| LangGraph 单层图 | 1 层 | ✓ | 抽象粒度单一 |
| AutoGen GroupChat | 1 层 | ✗ | 适合多 Agent 不适合任务规划 |
| 微软 TaskWeaver | 2 层 | 部分 | 介于中间 |

## Decision (决策)

**采用 KTG-STP-MFP 三层任务图模型**:

```
┌─────────────────────────────────────────────────────────────┐
│  KTG (Knowledge Task Graph) — 知识任务图 (年度/季度)         │
│                                                              │
│  - 节点:大目标、领域能力、关键主题                            │
│  - 边:依赖关系 (宏观)                                        │
│  - 粒度: 季度到年度                                          │
└────────────────────────┬────────────────────────────────────┘
                         │ decompose
┌────────────────────────▼────────────────────────────────────┐
│  STP (Short-Term Plan) — 短期计划 (周/日)                    │
│                                                              │
│  - 节点:可交付成果、里程碑、决策点                            │
│  - 边:依赖关系 (中观)                                        │
│  - 粒度: 天到周                                              │
└────────────────────────┬────────────────────────────────────┘
                         │ decompose
┌────────────────────────▼────────────────────────────────────┐
│  MFP (Multi-step Flow Plan) — 多步流计划 (会话/工具)         │
│                                                              │
│  - 节点:单步工具调用 / 子 Agent                              │
│  - 边:数据流 / 控制流 / 重试                                 │
│  - 粒度: 秒到分钟                                            │
└─────────────────────────────────────────────────────────────┘
```

### KTG Schema (Top-level)

```yaml
type: ktg
goal: "成为 Top 1% Agent Engineer"
horizon: 12 months
nodes:
  - id: ktg.001
    title: "掌握 Tauri 2 桌面端"
    type: skill_area
    children: [stp.q3.tauri, stp.q4.tauri-prod]
    progress: 0.4
  - id: ktg.002
    title: "完成 FnixAgent 顶级开源治理"
    type: deliverable
    children: [stp.q3.os-governance]
    progress: 0.65
```

### STP Schema

```yaml
type: stp
period: "2026-W33"
parent: ktg.002
milestones:
  - id: stp.w33.001
    title: "完成 5 个 ADR"
    done: true
  - id: stp.w33.002
    title: "通过 CodeQL 扫描"
    done: false
    deps: [stp.w33.001]
```

### MFP Schema (per session)

```json
{
  "type": "mfp",
  "session_id": "sess_abc123",
  "plan": [
    {"id": "step1", "tool": "fs.read", "args": {"path": "..."}},
    {"id": "step2", "tool": "shell.run", "args": {"cmd": "..."}, "deps": ["step1"]},
    {"id": "step3", "tool": "llm.generate", "args": {"prompt": "..."}, "deps": ["step2"]}
  ]
}
```

### 跨层接口

- **decompose**:KTG → STP (LLM 拆解季度目标为周里程碑)
- **schedule**:STP → MFP (LLM 生成当周任务的执行步骤)
- **reflect**:MFP → STP (执行结果回写到周计划进度)
- **learn**:MFP → KTG (高频失败模式提升为新能力节点)

## Consequences (后果)

### 正面

- **可解释**:每一层都可独立展示给用户 (vs LangGraph 黑盒)
- **可干预**:用户可以在任意层注入/删除节点
- **可回放**:MFP 是确定性图,可逐步重放
- **可度量**:每层都有 progress 指标

### 负面 / 风险

- 三层同步需要 LLM 多次调用 → latency
- 节点 ID 命名空间管理复杂
- 实现量大,需要先做 MFP,后做 STP,最后 KTG

### 缓解

- 每层独立 mock,先做垂直 demo,再做水平集成
- 节点 ID 用 `<layer>.<period>.<seq>` 格式,自动校验唯一
- MFP 优先,因为它是执行层;KTG 留到 v0.5

## Alternatives Considered (备选方案)

- **Anthropic Skill / Tool 编排**:过于扁平,没有时间维度
- **LangChain Plan-and-Execute**:只有一层 plan,不支持嵌套

## References (参考)

- [AutoGen Magentic-One Planning](https://microsoft.github.io/autogen/blog/2024/01/26/Magentic-One/)
- [LangGraph Hierarchical Agent](https://langchain-ai.github.io/langgraph/concepts/hierarchical/)
- 内部文档: `docs/layers/` `docs/memory-architecture.svg`

## Notes (备注)

术语统一在 `docs/GLOSSARY.md`,KTG / STP / MFP 都是首字母缩写,不要混用 plan / goal / task。