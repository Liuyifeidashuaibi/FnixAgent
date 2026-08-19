# Demo 录制脚本 / Recording Script

> **总时长**:5 分 30 秒
> **格式**:1280×720 (16:9) MP4
> **录制工具**:OBS Studio(免费,Windows/Mac/Linux)
> **剪辑**:剪映(中文字幕自动生成)
> **上传**:B 站 + YouTube

---

## 录制前检查清单

- [ ] FnixAgent agentd 已启动(`fnix start`)
- [ ] 桌面 App 打开,登录状态干净
- [ ] 系统通知 / 弹窗全部关闭(防止录制中出现)
- [ ] 鼠标指针光标动画关闭(录制更干净)
- [ ] 分辨率调到 1920×1080(让 OBS 缩放)
- [ ] 麦克风测试录音(用耳机确认无回音)

---

## 完整脚本(逐字稿)

### 🎬 开场(0:00 - 0:15)

**[画面]:桌面 App 主界面,光标移到 FnixAgent 图标**

> **旁白**:
>
> "大家好,我是刘逸飞。今天用一个 5 分钟的视频,
> 演示一下我做的桌面 Agent 项目 FnixAgent。"

**[字幕]**:FnixAgent - 5 分钟 Demo - 刘逸飞

---

### 🎬 第一幕:启动 + 整体感受(0:15 - 1:00)

**[画面]:从命令行 `fnix start` 到桌面 App 加载完整(加速 4x),展示主界面**

> **旁白**:
>
> "FnixAgent 是本地优先的桌面 Agent 工作台。
> 它跨进程运行:WebView 跑 React UI,Tauri Core 用 Rust 管权限,
> Python agentd 是业务核心,还有个 Rust 沙箱做最后一道防线。
> 整个安装包 6 MB,启动 1.5 秒。"

**[字幕 - 架构图弹出]**

```
WebView (React) → Tauri Core (Rust) → Python agentd → Rust Sandbox
```

---

### 🎬 第二幕:三层任务图规划(1:00 - 1:45)

**[画面]:在 UI 里输入"为 FnixAgent 添加 Docker 部署",点 Plan**

> **旁白**:
>
> "这是核心创新 — KTG / STP / MFP 三层任务图。
> 上面是季度战略,中间是周计划,下面是会话级执行步骤。
> 用户可以在任意一层干预,不像 LangGraph 那种黑盒单层图。"

**[字幕 - 切换到 STP 视图,展示节点依赖]**:
> "现在 LLM 把这个任务拆成了 5 个里程碑,每个有依赖关系。"

**[字幕 - 切换到 MFP 视图,展示步骤]**:
> "再拆到执行层,每一步是工具调用或者子 Agent。"

---

### 🎬 第三幕:长期记忆(1:45 - 2:30)

**[画面]:在 UI 里"Memory"面板,展示 episodic 目录**

> **旁白**:
>
> "用户记忆存在 Markdown 文件里,整个目录是 Git 仓库。
> 用户直接 `cd ~/.fnix/memory && git log` 看自己被记住了什么。
> 检索走 BM25 + 向量融合。"

**[字幕 - 切换到终端,`cd ~/.fnix/memory && git log --oneline`]**:
> "看,这是 200+ 条记忆的 git 历史。完全可审计、可回滚。"

**[画面 - UI 里输入"我之前说过我喜欢 Rust 吗?",Agent 引用历史回答]**:
> "跨会话调用,Agent 真的'记住'了用户的偏好。"

---

### 🎬 第四幕:Skill 系统(2:30 - 3:15)

**[画面]:打开 Skill 编辑器,展示 `~/.fnix/skills/code-review/SKILL.md`**

> **旁白**:
>
> "FnixAgent 的 Skill 系统就一个 Markdown 文件,
> YAML 头定义输入输出,正文就是 prompt。
> 任何人会写 Markdown 就能写 Skill。"

**[字幕 - 切到代码审查运行,展示结构化输出]**:

```
verdict: "request_changes"
summary: "..."
issues: [{severity, line, message}, ...]
```

> "执行 Skill 返回结构化 JSON,不是模糊的自然语言。"

---

### 🎬 第五幕:BYOK + OS Keychain(3:15 - 4:00)

**[画面]:设置 → API Keys,展示 OS Keychain 集成**

> **旁白**:
>
> "API Key 不存在磁盘,存在系统 Keychain 里。
> macOS 是 Keychain,Windows 是 Credential Manager,Linux 是 Secret Service。
> FnixAgent 服务端拿不到,即使数据库被入侵也泄漏不了。"

**[字幕 - 在终端 `security find-generic-password -s fnixagent`(macOS)]**:
> "看,Key 在这里,FnixAgent 进程只能按需读取。"

**[画面 - 调用云端 LLM,展示响应]**:
> "需要时调用云端  LLM,prompt 走 HTTPS,Key 仍然在 Keychain。"

---

### 🎬 第六幕:项目数据快闪(4:00 - 4:45)

**[画面]:VSCode 打开项目根目录,文件树快闪 8 秒(加速 6x)**

> **旁白**:
>
> "项目现在 30k 行代码,800+ commits,60+ 文档,
> 5 个 ADR,8 个 GitHub Actions workflow,38 个标签体系,
> 200+ 测试用例覆盖核心模块。"

**[字幕快闪 - 数字大字幕]**:

```
30k LoC · 800+ commits · 60+ docs
5 ADRs · 8 GH Actions · 38 labels
200+ tests · 85% coverage
```

**[画面 - 切到 docs/ADR/,展示 5 个 ADR 文件]**:
> "每个架构决策都有 ADR 记录,这是顶级开源项目的标配。"

---

### 🎬 结尾(4:45 - 5:30)

**[画面]:GitHub 项目页面,README 顶部,配 og-image 预览]**

> **旁白**:
>
> "代码在 GitHub 上 Liuyifeidashuaibi/FnixAgent。
> 项目以 PolyForm Noncommercial 1.0.0 发布:可自由使用与学习,禁止商用。
> 谢谢观看。""

**[字幕 - 大字结尾]**:

```
github.com/Liuyifeidashuaibi/FnixAgent
PolyForm Noncommercial 1.0.0
docs/community/HIRING-ONE-PAGER.md
```

**[音乐渐弱,3 秒黑屏]**

---

## 章节标记 / Chapters (上传到 B站 / YouTube 用)

```
0:00 开场
0:15 启动 + 整体感受
1:00 三层任务图规划
1:45 长期记忆(Markdown + Git)
2:30 Skill 系统(Markdown DSL)
3:15 BYOK + OS Keychain
4:00 项目数据快闪
4:45 结尾 + GitHub
```

---

## 字幕文件 / Subtitle

剪映 / Whisper 自动生成后,**手工校对**以下专有名词:

| 术语 | 不要错写成 |
| --- | --- |
| Tauri 2 | "Tory" "Taury" |
| BYOK | "BYOK" 不要翻译 |
| Keychain | "Key Chain" "钥匙链" |
| Markdown | "Mark Down" |
| LangGraph | "Lang Graph" |
| KTG / STP / MFP | 不展开解释,字幕照搬 |
| PolyForm Noncommercial 1.0.0 | "非商业使用许可" |

---

## 标题 / Title (B站 / YouTube)

```
5 分钟看懂 FnixAgent:本地优先的桌面 Agent 工作台(面试作品)
```

### 中文标题候选

- "我用 Tauri + Python + Rust 做了个桌面 Agent 框架(开源治理 60+ 文档)"
- "FnixAgent 5 分钟 Demo:三层任务图 + Markdown+Git 记忆 + BYOK"

### English Title

- "FnixAgent in 5 minutes: Local-First Desktop Agent with 3-Layer Task Graph"
- "I built a desktop AI agent in Tauri+Python+Rust (here's what I learned)"

---

## 简介 / Description (B站)

```
FnixAgent 是我用 Tauri 2 + Python 3.12 + Rust 做的本地优先桌面 Agent 工作台。

核心创新:
🧠 三层任务图规划 (KTG/STP/MFP) — 区别于 LangGraph 单层图
📚 长期记忆 = Markdown + Git 仓库 — 完全可审计
📝 Skill 系统用纯 Markdown — 门槛比 LangChain 低 10 倍
🔒 BYOK + OS Keychain — API Key 永远不离开用户电脑

技术栈:Tauri 2 / React 18 / Python 3.12 / Rust / uv / SQLite + sqlite-vec

项目治理 (顶级开源项目标准):
- 5 个 ADR (MADR 4.0 规范)
- 60+ 文档(架构/用户/开发/运营/营销/法律)
- 8 个 GitHub Actions workflows
- 38 个分类标签
- 200+ 测试用例,核心模块 85% 覆盖率

⚠️ 本项目以 PolyForm Noncommercial 1.0.0 方式发布
可以浏览学习,但禁止 fork / 商用 / 代码复用

GitHub: github.com/Liuyifeidashuaibi/FnixAgent
文档: docs/community/HIRING-ONE-PAGER.md

#AI #Agent #Tauri #Python #Rust #开源项目 #面试 #个人项目
```

---

## 标签 / Tags

```
FnixAgent Agent Tauri Python Rust OpenSource BYOK LLM
桌面应用 编程 开源 个人项目 程序员 面试
AI Agent 工程 架构设计 软件工程
```

---

## 录制命令 (OBS)

```bash
# 录制 1920x1080 @ 30fps
obs --startrecording --collection "FnixAgent Demo"

# 或在 OBS UI 里手动:
# Sources -> Display Capture -> 选主显示器
# Settings -> Video -> 1920x1080, 30fps
# Settings -> Audio -> 麦克风
# Controls -> Start Recording
```

---

## 后期剪辑流程

1. **导入**:剪映打开 OBS 录的 mp4
2. **加速**:第 1 幕启动部分加速 4x
3. **章节标记**:在关键时间点加章节标记
4. **字幕**:
   - 剪映"智能字幕"自动生成
   - 手工校对专有名词
   - 字体选思源黑体,白色 + 黑色描边
5. **背景音乐**:极轻的电子 lo-fi,音量 15%
6. **片头片尾**:用 Figma 做 5 秒片头(Logo + 标题)
7. **导出**:1080P H.264,码率 8000 kbps
8. **上传**:
   - B 站:挂"科技区"标签,加封面 1280×720
   - YouTube:选英文标题 + 简介,挂 "Tech / Programming"

---

## 发布后

1. 把视频链接放到:
   - GitHub README 顶部
   - 个人简历
   - LinkedIn / 知乎 / 小红书 个人介绍
2. 1 周后看数据:流量 / 收藏 / 评论
3. 必要时出 "Q&A" 续集回复评论区高频问题

---

## 上传封面设计 (1280×720)

**建议元素**:

- 左上角:FnixAgent Logo (大,200×200)
- 中间偏左:项目名 + 副标题
- 右侧:屏幕截图(主界面 或 任务图)
- 底部:GitHub URL

**风格**:深色背景 (`#0A0A0A`) + 灰阶 Logo + 白色文字。

**工具**:Canva / Figma / Sketch,模板选择 "Tech YouTube Thumbnail"。

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.