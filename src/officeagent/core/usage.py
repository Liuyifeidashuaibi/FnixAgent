"""Token/Cost 用量归因 —— P1-5。

借鉴 OpenAI Agents SDK 的 Usage 模型 + PydanticAI 的 UsageLimits,
提供统一的 Token/Cost 跟踪与限额控制。

核心类:
  - UsageExceededError: 用量超限异常
  - Usage:              单次或累积用量(请求数/token 数/成本)
  - UsageLimits:        用量限额(超限时抛 UsageExceededError)

设计要点:
  - Usage.add(other):     累加(不可变,返回新实例)
  - Usage.add_inplace(other): 原地累加(可变)
  - Usage.from_token_usage(): 从 LLMResponse.usage 构造
  - UsageLimits.check(usage): 检查是否超限(超限抛异常)

集成点:
  - ReasoningContext 新增 usage / usage_limits / billing_meter 字段
  - AgentRunner 在每步 LLM 调用后累加 usage
  - 超限时 Runner 提前终止并返回部分结果
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class UsageExceededError(Exception):
    """用量超限异常。

    由 UsageLimits.check() 在超限时抛出。
    携带 limit_type/limit/actual 信息,便于上层决策(降级/终止/提示用户)。

    Attributes:
        limit_type: 超限类型(requests/total_tokens/cost)
        limit:      限额值
        actual:     实际值
    """

    def __init__(
        self,
        limit_type: str,
        limit: float,
        actual: float,
    ) -> None:
        self.limit_type = limit_type
        self.limit = limit
        self.actual = actual
        super().__init__(
            f"Usage limit exceeded: {limit_type} limit={limit}, actual={actual}"
        )


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------


@dataclass
class Usage:
    """Token/Cost 用量(单次或累积)。

    Attributes:
        requests:       LLM 请求次数(含缓存命中),必须 >= 0
        input_tokens:   输入 token 数(prompt),必须 >= 0
        output_tokens:  输出 token 数(completion),必须 >= 0
        total_tokens:   总 token 数(应等于 input + output,>= 0)
        cost:           总成本(美元,按 provider 定价计算),>= 0

    不变量:
        - 所有数值字段 >= 0
        - total_tokens 应等于 input_tokens + output_tokens
          (from_token_usage / add / add_inplace 均维护此不变量)
    """

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0

    def __post_init__(self) -> None:
        """构造后校验:所有 token 数与 cost 必须 >= 0。

        负值通常源于上游错误(如 LLM 返回负的 completion_tokens),
        此处截断为 0 并重新计算 total_tokens,保证不变量成立。
        """
        # 非负校验:负值截断为 0(防御性,避免污染累计用量)
        if self.requests < 0:
            self.requests = 0
        if self.input_tokens < 0:
            self.input_tokens = 0
        if self.output_tokens < 0:
            self.output_tokens = 0
        if self.total_tokens < 0:
            self.total_tokens = 0
        if self.cost < 0:
            self.cost = 0.0
        # 维护不变量:total_tokens 应 >= input + output
        # (允许 total 大于 input+output,因部分 provider 额外计费如 reasoning tokens)
        expected_min = self.input_tokens + self.output_tokens
        if self.total_tokens < expected_min:
            self.total_tokens = expected_min

    # -- 累加 ---------------------------------------------------------------
    def add(self, other: "Usage") -> "Usage":
        """累加(不可变,返回新实例)。

        大数相加保护:Python int 为任意精度不会溢出,但 cost(float)
        累加可能损失精度。此处对 cost 做圆整(6 位小数),避免浮点误差累积。
        token 字段相加后由 __post_init__ 重新校验非负与不变量。

        Args:
            other: 另一个 Usage

        Returns:
            新的 Usage 实例(self + other)
        """
        return Usage(
            requests=self.requests + other.requests,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            # total_tokens 取 max(自身+other, input+output) 维护不变量
            total_tokens=max(
                self.total_tokens + other.total_tokens,
                (self.input_tokens + other.input_tokens)
                + (self.output_tokens + other.output_tokens),
            ),
            # cost 圆整避免浮点误差累积(大数相加精度问题)
            cost=round(self.cost + other.cost, 6),
        )

    def add_inplace(self, other: "Usage") -> "Usage":
        """原地累加(可变,修改 self 并返回)。

        线程安全说明:本方法非原子操作,多线程并发累加同一 Usage 实例
        需外部加锁(如 threading.Lock)。AgentRunner 通常单线程累加,
        跨线程聚合时应使用 add(不可变)而非 add_inplace。

        Args:
            other: 另一个 Usage

        Returns:
            self(累加后)
        """
        self.requests += other.requests
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        # 维护不变量:total >= input + output
        self.total_tokens = max(
            self.total_tokens + other.total_tokens,
            self.input_tokens + self.output_tokens,
        )
        # cost 圆整避免浮点误差
        self.cost = round(self.cost + other.cost, 6)
        # 再次校验非负(other 可能含负值)
        if self.requests < 0:
            self.requests = 0
        if self.input_tokens < 0:
            self.input_tokens = 0
        if self.output_tokens < 0:
            self.output_tokens = 0
        if self.total_tokens < 0:
            self.total_tokens = 0
        if self.cost < 0:
            self.cost = 0.0
        return self

    # -- 构造 ---------------------------------------------------------------
    @classmethod
    def from_token_usage(
        cls,
        token_usage: Any,
        cost: float = 0.0,
    ) -> "Usage":
        """从 LLMResponse.usage(TokenUsage)构造 Usage。

        兼容 officeagent.core.types.TokenUsage 的字段名:
          - prompt_tokens / completion_tokens / total_tokens

        Args:
            token_usage: TokenUsage 实例(或含 prompt_tokens/completion_tokens 的对象)
            cost:        本次调用成本(必须 >= 0,负值截断为 0)

        Returns:
            Usage 实例(requests=1)

        说明:所有 token 数负值截断为 0;total_tokens 取 max(显式值, input+output)
        以维护不变量(部分 provider 的 total_tokens 不含 reasoning tokens)。
        """
        prompt_tokens = (
            getattr(token_usage, "prompt_tokens", 0)
            or getattr(token_usage, "input_tokens", 0)
            or 0
        )
        completion_tokens = (
            getattr(token_usage, "completion_tokens", 0)
            or getattr(token_usage, "output_tokens", 0)
            or 0
        )
        total = (
            getattr(token_usage, "total_tokens", 0)
            or (prompt_tokens + completion_tokens)
        )
        # 非负校验(上游可能返回异常负值)
        prompt_tokens = max(0, int(prompt_tokens))
        completion_tokens = max(0, int(completion_tokens))
        total = max(0, int(total))
        # cost 非负
        cost = max(0.0, float(cost))
        # 维护不变量:total >= input + output
        total = max(total, prompt_tokens + completion_tokens)
        return cls(
            requests=1,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total,
            cost=cost,
        )

    @classmethod
    def empty(cls) -> "Usage":
        """创建空 Usage。"""
        return cls()

    # -- 序列化 -------------------------------------------------------------
    def to_dict(self) -> dict:
        """转为字典(用于 API 响应/日志)。"""
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": round(self.cost, 6),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Usage":
        """从字典重建。

        负值会在 __post_init__ 中被截断为 0(防御性,防止持久化的脏数据污染)。
        """
        return cls(
            requests=data.get("requests", 0),
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            cost=data.get("cost", 0.0),
        )

    # -- 便捷属性 -----------------------------------------------------------
    @property
    def is_empty(self) -> bool:
        """是否为空(无任何用量)。"""
        return (
            self.requests == 0
            and self.input_tokens == 0
            and self.output_tokens == 0
            and self.total_tokens == 0
            and self.cost == 0.0
        )

    def __repr__(self) -> str:
        return (
            f"Usage(requests={self.requests}, "
            f"input={self.input_tokens}, output={self.output_tokens}, "
            f"total={self.total_tokens}, cost=${self.cost:.4f})"
        )


# ---------------------------------------------------------------------------
# UsageLimits
# ---------------------------------------------------------------------------


@dataclass
class UsageLimits:
    """用量限额(超限时抛 UsageExceededError)。

    所有字段为 Optional,None 表示不限制该项。

    Attributes:
        request_limit:      最大请求次数
        total_tokens_limit: 最大总 token 数
        cost_limit:         最大成本(美元)
    """

    request_limit: Optional[int] = None
    total_tokens_limit: Optional[int] = None
    cost_limit: Optional[float] = None

    def check(self, usage: Usage) -> None:
        """检查 usage 是否超限(超限抛 UsageExceededError)。

        Args:
            usage: 当前累积用量(已校验非负)

        Raises:
            UsageExceededError: 任一维度超限
        """
        if self.request_limit is not None and usage.requests > self.request_limit:
            raise UsageExceededError(
                limit_type="requests",
                limit=self.request_limit,
                actual=usage.requests,
            )
        if (
            self.total_tokens_limit is not None
            and usage.total_tokens > self.total_tokens_limit
        ):
            raise UsageExceededError(
                limit_type="total_tokens",
                limit=self.total_tokens_limit,
                actual=usage.total_tokens,
            )
        if self.cost_limit is not None and usage.cost > self.cost_limit:
            raise UsageExceededError(
                limit_type="cost",
                limit=self.cost_limit,
                actual=usage.cost,
            )

    def check_or_warn(self, usage: Usage) -> bool:
        """检查是否超限,超限仅返回 False(不抛异常)。

        适用于"软限额"场景(超限仅告警,不终止)。

        Returns:
            True 未超限 / False 已超限
        """
        try:
            self.check(usage)
            return True
        except UsageExceededError:
            return False

    def to_dict(self) -> dict:
        """转为字典。"""
        return {
            "request_limit": self.request_limit,
            "total_tokens_limit": self.total_tokens_limit,
            "cost_limit": self.cost_limit,
        }

    @property
    def is_unlimited(self) -> bool:
        """是否无任何限制(所有字段为 None)。"""
        return (
            self.request_limit is None
            and self.total_tokens_limit is None
            and self.cost_limit is None
        )
