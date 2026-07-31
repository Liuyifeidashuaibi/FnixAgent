# Fnix v1.0.0-beta 发布指南

> **主产品**：Tauri 2 Desktop（`apps/workbench`，唯一开发与发行壳）  
> **后端**：Python agentd + fnix-local sidecar（Standalone 零 Docker）

## 本地验收

```bash
pnpm install
pip install -r requirements.txt && pip install -e ".[dev,security]"

# 完整 Beta 验收（pytest + typecheck + cargo + e2e:standalone）
pnpm verify:beta

# 仅 API 端到端（自动 spawn 后端）
pnpm e2e:standalone

# 三进程 + Tauri UI（pnpm dev:all 等价）
pnpm dev:all:tauri
```

可选 API 冒烟（需另开 `pnpm dev:api` 或使用 dev:all）：

```bash
SMOKE_WITH_API=1 pnpm verify:beta
# 或
pnpm e2e:api
```

## 发布前准备

```bash
pip install "pyinstaller>=6.0"   # 自包含 agentd（无系统 Python）
pnpm prepare:release
# → 生成 app-icon.png + tauri icons
# → PyInstaller one-folder → resources/agentd/fnix-agentd
# → smoke:clean-vm（bundled /health + capability gate）
# → verify:beta
# → SHA256SUMS + SBOM stub → dist-release/
```

### 签名 / Updater（密钥就绪后）

1. 生成 Tauri updater 密钥对，把 **公钥** 写入 `apps/workbench/src-tauri/tauri.conf.json` → `plugins.updater.pubkey`
2. 在 GitHub Secrets 配置 `TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`
3. Windows Authenticode / macOS notarization 证书按平台另行配置
4. Release 工作流已预留上述 env；未配置时仍可打出未签名安装包

## 本地打包安装包

```bash
pnpm --filter @fnixagent/workbench tauri:build
# Windows: apps/workbench/src-tauri/target/release/bundle/nsis/*.exe
# macOS:   .../bundle/dmg/*.dmg
# Linux:   .../bundle/deb/*.deb 或 appimage
```

前置：安装 [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/)。

**Windows**：Release 打包推荐 MSVC（见 `src-tauri/.cargo/config.toml.example`）。开发 `cargo check` 用默认 GNU 即可。

## GitHub Release（Community 安装包）

推送 tag 触发 CI：

```bash
git tag v1.0.0-beta.1
git push origin v1.0.0-beta.1
```

工作流：`.github/workflows/release.yml`（Tauri 三平台矩阵）。

产物上传为 GitHub Release 附件（pre-release 当 tag 含 `-beta`）。  
Release notes 标注 **Community**；企业部署另见 [`layers/COMMERCIAL.md`](./layers/COMMERCIAL.md) 与 [`DEPLOY.md`](./DEPLOY.md)。

## 架构（冻结）

```
Desktop (Tauri 2) → agentd:动态端口 → fnix-local:动态端口
                 ↘ ~/.fnix + {workspace}/.fnix
```

## 验收清单

- [x] `pnpm verify:beta` / `pnpm check:plan` 绿（自动）
- [x] `e2e:standalone` sidecar runtime=python
- [x] session 重启持久化（集成测试）
- [ ] `pnpm dev:all` 登录 + Work 流式任务（需 BYOK 手动）
- [ ] Code 模式 Composer 会话（需 BYOK 手动）
- [ ] Tauri 终端 Tab「本地 Shell」PTY（需手动）
- [ ] Token 存 OS Keychain（Tauri 登录后手动确认）
