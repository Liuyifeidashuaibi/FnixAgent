# ADR Index — FnixAgent 架构决策记录

> 本目录按 [MADR 4.0](https://adr.github.io/madr/) 规范记录 FnixAgent 所有重大架构决策。
> 每条 ADR 不可被直接修改;变更必须新增 ADR 并通过 `supersedes` / `superseded_by` 链接。

## 索引

| ID | 标题 | 状态 | 日期 | Tags |
| --- | --- | --- | --- | --- |
| [0001](0001-tauri-desktop-runtime.md) | 使用 Tauri 作为桌面端运行时 | ✅ Accepted | 2026-08-12 | architecture, desktop, tauri |
| [0002](0002-byok-keychain-strategy.md) | BYOK 凭据存储策略 | ✅ Accepted | 2026-08-13 | security, privacy, byok |
| [0003](0003-markdown-git-memory.md) | 长期记忆采用 Markdown + Git | ✅ Accepted | 2026-08-14 | architecture, storage, memory |
| [0004](0004-three-layer-task-graph.md) | 三层任务图模型 (KTG / STP / MFP) | ✅ Accepted | 2026-08-15 | architecture, planning, graph |
| [0005](0005-python-runtime-uv.md) | Python 异步运行时 + uv 包管理 | ✅ Accepted | 2026-08-16 | engineering, runtime, packaging |

## 状态图例

- 🟢 **Proposed** — 提案中,等待评审
- ✅ **Accepted** — 已接受,正在执行
- ⚠️ **Deprecated** — 已弃用,保留以备查阅
- ❌ **Rejected** — 已被否决
- 🔄 **Superseded** — 已被新 ADR 取代

## 模板

```markdown
---
adr_id: NNNN
title: <简短标题>
status: <Proposed|Accepted|Deprecated|Rejected|Superseded>
date: YYYY-MM-DD
deciders: <决策者>
consulted: <咨询对象>
informed: <知会对象>
supersedes: <旧 ADR ID 或 null>
superseded_by: <新 ADR ID 或 null>
tags: [tag1, tag2]
---

# ADR-NNNN: <标题>

## Context (背景)
<问题是什么,候选方案对比>

## Decision (决策)
<最终选择,具体到配置 / 接口 / Schema>

## Consequences (后果)
### 正面
### 负面 / 风险
### 缓解

## Alternatives Considered
## References
## Notes
```

## 评审流程

1. 提交 PR,标题 `docs(adr): propose NNNN-<short-title>`
2. 至少 2 名 Core Maintainer `LGTM`
3. 合入后 7 天无反对 → 状态自动从 `Proposed` 升为 `Accepted`
4. 任何后续变更必须新增 ADR 引用本条 (不可直接 edit)

## 自动化

- `.github/workflows/adr-lint.yml`:检查 frontmatter 必填字段
- `.github/workflows/adr-index.yml`:每次合入自动重生成本 README
- CI 会拒绝 ID 跳号 / 重复 / 缺失 frontmatter 的 PR