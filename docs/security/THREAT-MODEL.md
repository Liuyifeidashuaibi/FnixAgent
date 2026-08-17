# 威胁建模 / Threat Model

> 本文件基于 **STRIDE** 框架系统化梳理 FnixAgent 的安全威胁与对策。
> 本文件**非**安全审计报告,而是工程实现指南。

---

## 一、系统模型 / System Model

### 数据流图(DFD)

```
                              ┌──────────────────────┐
                              │   LLM Provider       │
                              │   (OpenAI/Anthropic/  │
                              │    Ollama/...)       │
                              └──────────┬───────────┘
                                         │ HTTPS / HTTP
                                         │ (prompt, response)
              ┌──────────────────────────▼─────────────────────────┐
              │                                                     │
   ┌──────────▼──────────┐                                ┌─────────▼────────┐
   │  WebView (React UI) │ ◄── IPC invoke() ────────────► │  Tauri Core (R)  │
   │  - React 18         │                                │  - 窗口管理       │
   │  - 用户输入/输出     │                                │  - 文件白名单      │
   │  - 不持文件/网络     │                                │  - Capability 检查 │
   └─────────────────────┘                                └─────────┬────────┘
                                                                   │ stdio JSON-RPC
                                                          ┌────────▼────────┐
                                                          │  Python agentd  │
                                                          │  - LLM 客户端    │
                                                          │  - 记忆 / Skill  │
                                                          │  - 规划器         │
                                                          └────────┬────────┘
                                                                   │ subprocess
                                                          ┌────────▼────────┐
                                                          │  fnix-local (R)  │
                                                          │  - 沙箱执行      │
                                                          │  - 系统调用      │
                                                          └─────────────────┘
```

### 信任边界

```
┌────────────────────────────────────────────────────┐
│ Trust Boundary 1: 浏览器进程                        │
│ (前端 — 不可信)                                      │
│   ↓ invoke() 必须经过 capability 检查                │
├────────────────────────────────────────────────────┤
│ Trust Boundary 2: Rust 进程                        │
│ (特权上下文 — 受限但必要)                            │
│   ↓ stdio 命令必须经过参数校验                       │
├────────────────────────────────────────────────────┤
│ Trust Boundary 3: Python 进程                      │
│ (业务逻辑 — 受信任)                                  │
│   ↓ subprocess 命令必须经过白名单                    │
├────────────────────────────────────────────────────┤
│ Trust Boundary 4: fnix-local 沙箱                   │
│ (系统调用 — 受限)                                   │
│   ↓ 网络调用必须有显式允许                           │
└────────────────────────────────────────────────────┘
```

---

## 二、STRIDE 威胁清单

#### S — Spoofing (伪装)

| 威胁 | 攻击路径 | 风险等级 | 对策 |
| --- | --- | --- | --- |
| **T-S1** 伪造用户调用 agentd | 进程监听 127.0.0.1,本地任意进程可连 | 🟡 中 | (1) 启用 mTLS (2) Token 鉴权 (3) Unix socket 替代 TCP |
| **T-S2** 伪造 LLM 响应 | 中间人替换 OpenAI 响应 | 🟢 低 | HTTPS + 证书钉扎 (未来) |
| **T-S3** 伪造 Skill 文件 | 攻击者写入 `~/.fnix/skills/evil/` | 🟡 中 | (1) Skill 目录权限 0700 (2) 启动时校验签名 (3) gitleaks 扫描 prompt injection |
| **T-S4** Token 重放 | 捕获 API Key 重放 | 🟢 低 | TLS + 短期 token |

#### T — Tampering (篡改)

| 威胁 | 攻击路径 | 风险等级 | 对策 |
| --- | --- | --- | --- |
| **T-T1** 篡改记忆 | 直接修改 `~/.fnix/memory/*.md` | 🟡 中 | (1) 目录权限 0700 (2) 关键记忆加 hash (3) Git 历史可回滚 |
| **T-T2** 篡改配置 | 修改 `~/.fnix/config.yaml` | 🟢 低 | (1) 配置项 schema 校验 (2) 启动时签名校验 |
| **T-T3** 篡改 Skill prompt | 修改 SKILL.md 注入恶意指令 | 🟠 高 | (1) Skill 签名 (2) Prompt 注入检测 (3) 用户视觉确认 dangerous skill |
| **T-T4** WebView 注入 XSS | 渲染未转义内容 | 🟡 中 | React 默认转义 + CSP 头 + 禁用 eval |
| **T-T5** IPC 参数篡改 | WebView 调用 `shell.run` 注入 | 🟠 高 | (1) Capability 白名单 (2) 参数 schema 校验 (3) 白名单路径正则 |

#### R — Repudiation (否认)

| 威胁 | 攻击路径 | 风险等级 | 对策 |
| --- | --- | --- | --- |
| **T-R1** 否认执行过的命令 | 用户说"我没让 Agent 执行 rm" | 🟡 中 | (1) 所有 dangerous 操作写入 audit log (2) 操作录屏(可选) (3) log 包含用户授权 hash |
| **T-R2** 否认修改过的文件 | 哪个 Skill 改了哪个文件? | 🟡 中 | 每次写文件记录 actor (skill name + session id) |

#### I — Information Disclosure (信息泄露)

| 威胁 | 攻击路径 | 风险等级 | 对策 |
| --- | --- | --- | --- |
| **T-I1** 记忆泄露 | 误把私人记忆发给云端 LLM | 🔴 **高** | (1) 记忆分私密 / 公开,公开才上传 (2) 默认全私密 (3) UI 显式标注"将上传到云端" |
| **T-I2** API Key 泄露 | 用户贴 Key 到 Issue / Slack | 🔴 **高** | (1) pre-commit gitleaks (2) OS Keychain (3) Key 不入日志 |
| **T-I3** 文件泄露 | Skill 读 `/etc/passwd` 发给 LLM | 🟠 高 | (1) fs.read 必须白名单路径 (2) 大文件限制 (3) 内容敏感字段 redact |
| **T-I4** 错误日志含敏感信息 | stack trace 含 token | 🟡 中 | (1) 日志脱敏中间件 (2) Sentry 关闭 |
| **T-I5** 网络流量被监听 | 用户在公司网络跑 | 🟢 低 | (1) 仅 HTTPS (2) 证书钉扎 (3) E2E 加密可选 |

#### D — Denial of Service (拒绝服务)

| 威胁 | 攻击路径 | 风险等级 | 对策 |
| --- | --- | --- | --- |
| **T-D1** LLM API 配额耗尽 | Skill 死循环调用 API | 🟠 高 | (1) 单 session token 限额 (2) 调用频率限制 (3) 熔断器 |
| **T-D2** 本地资源耗尽 | 读巨大文件 / fork 炸弹 | 🟠 高 | (1) 单文件最大 10MB (2) ulimit 设置 (3) fnix-local sandbox (4) worker 数限制 |
| **T-D3** Memory 膨胀 | 记忆无限累积 | 🟡 中 | (1) importance < 0.1 的 episodic 30 天后压缩 (2) 总大小限制 |
| **T-D4** WebView 崩溃 | 大量 DOM / 循环 | 🟢 低 | React 虚拟列表 + 帧率监控 |

#### E — Elevation of Privilege (权限提升)

| 威胁 | 攻击路径 | 风险等级 | 对策 |
| --- | --- | --- | --- |
| **T-E1** Skill 提权 | Skill 借助工具访问未授权资源 | 🟠 高 | (1) Capability 最小化 (2) 每个 Skill 独立权限集 (3) 用户显式确认 dangerous |
| **T-E2** WebView 越权 | XSS 注入调用 `shell.execute` | 🟠 高 | (1) CSP 严格 (2) IPC capability 白名单 (3) ContextIsolation |
| **T-E3** Python 进程提权 | subprocess.run 任意命令 | 🟠 高 | (1) command 白名单 (2) 参数校验 (3) 不在 agentd 直接执行 shell |
| **T-E4** 本地提权 | 漏洞利用升级到 root | 🟡 中 | (1) Rust 进程最低权限运行 (2) 不监听公网 (3) 自动更新 |

---

## 三、对策实施状态

| 威胁 | 对策 | 状态 | 备注 |
| --- | --- | --- | --- |
| T-S1 | mTLS 鉴权 | ⚠️ 计划 | v0.6 |
| T-S3 | Skill 签名 | ⚠️ 计划 | v0.6 |
| T-T3 | Skill prompt 注入检测 | ⚠️ 部分 | 已有 allowlist |
| T-T5 | Capability 白名单 | ✅ 已实现 | `src-tauri/capabilities/` |
| T-I1 | 记忆私密分级 | ✅ 已实现 | `memory.privacy: private\|public` |
| T-I2 | gitleaks | ✅ 已实现 | `.gitleaks.toml` |
| T-I3 | fs.read 白名单 | ✅ 已实现 | `fs.allowList` |
| T-D1 | Token 配额 | ✅ 已实现 | `runtime.token_budget` |
| T-D2 | 文件大小限制 | ✅ 已实现 | `fs.maxFileSize` |
| T-E2 | CSP | ✅ 已实现 | WebView CSP 头 |

---

## 四、信任假设 / Trust Assumptions

我们**假设**:

1. **操作系统可信**:用户没有安装恶意软件
2. **本地磁盘可信**:全盘加密(FileVault / BitLocker)由用户决定
3. **Rust 工具链可信**:Rust 编译产物未被篡改
4. **LLM Provider 可信**:OpenAI / Anthropic 等不会主动作恶
5. **OS Keychain 可信**:macOS Keychain / Windows Credential Manager 实现安全

我们**不假设**:

1. 用户能识别钓鱼 → 必须有 UI 安全提示
2. 网络链路保密 → 必须 TLS
3. Skill 作者善意 → 必须 capability 最小化
4. LLM 输出可信 → 必须 LLM 输出校验

---

## 五、安全开发生命周期 / SDL

每个 PR 必须经过:

1. **设计阶段**:威胁建模(本文)
2. **实现阶段**:Secure coding checklist
3. **测试阶段**:SAST (CodeQL) + DAST (ZAP) + 依赖扫描 (Dependabot)
4. **部署阶段**:签名 + SBOM
5. **运维阶段**:CVE 监控 + 快速补丁

---

## 六、漏洞披露 / Vulnerability Disclosure

见 [SECURITY.md](../../SECURITY.md) — 不在公开 Issue 写漏洞细节,走 PGP 加密邮件。

---

## 七、参考 / References

- [STRIDE Threat Modeling](https://learn.microsoft.com/en-us/security/engineering/threat-modeling)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Tauri Security](https://tauri.app/v1/guides/distribution/security)
- [NIST SP 800-218 (SSDF)](https://csrc.nist.gov/publications/detail/sp/800-218/final)

---

© 2024-2026 FnixAgent. All Rights Reserved.