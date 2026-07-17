# 姊妹项目 · FnixAi

FnixAgent 与 **FnixAi** 是两个**独立产品**，并行开发、互相吸收，无 monorepo 依赖。

| | **FnixAgent**（本仓） | **FnixAi** |
|---|---|---|
| 定位 | 当前流行向：学习 / 教育 / 办公智能 Agent | 未来趋势向：全 Rust 自治软件工程 AgentOS |
| 仓库 | [Liuyifeidashuaibi/FnixAgent](https://github.com/Liuyifeidashuaibi/FnixAgent) | [Liuyifeidashuaibi/FnixAi](https://github.com/Liuyifeidashuaibi/FnixAi) |
| 本地 | `E:\FNIX\FnixAgent` | `E:\FNIX\FnixAi` |
| 主栈 | Python + FastAPI + Web/Desktop | Rust `fnix-se` |

## `fnix-se/` 迁移说明

**Canonical（唯一真相）在 FnixAi**，不在本仓：

- GitHub：https://github.com/Liuyifeidashuaibi/FnixAi
- 本地：`E:\FNIX\FnixAi\fnix-se`
- 文档：`PROJECT_OVERVIEW.md`、`OPEN_TASKS.md`

本仓 `.gitignore` 已忽略 `/fnix-se/`：本地可留副本方便对照，**不会推上本仓 GitHub**。  
迁出说明见 [`archive/AGENTOS_MOVED.md`](./archive/AGENTOS_MOVED.md)。

## 互相吸收（不合并代码树）

**本仓 → FnixAi：** 场景工具经验、业务协议形状、评测思路（不迁办公主线进 Ai）。  
**FnixAi → 本仓：** MCP/LSP 协议形状、Meta Context/PDG 思路、durable/txn 工程模式（Python 侧择优移植）。

详细未完成任务在 FnixAi 的 `OPEN_TASKS.md`。
