"""
多层令牌桶限流器 (Multi-Layer Token Bucket Rate Limiter) — P0-02。

治理级限流,灵感来自 zhua 项目的 ratelimit.py。与 core.llm.rate_limiter 的单层
LLM 限流器不同,本模块面向网关级流量治理,提供三层隔离:

  1. 全局 QPS 桶  — 保护整体吞吐,默认 50 QPS
  2. 按用户 QPS 桶 — per user_id 惰性创建,默认 10 QPS/用户
  3. 按工具 QPS 桶 — per tool_name 惰性创建,默认 5 QPS/工具

并具备:
  - 自适应退避: 429/503 指数回退(QPS 减半,下限 0.1),成功逐步恢复(QPS *1.25,
    上限为默认 QPS)
  - 按用户并发信号量: 用户间互不阻塞,默认并发 5;可选全局并发上限
  - 端点规则: 按 URL/工具名前缀(最长前缀优先)覆盖 QPS/并发/最小调用间隔
  - 同步 acquire() 与异步 wait() 双 API

线程安全: 桶状态读写通过 threading.Lock 保护(与 core.llm.rate_limiter 一致),
使同步 acquire() 与异步 wait() 内部均可安全操作;异步 wait() 的等待段使用
asyncio.sleep,不阻塞事件循环。

依赖: 仅标准库(asyncio / logging / time / dataclasses / threading),零新增依赖。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# 数据结构
# ============================================================================


@dataclass
class TokenBucket:
    """令牌桶。

    惰性补充: 不用定时线程,在每次 refill/try_take 时按时间差一次性补齐,
    既精确又无后台开销。

    Attributes:
        capacity: 桶容量(最大令牌数,即突发上限)。
        rate: 每秒补充令牌数(稳态 QPS)。
        tokens: 当前令牌数。
        last_refill: 上次补充时间戳(monotonic)。
    """

    capacity: float
    rate: float
    tokens: float = 0.0
    last_refill: float = field(default_factory=time.monotonic)

    def refill(self, now: float) -> None:
        """惰性补充: 按时间差一次性补齐,不超过容量。"""
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now

    def try_take(self, now: float, n: float = 1.0) -> bool:
        """尝试扣减 n 个令牌;成功返回 True,不足返回 False(不扣减)。"""
        self.refill(now)
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def time_until(self, now: float, n: float = 1.0) -> float:
        """还需多少秒才能凑够 n 个令牌;已够返回 0.0,rate<=0 返回 inf。"""
        self.refill(now)
        if self.tokens >= n:
            return 0.0
        if self.rate <= 0:
            return float("inf")
        return (n - self.tokens) / self.rate


@dataclass
class EndpointRule:
    """per-endpoint 差异化限速规则。

    按 URL/工具名前缀匹配(最长前缀优先),可覆盖 QPS、并发与最小调用间隔。
    任一字段为 None 表示该维度沿用默认值。

    Attributes:
        prefix: URL 或工具名前缀。
        qps: 该端点专属 QPS(None 表示沿用默认)。
        concurrency: 该端点并发上限(None 表示沿用默认)。
        min_interval: 最小调用间隔(秒,None 表示不限制)。
    """

    prefix: str
    qps: Optional[float] = None
    concurrency: Optional[int] = None
    min_interval: Optional[float] = None


@dataclass
class DomainState:
    """per-domain 运行时状态(自适应退避 + 最小间隔)。

    包装一个令牌桶并记录其默认上限(用于自适应恢复的上界)与上次调用时间
    (用于端点规则的 min_interval 间隔控制)。

    Attributes:
        bucket: 关联的令牌桶。
        default_rate: 默认 QPS(自适应恢复上限)。
        default_capacity: 默认容量(自适应恢复上限)。
        last_call: 上次成功调用时间戳(monotonic),用于 min_interval。
    """

    bucket: TokenBucket
    default_rate: float
    default_capacity: float
    last_call: float = 0.0


# ============================================================================
# 多层限流器
# ============================================================================


class MultiLayerRateLimiter:
    """多层令牌桶限流器(全局 + 按用户 + 按工具)。

    三层桶串联: 请求需同时通过全局、用户、工具三道令牌桶扣减才被放行。
    各层桶独立补充、独立限速,实现"整体保护 + 用户隔离 + 工具隔离"。

    线程安全: 所有桶状态读写均在 self._lock 内完成。异步 wait() 仅在等待段
    释放锁并使用 asyncio.sleep,不阻塞事件循环。

    Attributes:
        _global_bucket: 全局 QPS 桶。
        _user_states: user_id -> DomainState(惰性创建)。
        _tool_states: tool_name -> DomainState(惰性创建)。
        _user_sems: user_id -> asyncio.Semaphore(惰性创建)。
        _endpoint_rules: 按 prefix 长度降序排列的端点规则。
    """

    def __init__(
        self,
        global_qps: float = 50.0,
        default_user_qps: float = 10.0,
        default_tool_qps: float = 5.0,
        default_user_concurrency: int = 5,
        global_concurrency: Optional[int] = None,
        endpoint_rules: Optional[list[EndpointRule]] = None,
    ):
        """初始化多层限流器。

        Args:
            global_qps: 全局 QPS,必须为正。
            default_user_qps: 默认每用户 QPS,必须为正。
            default_tool_qps: 默认每工具 QPS,必须为正。
            default_user_concurrency: 默认每用户并发数,必须为正整数。
            global_concurrency: 可选全局并发上限(None 表示不限)。
            endpoint_rules: 初始端点规则列表。

        Raises:
            ValueError: 任一 QPS/并发参数非正。
        """
        if global_qps <= 0:
            raise ValueError(f"global_qps must be positive, got {global_qps}")
        if default_user_qps <= 0:
            raise ValueError(f"default_user_qps must be positive, got {default_user_qps}")
        if default_tool_qps <= 0:
            raise ValueError(f"default_tool_qps must be positive, got {default_tool_qps}")
        if default_user_concurrency <= 0:
            raise ValueError(
                f"default_user_concurrency must be positive, got {default_user_concurrency}"
            )
        if global_concurrency is not None and global_concurrency <= 0:
            raise ValueError(f"global_concurrency must be positive, got {global_concurrency}")

        self._global_qps = float(global_qps)
        self._default_user_qps = float(default_user_qps)
        self._default_tool_qps = float(default_tool_qps)
        self._default_user_concurrency = default_user_concurrency
        self._global_concurrency_value = global_concurrency

        self._global_bucket = TokenBucket(
            capacity=self._global_qps, rate=self._global_qps, tokens=self._global_qps
        )
        self._user_states: dict[str, DomainState] = {}
        self._tool_states: dict[str, DomainState] = {}
        self._user_sems: dict[str, asyncio.Semaphore] = {}
        self._global_sem: Optional[asyncio.Semaphore] = (
            asyncio.Semaphore(global_concurrency) if global_concurrency is not None else None
        )

        self._endpoint_rules: list[EndpointRule] = []
        if endpoint_rules:
            self._endpoint_rules.extend(endpoint_rules)
        self._sort_rules()

        self._lock = threading.Lock()

    # ----------------------------------------------------------------------
    # 端点规则
    # ----------------------------------------------------------------------
    def _sort_rules(self) -> None:
        """按 prefix 长度降序排列(最长前缀优先匹配)。调用者需持锁。"""
        self._endpoint_rules.sort(key=lambda r: len(r.prefix), reverse=True)

    def _match_rule(self, name: str) -> Optional[EndpointRule]:
        """返回与 name 最长前缀匹配的规则,无匹配返回 None。调用者需持锁。"""
        for rule in self._endpoint_rules:
            if rule.prefix and name.startswith(rule.prefix):
                return rule
        return None

    def add_endpoint_rule(self, rule: EndpointRule) -> None:
        """运行时新增端点规则(自动重排序,线程安全)。

        注意: 规则仅对新增后惰性创建的工具桶生效;已存在的工具桶保持其创建时
        的 QPS 不变(避免在线流量被瞬时打断)。
        """
        with self._lock:
            self._endpoint_rules.append(rule)
            self._sort_rules()
        logger.info(
            "新增端点限速规则: prefix=%s qps=%s concurrency=%s min_interval=%s",
            rule.prefix,
            rule.qps,
            rule.concurrency,
            rule.min_interval,
        )

    def remove_endpoint_rule(self, prefix: str) -> Optional[EndpointRule]:
        """按 prefix 移除端点规则(线程安全,P2-03 热更新支持)。

        仅移除首个 prefix 完全相等的规则(不做前缀匹配,避免误删)。

        Args:
            prefix: 要移除的规则 prefix(精确匹配)

        Returns:
            被移除的 EndpointRule;不存在时返回 None
        """
        with self._lock:
            for i, rule in enumerate(self._endpoint_rules):
                if rule.prefix == prefix:
                    removed = self._endpoint_rules.pop(i)
                    self._sort_rules()
                    logger.info("移除端点限速规则: prefix=%s", prefix)
                    return removed
        return None

    def list_endpoint_rules(self) -> list[EndpointRule]:
        """返回当前端点规则的快照(线程安全,P2-03 热更新支持)。"""
        with self._lock:
            return list(self._endpoint_rules)

    # ----------------------------------------------------------------------
    # 惰性创建
    # ----------------------------------------------------------------------
    def _get_user_state(self, user_id: str, now: float) -> DomainState:
        """获取或创建用户 DomainState。调用者需持锁。"""
        st = self._user_states.get(user_id)
        if st is None:
            st = DomainState(
                bucket=TokenBucket(
                    capacity=self._default_user_qps,
                    rate=self._default_user_qps,
                    tokens=self._default_user_qps,
                ),
                default_rate=self._default_user_qps,
                default_capacity=self._default_user_qps,
                last_call=0.0,
            )
            self._user_states[user_id] = st
        return st

    def _get_tool_state(self, tool_name: str, now: float) -> DomainState:
        """获取或创建工具 DomainState(若匹配端点规则则用规则 QPS)。调用者需持锁。"""
        st = self._tool_states.get(tool_name)
        if st is None:
            rule = self._match_rule(tool_name)
            if rule is not None and rule.qps is not None:
                qps = float(rule.qps)
            else:
                qps = self._default_tool_qps
            st = DomainState(
                bucket=TokenBucket(capacity=qps, rate=qps, tokens=qps),
                default_rate=qps,
                default_capacity=qps,
                last_call=0.0,
            )
            self._tool_states[tool_name] = st
        return st

    # ----------------------------------------------------------------------
    # 核心: 扣减逻辑
    # ----------------------------------------------------------------------
    @staticmethod
    def _record_limit() -> None:
        """记录限流触发指标(observability 可选,失败静默)。"""
        try:
            from officeagent.core.observability.metrics import record_rate_limit_triggered

            record_rate_limit_triggered(limiter_type="governance")
        except Exception:
            pass

    def _acquire_locked(self, user_id: str, tool_name: str, now: float) -> bool:
        """核心扣减逻辑(调用者需持 self._lock)。

        三层串联: 最小间隔(工具层) -> 全局桶 -> 用户桶 -> 工具桶。
        任一层拒绝即返回 False(且已记录限流指标);全部通过则扣减并返回 True。

        Args:
            user_id: 用户标识。
            tool_name: 工具/端点名称(空串跳过工具层)。
            now: 当前 monotonic 时间戳。

        Returns:
            bool: 放行返回 True,限流返回 False。
        """
        # 1. 最小间隔检查(提前判断,避免无谓扣令牌)
        tool_st: Optional[DomainState] = None
        if tool_name:
            tool_st = self._get_tool_state(tool_name, now)
            rule = self._match_rule(tool_name)
            if rule is not None and rule.min_interval is not None:
                if now - tool_st.last_call < rule.min_interval:
                    self._record_limit()
                    return False

        # 2. 全局桶
        if not self._global_bucket.try_take(now, 1.0):
            self._record_limit()
            return False

        # 3. 用户桶
        user_st = self._get_user_state(user_id, now)
        if not user_st.bucket.try_take(now, 1.0):
            self._record_limit()
            return False

        # 4. 工具桶
        if tool_st is not None:
            if not tool_st.bucket.try_take(now, 1.0):
                self._record_limit()
                return False
            tool_st.last_call = now

        return True

    def acquire(self, user_id: str, tool_name: str = "") -> bool:
        """非阻塞尝试获取令牌(三层桶 + 最小间隔)。

        Args:
            user_id: 用户标识。
            tool_name: 工具/端点名称(可为空,空则跳过工具层)。

        Returns:
            bool: 三层均通过返回 True,任一层限流返回 False。
        """
        now = time.monotonic()
        with self._lock:
            return self._acquire_locked(user_id, tool_name, now)

    async def wait(self, user_id: str, tool_name: str = "") -> None:
        """阻塞(异步)等待直到放行。

        采用短轮询 + 自适应间隔: 失败时估算还需等待时长(取各层 time_until 与
        min_interval 余量的最大值),asyncio.sleep 后重试。等待段不持锁、不阻塞
        事件循环。
        """
        while True:
            now = time.monotonic()
            with self._lock:
                if self._acquire_locked(user_id, tool_name, now):
                    return
                wait_secs = self._estimate_wait_locked(user_id, tool_name, now)
            # 兜底: rate>0 时必为有限值;异常情况短睡避免死循环
            if wait_secs == float("inf"):
                wait_secs = 0.1
            # 限制单次睡眠区间: 不少于 5ms(避免忙循环),不超过 1s(及时重试)
            wait_secs = max(0.005, min(wait_secs, 1.0))
            await asyncio.sleep(wait_secs)

    def _estimate_wait_locked(self, user_id: str, tool_name: str, now: float) -> float:
        """估算还需等待多少秒(取各层最大值)。调用者需持锁。"""
        waits: list[float] = [self._global_bucket.time_until(now, 1.0)]

        user_st = self._user_states.get(user_id)
        if user_st is not None:
            waits.append(user_st.bucket.time_until(now, 1.0))

        if tool_name:
            tool_st = self._tool_states.get(tool_name)
            if tool_st is not None:
                waits.append(tool_st.bucket.time_until(now, 1.0))
                rule = self._match_rule(tool_name)
                if rule is not None and rule.min_interval is not None:
                    remaining = rule.min_interval - (now - tool_st.last_call)
                    if remaining > 0:
                        waits.append(remaining)

        return max(waits)

    # ----------------------------------------------------------------------
    # 并发信号量
    # ----------------------------------------------------------------------
    def semaphore(self, user_id: str) -> asyncio.Semaphore:
        """获取用户专属并发信号量(惰性创建,用户间互不阻塞)。

        典型用法::

            sem = limiter.semaphore(user_id)
            async with sem:
                ...  # 受并发限制的临界区

        每个用户独立信号量(默认并发 default_user_concurrency),不同用户互不阻塞。
        """
        with self._lock:
            sem = self._user_sems.get(user_id)
            if sem is None:
                sem = asyncio.Semaphore(self._default_user_concurrency)
                self._user_sems[user_id] = sem
            return sem

    def global_semaphore(self) -> Optional[asyncio.Semaphore]:
        """返回全局并发信号量(未配置全局并发上限时返回 None)。"""
        return self._global_sem

    # ----------------------------------------------------------------------
    # 自适应退避
    # ----------------------------------------------------------------------
    def update_on_status(self, user_id: str, status_code: int) -> bool:
        """根据响应状态码自适应调整用户桶 QPS。

        - 429/503: new_rate = max(rate * 0.5, 0.1)  — 指数回退
        - 2xx 成功: new_rate = min(rate * 1.25, default_rate)  — 逐步恢复
        - 其他状态码: 不调整

        调整时同步缩放桶容量(QPS 桶容量随速率变化),并裁剪当前令牌数不超容量。

        Args:
            user_id: 用户标识。
            status_code: 上游响应状态码。

        Returns:
            bool: QPS 发生变化返回 True,否则 False。
        """
        now = time.monotonic()
        with self._lock:
            st = self._get_user_state(user_id, now)
            b = st.bucket
            old_rate = b.rate

            if status_code in (429, 503):
                new_rate = max(b.rate * 0.5, 0.1)
                if new_rate < old_rate - 1e-9:
                    b.rate = new_rate
                    b.capacity = max(new_rate, 1.0)
                    b.tokens = min(b.tokens, b.capacity)
                    logger.warning(
                        "自适应退避: user=%s status=%s QPS %.4f -> %.4f",
                        user_id,
                        status_code,
                        old_rate,
                        new_rate,
                    )
                    return True
            elif 200 <= status_code < 300:
                new_rate = min(b.rate * 1.25, st.default_rate)
                if new_rate > old_rate + 1e-9:
                    b.rate = new_rate
                    b.capacity = max(new_rate, st.default_capacity)
                    # 容量恢复不主动增发令牌,由后续 refill 自然补齐
                    logger.info(
                        "自适应恢复: user=%s status=%s QPS %.4f -> %.4f",
                        user_id,
                        status_code,
                        old_rate,
                        new_rate,
                    )
                    return True
            return False

    # ----------------------------------------------------------------------
    # 监控 / 重置
    # ----------------------------------------------------------------------
    def get_stats(self) -> dict[str, dict[str, float]]:
        """返回所有桶的统计快照(线程安全)。

        Returns:
            形如 ``{"global": {...}, "user:<id>": {...}, "tool:<name>": {...}}``
            的映射,每项含 rate / capacity / tokens 等浮点字段。
        """
        now = time.monotonic()
        with self._lock:
            stats: dict[str, dict[str, float]] = {}

            self._global_bucket.refill(now)
            stats["global"] = {
                "rate": self._global_bucket.rate,
                "capacity": self._global_bucket.capacity,
                "tokens": round(self._global_bucket.tokens, 3),
            }

            for uid, st in self._user_states.items():
                st.bucket.refill(now)
                stats[f"user:{uid}"] = {
                    "rate": st.bucket.rate,
                    "capacity": st.bucket.capacity,
                    "tokens": round(st.bucket.tokens, 3),
                    "default_rate": st.default_rate,
                    "last_call": st.last_call,
                }

            for name, st in self._tool_states.items():
                st.bucket.refill(now)
                stats[f"tool:{name}"] = {
                    "rate": st.bucket.rate,
                    "capacity": st.bucket.capacity,
                    "tokens": round(st.bucket.tokens, 3),
                    "default_rate": st.default_rate,
                    "last_call": st.last_call,
                }

            return stats

    def reset(self) -> None:
        """重置所有限流运行时状态(桶、信号量清空;端点规则保留)。

        注意: 正被协程持有的信号量不会被强制释放,本方法主要用于测试与运维重置。
        """
        with self._lock:
            self._global_bucket = TokenBucket(
                capacity=self._global_qps, rate=self._global_qps, tokens=self._global_qps
            )
            self._user_states.clear()
            self._tool_states.clear()
            self._user_sems.clear()
            if self._global_concurrency_value is not None:
                self._global_sem = asyncio.Semaphore(self._global_concurrency_value)
            else:
                self._global_sem = None
        logger.info("多层限流器状态已重置(端点规则保留 %d 条)", len(self._endpoint_rules))


# ============================================================================
# 模块级单例
# ============================================================================

_default_limiter: Optional[MultiLayerRateLimiter] = None
_default_lock = threading.Lock()


def get_limiter() -> MultiLayerRateLimiter:
    """获取全局默认多层限流器(惰性单例,线程安全,默认参数)。"""
    global _default_limiter
    if _default_limiter is None:
        with _default_lock:
            if _default_limiter is None:
                _default_limiter = MultiLayerRateLimiter()
    return _default_limiter


def reset_limiter() -> None:
    """重置全局默认限流器单例(释放引用,下次 get_limiter 重建)。

    如需清空运行时状态而非重建实例,请对 ``get_limiter()`` 调用 ``reset()``。
    """
    global _default_limiter
    with _default_lock:
        _default_limiter = None
