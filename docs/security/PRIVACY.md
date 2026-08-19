# 隐私政策 / Privacy Policy

> 本文件说明 FnixAgent 如何处理用户数据。
> 这是产品隐私承诺,详细技术细节见 `docs/security/THREAT-MODEL.md`。

---

## 一、核心原则 / Core Principles

1. **本地优先 (Local-First)**:数据默认留在你的电脑
2. **零遥测 (Zero Telemetry)**:不上传任何使用统计
3. **BYOK (Bring Your Own Key)**:你的 API Key 你保管
4. **可审计**:你随时能看到 / 导出 / 删除自己的数据
5. **可移植**:标准格式导出,可迁移到任何工具

---

## 二、数据分类 / Data Categories

### 2.1 完全本地(默认)

| 数据 | 存储位置 | 是否上传 |
| --- | --- | --- |
| 用户偏好 | `~/.fnix/memory/core/` | ❌ 否 |
| 长期记忆 | `~/.fnix/memory/` | ❌ 否 |
| 对话历史 | `~/.fnix/conversations/` | ❌ 否 |
| API Key (Keychain 模式) | OS Keychain | ❌ 否 |
| Skill 文件 | `~/.fnix/skills/` | ❌ 否 |
| 配置文件 | `~/.fnix/config.yaml` | ❌ 否 |
| Skill 自定义脚本 | Skill 目录内 | ❌ 否 |
| 崩溃日志(本地) | `~/.fnix/logs/` | ❌ 否 |

### 2.2 仅在你主动调用云端 LLM 时发送

当你**显式选择**调用云端 LLM( LLM /  / DeepSeek / ...)时,
Agent 会向 LLM Provider 发送:

| 数据 | 用途 | 备注 |
| --- | --- | --- |
| 你的 prompt(对话输入) | LLM 推理 | 必需 |
| 必要的工具调用上下文 | LLM 推理 | 必需 |
| 历史对话(窗口内) | 保持上下文 | 必需 |
| 模型版本号(用于计费 / 调试) | Provider 计费 | Provider 必收 |
| Token 数(用于计费) | Provider 计费 | Provider 必收 |

**FnixAgent 不主动向 LLM Provider 发送**:

- ❌ 文件系统其他内容(除非 Skill 显式调用 `fs.read`)
- ❌ 你的其他应用数据
- ❌ 你的浏览器历史 / 剪贴板(除非你粘贴)
- ❌ 任何 OS Keychain 里的内容
- ❌ Skill 源码 / 配置

### 2.3 不上传任何数据

无论云端 LLM 还是本地 LLM,**永远不上传**到 FnixAgent 自己或任何第三方:

- ❌ 使用统计(MAU / 启动次数 / 功能使用率)
- ❌ 崩溃报告
- ❌ 性能数据
- ❌ 错误日志(本地保留即可)
- ❌ 任何形式的遥测 / beacon

---

## 三、第三方 LLM Provider 的数据处理

当你使用云端 LLM 时,Provider 的隐私政策约束**他们自己**,而非 FnixAgent。

**建议用户**在使用前阅读:

- [ LLM Privacy Policy](https://openai.com/policies/privacy-policy)
- [ Privacy Policy](https://www.anthropic.com/privacy)
- [DeepSeek Privacy Policy](https://www.deepseek.com/privacy)

**特别注意**:

-  LLM 默认会保留 API 数据 30 天(用于滥用检测),可通过 Organization
  Settings → Data Controls 关闭
-  默认不使用 API 数据训练模型
- 部分 Provider 可能在中国大陆有特殊合规要求,使用前自行评估

---

## 四、本地加密 / Local Encryption

### 4.1 静态数据加密(可选)

**API Key**:
- 模式 A(默认):OS Keychain,系统级加密
- 模式 B:Argon2id + AES-256-GCM 加密便携文件

**对话历史**:可选加密,默认明文(本地访问控制已足够)

启用加密:

```yaml
# ~/.fnix/config.yaml
privacy:
  encrypt_at_rest:
    enabled: true
    algorithm: aes-256-gcm
    kdf: argon2id
    kdf_params:
      m: 65536      # 64 MB
      t: 3          # iterations
      p: 4          # parallelism
```

### 4.2 传输加密

- 所有 HTTP → HTTPS(强制)
- 本地 IPC:Tauri IPC 不走网络,使用 named pipe / Unix socket
- agentd ↔ fnix-local:stdio JSON-RPC(不走网络)

### 4.3 全盘加密(由用户决定)

FnixAgent **不强制**全盘加密,但**强烈建议**开启:

- macOS:FileVault
- Windows:BitLocker
- Linux:LUKS

---

## 五、数据生命周期 / Data Lifecycle

### 创建

```
用户输入 → MemoryStore.add→ 写 ~/.fnix/memory/{type}/{date}.md
                                → 触发 git commit
                                → 触发 embedding 索引更新
```

### 访问

```
MemoryStore.search→ BM25 + 向量 RRF → LLM context → 用户
   ↑ 记入 access_count, 更新 last_accessed
```

### 衰减

```
importance < 0.1 且 age > 30 天  →  压缩为 summary
importance < 0.05 且 age > 90 天 →  删除
用户显式 forget                 →  立即删除
```

### 删除

```
MemoryStore.delete(id) → 从文件移除 → 从 SQLite 索引移除 → git add + commit "memory: delete <id>"
```

不可恢复(除非用户用 git reflog)。

---

## 六、用户权利 / Your Rights

你对自己的数据拥有**完全控制权**:

| 权利 | 实现 |
| --- | --- |
| **访问权** | 直接 `cd ~/.fnix/ && ls` |
| **更正权** | 编辑对应 .md 文件 + git commit |
| **删除权** | `fnix memory delete` 或手动 rm |
| **可携带权** | `fnix memory export --format=zip` |
| **拒绝处理权** | 关闭应用 = 停止所有处理 |
| **知情权** | 本文件 + `docs/security/THREAT-MODEL.md` |

### 一键导出全部数据

```bash
fnix export --output ~/Desktop/fnix-export-$(date +%Y%m%d).tar.gz
# 包含:
# - ~/.fnix/memory/   (记忆)
# - ~/.fnix/skills/    (技能)
# - ~/.fnix/config.yaml
# - ~/.fnix/conversations/
# - (不含 keystore.enc,因为需要主密码)
```

### 一键清除全部数据

```bash
fnix uninstall --purge
# 删除 ~/.fnix/ 全部内容
# OS Keychain 内的 Key
# 应用本地缓存
```

---

## 七、未成年人 / Minors

FnixAgent 服务于成年开发者。如未满 18 岁,使用前请监护人阅读本政策。

---

## 八、隐私政策变更 / Policy Changes

本政策更新会在以下渠道通知:

- 应用启动时横幅
- `CHANGELOG.md` 中的 `Privacy` section
- GitHub Release Notes

**实质性变更**(影响上述数据流向)将至少提前 60 天通知。

---

## 九、跨境传输 / Cross-Border Transfer

由于 FnixAgent **不主动上传数据到任何服务端**,不涉及跨境传输问题。

但**当你使用云端 LLM 时**:

- 你向  LLM(美国)发送 prompt
- 你向 (美国)发送 prompt
- 你向 DeepSeek(中国)发送 prompt

跨境传输发生在**你与 LLM Provider 之间**,由 Provider 的隐私政策约束,
FnixAgent **不参与**也不收集该传输的任何元数据。

---

## 十、Cookie / 跟踪 / Cookies

FnixAgent 是**桌面应用,不使用浏览器 Cookie**,不进行网站跟踪,
不嵌入任何分析 SDK。

---

## 十一、联系 / Contact

| 类别 | 邮箱 |
| --- | --- |
| 隐私问题 | liuyifeidashuaibi@gmail.com |
| 安全漏洞 | liuyifeidashuaibi@gmail.com (PGP,见 SECURITY.md) |
| 商用授权 | liuyifeidashuaibi@gmail.com |
| 一般问题 | GitHub Issues |

---

## 十二、合规/ Compliance References

本政策的隐私保护水平参考以下标准设计:

- [GDPR](https://gdpr-info.eu/) (欧盟通用数据保护条例)
- [CCPA](https://oag.ca.gov/privacy/ccpa) (加州消费者隐私法)
- [PIPL](http://www.gov.cn/zhengce/content/2021-08/20/content_5632339.htm)
  (个人信息保护法)
- [OWASP Privacy](https://owasp.org/www-project-top-10-privacy-risks/)

本项目为专有项目,**未声明**任何官方合规认证。

---

## 十三、政策版本

- v1.0.0 (2026-08-17): 初版
- 维护者:`@fnixagent-core`
- 下次复审:2027-02-17

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.