---
adr_id: 0003
title: 长期记忆采用 Markdown + Git 的版本化存储
status: Accepted
date: 2026-08-14
deciders: FnixAgent Core Team
consulted: Memory WG, Storage WG
informed: All contributors
supersedes: null
superseded_by: null
tags: [architecture, storage, memory]
---

# ADR-0003: 长期记忆采用 Markdown + Git 版本化存储

## Context (背景)

Agent 长期记忆需要持久化以下内容:

1. 用户偏好 (tone, hotness, role, language)
2. 项目笔记 (用户工作过哪些项目、关键决策)
3. 工具调用历史 (可追溯、可重放)
4. 失败案例 (避免重复犯错)

候选存储方案:

| 方案 | 可读 | 版本化 | 可移植 | 检索 | 备注 |
| --- | --- | --- | --- | --- | --- |
| **Markdown + Git** | ✓ | ✓ | ✓ | 弱 (grep) | 人类可读 |
| SQLite | ✗ | ✗ | ✓ | ✓ | 适合结构化但难审计 |
| JSON 文件 | ✓ | ✗ | ✓ | 中 | 无版本化 |
| 向量数据库 (Chroma) | ✗ | ✗ | ✗ | ✓ | 适合语义检索但不易审计 |

## Decision (决策)

**主存采用 Markdown 文件 + Git 版本化**;**索引采用 SQLite + sqlite-vec**。

### 存储结构

```
.fnix/memory/
├── core/                    # 永久记忆
│   ├── user.md             # 用户画像
│   ├── projects.md         # 用户参与的项目
│   └── decisions.md        # 关键决策记录
├── episodic/                # 情景记忆(按日期)
│   └── 2026-08-12.md
├── semantic/                # 语义记忆(向量索引)
│   └── index.sqlite
└── procedural/              # 程序记忆(技能)
    └── skills/
        └── *.md
```

### Markdown Schema (Front Matter)

```yaml
---
memory_id: mem_2026_08_12_001
type: episodic              # core | episodic | semantic | procedural
created: 2026-08-12T14:32:11+08:00
last_accessed: 2026-08-15T09:10:00+08:00
access_count: 7
importance: 0.72            # 0-1 重要度
ttl: null                   # 过期时间, null = 永久
tags: [user:刘逸飞, project:fnixagent, topic:architecture]
entities: [fnixagent, tauri, byok]
source: conversation        # conversation | import | inference
related: [mem_2026_08_10_003]
---

# 记忆正文(纯 Markdown,人类可读)
```

### 写入策略

- **append-only**:每次更新追加一行时间戳 + diff,不直接覆盖原内容
- **自动 commit**:`git add -A && git commit -m "memory: <memory_id> update"` 由后台 cron 执行
- **冲突处理**:每次 pull 自动 rebase,冲突交给 LLM 合并

### 检索策略

- **精确查询**:grep / ripgrep over `core/` `episodic/`
- **语义查询**:用 `sqlite-vec` 向量索引,embedding 用本地模型 (`bge-small-zh`)
- **混合查询**:RRF (Reciprocal Rank Fusion) 融合 grep + 向量

## Consequences (后果)

### 正面

- 用户可以**直接打开 `~/.fnix/memory/` 看自己被记住什么** → 透明度极高
- 版本化让用户可以**回滚误操作** (e.g. 删错记忆)
- Markdown 工具链丰富 (VSCode 插件、Obsidian、Logseq)
- 零额外依赖,纯文件系统

### 负面 / 风险

- 10 万条记忆后 grep 性能下降 → 需要按 `tags` 分目录
- Git 仓库会持续膨胀 → 需要 LFS 或定期 `git gc`
- Markdown 不是结构化数据 → 检索需要解析 front matter

### 缓解

- `episodic/` 按年/月分目录 (`episodic/2026/08/`)
- Git 配合 `git gc --aggressive --prune=now` 定期清理
- 用 `python-frontmatter` 解析,失败时 fallback 到纯文本

## Alternatives Considered (备选方案)

- **Obsidian 兼容**:考虑过 Obsidian `[[wiki-link]]` 语法,最终决定用纯 Markdown + tags,因为 Obsidian 链接耦合特定工具
- **Notion / Logseq 同步**:依赖第三方服务,违反本地优先原则,排除

## References (参考)

- [Markdown for documentation](https://www.writethedocs.org/videos/europe/2017/the-good-the-bad-and-the-mdx-the-markdown-story/)
- [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [Reciprocal Rank Fusion (Cormack et al. 2009)](https://dl.acm.org/doi/10.1145/1571941.1572114)

## Notes (备注)

记忆 schema 在 `packages/sdk/src/memory/schema.py` 中有 Pydantic 模型强校验。