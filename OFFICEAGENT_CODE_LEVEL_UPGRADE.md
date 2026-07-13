# OfficeAgent 代码级升级方案(顶级 Agent 改造蓝图)

> 本文档是 [OFFICEAGENT_TOP_TIER_UPGRADE_PLAN.md](file:///e:/Officeagent/OFFICEAGENT/OFFICEAGENT_TOP_TIER_UPGRADE_PLAN.md) 的代码级补充,基于对 LangGraph / OpenAI Agents SDK / PydanticAI / MetaGPT / AgentScope 五大顶级框架源码的深度研究,结合 OfficeAgent 现状代码调研(精确到行号),给出具体到类/接口/文件路径的改造方案。
>
> **核心哲学(借鉴 AgentScope 新版)**:单 Agent 极致健壮 + 多 Agent 平滑扩展 —— 多 Agent 所需的全部原语,都应在单 Agent 阶段就内建,避免 P3 返工。

---

## 〇、改造优先级与依赖关系

### 总体依赖图

```
┌─────────────── 跨阶段基础设施(AgentScope 核心借鉴)─────────────────┐
│                                                                    │
│  A-1 Msg+ContentBlock ──┬──→ A-2 Agent 基类 ──→ A-3 Middleware    │
│  (P0-1 Reducer)         │     (P0-2/P1-4)       (P0-2/P1-1)      │
│                         ├──→ A-4 ToolCallState                      │
│                         │     (P0-4 重试)                           │
│                         └──→ A-5 Context 拆分 (P1-4 Runner)        │
└────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────── P0 状态/安全/类型三补强 ────────────────────────────┐
│  P0-1 Reducer ──→ P0-2 Guardrail ──→ P0-3 LLM校验 ──→ P0-4 重试  │
└────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────── P1 可观测/可恢复/入口收敛 ──────────────────────────┐
│  P1-1 Tracing ──┬──→ P1-4 Runner ──→ chat.py 改造                │
│  P1-2 Checkpoint┤                                                   │
│  P1-3 Edge Route┤                                                   │
│  P1-5 Usage ────┘                                                   │
└────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────── P2 Office 顶级 + 办公生态 ──────────────────────────┐
│  P2-1~P2-11(11个任务,多数可并行)                                 │
└────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────── P3 多 Agent 协作 ───────────────────────────────────┐
│  P3-1 Handoff ──→ P3-2 Role ──→ P3-3 SOP ──→ P3-4 MessageBus     │
└────────────────────────────────────────────────────────────────────┘
```

### 执行顺序(阻塞关系驱动)

| 批次 | 任务 | 阻塞原因 |
|------|------|----------|
| **第1批(P0)** | ① A-1 Msg+ContentBlock → ② A-4 ToolCallState(并行)→ ③ A-2 Agent基类 → ④ A-3 Middleware → P0-1~P0-4 | A-1 是绝对地基,延迟会导致 P0-P2 返工 |
| **第2批(P1)** | ⑤ A-5 Context拆分(需先重命名 graph/state.py:AgentState→GraphState)→ P1-1~P1-5 | A-5 解锁 Runner 的状态持久化 |
| **第3批(P2)** | P2-1~P2-11(多数可并行) | 依赖 P0/P1 基础设施 |
| **第4批(P3)** | P3-1~P3-4 | 依赖 A-1/A-2 全部就位 |

---

## 一、AgentScope 核心借鉴(跨阶段基础设施)

> AgentScope 新版已移除 Actor 模型,改为"单 Agent 极致健壮 + 多 Agent 平滑扩展"设计。通过 ContentBlock 块化消息、中间件洋葱、ToolCallState 状态机、MessageBus 抽象,让单 Agent 阶段就内建多 Agent 所需全部原语。

### A-1: Msg + ContentBlock 块化消息

**影响**:P0-1 Reducer / P3-1 Handoff / P3-4 MessageBus
**落点**:新增 `core/types_msg.py`

```python
"""块化消息(借鉴 AgentScope Msg + ContentBlock)。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Union
import uuid

# ---------------------------------------------------------------------------
# ContentBlock 基类 + 6 种 Block
# ---------------------------------------------------------------------------

@dataclass
class ContentBlock:
    """内容块基类。"""
    block_type: str = "text"
    block_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

@dataclass
class TextBlock(ContentBlock):
    """文本块。"""
    block_type: str = "text"
    text: str = ""

@dataclass
class ThinkingBlock(ContentBlock):
    """思考块(ReAct thought / GLM-4.5 思考模式)。"""
    block_type: str = "thinking"
    thought: str = ""

@dataclass
class HintBlock(ContentBlock):
    """提示块(系统/人工干预注入)。"""
    block_type: str = "hint"
    hint: str = ""
    source: str = "system"  # system / human / tool

@dataclass
class ToolCallBlock(ContentBlock):
    """工具调用块。"""
    block_type: str = "tool_call"
    tool_name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

@dataclass
class ToolResultBlock(ContentBlock):
    """工具结果块。"""
    block_type: str = "tool_result"
    call_id: str = ""
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0

@dataclass
class DataBlock(ContentBlock):
    """通用数据块(图表/表格/文件引用等)。"""
    block_type: str = "data"
    data_type: str = ""  # chart / table / file / image
    payload: dict[str, Any] = field(default_factory=dict)

Block = Union[TextBlock, ThinkingBlock, HintBlock, ToolCallBlock, ToolResultBlock, DataBlock]

# ---------------------------------------------------------------------------
# Msg 类(替代现有 Message)
# ---------------------------------------------------------------------------

@dataclass
class Msg:
    """块化消息(借鉴 AgentScope Msg)。

    与现有 Message 的区别:
      - content: list[Block] 而非 str(支持多模态)
      - 携带路由字段(send_to/cause_by/sent_from),单 Agent 留空,P3 填写
      - id 字段供 Reducer 去重合并
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    role: str = "user"  # system / user / assistant / tool
    content: list[Block] = field(default_factory=list)
    name: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: Optional[int] = None
    # 路由字段(单 Agent 留空,P3 多 Agent 填写)
    send_to: Optional[str] = None       # 目标 Agent 名
    cause_by: Optional[str] = None      # 触发此消息的 Action 名
    sent_from: Optional[str] = None     # 发送方 Agent 名

    @property
    def text_content(self) -> str:
        """提取全部 TextBlock 文本拼接。"""
        return "".join(b.text for b in self.content if isinstance(b, TextBlock))

    def to_legacy_dict(self) -> dict:
        """兼容现有 to_llm_dict() 格式。"""
        return {"role": self.role, "content": self.text_content, "name": self.name}

# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def user_msg(text: str, **kwargs) -> Msg:
    return Msg(role="user", content=[TextBlock(text=text)], **kwargs)

def assistant_msg(text: str = "", blocks: list[Block] = None, **kwargs) -> Msg:
    content = blocks or ([TextBlock(text=text)] if text else [])
    return Msg(role="assistant", content=content, **kwargs)

def system_msg(text: str, **kwargs) -> Msg:
    return Msg(role="system", content=[TextBlock(text=text)], **kwargs)

def tool_msg(call_id: str, output: Any, error: Optional[str] = None, **kwargs) -> Msg:
    return Msg(role="tool", content=[ToolResultBlock(call_id=call_id, output=output, error=error)], **kwargs)

# ---------------------------------------------------------------------------
# Reducer 语义(供 P0-1 使用)
# ---------------------------------------------------------------------------

def add_msgs(left: list[Msg] | None, right: list[Msg]) -> list[Msg]:
    """Msg 列表 Reducer:按 id 去重追加。"""
    merged = list(left or [])
    seen_ids = {m.id for m in merged}
    for msg in right:
        if msg.id not in seen_ids:
            merged.append(msg)
            seen_ids.add(msg.id)
    return merged
```

**兼容方案**:现有 `Message` 保留,新增 `Msg`;`to_llm_dict()` 调用 `to_legacy_dict()`;渐进迁移节点返回值。

### A-2: Agent 类基类

**影响**:P0-2 / P1-4 Runner
**落点**:新增 `core/agent.py`

```python
"""Agent 基类(借鉴 AgentScope Agent + OpenAI SDK Agent)。

设计:Agent 是比 ReasoningEngine 更高层的抽象,
单 Agent 阶段由 Runner 包装单实例,多 Agent 阶段由 Environment 驱动多实例。
Agent 子类不感知自身是"单 Agent"还是"多 Agent 成员"。
"""
from __future__ import annotations
import abc
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from officeagent.core.types_msg import Msg

@dataclass
class AgentContext:
    """Agent 运行上下文(每次 reply 创建)。"""
    goal: str = ""
    user_id: str = ""
    session_id: str = ""
    trace_id: str = ""
    project_id: str = ""
    history: list[Msg] = field(default_factory=list)
    max_iterations: int = 10
    extra: dict[str, Any] = field(default_factory=dict)

class Agent(abc.ABC):
    """Agent 基类:4 步 ReAct + 双入口。

    生命周期:prepare → [think → act] × N → reflect
    单 Agent:Runner 直接调 reply()
    多 Agent:Environment 调 reply(),根据 handoff 转交
    """

    def __init__(self, name: str, **config) -> None:
        self._name = name
        self._config = config

    @property
    def name(self) -> str:
        return self._name

    @abc.abstractmethod
    async def prepare(self, ctx: AgentContext) -> AgentContext:
        """准备阶段:加载记忆/工具/技能。"""
        ...

    @abc.abstractmethod
    async def think(self, ctx: AgentContext) -> Optional[Msg]:
        """思考阶段:LLM 推理,返回思考消息(含 ToolCallBlock 或 TextBlock)。"""
        ...

    @abc.abstractmethod
    async def act(self, ctx: AgentContext, thought: Msg) -> Optional[Msg]:
        """行动阶段:执行工具调用,返回工具结果消息。"""
        ...

    @abc.abstractmethod
    async def reflect(self, ctx: AgentContext, trace: list[Msg]) -> Msg:
        """反思阶段:汇总结果,返回最终回复。"""
        ...

    # -- 双入口 -----------------------------------------------------------

    async def reply(self, ctx: AgentContext) -> Msg:
        """同步入口:4 步 ReAct 循环。"""
        ctx = await self.prepare(ctx)
        trace: list[Msg] = []
        for i in range(ctx.max_iterations):
            thought = await self.think(ctx)
            if thought is None:
                break
            trace.append(thought)
            if not any(b for b in thought.content if b.block_type == "tool_call"):
                return thought  # 直接给出最终答案
            result = await self.act(ctx, thought)
            if result:
                trace.append(result)
                ctx.history.append(result)
        return await self.reflect(ctx, trace)

    async def reply_stream(self, ctx: AgentContext) -> AsyncGenerator[Msg, None]:
        """流式入口:逐步 yield。"""
        ctx = await self.prepare(ctx)
        trace: list[Msg] = []
        for i in range(ctx.max_iterations):
            thought = await self.think(ctx)
            if thought is None:
                break
            yield thought
            trace.append(thought)
            result = await self.act(ctx, thought)
            if result:
                yield result
                trace.append(result)
        final = await self.reflect(ctx, trace)
        yield final
```

### A-3: 中间件洋葱

**影响**:P0-2 Guardrail / P1-1 Tracing
**落点**:新增 `core/middleware.py`

```python
"""中间件洋葱(借鉴 AgentScope MiddlewareBase 6 钩子)。"""
from __future__ import annotations
import abc
from typing import Any, Callable, Optional

from officeagent.core.types_msg import Msg

class MiddlewareBase(abc.ABC):
    """中间件基类:6 钩子,子类按需实现(is_implemented 自动检测)。"""

    async def on_request_start(self, msg: Msg, ctx: Any) -> Msg:
        """请求开始(用户消息进入)。"""
        return msg

    async def on_request_end(self, msg: Msg, ctx: Any) -> Msg:
        """请求结束(Agent 处理前最后一道)。"""
        return msg

    async def on_response_start(self, msg: Msg, ctx: Any) -> Msg:
        """响应开始(Agent 产出后第一道)。"""
        return msg

    async def on_response_end(self, msg: Msg, ctx: Any) -> Msg:
        """响应结束(返回用户前最后一道)。"""
        return msg

    async def on_error(self, error: Exception, ctx: Any) -> Exception:
        """异常处理(可吞掉异常返回 None,或转换异常)。"""
        return error

    async def on_tool_call(self, tool_name: str, args: dict, ctx: Any) -> tuple[str, dict]:
        """工具调用前(可修改参数)。"""
        return tool_name, args

    @property
    def is_implemented(self) -> dict[str, bool]:
        """自动检测哪些钩子被子类实现。"""
        return {
            "on_request_start": type(self).on_request_start is not MiddlewareBase.on_request_start,
            "on_request_end": type(self).on_request_end is not MiddlewareBase.on_request_end,
            "on_response_start": type(self).on_response_start is not MiddlewareBase.on_response_start,
            "on_response_end": type(self).on_response_end is not MiddlewareBase.on_response_end,
            "on_error": type(self).on_error is not MiddlewareBase.on_error,
            "on_tool_call": type(self).on_tool_call is not MiddlewareBase.on_tool_call,
        }

class MiddlewareChain:
    """中间件链:按注册顺序执行请求钩子,逆序执行响应钩子。"""

    def __init__(self, middlewares: Optional[list[MiddlewareBase]] = None) -> None:
        self._middlewares = middlewares or []

    def add(self, mw: MiddlewareBase) -> "MiddlewareChain":
        self._middlewares.append(mw)
        return self

    async def run_request(self, msg: Msg, ctx: Any) -> Msg:
        """请求方向:顺序执行 on_request_start → on_request_end。"""
        for mw in self._middlewares:
            impl = mw.is_implemented
            if impl["on_request_start"]:
                msg = await mw.on_request_start(msg, ctx)
            if impl["on_request_end"]:
                msg = await mw.on_request_end(msg, ctx)
        return msg

    async def run_response(self, msg: Msg, ctx: Any) -> Msg:
        """响应方向:逆序执行 on_response_start → on_response_end。"""
        for mw in reversed(self._middlewares):
            impl = mw.is_implemented
            if impl["on_response_start"]:
                msg = await mw.on_response_start(msg, ctx)
            if impl["on_response_end"]:
                msg = await mw.on_response_end(msg, ctx)
        return msg

# ---------------------------------------------------------------------------
# 现有模块适配为中间件
# ---------------------------------------------------------------------------

class SecurityMiddleware(MiddlewareBase):
    """安全中间件(包装 SecurityEngine/GuardrailPipeline)。"""
    def __init__(self, security_engine) -> None:
        self._engine = security_engine
    async def on_request_end(self, msg: Msg, ctx: Any) -> Msg:
        # 调用 GuardrailPipeline.run_input
        ...
    async def on_response_start(self, msg: Msg, ctx: Any) -> Msg:
        # 调用 GuardrailPipeline.run_output
        ...

class TracingMiddleware(MiddlewareBase):
    """Tracing 中间件(开/关 Span)。"""
    async def on_request_start(self, msg: Msg, ctx: Any) -> Msg:
        ...
    async def on_response_end(self, msg: Msg, ctx: Any) -> Msg:
        ...
```

**与 Guardrail 关系**:Guardrail 管道是 SecurityMiddleware 的内部实现,中间件是更通用的钩子框架。

### A-4: ToolCallState 状态机

**影响**:P0-4 重试策略
**落点**:改造 `core/types.py`

```python
# 在 core/types.py 追加

class ToolCallState(str, Enum):
    """工具调用状态机(借鉴 AgentScope)。"""
    CREATED = "created"       # LLM 决定调用,未执行
    APPROVED = "approved"     # 权限通过
    EXECUTING = "executing"   # 执行中
    SUCCESS = "success"       # 成功(终态)
    FAILED = "failed"         # 失败(可重试)
    CANCELLED = "cancelled"   # 取消(终态)

# ToolCall 改造(原 types.py:148-153)
@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None
    state: ToolCallState = ToolCallState.CREATED  # 新增
    attempts: int = 0                              # 新增

    def transition_to(self, new_state: ToolCallState) -> None:
        """状态流转(含合法性校验)。"""
        valid = {
            ToolCallState.CREATED: {ToolCallState.APPROVED, ToolCallState.CANCELLED},
            ToolCallState.APPROVED: {ToolCallState.EXECUTING, ToolCallState.CANCELLED},
            ToolCallState.EXECUTING: {ToolCallState.SUCCESS, ToolCallState.FAILED, ToolCallState.CANCELLED},
            ToolCallState.FAILED: {ToolCallState.EXECUTING, ToolCallState.CANCELLED},
            ToolCallState.SUCCESS: set(),
            ToolCallState.CANCELLED: set(),
        }
        if new_state not in valid.get(self.state, set()):
            raise ValueError(f"非法状态流转: {self.state} → {new_state}")
        self.state = new_state
```

### A-5: OrchestratorContext 拆分

**影响**:P1-4 Runner
**落点**:新增 `core/orchestrator/state.py`;重命名 `graph/state.py:AgentState` → `GraphState`

```python
"""上下文拆分(可持久化 vs 引用)。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class AgentState:
    """可持久化的 Agent 状态(可序列化、可跨 Agent 传递)。"""
    goal: str = ""
    messages: list = field(default_factory=list)  # list[Msg]
    reasoning_mode: str = ""
    execution_trace: Optional[dict] = None
    final_response: str = ""
    blocked: bool = False
    blocked_reason: str = ""
    # 请求标识
    user_id: str = ""
    session_id: str = ""
    tenant_id: str = ""
    trace_id: str = ""
    project_id: str = ""
    # 记忆上下文(可序列化部分)
    short_term_history: list = field(default_factory=list)
    long_term_memories: list = field(default_factory=list)
    user_profile: Optional[dict] = None

@dataclass
class EngineRefs:
    """不可序列化的引擎引用(不参与 handoff/checkpoint)。"""
    llm_router: Any               # LLMRouter
    memory_manager: Any           # MemoryManager
    tool_registry: Any            # ToolRegistry
    tool_executor: Any            # ToolExecutor
    security_engine: Any          # SecurityEngine
    prompt_manager: Any           # PromptManager
    reasoning_selector: Any       # ReasoningSelector
    validator: Any                # ResultValidator
    replanner: Any                # Replanner
    config: Any                   # CoreConfig

@dataclass
class OrchestratorContext:
    """拆分后的上下文 = AgentState + EngineRefs。"""
    state: AgentState = field(default_factory=AgentState)
    engines: Optional[EngineRefs] = None
```

---

## 二、P0 阶段:状态/安全/类型三补强

### P0-1: 显式 Reducer 状态 Schema

**落点**:新增 `graph/reducers.py`;改造 `graph/state.py`

```python
# graph/reducers.py(新增)
def last_value(left, right): return right
def add_int(left, right): return (left or 0) + right
def append_list(left, right): return (left or []) + right
def append_unique(left, right):
    merged = list(left or [])
    for item in right:
        if item not in merged: merged.append(item)
    return merged
def add_messages(left, right):
    """按 id/role+content 去重追加。"""
    merged, seen = [], set()
    for msg in (left or []) + right:
        key = msg.get("id") or f"{msg.get('role','')}:{msg.get('content','')}"
        if key not in seen:
            seen.add(key); merged.append(msg)
    return merged
def merge_dict(left, right):
    merged = dict(left or {}); merged.update(right); return merged
def merge_trace(left, right):
    """trace 字段深合并(list 追加,dict 合并)。"""
    merged = dict(left or {})
    for k, v in right.items():
        if k in merged and isinstance(merged[k], list) and isinstance(v, list):
            merged[k] = merged[k] + v
        elif k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged
```

```python
# graph/state.py 改造(原 26-56 行)
from typing import Annotated, Any, Optional, TypedDict
from officeagent.graph.reducers import (
    add_int, add_messages, append_list, append_unique,
    last_value, merge_dict, merge_trace,
)

class AgentState(TypedDict, total=False):
    # 对话与意图
    messages: Annotated[list[dict[str, Any]], add_messages]
    user_input: Annotated[str, last_value]
    current_goal: Annotated[str, last_value]
    intent_keywords: Annotated[list[str], append_unique]
    # 拓扑推理
    concept_path: Annotated[list[str], append_unique]
    topology_paths: Annotated[list[dict[str, Any]], append_list]
    # 技能调度
    selected_skills: Annotated[list[str], append_unique]
    skill_priorities: Annotated[dict[str, float], merge_dict]
    # 工具执行
    tool_calls: Annotated[list[dict[str, Any]], append_list]
    tool_results: Annotated[list[dict[str, Any]], append_list]
    # 执行轨迹
    trace: Annotated[dict[str, Any], merge_trace]
    iteration: Annotated[int, add_int]
    # 控制流
    should_continue: Annotated[bool, last_value]
    final_answer: Annotated[str, last_value]
    error: Annotated[Optional[str], last_value]
```

### P0-2: 统一 Guardrail 管道

**落点**:新增 `core/security/guardrail.py`;改造 `core/security/engine.py` + `core/llm/router.py`

```python
# core/security/guardrail.py(新增,核心接口)
@dataclass
class GuardrailResult:
    guardrail_name: str
    passed: bool = True
    tripwire_triggered: bool = False
    blocked_reason: str = ""
    sanitized_text: str = ""
    risk_score: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

class BaseGuardrail(abc.ABC):
    def __init__(self, name: str, *, enabled: bool = True): ...
    def check(self, text: str, **context) -> GuardrailResult: ...
    @abc.abstractmethod
    def _check(self, text: str, **context) -> GuardrailResult: ...

class InputGuardrail(BaseGuardrail): ...
class OutputGuardrail(BaseGuardrail): ...

# 5 个适配类:InputInjectionGuardrail / InputSensitiveGuardrail /
# InputModerationGuardrail / OutputModerationGuardrail / OutputDesensitizeGuardrail

class GuardrailPipeline:
    def __init__(self, input_guardrails=None, output_guardrails=None): ...
    def add_input(self, g: InputGuardrail) -> "GuardrailPipeline": ...
    def add_output(self, g: OutputGuardrail) -> "GuardrailPipeline": ...
    def run_input(self, text: str, **ctx) -> "GuardrailPipelineResult": ...
    def run_output(self, text: str, **ctx) -> "GuardrailPipelineResult": ...
```

### P0-3: LLM 输出结构化校验

**落点**:新增 `core/reasoning/schemas.py` + `core/output.py`

```python
# core/reasoning/schemas.py(新增)
from pydantic import BaseModel, Field

class ToolCallDecision(BaseModel):
    thought: str
    action_type: str  # "tool_call" | "final_answer"
    tool_name: Optional[str] = None
    tool_arguments: dict = {}
    final_answer: Optional[str] = None

class PlanStepOutput(BaseModel):
    step_no: int; description: str
    tool_name: Optional[str] = None
    arguments: dict = {}; depends_on: list[int] = []

class PlanOutput(BaseModel):
    goal: str; steps: list[PlanStepOutput]; reasoning: str = ""

class FinalAnswer(BaseModel):
    answer: str; confidence: float = 0.8
    citations: list[str] = []; summary: str = ""

# core/output.py(新增)
class OutputValidationError(Exception): ...
class OutputSchema(Generic[T]):
    model_type: type[T]
    def validate(self, text: str) -> T: ...
class ObjectOutputProcessor(OutputProcessor[T]):
    def process(self, text: str) -> T: ...
    def format_error_feedback(self, error) -> str: ...
```

### P0-4: 结构化重试策略

**落点**:新增 `core/tools/retry.py`;改造 `core/tools/protocol.py` + `executor.py`

```python
# core/tools/retry.py(新增)
class RetryableError(OfficeAgentError): ...
class NonRetryableError(OfficeAgentError): ...

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay: float = 0.5
    max_delay: float = 10.0
    backoff_factor: float = 2.0
    jitter: float = 0.1
    retryable_exceptions: tuple = (RetryableError,)
    def compute_delay(self, attempt: int) -> float: ...
    def should_retry(self, error: Exception, attempt: int) -> bool: ...

DEFAULT_RETRY_POLICY = RetryPolicy()
NETWORK_RETRY_POLICY = RetryPolicy(max_attempts=5, initial_delay=1.0)
NO_RETRY_POLICY = RetryPolicy(max_attempts=1)

def with_retry(func, policy, *args, **kwargs): ...

# ToolMetadata 新增字段
retry_policy: Optional[RetryPolicy] = None
is_concurrency_safe: bool = True
initial_state: ToolCallState = ToolCallState.CREATED
```

---

## 三、P1 阶段:可观测/可恢复/入口收敛

### P1-1: 分层 Tracing Span

**落点**:新增 `core/observability/tracing/` 目录(span.py/trace.py/scope.py/provider.py)

```python
# 核心类签名
class SpanStatus:
    STARTED = "started"; COMPLETED = "completed"; FAILED = "failed"

@dataclass
class SpanData: span_type: str = "custom"  # 基类
class AgentSpanData(SpanData): agent_name/reasoning_mode/iteration/thought
class LLMSpanData(SpanData): provider/model/prompt_tokens/completion_tokens/...
class ToolSpanData(SpanData): tool_name/arguments/status/duration_ms/error
class GuardrailSpanData(SpanData): direction/passed/blocked_reason/risk_score
class HandoffSpanData(SpanData): from_agent/to_agent/reason

@dataclass
class Span:  # 不可变快照
    span_id/trace_id/parent_id/name/started_at/ended_at/status/data/error/attributes

class SpanImpl:  # 可变,context manager
    def __enter__/__exit__/end/set_error/set_attribute/export

class TraceImpl:
    def start_span(name, data) -> SpanImpl
    def end(status)/export

class TracingScope:  # contextvars 栈
    def push/pop/current_span_id/current_span

class TracingProvider:
    def start_trace(name, trace_id=None, **attrs) -> TraceImpl
    def add_span_exporter/add_trace_exporter
```

### P1-2: Checkpoint 持久化

**落点**:新增 `core/checkpoint/` 目录(base/memory/postgres/types)

```python
@dataclass
class CheckpointMetadata:
    source: str = "loop"  # loop/input/update/interrupt
    step: int = -1
    writes: dict = field(default_factory=dict)
    score: Optional[float] = None

@dataclass
class Checkpoint:
    channel_values: dict = field(default_factory=dict)
    channel_versions: dict[str, int] = field(default_factory=dict)
    versions_seen: dict = field(default_factory=dict)
    metadata: CheckpointMetadata = field(default_factory=CheckpointMetadata)

@dataclass
class CheckpointTuple:
    config: dict; checkpoint: Checkpoint
    metadata: CheckpointMetadata; parent_config: Optional[dict] = None

class BaseCheckpointer(abc.ABC):
    def put/aput/get/aget/list/alist/get_state/aget_state/update_state

class MemoryCheckpointer(BaseCheckpointer): ...  # 测试用
class PostgresCheckpointer(BaseCheckpointer):    # 生产用
    SCHEMA_SQL = "CREATE TABLE agent_checkpoints ..."
```

### P1-3: Conditional Edge 动态路由

**落点**:改造 `graph/edges.py`

```python
RouteFn = Callable[[AgentState], str]

@dataclass
class RouteDecision:
    edge: str; reason: str = ""

class RouteRegistry:
    def register(node_name, route_fn, targets=None): ...
    def get(node_name) -> Optional[RouteFn]: ...

# 新增路由函数
def route_after_reflect_v2(state) -> RouteDecision: ...  # 含 to_human_review/to_replan
def route_after_execute(state) -> RouteDecision: ...     # 含 to_fallback
```

### P1-4: 单一 Runner 入口

**落点**:新增 `core/runner.py`;改造 `core/orchestrator/lifecycle.py` + `api/routers/chat.py`

```python
class StepKind(str, Enum):
    RUN_NODE / HANDOFF / FINAL / INTERRUPT / ERROR

@dataclass
class NextStep: kind: StepKind
class NextStepRunNode(NextStep): node_name/inputs
class NextStepHandoff(NextStep): target_agent/reason
class NextStepFinal(NextStep): answer/usage
class NextStepInterrupt(NextStep): reason/interrupt_id/resume_payload
class NextStepError(NextStep): error/error_type

@dataclass
class RunConfig:
    mode="auto"  # auto/legacy/graph
    max_steps=50; thread_id=""; checkpoint_enabled=False
    resume_from=None; stream=False; user_id=""; session_id=""; trace_id=""

@dataclass
class RunResult:
    answer/success/error/trace_id/thread_id/usage/execution_trace/duration_ms/steps_taken/final_step

class AgentRunner:
    def __init__(self, ctx, graph=None, checkpointer=None): ...
    def run(self, user_input, config=None) -> RunResult: ...
    async def arun(self, user_input, config=None) -> RunResult: ...
    async def astream(self, user_input, config=None) -> AsyncGenerator[NextStep, None]: ...
    def resume(self, thread_id, resume_payload=None) -> RunResult: ...
    def _main_loop(self, user_input, config, trace) -> RunResult: ...  # while True + NextStep
```

### P1-5: Token/Cost 归因

**落点**:新增 `core/usage.py`;改造 `core/reasoning/base.py`

```python
class UsageExceededError(Exception):
    limit_type/limit/actual

@dataclass
class Usage:
    requests/input_tokens/output_tokens/total_tokens/cost
    def add(other) -> Usage / add_inplace(other) -> Usage
    @classmethod
    def from_token_usage(token_usage, cost=0.0) -> Usage
    def to_dict() -> dict

@dataclass
class UsageLimits:
    request_limit: Optional[int] = None
    total_tokens_limit: Optional[int] = None
    cost_limit: Optional[float] = None
    def check(usage: Usage) -> None  # 超限抛 UsageExceededError

# ReasoningContext 新增字段
usage: Optional[Usage] = None
usage_limits: Optional[UsageLimits] = None
billing_meter: Any = None
```

---

## 四、P2 阶段:Office 顶级 + 办公生态(11 个任务)

### P2-1: 项目空间化

**落点**:新增 `core/project/`(models.py + service.py)

```python
class ProjectRole(str, Enum): OWNER/ADMIN/EDITOR/VIEWER
class Project(BaseModel): id/tenant_id/name/description/status/owner_id/settings/...
class ProjectMember(BaseModel): id/project_id/user_id/role/joined_at
class ProjectAsset(BaseModel): id/project_id/asset_type/ref_id/name/permission

class ProjectService:
    def create_project/get_project/update_project/archive_project/delete_project/list_projects
    def add_member/remove_member/update_member_role/list_members
    def add_asset/remove_asset/list_assets
    def check_permission/get_member_role
```

**DB 表**:`projects` / `project_members` / `project_assets`

### P2-2: 组织内技能市场

**落点**:扩展 `core/skills/`(market.py + install.py)

```python
class SkillStatus(str, Enum): DRAFT/PENDING_REVIEW/PUBLISHED/REJECTED/DEPRECATED
class SkillVersion(BaseModel): version/changelog/skill_level/tool_names/config_schema
class SkillMarketEntry(BaseModel): id/tenant_id/name/display_name/.../versions/install_count

class SkillMarket:
    def create_draft/submit_for_review/approve/deprecate
    def add_version/list_versions/get_version
    def search/get_entry

class SkillInstaller:
    def install/uninstall/disable/enable/upgrade
    def list_installations/get_installation/is_installed
```

### P2-3: MCP 消费接入办公生态

**落点**:新增 `core/mcp/`(types/client/registry/server)

```python
class MCPToolDef(BaseModel): name/description/input_schema/output_schema/server_id
class MCPRequest(BaseModel): tool_name/arguments/request_id/timeout_ms
class MCPResponse(BaseModel): request_id/success/result/error/latency_ms

class MCPClient:
    def connect/disconnect/list_tools/get_tool/call_tool/call_tool_async/ping

class MCPToolRegistry:
    def register_server/unregister_server/list_servers/sync_tools/sync_all
    def to_tool_metadata/make_executor/call

class MCPServer:
    def list_exposed_tools/is_exposed/add_to_whitelist/remove_from_whitelist
    def handle_call/server_info/serve_stdio/serve_sse
```

### P2-4: 工具两层架构 + 检索

**落点**:新增 `core/tools/retriever.py`;改造 `core/tools/protocol.py`

```python
class ToolLayer(str, Enum): L1_OFFICE / L2_ECOSYSTEM / INFRA

# ToolMetadata 新增字段
layer: ToolLayer = None
description_embedding: Optional[list[float]] = None
source: str = "builtin"  # builtin/mcp/market
cost_score: float = 0.5

class ToolRetriever:
    def __init__(self, tool_registry, embedder, top_k=5, min_score=0.3, l1_boost=0.15)
    def build_index/add_tool/remove_tool/reembed
    def retrieve(query, top_k, layer_filter, min_score) -> list[tuple[ToolMetadata, float]]
    def retrieve_with_fallback(query, topology_path) -> ...
```

### P2-5: Knowledge Pipeline

**落点**:新增 `core/knowledge/`(pipeline.py + steps.py)

```python
@dataclass
class PipelineContext:
    document_id/tenant_id/file_path/mime_type
    ocr_text/parsed_blocks/chunks/extracted_metadata/permission_tags/embeddings/errors

class PipelineStep(abc.ABC):
    @property
    def name(self) -> str: ...
    @property
    def required(self) -> bool: return True
    def execute(self, ctx) -> PipelineContext: ...
    def should_run(self, ctx) -> bool: return True

class KnowledgePipeline:
    def __init__(self, steps=None)  # 默认 6 步
    def run/run_async(ctx) -> PipelineContext
    def add_step/remove_step/replace_step/list_steps/get_progress

# 6 个步骤类
class OCRStep(PipelineStep): engine/lang; should_run(仅图片/扫描件)
class ParseStep(PipelineStep): parser(auto/docx/pdf/markdown/html)
class ChunkStep(PipelineStep): strategy/chunk_size/chunk_overlap
class ExtractStep(PipelineStep): extract_fields; required=False
class PermissionStep(PipelineStep): default_visibility
class EmbedStep(PipelineStep): embedder_name/batch_size
```

### P2-6: 推理策略可插拔

**落点**:新增 `core/reasoning/strategies/`;改造 `selector.py`

```python
@dataclass
class StrategyContext:
    goal/llm/tool_registry/tool_executor/history/user_id/session_id/project_id/trace_id/max_iterations

class BaseStrategy(abc.ABC):
    @property
    def name(self) -> str: ...
    @property
    def think_mode(self) -> bool: ...  # GLM-4.5 思考/非思考
    def execute(self, ctx) -> ExecutionTrace: ...
    def estimate_cost(self, ctx) -> dict: ...
    def is_applicable(self, ctx) -> bool: return True

class FastStrategy(BaseStrategy):     # 快速(单步ReAct,非思考)
class CheapStrategy(BaseStrategy):    # 低成本(便宜模型,少工具)
class PreciseStrategy(BaseStrategy):  # 精确(Plan&Execute+反思,思考模式)
class ComplianceStrategy(BaseStrategy):  # 合规(强审计,人工确认)

# ReasoningSelector 改造为策略模式
class ReasoningSelector:
    def select(goal, available_tools, user_preference, sensitivity) -> BaseStrategy
    def select_by_complexity(goal, available_tools) -> BaseStrategy
    def register_strategy/get_strategy/list_strategies
```

### P2-7: 蜂巢化部署

4 个独立服务:`doc-parser`(OCR/Parse/Chunk/Extract) / `knowledge`(Embed/检索) / `agent-runner`(推理调度) / `tool-executor`(沙箱+MCP)。
落点:`deploy/docker/docker-compose.prod.yml`(4 服务 + postgres/redis/minio/gateway)。

### P2-8: 思考/非思考模式

```python
@dataclass
class ModelCapability:
    model_name/supports_think_mode/supports_tool_calling/supports_vision
    context_window/cost_per_1k_input/cost_per_1k_output/latency_p50_ms

# LLMRouter 新增
def register_capability(capability: ModelCapability): ...
def chat_with_think(request, think_mode: bool) -> LLMResponse: ...

# ReasoningSelector 新增
def select_think_mode(goal, available_tools, user_preference) -> bool
def select_with_mode(...) -> tuple[BaseStrategy, bool]
```

### P2-9: L1 Office 专家能力深化

重组 `business/` → `office/` + `research/`,8 个 Expert 类:

| 类名 | 落点 | 核心方法 |
|------|------|----------|
| WordExpert | `office/word/` | create/edit/apply_style/generate_toc/merge/compare/redact/extract_tables/track_changes |
| ExcelExpert | `office/excel/` | create/read/formula/pivot_table/chart/merge/conditional_format/to_csv |
| PPTExpert | `office/ppt/` | create/add_slide/apply_theme/insert_image/insert_chart/export_images |
| PDFExpert | `office/pdf/` | create/merge/split/extract_text/extract_images/watermark/encrypt/ocr |
| ConverterExpert | `office/converter/` | convert/batch_convert/supported_conversions |
| ParserExpert | `office/parser/` | parse/parse_table/parse_form/detect_layout |
| ChartExpert | `office/chart/` | create_chart/create_from_csv/supported_types |
| TemplateManager | `office/template/` | list/apply/register/preview |

### P2-10: L2 办公生态覆盖

新增 `business/workspace/`,6 个 Connector(继承 WorkspaceConnector):

| Connector | 能力 |
|-----------|------|
| MailConnector | send/list/get/reply/search |
| ScheduleConnector | create_event/list/update/delete/check_freebusy |
| MeetingConnector | create/list/get_link/get_transcript |
| ApprovalConnector | submit/list_pending/approve/reject/get_status |
| IMConnector | send_message/send_card/create_group/list_groups |
| KnowledgeConnector | search/list_bases/get_doc/upload |

### P2-11: 诚实边界设计

**落点**:新增 `core/boundary.py`

```python
class BoundaryDecision(str, Enum): WITHIN/PARTIAL/OUT_OF_SCOPE/NEEDS_HUMAN
class ResponseStrategy(str, Enum): REFUSE_POLITELY/DEGRADE_AND_EXPLAIN/TRANSFER_TO_HUMAN/SUGGEST_ALTERNATIVE

@dataclass
class CapabilityDeclaration:
    name/supported_intents/unsupported_intents/max_input_tokens
    supported_languages/supported_file_types/known_limitations

@dataclass
class IntentAssessment:
    intent/decision/confidence/matched_capability/reason/suggested_strategy

class CapabilityBoundary:
    def declare(declaration) / declare_from_registry() -> int
    def assess_intent(user_request, available_tools) -> IntentAssessment
    def generate_response(assessment, user_request) -> str
    def refuse_politely(user_request, reason) -> str
    def suggest_alternative(user_request, available_capabilities) -> str
    def boundary_report() / known_limitations_summary()
```

---

## 五、P3 阶段:多 Agent 协作

### P3-1: 类型化消息 + Handoff 协议

**落点**:新增 `core/handoff.py`

```python
@dataclass
class HandoffInput:
    from_agent: str; to_agent: str
    reason: str; context: dict  # 含 history/trace/state

@dataclass
class HandoffOutput:
    accepted: bool; receiving_agent: str
    message: str; new_context: Optional[dict] = None

@dataclass
class Handoff:
    """Handoff 声明(Agent 配置)。"""
    target_agent: str
    description: str = ""
    input_filter: Optional[Callable] = None  # 过滤传递的 history
    max_depth: int = 5  # 防止 handoff 死循环

def make_handoff(target: str, **kwargs) -> Handoff: ...

# Runner 集成
class AgentRunner:
    def _exec_handoff(self, step: NextStepHandoff, config) -> NextStep: ...
```

### P3-2: 声明式角色配置

**落点**:新增 `config/roles/*.yaml` + `core/role_loader.py`

```yaml
# config/roles/researcher.yaml
name: researcher
display_name: 学术研究员
goal: 协助用户完成论文检索、文献综述、引用管理
backstory: 你是一位精通学术研究的助手,擅长 arXiv/知网/万方检索
constraints:
  - 引用必须标注来源
  - 不编造不存在的论文
tools: [paper_search, paper_download, citation_manager, bibtex_export]
reasoning_strategy: precise
max_iterations: 15
```

```python
class RoleLoader:
    def load(role_name: str) -> RoleConfig
    def list_roles() -> list[str]
    def validate(role_config: dict) -> bool
```

### P3-3: SOP 一等公民

**落点**:新增 `core/sop/`(models.py + executor.py + compiler.py)

```python
@dataclass
class ExpectedOutput:
    schema: dict  # JSON Schema 校验
    description: str = ""

@dataclass
class Action:
    name: str; tool_name: str
    arguments: dict; expected_output: Optional[ExpectedOutput] = None
    depends_on: list[int] = field(default_factory=list)

@dataclass
class SOP:
    name: str; goal: str
    actions: list[Action]
    version: str = "1.0.0"

class SOPExecutor:
    def execute(self, sop: SOP, ctx) -> ExecutionTrace: ...

class SOPCompiler:
    """SOP → LangGraph 子图。"""
    def compile(self, sop: SOP) -> Any:  # 返回 compiled graph
```

### P3-4: 多 Agent 消息总线

**落点**:新增 `core/multiagent/`(messagebus.py + environment.py + role.py)

```python
class MessageBus:
    def publish(topic: str, msg: Msg) -> None
    def subscribe(topic: str, handler: Callable) -> str  # 返回 sub_id
    def unsubscribe(sub_id: str) -> None

class InMemoryMessageBus(MessageBus): ...

@dataclass
class EnvironmentState:
    agents: dict[str, Agent]
    history: list[Msg]
    current_role: Optional[str] = None

class Environment:
    def __init__(self, bus: MessageBus, agents: list[Agent]): ...
    def publish(msg: Msg) -> None  # 路由到目标 Agent
    def step() -> Msg  # 驱动一轮 Watch-Think-Act
    def get_state() -> EnvironmentState

class Role(Agent):
    """Watch-Think-Act 生命周期的 Agent 子类。"""
    def __init__(self, name, watch_actions: list[str], bus: MessageBus): ...
    async def watch(self, msg: Msg) -> bool  # 是否关注此消息
    async def think(self, ctx) -> Optional[Msg]  # 复用父类
    async def act(self, ctx, thought) -> Optional[Msg]  # 复用父类
```

---

## 六、文件清单总览

### 新增文件

| 阶段 | 文件路径 | 说明 |
|------|----------|------|
| A-1 | `core/types_msg.py` | ContentBlock + Msg + 工厂函数 |
| A-2 | `core/agent.py` | Agent 基类 + AgentContext |
| A-3 | `core/middleware.py` | MiddlewareBase + MiddlewareChain |
| A-5 | `core/orchestrator/state.py` | AgentState + EngineRefs |
| P0-1 | `graph/reducers.py` | 7 个 reducer 函数 |
| P0-2 | `core/security/guardrail.py` | Guardrail 抽象 + 管道 |
| P0-3 | `core/reasoning/schemas.py` | 4 个 Pydantic Model |
| P0-3 | `core/output.py` | OutputSchema + OutputProcessor |
| P0-4 | `core/tools/retry.py` | RetryPolicy + RetryableError |
| P1-1 | `core/observability/tracing/` | span/trace/scope/provider |
| P1-2 | `core/checkpoint/` | base/memory/postgres/types |
| P1-4 | `core/runner.py` | AgentRunner + RunConfig + NextStep |
| P1-5 | `core/usage.py` | Usage + UsageLimits |
| P2-1 | `core/project/` | models + service |
| P2-2 | `core/skills/market.py` + `install.py` | 技能市场 + 安装器 |
| P2-3 | `core/mcp/` | types/client/registry/server |
| P2-4 | `core/tools/retriever.py` | ToolRetriever |
| P2-5 | `core/knowledge/` | pipeline + steps |
| P2-6 | `core/reasoning/strategies/` | 5 策略 + base |
| P2-7 | `deploy/docker/docker-compose.prod.yml` | 蜂巢化部署 |
| P2-11 | `core/boundary.py` | CapabilityBoundary |
| P3-1 | `core/handoff.py` | Handoff 协议 |
| P3-2 | `config/roles/` + `core/role_loader.py` | 声明式角色 |
| P3-3 | `core/sop/` | models + executor + compiler |
| P3-4 | `core/multiagent/` | messagebus + environment + role |

### 改造文件

| 阶段 | 文件路径 | 改造内容 |
|------|----------|----------|
| A-4 | `core/types.py` | 追加 ToolCallState;ToolCall/ToolResult 加 state/attempts |
| P0-1 | `graph/state.py` | AgentState 加 Annotated[T, reducer] |
| P0-2 | `core/security/engine.py` | SecurityEngine 委托 GuardrailPipeline |
| P0-2 | `core/llm/router.py` | chat() 插入 Guardrail |
| P0-3 | `core/reasoning/base.py` | _call_llm 加 output_schema |
| P0-4 | `core/tools/protocol.py` | ToolMetadata 加 retry_policy/is_concurrency_safe |
| P0-4 | `core/tools/executor.py` | execute 加重试 + 状态流转 |
| P1-1 | `core/llm/base.py` | chat 加 Span 埋点 |
| P1-1 | `core/tools/executor.py` | execute 加 Span 埋点 |
| P1-1 | `core/reasoning/react.py` 等 | reason 加 AgentSpan |
| P1-1 | `core/flywheel/trace.py` | TraceStore 加 append_span |
| P1-2 | `graph/builder.py` | build 接受 checkpointer |
| P1-3 | `graph/edges.py` | 新增 RouteRegistry |
| P1-4 | `core/orchestrator/lifecycle.py` | run 加 Span + Usage |
| P1-4 | `api/routers/chat.py` | 走 AgentRunner |
| P1-5 | `core/reasoning/base.py` | ReasoningContext 加 usage |
| P2-4 | `core/tools/protocol.py` | ToolMetadata 加 layer/embedding |
| P2-6 | `core/reasoning/selector.py` | 改为策略模式 |
| P2-8 | `core/llm/router.py` | 加 ModelCapability |
| A-5 | `graph/state.py` | AgentState → GraphState(重命名) |

---

## 七、关键设计决策

1. **A-1 Msg+ContentBlock 最先落地**:块化消息是 Reducer/Handoff/MessageBus 的共同地基,延迟会导致 P0-P2 返工
2. **Agent 基类统一单/多 Agent**:Agent 子类不感知自身角色,单 Agent 阶段 Runner 包装单实例,P3 阶段 Environment 驱动多实例
3. **中间件洋葱让横切关注点提前就位**:SecurityMiddleware 在 P0-2 就包裹 Agent,多 Agent 时各 Role 复用
4. **ToolCallState 驱动单 Agent 重试,P3 复用**:handoff 后目标 Agent 接力执行,state 机保证不重复
5. **Context 拆分使状态可跨 Agent 传递**:handoff 只传 AgentState(可序列化),不传 EngineRefs(线程池等)
6. **Guardrail 是 SecurityMiddleware 的内部实现**:中间件是更通用的钩子框架,二者互补
7. **Checkpoint 单表而非三表**:OfficeAgent 状态规模小,单表 + JSONB 足够,降低运维复杂度
8. **Runner 主循环 while True + NextStep**:而非递归,便于中断/恢复;NextStep 用 dataclass 联合类型
9. **L1/L2 分层通过 ToolLayer 固化**:检索器用 l1_boost 加权护城河优先召回
10. **诚实边界作为横切关注点**:在推理流程入口拦截,越界任务诚实告知不擅长

---

本方案已完成代码级接口设计,所有签名含完整类型注解与 docstring。建议按"A-1/A-4 → A-2/A-3 → P0 → A-5 → P1 → P2 → P3"顺序实施。
