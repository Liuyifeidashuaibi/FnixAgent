"""治理层 (Governance) — 流量治理与限流。

P0-02: 提供网关级多层令牌桶限流器(全局 + 按用户 + 按工具),含自适应退避、
按用户并发信号量与端点规则。与 core.llm.limiter(单层 LLM 限流)互补:
本模块面向跨 LLM/工具/上游 API 的整体流量治理。
"""

from fnixagent.core.governance.limiter import (
    DomainState,
    EndpointRule,
    MultiLayerRateLimiter,
    TokenBucket,
    get_limiter,
    reset_limiter,
)

__all__ = [
    "DomainState",
    "EndpointRule",
    "MultiLayerRateLimiter",
    "TokenBucket",
    "get_limiter",
    "reset_limiter",
]
