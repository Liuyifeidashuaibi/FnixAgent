# 面试准备 / Interview Prep

> 这个项目适合用来回答哪些面试题?
> 每题给一段 1-2 分钟的口头回答 + 延伸阅读链接。

---

## 一、架构题

### Q1: 讲讲你这个项目的整体架构?

**答(60 秒)**:

> FnixAgent 是三层进程架构。**WebView 进程**跑 React UI,**Tauri Core 进程**(Rust)
> 负责窗口、IPC、Capability 检查、文件系统白名单,**Python agentd 进程**是业务核心,
> 跑 LLM 客户端、记忆、规划。Tauri Core 与 agentd 通过 stdio JSON-RPC 通信。
>
> 关键设计:
> 1. **三进程隔离**避免 WebView XSS 直接控制 shell
> 2. **Capability 白名单**最小化每个进程的权限
> 3. **fnix-local Rust 沙箱**作为最后一道防线,用 ulimit 隔离资源
>
> 具体在 [ARCHITECTURE.md](../../ARCHITECTURE.md) 和 [ADR-0001](../adr/0001-tauri-desktop-runtime.md)。

**延伸阅读**:

- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/architecture.svg](../../docs/architecture.svg)
- [ADR-0001](../adr/0001-tauri-desktop-runtime.md)

---

### Q2: 为什么不直接用 Electron / 浏览器扩展?

**答**:

> Electron 80+ MB 内存 400+ MB,且 Chromium 安全面大。浏览器扩展权限模型
> 复杂、API 受限、不能直接跑本地 LLM。
> Tauri 2 用系统 WebView,安装包 6-12 MB,内存 80-150 MB,Rust 进程天然抗 XSS。
> 另外浏览器扩展走 Manifest V3 后,**所有网络请求**都要经过 Chrome,
> 不利于 BYOK 隐私要求。

**延伸阅读**:

- [docs/COMPARISON.md](../COMPARISON.md)
- [ADR-0001](../adr/0001-tauri-desktop-runtime.md) — Alternatives Considered

---

### Q3: 你的三层任务图是怎么设计的?

**答**:

> 受 LangGraph 启发,但 LangGraph 是单层图。复杂任务需要时间跨度的表达:
> **KTG**(年度战略)、**STP**(周计划)、**MFP**(执行流)。
> 三层独立 Schema、独立 DAG,用户可以在任意层干预。
> LLM 负责跨层 decompose / schedule / reflect / learn。
> 设计在 [ADR-0004](../adr/0004-three-layer-task-graph.md)。

**追问准备**:

- Q: MFP 死循环怎么办?
  A: MFP 有 max_steps(默认 100) + 用户可手动 cancel + 失败后回到 STP 重排
- Q: KTG 不就只是个文件吗?
  A: KTG 是嵌套数据结构,每节点有 progress、children、deps,支持合并多个 Agent 的 KTG

---

## 二、AI / LLM 题

### Q4: Agent 怎么"记住"用户?

**答**:

> 三类记忆:
> 1. **核心记忆**(`~/.fnix/memory/core/`):用户画像、长期偏好,Markdown 文件
> 2. **情景记忆**(`episodic/YYYY-MM-DD.md`):每次对话的关键事件
> 3. **语义记忆**:`sqlite-vec` 向量索引,BM25 + RRF 融合
>
> 整个 `~/.fnix/memory/` 是 Git 仓库,**直接 `git log` 看记忆历史**。
> 这是我设计里**最自豪的**部分 — 透明、可审计、可回滚。

**延伸阅读**:

- [ADR-0003](../adr/0003-markdown-git-memory.md)
- [docs/memory-architecture.svg](../../docs/memory-architecture.svg)

---

### Q5: Prompt 注入怎么防?

**答**:

> 三层防御:
> 1. **Skill Capability 最小化** — 每个 Skill 只能用自己声明的工具
> 2. **三级 Safety 分级** — `safe` / `moderate` / `dangerous`,后者每次都要用户确认
> 3. **输入校验** — 所有 IPC 参数、Skill 输入都过 schema 校验
>
> 剩余风险靠 LLM 输出再校验(例如代码执行前 AST 解析)。

**延伸阅读**:

- [docs/security/THREAT-MODEL.md](../security/THREAT-MODEL.md) — T-T3, T-T5, T-E1

---

### Q6: 怎么评估 Agent 的输出质量?

**答**:

> 三个层面:
> 1. **Skill 输出 schema 校验** — 强类型输出,LLM 必填字段缺失直接重试
> 2. **MFP 步骤回放** — 任意时刻可以回放执行链,人工 review
> 3. **用户反馈循环** — 用户可标 👍 / 👎,进入记忆衰减训练
>
> 没有用 RLHF,因为是个人作品集。生产环境会接 LangSmith / Helicone。

---

## 三、工程题

### Q7: Python / Rust / TypeScript 跨语言怎么协同?

**答**:

> 两种 IPC:
> 1. **Tauri IPC**(WebView ↔ Tauri Core Rust):基于 `invoke()` 函数,自动序列化 JSON
> 2. **stdio JSON-RPC**(Tauri Core ↔ Python agentd):子进程 stdin/stdout,自定义 schema
>
> 关键点:**所有跨语言边界都强类型 + schema 校验**,避免运行时类型 bug。
> 共享类型用 `packages/protocol/`(JSON Schema) + `packages/sdk/`(Pydantic + Zod 同步生成)。

---

### Q8: 为什么用 uv 而不是 poetry / pip?

**答**:

> **uv 安装比 poetry 快 10-100 倍**,锁文件 (`uv.lock`) 是 TOML 格式
> 审查体验比 poetry.lock 好。团队 6 人以上时,uv 的 cache 命中率明显更高。
> Python 3.10 才稳定的特性(Pattern Matching、better error messages)也用上了。
> 详见 [ADR-0005](../adr/0005-python-runtime-uv.md)。

---

### Q9: 性能怎么优化?

**答**:

> 启动:WebView 路由级 lazy load + Rust 后台 warm up embedding
> 内存:LRU 边界强制设置,默认 None 等于内存炸弹(踩过坑,见 postmortem)
> LLM:流式响应 + prompt cache + 并行 gather
> 记忆:BM25 + 向量并行检索 + RRF 融合
>
> 详见 [PERFORMANCE.md](../development/PERFORMANCE.md)。

---

## 四、安全题

### Q10: API Key 怎么存?

**答**:

> 默认 OS Keychain(macOS Keychain / Windows Credential Manager / Linux Secret Service)。
> Rust 用 `keyring-rs`,Python 用 `keyring` 包。
> 高级用户可选加密便携文件:Argon2id(m=64MB, t=3, p=4)派生 32B key,
> AES-256-GCM 加密。可备份到 U 盘跨设备迁移。
> 内存中用完即清零,见 [ADR-0002](../adr/0002-byok-keychain-strategy.md)。

---

### Q11: 数据会不会泄露?

**答**:

> **不会**,除非你显式调用云端 LLM。
> 详细隐私政策在 [docs/security/PRIVACY.md](../security/PRIVACY.md),
> 威胁模型在 [docs/security/THREAT-MODEL.md](../security/THREAT-MODEL.md)。
> 核心:默认零出站、零遥测、零统计、零崩溃上报。

---

## 五、产品 / 协作题

### Q12: 这个项目怎么协作?接受 PR 吗?

**答**(诚实):

> **不接受**。这是个人作品集项目,[LICENSE](../../LICENSE) 是 All Rights Reserved。
> 设计目的就是**展示能力**给招聘官看,不是社区项目。
> 但欢迎在 GitHub Issue / Discussion 讨论设计、写 issue 报告 bug。

---

### Q13: 你这个项目最自豪的部分是什么?

**答**(真心):

> 三层任务图模型 + Markdown + Git 长期记忆。
> 这两个设计**让 Agent 第一次具备了"工程纪律"**:
> - 任务有结构、有时间跨度、有依赖,可解释可干预
> - 记忆是 Git 仓库,**审计成本 = 0**
>
> 而不是 LangChain 那种"LLM 自由发挥"的黑盒。

---

### Q14: 这个项目最不满意的地方?

**答**(诚实):

> 1. **KTG 还没实现**,目前只有 STP + MFP,长期目标层 v0.6 才出
> 2. **没有 benchmark** 跟 LangGraph / AutoGen 对比数据
> 3. **多 Agent 协作**还没做,目前是单 Agent + 复杂计划
> 4. **没有移动端**
>
> 个人项目,时间是有限的。

---

### Q15: 如果要团队化,你第一步做什么?

**答**:

> 1. **决定许可证** — 改成 AGPL 还是商业开源,这是根本问题
> 2. **拆分 Owner / Maintainer / Triager 角色** — 现在是一个人干所有
> 3. **建立 RFC 流程** — 大特性必须先 RFC 评审
> 4. **建立 CI 矩阵** — Ubuntu / macOS / Windows 三平台
> 5. **引入 LangSmith / Helicone** 做 LLM 调用观测
>
> 详见 [GOVERNANCE.md](../../GOVERNANCE.md) 与
> [MAINTAINER-ONBOARDING.md](../operations/MAINTAINER-ONBOARDING.md)。

---

## 六、智力题

### Q16: 100k 上下文 prompt 怎么优化?

**答**:

> 1. **截断**:取最近 N 轮对话,前面的转成 episodic 记忆
> 2. **压缩**:用 LLM 把历史对话总结成 500 字摘要
> 3. **向量召回**:用 RAG 而不是塞全量
> 4. **Prompt cache**:Anthropic / DeepSeek 都支持,重复 system prompt 命中
> 5. **分块并行**:长任务拆 MFP 并行,而不是塞一个 prompt

---

### Q17: Agent 死循环怎么办?

**答**:

> 1. **MFP.max_steps** 默认 100
> 2. **用户可在 UI 强制 Cancel**
> 3. **失败 N 次后**自动回退到 STP 重排
> 4. **token 预算**耗尽时熔断
> 5. **日志全留**,事后复盘

---

## 七、行为题

### Q18: 为什么用 TypeScript 而不是直接 Rust 全栈?

**答**:

> React 生态成熟(组件库、Hook、IDE 提示),招前端容易。
> Rust 适合系统级 / 性能敏感 / 安全性关键的部分,但 UI 用 Rust 写太痛苦。
> Tauri 的设计哲学就是:**Web 做 UI,Native 做能力**。
> 我赞同这个分工。

---

## 八、追问准备 / Follow-ups

面试官可能会深挖的细节:

1. **IPC 协议怎么设计 schema?** → 答 `packages/protocol/`,JSON Schema + codegen
2. **MFP 节点失败怎么 retry?** → 答 每个 step 有 retry policy + fallback
3. **Embedding 模型怎么选?** → 答 `bge-small-zh`,本地推理 < 100ms/query
4. **怎么测 LLM 输出?** → 答 Snapshot + Golden Master + Property-based
5. **BYOK 怎么支持多设备?** → 答 加密便携模式 (Argon2id + AES-256-GCM)
6. **Tauri 内存泄漏怎么查?** → 答 py-spy + heaptrack + mprof

---

## 九、Reference / 引用本文

详见 [CITATIONS.md](CITATIONS.md)。

---

© 2024-2026 FnixAgent. All Rights Reserved.