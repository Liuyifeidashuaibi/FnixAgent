# Changelog

本文件记录 OfficeAgent 项目的所有值得关注的变更(notable changes)。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/),
并遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

变更类型说明:

- **Added** — 新增的功能
- **Changed** — 对已有功能的变更
- **Deprecated** — 即将废弃的功能
- **Removed** — 已移除的功能
- **Fixed** — 缺陷修复
- **Security** — 安全相关的修复与增强(在存在漏洞时)

## [Unreleased]

### Added

- **协议升级**:Apache 2.0 协议替换原 MIT 协议,提供专利授权条款
- **工程基础设施**:新增 pre-commit / CHANGELOG / CONTRIBUTING / SECURITY / CODE_OF_CONDUCT 完整工程文档
- **安全增强模块**:
  - OS 级执行沙箱(Windows Job Object / Linux bubblewrap / macOS Seatbelt)
  - 工具语义审计层(ToolAuditor)
  - 影响溯源系统(ImpactTracker + 回滚)
  - 凭证治理(SecretManager + 环境变量强制)
  - KDK 分离(KDF + HKDF-SHA256)
  - 注入检测(InjectionDetector)
  - 工具白名单(ToolWhitelist)
  - 数字签名(资产完整性校验)
- **架构增强**:
  - DocumentConverter 协议(统一文档转换接口)
  - 三层质量梯度(fast / balanced / hi_res)
  - 插件生态(officeagent.converters 入口点)
  - MCP 规范化(Model Context Protocol 标准化接入)
- **构建系统**:pyproject.toml 迁移到 hatchling + ruff 工具链

### Changed

- **协议**:从 MIT 改为 Apache-2.0
- **代码格式化工具**:从 black + isort + flake8 迁移到 ruff(check + format)
- **构建后端**:从 setuptools 迁移到 hatchling
- **类型检查**:从 mypy 迁移到 pyright(strict 模式)
- **CI 矩阵**:补全 Python 3.12 测试矩阵

### Security

- 新增 OS 级执行沙箱(Windows Job Object / Linux bubblewrap / macOS Seatbelt),
  限制工具执行的系统调用与文件系统访问范围
- 新增工具语义审计层(ToolAuditor),在执行前对工具调用进行风险评级与拦截
- 新增影响溯源系统(ImpactTracker + 回滚),记录所有副作用并支持事务回滚
- 新增凭证治理(SecretManager + 环境变量强制),禁止硬编码密钥
- 新增 KDK 分离(KDF + HKDF-SHA256),主密钥派生与数据密钥分离
- 新增密钥泄露检测(detect-secrets + gitleaks)pre-commit 钩子

## [1.0.0] - 2026-01-01

### Added

- 首个稳定版本,包含完整 OfficeAgent 能力栈(L1-L6):
  - L1 文档处理:Word / Excel / PPT / PDF 读写与格式转换
  - L2 数据分析:数据清洗、可视化、统计建模
  - L3 知识管理:向量检索、知识图谱、长期记忆
  - L4 工具编排:LangGraph 状态机、工具注册与调用
  - L5 多 Agent 协作:角色编排、拓扑调度、handoff
  - L6 自进化:飞轮学习、技能沉淀、策略迭代
- 安全基线:Argon2id 密码哈希、RSA-2048 传输加密、AES-256-GCM 资产加密
- 身份认证:LDAP/AD 域集成、SSO(SAML 2.0 / OAuth 2.0)、MFA(TOTP / 短信)
- 部署:Docker / docker-compose / Helm / Terraform 多环境部署支持
