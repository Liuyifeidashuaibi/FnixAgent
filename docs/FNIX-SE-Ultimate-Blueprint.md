# FNIX-SE 终极方案：面向自治软件工程的原生神经符号通用智能运行时

> 工程代号：FNIX-SE（FNIX Software Engine）
> 学术定名：面向自治软件工程的原生神经符号通用智能运行时
> 文档日期：2026-07-15
> 状态：设计定稿

> **权威范围（2026-07-17 校正）**
> - **执行只认本章第一～十一章**（定位、四层架构、选型、五大创新、阶段路线）。
> - 第十二章及以后已移至 [archive/blueprint-ch12-plus.md](./archive/blueprint-ch12-plus.md)，**仅作历史附录，不作完成依据**。
> - **禁止**再往蓝图追加「任务执行日志」；进度只改 [FNIX-SE-IMPLEMENTATION-PLAN.md](./FNIX-SE-IMPLEMENTATION-PLAN.md)。
> - 产品是全 Rust **AgentOS / 自治软件工程运行时**，不是办公套件；Python 仅参考/远期可选 bridge。

---


## 一、核心定位

FNIX-SE 不是「更好的 AI 编辑器」，而是 AGI 在软件开发领域的原生落地底座——代码编辑器只是它的可视化交互入口之一，系统主体是能自主理解、规划、执行、进化的软件生产智能体。

### 终极形态三大判定标准

| 维度 | 过渡产品（Cursor/Trae/Zed） | 终极形态（FNIX-SE） |
|---|---|---|
| 系统主体 | 人类编辑器，AI 是插件辅助 | AI 智能体，编辑器是可视化窗口 |
| 认知方式 | 大模型上下文窗口硬塞代码，无原生结构化认知 | 神经符号融合内核，持久化全局语义记忆，不依赖上下文窗口大小 |
| 能力增长 | 完全绑定外部大模型版本，自身不会进化 | 闭环自进化，从执行经验中自主沉淀知识、优化策略，越用越强 |

---

## 二、调研基础：2026 年前沿全景

| 领域 | 顶级方案 | 关键数据 | FNIX-SE 超越点 |
|---|---|---|---|
| AI 编程 Agent | **OpenAI Codex CLI** (Rust 重写, 67K stars) | bubblewrap 沙箱 + Lark 语法 patch + 两阶段 AI 记忆管线 + JSON-RPC app-server + 多 Agent spawning | Codex 无神经符号认知、无自进化、无事务存储。FNIX-SE 在这三个核心维度形成代差 |
| 多 Agent 编排 | **VMAO** (ICLR 2026) | Plan-Execute-Verify-Replan DAG，completeness 3.1→4.2 | VMAO 是静态 DAG。FNIX-SE 升级为动态拓扑 + 自进化闭环 |
| 神经符号 AI | **AAAI 2026 综述** + **Stanford ComplianceTwin** | TLA+ 形式化保证 + 可解释推理 + 鲁棒性 | 现有方案是通用框架。FNIX-SE 专注程序语义，PDG 提供精确符号基础 |
| 自进化 Agent | **TMLR 2026 综述** + **Microsoft 300 篇 agentic evolution** | BDI-LLM 架构 + 三轴分类(evolutionary substrate/consolidation/selective pressure) | 现有是理论框架。FNIX-SE 是工程落地，从执行轨迹自动沉淀知识 |
| SWE-bench | **Claude Opus 4.6: 80.8%** · **Meta Context Engineering: 89.1%** | 500 题 Verified 基准 | FNIX-SE 目标：Meta Context Engineering + 神经符号校验 → 90%+ |
| 代码搜索 | **tree-sitter + vector embeddings** (2026 实践) | BM25 + 向量混合检索 | FNIX-SE 升级为 PDG 语义图谱 + usearch HNSW 持久化向量 |
| GPU 渲染 | **Zed GPUI** (Rust + wgpu + SDF) | 0.4s 启动, 2ms 输入延迟, 120 FPS | FNIX-SE 复用同一技术栈 (wgpu + cosmic-text) |
| 事务存储 | **sled** (MVCC + ACID) + **PostgreSQL Snapshot Isolation** | 嵌入式 KV，闭包式事务 | FNIX-SE 扩展为多粒度代码事务 (行/函数/文件/分支) |
| 沙箱 | **wasmtime** (capability-based WASM) + **Codex bubblewrap** | WASM 线性内存隔离 + namespace 隔离 | FNIX-SE 三级隔离：进程 + WASM + 权限 DSL |

---

## 三、四层架构总览

```
┌─────────────────────────────────────────────────────┐
│ L4 多端交互兼容层 （可视化入口 + 生态协议网关）       │ 非核心壁垒，可迭代替换
├─────────────────────────────────────────────────────┤
│ L3 通用智能调度层 （动态多Agent + 自进化闭环）        │ 核心壁垒1：AGI决策与进化能力
├─────────────────────────────────────────────────────┤
│ L2 神经符号认知层 （原生程序语义 + 双模态推理）        │ 核心壁垒2：AGI代码理解能力
├─────────────────────────────────────────────────────┤
│ L1 基础运行时层 （事务化存储 + 沙箱执行引擎）          │ 核心壁垒3：AGI执行物理底座
└─────────────────────────────────────────────────────┘
```

---

## 四、逐层设计

### L1 基础运行时层（工程周期：0~6 个月 | 论文对应：系统架构 + 基础模型）

#### 1. 事务化代码存储引擎

- 底层：**sled** 嵌入式数据库（MVCC + ACID 事务）
- 多粒度事务：行级 / 函数级 / 文件级 / 分支级
- 操作：`begin → execute → commit/rollback/preview`，支持嵌套事务
- 快照隔离：每个事务看到一致性时间点快照，切换分支自动隔离所有状态
- 形式化：`Tx = (Snapshot, OpLog, CommitPoint)`，证明可串行化

**超越 Codex CLI 的关键**：Codex 用 SQLite 存会话历史但代码操作无事务。FNIX-SE 的每次代码修改都是事务，可回滚到任意粒度。

#### 2. 三级沙箱执行引擎

- 进程沙箱：Linux bubblewrap / macOS Seatbelt / Windows restricted token（复用 Codex 验证方案）
- WASM 沙箱：**wasmtime** capability-based security（Agent 生成的代码在 WASM 线性内存中执行，无宿主访问权）
- 权限沙箱：DSL 规则引擎（`*.rules` 文件），命令匹配 + 硬编码禁令（shell 解释器、`sudo` 等）

#### 3. GPU 原生渲染底座

- **wgpu** 跨平台 GPU API（Vulkan / Metal / DirectX 12 / WebGPU）
- 自研文本光栅化：**cosmic-text** 文本布局 + **glyphon** 字形图集打包 + wgpu instanced rendering
- 参考 Zed GPUI 的 SDF（Signed Distance Function）矩形渲染
- 目标：百万行代码 120 FPS 滚动，2ms 输入延迟

#### 4. 基础组件

- **tree-sitter**：增量 AST 解析，全语言覆盖，增量重解析 O(edit_size)
- **git2-rs**：libgit2 绑定，零进程开销
- **portable-pty**：跨平台 PTY 终端
- **tokio**：Rust 异步运行时

**对应学术内容**：
- 创新点：提出事务化代码执行模型，从底层解决自治 Agent 执行的安全性与可追溯性问题
- 对应论文章节：第3章 方法论（事务模型形式化定义）、第4章 系统设计（运行时层）
- 实验支撑：原子事务粒度、回滚精度、沙箱性能开销、内存占用对比实验

---

### L2 神经符号认知层（工程周期：6~12 个月 | 论文对应：核心算法 + 认知框架）

#### 1. 程序语义图谱 (PDG)

- tree-sitter 增量解析 → AST → 提取 def-use chain + control dependency → 构建 PDG
- **petgraph** 存储有向图：节点 = 函数/变量/类型/模块，边 = 调用/依赖/导入
- 增量更新：文件修改时只重解析受影响子树，O(edit_size) 复杂度
- 持久化到 sled，跨分支语义快照

#### 2. 神经符号融合推理框架

```
循环:
  1. 语义检索: PDG 查询相关符号 + 依赖链 → 结构化上下文
  2. Meta Context: 上下文组装优化 (参考 SWE-bench 89.1% 方案)
  3. LLM 生成: 结构化上下文注入 → LLM 生成代码
  4. 符号校验: tree-sitter 解析 → PDG 增量更新 → 类型检查 + 依赖一致性
  5. 错误反馈: 结构化错误 → 回到步骤 3
  6. 通过: 提交事务
```

- 参考 AAAI 2026 综述：Logic Tensor Networks 将逻辑规则编码为张量，与神经网络联合优化
- 参考 Stanford ComplianceTwin：符号层强制可验证正确性
- TLA+ 形式化保证：关键路径的推理过程可形式化验证

#### 3. 持久化通用记忆体

- 关系库（sled）：结构化语义（符号表、依赖关系、类型信息）
- 向量库（**usearch** HNSW + SIMD）：语义描述、解法、踩坑记录
- 两阶段 AI 记忆管线（参考 Codex CLI）：
  - Phase 1：启动时扫描历史会话，用小模型提取原始记忆
  - Phase 2：用大模型合并去重，生成 `memory_summary.md`，注入会话上下文
- 跨项目知识复用：解法模式自动检索与适配

#### 4. Meta Context Engineering

- 参考 SWE-EVO 2026：上下文组装作为优化问题，89.1% vs 70.7% 手工基线
- 自动选择注入哪些文件/符号/依赖链，在 token 预算内最大化相关信息密度

**对应学术内容**：
- 创新点：提出神经符号融合的代码认知框架，突破纯大模型上下文驱动的认知局限，实现结构化、持久化的程序理解
- 对应论文章节：第3章 方法论（神经符号认知模型）、第4章 系统设计（语义内核层）
- 实验支撑：代码生成准确率、幻觉率、跨文件重构精度、语义检索召回率对比实验

---

### L3 通用智能调度层（工程周期：12~18 个月 | 论文对应：核心算法 + 自进化理论）

#### 1. 动态拓扑多 Agent DAG 调度引擎

- 参考 VMAO（ICLR 2026）的 Plan-Execute-Verify-Replan，升级为动态拓扑：
  - 任务到达 → LLM 分析需求 → 分解为子任务 → **petgraph** 构建 DAG
  - 拓扑排序 → 并行调度就绪任务
  - 每个任务动态创建 Agent（分配模型/工具/权限），完成后销毁
  - Verify 阶段：独立验证 Agent 检查结果完整性
  - Replan：检测到缺失信息 → 自适应重新规划
- 参考 Codex CLI 多 Agent：`spawn_agent / wait_agent / send_input / close_agent`，最大深度 1，最大 6 并行
- FNIX-SE 升级：无固定深度限制，按任务复杂度自动分配

#### 2. 自进化闭环引擎

- 参考 TMLR 2026 综述三轴分类 + Microsoft 300 篇 agentic evolution：
  - **What to evolve**：任务拆分策略、模型选型阈值、工具调用参数、知识库
  - **When to evolve**：每次任务完成后（即时）、每 N 次任务（批量）、达标后（触发式）
  - **How to evolve**：轨迹复盘 → 归因分析 → 知识沉淀 → 策略优化
- 参考 BDI-LLM 架构（arXiv 2604.27264）：Agent 的 Belief-Desire-Intention 推理循环与 LLM 融合
- 进化验证：同类型任务重复执行 20 次，观测完成率/耗时/错误率趋势

#### 3. 全链路自治执行闭环

```
需求理解 → 方案规划(DAG) → 代码生成(神经符号) → 语义校验(PDG)
→ 沙箱测试(WASM) → 问题修复(自进化) → 结果提交(事务)
```

异常自主处理：错误归因 → 重试/降级/升级，无需人工介入

**对应学术内容**：
- 创新点：提出动态拓扑多智能体调度算法与自进化闭环机制，实现能力自主增长，突破硬编码工作流的静态局限
- 对应论文章节：第3章 方法论（自进化调度算法）、第4章 系统设计（智能调度层）
- 实验支撑：任务完成率、人工干预次数、执行效率、重复任务进化幅度对比实验

---

### L4 多端交互兼容层（工程周期：穿插全程 | 论文对应：实现细节 + 生态扩展）

#### 1. 协议网关

- **LSP 3.17**（tower-lsp）：补全/跳转/悬停/诊断/引用/重命名
- **MCP 1.0**（rmcp）：工具/资源标准化接入
- **DAP**：调试协议
- **FNIX 扩展协议**：事务标识、语义校验请求、Agent 调度指令

#### 2. 多端入口

- GPU 桌面（主入口）：wgpu + cosmic-text
- Web 控制台：axum HTTP API
- CLI 命令行：clap
- HTTP API 服务：axum

#### 3. WASM 插件运行时

- 第三方工具/模型/服务按标准协议接入（wasmtime 隔离）

**对应学术内容**：
- 创新点：提出自治软件工程的标准化接入协议，实现内核与生态解耦
- 对应论文章节：第4章 系统设计（交互兼容层）、第6章 讨论与展望
- 实验支撑：协议兼容度、生态接入成本、多端性能一致性验证

---

## 五、Cargo Workspace 结构

```
fnix-se/
├── Cargo.toml                    # workspace 根
├── crates/
│   ├── fnix-runtime/             # L1: 事务存储 + 沙箱 + PTY + Git
│   │   ├── storage/              #   事务化代码存储 (sled + MVCC)
│   │   ├── sandbox/              #   WASM 沙箱 (wasmtime)
│   │   ├── git/                  #   Git 操作 (git2-rs)
│   │   └── pty/                  #   终端模拟 (portable-pty)
│   ├── fnix-cognition/           # L2: 语义图谱 + 神经符号 + 记忆体
│   │   ├── pdg/                  #   程序依赖图 (tree-sitter + petgraph)
│   │   ├── neuro-symbolic/       #   神经符号融合推理框架
│   │   ├── memory/               #   持久化记忆体 (sled + usearch)
│   │   └── embedder/             #   向量嵌入 (async-openai → embedding API)
│   ├── fnix-scheduler/           # L3: 多Agent调度 + 自进化
│   │   ├── dag/                  #   动态 DAG 任务拓扑 (petgraph)
│   │   ├── agent/                #   Agent 生命周期管理
│   │   ├── evolution/            #   自进化闭环引擎
│   │   └── knowledge/            #   知识沉淀与策略优化
│   ├── fnix-ui/                  # L4: GPU 渲染 + 交互
│   │   ├── gpui/                 #   GPU 渲染管线 (wgpu + cosmic-text)
│   │   ├── editor/               #   代码编辑器组件
│   │   ├── terminal/             #   终端 UI
│   │   └── components/           #   极简 UI 组件库
│   ├── fnix-protocol/            # L4: 协议网关
│   │   ├── lsp/                  #   LSP 3.17 服务端 (tower-lsp)
│   │   ├── mcp/                  #   MCP 1.0 服务端 (rmcp)
│   │   ├── dap/                  #   DAP 调试协议
│   │   └── fnix-ext/             #   FNIX 扩展协议字段
│   └── fnix-core/                # 公共类型 + 错误处理 + 配置
├── apps/
│   ├── desktop/                  # 桌面应用入口 (GPU 窗口)
│   ├── cli/                      # CLI 命令行
│   └── server/                   # HTTP API 服务 (axum)
└── docs/
    └── paper/                    # 论文稿 + 实验数据
```

---

## 六、技术选型一览

| 层 | 模块 | 选型 | 调研依据 |
|---|---|---|---|
| L1 | GPU 渲染 | **wgpu** + **cosmic-text** + **glyphon** | Zed GPUI 验证了 SDF+字形图集方案，0.4s 启动、2ms 输入延迟 |
| L1 | 事务存储 | **sled** (嵌入式 KV，MVCC+ACID) | sled 原生支持闭包式事务，跨树原子提交 |
| L1 | 沙箱 | **wasmtime** (WASM 隔离) + 进程级隔离 | wasmtime 基于 Rust 内存安全 + WASM 线性内存隔离 |
| L1 | 语法解析 | **tree-sitter** (增量 AST) | 全语言覆盖，增量重解析 O(edit_size) |
| L1 | Git | **git2-rs** (libgit2 绑定) | 纯 C 库，零进程开销 |
| L1 | 异步运行时 | **tokio** | Rust 异步事实标准 |
| L1 | 终端 | **portable-pty** | 跨平台 PTY |
| L2 | 语义图谱 | **petgraph** (PDG 数据结构) + tree-sitter 增量构建 | PDG 学术基础成熟 |
| L2 | 向量检索 | **usearch** (SIMD 加速 ANN) | 比 FAISS 轻量，HNSW 算法 |
| L2 | LLM 接口 | **async-openai** (OpenAI 兼容) | 支持 DashScope/Qwen/DeepSeek 等所有兼容接口 |
| L3 | DAG 调度 | **tokio** + **petgraph** | 参考 VMAO + mase-multi-agent |
| L4 | LSP | **tower-lsp** (LSP 3.17) | Rust 生态最成熟的 LSP 实现 |
| L4 | MCP | **rmcp** (Rust MCP SDK) | Anthropic 官方协议 |
| L4 | Web 服务 | **axum** | tokio 原生，类型安全 |
| L4 | CLI | **clap** | Rust CLI 事实标准 |

---

## 七、五大核心创新 → 五篇论文

| # | 创新点 | 学术基础 | 目标期刊 | 实验设计 |
|---|---|---|---|---|
| 1 | 事务化代码执行模型 | PostgreSQL SI + STM + sled MVCC | TSE 第3章 | 原子事务粒度、回滚精度、并发冲突率对比 |
| 2 | 神经符号融合认知框架 | AAAI 2026 + TLA+ + Logic Tensor Networks | TOSEM 第3章 | 幻觉率（vs 纯 LLM）、跨文件重构精度、语义检索召回率 |
| 3 | 动态拓扑自进化调度 | VMAO (ICLR 2026) + TMLR 2026 + BDI-LLM | TSE 第3章 | 任务完成率趋势（20 次重复）、人工干预次数、进化幅度 |
| 4 | Meta Context Engineering | SWE-EVO 2026 (89.1% SWE-bench) | JSS 第5章 | SWE-bench Verified 分数、token 消耗、对比 Cursor/Codex |
| 5 | 自治软件工程运行时标准 | AIOS + Codex app-server + MCP | TSE 第6章 | 协议兼容度、生态接入成本、多端性能一致性 |

---

## 八、论文完整大纲

| 论文章节 | 核心内容 | 对应工程模块 |
|---|---|---|
| 1. Introduction | 研究背景：现有 AI 编程工具的三大本质缺陷；研究问题；核心贡献 | 全系统整体定位 |
| 2. Related Work | AI 辅助编程工具、代码大模型、神经符号程序分析、软件工程智能体四方向研究现状 | 全领域调研 |
| 3. Methodology | ① 事务化代码执行模型 ② 神经符号融合代码认知框架 ③ 动态多智能体自进化调度算法 | L1+L2+L3 核心算法 |
| 4. System Design | 整体四层架构；各模块详细设计；关键实现细节；协议兼容设计 | 全系统工程实现 |
| 5. Evaluation | 评测基准；对比基线；量化指标；整体对比实验；消融实验；进化能力验证；案例分析 | 全系统埋点数据 |
| 6. Discussion | 研究局限；未来工作；对自治软件工程的范式启示 | 终局形态展望 |
| 7. Conclusion | 核心工作与价值总结 | — |

---

## 九、实验评估方案

### 对比基线

Cursor · Codex CLI · Claude Code · Devin · SWE-agent · 纯 GPT-5.3

### 消融实验

| 实验 | 移除模块 | 验证目标 |
|---|---|---|
| 消融 A | L2 神经符号 → 纯 LLM | 验证幻觉率降低 |
| 消融 B | L1 事务沙箱 → 直接文件操作 | 验证安全性与可回滚性 |
| 消融 C | L3 自进化 → 固定角色 Agent | 验证进化效果 |
| 消融 D | Meta Context Engineering → 手工上下文 | 验证 89.1% vs 70.7% |

### 进化能力验证

同类型任务重复执行 20 次，观测完成率、耗时、错误率的变化趋势，验证自进化效果。

### 定性案例分析

选取 2-3 个典型复杂任务，完整展示系统从需求到交付的全流程，剖析语义校验、事务回滚、动态调度的实际作用。

---

## 十、与现有 FnixAgent 的迁移路径

| 现有模块 | FNIX-SE 对应 | 迁移策略 |
|---|---|---|
| AgenticLoop (Think→Act→Observe→Reflect) | L3 调度层 | Rust 重写，Python 版作为算法验证 |
| LLMAdapter (6 Provider) | L2 LLM 接口 | Rust 重写为 async-openai |
| CodeIndexer (AST + BM25) | L2 PDG + 向量检索 | 升级为 tree-sitter PDG + usearch |
| GitAgent | L1 Git | 迁移到 git2-rs |
| FastAPI 13 路由 | L4 协议网关 | 迁移到 axum |
| Electron 桌面 | L4 GPU UI | 完全替换为 wgpu |

---

## 十一、分阶段落地路线

| 阶段 | 时间 | 工程产出 | 论文产出 | 里程碑 |
|---|---|---|---|---|
| **1 内核底座期** | 0-6 月 | Rust+GPU 内核 + 事务存储原型 + 沙箱 + 基础 LSP/MCP 兼容 | 引言 + 相关工作 + 事务模型章节 + 底层性能对比实验数据 | 性能全面碾压 Electron 架构产品，底层数据模型一步到位 |
| **2 认知内核期** | 6-12 月 | 神经符号语义内核 + 沙箱完善 + 代码生成校验闭环 | 神经符号认知框架章节 + 代码精度/幻觉率/重构准确率核心实验数据 | 代码逻辑一致性与准确率大幅超越纯大模型方案，形成架构代差 |
| **3 智能自治期** | 12-18 月 | 动态多 Agent 调度 + 自进化闭环 + 全链路无人值守 | 调度算法 + 自进化机制章节 + 全部对比/消融/进化实验 + 案例分析 | 系统从「辅助工具」升级为「执行主体」，论文主体全部完成 |
| **4 标准定义期** | 18+ 月 | 分布式内核改造 + 开放协议输出 + 第三方生态体系 | 全文润色投稿 + 持续产出生态架构/行业标准方向系列论文 | 成为自治软件工程领域的事实标准，从产品升级为基础设施 |


## 附录说明

第十二章及以后内容见 [archive/blueprint-ch12-plus.md](./archive/blueprint-ch12-plus.md)（非权威）。
