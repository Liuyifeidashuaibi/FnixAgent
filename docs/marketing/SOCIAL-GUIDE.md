# 社交媒体指南 / Social Media Guide

> 在 X / 小红书 / 知乎 / B站 等平台发 FnixAgent 内容时的最佳实践。

---

## 一、平台差异 / Platform Differences

| 平台 | 用户群 | 内容风格 | 长度 |
| --- | --- | --- | --- |
| **X / Twitter** | 全球开发者 | 简洁、有冲击力 | < 280 字 / 推文串 |
| **小红书** | 中文年轻用户 | 故事化、视觉化 | 500-1000 字 + 多图 |
| **知乎** | 中文技术深度读者 | 长文、专业 | 2000-5000 字 |
| **B站** | 视频观众 | 教程、对比 demo | 5-15 分钟视频 |
| **LinkedIn** | 全球职场人 | 职业向、招聘向 | 800-1500 字 |
| **微信公众号** | 中文长文读者 | 深度文章 | 2000-5000 字 |

---

## 二、Twitter / X 模板

### 模板 1:项目发布

```
🔒 FnixAgent v0.5.0 Released

Local-first desktop AI workbench with:
- 3-layer task graph (KTG/STP/MFP)
- Markdown+Git long-term memory
- BYOK via OS Keychain

⚠️ All Rights Reserved — personal portfolio, view only.

GitHub: github.com/fnixagent/fnixagent
```

### 模板 2:技术洞察

```
我做了 800+ commits / 30k LoC 的桌面 Agent 项目后,学到的 5 件事:

1. BYOK 不是 feature,是 foundation
2. 长期记忆 = Git 仓库 = 零审计成本
3. 三进程隔离 > 单进程便利
4. Skill 用 Markdown 写,门槛直降 10x
5. 文档矩阵比代码更重要

🧵 Thread
```

### 模板 3:招聘向

```
我在 GitHub 上做了个桌面 Agent 框架:

- Tauri 2 + Python + Rust 三进程
- KTG/STP/MFP 三层任务图
- Markdown+Git 长期记忆
- 5 个 ADR + 60+ 文档

⚠️ All Rights Reserved,可看不能用,目的是简历作品。

🔗 github.com/fnixagent/fnixagent

#AI #OpenSource #Engineering
```

### 模板 4:对比

```
我用 LangChain 一年,最后自己造了 Agent 框架。

为什么?

- LangChain 太抽象,出问题 debug 痛苦
- 我需要 BYOK + 本地 LLM,LangChain 不支持
- 我要可审计的长期记忆,LangChain 没有
- 我要中文 + 本地化,LangChain 是英文优先

现在我有了 FnixAgent:
github.com/fnixagent/fnixagent

🧵 为什么 + 怎么做的
```

---

## 三、小红书模板

### 标题党但不要假

```
✅ 好标题:
- "我做了一年的 Agent 项目,踩过的 5 个坑"
- "我为什么把 LLM 记忆存成 Git 仓库"
- "30k 行代码 / 60 篇文档,我的桌面 Agent 开源了"
- "Agent 工程实战:BYOK + 三层任务图"

❌ 差标题:
- "震惊!我做了一个改变世界的项目"
- "程序员必看!错过后悔"
- "吊打 LangChain 的国产 AI 框架"
```

### 正文结构

```markdown
🌟 项目简介(1 段)
我做了一个桌面 Agent 项目 FnixAgent...
(配 1 张 logo + 主界面截图)

💡 核心创新(2-3 段,每段配 1 张图)
1. 三层任务图 (KTG/STP/MFP)
2. Markdown+Git 长期记忆
3. BYOK + OS Keychain

🎯 适合谁(1 段)
想做 Agent 工程的 / 对隐私敏感的 / 想看顶级工程治理的

⚠️ 注意
All Rights Reserved,可以看但不能用哦

📚 链接
- GitHub: ...
- 文档: ...
- 招聘一页纸: ...
```

### 配图要求

- 封面:1 张主图,1280×640 (og-image 尺寸)
- 正文:5-9 张,每张 1080×1080 或 3:4
- 工具:Canva / Figma / 截图 + 标注
- 风格:简洁,统一字体(思源黑体 / Inter)

### 标签

```
#AI #Agent #开源项目 #程序员 #代码 #GitHub #Python #Rust
#个人项目 #工程师 #AI工程师 #编程 #技术分享
```

---

## 四、知乎模板

### 回答(适合答"如何做 Agent"类问题)

```markdown
作为做过 30k 行桌面 Agent 项目的过来人,
分享几个关键点:...

## 1. 进程隔离(WebView / Tauri Core / Python agentd)

(贴架构图 + 300 字解释)

## 2. 任务图规划(三层 KTG/STP/MFP)

(贴 SVG + 500 字解释)

## 3. 长期记忆(Git 仓库)

(贴示例 + 400 字解释)

## 4. BYOK(OS Keychain)

(贴代码 + 300 字解释)

## 5. Skill 系统(Markdown DSL)

(贴 Skill 示例 + 300 字解释)

完整项目:github.com/fnixagent/fnixagent (All Rights Reserved,可读不可用)
```

### 文章(适合"Agent 工程实践"类话题)

用 [BLOG-TEMPLATE.md](BLOG-TEMPLATE.md) 的"技术深度文"模板。

---

## 五、B站视频脚本

### 5 分钟技术 Demo 结构

```
00:00 开场 (15s)
  "大家好,我是刘逸飞,今天演示 FnixAgent 这个桌面 Agent 项目"

00:15 问题背景 (45s)
  "传统 Agent 工具有两类问题..."
  (配 slides)

01:00 项目演示 (2min 30s)
  - 启动:30s
  - 三层任务图:30s
  - 长期记忆:30s
  - Skill 系统:30s
  - BYOK:30s

03:30 关键设计讲解 (1min)
  - 三进程架构
  - 为什么 Tauri 不是 Electron
  - 为什么不用 LangChain

04:30 结尾 (30s)
  "代码在 GitHub 上,All Rights Reserved,大家可以看不能用"
  (放链接 / 联系方式)
```

### 录制工具

- 屏幕:ScreenFlow / OBS
- 剪辑:Final Cut Pro / DaVinci Resolve
- 字幕:剪映 / 必剪
- 封面:1280×720,大字号 + 主视觉

---

## 六、LinkedIn 模板(招聘向)

### 中文

```
过去 1 年,我独立完成了 FnixAgent 这个桌面 Agent 工作台:

📐 三进程架构:Tauri 2 + Python + Rust
🧠 三层任务图:KTG / STP / MFP(战略 / 战术 / 执行)
📚 长期记忆:Markdown + Git(零审计成本)
🔒 BYOK:macOS Keychain / Windows Credential Manager
📝 Skill 系统:Markdown DSL
📊 完整治理:5 ADR + 60 文档 + 8 CI workflow + 38 labels
🔍 测试:200+ 用例,核心模块 85% 覆盖

⚠️ 这是个人作品集项目,All Rights Reserved,
GitHub 上可阅读但禁止商用 / Fork。

技术深度:
- 跨语言 IPC 协议设计
- 长期记忆的版本化存储
- LLM 调用性能优化
- 安全威胁建模 (STRIDE)

适合岗位:
- AI Engineer / Agent Engineer
- 系统架构师
- 资深前端 / Rust / Python

欢迎面试官查看:github.com/fnixagent/fnixagent

#AI #Agent #Engineering #Hiring #OpenSource
```

### English

```
Over the past year, I've built FnixAgent, a local-first desktop
agent workbench:

🏗️ 3-process architecture: Tauri 2 + Python + Rust
🧠 3-layer task graph: KTG/STP/MFP
📚 Long-term memory: Markdown + Git
🔒 BYOK via OS Keychain
📝 Skill system: Markdown DSL
📊 Full governance: 5 ADRs + 60 docs + 8 CI workflows
🔍 Testing: 200+ cases, 85% coverage in core modules

⚠️ Personal portfolio project, All Rights Reserved.
Viewable on GitHub but no commercial use / forking.

Open to:
- AI Engineer / Agent Engineer roles
- System Architect
- Senior Frontend / Rust / Python

GitHub: github.com/fnixagent/fnixagent
```

---

## 七、抖音 / 视频号 (面向大众)

### 30 秒脚本

```
[画面:打开 FnixAgent]
"这个 AI 助手..."

[画面:输入"用 Rust 写 hello world"]
"...能跑在你电脑上"

[画面:任务图弹出]
"...能规划多步任务"

[画面:记忆库展示]
"...能记住你的偏好"

[画面:BYOK 设置]
"...而且 Key 在你钥匙串里,我看不到"

[文字:Github:fnixagent/fnixagent]
"个人作品,代码只读"
```

---

## 八、不要做的事

| ❌ 行为 | 后果 |
| --- | --- |
| 用夸张标题 | 失去技术圈信任 |
| 蹭热点但内容跑题 | 算法降权 |
| 抹除版权 / Logo | 法律风险 |
| 公开 API Key | 永远不要 |
| 与竞品直接对比贬低 | 显得不专业 |
| 承诺不切实际的功能 | 信任崩塌 |
| 拉踩国产 / 国外 | 引发争议 |

---

## 九、数据复盘

每发一篇,记录:

| 日期 | 平台 | 标题 | 阅读 / 互动 |
| --- | --- | --- | --- |

月底复盘:

- 哪个平台流量最大?
- 哪种类型互动最多?
- 哪类内容带来了招聘机会?

---

© 2024-2026 FnixAgent. All Rights Reserved.