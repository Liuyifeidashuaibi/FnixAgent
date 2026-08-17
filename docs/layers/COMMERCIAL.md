# Fnix 发布策略（定稿）

> 状态：**定稿（L6）** · 主仓许可证：**Proprietary（专有软件）**
> 原则：本地优先，BYOK，用户下载安装包后本地使用，无账号无注册。

---

## 1. 产品形态

| 项 | 约定 |
|----|------|
| 许可证 | 专有软件许可（仓库根 [`LICENSE`](../../LICENSE)） |
| Profile | `FNIXAGENT_PROFILE=standalone`（默认） |
| 账号 | **无**强制注册 / 手机号 / Google |
| LLM | **BYOK**；`FNIX_API_ONLY=1`；不代付 |
| 数据 | `~/.fnix` 本机；Key 可进 OS Keychain |
| 分发 | GitHub Release：Tauri 安装包 |
| 入口 | Download → 打开 → 引导 → Work/Code |

```bash
pnpm setup && pnpm doctor && pnpm dev:all:tauri
pnpm prepare:release   # 图标 + bundle Python + verify
pnpm build             # 本地打安装包
# 或：git tag v1.0.0-beta.1 && git push origin v1.0.0-beta.1
```

详见 [`../BETA_RELEASE.md`](../BETA_RELEASE.md)。

---

## 2. 功能边界

| 能力 | 说明 |
|------|------|
| Work / Code 本机 | ✅ 核心功能 |
| BYOK | ✅ 必须，用户自带 API Key |
| 无账号打开 Desktop | ✅ 默认 |
| 多用户 JWT / RBAC | 代码层保留接口，桌面产品不启用 |
| GitHub 安装包 | ✅ 主分发渠道 |

代码入口：[`src/fnixagent/core/profile.py`](../../src/fnixagent/core/profile.py)（`standalone` / `cloud`）。

---

## 3. Release notes 模板

> FnixAgent `vX.Y.Z` — 本地 Work/Code，BYOK，无账号。
> 下载对应平台安装包；Key 仅存本机。

---

## 4. 定稿检查清单

- [x] 本文件定稿并链到 layers INDEX
- [x] 默认 profile = standalone
- [x] README 描述产品定位
- [x] LICENSE 为专有软件许可
