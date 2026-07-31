# FnixAgent 项目状态（测试版 · Standalone）

> 更新：2026-07-18 · 无域名 / 无云服务器时的默认形态

## 当前形态

| 项 | 状态 |
|---|---|
| 部署 Profile | `standalone`（默认） |
| 客户端 | Electron + Mantine Desktop |
| 后端 | 本机 Python FastAPI |
| 存储 | JSON 用户 + Harness sessions + KTG 快照 |
| 本地引擎 | fnix-local sidecar（Python MVP → Rust） |
| 参考库 | `_references/`（`pnpm refs:clone`） |
| LLM | BYOK（用户 `.env` 或 Desktop 设置） |
| 云 / 域名 | **不需要**（测试版） |

## 黄金路径

```bash
pnpm dev:all
```

1. 登录（或所有者通道）
2. 打开本地文件夹
3. Work 模式发任务 → KTG/STP/MFP 流式 → 产物验收

## 命令

| 命令 | 说明 |
|---|---|
| `pnpm dev:all` | fnix-local + API + Desktop 三进程 |
| `pnpm dev:local` | 仅 fnix-local sidecar |
| `pnpm refs:clone` | 克隆参考仓库到 `_references/` |
| `pnpm dev:api` | 仅 Python API |
| `pnpm smoke:standalone` | profile 单元测试 + 可选 health |
| `pnpm --filter @fnixagent/desktop build` | 打包 Desktop |

## 以后升级

| 阶段 | 操作 |
|---|---|
| 本机 Docker | `FNIXAGENT_PROFILE=local-stack` + `docker-compose.lite.yml` |
| 自有 VPS | `FNIXAGENT_PROFILE=cloud` + `docs/DEPLOY.md` |
| Rust 本地引擎 | 姊妹仓 [FnixAi](https://github.com/Liuyifeidashuaibi/FnixAi) → fnix-local sidecar |

## 文档索引

- [QUICKSTART.md](./QUICKSTART.md) — 10 分钟上手
- [DESKTOP_PRODUCT.md](./DESKTOP_PRODUCT.md) — 产品主线
- [EVOLUTION_CORE.md](./EVOLUTION_CORE.md) — KTG/STP/MFP
- [DEPLOY.md](./DEPLOY.md) — 买服务器后
