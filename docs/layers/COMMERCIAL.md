# Fnix 开源 / 商业双轨（定稿）

> 状态：**定稿（L6）** · 主仓许可证：**Apache-2.0**  
> 原则：商业能力用 **profile / 文档 / 部署形态** 隔离，不污染默认 `pnpm dev`；不另起闭源 fork。

---

## 1. Community（开源轨）

| 项 | 约定 |
|----|------|
| 许可证 | Apache-2.0（仓库根 [`LICENSE`](../../LICENSE)） |
| Profile | `FNIXAGENT_PROFILE=standalone`（默认） |
| 账号 | **无**强制注册 / 手机号 / Google |
| LLM | **BYOK**；`FNIX_API_ONLY=1`；不代付 |
| 数据 | `~/.fnix` 本机；Key 可进 OS Keychain |
| 分发 | GitHub Release：**Community** Tauri 安装包 |
| 入口 | Download → 打开 → 引导 → Work/Code |

```bash
pnpm setup && pnpm doctor && pnpm dev:all:tauri
pnpm prepare:release   # 图标 + bundle Python + verify
pnpm build             # 本地打安装包
# 或：git tag v1.0.0-beta.1 && git push origin v1.0.0-beta.1
```

详见 [`../BETA_RELEASE.md`](../BETA_RELEASE.md)、[`../OPEN_SOURCE.md`](../OPEN_SOURCE.md)。

---

## 2. Enterprise / Commercial（企业轨）

| 项 | 约定 |
|----|------|
| Profile | `FNIXAGENT_PROFILE=cloud` |
| 认证 | JWT / RBAC（**非** Desktop Community 主路径） |
| 部署 | [`../DEPLOY.md`](../DEPLOY.md)（Docker / 反向代理） |
| LLM | 企业自管网关或 BYOK；**不**把「Fnix 代付」当作个人桌面默认 |
| 分发 | 部署指南 + 可选企业支持（商业条款在仓外） |
| 门控 | `FNIXAGENT_PROFILE` / env；默认 standalone 不加载企业强制依赖 |

**双轨禁止**：

- 用强制登录锁死 Community Desktop
- Hermes 式消息网关 / Portal OAuth 作为主产品
- 默认遥测上传用户代码与 Key

---

## 3. Feature 边界速查

| 能力 | Community | Enterprise |
|------|-----------|------------|
| Work / Code 本机 | ✅ | ✅ |
| BYOK | ✅ 必须 | ✅（或企业网关） |
| 无账号打开 Desktop | ✅ | 可选（连私有 agentd 时可 JWT） |
| 多用户 JWT / RBAC | ❌ 默认关 | ✅ |
| 公网多租户 SaaS | ❌ | 企业自建自负 |
| GitHub Community 安装包 | ✅ | — |
| 企业部署手册 | 参考 | ✅ 主路径 |

代码入口：[`src/fnixagent/core/profile.py`](../../src/fnixagent/core/profile.py)（`standalone` / `cloud`）。

---

## 4. Release notes 模板

**Community**

> Fnix Harness Community `vX.Y.Z` — 本地 Work/Code，BYOK，无账号。  
> 下载对应平台安装包；Key 仅存本机。

**Enterprise**

> 企业部署请使用 `FNIXAGENT_PROFILE=cloud` 并参阅 `docs/DEPLOY.md`。  
> 与 Community 安装包分离；不要求个人用户登录。

---

## 5. 定稿检查清单

- [x] 本文件定稿并链到 layers INDEX
- [x] `OPEN_SOURCE.md` 指向 Community
- [x] `DEPLOY.md` 标明 Enterprise / cloud
- [x] 默认 profile = standalone
- [x] README 区分两条路径
