---
adr_id: 0001
title: 使用 Tauri 作为桌面端运行时
status: Accepted
date: 2026-08-12
deciders: FnixAgent Core Team
consulted: Security WG, Frontend WG
informed: All contributors
supersedes: null
superseded_by: null
tags: [architecture, desktop, tauri]
---

# ADR-0001: 使用 Tauri 作为桌面端运行时

## Context (背景)

FnixAgent 需要一个跨平台桌面运行时,承载以下工作负载:

1. 渲染 React 前端 (workbench UI)
2. 调用本地 LLM (Ollama / LM Studio) 与本地工具 (shell、文件系统)
3. 持有 BYOK (Bring-Your-Own-Key) 凭据,不能上传到云
4. 打包成 < 30 MB 的单文件安装包
5. 同时支持 Windows / macOS / Linux

候选方案:

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **Tauri 2** | 体积小、内存低、Rust 进程隔离、官方插件生态完善 | 部分原生能力需要 Rust 实现 |
| Electron | 生态最广、npm 兼容 | 体积 80+ MB、内存高 400+ MB、Chromium 安全面大 |
| Neutralino | 极致轻量 | 生态弱、调试体验差 |
| Flutter Desktop | UI 漂亮 | 与 Web 前端技术栈脱节 |

## Decision (决策)

**采用 Tauri 2 作为桌面运行时**,前端 React 18 + Vite,后端 Rust + Tokio。

### 进程模型(三进程)

```
┌─────────────────┐    IPC     ┌──────────────────┐
│  WebView 进程    │ ◄────────► │  Tauri Core 进程  │
│  (React UI)     │  invoke()  │  (Rust commands) │
└─────────────────┘            └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │  Sidecar 进程     │
                              │  (Python Agent)  │
                              └──────────────────┘
```

- WebView 进程:只跑 React UI,不能直接访问文件系统或网络
- Tauri Core 进程:Rust 实现,负责窗口管理、IPC、剪贴板、文件系统白名单
- Sidecar 进程:Python Agent 核心,通过 stdio JSON-RPC 与 Core 通信

### Capability 边界

- 浏览器侧 `window.__TAURI__` API 必须经过 `capabilities/*.json` 白名单过滤
- 任何 `shell.execute` 调用必须经过参数校验 (白名单 + 路径正则)
- 文件访问路径必须在 `tauri.conf.json` 的 `fs.allowList` 中声明

## Consequences (后果)

### 正面

- 安装包体积从 Electron 的 80+ MB 降到 6-12 MB
- 内存占用从 400+ MB 降到 80-150 MB
- Rust 侧天然抗 XSS / 任意命令执行
- 可以无缝集成 macOS Keychain / Windows Credential Manager (BYOK)

### 负面 / 风险

- Tauri 2 仍在快速迭代,部分插件 API 仍在 breaking
- Windows 上 WebView2 缺失时需要提示用户安装
- Linux 上 WebKitGTK 版本碎片化

### 缓解

- 锁定 Tauri 2.x 主版本,使用精确依赖版本
- 安装脚本 `install.ps1` / `install.sh` 自动检测 WebView2 / WebKitGTK
- 监控 Tauri GitHub release,出现 CVE 24h 内打补丁

## Alternatives Considered (备选方案)

参见上文表格。

## References (参考)

- [Tauri Security Model](https://tauri.app/v1/guides/distribution/security)
- [Tauri 2 Migration Guide](https://tauri.app/v2/guides/migrate/)
- 内部分享: `docs/architecture.svg` / `docs/security-layers.svg`

## Notes (备注)

本 ADR 不可被直接修改;若需变更,必须新增 ADR 并引用本文件 (`supersedes: 0001`)。