# Press Kit / 媒体素材包

> 给媒体、博主、招聘官使用的官方素材合集。

---

## ⚠️ 重要版权说明

本 Press Kit 中的所有素材(Logo、图片、设计稿、截图、数据可视化)
均受 [LICENSE](../../LICENSE) 与 [TRADEMARKS.md](../../TRADEMARKS.md) 约束。

**允许使用**:

- ✅ 编辑性使用(技术博客、新闻报道、学术论文)
- ✅ 个人简历 / 作品集
- ✅ 教学幻灯片(标注出处)
- ✅ 招聘相关使用(招聘官查看项目作品)

**不允许使用**:

- ❌ 商业培训课程
- ❌ 商品 / 服务宣传
- ❌ 暗示背书
- ❌ 修改 Logo 颜色 / 比例
- ❌ 抹除版权信息

如有疑问:`press@fnixagent.dev`

---

## 1. 项目一句话 / Elevator Pitch

**中文 (60 字以内)**:

> FnixAgent 是一个本地优先、BYOK 的桌面 Agent 工作台,具备三层任务图规划
> 和 Markdown+Git 版本化长期记忆。个人作品集项目,代码不可商用。

**English (60 words)**:

> FnixAgent is a local-first, BYOK desktop agent workbench featuring
> three-layer task graph planning and versioned long-term memory via
> Markdown + Git. A personal portfolio project; the source code is
> proprietary (All Rights Reserved).

---

## 2. 项目简介 / Short Description

**100 字**:

> FnixAgent 是刘逸飞独立开发的桌面 Agent 工作台,采用 Tauri 2 + Python +
> Rust 三进程架构,实现本地优先、隐私优先的 AI 助手体验。核心创新是 KTG /
> STP / MFP 三层任务图规划模型,以及把长期记忆存储为 Git 仓库(完全可审计)。
> 支持调用本地 LLM(Ollama / LM Studio)和云端 LLM(OpenAI / Anthropic),但
> API Key 由用户用 OS Keychain 管理,FnixAgent 不接触。项目以 All Rights
> Reserved 方式发布,GitHub 上可阅读但禁止 fork / 商用。

---

## 3. 项目长介绍 / Long Description

**500 字**:

> FnixAgent 是一个跨进程 (Tauri 2 + Python + Rust) 的桌面 Agent 工作台,
> 由刘逸飞独立开发并维护。
>
> **为什么需要它?** 当前的 AI Agent 工具有两类极端:
>    1. 云端 SaaS(数据离开你的电脑,被锁定)
>    2. DIY 脚本(隐私好但用户体验差)
>
> FnixAgent 走"中间路线":数据默认留在本地,UI 像 IDE 一样精致,
> 同时支持 BYOK(用户自带 OpenAI / Anthropic Key)。
>
> **核心创新**:
>    - **三层任务图规划模型 (KTG / STP / MFP)**:区别于 LangGraph 单层图,
>      把任务分成"战略 / 战术 / 执行"三个时间跨度
>    - **Markdown + Git 长期记忆**:用户的记忆就是 Git 仓库,可读、可审计、可回滚
>    - **"Markdown 即代码"的 Skill 系统**:任何会写 Markdown 的人都能写 Skill
>    - **BYOK + OS Keychain**:API Key 用 macOS Keychain / Windows Credential
>      Manager 存储,FnixAgent 服务端永远看不到
>    - **三进程隔离**:WebView / Tauri Core / Python agentd / Rust Sandbox
>      分层,Capability 最小化
>
> **技术栈**:Tauri 2 + React 18 + TypeScript + Python 3.12 + Rust + uv + SQLite
> + sqlite-vec + Ollama / OpenAI / Anthropic SDK。
>
> **许可证**:本项目以 **All Rights Reserved** 方式发布。可以在 GitHub 上
> 浏览代码、学习设计,但严禁 fork、商用、代码复用。详见
> [LICENSE](../../LICENSE)。
>
> **目标用户**:面向大厂求职的高级工程师、隐私敏感的开发者、研究 Agent
> 架构的学者。

---

## 4. Logo 与图片 / Logo & Images

### Logo (官方)

- 矢量 SVG:[`assets/brand/logo.svg`](../../assets/brand/logo.svg)
- 1280×640 og-image:[`assets/brand/og-image.png`](../../assets/brand/og-image.png)
- 32x32 icon:[`assets/brand/icon-32.png`](../../assets/brand/icon-32.png)
- 256x256 icon:[`assets/brand/icon-256.png`](../../assets/brand/icon-256.png)

**使用规则**:

- 最小尺寸:Web 32×32 px,印刷 8 mm
- 留白:Logo 高度 1× 的空白区
- **禁止**修改颜色、比例、添加阴影、与其他 Logo 组合

### 截图 / Screenshots

| 场景 | 文件 |
| --- | --- |
| 主界面 | `assets/screenshots/main.png` |
| 任务图规划 | `assets/screenshots/plan.png` |
| 记忆管理 | `assets/screenshots/memory.png` |
| Skill 编辑 | `assets/screenshots/skill-editor.png` |
| 设置 | `assets/screenshots/settings.png` |

所有截图均可用于编辑性使用,须标注 "截图来自 FnixAgent"。

### 架构图 / Architecture Diagrams

SVG 矢量,见 [`docs/architecture.svg`](../../docs/architecture.svg)、
[`docs/data-flow.svg`](../../docs/data-flow.svg) 等。

---

## 5. 关键数据 / Key Numbers

(截至 2026-08-17)

| 指标 | 数值 |
| --- | --- |
| 提交数 | 800+ |
| 代码行数 | ~30k |
| 文档文件 | 60+ |
| 架构决策记录 | 5 |
| 内置 Skill | 8 |
| GitHub Actions | 8 |
| 标签体系 | 38 |
| 测试用例 | 200+ |
| 测试覆盖率(核心) | 85% |

---

## 6. 关键人物 / Key People

**刘逸飞 (Liu Yifei)**
- 角色:FnxAgent 设计与开发者
- 邮箱:hello@fnixagent.dev
- GitHub:[@fnixagent](https://github.com/fnixagent)
- Twitter / X:[@fnixagent](https://twitter.com/fnixagent)

---

## 7. 联系 / Contact

| 用途 | 邮箱 |
| --- | --- |
| 媒体采访 | press@fnixagent.dev |
| 商用授权 | licensing@fnixagent.dev |
| 安全漏洞 | security@fnixagent.dev |
| 一般咨询 | hello@fnixagent.dev |

**响应时间**:工作日 48 小时内

---

## 8. 常见问题 (媒体版) / FAQ for Press

### "FnixAgent 是开源的吗?"

不是。本项目以 **All Rights Reserved** 方式发布。GitHub 上**可阅读**代码,
但**禁止**复制、修改、商用、Fork、衍生创作。这是个人作品集项目,
目的是展示工程能力,不是社区项目。

### "为什么不让开源?"

这是一个**个人简历作品集项目**,目标是向大厂招聘官展示工程能力,
不是社区协作型开源项目。开源会带来商标盗用、商业化分叉、维护负担等
问题,与项目目标不符。详见 [LICENSE](../../LICENSE)。

### "那你希望被怎么使用?"

希望:

- 招聘官在评审简历时能浏览代码,了解作者能力
- AI 工程研究者阅读论文 / 架构文档,作为参考
- 个人学习 Agent 架构的开发者参考设计

**不希望**:

- 商业公司基于此项目 fork 商用
- 培训机构包装成付费课程
- 抹除版权信息后重新分发

### "技术亮点是什么?"

三层任务图规划 + Markdown + Git 长期记忆 + 三进程隔离架构 + BYOK +
Skill 系统。具体见 [`docs/community/HIRING-ONE-PAGER.md`](../community/HIRING-ONE-PAGER.md)。

---

## 9. 引用模板 / Boilerplate

### 中文

> FnixAgent 是刘逸飞开发的桌面 Agent 工作台,采用 Tauri 2 + Python + Rust
> 三进程架构,以 All Rights Reserved 方式发布,GitHub:github.com/fnixagent/fnixagent。

### English

> FnixAgent is a desktop agent workbench developed by Liu Yifei, featuring
> a Tauri 2 + Python + Rust three-process architecture. Released under
> All Rights Reserved; GitHub: github.com/fnixagent/fnixagent.

---

© 2024-2026 FnixAgent. All Rights Reserved.