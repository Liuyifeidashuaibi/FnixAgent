# 5个开源 AI Agent 项目聊天区"逐字流式输出"实现机制调研报告

> 调研日期：2026-08-24
> 调研对象：Cline、OpenHands、Aider、Continue、CrewAI

---

## 一、总览对比表

| 维度 | Aider | Cline | OpenHands | Continue | CrewAI |
|------|-------|-------|-----------|----------|--------|
| **产品形态** | Python CLI 终端工具 | VSCode 插件 | Web 平台 (React+FastAPI) | VSCode/JetBrains 插件 | Python 多 Agent 框架 |
| **LLM 输出格式** | 纯文本/Markdown | XML 标签嵌入文本 (自定义解析) | Function Calling (OpenAI 格式) | OpenAI Chat Completion 格式 | LangChain LLM 格式 |
| **聊天区显示内容** | LLM 原始输出直接流式显示 | 解析后分离文本/工具调用展示 | 事件驱动 (Action/Observation) | 加工后的消息 | 无内置聊天区 (框架级) |
| **工具调用展示** | 终端文本 + diff 高亮 | XML 标签解析 + VSCode diffView | ActionEvent + ObservationEvent | slash commands | LangChain Tools 集成 |
| **流式传输协议** | Python SDK `stream=True` (HTTP SSE 底层) | VSCode `postMessage` (进程间通信) | **SSE** (Server-Sent Events) | VSCode `postMessage` (进程间通信) | LangChain streaming callback |
| **chunk 格式** | OpenAI delta chunks | 自定义文本增量 | 事件 JSON (`event_to_dict`) | `ChatMessage` 增量 | LangChain token chunks |
| **前端渲染机制** | `rich.Live` 滑动窗口重绘 | React Webview + postMessage | React + EventSource (SSE) | React Webview + postMessage | 无前端 (需自建) |
| **节流/缓冲机制** | 20fps 节流 + 动态调整 | 即时渲染 + 分块解析 | 异步事件队列 + 线程池分发 | async generator + abort | step_callback 回调 |

---

## 二、逐项目详细分析

### 1. Aider — 终端流式 Markdown 渲染

#### 1.1 核心架构

Aider 是一个纯 Python CLI 工具，不依赖任何前端框架。流式输出的核心是利用 Python `rich` 库的 `Live` 功能实现终端实时重绘。

**关键文件：**
- `aider/mdstream.py`（243行）— `MarkdownStream` 类，核心流式渲染引擎
- `aider/coders/base_coder.py`（2485行）— `Coder` 类，管理 LLM 交互和流式控制
- `aider/sendchat.py`（61行）— 消息验证辅助函数

#### 1.2 五个核心问题

**Q1: LLM 输出的是结构化 JSON 还是纯文本？**

纯文本/Markdown。Aider 不使用 Function Calling 或结构化 JSON，LLM 的原始输出就是 Markdown 格式的文本，包含代码块、解释和思考过程。工具调用（如编辑文件）通过 `SEARCH/REPLACE` 块的文本模式实现，由后端正则匹配解析。

**Q2: 聊天区显示的是 LLM 原始输出还是后端加工后的摘要？**

LLM 原始输出直接流式显示，无中间加工层。用户在终端看到的就是 LLM 逐字生成的完整 Markdown 内容。

**Q3: 工具调用在聊天区如何展示？**

工具调用以 Markdown 文本形式展示在终端：
- 文件编辑通过 `SEARCH/REPLACE` 块格式，终端以 diff 高亮显示
- 命令执行结果显示为代码块输出
- 无独立"工具调用卡片"UI（因为终端环境限制）

**Q4: 流式输出是通过 SSE 还是 WebSocket？**

都不是。Aider 使用 LLM SDK 原生的 `stream=True` 参数（底层是 HTTP SSE，但对 Aider 而言是 Python async generator）。代码调用 LLM SDK 的 streaming API，直接获取 chunk 迭代器。

```python
# 简化逻辑（base_coder.py 中）
for chunk in llm.stream(messages):
    # 每个 chunk 是 LLM 返回的文本增量
    mdstream.update(chunk.content)
```

**Q5: 前端收到 chunk 后如何渲染？**

使用 `rich.Live` 的滑动窗口机制，核心实现在 `mdstream.py`：

```python
class MarkdownStream:
    live_window = 6  # 滑动窗口：最后6行在Live窗口中重绘

    def update(self, token):
        self.md += token
        # 1. 将累积文本按行分割
        lines = self.md.split('\n')
        # 2. 已稳定的旧行输出到 console（scrollback）
        # 3. 不稳定的新行在 Live 窗口中重绘
        # 4. 节流控制：20fps
        min_delay = max(render_time * 10, 1.0/20)
        min_delay = min(min_delay, 2)  # 上限2秒
```

**关键渲染机制：**
- **滑动窗口**：维护最后 `live_window=6` 行为"活跃区"，在终端 Live 区域重绘
- **稳定行下沉**：超过窗口的旧行已经确定，输出到终端 scrollback（不再重绘）
- **节流**：`min_delay = 1.0/20`（20fps），并根据上一次渲染耗时动态调整
- **Markdown 实时解析**：`rich.Live` 在每次更新时重新解析 Markdown 并渲染

---

### 2. Cline — VSCode 插件的 XML 标签流式解析

#### 2.1 核心架构

Cline 是 VSCode 插件，采用 **主进程 ↔ Webview** 双进程架构。主进程负责 LLM 调用和工具执行，Webview（React）负责 UI 渲染，通过 VSCode `postMessage` 通信。

**关键文件（来自源码分析）：**
- `src/core/task/index.ts` — `Task` 类，核心任务执行引擎
- `src/core/assistant-message/parse-assistant-message.ts` — `parseAssistantMessageV2`，LLM 输出解析器
- `src/core/controller/grpc-handler.ts` — 主进程 gRPC 请求处理器
- `src/core/controller/index.ts` — `initTask` 方法，任务初始化
- `webview-ui/src/components/chat/ChatView.tsx` — 前端聊天视图
- `webview-ui/src/services/grpc-client-base.ts` — Webview gRPC 客户端

#### 2.2 五个核心问题

**Q1: LLM 输出的是结构化 JSON 还是纯文本？**

**自定义 XML 标签格式嵌入纯文本**。Cline 不使用 OpenAI Function Calling，而是在 System Prompt 中定义工具调用格式，要求 LLM 输出包含 XML 标签的文本：

```
<thinking>
我需要在文件中添加快速排序算法...
</thinking>

<replace_in_file>
<path>src/utils/index.ts</path>
<diff>
------- SEARCH
[原始代码]
=======
[新代码]
+++++++ REPLACE
</diff>
</replace_in_file>
```

前端处理方式：`parseAssistantMessageV2` 方法通过正则解析 XML 标签，分离出文本内容和工具调用。

**Q2: 聊天区显示的是 LLM 原始输出还是后端加工后的摘要？**

**解析后展示**。Cline 将 LLM 输出解析为两种类型：
- **文本消息**：`<thinking>` 标签内的内容和标签外的文本，展示为聊天消息
- **工具调用**：XML 标签内的参数（如文件路径、diff 内容），展示为可交互的工具卡片

通过 `say` 方法在聊天面板新增消息：
```typescript
await this.say("text", task, images, files)  // 用户消息
await this.say("tool", toolResult)            // 工具结果
```

**Q3: 工具调用在聊天区如何展示？**

工具调用以**结构化卡片**形式展示在 Webview 聊天面板：
- **文件编辑** (`replace_in_file`)：借助 VSCode 的 diffView 能力，以 diff 视图展示代码变更
- **命令执行** (`execute_command`)：显示命令文本和执行结果
- **文件读取** (`read_file`)：显示文件内容摘要
- **浏览器操作**：显示操作步骤和结果

每个工具调用在聊天区有独立的 UI 组件，包含工具名称、参数、执行状态和结果。

**Q4: 流式输出是通过 SSE 还是 WebSocket？**

**VSCode `postMessage`**（进程间通信，非 SSE/WebSocket）。

```
Webview (React)  ←→  VSCode 主进程  ←→  LLM API
   postMessage         HTTP SSE (SDK层)
```

Webview 通过 `vscode.postMessage` 发送请求：
```typescript
vscode.postMessage({
  type: "grpc_request",
  grpc_request: {
    service: service.fullName,
    method: method.name,
    message: encodedRequest,
    request_id: requestId,
    is_streaming: false,
  },
})
```

主进程处理过程中，实时通过 `postMessage` 将 LLM 的流式输出发送回 Webview。

**Q5: 前端收到 chunk 后如何渲染？**

React Webview 通过 `window.addEventListener("message", handleResponse)` 接收消息，直接更新 React 状态并渲染：

1. 主进程的 `attemptApiRequest` 方法创建流：`let stream = this.api.createMessage(systemPrompt, history)`
2. `parseAssistantMessageV2` 逐步解析流式输出中的 XML 标签
3. 解析出的文本和工具调用通过 `presentAssistantMessage` 展示
4. Webview 的 React 组件根据消息类型（text/tool/tool_result）渲染不同 UI

**渲染特点：**
- 无独立缓冲层，chunk 到达即渲染
- XML 标签解析是流式的，可以在标签未完整时开始处理
- diffView 利用 VSCode 原生能力，不需要自己实现 diff 渲染

---

### 3. OpenHands — 事件驱动的 SSE 流式架构

#### 3.1 核心架构

OpenHands 采用 **事件驱动架构（EDA）**，是 5 个项目中最复杂的流式输出系统。分为两层部署：App Server（FastAPI）→ Sandbox 容器内的 Agent Server。

**关键文件/模块：**
- `openhands/sdk/event/` — Event 模型（Action/Observation/Message）
- `openhands/sdk/agent/agent.py` — Agent ReAct 循环
- `openhands/sdk/agent/response_dispatch.py` — LLM 响应分类分发
- `openhands/sdk/llm/llm.py` — LLM 抽象层（基于 LiteLLM）
- `openhands/agent_server/conversation_service.py` — 沙箱内 Agent 服务
- `openhands/app_server/v1_router.py` — API 路由
- 前端 React + TypeScript + Vite

#### 3.2 五个核心问题

**Q1: LLM 输出的是结构化 JSON 还是纯文本？**

**Function Calling 格式（OpenAI 兼容）**。OpenHands 通过 LiteLLM 调用 LLM，使用标准的 Function Calling 模式。LLM 返回的 `tool_calls` 被分类处理：

```
LLM Response → classify_response() → 4种分类：
1. TOOL_CALLS → 创建 ActionEvent → 安全检查 → 并行执行
2. CONTENT → 视为最终回覆 → 设置 FINISHED
3. REASONING_ONLY → 只有 thinking blocks → 发 corrective nudge
4. EMPTY → 发 corrective nudge
```

聊天区文本处理：LLM 返回的 `content` 部分直接作为 `MessageEvent` 发送到前端，`tool_calls` 部分转为 `ActionEvent`。

**Q2: 聊天区显示的是 LLM 原始输出还是后端加工后的摘要？**

**事件驱动展示**。聊天区显示的是经过事件系统封装的内容：
- `MessageEvent` — 用户或 Agent 的文本消息（LLM 原始文本内容）
- `ActionEvent` — Agent 决定执行某个工具（包含工具名和参数）
- `ObservationEvent` — 工具执行后的结果（包含输出内容）
- `AgentErrorEvent` — 错误信息

LLM 的原始文本内容在 `MessageEvent` 中保留，但工具调用被拆分为独立的 Action/Observation 事件。

**Q3: 工具调用在聊天区如何展示？**

通过 **Action → Observation** 事件对展示：
- **ActionEvent**：显示"Agent 决定执行 [工具名]"，展示工具参数（如要运行的命令、要编辑的文件）
- **ObservationEvent**：显示工具执行结果（如命令输出、文件变更内容）
- **ReAct 循环**：每次 Action → Observation 构成一个"思考-行动-观察"循环，前端按时间线展示

支持的工具类型包括：TerminalTool（Shell 命令）、FileEditorTool（文件编辑）、BrowserUseTool（浏览器自动化）、GlobTool/GrepTool（文件搜索）、DelegateTool（子 Agent 委派）等。

**Q4: 流式输出是通过 SSE 还是 WebSocket？**

**SSE (Server-Sent Events)**。这是 5 个项目中唯一使用标准 SSE 协议的：

```
前端 React  ←  SSE  ←  App Server (FastAPI)  ←  HTTP  ←  Agent Server (容器内)
                                          ←  LiteLLM  ←  LLM Provider
```

关键 SSE 端点：
```
GET /api/v1/conversation/{id}/events/     — 事件读取/搜索
GET /agent-server/api/conversations/{id}/events/stream  — SSE 串流事件
```

Agent Server（沙箱内）通过 SSE 向 App Server 推送事件，App Server 再通过 SSE 向前端推送。事件格式为 JSON（`event_to_dict` 序列化）。

`buildConfiguredOpenHandsAgentSettings` 中设置 `llm.stream = true`，注释说明"agent-server 只对 stream=True 的 LLM 发出 StreamingDeltaEvents"。

**Q5: 前端收到 chunk 后如何渲染？**

React 前端通过 **EventSource API**（或 fetch + ReadableStream）接收 SSE 事件流：

1. **EventStream 分发机制**（后端）：使用异步队列 + 独立线程处理事件队列，通过线程池为每个订阅者的回调函数创建独立执行环境
2. **事件分发**：`_process_queue` 方法按订阅者 ID 排序，将事件分发给所有订阅者（Runtime、AgentController、Memory、Server 等）
3. **前端渲染**：React 组件接收事件 JSON，根据事件类型（`MessageEvent`/`ActionEvent`/`ObservationEvent`）渲染不同 UI 组件

**渲染特点：**
- 事件系统天然支持多订阅者（Runtime、Controller、Memory、Server 同时接收）
- 异步队列 + 线程池保证事件按序分发且不阻塞
- 事件持久化到文件系统（EventLog），支持断点恢复
- `StreamingDeltaEvent` 提供逐 token 的流式增量

---

### 4. Continue — VSCode 插件的 Async Generator 流式

#### 4.1 核心架构

Continue 是 VSCode/JetBrains 插件，已标记为"不再活跃维护"（read-only）。采用与 Cline 类似的主进程 ↔ Webview 架构，但流式输出实现更简洁。

**关键文件：**
- `core/llm/streamChat.ts`（147行）— `llmStreamChat` async generator 函数
- `core/llm/index.ts`（1504行）— `BaseLLM` 抽象类，`streamChat` 方法
- `core/llm/llms/` — 具体 provider 实现
- `gui/` — 前端渲染（VSCode Webview）

#### 4.2 五个核心问题

**Q1: LLM 输出的是结构化 JSON 还是纯文本？**

**OpenAI Chat Completion 格式**。Continue 使用 OpenAI adapter 模式，LLM 返回标准的 Chat Completion chunks，通过 `fromChatCompletionChunk` 转换为内部 `ChatMessage` 类型。

```typescript
// index.ts 中的 chunk 转换
static fromChatCompletionChunk(chunk: ...): ChatMessage {
  // 将 OpenAI delta chunk 转为内部 ChatMessage
}
```

注意：o1 模型禁用 streaming（不支持流式输出）。

**Q2: 聊天区显示的是 LLM 原始输出还是后端加工后的摘要？**

LLM 原始输出（文本内容部分）直接流式显示。Continue 不对文本内容做二次加工，但支持 **legacy slash commands** 对输出进行后处理。

**Q3: 工具调用在聊天区如何展示？**

Continue 的工具调用通过 **slash commands** 实现（legacy 模式），在聊天区以命令文本和结果展示。工具调用不是 LLM 的 Function Calling，而是用户主动触发的命令。

**Q4: 流式输出是通过 SSE 还是 WebSocket？**

**VSCode `postMessage`**（进程间通信）。与 Cline 类似，Continue 使用 VSCode 的 `postMessage` 机制在主进程和 Webview 之间传输数据。LLM SDK 层面使用 `stream: true` 参数。

**Q5: 前端收到 chunk 后如何渲染？**

通过 **async generator** 模式流式渲染：

```typescript
// streamChat.ts
export async function* llmStreamChat(
  llm: BaseLLM,
  messages: ChatMessage[],
  abortController?: AbortController,
): AsyncGenerator<ChatMessage> {
  const stream = await llm.streamChat(messages, abortController)
  for await (const chunk of stream) {
    yield chunk  // 每个 chunk 是 ChatMessage 类型
  }
}
```

**渲染特点：**
- `BaseLLM.streamChat()` 返回 async iterable，前端通过 `for await...of` 消费
- 支持 `AbortController` 取消流式输出
- 前端 React Webview 接收 chunk 后更新消息状态，增量渲染
- 无复杂缓冲机制，chunk 到达即追加

---

### 5. CrewAI — 多 Agent 框架的 Callback 流式

#### 5.1 核心架构

CrewAI 与其他 4 个项目有本质区别：它是一个 **Python 多 Agent 编排框架**，不是 IDE 插件或 Web 应用，**没有内置聊天区 UI**。流式输出通过回调机制实现，需要开发者自行接入前端。

**关键概念：**
- `Agent` — 自主单元，有角色/目标/工具
- `Task` — 具体任务指令
- `Crew` — Agent 团队，编排执行
- `Process` — 执行流程（顺序/层级）
- `step_callback` — 每步回调函数（流式输出的关键）

#### 5.2 五个核心问题

**Q1: LLM 输出的是结构化 JSON 还是纯文本？**

**LangChain LLM 格式**。CrewAI 基于 LangChain 的 LLM 接口，LLM 输出格式取决于配置的 `llm` 参数（默认 OpenAI GPT-4）。支持 `function_calling_llm` 单独控制工具调用的模型。

**Q2: 聊天区显示的是 LLM 原始输出还是后端加工后的摘要？**

**无内置聊天区**。CrewAI 的输出通过以下方式获取：
- `crew.kickoff()` 返回 `CrewOutput` 对象（包含 `raw` 文本、`pydantic` 结构化数据）
- `agent.kickoff()` 返回 `LiteAgentOutput` 对象
- `step_callback` 回调函数在每个 Agent 步骤后触发，可用于流式输出

开发者需要自行构建前端来展示流式输出。

**Q3: 工具调用在聊天区如何展示？**

CrewAI 支持 LangChain Tools 和 CrewAI Toolkit 工具。工具调用在框架内部处理，结果通过 `step_callback` 回调暴露。展示方式完全由开发者决定。

**Q4: 流式输出是通过 SSE 还是 WebSocket？**

**LangChain streaming callback**。CrewAI 不直接使用 SSE 或 WebSocket，而是通过 LangChain 的 streaming 机制：

```python
# Agent 创建时可配置 step_callback
agent = Agent(
    role="Research Analyst",
    goal="Find and summarize information",
    backstory="Experienced researcher",
    step_callback=my_callback,  # 每步回调，可用于流式输出
    verbose=True,               # 详细日志输出
)
```

`step_callback` 在每个 Agent 步骤（包括 LLM 调用、工具执行）后触发，开发者可以在回调中实现自定义的流式输出逻辑（如推送到 WebSocket、写入文件、打印到终端）。

**Q5: 前端收到 chunk 后如何渲染？**

**无内置前端渲染**。CrewAI 是纯后端框架，需要开发者自行实现：
1. 通过 `step_callback` 捕获每步输出
2. 通过自定义 WebSocket/SSE 服务器推送到前端
3. 前端自行实现渲染逻辑

CrewAI Enterprise 版本（CrewAI AMP）提供 Visual Agent Builder 和可视化界面，但属于商业产品，不在开源范畴。

---

## 三、关键设计模式对比

### 3.1 流式传输协议对比

| 项目 | 传输层协议 | 前端接收方式 | 适用场景 |
|------|-----------|------------|---------|
| **Aider** | HTTP SSE (SDK 内部) → Python iterator | `rich.Live` 直接消费 | 终端 CLI |
| **Cline** | VSCode `postMessage` (IPC) | React `addEventListener` | VSCode 插件 |
| **OpenHands** | **SSE** (HTTP 长连接) | `EventSource` / `fetch+ReadableStream` | Web 应用 |
| **Continue** | VSCode `postMessage` (IPC) | React async generator 消费 | IDE 插件 |
| **CrewAI** | LangChain callback (无传输层) | 开发者自定义 | 后端框架 |

### 3.2 LLM 输出解析策略对比

| 项目 | 解析方式 | 工具调用格式 | 解析时机 |
|------|---------|------------|---------|
| **Aider** | 无解析（纯文本直出） | `SEARCH/REPLACE` 文本块 | 后处理（非流式） |
| **Cline** | XML 标签正则解析 | `<tool_name>...</tool_name>` | **流式解析**（标签未完整时开始） |
| **OpenHands** | Function Calling 原生 | OpenAI `tool_calls` | LLM SDK 原生解析 |
| **Continue** | OpenAI Chat Completion | slash commands (非 LLM) | SDK 原生解析 |
| **CrewAI** | LangChain 原生 | LangChain Tools | 框架内部 |

### 3.3 前端渲染机制对比

| 项目 | 渲染技术 | 缓冲/节流机制 | 特殊处理 |
|------|---------|-------------|---------|
| **Aider** | `rich.Live` 终端重绘 | 20fps 节流 + 动态调整 | 滑动窗口（6行）+ 稳定行下沉 |
| **Cline** | React + VSCode Webview | 即时渲染（无节流） | diffView 原生集成 |
| **OpenHands** | React + EventSource (SSE) | 异步事件队列 + 线程池 | 事件持久化 + 断点恢复 |
| **Continue** | React + VSCode Webview | async generator 自然节流 | AbortController 取消 |
| **CrewAI** | 无（需自建） | N/A | N/A |

---

## 四、架构洞察与设计启示

### 4.1 两种主流流式输出范式

**范式一：IDE 插件模式（Cline、Continue）**
```
LLM API (SSE) → 主进程 (解析+工具执行) → postMessage → Webview (React渲染)
```
- 优点：主进程可以做复杂处理（权限检查、工具执行、diffView集成）
- 缺点：postMessage 是全量序列化，大消息有性能瓶颈

**范式二：Web SSE 模式（OpenHands）**
```
LLM API (SSE) → Agent Server (SSE) → App Server (SSE) → 前端 (EventSource)
```
- 优点：标准协议、天然支持多客户端、断线重连
- 缺点：事件系统复杂、调试困难

### 4.2 Claude Code 的双路径设计（参考）

从 Claude Code 源码分析中可以看到一个更成熟的流式输出设计：

```
API 增量 → 两条并行路径：
  路径A: 累积到 contentBlocks → content_block_stop 时产出完整 AssistantMessage → 供 Agent 决策
  路径B: 包装为 StreamEvent → 实时转发给 REPL → 逐字显示终端内容
```

这种"一份数据两条用途"的设计值得借鉴：
- **StreamEvent**（半截数据）：服务于实时显示，用户看到逐字输出
- **AssistantMessage**（完整数据）：服务于 Agent 逻辑，只有内容块完整后才用于工具调用

当流式连接中断时，Claude Code 会：
1. 发出 Tombstone（墓碑标记）撤销已显示的旧消息
2. 改用非流式请求重新获取完整结果
3. 如果同模型持续 529 过载，切换备用模型

### 4.3 对 FnixAgent 的设计建议

基于本次调研，对 FnixAgent（Next.js 16 + React 19 Web 应用）的建议：

1. **采用 SSE 模式**（参考 OpenHands）：FnixAgent 是 Web 应用，SSE 是最自然的流式传输协议
2. **双路径设计**（参考 Claude Code）：将 LLM 增量同时用于实时显示和完整消息累积
3. **事件驱动架构**（参考 OpenHands EventStream）：将用户消息、AI 回复、工具调用统一为事件
4. **工具调用展示**（参考 Cline）：为工具调用设计结构化卡片 UI
5. **节流机制**（参考 Aider）：前端渲染节流控制，避免每个 token 触发重渲染
6. **教学场景适配**：FnixAgent 是教育产品，流式输出不仅要快，还要在关键步骤暂停（元认知提示、分块呈现）

---

## 五、关键文件索引

### Aider
| 文件 | 行数 | 职责 |
|------|------|------|
| `aider/mdstream.py` | 243 | `MarkdownStream` 类，终端流式 Markdown 渲染（滑动窗口+节流） |
| `aider/coders/base_coder.py` | 2485 | `Coder` 类，LLM 交互和流式控制 |
| `aider/sendchat.py` | 61 | 消息验证辅助函数 |

### Cline
| 文件 | 职责 |
|------|------|
| `src/core/task/index.ts` | `Task` 类，核心任务执行引擎 |
| `src/core/assistant-message/parse-assistant-message.ts` | `parseAssistantMessageV2`，XML 标签流式解析 |
| `src/core/controller/grpc-handler.ts` | 主进程 gRPC 请求处理 |
| `src/core/controller/index.ts` | `initTask`，任务初始化 |
| `webview-ui/src/components/chat/ChatView.tsx` | 前端聊天视图 |
| `webview-ui/src/services/grpc-client-base.ts` | Webview gRPC 客户端 |

### OpenHands
| 文件 | 职责 |
|------|------|
| `openhands/sdk/event/` | Event 模型（Action/Observation/Message） |
| `openhands/sdk/agent/agent.py` | Agent ReAct 循环 |
| `openhands/sdk/agent/response_dispatch.py` | LLM 响应分类分发（4种类型） |
| `openhands/sdk/llm/llm.py` | LLM 抽象层（LiteLLM 封装） |
| `openhands/agent_server/conversation_service.py` | 沙箱内 Agent 服务（含 SSE 端点） |
| `openhands/app_server/v1_router.py` | API 路由定义 |

### Continue
| 文件 | 行数 | 职责 |
|------|------|------|
| `core/llm/streamChat.ts` | 147 | `llmStreamChat` async generator |
| `core/llm/index.ts` | 1504 | `BaseLLM` 抽象类，`streamChat` 方法 |

### CrewAI
| 概念 | 职责 |
|------|------|
| `Agent.step_callback` | 每步回调函数，流式输出的关键接口 |
| `Crew.kickoff()` | 启动 Crew 执行，返回 `CrewOutput` |
| `Agent.kickoff()` | 直接 Agent 交互，返回 `LiteAgentOutput` |
| `Agent.llm` | LangChain LLM 实例，支持 streaming |

---

## 六、调研完成度

| 项目 | 调研深度 | 关键源码获取 | 完成状态 |
|------|---------|------------|---------|
| Aider | ★★★★★ | mdstream.py(完整), base_coder.py(部分), sendchat.py(完整) | ✅ 完成 |
| Cline | ★★★★☆ | 源码分析文章(完整), 架构流程(完整), 关键文件路径确认 | ✅ 完成 |
| OpenHands | ★★★★☆ | 事件系统(完整), 架构图(完整), SSE端点确认, 响应分发逻辑 | ✅ 完成 |
| Continue | ★★★★☆ | streamChat.ts(完整), index.ts(部分), 架构确认 | ✅ 完成 |
| CrewAI | ★★★☆☆ | 官方文档(完整), 架构确认, step_callback机制确认 | ✅ 完成 |
