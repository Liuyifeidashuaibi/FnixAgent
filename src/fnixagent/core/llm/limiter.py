"""
令牌桶限流器 (Token Bucket Rate Limiter)。

算法原理:
  令牌桶以固定速率(refill_rate)补充令牌,桶容量为 capacity。
  每次请求消耗 N 个令牌;桶空时拒绝或等待。
  惰性补充: 不用定时线程,在每次 acquire 时根据时间差一次性补齐,
  既精确又无后台开销。

适用场景: LLM API 调用限流,按 user/tenant 隔离。

注意: 本限流器面向 LLM 层单 key 限流(per API key / per tenant)。
若需网关级多层限流(全局 + 按用户 + 按工具 + 自适应退避 + 按用户并发信号量),
请改用 ``fnixagent.core.governance.limiter.MultiLayerRateLimiter``
(或 ``from fnixagent.core.governance import get_limiter`` 获取默认单例)。
两者互补: 本类专注 LLM per-key 限流,治理层专注跨 LLM/工具/上游 API 的整体流量治理。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

@dataclass
class _Bucket:
    """单个限流桶的内部状态。"""

    tokens: float  # 当前令牌数
    capacity: float  # 桶容量
    refill_rate: float  # 每秒补充令牌数
    last_refill: float  # 上次补充的时间戳(monotonic)

    def _refill(self, now: float) -> None:
        """惰性补充: 根据距上次的时间差一次性补齐,不超过容量。"""
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

class TokenBucketRateLimiter:
    """多 key 令牌桶限流器。

    每个 key(user_id / tenant_id)拥有独立的桶,互不影响,实现按用户隔离限流。

    线程安全: 令牌补充与扣减均在 self._lock 内原子完成,避免并发 check-then-act
    导致的超扣(两个线程同时看到 tokens 充足并各自扣减)。

    Attributes:
        _default_capacity: 默认桶容量(同时是初始令牌数)。
        _default_rate: 默认每秒补充令牌数。
        _buckets: key → _Bucket 映射。
    """

    def __init__(
        self,
        capacity: int = 60,
        refill_per_sec: float = 10.0,
    ):
        """初始化限流器。

        Args:
            capacity: 桶容量(初始令牌数),必须为正。
            refill_per_sec: 每秒补充令牌数,必须为正。

        Raises:
            TypeError: 参数类型错误。
            ValueError: 参数非正数。
        """
        if isinstance(capacity, bool) or not isinstance(capacity, (int, float)):
            raise TypeError(f"capacity must be numeric, got {type(capacity).__name__}")
        if isinstance(refill_per_sec, bool) or not isinstance(refill_per_sec, (int, float)):
            raise TypeError(f"refill_per_sec must be numeric, got {type(refill_per_sec).__name__}")
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")
        if refill_per_sec <= 0:
            raise ValueError(f"refill_per_sec must be positive, got {refill_per_sec}")
        self._default_capacity = float(capacity)
        self._default_rate = refill_per_sec
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> _Bucket:
        """获取或创建指定 key 的桶。调用者需持锁。"""
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(
                tokens=self._default_capacity,
                capacity=self._default_capacity,
                refill_rate=self._default_rate,
                last_refill=time.monotonic(),
            )
            self._buckets[key] = b
        return b

    def acquire(self, key: str, tokens: float = 1.0) -> bool:
        """非阻塞尝试获取令牌。

        采用惰性补充:先按时间差补齐令牌(不超过容量),再判断是否足够扣除。
        补充与扣减在同一锁内,保证原子性,O(1) 复杂度。

        Args:
            key: 限流键(通常为 user_id / tenant_id)。
            tokens: 本次请求所需令牌数,必须为正。

        Returns:
            bool: 成功扣除返回 True,令牌不足返回 False。

        Raises:
            TypeError: tokens 不是数值。
            ValueError: tokens 非正数。
        """
        if isinstance(tokens, bool) or not isinstance(tokens, (int, float)):
            raise TypeError(f"tokens must be numeric, got {type(tokens).__name__}")
        if tokens <= 0:
            raise ValueError(f"tokens must be positive, got {tokens}")
        with self._lock:
            b = self._get_bucket(key)
            now = time.monotonic()
            # P1-06: Rust 加速预留点。
            # 高并发场景下,可将下方 refill + check + 扣减替换为
            # fnixagent.core.rust_ext.probe.try_rust_token_bucket_check(
            #     tokens=b.tokens, capacity=b.capacity, rate=b.refill_rate,
            #     last_refill=b.last_refill, now=now,
            #     python_fallback=<current pure-python logic>,
            # )
            # 当前保持纯 Python 实现,以保证零额外依赖与行为一致。
            b._refill(now)
            if b.tokens >= tokens:
                b.tokens -= tokens
                return True
            # Phase 2.10: 记录限流触发指标
            try:
                from fnixagent.core.observability.metrics import record_rate_limit_triggered

                record_rate_limit_triggered(limiter_type="llm")
            except Exception:
                pass
            return False

    def try_acquire(self, key: str, tokens: float = 1.0) -> bool:
        """acquire 的语义别名,显式表达"非阻塞尝试"。"""
        return self.acquire(key, tokens)

    def wait_and_acquire(self, key: str, tokens: float = 1.0, timeout: float = 30.0) -> bool:
        """阻塞等待直到获取令牌或超时。

        采用短轮询 + 自适应间隔:根据令牌缺口与补充速率估算等待时长,
        避免精确 sleep 导致的偏差,同时不至于过度轮询浪费 CPU。

        Args:
            key: 限流键。
            tokens: 所需令牌数,必须为正。
            timeout: 最大等待秒数,必须为正。

        Returns:
            bool: 成功获取返回 True,超时返回 False。
        """
        deadline = time.monotonic() + timeout
        while True:
            if self.acquire(key, tokens):
                return True
            if time.monotonic() >= deadline:
                return False
            # 计算还需等待多久才能凑够令牌
            with self._lock:
                b = self._get_bucket(key)
                now = time.monotonic()
                b._refill(now)
                deficit = tokens - b.tokens
                if self._default_rate > 0:
                    wait = deficit / self._default_rate
                else:
                    wait = 0.1
            wait = max(0.01, min(wait, 0.5))
            time.sleep(wait)

    def get_available(self, key: str) -> float:
        """查看当前可用令牌数(不消耗,会先惰性补充)。"""
        with self._lock:
            b = self._get_bucket(key)
            b._refill(time.monotonic())
            return b.tokens

    def reset(self, key: str | None = None) -> None:
        """重置指定 key 或全部 key 的桶。"""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)

    def stats(self) -> dict:
        """返回限流器统计信息(线程安全快照)。"""
        with self._lock:
            return {
                "total_keys": len(self._buckets),
                "capacity": self._default_capacity,
                "refill_rate": self._default_rate,
                "keys": {
                    key: {
                        "available_tokens": round(b.tokens, 2),
                        "capacity": b.capacity,
                    }
                    for key, b in self._buckets.items()
                },
            }

# 向后兼容别名:对外提供 RateLimiter 简称,与 TokenBucketRateLimiter 等价
RateLimiter = TokenBucketRateLimiter
