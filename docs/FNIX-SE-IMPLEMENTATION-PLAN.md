# FNIX-SE 真正执行计划（AgentOS / 全 Rust）

> **唯一执行文档** · 2026-07-17 重对齐  
> **Canonical 已迁至姊妹仓 [FnixAi](https://github.com/Liuyifeidashuaibi/FnixAi)**（本地 `E:\FNIX\FnixAi`）  
> 本文件在 FnixAgent 内仅为过渡副本；请改 FnixAi 的同名文档与 `OPEN_TASKS.md`  
> 设计权威：[`FNIX-SE-Ultimate-Blueprint.md`](./FNIX-SE-Ultimate-Blueprint.md) **仅第一～十一章**  
> 姊妹关系：[`FNIXAI_SIBLING.md`](./FNIXAI_SIBLING.md)  
> 产品：**全 Rust AgentOS**（现属 FnixAi）；本仓主产品仍是办公/Python Agent

---

## 0. 文档与产品边界

| 文档 | 作用 | 要不要按它干活 |
|---|---|---|
| **本文** | 唯一执行勾选 | **要** |
| 蓝图 §一～§十一 | AgentOS 四层设计 | 查设计 |
| 蓝图附录 ch12+ | 历史噪声 / 旧办公与 Layer6 痕迹 | **否** |
| Python `src/fnixagent/` | 算法参考 | **否**（非并行产品） |
| `_references` / ADAPT | 可选工具改造 | 不重新定义产品 |

**硬规则：**

1. 产品 = **全 Rust `fnix-se` AgentOS**（自治软件工程运行时），**不是**办公套件。  
2. 不新建平行计划；不往蓝图写任务执行日志。  
3. 「蓝图/旧日志写已完成」≠ 完成；以 `cargo` / CLI / CI 为准。  
4. 冻结 Layer-6 crate 膨胀与 Office MCP / OfficeBench 主线排期。

---

## 1. 产品目标

建成 **FNIX-SE AgentOS**：Agent 是主体，CLI/编辑器是窗口。

```
L4  交互/协议     CLI · axum ·（后置）LSP/MCP · UI
L3  调度/进化     DAG · AgentLoop · 受控进化
L2  认知          PDG · Meta Context · 符号校验 · 记忆
L1  运行时        事务存储 · 沙箱 · Git · PTY
```

---

## 2. 当前真实状态

| 项 | 状态 |
|---|---|
| CLI 金路径 | `status` / `index` / `agent` / `run` / `pev` / `evolve` / `verify` / `git` / `pty` / `checkpoint` / `serve-mcp` / `serve-lsp` |
| Meta Context | PDG 符号排序注入 agent |
| PEV | `fnix pev` Plan→Execute→Verify 已通 |
| 进化 | `fnix evolve` 离线候选 + EvolutionGuard（`apply=false`） |
| Git / PTY | 最小接口：git CLI 封装 + process session（真交互 PTY 后置） |
| 沙箱 | wasmtime + 单测 |
| LLM | DashScope/千问 openai-compat |
| MCP | `fnix serve-mcp` stdio JSON-RPC，暴露全部 fnix 工具（initialize / tools/list / tools/call） |
| LSP | `fnix serve-lsp` stdio LSP 3.17，补全/悬停/跳转/引用/文档符号由 `.fnix/index/pdg_symbols.json` 驱动 |

---

## 3. 阶段

### 阶段 0–2

**完成**（核心绿编 + MVP 真 LLM 改码 + unstub run + wasmtime）。

### 阶段 3 · 认知 / 调度闭环

| ID | 任务 | 状态 | 证据 |
|---|---|---|---|
| 3.1 | PDG 符号目录注入 | **完成** | `pdg_symbols.json` |
| 3.2 | Meta Context 预算切片 | **完成** | `ContextAssembler` |
| 3.3 | verify ↔ PDG | **完成** | `fnix verify` |
| 3.4 | `run` 扩 write/replace | **完成** | 指令语法 |
| 3.5 | 进化离线+护栏 | **完成** | `fnix evolve` → `.fnix/evolution/candidates/` |
| 3.6 | Plan→Execute→Verify | **完成** | `fnix pev` 输出 `PEV CLOSED` |

### 阶段 4 · 协议（进行中）

| ID | 任务 | 状态 | 证据 |
|---|---|---|---|
| 4.1 | JSON-RPC 2.0 类型层（`fnix-protocol::jsonrpc`） | **完成** | `cargo test -p fnix-protocol` |
| 4.2 | 最小 MCP 服务端（initialize / tools/list / tools/call） | **完成** | `fnix-protocol::mcp` + `LineTransport` |
| 4.3 | CLI `serve-mcp`：ToolRegistry → MCP 桥接 | **完成** | stdio 实测 tools/list + tools/call |
| 4.4 | LSP↔PDG（补全/悬停/跳转/引用/文档符号） | **完成** | `fnix serve-lsp` + 索引含行列；协议层 32 tests |
| 4.5 | pyo3 bridge | 远期 | — |

### 阶段 5–6

UI 后置 · SWE 评测。

---

## 4. 进度板

| 阶段 | 状态 |
|---|---|
| 0–2 | **完成** |
| 3 认知/闭环 | **完成**（3.1–3.6） |
| 4 协议 | **完成**（4.1–4.4：MCP + LSP↔PDG；4.5 pyo3 远期） |
| 5–6 | 后置 |

---

## 5. 明确不做

- 办公专项 / OfficeBench  
- Python 全量迁移当里程碑  
- 蓝图追加执行日志  
- 新开 Layer6 crate / Zed GPL  
- 离线进化候选自动 apply 到线上  

---

## 6. 下一步（按序）

1. ~~L4：最小通用 MCP / LSP↔PDG~~ **完成**（`serve-mcp` / `serve-lsp`）  
2. L1：真交互 PTY（portable-pty）/ 可选 git2  
3. 评测脚手架（SWE）后置  

---

*实现只认本文勾选；蓝图 §一～§十一只回答「为什么这样设计」。*
