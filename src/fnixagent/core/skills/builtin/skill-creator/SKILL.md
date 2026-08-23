---
name: skill-creator
description: 元 skill — 引导用户创建新的 Agent Skill（SKILL.md 格式）
version: 1.0.0
license: Apache-2.0
level: META
output_format: md
tags:
  - meta
  - skill-creator
  - authoring
  - template
resources:
  - core/skills/loader.py
  - core/skills/market.py
---

# Skill Creator Skill

元 skill：引导用户创建新的 Agent Skill（SKILL.md 格式）。当用户说「我想创建一个 skill」或「把这个工作流沉淀成 skill」时启用。本 skill 是 META 级，需要用户显式授权才能写盘到 `builtin/` 或 `~/.fnix/skills/`。

## 何时使用

- 用户明确表达要创建新 skill（「我想做一个 skill 来…」）
- 用户重复执行同一工作流 ≥3 次，建议沉淀为 skill
- 用户要把一段 SOP / 检查清单 / 操作流程固化为 skill
- 用户要为团队 / 组织发布 skill 到市场

不要用于：执行已有 skill（用对应 skill）、修改内置 skill（不允许，内置 skill 只读）。

## 工作流程

1. **意图澄清**：问用户 5 个问题：
   - skill 名（小写字母/数字/连字符，≤64 字符）
   - 何时使用（触发场景）
   - 工作流程（3–5 步）
   - 输出契约（output_format + 元数据）
   - Fnix 集成点（对应哪个 office 模块 / code agent / 外部工具）
2. **草稿生成**：基于用户回答，参考 `template-skill` skill 模板，生成 `SKILL.md` 草稿（含 frontmatter + body 五章节）。
3. **校验**：调用 `BuiltinSkillLoader._parse_skill_md` 校验 frontmatter 格式（name 正则 / version semver / 必填字段）；不通过则进入 fix 循环。
4. **试运行**：让用户用一个示例输入试跑 skill（手动模拟），验证 body 描述是否清晰可执行。
5. **落盘**：用户确认后，写入 `~/.fnix/skills/<name>/SKILL.md`（用户级）或发布到 `SkillMarket`（组织级）；不允许写入 `builtin/`（产品内置只读）。
6. **交付**：返回 skill 路径与 frontmatter 摘要；提示用户可在下次会话中通过 `load_workspace_skills` 自动加载。

## 输出契约

- `output_format: md`（SKILL.md 文件）
- 产物路径：`~/.fnix/skills/<skill_name>/SKILL.md`（用户级）或 `SkillMarket` 条目（组织级）
- SKILL.md 必含：
  - frontmatter: name / description / version / license（必填）+ level / output_format / tags / resources（可选）
  - body: `## 何时使用` / `## 工作流程` / `## 输出契约` / `## Fnix 集成点` / `## 示例`
- name 必须满足 `^[a-z0-9-]{1,64}$`
- version 必须是 semver（如 `1.0.0`）
- 不允许覆盖内置 skill 名（16 个 builtin 名占位）
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.core.skills.loader.BuiltinSkillLoader`（校验 frontmatter）
- 工具注册：`skill-creator.clarify` / `skill-creator.draft` / `skill-creator.validate` / `skill-creator.save` / `skill-creator.publish`
- 协作：用 `template-skill` skill 作为模板基线
- 持久化：用户级 → `~/.fnix/skills/<name>/SKILL.md`；组织级 → `SkillMarket.create_draft` + `submit_for_review` + `approve`
- 模式：META 级 — 需要用户显式授权；不修改 `builtin/` 目录
- 加载：新 skill 创建后通过 `harness/skills_loader.py` 的 `load_workspace_skills` 自动加载

## 示例

**用户**：我想做一个 skill，用来自动化周报生成。

**Skill 执行**：
1. `skill-creator.clarify()` → 问 5 个问题
2. 用户回答：
   - name: `weekly-report`
   - 何时使用: 每周五下午需要写周报
   - 工作流程: 1) 拉本周 git commits 2) 拉本周完成的 task 3) 按模板生成 4) 写入 docx
   - 输出契约: docx + 元数据 {commits, tasks, week}
   - Fnix 集成点: `docx` skill + `office/template.py`
3. `skill-creator.draft(answers=...)` → 生成 SKILL.md 草稿
4. `skill-creator.validate(path=<草稿>)` → 通过 BuiltinSkillLoader 校验
5. 用户确认 → `skill-creator.save(name="weekly-report", scope="user")` → 写入 `~/.fnix/skills/weekly-report/SKILL.md`
6. 返回路径 + frontmatter 摘要
