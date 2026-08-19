# 示例集 / Examples

> 通过具体示例演示 FnixAgent 的能力。

---

## 目录

- [Hello World](#hello-world)
- [本地 LLM 跑对话](#本地-llm-跑对话)
- [长期记忆](#长期记忆)
- [Skill:代码审查](#skill代码审查)
- [Skill:文件批量重命名](#skill文件批量重命名)
- [任务图规划](#任务图规划)
- [BYOK 配置](#byok-配置)

---

## Hello World

**目标**:让 FnixAgent 说 "Hello, world"。

```python
# examples/01_hello.py
import asyncio
from fnixagent import Agent

async def main():
    agent = Agent(provider="openai", model="gpt-4o-mini")
    result = await agent.run("请用中文说一句问候,不超过 10 个字")
    print(result.text)

asyncio.run(main())
```

**输出**:
```
你好,世界!
```

---

## 本地 LLM 跑对话

**目标**:完全不联网,跑 7B 模型。

```python
# examples/02_local_llm.py
import asyncio
from fnixagent import Agent, Config

async def main():
    config = Config.from_yaml("""
    llm:
      default_provider: local-llm
      providers:
        local-llm:
          base_url: http://127.0.0.1:11434
          default_model: qwen2.5-coder:7b
    """)

    agent = Agent(config=config)
    result = await agent.run("用 Rust 写一个 hello world 函数")
    print(result.text)

asyncio.run(main())
```

**前置**:

```bash
# 1. 装 本地推理引擎
curl -fsSL 参见本地推理引擎安装指南 | sh
local-llm serve &

# 2. 拉模型(约 4.7 GB)
local-llm pull qwen2.5-coder:7b

# 3. 跑示例
uv run python examples/02_local_llm.py
```

---

## 长期记忆

**目标**:让 Agent 记住你的偏好,跨会话使用。

```python
# examples/03_memory.py
import asyncio
from fnixagent import Agent

async def main():
    agent = Agent(provider="openai", enable_memory=True)

    # 第 1 轮:告诉它你的偏好
    await agent.run("记住:我喜欢用 Rust 而不是 Go,因为我重视类型安全和所有权系统")

    # 第 2 轮:问相关问题,看是否记得
    result = await agent.run("我应该选 Rust 还是 Go 来写一个新项目?")
    print(result.text)

    # 输出可能包含"考虑到你之前提到重视类型安全和所有权系统,Rust 更适合..."

asyncio.run(main())
```

**存储位置**:

```bash
ls ~/.fnix/memory/core/
# user.md
# preferences.md

cat ~/.fnix/memory/core/preferences.md
```

输出:
```markdown
---
memory_id: mem_2026_08_17_001
type: core
importance: 0.85
tags: [user:刘逸飞, topic:language-preference]
---

用户偏好 Rust,理由是类型安全 + 所有权系统优于 Go 的 interface 灵活性。
```

---

## Skill:代码审查

**目标**:对一个 Git diff 做代码审查。

**Skill 定义**(`~/.fnix/skills/code-review/SKILL.md`):

```markdown
---
skill: code-review
version: 1.0.0
description: 对代码 diff 进行结构化审查
inputs:
  - name: diff
    type: string
    required: true
  - name: language
    type: string
    default: auto
outputs:
  type: object
  schema:
    verdict: enum[approve, request_changes, comment]
    summary: string
    issues: array[{severity, line, message}]
    suggestions: array[string]
---

# Code Review Skill

## Instructions

你是一名资深 ${language} 工程师,对以下 diff 进行结构化审查:

```
${diff}
```

## 输出格式

请严格按以下 JSON 输出:

```json
{
  "verdict": "approve" | "request_changes" | "comment",
  "summary": "< 50 字总结 >",
  "issues": [
    {"severity": "blocker|major|minor|nit", "line": <int>, "message": "<string>"}
  ],
  "suggestions": ["<string>", ...]
}
```

## 审查维度

- 正确性:逻辑是否正确,边界条件是否处理
- 性能:是否有 O(n²) 循环、内存泄漏
- 安全:SQL 注入、XSS、SSRF、敏感信息泄露
- 可读性:命名、注释、代码结构
- 可测性:是否便于单元测试
- 一致性:与项目其他代码风格是否一致
```

**调用**:

```python
# examples/04_code_review.py
import asyncio
from fnixagent import Agent
import subprocess

async def main():
    diff = subprocess.check_output(["git", "diff", "HEAD~1"]).decode()

    agent = Agent(provider="openai", model="gpt-4o")
    result = await agent.run(
        "请审查以下代码 diff:",
        skills=["code-review"],
        inputs={"diff": diff, "language": "python"},
    )

    review = result.skill_outputs["code-review"]
    print(f"Verdict: {review.verdict}")
    print(f"Summary: {review.summary}")
    for issue in review.issues:
        print(f"  [{issue.severity}] L{issue.line}: {issue.message}")

asyncio.run(main())
```

---

## Skill:文件批量重命名

**目标**:把目录里所有 `.txt` 改成 `.md`,并加日期前缀。

**Skill**(`~/.fnix/skills/batch-rename/SKILL.md`):

```markdown
---
skill: batch-rename
version: 1.0.0
description: 批量重命名文件,支持模式匹配
inputs:
  - name: directory
    type: string
    required: true
  - name: pattern
    type: string
    required: true
  - name: replacement
    type: string
    required: true
  - name: dry_run
    type: boolean
    default: true
safety: dangerous  # 标记为危险,需要用户确认
---

# Batch Rename Skill

## 工具

- `fs.list(dir, pattern)`:列出匹配文件
- `fs.rename(old, new)`:重命名

## Instructions

1. 用 `${pattern}` 匹配 `${directory}` 下所有文件
2. 对每个文件,根据 `${replacement}` 计算新文件名
3. 如果 `dry_run=true`,只输出计划不执行
4. 如果 `dry_run=false`,执行前**必须**请求用户确认

## Safety

`dangerous` 等级的 Skill 执行前会弹出确认对话框,需要用户点击"同意"。
```

**调用**:

```python
result = await agent.run(
    "批量重命名",
    skills=["batch-rename"],
    inputs={
        "directory": "~/Documents/notes",
        "pattern": "*.txt",
        "replacement": "2026-08-17-{name}.md",
        "dry_run": False,
    },
)
```

---

## 任务图规划

**目标**:让 Agent 规划"为 FnixAgent 添加 Docker 部署"这个任务。

```python
# examples/06_task_graph.py
import asyncio
from fnixagent import Agent, PlanEngine

async def main():
    agent = Agent(provider="openai", enable_planning=True)

    # 启动一个 KTG 节点
    ktg_node = await agent.ktg.create(
        title="为 FnixAgent 添加 Docker 部署",
        horizon="2026-Q3",
        parent="ktg.deployment",
    )

    # 自动分解为 STP 周计划
    stp_plan = await agent.stp.from_ktg(ktg_node.id)
    for milestone in stp_plan.milestones:
        print(f"[{milestone.status}] {milestone.title}")

    # 进一步分解当前周为 MFP 执行步骤
    current_week = stp_plan.current_week()
    mfp = await agent.mfp.from_stp(current_week.id)
    print(f"\n本周 {len(mfp.steps)} 步:")
    for step in mfp.steps:
        deps = ",".join(step.deps) or "(root)"
        print(f"  [{deps}] {step.tool}({step.args})")

asyncio.run(main())
```

**输出**:

```
[done]     完成 Dockerfile 多阶段构建
[done]     配置 docker-compose.yml
[in_progress] 通过 CI 自动化构建
[pending]   推送镜像到 ghcr.io
[pending]   写部署文档

本周 3 步:
  [(root)]    fs.read(config/agentd.yaml)
  [step1]     shell.run(docker build -t fnixagent:dev .)
  [step2,step3] llm.generate(写部署文档)
```

---

## BYOK 配置

**目标**:把  LLM Key 存进 OS Keychain。

```bash
# 交互式
fnix key set --provider=openai
> Enter API Key: sk-...
> ✓ Stored in macOS Keychain

# 非交互式(脚本场景)
fnix key set --provider=openai --from-stdin <<< "sk-..."

# 查看已存 Key(只显示 provider,不显示值)
fnix key list
> openai     (macOS Keychain)
> anthropic  (macOS Keychain)

# 清除
fnix key delete --provider=openai
```

**加密便携模式**:

```bash
# 导出为加密文件
fnix key export --mode=encrypted --output ~/keystore.enc
> Enter master password: ******
> ✓ Encrypted with Argon2id, AES-256-GCM

# 在新机器导入
fnix key import --input ~/keystore.enc
> Enter master password: ******
> ✓ Decrypted and imported
```

---

## 完整示例:做一个完整项目

[`examples/full-project/`](./examples/full-project/),演示从需求到
部署的完整流程。

---

## 更多示例

- [`examples/07_mcp_integration.py`](./examples/07_mcp_integration.py) — 接 MCP 服务器
- [`examples/08_memory_search.py`](./examples/08_memory_search.py) — 语义检索记忆
- [`examples/09_stp_reflect.py`](./examples/09_stp_reflect.py) — STP 回写 KTG
- [`examples/10_skill_chaining.py`](./examples/10_skill_chaining.py) — Skill 链式调用
- [`examples/11_react_ui.py`](./examples/11_react_ui.py) — React UI 中嵌入
- [`examples/12_headless_cli.py`](./examples/12_headless_cli.py) — 无 UI 命令行模式

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.