# 引用 / Citations

> 在论文、博客、社交媒体中引用 FnixAgent 时,请参考本指南。

---

## 一、学术引用 / Academic Citation

### BibTeX

```bibtex
@software{fnixagent2026,
  title  = {FnixAgent: A Local-First Desktop Agent Workbench
            with Three-Layer Task Graph Planning},
  year   = {2026},
  author = {Liu, Yifei},
  url    = {https://github.com/fnixagent/fnixagent},
  note   = {All Rights Reserved. View-only access via GitHub.},
  version = {0.5.0},
}
```

### APA

```
Liu, Y. (2026). FnixAgent: A Local-First Desktop Agent Workbench with
Three-Layer Task Graph Planning (Version 0.5.0) [Computer software].
https://github.com/fnixagent/fnixagent
```

### MLA

```
Liu, Yifei. FnixAgent: A Local-First Desktop Agent Workbench with
Three-Layer Task Graph Planning. Version 0.5.0, 2026,
github.com/fnixagent/fnixagent.
```

---

## 二、技术博客引用 / Blog Citation

### Markdown

```markdown
本文讨论的 [FnixAgent](https://github.com/fnixagent/fnixagent)
是刘逸飞开发的本地优先桌面 Agent 工作台,采用三层任务图规划模型
(KTG/STP/MFP),详见 [架构决策记录](https://github.com/fnixagent/fnixagent/blob/main/docs/adr/0004-three-layer-task-graph.md)。
```

### 引用论文 / 链接规范

- 优先链接到**主分支具体行号**:`blob/main/docs/adr/0004.md#L10-L30`
- 而不是根目录:`docs/adr/0004.md`(因为行号会漂移)

---

## 三、引用图 / Reference Figures

### 架构图

```markdown
![FnixAgent 架构图](https://raw.githubusercontent.com/fnixagent/fnixagent/main/docs/architecture.svg)

> 来源:[FnixAgent Architecture](https://github.com/fnixagent/fnixagent/blob/main/docs/architecture.svg),
> © 2026 刘逸飞,引用请注明出处。
```

**注意**:

- ✅ 允许在学术论文、教学幻灯片、技术博客中引用并注明出处
- ❌ 禁止用作商业培训教材封面
- ❌ 禁止抹除版权信息

详见 [TRADEMARKS.md](../../TRADEMARKS.md)。

---

## 四、Logo 使用 / Logo Usage

### 允许

- 技术博客中"项目展示"列表
- 学术论文 / 教学幻灯片
- 个人简历"项目经历"板块
- GitHub star 列表截图

### 不允许

- 修改颜色 / 比例
- 与其他 Logo 组合
- 用作商业产品名
- 用作培训课程名

详细见 [TRADEMARKS.md](../../TRADEMARKS.md) 与
[`assets/brand/usage.md`](../../assets/brand/usage.md)。

---

## 五、姓名使用 / Name Usage

**FnixAgent**(项目名) vs **刘逸飞**(作者):

| 场景 | 写法 |
| --- | --- |
| 学术引用 | "FnixAgent" 或 "Liu, Y." |
| 个人简历 | "刘逸飞 / FnixAgent 作者" |
| 致谢 | "感谢刘逸飞开发了 FnixAgent" |
| 公司博客 | 引用请注明 "刘逸飞 (fnixagent.dev)" |

---

## 六、第三方依赖引用 / Third-Party Attribution

FnixAgent 的完整 SBOM 见 [`reports/sbom.spdx.json`](../../reports/sbom.spdx.json)。

引用本项目时,如第三方组件也要提及,需注明**完整链路**:

```
基于 [Tauri 2](https://tauri.app/) (MIT/Apache-2.0),
[React](https://react.dev/) (MIT), 和
[Rust](https://www.rust-lang.org/) (MIT/Apache-2.0) 的
[FnixAgent](https://github.com/fnixagent/fnixagent)。
```

---

## 七、媒体采访引用 / Media Quotes

如需在新闻 / 采访 / 播客中引用 FnixAgent 或作者:

| 主题 | 联系邮箱 |
| --- | --- |
| 技术细节 | tech@fnixagent.dev |
| 产品方向 | hello@fnixagent.dev |
| 商用合作 | licensing@fnixagent.dev |
| 媒体采访 | press@fnixagent.dev |
| 安全研究 | security@fnixagent.dev |

---

## 八、避免的措辞 / Avoid These Phrases

| ❌ 避免 | ✅ 推荐 |
| --- | --- |
| "FnixAgent 是开源的" | "FnixAgent 是公开可见的(All Rights Reserved)" |
| "Fork 即可" | "请勿 fork,见 LICENSE" |
| "免费商用" | "需要商用授权,见 LICENSE-COMMERCIAL.md" |
| "FnixAgent 由 FnixAgent 公司开发" | "FnixAgent 由刘逸飞独立开发" |
| "本项目受 MIT 许可证约束" | "本项目受 All Rights Reserved 约束,仅供查看" |

---

## 九、参考项目 / Inspiration

FnixAgent 受以下项目启发(已在 [agent-research-report.md](../../agent-research-report.md) 中详细分析):

- [LangChain](https://github.com/langchain-ai/langchain) — Python SDK 设计参考
- [LangGraph](https://github.com/langchain-ai/langgraph) — 图规划思想
- [AutoGen](https://github.com/microsoft/autogen) — 多 Agent 协作
- [Continue](https://github.com/continuedev/continue) — VS Code 集成参考
- [Cline](https://github.com/cline/cline) — Skill 概念
- [Ollama](https://github.com/ollama/ollama) — 本地 LLM 集成
- [Tauri](https://github.com/tauri-apps/tauri) — 桌面运行时
- [Obsidian](https://obsidian.md/) — Markdown 记忆设计
- [Dify](https://github.com/langgenius/dify) — Agent 编排 UI
- [Anthropic Skills](https://docs.anthropic.com/) — Skill schema 设计
- [Microsoft TypeChat](https://github.com/microsoft/TypeChat) — 结构化输出

---

## 十、引用本项目的话术模板 / Quote Templates

### "这个项目让我印象最深的是..."

> FnixAgent 在三层任务图规划上的设计(KTG/STP/MFP)展现了
> 对 Agent 工程深度的思考,记忆层用 Markdown + Git 的方案既
> 透明又可移植。
> —— [姓名], [职位], [日期]

### 在论文 Related Work 中

> Liu [1] 提出 FnixAgent,采用 KTG/STP/MFP 三层任务图模型,
> 长期记忆用 Markdown + Git 实现可审计性。然而该模型尚未开源,
> 我们无法直接复现对比。...(后续讨论)

---

© 2024-2026 FnixAgent. All Rights Reserved.