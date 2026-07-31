# FNIX-SE 参考仓改造备忘（非产品主线）

> **降级说明（2026-07-17）**  
> 本文**不是**执行计划。产品主线见 [`FNIX-SE-IMPLEMENTATION-PLAN.md`](./FNIX-SE-IMPLEMENTATION-PLAN.md)。  
> FNIX-SE 是 **AgentOS / 自治软件工程运行时**，**不是**办公文档 Agent。

---

## 可用原则

| 原则 | 含义 |
|---|---|
| 改造优先 | `_references` 能 wrap/移植算法就用，不整仓重写 |
| 内核自有 | txn / Durable / PDG / 进化不交给参考仓 |
| 许可红线 | Apache/MIT 可移植；**Zed GPL 禁止并入** |
| 依赖隔离 | grok-build **不**整仓 `path=` |

---

## 对 AgentOS 有用的改造（保留）

| 参考 | 用法 | 状态 |
|---|---|---|
| grok-build | grep / edit / 截断等工具行为 → `fnix-tools` | grep + search_replace 已接 |
| markitdown | 可选：文档→md 进上下文（通用，非办公产品） | L1 wrap 已有 |
| （通用）MCP/LSP | 蓝图 L4 **通用**协议，后置 | 未做 |

## 明确降权 / 不做主线（旧办公痕迹）

| 项 | 处理 |
|---|---|
| Office-Word-MCP sidecar | **不排期**；`office_word_catalog` 可留可不进默认成功标准 |
| OfficeBench | **不作为**阶段 6 主评测（改用 SWE 等） |
| open-office-agent | 仅安全模式参考，非产品方向 |

---

## 与主计划关系

- Wave A/B 中与 **代码 Agent 工具**相关的已落地部分：继续用。  
- 原 Wave C「Office sidecar / OfficeBench」：**取消主线任务**。  
- 进度与门禁：**只认** IMPLEMENTATION-PLAN。
