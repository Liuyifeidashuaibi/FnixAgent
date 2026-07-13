# 贡献指南

[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)

👍🎉 感谢您愿意为 OfficeAgent 贡献力量!🎉👍

本文件是参与 OfficeAgent 项目贡献的指南。遵守本指南有助于 review 流程顺畅,
节省维护者时间,并避免 PR 被 CI 拒绝。

## 目录

- [行为准则](#行为准则)
- [入门](#入门)
- [开发环境搭建](#开发环境搭建)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [分支策略](#分支策略)
- [Pull Request 流程](#pull-request-流程)
- [测试要求](#测试要求)
- [Issue 报告](#issue-报告)

---

## 行为准则

参与本项目即代表您同意遵守 [贡献者公约](CODE_OF_CONDUCT.md)。请在所有社区互动中
保持友善与尊重。

## 入门

1. 浏览 [GitHub Issues](https://github.com/officeagent/officeagent/issues),
   从带 `good first issue` 标签的简单 issue 开始。
2. 找到感兴趣的 issue 后,在评论区留言认领,避免重复劳动。
3. Fork 仓库并创建功能分支(见 [分支策略](#分支策略))。
4. 完成开发后提交 Pull Request。

## 开发环境搭建

OfficeAgent 推荐使用 [uv](https://docs.astral.sh/uv/) 作为包管理器,
它比 pip 快 10-100 倍并自带虚拟环境管理。

### 1. 安装 uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. 克隆并安装依赖

```bash
git clone https://github.com/officeagent/officeagent.git
cd officeagent

# 创建虚拟环境并安装依赖(含开发依赖)
uv sync --extra dev

# 或使用 pip(兼容方式)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. 安装 pre-commit 钩子

```bash
pip install pre-commit
pre-commit install
```

此后每次 `git commit` 都会自动运行 ruff 检查、格式化、密钥扫描等钩子。

### 4. 验证安装

```bash
# 运行测试
uv run pytest tests/unit/ -v

# 运行 ruff 检查
uv run ruff check src/ tests/

# 运行 ruff 格式化
uv run ruff format src/ tests/
```

## 代码规范

### Python 代码风格

- **格式化工具**:统一使用 [ruff](https://docs.astral.sh/ruff/)
  (替代 black + isort + flake8)
- **行宽**:100 字符
- **目标版本**:Python 3.11+
- **类型检查**:使用 [pyright](https://github.com/microsoft/pyright) strict 模式

### 检查与格式化命令

```bash
# 检查代码
ruff check src/ tests/

# 自动修复
ruff check --fix src/ tests/

# 格式化
ruff format src/ tests/

# 类型检查
pyright src/officeagent/
```

### 代码要求

- 新增的类、函数、方法必须添加类型注解(type hints)
- 新增的类、函数、方法必须添加 docstring(中文)
- 公共 API 必须有对应的单元测试
- 注释使用中文,变量名与函数名使用英文
- 禁止硬编码密钥、令牌、密码等敏感信息(使用环境变量)

## 提交规范

OfficeAgent 遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/)
规范。提交信息格式:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### 常用 type

| type       | 说明                                   |
| ---------- | -------------------------------------- |
| `feat`     | 新功能                                 |
| `fix`      | 缺陷修复                               |
| `docs`     | 文档变更                               |
| `style`    | 代码格式(不影响功能)                 |
| `refactor` | 重构(既非新增功能也非修复)           |
| `perf`     | 性能优化                               |
| `test`     | 新增或修改测试                         |
| `chore`    | 构建 / 工具链 / 依赖等杂项            |
| `ci`       | CI 配置变更                            |
| `security` | 安全相关修复                           |

### 示例

```
feat(security): 新增 OS 级执行沙箱(Windows Job Object)

- 实现 Windows Job Object 沙箱后端
- 限制子进程 CPU / 内存 / 文件系统访问
- 新增 ImpactTracker 记录副作用

Closes #42
```

## 分支策略

OfficeAgent 采用简化的 [GitHub Flow](https://docs.github.com/zh/get-started/quickstart/github-flow):

- `main`:稳定发布分支,始终保持可发布状态
- `develop`:开发集成分支(可选,小项目可直接在 main 上 PR)
- 功能分支:`<type>/<description>`,例如 `feat/sandbox`、`fix/auth-token`

### 分支命名约定

```
feat/<描述>       # 新功能
fix/<描述>        # 缺陷修复
docs/<描述>       # 文档
chore/<描述>      # 杂项
```

## Pull Request 流程

### 提交前检查清单

- [ ] 代码已通过 `ruff check` 与 `ruff format`
- [ ] 类型检查已通过 `pyright`
- [ ] 新增功能有对应的单元测试
- [ ] 测试覆盖率不低于 80%
- [ ] `CHANGELOG.md` 已更新(在 `[Unreleased]` 段添加条目)
- [ ] 提交信息遵循 Conventional Commits 规范
- [ ] 没有调试代码、注释掉的代码
- [ ] 没有硬编码的密钥或敏感信息

### PR 步骤

1. **创建 PR**:从功能分支向 `main`(或 `develop`)发起 PR。
2. **PR 标题**:遵循 Conventional Commits 规范,例如 `feat: 新增沙箱模块`。
3. **PR 描述**:
   - 说明本次变更的内容与目的
   - 关联相关 Issue(如 `Closes #42`)
   - 如有必要,提供测试步骤
4. **CI 检查**:所有 CI 检查必须通过(lint / test / security / docker-build)。
5. **Code Review**:至少一位维护者 review 并 approve。
6. **Squash Merge**:合并时使用 squash,保留干净的提交历史。

### Draft PR

如 PR 尚未准备好接受最终 review,请使用 Draft 模式,并在标题加 `[WIP]` 前缀。

## 测试要求

- **覆盖率**:新增代码的测试覆盖率不低于 80%
- **单元测试**:位于 `tests/unit/`,测试单个模块 / 函数
- **集成测试**:位于 `tests/integration/`,测试模块间协作
- **标记**:使用 `@pytest.mark.unit` / `@pytest.mark.integration` / `@pytest.mark.slow`
  标记测试类型

### 运行测试

```bash
# 运行所有单元测试并生成覆盖率报告
pytest tests/unit/ -v --cov=src/officeagent --cov-report=term-missing

# 运行集成测试
pytest tests/integration/ -v

# 只运行带特定标记的测试
pytest -m "not slow" tests/
```

### 测试编写规范

- 测试文件命名:`test_<被测模块>.py`
- 测试函数命名:`test_<被测行为>`
- 使用 `conftest.py` 共享 fixture
- 避免测试间的相互依赖,每个测试应可独立运行
- Mock 外部依赖(数据库、网络、文件系统)

## Issue 报告

提交 Issue 前:

1. 搜索已有 Issue,确认问题未被报告过。
2. 使用 Issue 模板(如已配置)。
3. 提供以下信息:
   - OfficeAgent 版本号
   - Python 版本与操作系统
   - 复现步骤(最小化示例)
   - 期望行为与实际行为
   - 相关日志 / 错误堆栈
4. 安全漏洞请勿通过 Issue 报告,参见 [SECURITY.md](SECURITY.md)。

## 许可协议

贡献的代码将在 [Apache License 2.0](LICENSE) 下发布。
提交 PR 即代表您同意将贡献以该协议授权。

## 致谢

感谢每一位为 OfficeAgent 贡献代码、文档、Issue 和建议的贡献者!
