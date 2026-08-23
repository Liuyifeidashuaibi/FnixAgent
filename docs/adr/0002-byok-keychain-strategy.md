---
adr_id: 0002
title: BYOK (Bring-Your-Own-Key) 凭据存储策略
status: Accepted
date: 2026-08-13
deciders: FnixAgent Core Team, Security WG
consulted: Privacy WG
informed: All contributors
supersedes: null
superseded_by: null
tags: [security, privacy, byok]
---

# ADR-0002: BYOK 凭据存储策略

## Context (背景)

FnixAgent 用户使用云端 LLM ( LLM /  / DeepSeek) 时必须提供 API Key。

需求:

1. **零信任**:FnixAgent 服务端永远不能获取用户的 API Key
2. **加密落盘**:Key 在磁盘上必须加密,不能明文
3. **跨平台**:Windows / macOS / Linux 都要支持
4. **便携**:用户可以备份 / 迁移配置文件
5. **可撤销**:用户可以一键清除所有 Key

候选方案:

| 方案 | 安全 | 跨平台 | 便携 | 备注 |
| --- | --- | --- | --- | --- |
| OS Keychain (Keychain/Credential Manager/Secret Service) | ★★★★★ | ✓ | ✗ | 系统绑定,不能跨设备 |
| AES-256-GCM + 本地口令派生 (Argon2id) | ★★★★ | ✓ | ✓ | 需用户口令 |
| 明文文件 | ✗ | ✓ | ✓ | 禁用 |
| 云端托管 | ✗ | ✓ | ✓ | 违反隐私 |

## Decision (决策)

**采用双模式,默认 OS Keychain,可选加密文件**:

### 模式 A (默认):OS Keychain

- macOS: Keychain Services (`security find-generic-password`)
- Windows: Credential Manager (`wincred` via `keyring` crate)
- Linux: Secret Service (`org.freedesktop.secrets` via D-Bus)

Rust 端通过 [`keyring-rs`](https://crates.io/crates/keyring) crate 访问,Python 端通过 `keyring` (PyPI) 包访问。

### 模式 B (高级用户):加密便携文件

- 用户提供一个 master password
- Key 用 **Argon2id** (m=64MB, t=3, p=4) 派生 32B key
- 用 **AES-256-GCM** 加密 API Key
- 加密文件存放在 `~/.fnix/keystore.enc`
- 文件可拷贝到 U 盘备份 / 跨设备迁移

### 凭据生命周期

```
created → loaded → in-memory → written → rotated → revoked
                  (内存中明文)    (持久化加密)    (过期)    (清除)
```

- 内存中的明文仅在请求中使用,**用完即清零**
- 每次应用启动重新从 Keychain / 文件加载

## Consequences (后果)

### 正面

- 用户 Key 永不离开本机 (零信任)
- 满足 GDPR / 个保法 "最小必要" 原则
- 模式 B 可备份 / 跨设备,提升用户体验

### 负面 / 风险

- 模式 A 重装系统后 Key 丢失 (用户文档需要说明)
- 模式 B 口令忘了 = Key 永久丢失 (无密码找回路径)
- Linux 无桌面环境时 (headless) 模式 A 不可用 → 必须回退到模式 B

### 缓解

- 安装时引导用户选择模式,并在 README 明确说明后果
- 提供 `fnix key export --encrypted` 命令,允许用户主动备份
- 模式 B 失败 3 次自动锁定,防止暴力破解

## Alternatives Considered (备选方案)

- **1Password / Bitwarden CLI 集成**:安全性高但依赖外部软件,排除
- **云 KMS (AWS KMS / Vault)**:违反零信任原则,排除

## References (参考)

- [OWASP Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [Argon2 RFC 9106](https://datatracker.ietf.org/doc/html/rfc9106)
- 内部分享: `SECURITY.md` v2.0

## Notes (备注)

任何外部贡献 PR 中包含真实 API Key 都会被 `gitleaks` pre-commit 钩子拦截。