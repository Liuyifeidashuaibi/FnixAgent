# FnixForge — Agent 生产级熔炉

FnixForge 是 FnixAgent 独占的能力：**把你正在开发的（半成品的）Agent 放进熔炉，用专业 benchmark 反复锻打，暴露缺陷、自动修复、复测验证，直到生产级。**

这是 FnixAgent 区别于 Codex / Claude Code / TRAE / WorkBuddy 的核心功能：
它们只能写代码；FnixAgent 还能**给别人写的 Agent 做体检与治疗**。

```
┌─────────────────────────────────────────────────────────────┐
│  fnixagent forge fix /path/to/your-agent --suite core       │
│                                                             │
│   round 0  测评 19 道生产级基准题  ──► 通过 4/19 (21%)      │
│            诊断: 3 个失败簇                                  │
│            修复提案: agent.py, router.py                     │
│   round 1  全量复测(带回归)      ──► 通过 11/19 (58%)  kept │
│            诊断: 1 个失败簇                                  │
│            修复提案: parser.py                               │
│   round 2  复测出现回归          ──► rolled_back             │
│            换思路再修            ──► 通过 17/19 (89%)  kept  │
│   round 3  全量复测              ──► 通过 19/19 (100%)       │
│                                                             │
│   ✅ PRODUCTION READY  报告: forge-report.html              │
└─────────────────────────────────────────────────────────────┘
```

---

## 快速开始

```bash
# 0. 体验一把：我们内置了一个"故意带缺陷的半成品 Agent"
fnixagent forge test benchmarks/forge/sample-agent --suite smoke
fnixagent forge fix  benchmarks/forge/sample-agent --suite core --rounds 3 --report report

# 1. 对你自己的 Agent 项目:
fnixagent forge probe /path/to/your-agent --write   # 自动生成 forge.config.json
fnixagent forge test  /path/to/your-agent           # 先体检（只读，不动你的代码）
fnixagent forge fix   /path/to/your-agent --rounds 3 --report report
```

web 界面端: `POST /api/v1/forge/run`（SSE 事件流）/ `GET /api/v1/forge/suites` / `POST /api/v1/forge/probe`。

## 工作原理（六层）

| 层 | 模块 | 职责 |
|---|---|---|
| 接入层 | `core/forge/probe.py` + `adapters.py` | 自动探测目标 Agent 调用方式（CLI / HTTP / Python），统一为 `invoke(prompt, workspace)` |
| 测评层 | `core/forge/spec.py` | 题目 schema；19 道内置基准随 FnixAgent 分发（独占资源） |
| 执行层 | `core/forge/runner.py` | 每题独立沙箱、文件指纹快照、越界检测 |
| 判定层 | `core/forge/checks.py` | **确定性**校验（不用 LLM 打分，可重复可回归） |
| 诊断层 | `core/forge/diagnose.py` | 失败聚类 + 在目标项目源码中定位最可能相关的文件 |
| 修复层 | `core/forge/fixer.py` + `loop.py` | Git 守卫下用 FnixAgent 自己的 LLM 修目标代码；**回归即回滚** |

## 被测 Agent 接入（forge.config.json）

Forge 对你的 Agent 形态零假设。在目标项目根目录放 `forge.config.json`（可由 `forge probe --write` 自动生成）：

**CLI 形态**（最常见）:

```json
{
  "type": "cli",
  "command": "python main.py",
  "env": {"MY_AGENT_MODE": "benchmark"}
}
```

每次测评，Forge 会注入环境变量：

- `FNIX_FORGE_WORKSPACE` — 沙箱目录（你的 Agent 应在此目录内工作）
- `FNIX_FORGE_PROMPT_B64` — base64 编码的任务 prompt

命令模板占位符: `{prompt}` `{prompt_b64}` `{workspace}`。

**HTTP 形态**（Agent 是个服务）:

```json
{
  "type": "http",
  "endpoint": "http://127.0.0.1:8080/chat",
  "body_template": {"prompt": "{prompt}", "workspace": "{workspace}"},
  "response_field": "choices.0.message"
}
```

## 题目 schema（编写你自己的套件）

套件放在 `benchmarks/forge/suites/<名字>/`，一个 JSON 一道题：

```json
{
  "id": "my-001",
  "title": "example",
  "prompt": "在当前目录创建 answer.txt，内容为 42",
  "capability": "instruction_following",
  "difficulty": 2,
  "setup": {"files": {"input.txt": "..."}},
  "allowed_scope": ["answer.txt"],
  "protected": ["input.txt"],
  "checks": [
    {"function": "file_equals", "args": {"path": "answer.txt", "content": "42"}},
    {"function": "scope_respected", "args": {}},
    {"function": "protected_untouched", "args": {}}
  ]
}
```

**能力维度**（影响能力矩阵报告）: `instruction_following | file_edit | code_gen | tool_use | multi_step | context_retrieval | output_contract | error_recovery | safety | language`

**内置检查函数**:

| 函数 | 作用 |
|---|---|
| `file_exists` / `file_not_exists` | 文件存在性 |
| `file_contains` / `file_not_contains` | 文件含/不含文本或正则 |
| `file_equals` | 文件内容精确相等 |
| `file_json_field` | JSON 字段断言（dot pointer） |
| `stdout_match` / `message_match` | 进程输出 / HTTP 响应匹配 |
| `exit_code` | 进程退出码 |
| `command_succeeds` | **沙箱内跑任意验证命令**（编译、单测、linter），可断言 stdout 正则 |
| `scope_respected` | 只改动了 `allowed_scope` 内的路径 |
| `protected_untouched` | `protected` 路径未被改动 |

## 评分与生产级判定

- 每道 required check 未过 → 本题不得"通过"，且分数封顶 40%
- 套件总分 = 难度加权的通过率（难度 1~5 权重 1.0~2.5）
- **PRODUCTION READY** = 总分 ≥ 阈值（默认 90%）且所有能力维度均 ≥ 阈值

## 安全保证（fix 模式）

1. 修复前自动建立 Git 基线（非 git 项目会自动 `git init` + 基线提交）
2. 每轮修复后**全量复测**，不只重跑失败题
3. 出现任何回归 → `git reset --hard` 立即回滚，不保留半吊子修复
4. 无净进步的修复同样回滚，保持历史干净
5. 被保留的修复以 `fnix-forge: round N fix` 提交，随时可审计
6. 测评沙箱与目标源码完全隔离，benchmark 本身不会污染你的项目

## 独占设计

- benchmark 套件（`benchmarks/forge/`）只随 FnixAgent 分发
- 修复能力直接复用 FnixAgent 自身的 LLM 接入（BYOK），不依赖外部服务
- 用户必须安装 FnixAgent 才能享受"把自己的 Agent 练到生产级"这项能力
