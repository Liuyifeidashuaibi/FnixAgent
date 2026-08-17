---
name: template-skill
description: Skill 模板 — 创建新 skill 时复制此目录作为基线
version: 1.0.0
license: Apache-2.0
level: BASIC
output_format: md
tags:
  - template
  - meta
  - scaffold
  - starter
resources:
  - core/skills/loader.py
---

# Template Skill

Skill 模板。本 skill 本身不执行具体功能，作为 `skill-creator` 创建新 skill 时的基线模板。复制此目录 → 修改 frontmatter + body → 校验 → 落盘。

## 何时使用

- `skill-creator` skill 调用本模板作为基线
- 用户希望手动复制模板创建新 skill
- 教学 / 文档场景展示 SKILL.md 标准结构

不要用于：直接执行（本模板 body 无实际可执行内容）。

## 工作流程

1. **复制目录**：把 `builtin/template-skill/` 复制到 `~/.fnix/skills/<new-name>/`。
2. **修改 frontmatter**：把 `name` 改为 `<new-name>`；调整 `description` / `version` / `level` / `output_format` / `tags` / `resources`。
3. **填充 body**：按以下五章节模板填写：
   - `## 何时使用`：列出 3–5 个触发场景
   - `## 工作流程`：3–5 步执行流程
   - `## 输出契约`：output_format + 元数据 schema
   - `## Fnix 集成点`：对应哪个 office 模块 / code agent
   - `## 示例`：1 个简短示例（用户输入 + skill 执行步骤 + 输出）
4. **校验**：用 `BuiltinSkillLoader._parse_skill_md` 校验 frontmatter。
5. **落盘**：写入 `~/.fnix/skills/<new-name>/SKILL.md`。

## 输出契约

- `output_format: md`（SKILL.md 文件）
- 产物路径：`~/.fnix/skills/<new-name>/SKILL.md`
- frontmatter 必填字段：name / description / version / license
- frontmatter 可选字段：level / output_format / tags / resources
- body 必含五章节：何时使用 / 工作流程 / 输出契约 / Fnix 集成点 / 示例
- name 正则：`^[a-z0-9-]{1,64}$`
- version 格式：semver（`1.0.0`）
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.core.skills.loader.BuiltinSkillLoader`（校验）
- 工具注册：本模板不注册工具（作为模板基线）
- 协作：被 `skill-creator` skill 调用作为基线
- 加载：用户级 skill 通过 `harness/skills_loader.py` 加载
- 模式：META 级（创建 skill 属于自我修改）— 需用户显式授权

## 示例

**用户**：复制 template-skill 创建一个 `meeting-notes` skill。

**Skill 执行**：
1. 复制 `builtin/template-skill/SKILL.md` → `~/.fnix/skills/meeting-notes/SKILL.md`
2. 修改 frontmatter：
   ```yaml
   ---
   name: meeting-notes
   description: 会议纪要自动生成 — 转录/议程/决议/行动项
   version: 1.0.0
   license: Apache-2.0
   level: BASIC
   output_format: md
   tags: [meeting, notes, office, work]
   resources: [office/markdown.py]
   ---
   ```
3. 填充 body 五章节（参考其他 builtin skill 风格）
4. `BuiltinSkillLoader._parse_skill_md(path)` 校验通过
5. 返回 `~/.fnix/skills/meeting-notes/SKILL.md` 路径
