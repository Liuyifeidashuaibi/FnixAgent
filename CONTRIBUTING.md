# 贡献指南 (Contributing Guide)

> ⚠️ **重要声明 / Important Notice**
>
> **本项目不接受外部代码贡献**。本项目以 [All Rights Reserved](LICENSE)
> 方式发布,详见下文 "贡献边界" 章节。
>
> **This project does NOT accept external code contributions at this time.**
> The project is released under [All Rights Reserved](LICENSE).
> See "Contribution Boundaries" below.

---

感谢您关注 FnixAgent!

## ⚠️ 贡献边界 / Contribution Boundaries

| 类型                            | 是否接受                                                |
| ------------------------------- | ------------------------------------------------------- |
| ❌ 代码贡献 (Pull Request)      | **不接受**                                              |
| ❌ 翻译合作                     | **不接受**(由维护者本人完成)                            |
| ❌ Skill / Prompt 投稿          | **不接受**(见 [docs/TRADEMARKS.md](docs/TRADEMARKS.md)) |
| ✅ Bug 报告 (GitHub Issue)      | 欢迎                                                    |
| ✅ 设计讨论 (GitHub Discussion) | 欢迎                                                    |
| ✅ 安全漏洞披露 (PGP 邮件)      | 欢迎                                                    |
| ✅ Star / 引用 / 在社交媒体提及 | 欢迎                                                    |

**为什么?**

1. **许可证限制**:本项目以 All Rights Reserved 发布,合入外部代码会带来
   法律风险(版权归属不清)
2. **维护模式**:本项目由单一维护者独立研发,当前阶段不接受社区代码合入,
   以保证架构与质量控制的一致性
3. **质量控制**:作者对每一行代码的设计都有明确意图,外部代码难以匹配
4. **法律保护**:详细见 [LICENSE](LICENSE) 与 [docs/LICENSE-COMMERCIAL.md](docs/LICENSE-COMMERCIAL.md)

## 如果你想做类似项目

欢迎基于**自己的理解**写自己的代码,不要直接复制本项目代码或创建
实质相似的 fork,详见 [LICENSE](LICENSE) 中的"View-Only License"。

---

## 如何贡献(报告与讨论)

### 报告问题

在创建 issue 之前，请先搜索现有 issue 列表，确保您的问题尚未被报告。如果找到相关 issue，您可以添加评论提供额外信息。

创建新 issue 时，请使用相应的 issue 模板：

- **Bug 报告**: 描述问题、复现步骤、预期行为和实际行为
- **功能请求**: 描述您想要的功能、使用场景和预期收益

### 提交代码

本项目当前为**专有软件 (All Rights Reserved)**，不接受外部代码合入 (Pull Request)。
以下开发环境设置和代码规范仅供维护者内部参考。

如发现 Bug 或希望提出功能建议，请通过
[GitHub Issues](https://github.com/Liuyifeidashuaibi/FnixAgent/issues)
或 [Discussions](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions)
发起讨论。

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/Liuyifeidashuaibi/FnixAgent.git
cd FnixAgent

# 安装依赖
pnpm setup

# 检查环境
pnpm doctor

# 启动开发服务器
pnpm dev
```

### 代码规范

- 使用 **ruff** 进行代码格式化和 lint
- 使用 **pyright** 进行类型检查
- 遵循 **PEP 8** 风格指南
- 编写清晰的提交信息，使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式

### 提交信息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型：

- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响代码运行的变动）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试
- `chore`: 构建过程或辅助工具的变动

### 测试

- 为新功能编写测试
- 确保所有现有测试通过
- 运行测试：`pnpm test`

### 文档

- 更新相关文档以反映您的更改
- 如果添加了新功能，请添加使用示例

## 行为准则

本项目遵循 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) 中定义的行为准则。参与本项目即表示您同意遵守这些准则。

## 许可证

通过向本项目提交代码，您同意您的贡献将根据项目的许可证条款进行许可。

## 联系方式

- **Issues**: [GitHub Issues](https://github.com/Liuyifeidashuaibi/FnixAgent/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Liuyifeidashuaibi/FnixAgent/discussions)
- **安全**: [SECURITY.md](SECURITY.md)

感谢您的贡献！
