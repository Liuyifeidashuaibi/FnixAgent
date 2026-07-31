# Fnix Desktop Tauri — packaging shell (legacy)

> **不要用这个包做日常开发。** 日常只开 `apps/workbench`：`pnpm dev`。

本目录曾是独立 Tauri 壳，与 workbench **同名同 identifier（`com.fnix.agent`）**，会抢占 `:5175`、WebView 用户数据，并出现「两个 Fnix 窗口、一个 Offline」的混乱。

现已改为：

| 项 | 值 |
|---|---|
| productName | `Fnix Packaging` |
| identifier | `com.fnix.agent.packaging` |
| `pnpm --filter @fnixagent/desktop-tauri dev` | **重定向到 workbench** |
| 真正打包调试 | `pnpm --filter @fnixagent/desktop-tauri dev:packaging`（少用） |

## 正确入口

```bash
pnpm dev                 # workbench Tauri（唯一产品壳）
pnpm build               # workbench 安装包
# 或仍走本包资源预打包：
pnpm --filter @fnixagent/desktop-tauri build
```

## 架构（打包时）

```
apps/desktop-tauri (资源 / 可选安装包壳)
  └─ UI dist from @fnixagent/workbench
```

Python agentd + fnix-local 由 workbench `runtime.rs` 或外部 `FNIXAGENT_BACKEND_URL` 管理。
