# Skill 开发指南 / Plugin Development

> 本文件教你怎么写 FnixAgent 的 Skill(技能 / 插件)。
> Skill 是 FnixAgent 的核心扩展机制 — 一个纯 Markdown 文件,描述 LLM 如何完成一类任务。

---

## 一、什么是 Skill? / What is a Skill?

Skill = 一个**纯 Markdown 文件** + 必要的资源(脚本、图标、Schema)。

```
~/.fnix/skills/<skill-name>/
├── SKILL.md              # 主文件(必须)
├── SKILL.zh-CN.md        # 多语言版本(可选)
├── resources/            # 附带的脚本/数据
│   └── helper.py
├── icon.svg              # 16x16 图标
└── tests/
    └── test.md           # 测试用例(可选)
```

**核心思想**:Skill 的全部"代码"就是 `SKILL.md`,LLM 直接读它来理解怎么执行任务。
这种"prompt 即代码"的范式让 Skill 开发门槛降到 0 — **任何人**会写 Markdown 就会写 Skill。

---

## 二、最小 Skill / Minimal Skill

`~/.fnix/skills/hello-world/SKILL.md`:

```markdown
---
skill: hello-world
version: 1.0.0
description: 说一句问候
author: 刘逸飞
license: All Rights Reserved
inputs:
  - name: name
    type: string
    required: false
    default: "世界"
outputs:
  type: string
---

# Hello World Skill

## Instructions

向 ${name} 致以问候。

## Output

直接输出一句中文问候,不超过 20 字。

## Examples

Input: name="小明"
Output: "小明,你好!"
```

**调用**:

```python
result = await agent.run(
    "打招呼",
    skills=["hello-world"],
    inputs={"name": "小明"},
)
print(result.text)  # "小明,你好!"
```

---

## 三、完整 Schema / Full Frontmatter

```yaml
---
# 必填
skill: code-review                     # 唯一 ID(小写 + 连字符)
version: 1.0.0                         # 语义化版本
description: 对代码 diff 进行结构化审查   # 一句话描述

# 元数据(可选但推荐)
author: 刘逸飞
license: All Rights Reserved           # 与主项目一致
homepage: https://fnixagent.dev/skills/code-review
tags: [code, review, productivity]
category: development                  # development|productivity|creative|research|ops
icon: ./icon.svg
min_fnixagent_version: 0.5.0

# 输入定义
inputs:
  - name: diff
    type: string
    required: true
    description: Git diff 文本
  - name: language
    type: string
    enum: [python, rust, typescript, go, java, cpp, other]
    default: auto
  - name: strictness
    type: string
    enum: [lenient, normal, strict]
    default: normal
  - name: max_issues
    type: integer
    default: 20
    minimum: 1
    maximum: 100

# 输出定义
outputs:
  type: object
  schema:
    type: object
    properties:
      verdict:
        type: string
        enum: [approve, request_changes, comment]
      summary:
        type: string
        maxLength: 200
      issues:
        type: array
        items:
          type: object
          properties:
            severity: { type: string, enum: [blocker, major, minor, nit] }
            line: { type: integer, minimum: 1 }
            message: { type: string }
      suggestions:
        type: array
        items: { type: string }

# 使用的工具
tools:
  - fs.read
  - shell.run    # 如使用工具,标 safety

# 危险标记
safety: safe        # safe | moderate | dangerous
                    # safe: 无副作用,可自动执行
                    # moderate: 有副作用,需 UI 确认
                    # dangerous: 高风险,必须二次确认

# LLM 推荐配置
llm:
  provider: anthropic
  model: claude-sonnet-4-5
  temperature: 0.2
  max_tokens: 4000

# 多语言版本
i18n:
  en-US: ./SKILL.md
  zh-CN: ./SKILL.zh-CN.md
  ja-JP: ./SKILL.ja-JP.md

# 依赖其他 Skill
requires:
  - name: git-diff-parser
    version: ">=1.0.0"

# 沙箱配置(可选)
sandbox:
  cpu_limit: "500m"
  memory_limit: "256Mi"
  timeout: "30s"
  network: blocked   # blocked | limited | open

# 测试
tests:
  - input:
      diff: |
        diff --git a/x.py b/x.py
        @@
        -print("old")
        +print("new")
    expected_output_contains: ["verdict"]
  - input:
      diff: "..."
    expected_output: null    # 仅校验调用不报错

---
```

---

## 四、Markdown Body 模板 / Body Template

```markdown
# <Skill 标题>

## 角色 (Role)

你是 <角色描述>。

## 任务 (Task)

<任务目标,用第一人称 / 第二人称 / 客观描述皆可,但全文统一>。

## 输入 (Inputs)

- `${input1}`: <说明>
- `${input2}`: <说明>

## 步骤 (Steps)

1. 第一步做什么
2. 第二步做什么
3. ...

## 输出格式 (Output Format)

严格按以下 JSON 输出,无任何额外解释:

```json
{
  ...
}
```

## 约束 (Constraints)

- 不要做 X
- 必须做 Y
- 当 Z 时,优先 W

## 示例 (Examples)

### 示例 1

输入: ...

输出: ...

### 示例 2

输入: ...

输出: ...

## 边界情况 (Edge Cases)

- 如果 A 为空,返回 { ... }
- 如果 B 超过 100,截断并提示

## 失败模式 (Failure Modes)

| 错误 | 处理 |
| --- | --- |
| 网络超时 | 重试 3 次后返回 null |
| 输入格式错误 | 返回 { error: "invalid_input", message: "..." } |
```

---

## 五、Tool 工具调用 / Tool Calls

Skill 可声明使用工具,工具会在执行时挂载到 LLM context:

```yaml
tools:
  - fs.read           # 读文件
  - fs.write          # 写文件(默认 moderate)
  - shell.run         # 执行 shell(默认 dangerous)
  - web.fetch         # HTTP GET
  - llm.embed         # 生成 embedding
  - memory.search     # 检索记忆
  - skill.invoke      # 调用其他 Skill
```

每个工具调用会自动包装权限检查:

```
LLM 想调用 shell.run("rm -rf /")
  ↓
Skill safety: moderate
  ↓
UI 弹出确认框:"Skill 'my-skill' 想执行: rm -rf /  [允许] [拒绝]"
  ↓
用户允许 → 执行;拒绝 → 返回 error
```

---

## 六、高级特性 / Advanced Features

### 6.1 多步 Skill(自带流程控制)

```markdown
## Steps

1. 调用 `fs.read` 读取 `${file_path}`
2. 调用 `llm.generate` 分析内容(prompt: ...)
3. 调用 `web.fetch` 获取相关文档
4. 综合信息生成最终报告
```

LLM 会按顺序执行,Agent 引擎记录每步结果。

### 6.2 子 Skill

```yaml
requires:
  - name: code-style-check
    version: ">=1.0.0"
```

```markdown
## Steps

1. 调用子 skill `code-style-check` 风格检查
2. 基于结果补充审查意见
```

### 6.3 流式输出

```yaml
outputs:
  type: object
  streaming: true   # 支持流式返回
  schema:
    type: object
    properties:
      verdict: { type: string }
      progress: { type: integer }  # 0-100
      current_step: { type: string }
```

### 6.4 资源文件

Skill 可附带 Python / Node / Rust 脚本:

```yaml
sandbox:
  scripts:
    - path: ./resources/parser.py
      runtime: python
      timeout: 10s
      inputs_schema:
        diff: string
      outputs_schema:
        files: array
```

LLM 可以调用这些脚本作为子工具。

### 6.5 测试用例

`tests/test.md`:

```markdown
# Test Cases

## Test 1: 简单 diff

input:
  diff: "..."
expected:
  verdict: "approve"
  issues: []

## Test 2: SQL 注入

input:
  diff: "..."
expected:
  verdict: "request_changes"
  issues:
    - severity: "blocker"
      message: "存在 SQL 注入风险"
```

跑测试:

```bash
fnix skill test code-review
```

---

## 七、安全等级详解 / Safety Levels

| 等级 | 行为 | 例子 |
| --- | --- | --- |
| `safe` | 无需确认 | 读文件、计算、生成文本 |
| `moderate` | 首次执行确认 | 写文件、发 HTTP、修改配置 |
| `dangerous` | 每次确认 + 输入显示 | 执行 shell、删除文件、发邮件 |

用户可以在 Settings → Skills 里**永久信任**某个 Skill(跳过确认)。

---

## 八、发布到个人 / Publishing

由于本项目为专有项目([LICENSE](../../LICENSE)),**Skill 也属于专有
作品**。

如需分享 Skill 给他人:

- **允许**:发邮件 / GitHub Gist 给特定个人,对方不得再分发
- **不允许**:上传到公共 Skill 市场 / 写博客公开完整内容 / Fork

详见 [LICENSE](../../LICENSE) 与 [TRADEMARKS.md](../../TRADEMARKS.md)。

---

## 九、调试 / Debugging

```bash
# 单步执行,看每步输入输出
fnix skill debug code-review --inputs '{"diff": "..."}'

# 看 Skill 解析后的 prompt
fnix skill show code-review --as-prompt

# 校验 frontmatter
fnix skill validate code-review

# 重载
fnix skill reload code-review
```

---

## 十、参考示例 / Reference Examples

`~/.fnix/skills/` 内置示例:

- `hello-world` — 最简 Skill
- `code-review` — 完整 schema + 工具调用
- `batch-rename` — dangerous Skill + 二次确认
- `web-search` — HTTP API 调用
- `memory-recall` — 调 memory.search
- `git-commit-msg` — 模板生成

---

## 十一、参考 / References

- [Anthropic Tool Use](https://docs.anthropic.com/en/docs/tool-use)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [LangChain Tools](https://python.langchain.com/docs/modules/agents/tools/)

---

© 2024-2026 FnixAgent. All Rights Reserved.