"""
内核统一类型定义。

所有跨模块流转的数据结构集中在此,确保上下游契约一致。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class MessageRole(str, Enum):
    """对话消息角色。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class TaskStatus(str, Enum):
    """任务状态机。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StepStatus(str, Enum):
    """子任务步骤状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ToolPermission(str, Enum):
    """工具权限等级(越高越敏感)。"""

    LOW = "low"  # 纯计算/检索, 无副作用
    MIDDLE = "middle"  # 读写文件, 调用外部 API
    HIGH = "high"  # 执行代码, 写库, 发送消息


class ReasoningMode(str, Enum):
    """推理模式。"""

    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    SELF_REFLECT = "self_reflect"


class ToolExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CircuitState(str, Enum):
    """熔断器状态。"""

    CLOSED = "closed"  # 正常放行
    OPEN = "open"  # 熔断, 快速失败
    HALF_OPEN = "half_open"  # 半开, 探测恢复


class ToolCallState(str, Enum):
    """工具调用状态机。

    状态流转图:
        CREATED ──→ APPROVED ──→ EXECUTING ──→ SUCCESS(终态)
           │           │              │
           ↓           ↓              ↓
        CANCELLED   CANCELLED    FAILED ──→ EXECUTING(重试)
        (终态)      (终态)         │
                                   ↓
                               CANCELLED(终态)

    用途:
      - P0-4 重试策略:仅 FAILED 状态可重试,重试时回到 EXECUTING
      - P3-1 Handoff:目标 Agent 接力时检查 state,避免重复执行已成功调用
      - 可观测性:每个状态流转都埋 Span
    """

    CREATED = "created"  # LLM 决定调用,未执行
    APPROVED = "approved"  # 权限通过(待执行)
    EXECUTING = "executing"  # 执行中
    SUCCESS = "success"  # 成功(终态)
    FAILED = "failed"  # 失败(可重试)
    CANCELLED = "cancelled"  # 取消(终态)


# ---------------------------------------------------------------------------
# 消息与对话
# ---------------------------------------------------------------------------


@dataclass
class Message:
    """一条对话消息。"""

    role: MessageRole
    content: str
    name: str | None = None  # tool 角色时的工具名
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int | None = None  # 由 tokenizer 回填
    # Bug-037: assistant 消息声明的工具调用 / tool 消息对应的调用 ID。
    # 缺失时严格校验的 provider（qwen-max 等）对 role=tool 消息直接 400
    # "must be a response to a preceeding message with tool_calls"。
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None

    def to_llm_dict(self) -> dict[str, Any]:
        """转换为 LLM provider 通用的 dict 结构。"""
        d: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        # Bug-037: 透传工具调用上下文，保证 assistant(tool_calls) 与
        # 后续 role=tool(tool_call_id) 消息成对出现、序列完整。
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class TokenUsage:
    """Token 用量。

    Attributes:
        prompt_tokens:     输入 token 数
        completion_tokens: 输出 token 数
        total_tokens:      总 token 数(prompt + completion)
        cached_tokens:     P4.2 — prompt cache 命中的 token 数 (OpenAI 兼容字段
                           prompt_tokens_details.cached_tokens; DeepSeek 字段
                           prompt_cache_hit_tokens)。0 表示无 cache 命中。
                           命中部分通常按 10-50% 价格计费 (qwen-plus 隐式 20% /
                           GLM 50% / DeepSeek 2%), 用于监控 cache 优化效果。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def add(self, other: TokenUsage) -> TokenUsage:
        """累加另一份 Token 用量, 返回新的 TokenUsage 实例。

        Args:
            other: 另一份 TokenUsage

        Returns:
            累加后的新 TokenUsage(不修改 self 与 other)

        Raises:
            TypeError: other 不是 TokenUsage 实例
        """
        if not isinstance(other, TokenUsage):
            raise TypeError(f"other must be TokenUsage, got {type(other).__name__}")
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


# ---------------------------------------------------------------------------
# LLM 响应
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """LLM 调用结果。"""

    content: str
    model: str
    usage: TokenUsage
    raw: Any = None  # provider 原始返回
    cached: bool = False  # 是否命中缓存
    finish_reason: str | None = None
    tool_calls: list[dict] = field(default_factory=list)  # function calling 工具调用
    # Spec 2: reasoning model 的思考链内容 (Qwen3 reasoning_content / OpenAI o1 reasoning /
    # 推理模型 thinking)。普通模型 (qwen-plus / glm-4 / gpt-4o) 此字段为空。
    # 由 OpenAICompatibleProvider._parse_response 从 message.reasoning_content /
    # message.reasoning / message.thinking 中提取，供前端 ProcessTimeline 折叠展示。
    reasoning_content: str = ""


# ---------------------------------------------------------------------------
# 记忆
# ---------------------------------------------------------------------------


@dataclass
class MemoryItem:
    """长期记忆中的一条记录。"""

    id: str
    content: str
    score: float  # 召回相似度
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Entity:
    """实体记忆(结构化业务实体)。"""

    entity_type: str  # user_profile / paper / project ...
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """LLM 决定调用某工具(含状态机,)。

    state 字段驱动 P0-4 重试策略与 P3-1 Handoff 接力:
      - 重试:仅 FAILED 可重试,重试时 attempts+=1 并回到 EXECUTING
      - Handoff:目标 Agent 检查 state,SUCCESS 的调用不重复执行
    """

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None  # 用于关联 tool 角色回执
    state: ToolCallState = ToolCallState.CREATED  # 状态机
    attempts: int = 0  # 已尝试次数(含首次)

    def transition_to(self, new_state: ToolCallState) -> None:
        """状态流转(含合法性校验)。

        合法流转:
          CREATED   → APPROVED | CANCELLED
          APPROVED  → EXECUTING | CANCELLED
          EXECUTING → SUCCESS | FAILED | CANCELLED
          FAILED    → EXECUTING(重试) | CANCELLED
          SUCCESS   → (终态,不可流转)
          CANCELLED → (终态,不可流转)

        Raises:
            ValueError: 非法状态流转
        """
        valid_transitions: dict[ToolCallState, set[ToolCallState]] = {
            ToolCallState.CREATED: {ToolCallState.APPROVED, ToolCallState.CANCELLED},
            ToolCallState.APPROVED: {ToolCallState.EXECUTING, ToolCallState.CANCELLED},
            ToolCallState.EXECUTING: {
                ToolCallState.SUCCESS,
                ToolCallState.FAILED,
                ToolCallState.CANCELLED,
            },
            ToolCallState.FAILED: {ToolCallState.EXECUTING, ToolCallState.CANCELLED},
            ToolCallState.SUCCESS: set(),
            ToolCallState.CANCELLED: set(),
        }
        if new_state not in valid_transitions.get(self.state, set()):
            raise ValueError(f"非法状态流转: {self.state.value} → {new_state.value}")
        self.state = new_state

    def is_terminal(self) -> bool:
        """是否处于终态(SUCCESS / CANCELLED)。"""
        return self.state in (ToolCallState.SUCCESS, ToolCallState.CANCELLED)

    def can_retry(self) -> bool:
        """是否可重试(仅 FAILED 状态可重试)。"""
        return self.state == ToolCallState.FAILED


@dataclass
class ToolResult:
    """工具执行结果。

    state 字段与 ToolCall.state 对应,便于结果侧也追踪状态。
    """

    call_id: str | None
    name: str
    status: ToolExecutionStatus
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    state: ToolCallState = ToolCallState.CREATED  # 对应 ToolCall.state


# ---------------------------------------------------------------------------
# 推理过程
# ---------------------------------------------------------------------------


@dataclass
class ThoughtStep:
    """ReAct 单步: 思考-行动-观察。"""

    thought: str  # 推理过程
    action: ToolCall | None = None  # 决定调用的工具
    observation: ToolResult | None = None  # 工具返回


@dataclass
class PlanStep:
    """Plan&Execute 中的计划步骤。"""

    step_no: int
    description: str
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: list[int] = field(default_factory=list)  # 依赖的前置步骤号


@dataclass
class Plan:
    """执行计划。"""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)


@dataclass
class ReflectionResult:
    """反思校验结果。"""

    passed: bool
    score: float  # 0~1 置信度
    check_type: str = "completeness"
    reason: str = ""
    suggestion: str = ""  # 重规划建议
    needs_replan: bool = False


@dataclass
class ExecutionTrace:
    """单次任务完整执行轨迹(供落库与案例回流)。"""

    task_id: str
    trace_id: str
    mode: ReasoningMode
    steps: list[Any] = field(default_factory=list)  # ThoughtStep / PlanStep
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    reflections: list[ReflectionResult] = field(default_factory=list)
    total_usage: TokenUsage = field(default_factory=TokenUsage)
    iterations: int = 0


# ===========================================================================
# 知识拓扑图 (KTG) / 技能-拓扑突触协议 (STP) / 四阶段进化飞轮 (MFP)
# ===========================================================================
# 此区域类型服务于"自进化 Agent"三层子系统:
#   - KTG: 用 4 层固定拓扑替代高维向量召回,权重路径搜索避免语义漂移
#   - STP: 技能绑定到 L2 概念节点,拓扑权重动态换算调度优先级
#   - MFP: 四飞轮闭环驱动持续进化(感知→固化→反思→爬山)
# 所有类型为纯数据结构,不耦合具体存储后端,便于单元测试与跨平台迁移。


class TopologyLayer(str, Enum):
    """KTG 四层固定结构。

    严格遵循"上层抽象、下层具体"原则,不允许跨层直接连边(L1 只连 L2,L2 只连 L3)。
    """

    L1_GOAL = "L1"  # 目标层: 用户意图/任务目标(如"撰写论文综述")
    L2_CONCEPT = "L2"  # 概念层: 抽象概念(如"文献检索")— STP 技能绑定层
    L3_RULE = "L3"  # 规则层: 可执行规则(如"按发表年份降序排序")
    L4_FACT = "L4"  # 事实层: 具体事实/案例(如"arXiv:2401.00001 是 GPT-4 论文")


class NodeType(str, Enum):
    """KTG 节点类型(6 种,永久固定,不允许新增)。

    不同节点类型承载不同语义,边权计算策略也不同。
    前 4 类对应四层各一类;CONSTRAINT 与 INFERENCE 是 L3 规则层的子类。
    """

    GOAL = "goal"  # 目标节点(仅 L1): 根目标
    CONCEPT = "concept"  # 概念节点(仅 L2): STP 绑定锚点
    RULE = "rule"  # 规则节点(仅 L3): 调用前置/约束/优先级
    FACT = "fact"  # 事实节点(仅 L4): 具体执行案例/最优参数
    CONSTRAINT = "constraint"  # 约束节点(仅 L3): 规则子类(threshold 型)
    INFERENCE = "inference"  # 推理链路节点(仅 L3): from→to 推理路径


class EdgeType(str, Enum):
    """KTG 边类型(6 种,永久固定,不允许新增)。

    每种边携带独立权重,路径搜索时按边类型分别加权。
    MUTEX 边权重恒为 -1.0(降权),CONTAINS 边权重恒为 1.0。
    """

    CAUSAL = "causal"  # 因果: A 导致 B(因果强度)
    DEPENDS_ON = "depends_on"  # 依赖: A 依赖 B(依赖必要性)
    DERIVES = "derives"  # 推导: A 推导出 B(推导置信度)
    CONTAINS = "contains"  # 包含: A 包含 B(恒 1.0)
    PRECONDITION = "precondition"  # 前置: A 是 B 的前置(前置必要性)
    MUTEX = "mutex"  # 互斥: A 与 B 互斥(恒 -1.0,降权)


class SkillLevel(str, Enum):
    """技能三级权限(STP)。

    决定调度时是否需要用户确认,以及是否允许自动执行。
    """

    BASIC = "basic"  # 基础: 纯计算/检索,无副作用,自动调用
    REASONING = "reasoning"  # 推理: 调用外部 API/读写文件,需确认
    META = "meta"  # 元级: 修改自身(技能/拓扑),默认禁用


class FlywheelStage(str, Enum):
    """MFP 四阶段飞轮。

    四阶段循环执行,形成自驱动闭环。
    """

    PERCEPTION = "perception"  # ① 感知-执行: 任务理解→工具调用→结果收集
    SOLIDIFICATION = "solidification"  # ② 知识固化: 案例归并→规则提取→写入 KTG
    META_REFLECTION = "meta_reflection"  # ③ 元反思: 评估策略/识别短板/规划改进
    HILL_CLIMBING = "hill_climbing"  # ④ 爬山进化: 试探性变异→对比基线→保留/回滚


@dataclass
class TopologyNode:
    """KTG 节点。

    所有节点共享同一结构,通过 layer 与 node_type 区分语义。
    节点不持有边的引用(避免双向引用导致的循环),边由 TopologyEdge 单独维护。
    """

    node_id: str  # 全局唯一 ID(如 "L2:literature_search")
    layer: TopologyLayer  # 所属层级
    node_type: NodeType  # 节点类型
    name: str  # 人类可读名称
    content: str = ""  # 节点内容(规则文本/事实描述等)
    weight: float = 0.5  # 节点权重(0~1,受衰减与强化影响)
    confidence: float = 0.3  # 置信度(0~1,新节点 0.3,命中 +0.02)
    use_count: int = 0  # 命中次数
    freshness: float = 1.0  # 新鲜度(每日 ×0.999,命中重置 1.0)
    deprecated: bool = False  # 是否废弃(权重降至 0.01,不物理删除)
    version: int = 1  # 版本号(支持快照回放)
    metadata: dict[str, Any] = field(
        default_factory=dict
    )  # 扩展字段(source/priority/precondition 等)
    skill_binding: str | None = None  # 仅 L2 节点: 绑定的技能名
    created_at: float = 0.0  # Unix 时间戳(用于衰减计算)
    last_used_at: float = 0.0  # 最近使用时间戳


@dataclass
class TopologyEdge:
    """KTG 边。

    边是有向的(from→to),权重独立于节点权重。
    路径搜索时,边权重与节点权重共同决定路径优先级。
    MUTEX 边权重恒 -1.0(降权),CONTAINS 边权重恒 1.0。
    """

    edge_id: str  # 边唯一 ID
    source_id: str  # 起点节点 ID
    target_id: str  # 终点节点 ID
    edge_type: EdgeType  # 边类型
    weight: float = 0.5  # 边权重(MUTEX=-1.0, CONTAINS=1.0, 其余 0~1)
    version: int = 1  # 版本号
    deprecated: bool = False  # 是否废弃
    metadata: dict[str, Any] = field(default_factory=dict)  # 创建原因/置信度等
    created_at: float = 0.0


@dataclass
class TopologyPath:
    """KTG 路径搜索结果。

    一条路径 = 起点节点 + 终点节点 + 中间边序列 + 累积权重。
    """

    nodes: list[str] = field(default_factory=list)  # 节点 ID 序列(含起终点)
    edges: list[str] = field(default_factory=list)  # 边 ID 序列
    total_weight: float = 0.0  # 累积权重(乘积或加权和)
    depth: int = 0  # 路径深度(边数)


@dataclass
class SkillRecord:
    """技能记录(STP)。

    描述一个可被调度的技能,与 ToolMetadata.skill_level/topology_binding 对应。
    技能本身不持有 func 引用,通过 name 与工具注册表关联。
    """

    name: str  # 技能名(与 ToolMetadata.name 对应)
    skill_level: SkillLevel  # 权限级别
    bound_concept_id: str | None = None  # 绑定的 L2 概念节点 ID
    priority: float = 0.5  # 当前调度优先级(由拓扑权重动态换算)
    success_count: int = 0  # 历史成功调用次数
    failure_count: int = 0  # 历史失败调用次数
    last_invoked_at: float = 0.0  # 最近调用时间戳


@dataclass
class TraceRecord:
    """执行轨迹记录(供飞轮 ② 知识固化消费)。

    每次任务执行后,由飞轮 ① 感知-执行阶段产出,飞轮 ② 消费并提取规则。
    与 ExecutionTrace 区别: TraceRecord 是持久化版本,ExecutionTrace 是运行时版本。
    """

    trace_id: str
    task_id: str
    goal: str  # 用户目标(L1 节点候选)
    mode: ReasoningMode  # 使用的推理模式
    concept_path: list[str] = field(default_factory=list)  # 命中的 L2 概念序列
    tool_calls: list[dict] = field(default_factory=list)  # 工具调用记录(name+args+status)
    success: bool = False  # 整体是否成功
    duration_ms: float = 0.0  # 总耗时
    usage_tokens: int = 0  # 总 token 消耗
    reflection_score: float = 0.0  # 元反思打分(0~1)
    created_at: float = 0.0
    # Spec 7 fail-soft-with-signal 闭环: Critic 审查状态
    # True=审查未完成 (LLM 故障/解析失败/异常), MFP 第 3 阶统计 skip_rate
    critic_skipped: bool = False


@dataclass
class EvolutionSnapshot:
    """进化快照(飞轮 ④ 爬山进化产出)。

    每次进化检查时生成一份快照,保留拓扑与技能权重状态,
    若后续性能回退则可回滚到历史快照。
    """

    snapshot_id: str
    stage: FlywheelStage  # 快照对应飞轮阶段
    node_count: int = 0  # 拓扑节点数
    edge_count: int = 0  # 拓扑边数
    skill_count: int = 0  # 技能数
    avg_success_rate: float = 0.0  # 最近任务平均成功率
    avg_token_efficiency: float = 0.0  # 平均 token 效率(success/tokens)
    payload: dict[str, Any] = field(default_factory=dict)  # 完整拓扑与技能权重序列化
    created_at: float = 0.0
