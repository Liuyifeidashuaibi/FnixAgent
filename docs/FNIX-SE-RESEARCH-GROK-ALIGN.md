# FNIX-SE × 参考仓 深度对照与工程路线

> 2026-07-17 · 研究产出（执行仍以 `FNIX-SE-IMPLEMENTATION-PLAN.md` 为准）  
> **产品 = 全 Rust AgentOS**；Office / Python 不是主线。

---

## 1. 一句话定位

| 产品 | 本质 |
|---|---|
| **Grok Build** | 终端编码助手 harness（Agent loop + tools + TUI） |
| **Cursor / Trae 类（Python 线）** | 人机协同 IDE 助手（本仓仅参考） |
| **FNIX-SE** | **事务化 + 可恢复 + 可进化** 的自治软件工程**运行时** |

FNIX-SE 要更强：不是第二个 Grok Build，而是在其工程模式之上加上 **txn / DurableExecutor / PDG / 受控进化**。

---

## 2. Grok Build → FNIX-SE（可抄 vs 禁抄）

### 可抄（模式）

1. Tool 三层：Description / typed Tool / Dispatch + Capabilities  
2. Agent = Definition + PromptContext + ToolBridge  
3. Turn 边界：before/after、路径锁、max_turns、无 tools → 完成  
4. Workspace 门面（工具不直接碰全局 FS）  
5. MCP / skills / hooks / subagents **独立扩展点**  
6. 输出截断与只读并发  

### 禁抄

1. 整份 TUI / pager  
2. 加密系统提示、xAI 私有协议与遥测  
3. `~/.grok` 路径字面量  
4. 用 rewind-checkpoint **替换** DurableExecutor  
5. Zed GPL / vendor 双工具集整库粘贴  

### Top 对齐落点

| # | Grok | FNIX-SE |
|---|---|---|
| 1 | `xai-tool-runtime` Tool/Dispatch | `fnix-agent/src/tool.rs` |
| 2 | `xai-grok-tools` bridge + register_all | `fnix-tools` |
| 3 | `xai-grok-shell` turn loop | `fnix-agent/src/loop_engine.rs` |
| 4 | `xai-grok-workspace` checkpoint | turn rewind **+** `fnix-checkpoint` WAL |
| 5 | MCP / skills / subagents | 阶段 4+（后置） |

---

## 3. 其它 `_references` 优先级

| 优先级 | 项目 |
|---|---|
| **现在有用** | grok-build（工具/循环模式）、markitdown（通用文档→md，非办公产品） |
| **降权 / 非主线** | Office-Word-MCP-Server、OfficeBench、open-office-agent |
| **MVP 忽略** | Zed GPL 复制、多 UI 框架并行 |

---

## 4. 现状（与执行计划对齐 · 2026-07-17）

- 阶段 0–2：**完成**（DashScope 改码、`run` 真工具、wasmtime、verify、CI 核心子集）  
- 阶段 3：**进行中**（PDG 增量 / Meta Context 深化）  
- 细节与勾选：**只认** [`FNIX-SE-IMPLEMENTATION-PLAN.md`](./FNIX-SE-IMPLEMENTATION-PLAN.md)

---

## 5. 与主计划关系

本文是对照研究，**不是**执行计划。门禁与下一步以 IMPLEMENTATION-PLAN 为准。
