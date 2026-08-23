"""
认证端点速率限制器 (Auth Rate Limiter)。

滑动窗口内存限流，防止暴力破解与撞库攻击。
不引入外部依赖，适合 standalone / 单实例部署；多实例场景可替换为 Redis 后端。

限制策略:
    - 每 IP 每 60 秒最多 10 次认证请求 (login / register / sms_login 等)
    - 超限时返回 429 Too Many Requests
    - 窗口自动滑过，无需手动解锁
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

# 默认限制参数
_DEFAULT_WINDOW_SECONDS = 60
_DEFAULT_MAX_ATTEMPTS = 10

# 全局限流状态 (进程内单例)
_buckets: dict[str, list[float]] = defaultdict(list)
_lock = Lock()


def check_rate_limit(
    key: str,
    *,
    window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
) -> tuple[bool, int]:
    """检查滑动窗口速率限制。

    Args:
        key: 限流键 (通常为 IP 地址或 username + IP)
        window_seconds: 时间窗口 (秒)
        max_attempts: 窗口内最大允许次数

    Returns:
        (allowed, retry_after_seconds)
        - allowed=True 表示放行
        - allowed=False 表示被限流，retry_after 为建议重试等待秒数
    """
    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        bucket = _buckets[key]
        # 移除过期条目 (滑动窗口)
        while bucket and bucket[0] < cutoff:
            bucket.pop(0)

        if len(bucket) >= max_attempts:
            # 计算最早条目的剩余等待时间
            oldest = bucket[0] if bucket else now
            retry_after = max(1, int(oldest + window_seconds - now))
            return False, retry_after

        bucket.append(now)
        return True, 0


def reset_key(key: str) -> None:
    """重置指定键的限流 (登录成功后可调用以清零计数)。"""
    with _lock:
        _buckets.pop(key, None)


def get_stats() -> dict:
    """返回当前限流器统计信息 (用于监控)。"""
    with _lock:
        return {
            "tracked_keys": len(_buckets),
            "total_entries": sum(len(v) for v in _buckets.values()),
        }
