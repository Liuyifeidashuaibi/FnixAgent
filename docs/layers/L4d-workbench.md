# L4d — Fnix Workbench（自有前端）

## 栈（冻结）

**React 19 + Tauri 2 + Tailwind 4 + Monaco**

## 来源与归属

| 项 | 说明 |
|----|------|
| 产品 UI | `apps/workbench` — **Fnix 自有维护** |
| 历史来源 | PunamIDE（MIT）布局与编辑器壳，已品牌化并接入 Harness |
| 许可留存 | `LICENSE-MIT-PUNAMIDE` + `NOTICE.md` |
| 参考 | 上游克隆按需 `pnpm refs:clone`；Locus/Electron/Web/Admin 已从仓库移除 |

## Fnix 化要点

- 身份 / Prompt：Fnix Harness · BYOK · 无登录
- 配置：`fnix-settings*.json`；同步 `PUT /api/v1/harness/config`
- 工程布局：打开目录时 `ensure` → `{workspace}/.fnix`
- 规则文件：`.fnix/rules.md`、`AGENTS.md`、`AGENTS.override.md`
- 数据目录：`.fnix-backups`、本机 `fnix` app data（非上游名）

## 启动

```bash
pnpm install
pnpm --filter @fnixagent/workbench tauri:dev
# 或
pnpm dev:all:tauri
```
