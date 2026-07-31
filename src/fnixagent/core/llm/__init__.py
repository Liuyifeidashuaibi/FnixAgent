"""LLM 基础服务层。

提供多模型兼容、负载均衡、限流、token 计费统计、请求缓存、异常熔断。
P2-8 新增:模型能力描述(ModelCapability / CapabilityRequirement),
让 LLMRouter 按需筛选具备 think_mode / vision / function_calling 等能力的 provider。
"""

from fnixagent.core.llm.base import BaseLLMProvider, LLMRequest
from fnixagent.core.llm.billing import BillingMeter
from fnixagent.core.llm.cache import ResponseCache
from fnixagent.core.llm.capability import (
    CapabilityRequirement,
    ModelCapability,
    ModelCapabilityFlag,
)
from fnixagent.core.llm.circuit import CircuitBreaker
from fnixagent.core.llm.limiter import TokenBucketRateLimiter
from fnixagent.core.llm.router import LLMRouter, RouterStats

__all__ = [
    "BaseLLMProvider",
    "LLMRequest",
    "LLMRouter",
    "RouterStats",
    "CircuitBreaker",
    "ResponseCache",
    "TokenBucketRateLimiter",
    "BillingMeter",
    # P2-8: 模型能力
    "ModelCapability",
    "ModelCapabilityFlag",
    "CapabilityRequirement",
]
