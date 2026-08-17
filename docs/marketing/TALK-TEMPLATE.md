# 演讲模板 / Talk Templates

> 在会议 / meetup / 高校 / 公司内部分享 FnixAgent 的演讲模板。

---

## 模板 A:30 分钟技术分享(默认)

### 受众

- 工程师 / AI 开发者 / 架构师
- 假设听者熟悉 Python + LLM,不一定熟悉 Rust / Tauri

### 大纲

```
00:00 - 02:00  开场自我介绍 + 项目 30 秒
02:00 - 05:00  为什么做这个(2 个故事)
05:00 - 12:00  核心架构(三进程 + 协议)
12:00 - 18:00  关键技术(任务图 + 记忆 + Skill)
18:00 - 25:00  Demo
25:00 - 28:00  踩过的坑 / 教训
28:00 - 30:00  Q&A
```

### 详细脚本

#### 开场(2 min)

```markdown
[Slide 1: 标题]
FnixAgent: 一个本地优先的桌面 Agent 工作台

大家好,我是 [姓名],今天分享一个我做了 [时长] 的项目 — FnixAgent。

[Slide 2: 一句话定义]
"本地优先 + BYOK + 三层任务图规划的桌面 Agent"

为什么做这个?因为我用了一年 LangChain,踩了三个坑。
```

#### 为什么做(3 min)

```markdown
[Slide 3: 三个故事]

故事 1: "我让 Agent 帮我写项目文档,2 周后它忘了所有偏好"
  - 问题:短期记忆 = 短期上下文窗口
  - 后果:每次都得重新教

故事 2: "我花了 1 天搞清楚 LangChain 的 5 层 callback 是什么"
  - 问题:过度抽象
  - 后果:debug 时间 > 开发时间

故事 3: "我的 API Key 不小心 commit 进了仓库"
  - 问题:SDK 设计鼓励硬编码
  - 后果:rebase + 改 Key 全套流程

[Slide 4: 我的目标]
- 长期记忆:可审计 / 可回滚
- 架构:可解释 / 可干预
- 隐私:零信任 / 本地优先
```

#### 核心架构(7 min)

```markdown
[Slide 5: 整体架构图]
<展示 docs/architecture.svg>

四个进程,三种语言:

WebView (React) ─ IPC ─> Tauri Core (Rust) ─ stdio ─> Python agentd ─ subprocess ─> fnix-local (Rust)

[Slide 6: 三进程动机]
为什么不用 Electron?
- 体积:6-12 MB vs 80+ MB
- 内存:80-150 MB vs 400+ MB
- 安全:Rust 进程天然抗 XSS
- 性能:启动 < 1.5s

[Slide 7: 协议]
跨进程通信的 schema 在 packages/protocol/,JSON Schema + codegen

[Slide 8: Capability]
每个进程的权限被 capability/*.json 严格限制
```

#### 关键技术(6 min)

```markdown
[Slide 9: 三层任务图]
KTG ─ 年度战略
STP ─ 周计划
MFP ─ 执行流

每层独立 Schema、独立 DAG,LLM 负责跨层 decompose

[Slide 10: 长期记忆]
用户的记忆就是 Git 仓库,直接 cd ~/.fnix/memory && git log

三种检索:BM25 + 向量(sqlite-vec) + RRF 融合

[Slide 11: Skill 系统]
整个 Skill 就一个 Markdown 文件,YAML frontmatter + 正文 prompt

门槛 = 0,任何人会写 Markdown 就能写 Skill
```

#### Demo(7 min)

```markdown
[实操]
1. 启动 agentd(15s)
2. 打开 workbench(15s)
3. 演示三层任务图生成(60s)
4. 演示记忆写入 + 检索(60s)
5. 演示 Skill 执行(60s)
6. 演示 BYOK + Keychain(30s)
7. 演示 Git 历史记录(30s)
```

#### 踩过的坑(3 min)

```markdown
[Slide 12: 4 个事故]

1. LRU 设 None → 内存炸弹
2. Mock 真实资源 → 集成测试假象
3. macOS 14 没实测 → 30% 用户 OOM
4. CSP 没设置 → XSS 风险

每条都有具体 commit hash + 教训
```

#### Q&A(2 min)

```markdown
[Slide 13: 链接 + 联系]
- GitHub: github.com/fnixagent/fnixagent
- 文档: fnixagent.dev/docs
- 招聘一页纸: docs/community/HIRING-ONE-PAGER.md
- 邮箱: hello@fnixagent.dev

⚠️ All Rights Reserved,可读不可商用
```

---

## 模板 B:5 分钟闪电演讲

### 大纲

```
00:00 开场(15s)
00:15 问题(30s)
00:45 方案(2min)
02:45 Demo(1min 30s)
04:15 结束 + 链接(45s)
```

### 详细脚本

#### 开场(15s)

```markdown
我做了 30k 行的桌面 Agent 项目,学到一件事:
**长期记忆应该是 Git 仓库**。
```

#### 问题(30s)

```markdown
Agent 工具普遍"金鱼脑":
- 短期记忆 = 上下文窗口,清掉就没了
- 长期记忆 = 黑盒向量数据库,你看不到

结果:用户不被记住,Agent 永远"陌生人"
```

#### 方案(2 min)

```markdown
我的方案:把记忆存成 Markdown 文件,整个目录是 Git 仓库。

[架构图]
~/.fnix/memory/
├── core/user.md
├── episodic/2026-08-17.md
└── semantic/index.sqlite

用户直接 `git log`,看到自己被记住什么。
搜索走 BM25 + 向量,RRF 融合。

意外收获:用户可以 `git checkout` 回滚误操作。
```

#### Demo(1 min 30s)

```markdown
[实操]
- 写一条记忆
- git status
- git log --oneline (展示版本化)
- 检索 + 看命中片段
```

#### 结尾(45s)

```markdown
项目地址:github.com/fnixagent/fnixagent
⚠️ All Rights Reserved,可看不能用

谢谢。
```

---

## 模板 C:技术 Workshop(2 小时)

### 适合谁

- 50 人以内,
- 想实际跑代码的工程师

### 大纲

```
00:00 - 00:15  开场 + 项目演示
00:15 - 00:30  部署环境(每人 clone + install)
00:30 - 01:00  Step 1: 写第一个 Skill
01:00 - 01:30  Step 2: 配置 BYOK + LLM Provider
01:30 - 02:00  Step 3: 扩展 - 加自定义工具
```

### 准备

- 提前部署 docker-compose,每人一键启动
- 准备 GitHub Codespaces 配置(无需本地装环境)
- 准备好 Skill 模板让学员填

### 步骤 1:Hello Skill

```markdown
# 任务
每个学员在 5 分钟内创建一个 Skill,功能是"打招呼"。

# 给的模板
~/.fnix/skills/hello/SKILL.md
---
skill: hello
version: 1.0.0
inputs:
  - name: name
    type: string
---

# Hello Skill

向 ${name} 致以问候。
```

### 步骤 2:BYOK

```markdown
# 任务
1. 打开 fnix web UI
2. 进入 Settings → API Keys
3. 配置 OpenAI / Ollama
4. 验证调用成功
```

### 步骤 3:加自定义工具

```markdown
# 任务
在 Skill 中加入 `fs.read` 工具,读一个本地文件返回摘要。

提示:
tools:
  - fs.read
```

---

## 模板 D:招聘专场(15 min,内部分享)

### 大纲

```
00:00 - 01:00  项目概览(招聘向)
01:00 - 05:00  技术亮点(对应 5 个面试题)
05:00 - 10:00  Demo
10:00 - 12:00  怎么评估类似能力
12:00 - 15:00  Q&A
```

### 关键点

- 不要炫技:招聘方关心的是"你能不能干活"
- 用业务语言:不说"KTG",说"任务的战略/战术/执行分层"
- 强调工程纪律:"我写了 5 个 ADR + 60 篇文档 + 8 个 CI"
- 强调安全意识:"所有 API Key 在 OS Keychain,我服务端拿不到"

---

## 演讲技巧

### 视觉

- 配色:统一品牌色 (#FF6B35 + 黑白灰)
- 字体:Inter / 思源黑体 / 苹方
- 模板:[slides.com/fnixagent](https://slides.com/fnixagent)(TODO)
- 字号:正文 ≥ 24pt,标题 ≥ 36pt

### 节奏

- 不要念 slides,讲故事
- 每 5 分钟切换一次"形态"(slide → demo → talk)
- 提前彩排 2 次以上

### 应对 Q&A

| Q | A |
| --- | --- |
| 为什么不直接用 LangChain? | (参考[INTERVIEW-PREP](../community/INTERVIEW-PREP.md)) |
| 三层任务图有什么实际收益? | 用具体场景讲 |
| 商业化打算? | 个人作品集项目,不商用 |
| 这个项目最难的部分是什么? | 跨进程 schema 一致性 / 长期记忆的隐私分级 |

---

## 录音 / 录屏

如果会议允许:

- OBS 录制(免费)
- 上传 B站 + YouTube
- 添加章节标记(chapters)
- 加中英双语字幕(用 whisper / 剪映)

---

## PPT 模板

`assets/talks/template.pptx`(TODO,可付费购买)

自建推荐:

- Google Slides → 导出 PDF
- reveal.js(HTML,适合嵌入代码 demo)
- Slidev(Markdown 写 slides,Vue 渲染)

---

## 反馈收集

演讲结束后:

- 收集反馈:[forms.gle/fnixagent-talk](https://forms.gle)(TODO)
- 发 PPT + Demo 代码到 GitHub Release
- 写一篇博客:[BLOG-TEMPLATE.md](BLOG-TEMPLATE.md) 技术深度文

---

© 2024-2026 FnixAgent. All Rights Reserved.