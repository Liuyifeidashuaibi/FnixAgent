"""核心适配器 — 外部服务端点管理。

P1-01: 提供端点连接池(EndpointPool),用于管理外部服务端点(search / crawler 等)
的健康检查、故障恢复与负载均衡。灵感来自 zhua 项目的 proxy_pool.py。

三种选择策略: 轮询(加权) / 随机 / 粘性会话。
健康管理: 失败冷却(短期)+ 连续故障隔离(长期),成功自动恢复。
线程安全: threading.Lock 保护所有状态变更。
"""

from fnixagent.core.adapters.endpoint_pool import (
    Endpoint,
    EndpointPool,
    EndpointStats,
    EndpointStrategy,
    get_endpoint_pool,
    reset_endpoint_pool,
)

__all__ = [
    "Endpoint",
    "EndpointPool",
    "EndpointStats",
    "EndpointStrategy",
    "get_endpoint_pool",
    "reset_endpoint_pool",
]
