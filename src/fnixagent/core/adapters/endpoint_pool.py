"""
端点连接池 (Endpoint Pool) — P1-01。

灵感来自 zhua 项目的 proxy_pool.py,为外部服务端点(search / crawler 等)提供
统一的连接健康管理、故障恢复与负载均衡。

核心能力:
  1. 多端点注册: 支持添加/移除外部服务端点,每个端点独立维护运行时统计
  2. 健康管理: 失败冷却(短期)+ 连续故障隔离(长期),成功自动恢复
  3. 负载均衡: 轮询(加权) / 随机 / 粘性会话 三种选择策略
  4. 线程安全: 所有状态变更通过 threading.Lock 保护

健康管理策略:
  - 单次失败: 冷却 cooldown_seconds 秒(默认 60s),期间不被选中
  - 连续失败达 isolation_threshold 次: 长期隔离 isolation_seconds 秒(默认 600s)
  - 成功调用: 重置连续失败计数,清除冷却/隔离标记
  - is_available 属性实时判定: 冷却且未隔离时才可用

选择策略:
  - ROUND_ROBIN: 平滑加权轮询(nginx 风格 SWRR),按 weight 分配
  - RANDOM: 加权随机选择
  - STICKY: 同一 sticky_key 优先绑定到上次使用的端点(粘性会话)

依赖: 仅标准库(threading / time / random / logging / dataclasses / enum),零新增依赖。
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构
# ============================================================================


class EndpointStrategy(str, Enum):
    """端点选择策略。"""

    ROUND_ROBIN = "round_robin"  # 加权轮询
    RANDOM = "random"  # 加权随机
    STICKY = "sticky"  # 粘性会话(同一 key 优先同一端点)


@dataclass
class Endpoint:
    """端点定义。

    Attributes:
        name: 端点名称(唯一标识)。
        base_url: 基础 URL。
        weight: 权重(轮询/随机时影响选中概率),必须为正。
        max_concurrent: 最大并发数(预留字段,当前版本未强制限制)。
        timeout: 调用超时秒数。
    """

    name: str
    base_url: str
    weight: int = 1
    max_concurrent: int = 10
    timeout: float = 30.0


@dataclass
class EndpointStats:
    """端点运行时统计。

    Attributes:
        name: 端点名称。
        total_requests: 总请求数。
        success_count: 成功次数。
        failure_count: 失败次数。
        consecutive_failures: 连续失败次数(成功时归零)。
        cooldown_until: 冷却结束时间戳(monotonic),0 表示可用。
        isolated_until: 长期隔离结束时间戳(monotonic),0 表示未隔离。
        sticky_key: 粘性会话绑定的 key(仅 STICKY 策略下使用)。
        last_used: 最近一次被选中的时间戳(monotonic)。
        avg_latency_ms: 平均延迟(毫秒),增量平均。
    """

    name: str
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    isolated_until: float = 0.0
    sticky_key: str = ""
    last_used: float = 0.0
    avg_latency_ms: float = 0.0

    @property
    def is_available(self) -> bool:
        """是否可用(未冷却且未隔离)。"""
        now = time.monotonic()
        return self.cooldown_until <= now and self.isolated_until <= now

    @property
    def success_rate(self) -> float:
        """成功率,无调用记录时返回 1.0(视为健康)。"""
        if self.total_requests == 0:
            return 1.0
        return self.success_count / self.total_requests


# ============================================================================
# 端点连接池
# ============================================================================


class EndpointPool:
    """端点连接池 — 健康管理、故障恢复、负载均衡。

    三种选择策略:
        1. ROUND_ROBIN: 加权轮询可用端点(平滑加权轮询,nginx 风格)
        2. RANDOM: 加权随机选择可用端点
        3. STICKY: 同一 sticky_key 优先使用上次绑定的端点

    健康管理:
        - 失败 1 次: 冷却 cooldown_seconds 秒
        - 连续失败达 isolation_threshold 次: 长期隔离 isolation_seconds 秒
        - 成功: 重置连续失败计数,清除冷却/隔离
        - is_available 属性实时判定

    线程安全: threading.Lock 保护所有状态变更,避免并发 check-then-act 竞态。

    用法::

        pool = EndpointPool(strategy=EndpointStrategy.ROUND_ROBIN)
        pool.add_endpoint(Endpoint(name="a", base_url="http://a", weight=2))
        pool.add_endpoint(Endpoint(name="b", base_url="http://b", weight=1))
        ep = pool.get_endpoint()
        try:
            ...  # 调用 ep
            pool.record_success(ep.name, latency_ms=120.0)
        except Exception:
            pool.record_failure(ep.name)
    """

    def __init__(
        self,
        strategy: EndpointStrategy = EndpointStrategy.ROUND_ROBIN,
        cooldown_seconds: float = 60.0,
        isolation_threshold: int = 3,
        isolation_seconds: float = 600.0,
    ):
        """初始化端点池。

        Args:
            strategy: 选择策略,默认轮询。
            cooldown_seconds: 单次失败冷却秒数,必须为正。
            isolation_threshold: 触发长期隔离的连续失败次数,必须为正整数。
            isolation_seconds: 长期隔离秒数,必须为正。

        Raises:
            TypeError: 参数类型错误。
            ValueError: 参数非正数。
        """
        if not isinstance(strategy, EndpointStrategy):
            raise TypeError(f"strategy must be EndpointStrategy, got {type(strategy).__name__}")
        if isinstance(cooldown_seconds, bool) or not isinstance(cooldown_seconds, (int, float)):
            raise TypeError(
                f"cooldown_seconds must be numeric, got {type(cooldown_seconds).__name__}"
            )
        if isinstance(isolation_threshold, bool) or not isinstance(isolation_threshold, int):
            raise TypeError(
                f"isolation_threshold must be int, got {type(isolation_threshold).__name__}"
            )
        if isinstance(isolation_seconds, bool) or not isinstance(isolation_seconds, (int, float)):
            raise TypeError(
                f"isolation_seconds must be numeric, got {type(isolation_seconds).__name__}"
            )
        if cooldown_seconds <= 0:
            raise ValueError(f"cooldown_seconds must be positive, got {cooldown_seconds}")
        if isolation_threshold <= 0:
            raise ValueError(f"isolation_threshold must be positive, got {isolation_threshold}")
        if isolation_seconds <= 0:
            raise ValueError(f"isolation_seconds must be positive, got {isolation_seconds}")

        self._strategy = strategy
        self._cooldown_seconds = float(cooldown_seconds)
        self._isolation_threshold = isolation_threshold
        self._isolation_seconds = float(isolation_seconds)
        self._endpoints: dict[str, Endpoint] = {}
        self._stats: dict[str, EndpointStats] = {}
        self._sticky_map: dict[str, str] = {}  # sticky_key -> endpoint_name
        self._rr_weights: dict[str, int] = {}  # SWRR 动态权重(current_weight)
        self._lock = threading.Lock()

    # -- 注册 --------------------------------------------------------------

    def add_endpoint(self, endpoint: Endpoint) -> None:
        """添加一个端点到池中。

        Args:
            endpoint: 端点定义。

        Raises:
            TypeError: endpoint 不是 Endpoint 实例。
            ValueError: name 已存在,或 name/base_url 为空,或 weight/max_concurrent/timeout 非正。
        """
        if not isinstance(endpoint, Endpoint):
            raise TypeError(f"endpoint must be Endpoint, got {type(endpoint).__name__}")
        if not endpoint.name:
            raise ValueError("endpoint.name must be non-empty")
        if not endpoint.base_url:
            raise ValueError("endpoint.base_url must be non-empty")
        if endpoint.weight <= 0:
            raise ValueError(f"endpoint.weight must be positive, got {endpoint.weight}")
        if endpoint.max_concurrent <= 0:
            raise ValueError(
                f"endpoint.max_concurrent must be positive, got {endpoint.max_concurrent}"
            )
        if endpoint.timeout <= 0:
            raise ValueError(f"endpoint.timeout must be positive, got {endpoint.timeout}")
        with self._lock:
            if endpoint.name in self._endpoints:
                raise ValueError(f"endpoint '{endpoint.name}' already exists")
            self._endpoints[endpoint.name] = endpoint
            self._stats[endpoint.name] = EndpointStats(name=endpoint.name)
            self._rr_weights[endpoint.name] = 0
            logger.info(
                "已添加端点: name=%s base_url=%s weight=%d",
                endpoint.name,
                endpoint.base_url,
                endpoint.weight,
            )

    def remove_endpoint(self, name: str) -> bool:
        """移除一个端点。

        Args:
            name: 端点名称。

        Returns:
            bool: 移除成功返回 True,不存在返回 False。
        """
        with self._lock:
            if name not in self._endpoints:
                return False
            del self._endpoints[name]
            del self._stats[name]
            self._rr_weights.pop(name, None)
            # 清理指向该端点的粘性会话绑定
            self._sticky_map = {k: v for k, v in self._sticky_map.items() if v != name}
            logger.info("已移除端点: name=%s", name)
            return True

    # -- 选择 --------------------------------------------------------------

    def get_endpoint(self, sticky_key: str = "") -> Endpoint | None:
        """获取一个可用端点。

        Args:
            sticky_key: 粘性会话 key(STICKY 策略时使用,同一 key 优先同一端点)。

        Returns:
            可用端点;无可用端点时返回 None。
        """
        with self._lock:
            available: list[tuple[Endpoint, EndpointStats]] = [
                (ep, self._stats[name])
                for name, ep in self._endpoints.items()
                if self._stats[name].is_available
            ]
            if not available:
                logger.warning("无可用端点(共注册 %d 个)", len(self._endpoints))
                return None

            # STICKY: 优先返回上次绑定的端点
            if self._strategy == EndpointStrategy.STICKY and sticky_key:
                bound = self._sticky_map.get(sticky_key)
                if bound and bound in self._endpoints:
                    stats = self._stats[bound]
                    if stats.is_available:
                        stats.last_used = time.monotonic()
                        return self._endpoints[bound]
                # 绑定端点不存在或不可用 → 重新选择并更新绑定

            chosen = self._pick(available)
            if chosen is None:
                return None
            ep, stats = chosen
            stats.last_used = time.monotonic()

            # STICKY: 乐观更新绑定(后续失败会通过冷却自动切换)
            if self._strategy == EndpointStrategy.STICKY and sticky_key:
                self._sticky_map[sticky_key] = ep.name
                stats.sticky_key = sticky_key

            return ep

    def _pick(
        self, available: list[tuple[Endpoint, EndpointStats]]
    ) -> tuple[Endpoint, EndpointStats] | None:
        """按策略选择端点(调用者需持锁)。"""
        if self._strategy == EndpointStrategy.RANDOM:
            return self._pick_random(available)
        # ROUND_ROBIN / STICKY(STICKY 回退到轮询)
        return self._pick_round_robin(available)

    def _pick_round_robin(
        self, available: list[tuple[Endpoint, EndpointStats]]
    ) -> tuple[Endpoint, EndpointStats] | None:
        """平滑加权轮询(Smooth Weighted Round-Robin,nginx 风格)。

        算法:
          1. 每个端点 current_weight += weight
          2. 选 current_weight 最大的
          3. 被选中的 current_weight -= 总 weight

        优点: 分布平滑、不集中,对动态增删端点鲁棒。
        调用者需持锁。
        """
        total_weight = 0
        best: tuple[Endpoint, EndpointStats] | None = None
        best_cw = 0
        for ep, stats in available:
            cw = self._rr_weights.get(ep.name, 0) + ep.weight
            self._rr_weights[ep.name] = cw
            total_weight += ep.weight
            if best is None or cw > best_cw:
                best_cw = cw
                best = (ep, stats)
        if best is not None:
            self._rr_weights[best[0].name] -= total_weight
        return best

    def _pick_random(
        self, available: list[tuple[Endpoint, EndpointStats]]
    ) -> tuple[Endpoint, EndpointStats]:
        """加权随机选择。调用者需持锁。"""
        weights = [ep.weight for ep, _ in available]
        idx = random.choices(range(len(available)), weights=weights, k=1)[0]
        return available[idx]

    # -- 事件记录 ----------------------------------------------------------

    def record_success(self, name: str, latency_ms: float = 0.0) -> None:
        """记录一次成功调用。

        - total_requests / success_count += 1
        - consecutive_failures 归零
        - 清除 cooldown_until / isolated_until
        - 更新 avg_latency_ms(增量平均)

        Args:
            name: 端点名称。
            latency_ms: 本次调用延迟(毫秒),<=0 时不更新平均延迟。
        """
        with self._lock:
            stats = self._stats.get(name)
            if stats is None:
                logger.warning("record_success: 端点 '%s' 不存在", name)
                return
            stats.total_requests += 1
            stats.success_count += 1
            stats.consecutive_failures = 0
            stats.cooldown_until = 0.0
            stats.isolated_until = 0.0
            if latency_ms > 0:
                # 增量平均: new_avg = old_avg + (value - old_avg) / count
                stats.avg_latency_ms = (
                    stats.avg_latency_ms + (latency_ms - stats.avg_latency_ms) / stats.success_count
                )

    def record_failure(self, name: str) -> None:
        """记录一次失败调用。

        - total_requests / failure_count / consecutive_failures += 1
        - 达到 isolation_threshold: 设置 isolated_until(长期隔离)
        - 否则: 设置 cooldown_until(短期冷却)

        Args:
            name: 端点名称。
        """
        with self._lock:
            stats = self._stats.get(name)
            if stats is None:
                logger.warning("record_failure: 端点 '%s' 不存在", name)
                return
            stats.total_requests += 1
            stats.failure_count += 1
            stats.consecutive_failures += 1
            now = time.monotonic()
            if stats.consecutive_failures >= self._isolation_threshold:
                stats.isolated_until = now + self._isolation_seconds
                logger.warning(
                    "端点 '%s' 连续失败 %d 次(阈值 %d),隔离 %.0f 秒",
                    name,
                    stats.consecutive_failures,
                    self._isolation_threshold,
                    self._isolation_seconds,
                )
            else:
                stats.cooldown_until = now + self._cooldown_seconds
                logger.info(
                    "端点 '%s' 失败(连续 %d 次),冷却 %.0f 秒",
                    name,
                    stats.consecutive_failures,
                    self._cooldown_seconds,
                )

    # -- 统计与运维 --------------------------------------------------------

    def get_stats(self) -> dict[str, dict[str, Any]]:
        """返回所有端点统计(线程安全快照)。"""
        with self._lock:
            return {
                name: {
                    "total_requests": stats.total_requests,
                    "success_count": stats.success_count,
                    "failure_count": stats.failure_count,
                    "consecutive_failures": stats.consecutive_failures,
                    "is_available": stats.is_available,
                    "success_rate": round(stats.success_rate, 4),
                    "avg_latency_ms": round(stats.avg_latency_ms, 2),
                    "cooldown_until": stats.cooldown_until,
                    "isolated_until": stats.isolated_until,
                    "last_used": stats.last_used,
                    "sticky_key": stats.sticky_key,
                }
                for name, stats in self._stats.items()
            }

    def health_check(self) -> dict[str, bool]:
        """返回各端点健康状态(是否可用)。"""
        with self._lock:
            return {name: stats.is_available for name, stats in self._stats.items()}

    def reset(self) -> None:
        """重置所有统计(保留端点定义,清空运行时统计与粘性绑定)。"""
        with self._lock:
            for name in self._stats:
                self._stats[name] = EndpointStats(name=name)
                self._rr_weights[name] = 0
            self._sticky_map.clear()
            logger.info("端点池统计已重置(%d 个端点)", len(self._stats))

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"<EndpointPool strategy={self._strategy.value} endpoints={len(self._endpoints)}>"
            )


# ============================================================================
# 模块级单例(double-checked locking)
# ============================================================================

_default_pool: EndpointPool | None = None
_default_lock = threading.Lock()


def get_endpoint_pool() -> EndpointPool:
    """获取全局默认端点池(惰性单例,线程安全,默认参数)。

    首次调用时创建;后续调用返回同一实例。
    使用 double-checked locking 保证多线程下只创建一个实例。
    测试场景可用 ``reset_endpoint_pool()`` 重建。
    """
    global _default_pool
    if _default_pool is None:
        with _default_lock:
            if _default_pool is None:
                _default_pool = EndpointPool()
    return _default_pool


def reset_endpoint_pool() -> None:
    """重置全局默认端点池单例(释放引用,下次 ``get_endpoint_pool`` 重建)。

    如需清空运行时状态而非重建实例,请对 ``get_endpoint_pool()`` 调用 ``reset()``。
    """
    global _default_pool
    with _default_lock:
        _default_pool = None
