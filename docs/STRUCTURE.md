# Fnix Agent — 仓库结构（规范）

社区主产品路径：**Workbench（React + Tauri + Tailwind + Monaco）+ agentd（Python）**。

```text
FnixAgent/
├── apps/
│   ├── workbench/          # 唯一日常桌面：UI + src-tauri（pnpm dev）
│   ├── desktop-tauri/      # 遗留打包壳（勿与 workbench 同时开）
│   └── fnix-local/         # Rust 本地 sidecar（索引/沙箱，可降级）
├── src/fnixagent/          # Python agentd（默认 :8003）与 CLI
├── packages/
│   ├── protocol/           # 契约 / OpenAPI 相关
│   └── sdk/                # TS OpenAPI 客户端（可选）
├── scripts/                # setup / doctor / dev-all / e2e / release
├── docs/                   # 产品与分层文档（FNIX_PRODUCT.md 为准）
├── tests/                  # pytest
├── e2e/                    # Playwright（可选）
├── config/ · migrations/ · deploy/
└── ...
```

## 入口命令

| 命令                   | 作用                                      |
| ---------------------- | ----------------------------------------- |
| `pnpm setup`           | 安装依赖                                  |
| `pnpm doctor`          | 环境检查                                  |
| `pnpm dev`             | Workbench Tauri                           |
| `pnpm dev:all:tauri`   | fnix-local + agentd + Workbench           |
| `pnpm dev:api`         | 仅 agentd                                 |
| `pnpm e2e:api`         | API 冒烟                                  |
| `pnpm build`           | Workbench 生产构建                        |
| `pnpm build:packaging` | workbench Tauri 安装包（含 sidecar 资源） |

## 已移除（不再维护）

- Electron `apps/desktop`
- Locus 备份 `apps/workbench-locus-backup`
- 云端 `apps/web` / 企业 `apps/admin`（见 `docs/layers/COMMERCIAL.md` 若需另轨）
- Mantine 时代包：`packages/agent-ui`、`packages/ui`、`packages/ag-ui-mapper`

## 命名约定

| 旧                     | 新                     |
| ---------------------- | ---------------------- |
| `apps/workbench`       | `apps/workbench`       |
| `@fnixagent/workbench` | `@fnixagent/workbench` |
| `smoke:fnix`           | `smoke:fnix`           |
