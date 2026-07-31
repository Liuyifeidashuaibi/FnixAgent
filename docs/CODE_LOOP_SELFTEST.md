# 内部自测：Code 全流程闭环

> 场景：**新建项目 → AI 编写代码 → 自动编译 → 报错修复**  
> 命令：`pnpm smoke:code-loop`  
> 日期：2026-07-18

## 链路

```text
ensure_project_layout({tmp}/.fnix)
    → CodingAgent PLAN（脚本化 LLM：写坏逻辑 + 测试）
    → EXECUTE write/compile/test（test 失败不中断）
    → REVIEW（compileall + pytest）失败
    → HEAL（带报错再规划 edit → compile → test）
    → REVIEW 通过 → COMPLETED
```

## 本轮实现

| 项 | 说明 |
|----|------|
| `CodeTools.compile_check` | `py_compile` / `compileall` |
| `CodingAgent` compile 步骤 + Review 编译门 | 语法先于测试 |
| Heal 闭环 | `FNIX_CODE_HEAL_ROUNDS`（默认 2） |
| test/compile 步骤失败不炸整任务 | 进入 Review→Heal |
| 集成测 | `tests/integration/test_code_loop_closed.py` |

## 验收证据

```bash
pnpm smoke:code-loop
# → 2 passed
# → [smoke:code-loop] OK — 新建项目→写码→编译→修错 闭环通过
```

无需真实 API Key（`ScriptedCodeLLM`）。真 Key 路径仍走同一 Agent。
