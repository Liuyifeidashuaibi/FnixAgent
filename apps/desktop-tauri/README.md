# `@fnixagent/desktop-tauri`

> Tauri 2 桌面应用的 **生产打包配置**。
> 复用 `@fnixagent/workbench` 的前端,加上 Tauri 的原生 shell。

---

## 它是什么? / What is this?

`desktop-tauri` 是 FnixAgent 的**桌面分发形态**。它把 `@fnixagent/workbench`
的前端 (React UI) 与 Tauri 2 的 Rust 后端打包成:

- Windows: `FnixAgent_x.y.z_x64-setup.exe`
- macOS: `FnixAgent_x.y.z_aarch64.dmg`
- Linux: `fnixagent_x.y.z_amd64.AppImage`

---

## 与 `workbench` 的关系

```
┌──────────────────────────────────────────┐
│  apps/desktop-tauri (本包)                │
│                                          │
│  - tauri.conf.json                        │
│  - src-tauri/                            │
│    ├── Cargo.toml                        │
│    ├── src/main.rs         ◄── Rust 入口 │
│    ├── capabilities/                    │
│    ├── icons/             ◄── 各种尺寸   │
│    └── tauri.conf.json                   │
│                                          │
│  运行时加载:                              │
│  └─ apps/workbench/dist/  (前端 bundle) │
└──────────────────────────────────────────┘
```

`workbench` 可以**独立运行**(vite dev server + 浏览器),
`desktop-tauri` 提供**桌面原生能力**(窗口、文件系统、菜单、托盘)。

---

## 开发 / Develop

### 前置

- Node 20+
- Rust 1.75+ (`rustup install stable`)
- (Windows) WebView2 Runtime
- (Linux) `libwebkit2gtk-4.1-dev`

### 安装

```bash
pnpm install
```

### Dev 模式

```bash
pnpm dev
# 1. 启动 workbench vite dev server (port 5173)
# 2. 启动 tauri dev,加载 http://localhost:5173
```

### 构建

```bash
pnpm build
# 输出:
#   src-tauri/target/release/bundle/
#   ├── msi/FnixAgent_0.5.0_x64_en-US.msi
#   ├── deb/fnixagent_0.5.0_amd64.deb
#   ├── appimage/fnixagent_0.5.0_amd64.AppImage
#   └── dmg/FnixAgent_0.5.0_aarch64.dmg
```

---

## 配置 / Configuration

`src-tauri/tauri.conf.json`:

```json
{
  "productName": "FnixAgent",
  "version": "0.5.0",
  "identifier": "dev.fnixagent.app",
  "build": {
    "beforeBuildCommand": "pnpm --filter @fnixagent/workbench build",
    "frontendDist": "../workbench/dist"
  },
  "app": {
    "windows": [{
      "title": "FnixAgent",
      "width": 1280,
      "height": 800,
      "minWidth": 800,
      "minHeight": 600,
      "decorations": true,
      "transparent": false,
      "center": true
    }],
    "security": {
      "csp": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ipc: http://ipc.localhost"
    }
  },
  "bundle": {
    "active": true,
    "targets": ["msi", "deb", "appimage", "dmg"],
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  }
}
```

---

## Capabilities / 权限

每个能力在 `src-tauri/capabilities/*.json` 显式声明:

```json
// capabilities/default.json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default capabilities",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "core:window:default",
    "core:webview:default",
    "core:event:default",
    "dialog:default",
    "fs:default",
    "fs:allow-read-text-file",
    {
      "identifier": "fs:scope",
      "allow": [
        { "path": "$HOME/.fnix/**" },
        { "path": "$DOCUMENT/**" }
      ]
    }
  ]
}
```

---

## 国际化 / i18n

支持 11 种语言,通过 `apps/workbench/src/i18n/` 切换。
Tauri 窗口标题随语言动态切换。

---

## 自动更新 / Auto-update

通过 Tauri `updater` 插件:

```json
"plugins": {
  "updater": {
    "endpoints": ["https://github.com/Liuyifeidashuaibi/FnixAgent/releases"],
    "pubkey": "dW50cnVzdGVy...",
    "windows": {
      "installMode": "passive"
    }
  }
}
```

更新流程:

1. 应用启动 → 后台请求 endpoint
2. 收到新版本 → 提示用户
3. 用户确认 → 下载 + 校验签名
4. 重启安装

---

## 调试 / Debugging

```bash
# 开启 Rust 调试
RUST_LOG=debug pnpm dev

# 开启 WebView DevTools
pnpm dev -- --devtools

# 查看 Rust panic
RUST_BACKTRACE=full pnpm dev
```

---

## 安全 / Security

详见 [`docs/security/THREAT-MODEL.md`](../../docs/security/THREAT-MODEL.md)。

---

## 故障排查 / Troubleshooting

| 问题 | 解决 |
| --- | --- |
| macOS: "无法打开,无法验证开发者" | `xattr -d com.apple.quarantine /Applications/FnixAgent.app` |
| Linux: 缺 WebKitGTK | 见 [install.sh](../../install.sh) 自动检测 |
| Windows: WebView2 缺失 | `winget install Microsoft.EdgeWebView2Runtime` |
| 启动后白屏 | F12 → Console 看错误;见 [TROUBLESHOOTING.md](../../docs/operations/TROUBLESHOOTING.md) |

---

## 性能 / Performance

| 指标 | 目标 |
| --- | --- |
| 安装包 (Windows MSI) | < 30 MB |
| 安装包 (macOS DMG) | < 25 MB |
| 安装包 (Linux AppImage) | < 30 MB |
| 启动时间 | < 1.5 s |
| 空闲内存 | < 200 MB |

---

## 参考 / References

- [Tauri 2 文档](https://tauri.app/v2/)
- [Tauri 安全指南](https://tauri.app/v2/security/)
- [`@fnixagent/workbench`](../workbench/README.md)
- [`docs/adr/0001-tauri-desktop-runtime.md`](../../docs/adr/0001-tauri-desktop-runtime.md)

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.