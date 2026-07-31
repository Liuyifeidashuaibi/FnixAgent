# Changelog

本文件记录 FnixAgent 项目的所有值得关注的变更(notable changes)。

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

### Fixed

- **E2E 环境隔离**：`test_scheduler_e2e` 与 `test_user_flows` fixture 增加 `dotenv.load_dotenv` monkeypatch，防止 `.env` 真实 API Key 污染测试环境（根因：`build_scheduler()` 内部调用 `load_dotenv` 覆盖 `monkeypatch.delenv`，导致 craft 等流式测试命中真实 LLM API 挂起）
- **task_id 路径参数**：`/tasks/{task_id}` 路由从 `int` 改为 `str` 入参 + `_coerce_task_id` 强制转换，非数字 ID 返回 404（资源不存在）而非 422（参数校验错误），符合 REST 语义
- **MockLLM 回退链路**：`llm_policy.resolve_llm_for_request` 在无服务端 Key 且无用户 Key 时放行（而非阻断），`build_work_agent_loop` 在请求级 LLM 未配置时回退到全局调度器 `LLMRouter`（含 MockLLMProvider），使离线/测试环境完整流程可运行
- **5 个 F821 未定义名 bug**：`daao_router.py` 缺 `Any` 导入、`topology/store.py` 缺 `TopologyGraph` 导入、`tasks/editability.py` 缺 `ExpertError` 导入（3 处）
- **ruff lint 从 5431 错误降至 0**：自动修复 3010 项，修复 5 个 F821 真实 bug + 15 个 F401 未用导入 + 21 个 F841 未用变量，调整配置消除中文标点/服务端/非加密哈希等误报，格式化 383 文件

### Changed

- **README 徽章修复**：将损坏的裸文本链接替换为 shields.io 标准徽章图片（CI/Release/License/Python/Tauri/Ruff）
- **ruff 配置完善**：`pyproject.toml` 增加全局 ignore（消除中文字符标点、服务端绑定、非加密哈希等误报）+ 分模块 per-file-ignores（API/安全/MCP/业务工具）
- **.gitignore 补全**：增加 `_debug_home/`、`_debug_ws/`、`debug_craft.py` 模式

### Added

- **Standalone E2E**：`pnpm e2e:standalone` 自动 spawn fnix-local + agentd 并验收 Harness/Work API
- **集成测试**：`tests/integration/test_standalone_harness.py`（Work/Code session 列表与持久化）
- **Electron 退役说明**：`apps/desktop/DEPRECATED.md`；`pnpm dev:all` 默认转发 Tauri 三进程
- **Tauri 2 Desktop v1.0 Beta 发布阶段**
  - `apps/desktop-tauri`：Rust spawn agentd/fnix-local、OS Keychain、portable-pty 本地终端
  - `pnpm verify:beta` / `pnpm prepare:release` / `pnpm dev:all:tauri`
  - GitHub Actions：`release.yml` Tauri 三平台打包；CI `desktop-tauri` job
  - 文档：`docs/BETA_RELEASE.md`、`docs/DESKTOP_TAURI.md`、`docs/QUICKSTART.md` 更新
- **自进化飞轮系统 (Intelligence & Auto-Evolution)**: 新增 `core/intelligence/` 模块, 实现持续信息采集→知识提炼→升级闭环
  - 多源智能采集 (GitHub/arXiv/大厂博客/社区/协议/会议)
  - 知识提炼引擎 (相关性评分、分类排序、逐级过滤)
  - 升级引擎 (差距分析、10维升级类型、执行追踪)
  - 飞轮调度 (每天/每周/每月三级频率, cron驱动)
  - 设计参考: Hermes Agent (技能自动创建+GEPA), OpenClaw (self-improving-agent), SAGE (RL自进化)
- **架构可视化文档**: 新增 6 张专业 SVG 架构图（系统总览 / 数据流 / 自进化内核 / 安全纵深防御 / 三层记忆 / 部署拓扑）
- **README 深度重写**: 从 167 行扩充至 770+ 行，含 16 章节、对比表格、完整代码示例、配套架构图内嵌

### Changed

- **默认 Desktop 壳层**：`pnpm dev` / README 快速开始指向 Tauri 2；Electron 保留为 `dev:electron`
- **requirements.txt**: 清理遗留的 flake8/black/mypy 依赖，工具链已迁移至 ruff+pyright
- **.env.example**: 补充 DEEPSEEK_API_KEY 和 ES_PASSWORD，新增分组注释

### Fixed

- **cloud profile**：`apply_profile_defaults()` 不再在 cloud 模式下错误保留 `SERVICE_ENV=development`
- **Windows 路径**：`verify-beta` 在 Node 安装于 `Program Files` 时不再因 shell 拆路径失败

### Security

- **移除已提交的私钥**: 删除 `assets/keys/default.private.pem`，新增目录 README 说明安全策略

### Removed

- **清理根目录冗余文件**: 移除 FNIXAGENT_CODE_LEVEL_UPGRADE.md、FNIXAGENT_TOP_TIER_UPGRADE_PLAN.md、FNIXAGENT_TECH_PLAN_V2.md 等临时规划文档

## [1.1.0] - 2026-07-13

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
  - 插件生态(fnixagent.converters 入口点)
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

- 首个稳定版本,包含完整 FnixAgent 能力栈(L1-L6):
  - L1 文档处理:Word / Excel / PPT / PDF 读写与格式转换
  - L2 数据分析:数据清洗、可视化、统计建模
  - L3 知识管理:向量检索、知识图谱、长期记忆
  - L4 工具编排:LangGraph 状态机、工具注册与调用
  - L5 多 Agent 协作:角色编排、拓扑调度、handoff
  - L6 自进化:飞轮学习、技能沉淀、策略迭代
- 安全基线:Argon2id 密码哈希、RSA-2048 传输加密、AES-256-GCM 资产加密
- 身份认证:LDAP/AD 域集成、SSO(SAML 2.0 / OAuth 2.0)、MFA(TOTP / 短信)
- 部署:Docker / docker-compose / Helm / Terraform 多环境部署支持

[Unreleased]: https://github.com/Liuyifeidashuaibi/FnixAgent/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Liuyifeidashuaibi/FnixAgent/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Liuyifeidashuaibi/FnixAgent/releases/tag/v1.0.0
