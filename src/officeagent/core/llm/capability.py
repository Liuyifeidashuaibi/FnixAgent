"""LLM 模型能力描述(P2-8)。

不同 LLM 模型具有不同能力,需在 Router 路由时按需筛选:
  - think_mode:        思考模式(GLM-4.5 / DeepSeek-R1,生成 thinking token)
  - vision:            多模态视觉(支持图片输入)
  - function_calling:  函数调用(支持 tools 参数)
  - json_mode:         JSON 模式(强制输出 JSON)
  - long_context:      长上下文(>32K)
  - streaming:         流式输出
  - high_quality:      高质量(贵模型,适合 Precise 策略)
  - low_cost:          低成本(便宜模型,适合 Cheap 策略)

设计:
  - ModelCapability 用位标志(bit flag)存储,便于 & 运算快速匹配
  - LLMRouter.register(provider, capabilities=...) 注册时声明能力
  - LLMRouter._select_for(request) 按需筛选(如 think_mode=True 时跳过不支持的 provider)
  - LLMRequest 新增 think_mode: bool = False 字段(对接 P2-6 策略)
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 能力位标志
# ---------------------------------------------------------------------------


class ModelCapabilityFlag(enum.IntFlag):
    """模型能力位标志(可用 | 组合,& 检测)。"""

    NONE = 0
    THINK_MODE = 1 << 0           # 思考模式(GLM-4.5 / DeepSeek-R1)
    VISION = 1 << 1               # 多模态视觉
    FUNCTION_CALLING = 1 << 2     # 函数调用(tools 参数)
    JSON_MODE = 1 << 3            # JSON 模式(强制输出 JSON)
    LONG_CONTEXT = 1 << 4         # 长上下文(>32K)
    STREAMING = 1 << 5            # 流式输出
    HIGH_QUALITY = 1 << 6         # 高质量(贵模型)
    LOW_COST = 1 << 7             # 低成本(便宜模型)
    TOOL_CHOICE_REQUIRED = 1 << 8 # 支持工具强制选择(tool_choice="required")
    # 预留扩展位
    ALL = THINK_MODE | VISION | FUNCTION_CALLING | JSON_MODE | LONG_CONTEXT | STREAMING | HIGH_QUALITY | LOW_COST | TOOL_CHOICE_REQUIRED


# ---------------------------------------------------------------------------
# ModelCapability
# ---------------------------------------------------------------------------


@dataclass
class ModelCapability:
    """模型能力描述。

    用位标志存储,支持 require(检查必需能力)与 has(检查是否具备)。

    用法:
        cap = ModelCapability(
            model_name="glm-4.5",
            flags=ModelCapabilityFlag.THINK_MODE | ModelCapabilityFlag.FUNCTION_CALLING,
        )
        if cap.require(ModelCapabilityFlag.THINK_MODE):
            # 启用思考模式参数
            ...
    """

    model_name: str = ""
    flags: ModelCapabilityFlag = ModelCapabilityFlag.NONE
    # 能力对应的参数(由 provider 在调用时读取)
    # 如 think_mode 参数名:GLM 用 "thinking",DeepSeek 用 "enable_thinking"
    params: dict[str, Any] = field(default_factory=dict)
    # 上下文窗口与成本(供 Cheap/Precise 策略参考)
    max_context_tokens: int = 8192
    cost_per_1k_input: float = 0.001    # USD
    cost_per_1k_output: float = 0.002
    avg_latency_ms: float = 1000.0

    # ------------------------------------------------------------------
    # 能力检测
    # ------------------------------------------------------------------

    def has(self, flag: ModelCapabilityFlag) -> bool:
        """检查是否具备指定能力。"""
        return bool(self.flags & flag)

    def require(self, flag: ModelCapabilityFlag) -> bool:
        """require 的别名(语义同 has,链式调用更易读)。"""
        return self.has(flag)

    def has_all(self, flags: ModelCapabilityFlag) -> bool:
        """检查是否具备全部指定能力。"""
        return (self.flags & flags) == flags

    def has_any(self, flags: ModelCapabilityFlag) -> bool:
        """检查是否具备任一指定能力。"""
        return bool(self.flags & flags)

    def add(self, flag: ModelCapabilityFlag) -> "ModelCapability":
        """添加能力(链式)。"""
        self.flags |= flag
        return self

    def remove(self, flag: ModelCapabilityFlag) -> "ModelCapability":
        """移除能力(链式)。"""
        self.flags &= ~flag
        return self

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict(供审计/调试)。"""
        return {
            "model_name": self.model_name,
            "flags": int(self.flags),
            "flags_names": self.flags_names,
            "max_context_tokens": self.max_context_tokens,
            "cost_per_1k_input": self.cost_per_1k_input,
            "cost_per_1k_output": self.cost_per_1k_output,
            "avg_latency_ms": self.avg_latency_ms,
        }

    @property
    def flags_names(self) -> list[str]:
        """能力名列表(可读形式)。"""
        names: list[str] = []
        for flag in ModelCapabilityFlag:
            if flag == ModelCapabilityFlag.NONE or flag == ModelCapabilityFlag.ALL:
                continue
            if self.has(flag):
                names.append(flag.name)
        return names

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def for_think_mode(cls, model_name: str = "") -> "ModelCapability":
        """构造仅具备 think_mode 能力的实例。"""
        return cls(
            model_name=model_name,
            flags=ModelCapabilityFlag.THINK_MODE
            | ModelCapabilityFlag.FUNCTION_CALLING
            | ModelCapabilityFlag.STREAMING,
        )

    @classmethod
    def for_high_quality(cls, model_name: str = "") -> "ModelCapability":
        """构造高质量模型能力。"""
        return cls(
            model_name=model_name,
            flags=ModelCapabilityFlag.HIGH_QUALITY
            | ModelCapabilityFlag.THINK_MODE
            | ModelCapabilityFlag.FUNCTION_CALLING
            | ModelCapabilityFlag.STREAMING
            | ModelCapabilityFlag.LONG_CONTEXT,
            max_context_tokens=128000,
            cost_per_1k_input=0.01,
            cost_per_1k_output=0.03,
            avg_latency_ms=2000.0,
        )

    @classmethod
    def for_low_cost(cls, model_name: str = "") -> "ModelCapability":
        """构造低成本模型能力。"""
        return cls(
            model_name=model_name,
            flags=ModelCapabilityFlag.LOW_COST
            | ModelCapabilityFlag.FUNCTION_CALLING
            | ModelCapabilityFlag.STREAMING,
            max_context_tokens=8192,
            cost_per_1k_input=0.0001,
            cost_per_1k_output=0.0002,
            avg_latency_ms=800.0,
        )


# ---------------------------------------------------------------------------
# LLMRequest 能力需求(对接 P2-6 策略)
# ---------------------------------------------------------------------------


@dataclass
class CapabilityRequirement:
    """LLM 调用的能力需求(由 StrategyContext.extra 构造,传给 Router)。

    Router 根据 requirement 筛选具备对应能力的 provider。
    """

    required: ModelCapabilityFlag = ModelCapabilityFlag.NONE
    preferred: ModelCapabilityFlag = ModelCapabilityFlag.NONE  # 优先选择(非强制)
    forbidden: ModelCapabilityFlag = ModelCapabilityFlag.NONE  # 禁止(如 Cheap 策略禁止 HIGH_QUALITY)

    @classmethod
    def for_think_mode(cls) -> "CapabilityRequirement":
        """需要思考模式(Precise/Compliance 策略)。"""
        return cls(required=ModelCapabilityFlag.THINK_MODE)

    @classmethod
    def for_low_cost(cls) -> "CapabilityRequirement":
        """偏好低成本(Cheap 策略)。"""
        return cls(
            preferred=ModelCapabilityFlag.LOW_COST,
            forbidden=ModelCapabilityFlag.HIGH_QUALITY,
        )

    @classmethod
    def for_high_quality(cls) -> "CapabilityRequirement":
        """偏好高质量(Precise 策略)。"""
        return cls(preferred=ModelCapabilityFlag.HIGH_QUALITY)

    def matches(self, capability: ModelCapability) -> bool:
        """检查 capability 是否满足 requirement。"""
        # 必需能力必须全部具备
        if not capability.has_all(self.required):
            return False
        # 禁止能力必须全部不具备
        if capability.has_any(self.forbidden):
            return False
        return True

    def score(self, capability: ModelCapability) -> float:
        """给 capability 打分(供 Router 在多个匹配 provider 中选最优)。

        分数 = 必需能力命中数 * 1.0 + 偏好能力命中数 * 0.5 - 禁止能力命中数 * 2.0

        Args:
            capability: 待评估的模型能力描述。

        Returns:
            float: 综合得分,越高越优。
        """
        score = 0.0
        # 三类权重合并到单次遍历,避免重复迭代 IntFlag
        skip = (ModelCapabilityFlag.NONE, ModelCapabilityFlag.ALL)
        for flag in ModelCapabilityFlag:
            if flag in skip:
                continue
            if not capability.has(flag):
                continue
            if self.required & flag:
                score += 1.0
            if self.preferred & flag:
                score += 0.5
            if self.forbidden & flag:
                score -= 2.0
        return score
