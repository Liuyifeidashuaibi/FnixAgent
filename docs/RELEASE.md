# OfficeAgent 客户端发布指南

> Phase 2.6 — 全平台客户端(Win + macOS + Linux)+ 代码签名架构

本文档描述如何打包发布 OfficeAgent 桌面客户端,以及如何配置代码签名证书。

---

## 1. 本地开发打包(无证书)

不设置任何证书环境变量,直接运行:

```bash
# 单平台
pnpm --filter @officeagent/desktop build:win      # 产出未签名 .exe
pnpm --filter @officeagent/desktop build:mac      # 产出未签名 .dmg
pnpm --filter @officeagent/desktop build:linux    # 产出 AppImage + deb + rpm

# 全平台(仅在同平台 runner 上执行,跨平台需借助 CI)
pnpm --filter @officeagent/desktop build:all
```

产物路径:`apps/desktop/release/<version>/`

> 注意:macOS 上可同时构建 Win/Mac/Linux;Windows 上只能构建 Win;Linux 上只能构建 Linux/Win(不能构建 macOS,因 macOS 不允许跨平台签名)。

---

## 2. 代码签名配置

### 2.1 Windows EV 代码签名

**为什么需要**:Windows SmartScreen 对未签名程序会显示警告,影响用户体验。EV 证书签名后可立即建立声誉,跳过 SmartScreen 警告。

**证书获取**:
- 购买渠道:Sectigo / DigiCert / GlobalSign 等 CA(约 $200-400/年)
- 类型:**EV Code Signing Certificate**(比普通 OV 证书更严格,需 USB Token 或硬件 HSM,但 SmartScreen 立即信任)
- 文件格式:`.pfx`(Personal Information Exchange)

**配置 GitHub Secrets**:

| Secret 名 | 值 | 说明 |
|---|---|---|
| `CSC_LINK` | base64 编码的 .pfx 文件内容 | `base64 cert.pfx -w 0` 生成 |
| `CSC_KEY_PASSWORD` | .pfx 文件密码 | 证书导出时设置的密码 |

**本地设置**(可选,用于本地签名):
```bash
# PowerShell
$env:CSC_LINK = "C:\path\to\cert.pfx"   # 本地可用文件路径,CI 用 base64
$env:CSC_KEY_PASSWORD = "your-password"
pnpm --filter @officeagent/desktop build:win
```

### 2.2 macOS Developer ID + Notarization

**为什么需要**:macOS Gatekeeper 默认阻止未签名/未公证的应用运行。用户必须右键 → 打开才能运行,体验差。Developer ID 签名 + Notarization 后用户可双击直接运行。

**证书获取**:
- 加入 **Apple Developer Program**($99/年)
- 在 Developer Portal 创建 **Developer ID Application** 证书(用于签名)
- 在 Apple ID 网站创建 **App-Specific Password**(用于 notarytool 公证)

**配置 GitHub Secrets**:

| Secret 名 | 值 | 说明 |
|---|---|---|
| `CSC_NAME` | `Developer ID Application: Your Company (XXXXXXXXXX)` | Keychain 中证书的 Common Name |
| `APPLE_ID` | `you@example.com` | Apple Developer 账户邮箱 |
| `APPLE_APP_SPECIFIC_PASSWORD` | 16 位应用专用密码 | https://appleid.apple.com → 登录与安全 → 应用专用密码 |
| `APPLE_TEAM_ID` | 10 位字母数字 | Developer 账户 → Membership Details → Team ID |

**本地设置**(可选):
```bash
export CSC_NAME="Developer ID Application: Your Company (XXXXXXXXXX)"
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="xxxx-xxxx-xxxx-xxxx"
export APPLE_TEAM_ID="XXXXXXXXXX"
pnpm --filter @officeagent/desktop build:mac
```

> electron-builder 24.x 内置 Notarization:只需在 `electron-builder.yml` 的 `mac.notarize.teamId` 配置 teamId,并通过环境变量注入 Apple 凭据,签名后自动调用 `xcrun notarytool` 提交公证并轮询结果。

### 2.3 Linux 签名(可选)

Linux 桌面生态无强制签名要求,**默认不签名**。如需 GPG 签名:

```yaml
# electron-builder.yml 追加:
linux:
  signPackages: true
  # GPG 密钥通过环境变量 GPKey 注入
```

```bash
export GPKey=$(gpg --export-secret-keys --armor "your-gpg-key-id@officeagent.com")
```

---

## 3. CI 自动发布

### 3.1 触发方式

```bash
# 推送 v 前缀的 tag 自动触发发布
git tag v1.0.0
git push origin v1.0.0

# 或在 GitHub Actions 页面手动触发(workflow_dispatch)
```

### 3.2 工作流文件

| 文件 | 触发 | 作用 |
|---|---|---|
| `.github/workflows/ci.yml` | PR / push 到 main | 代码质量检查 + 单元测试 + Docker 构建验证 |
| `.github/workflows/build.yml` | push main / tag | Docker 镜像构建并推送 GHCR |
| `.github/workflows/release.yml` | tag `v*` | **桌面客户端三平台打包 + 发布 GitHub Releases** |

### 3.3 release.yml 流程

1. **三平台并行构建**(matrix: windows-latest / macos-latest / ubuntu-latest)
2. **代码签名**(根据平台注入对应证书 Secrets)
3. **上传到 GitHub Releases**(`electron-builder --publish always`)
4. **汇总发布 Release**(softprops/action-gh-release 聚合所有产物)
5. **CDN 同步**(可选,通过 `scripts/publish-cdn.sh`)

### 3.4 产物清单

| 平台 | 产物 | 文件名 |
|---|---|---|
| Windows | nsis 安装包 | `OfficeAgent-Setup-<version>.exe` |
| macOS (x64) | dmg | `OfficeAgent-<version>-x64.dmg` |
| macOS (arm64) | dmg | `OfficeAgent-<version>-arm64.dmg` |
| Linux (x64) | AppImage | `OfficeAgent-<version>-x64.AppImage` |
| Linux (x64) | deb | `OfficeAgent-<version>-x64.deb` |
| Linux (x64) | rpm | `OfficeAgent-<version>-x64.rpm` |
| Linux (arm64) | AppImage | `OfficeAgent-<version>-arm64.AppImage` |
| Linux (arm64) | deb | `OfficeAgent-<version>-arm64.deb` |
| 全平台 | 更新元数据 | `latest.yml` / `latest-mac.yml` / `latest-linux.yml` |

---

## 4. 自动更新

桌面客户端集成了 `electron-updater`,启动后自动从 GitHub Releases 检查更新。

**配置位置**:`apps/desktop/electron-builder.yml` 的 `publish` 字段
**实现代码**:`apps/desktop/src/main/updater.ts`

**更新流程**:
1. 应用启动 10 秒后检查更新
2. 发现新版本后自动后台下载
3. 下载完成通过 IPC 通知渲染进程(`updater:status` 事件)
4. 用户确认后调用 `quitAndInstall()` 重启安装

**禁用更新**(开发环境):
```bash
export OFFICEAGENT_DISABLE_UPDATER=1
```

> 注意:electron-updater 的签名校验仅对 macOS / Windows 生效(需要代码签名)。Linux AppImage 不校验签名,依赖 HTTPS 传输保证完整性。

---

## 5. GitHub Secrets 配置清单

在仓库 Settings → Secrets and variables → Actions → New repository secret 添加:

| Secret 名 | 必需 | 平台 | 说明 |
|---|---|---|---|
| `CSC_LINK` | 否 | Windows | base64 编码的 .pfx 证书 |
| `CSC_KEY_PASSWORD` | 否 | Windows | .pfx 密码 |
| `CSC_NAME` | 否 | macOS | Developer ID Application 证书名 |
| `APPLE_ID` | 否 | macOS | Apple ID 邮箱 |
| `APPLE_APP_SPECIFIC_PASSWORD` | 否 | macOS | Apple 应用专用密码 |
| `APPLE_TEAM_ID` | 否 | macOS | Apple Team ID |
| `CDN_RSYNC_HOST` | 否 | 全平台 | CDN 主机(可选) |
| `CDN_RSYNC_USER` | 否 | 全平台 | CDN 用户名(可选) |
| `CDN_RSYNC_KEY` | 否 | 全平台 | CDN SSH 私钥(可选) |

> `GITHUB_TOKEN` 自动提供,无需手动添加。

---

## 6. 故障排查

### 6.1 Windows 签名失败

```
Error: Could not find code signing certificate
```

**原因**:`CSC_LINK` 未配置或格式错误。
**解决**:
```bash
# 检查 base64 编码
base64 cert.pfx -w 0 | wc -c   # 应为证书文件大小的 ~1.33 倍
# 在 GitHub Secrets 中确认 CSC_LINK 的值无换行
```

### 6.2 macOS Notarization 失败

```
Error: Apple failed to notarize the application
```

**原因**:Apple ID 凭据错误,或应用包含未签名二进制。
**解决**:
```bash
# 查看详细公证日志(邮件会收到)
# 检查 Hardened Runtime 是否启用(electron-builder.yml: hardenedRuntime: true)
# 检查 entitlements 是否包含所有必需权限
```

### 6.3 Linux 包依赖缺失

```
error while loading shared libraries: libnss3.so
```

**原因**:目标系统缺少 electron 运行时依赖。
**解决**:deb/rpm 包已在 `electron-builder.yml` 的 `deb.depends` / `rpm.depends` 中声明依赖,安装时会自动拉取。AppImage 不依赖系统库(自带)。

---

## 7. 发布检查清单

发布新版本前确认:

- [ ] `apps/desktop/package.json` 的 `version` 字段已更新
- [ ] `apps/desktop/electron-builder.yml` 的 `copyright` 年份正确
- [ ] 图标文件已放置到 `apps/desktop/buildResources/`(icon.ico / icon.icns / icon.png)
- [ ] GitHub Secrets 已配置(如需签名)
- [ ] `CHANGELOG.md` 已更新(如存在)
- [ ] 本地 `pnpm --filter @officeagent/desktop typecheck` 通过
- [ ] 本地 `pnpm --filter @officeagent/desktop build:<platform>` 成功产出
- [ ] 推送 tag:`git tag v<version> && git push origin v<version>`
- [ ] 在 GitHub Releases 页面确认产物已上传
- [ ] 下载产物在本机验证可运行
