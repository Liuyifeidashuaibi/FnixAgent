# 竞品对比 / Comparison

> 本文件客观对比 FnixAgent 与主流 AI Agent 工具,不含价值评判。

---

## 一、综合对比表

| 维度           | FnixAgent       |           | Continue     | Cline        |           |             | Devin   |
| -------------- | --------------- | --------- | ------------ | ------------ | --------- | ----------- | ------- |
| **形态**       | 桌面 App        | IDE       | VS Code 插件 | VS Code 插件 | CLI       | IDE 插件    | 云端    |
| **语言栈**     | TS+Rust+Py      | TS        | TS           | TS           | Py        | TS+云       | 闭源    |
| **本地 LLM**   | ✅              | ⚠️ 实验   | ✅           | ✅           | ✅        | ❌          | ❌      |
| **BYOK**       | ✅ OS Keychain  | ✅        | ✅           | ✅           | ✅        | ❌          | ❌      |
| **长期记忆**   | ✅ Markdown+Git | ❌        | ⚠️ 实验      | ❌           | ❌        | ❌          | ❌      |
| **任务图规划** | ✅ KTG/STP/MFP  | ❌        | ❌           | ❌           | ❌        | ❌          | ⚠️      |
| **Skill 机制** | ✅ 完整         | ⚠️ MCP    | ⚠️ 简化      | ❌           | ❌        | ⚠️ 编辑补全 | ⚠️      |
| **离线运行**   | ✅ 完全         | ❌        | ⚠️ 部分      | ⚠️ 部分      | ✅ 完全   | ❌          | ❌      |
| **多模态**     | ✅ 图文音       | ⚠️        | ⚠️           | ⚠️           | ❌        | ✅          | ✅      |
| **可审计性**   | ✅ Markdown     | ❌        | ❌           | ⚠️           | ⚠️        | ❌          | ❌      |
| **开源**       | ❌ 专有         | ❌ 闭源   | ⚠️ Apache    | ⚠️ Apache    | ⚠️ Apache | ❌ 闭源     | ❌ 闭源 |
| **价格**       | 免费 (BYOK)     | $20/月    | 免费+云      | 免费+云      | 免费+云   | $10/月      | $500/月 |
| **品牌定位**   | 独立开发者      | 个人+团队 | 个人         | 个人         | 个人      | 个人+团队   | 企业    |

---

## 二、详细对比

### 1. 记忆系统

| 工具          | 短期 | 长期            | 可导出  | 可审计       |
| ------------- | ---- | --------------- | ------- | ------------ |
| **FnixAgent** | ✓    | ✓ Markdown+Git  | ✓ 一键  | ✓ 直接看 .md |
|               | ✓    | ✗               | ✗       | ✗            |
| Continue      | ✓    | ⚠️ 实验         | ⚠️      | ✗            |
| Cline         | ✓    | ✗               | ⚠️ 部分 | ✗            |
|               | ✓    | ⚠️ chat history | ✓ .md   | ⚠️           |
| AI 补全工具   | ✓    | ✗               | ✗       | ✗            |
| Devin         | ✓    | ⚠️              | ✗       | ✗            |

**FnixAgent 优势**:长期记忆**就是** Git 仓库,直接 `cd ~/.fnix/memory && git log`。

### 2. 任务规划

| 工具            | 单步 | 多步计划 | 长期计划 |
| --------------- | ---- | -------- | -------- |
| **FnixAgent**   | MFP  | STP      | KTG      |
| Composer        | ✓    | ⚠️ 部分  | ✗        |
| Continue        | ✓    | ✗        | ✗        |
| Cline Plan Mode | ✓    | ⚠️       | ✗        |
|                 | ✓    | ✗        | ✗        |
| Devin           | ✓    | ✓        | ⚠️ 实验  |

**FnixAgent 优势**:唯一具备**三层时间跨度**规划的 Agent。

### 3. Skill / 工具扩展

| 工具          | Skill DSL     | 沙箱执行     | 跨进程 | 热加载 |
| ------------- | ------------- | ------------ | ------ | ------ |
| **FnixAgent** | Markdown+YAML | Rust sandbox | ✓      | ✓      |
| MCP           | JSON          | 进程隔离     | ✓      | ⚠️     |
| Continue      | YAML          | 子进程       | ✓      | ⚠️     |
| Cline         | TS/JS         | 子进程       | ✓      | ✓      |
|               | Python        | 子进程       | ✓      | ✗      |

**FnixAgent 优势**:Skill 用纯 Markdown 写,开发者门槛最低。

### 4. 隐私

| 工具          | 数据出站 | API Key 存储 | 用户控制 |
| ------------- | -------- | ------------ | -------- |
| **FnixAgent** | 默认零   | OS Keychain  | 完全本地 |
|               | 强制云   | 云端         | 弱       |
| Continue      | 可选     | 配置文件     | 中       |
| Cline         | 可选     | 配置文件     | 中       |
| AI 补全工具   | 强制云   | 云端         | 弱       |
| Devin         | 强制云   | 云端         | 弱       |

**FnixAgent 优势**:唯一**默认零出站**且代码可读的 Agent。

---

## 三、场景化推荐

### 场景 1:个人开发 + 隐私敏感

| 工具        | 推荐度 |
| ----------- | ------ |
| FnixAgent   | ★★★★★  |
| Continue    | ★★★★   |
| Cline       | ★★★★   |
|             | ★★     |
| AI 补全工具 | ★      |

### 场景 2:团队协作 + 大量 PR Review

| 工具        | 推荐度               |
| ----------- | -------------------- |
|             | ★★★★★                |
| AI 补全工具 | ★★★★                 |
| Continue    | ★★★                  |
| FnixAgent   | ★★★ (强项在长期项目) |

### 场景 3:复杂 Agent 应用研发

| 工具          | 推荐度                 |
| ------------- | ---------------------- |
| **FnixAgent** | ★★★★★ (就是为这个做的) |
| LangGraph     | ★★★★                   |
| AutoGen       | ★★★★                   |

### 场景 4:纯代码补全

| 工具        | 推荐度                   |
| ----------- | ------------------------ |
| AI 补全工具 | ★★★★★                    |
| Tab         | ★★★★★                    |
| Continue    | ★★★★                     |
| FnixAgent   | ★★★ (可补但不是主要场景) |

---

## 四、本项目不做什么

为了避免误解,FnixAgent **明确不做**:

- ❌ **不做 IDE**:它不是替代 VS Code / JetBrains 的
- ❌ **不做 SaaS**:不提供云端服务
- ❌ **不做团队版**:没有 workspace / billing / seats
- ❌ **不做插件市场**:Skill 可以自己写,但不提供分发平台
- ❌ **不做移动端**:仅桌面

如需这些能力,请用其他工具。

---

## 五、引用 / References

- [ 官方文档](https://docs.cursor.com/)
- [Continue 官方文档](https://docs.continue.dev/)
- [Cline 官方文档](https://docs.cline.bot/)
- [ 官方文档](https://aider.chat/)
- [AI 补全工具文档](https://docs.github.com/copilot)
- [Devin 介绍](https://devin.ai/)

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.
