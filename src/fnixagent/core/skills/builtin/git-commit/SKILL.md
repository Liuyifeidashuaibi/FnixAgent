---
name: git-commit
description: Conventional Commits 安全提交流程：分析 diff、拆分暂存、生成规范 message
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: md
tags:
  - git
  - commit
  - conventional-commits
  - trae-work
---
# Git Commit Skill

基于 Conventional Commits 的安全提交技能。分析变更、按逻辑拆分、生成规范 message，并严格遵守 Git 安全协议。

## 何时使用

- 用户要求提交 / commit / 写提交信息
- 工作区有待提交变更且用户希望规范化提交
- 需要把混杂变更按意图拆成多次提交

## 工作流程

1. **并行收集上下文**（必须同时执行）：
   - `git status`
   - `git diff` + `git diff --staged`
   - `git log -5 --oneline`（对齐本仓库风格）
2. **分析意图**：判断类型 `feat|fix|docs|refactor|test|chore|perf|ci|build|style`，可选 scope。
3. **安全检查**：绝不提交 `.env`、密钥、凭证、私钥、大体积二进制；发现则警告并排除。
4. **暂存**：仅 `git add` 相关文件；多项无关变更时拆分多次提交。
5. **提交**：用 HEREDOC 传 message；message 聚焦 *why*，祈使句，标题 ≤72 字符。
6. **验证**：`git status` 确认成功。

## Message 模板

```
<type>(<scope>): <summary>

<optional body explaining why>
```

## 安全协议（硬约束）

- 禁止修改 git config
- 禁止 `--force` / `hard reset` / 破坏性命令（除非用户明确要求）
- 禁止默认 `--no-verify` / 跳过 hooks
- 禁止主动 `push`（除非用户明确要求）
- 禁止交互式命令（`git add -i` / `rebase -i`）
- hooks 失败时：修复后 **新建** commit，不要 amend（除非满足 amend 安全条件）

## 输出

向用户报告：提交 hash、message、仍未提交的文件（如有）。

