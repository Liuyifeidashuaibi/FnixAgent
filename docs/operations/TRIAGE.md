# Issue / PR 分诊指南 / Triage Guide

> 本文件指导 Triager 如何高效分诊用户报告。
> 由于本项目不接受外部代码贡献,本指南侧重 **Issue / Discussion 分诊**。

---

## 一、目标 / Goals

- **5 分钟**内给每个新 Issue 一个有效响应
- **24 小时**内给每个 Issue 准确分诊标签
- **48 小时**内将 Issue 路由到正确模块维护者

---

## 二、响应模板 / First Response Templates

### 2.1 通用感谢 + 标签请求

```markdown
感谢报告!🤝

我会尽快复现这个问题。在那之前,如果你能补充以下信息会很有帮助:

- [ ] 操作系统与版本
- [ ] FnixAgent 版本
- [ ] 复现步骤(最小化)
- [ ] 期望行为 vs 实际行为
- [ ] 截图 / 录屏 / 日志

如果是安全问题或漏洞,请改发 liuyifeidashuaibi@gmail.com(见 SECURITY.md)。
```

### 2.2 Bug 报告

```markdown
感谢报告!已经复现,正在定位根因。
初步判断是 [模块] 的问题,会在 [时间] 给更新。
追踪进度:本贴 #issue_num
```

### 2.3 Feature Request

```markdown
感谢建议!

这个想法很有意思。我会把它移到 "Discussion → Ideas" 进一步讨论,
看是否有更多用户也想要这个功能。

如果有具体使用场景和 Mock UI / 示意图会更有帮助。
```

### 2.4 重复问题

```markdown
感谢报告!这个问题之前在 #other_issue 讨论过,合并到那里继续。
```

### 2.5 问题不在项目范围内

```markdown
感谢提问!

这看起来更属于 [其他工具] 的范畴:
- 链接: ...
- 我们的文档: ...

如果你是想在 FnixAgent 中集成,可以提 Feature Request。
```

---

## 三、标签系统 / Label System

### 3.1 类型 (kind)

| 标签 | 含义 |
| --- | --- |
| `kind: bug` | 缺陷 |
| `kind: feature` | 新功能 |
| `kind: enhancement` | 改进 |
| `kind: docs` | 文档 |
| `kind: question` | 提问 |
| `kind: discussion` | 设计讨论 |
| `kind: security` | 安全相关 |
| `kind: performance` | 性能 |
| `kind: a11y` | 可访问性 |
| `kind: i18n` | 国际化 |

### 3.2 区域 (area)

| 标签 | 模块 |
| --- | --- |
| `area: agentd` | Python 核心 |
| `area: workbench` | React 前端 |
| `area: tauri-core` | Rust 进程 |
| `area: fnix-local` | Rust 沙箱 |
| `area: memory` | 记忆系统 |
| `area: skill` | Skill 系统 |
| `area: llm` | LLM 集成 |
| `area: mcp` | MCP 协议 |
| `area: sdk-py` | Python SDK |
| `area: sdk-rust` | Rust SDK |
| `area: sdk-ts` | TS SDK |
| `area: docs` | 文档 |
| `area: ci` | CI/CD |
| `area: brand` | 品牌 |

### 3.3 优先级 (priority)

| 标签 | 含义 | SLA |
| --- | --- | --- |
| `priority: critical` | 阻塞主流程 | 24h |
| `priority: high` | 影响核心功能 | 1 周 |
| `priority: medium` | 普通 | 1 月 |
| `priority: low` | nice-to-have | 不保证 |

### 3.4 状态 (status)

| 标签 | 含义 |
| --- | --- |
| `status: triaged` | 已分诊 |
| `status: in-progress` | 处理中 |
| `status: needs-info` | 等用户补充 |
| `status: wontfix` | 不修复 |
| `status: duplicate` | 重复 |
| `status: blocked` | 被阻塞 |
| `status: stale` | 30 天无活动 |

### 3.5 其他

| 标签 | 含义 |
| --- | --- |
| `good first issue` | 适合新手 |
| `help wanted` | 欢迎帮助 |
| `breaking-change` | 破坏性变更 |
| `security-advisory` | 安全公告 |
| `needs-rfc` | 需要设计 RFC |

---

## 四、分诊决策树 / Decision Tree

```
新 Issue 进来
   ↓
[ ] 是安全问题吗?
   ↓ Yes → 立即移到私下处理,公开 Issue 关闭,留 liuyifeidashuaibi@gmail.com
   ↓ No
[ ] 是 bug 还是 feature?
   ↓ Bug
   |  → 尝试复现 (5 分钟)
   |    ↓ 复现成功
   |    → 加 kind:bug, priority:* , area:* , 分配给 Owner
   |    ↓ 复现失败
   |    → status:needs-info, 求用户补充
   ↓ Feature
   |  → kind:feature, 移到 Discussion → Ideas
   ↓ Question
   |  → kind:question, 引用 FAQ.md, 如 FAQ 未覆盖则回答 + 更新 FAQ
   ↓ Discussion
   |  → kind:discussion, 移到 Discussion → General
   ↓ 重复
   |  → 指向老 issue, status:duplicate, 关闭
   ↓ 不在范围
   |  → 礼貌解释, 提供替代方案, 关闭
```

---

## 五、Stale 管理 / Stale Management

30 天无活动的 Issue / PR:

- 第一次:`stale/bot` 自动评论"还在跟进吗?"
- 60 天无活动:自动 `status:stale`, 关闭
- 用户在关闭后 14 天内回复:自动 reopen

`.github/workflows/stale.yml`:

```yaml
name: Stale
on:
  schedule:
    - cron: "0 0 * * *"

jobs:
  stale:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/stale@v9
        with:
          days-before-stale: 30
          days-before-close: 14
          stale-pr-message: |
            这个 PR 已经 30 天没有活动。仍在跟进吗?
            如果是, 请更新本评论,否则 14 天后将自动关闭。
          exempt-pr-labels: |
            priority:critical
            in-progress
            security-advisory
```

---

## 六、每周例行 / Weekly Routine

每周一 Maintainer 做:

1. 扫所有 `kind:bug priority:critical|high` → 跟踪进度
2. 扫所有 `status:needs-info` → 私信提醒或关闭
3. 扫所有 `kind:feature` Discussion 投票,接受/拒绝
4. 整理 `good first issue`(让 Issue 池保持 5-10 个)
5. 关掉过去 30 天的 stale

---

## 七、Issue 关闭话术 / Closing Messages

### 修复后关闭

```markdown
已在 v0.5.1 修复:

- 修复 commit: abc123
- Release: https://github.com/Liuyifeidashuaibi/FnixAgent/releases/tag/v0.5.1

升级后请确认问题解决。如有问题请重新打开本 issue。
```

### 不修复关闭 (wontfix)

```markdown
经过评估,这个特性与我们的产品方向不符,暂不纳入路线图。
理由:
- ...

替代方案: [docs 链接]
如果仍想推动,请在 Discussion → Ideas 重新发起讨论并附详细用例。
```

### 用户不再回应 (stale)

```markdown
30 天未收到回应,即将关闭。
如仍有问题,请:
1. 升级到最新版本测试
2. 在本贴更新信息
14 天后将自动关闭。
```

---

## 八、/ References

- [GitHub — Triaging issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/about-issues-and-pull-requests)
- [Conventional Comments](https://conventionalcomments.org/)
- [GitHub Issue Templates](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests)

---

© 2024-2026 FnixAgent. All Rights Reserved.