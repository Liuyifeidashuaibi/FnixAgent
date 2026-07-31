# Tauri v1.1 — 本地运行时 + PTY + Keychain

## 已实现

| 模块 | 说明 |
|------|------|
| `runtime.rs` | Standalone 自动拉起 fnix-local + agentd（无 env 时） |
| `secure.rs` | OS Keychain（keyring crate）存 JWT |
| `pty.rs` | portable-pty 本地 Shell + `pty-output` 事件 |
| `LocalPtyTerminal.tsx` | xterm.js 终端 UI |
| `TerminalPanel` | 本地 Shell / AgentOS 双 Tab |
| `bundle-python-runtime.mjs` | 同步复制到 `desktop-tauri/resources` |

## 启动

```bash
# 仅 Tauri（自动 spawn 三进程）
pnpm --filter @fnixagent/desktop-tauri dev

# 或 dev:all:tauri（外部 spawn，避免重复）
pnpm dev:all:tauri
```

## 参考

- Terax — PTY / 轻量壳
- IfAI — Harness 工具注册
