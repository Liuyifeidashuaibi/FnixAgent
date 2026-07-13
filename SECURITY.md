# 安全策略

FnixAgent 团队高度重视项目安全。本文件说明支持的版本、漏洞报告流程与响应承诺。

## 支持的版本

FnixAgent 仅对最新稳定版本提供安全更新。下表列出当前支持状态:

| 版本    | 支持状态          | 备注                |
| ------- | ----------------- | ------------------- |
| 1.1.x   | ✅ 当前支持       | 安全更新持续发布    |
| 1.0.x   | ⚠️ 有限支持       | 仅关键 CVE 修复     |
| < 1.0   | ❌ 不再支持       | 请升级到最新版本    |

## 漏洞报告流程

**请不要通过公开的 GitHub Issue 报告安全漏洞。**

我们遵循 [协调漏洞披露](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure)(CVD)原则。
如发现安全漏洞,请按以下流程报告:

1. **发送邮件**至 [security@fnixagent.dev](mailto:security@fnixagent.dev),
   主题以 `[SECURITY]` 前缀开头。
2. **加密通信**:如内容敏感,请使用我们的 PGP 公钥加密邮件。
   PGP 公钥获取方式:
   - 在密钥服务器 `keys.openpgp.org` 搜索 `security@fnixagent.dev`
   - 或访问 `https://fnixagent.dev/.well-known/pgp-key.txt` 下载
3. **提供以下信息**(尽量完整,以便快速定位):
   - 漏洞类型(如:SQL 注入、XSS、命令注入、权限提升等)
   - 受影响的源文件路径与相关代码位置(tag / branch / commit 或 URL)
   - 复现步骤(详细到可独立复现)
   - 最小化 PoC 或 exploit 代码(如可能)
   - 漏洞影响评估与攻击者可能的利用方式
   - 您建议的修复方案(可选)
4. **等待确认**:我们会在 SLA 时间内回复确认。

## 响应时间 SLA

| 阶段           | 时间窗口     | 说明                                       |
| -------------- | ------------ | ------------------------------------------ |
| 收到确认       | 24 小时内    | 确认收到报告并分配处理人                   |
| 初步评估       | 7 天内       | 评估漏洞严重性与影响范围,给出修复计划     |
| 修复发布       | 90 天内      | 发布修复版本(严重漏洞优先在 30 天内)    |
| 公开披露       | 修复后 14 天 | 在确认用户已升级后公开披露详情             |

若未在 24 小时内收到回复,请再次发送邮件以确认我们已收到。

## MSRC 报告渠道

如漏洞涉及 Microsoft 组件(例如 markitdown 集成、Azure 文档智能等),
可同步报告至 [Microsoft Security Response Center (MSRC)](https://msrc.microsoft.com/create-report)。
MSRC 也接受匿名报告。

## 漏洞奖励

FnixAgent 当前为社区驱动的开源项目,暂无现金漏洞奖励计划。
但我们会对报告者致谢(经报告者同意后):

- 在 SECURITY.md 与发布说明中署名
- 颁发 "FnixAgent Security Contributor" 数字徽章

## 公开披露时机

- 修复版本发布后 14 天,我们将在 GitHub Advisory Database 公开披露
- 报告者可与维护者协商提前或延后披露时间
- 在用户未充分升级前,我们不会公开 PoC

## 安全加固建议

部署 FnixAgent 时建议遵循以下加固清单:

1. **密钥管理**:所有密钥通过环境变量或 KMS(Vault / AWS KMS / 阿里云 KMS)注入,
   禁止硬编码。`.env` 文件加入 `.gitignore`。
2. **沙箱启用**:生产环境强制开启 OS 级执行沙箱,限制工具的文件系统与系统调用范围。
3. **最小权限**:运行账户使用最小权限原则,容器以非 root 用户运行。
4. **网络隔离**:数据库、Redis、MinIO 等中间件仅对应用内网开放,
   禁止暴露到公网。
5. **审计日志**:开启 ToolAuditor 与 ImpactTracker,所有工具调用与副作用记录到审计日志。
6. **依赖更新**:定期运行 `pip-audit` 与 `trivy`,及时更新存在 CVE 的依赖。
7. **MFA 强制**:管理员账户强制启用 MFA(TOTP / 硬件密钥)。
8. **传输加密**:所有对外通信强制 TLS 1.2+,内部服务间建议 mTLS。

## 安全相关配置

- 敏感词过滤:`config/security/sensitive_words.yaml`
- 沙箱配置:`config/settings.yaml` 中的 `sandbox` 段
- 审计日志:`config/settings.yaml` 中的 `audit` 段
- 密钥轮换:建议每 90 天轮换一次主密钥

## 联系方式

- 安全邮箱:[security@fnixagent.dev](mailto:security@fnixagent.dev)
- 公开议题(非敏感):[GitHub Issues](https://github.com/Liuyifeidashuaibi/FnixAgent/issues)
