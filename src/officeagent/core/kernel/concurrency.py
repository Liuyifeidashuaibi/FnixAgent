"""
并发原语与限流器 (Concurrency Primitives & Rate Limiters)
===========================================================
纯 Python + stdlib (threading) 实现,零外部依赖。

算法清单:
  TokenBucket       - 令牌桶限流 (平滑突发)
  SlidingWindow     - 滑动窗口限流 (严格速率)
  LeakyBucket        - 漏桶限流 (恒定速率)
  AtomicCounter      - 原子计数器 (线程安全)
  RWLock              - 读写锁 (多读单写, 避免写饥饿)
  Semaphore           - 计数信号量 (条件变量实现)
  Barrier             - 同步屏障 (多线程会合)
  CancellationToken  - 取消令牌 (协作式取消)
  Debouncer           - 消抖器 (高频事件降频)
  RateLimiter         - 统一限流接口 (多策略组合)
"""
from __future__ import annotations

import time
import threading
from collections import deque
from typing import Generic, TypeVar

T = TypeVar("T")


# ===========================================================================
# TokenBucket — 令牌桶限流
# ===========================================================================


class TokenBucket:
    """令牌桶: 平滑突发限流, 允许短时突发, 长期速率恒定。

    原理:
      - 桶容量 = burst 个令牌
      - 令牌以 rate 个/秒的速度生成
      - 每个请求消耗 1 个令牌
      - 令牌不足 → 拒绝

    复杂度: O(1)

    Example:
        >>> tb = TokenBucket(rate=100, burst=200)  # 100 QPS, 允许突发 200
        >>> tb.try_consume(1)  # True
    """

    def __init__(self, rate: float, burst: float | None = None):
        if rate <= 0:
            raise ValueError(f"rate 必须为正: {rate}")
        self._rate = rate
        self._burst = burst if burst is not None else rate
        self._tokens = self._burst
        self._last_time = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_time
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_time = now

    def try_consume(self, tokens: float = 1.0) -> bool:
        """尝试消耗 tokens 个令牌, 返回是否成功。"""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def consume(self, tokens: float = 1.0, timeout: float | None = None) -> bool:
        """阻塞方式消耗令牌, timeout 秒后返回 False。"""
        deadline = time.monotonic() + (timeout or float("inf"))
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.01, remaining))

    @property
    def available_tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


# ===========================================================================
# SlidingWindow — 滑动窗口限流
# ===========================================================================


class SlidingWindow:
    """滑动窗口限流: 严格限制最近 window 秒内最多 max_requests 次。

    原理:
      - 维护请求时间戳队列
      - 每个请求到来时, 丢弃窗口外的旧时间戳
      - 队列长度 >= max_requests → 拒绝

    复杂度: O(w)  (w = 窗口内请求数)

    Example:
        >>> sw = SlidingWindow(max_requests=100, window=1.0)  # 100 QPS
        >>> sw.try_acquire()  # True
    """

    def __init__(self, max_requests: int, window: float = 1.0):
        if max_requests <= 0:
            raise ValueError(f"max_requests 必须为正: {max_requests}")
        if window <= 0:
            raise ValueError(f"window 必须为正: {window}")
        self._max = max_requests
        self._window = window
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        """尝试获取一个请求配额。"""
        with self._lock:
            now = time.monotonic()
            # 丢弃过期时间戳
            cutoff = now - self._window
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max:
                return False
            self._timestamps.append(now)
            return True

    @property
    def current_count(self) -> int:
        with self._lock:
            cutoff = time.monotonic() - self._window
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            return len(self._timestamps)


# ===========================================================================
# LeakyBucket — 漏桶限流
# ===========================================================================


class LeakyBucket:
    """漏桶: 恒定速率流出, 请求入桶, 桶满即拒绝。

    原理:
      - 桶容量 = capacity
      - 水以 rate 桶/秒流出
      - 请求到达 → 往桶里加水 (水量)
      - 桶满 → 拒绝

    复杂度: O(1)

    Example:
        >>> lb = LeakyBucket(rate=100, capacity=200)  # 100 QPS, 最多排队 200
        >>> lb.try_acquire(1)  # True
    """

    def __init__(self, rate: float, capacity: float):
        if rate <= 0:
            raise ValueError(f"rate 必须为正: {rate}")
        self._rate = rate
        self._capacity = capacity
        self._water = 0.0
        self._last_time = time.monotonic()
        self._lock = threading.Lock()

    def _drain(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_time
        self._water = max(0.0, self._water - elapsed * self._rate)
        self._last_time = now

    def try_acquire(self, water: float = 1.0) -> bool:
        with self._lock:
            self._drain()
            if self._water + water <= self._capacity:
                self._water += water
                return True
            return False


# ===========================================================================
# AtomicCounter — 原子计数器
# ===========================================================================


class AtomicCounter:
    """线程安全原子计数器 (int64 范围)。

    Example:
        >>> c = AtomicCounter(0)
        >>> c.inc()  # 1
        >>> c.add(5)  # 6
    """

    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = threading.Lock()

    def inc(self, delta: int = 1) -> int:
        with self._lock:
            self._value += delta
            return self._value

    def dec(self, delta: int = 1) -> int:
        return self.inc(-delta)

    def get(self) -> int:
        with self._lock:
            return self._value

    def set(self, value: int) -> None:
        with self._lock:
            self._value = value

    def compare_and_swap(self, expected: int, new: int) -> bool:
        with self._lock:
            if self._value == expected:
                self._value = new
                return True
            return False


# ===========================================================================
# RWLock — 读写锁
# ===========================================================================


class RWLock:
    """读写锁: 多读单写, 写优先避免写饥饿。

    性质:
      - 无写者时: 多读者可并发
      - 有写者等待时: 新读者阻塞, 优先让写者执行
      - 写者互斥

    Example:
        >>> rwlock = RWLock()
        >>> with rwlock.read():
        ...     # 读操作
        ...     pass
        >>> with rwlock.write():
        ...     # 写操作
        ...     pass
    """

    def __init__(self):
        self._readers = 0
        self._writers_waiting = 0
        self._writing = False
        self._cond = threading.Condition()

    def read_acquire(self) -> None:
        with self._cond:
            while self._writing or self._writers_waiting > 0:
                self._cond.wait()
            self._readers += 1

    def read_release(self) -> None:
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def write_acquire(self) -> None:
        with self._cond:
            self._writers_waiting += 1
            try:
                while self._readers > 0 or self._writing:
                    self._cond.wait()
                self._writing = True
            finally:
                self._writers_waiting -= 1

    def write_release(self) -> None:
        with self._cond:
            self._writing = False
            self._cond.notify_all()

    def read(self) -> _ReadGuard:
        return _ReadGuard(self)

    def write(self) -> _WriteGuard:
        return _WriteGuard(self)


class _ReadGuard:
    def __init__(self, rwlock: RWLock):
        self._rwlock = rwlock

    def __enter__(self):
        self._rwlock.read_acquire()
        return self

    def __exit__(self, *args):
        self._rwlock.read_release()


class _WriteGuard:
    def __init__(self, rwlock: RWLock):
        self._rwlock = rwlock

    def __enter__(self):
        self._rwlock.write_acquire()
        return self

    def __exit__(self, *args):
        self._rwlock.write_release()


# ===========================================================================
# Semaphore — 计数信号量
# ===========================================================================


class Semaphore:
    """计数信号量: 控制同时访问资源的线程数。

    Example:
        >>> sem = Semaphore(5)  # 最多 5 个并发
        >>> with sem:
        ...     # 临界区
        ...     pass
    """

    def __init__(self, value: int = 1):
        if value < 0:
            raise ValueError(f"信号量初始值不能为负: {value}")
        self._value = value
        self._cond = threading.Condition()

    def acquire(self, timeout: float | None = None) -> bool:
        with self._cond:
            if timeout is not None:
                deadline = time.monotonic() + timeout
                while self._value == 0:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._cond.wait(remaining)
            else:
                while self._value == 0:
                    self._cond.wait()
            self._value -= 1
            return True

    def release(self) -> None:
        with self._cond:
            self._value += 1
            self._cond.notify()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


# ===========================================================================
# Barrier — 同步屏障
# ===========================================================================


class Barrier:
    """同步屏障: 所有线程到达屏障点后同时继续。

    Example:
        >>> barrier = Barrier(3)
        >>> # 在 3 个线程中分别调用:
        >>> barrier.wait()  # 第三个线程到达时, 所有线程同时释放
    """

    def __init__(self, parties: int):
        if parties <= 0:
            raise ValueError(f"parties 必须为正: {parties}")
        self._parties = parties
        self._count = 0
        self._generation = 0
        self._cond = threading.Condition()

    def wait(self, timeout: float | None = None) -> int:
        """等待其他线程到达, 返回到达编号 (0 ~ parties-1)。"""
        with self._cond:
            gen = self._generation
            self._count += 1
            if self._count == self._parties:
                self._count = 0
                self._generation += 1
                self._cond.notify_all()
                return 0
            deadline = time.monotonic() + (timeout or float("inf"))
            while self._generation == gen:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._count -= 1
                    raise TimeoutError("Barrier wait timeout")
                self._cond.wait(remaining)
            return self._count


# ===========================================================================
# CancellationToken — 取消令牌
# ===========================================================================


class CancellationToken:
    """协作式取消令牌: 长任务可定期检查是否应取消。

    Example:
        >>> token = CancellationToken()
        >>> # 在另一个线程:
        >>> token.cancel()
        >>> # 在任务中:
        >>> if token.is_cancelled:
        ...     return  # 提前退出
    """

    def __init__(self):
        self._cancelled = False
        self._lock = threading.Lock()

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def throw_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise CancelledError("操作已取消")


class CancelledError(Exception):
    pass


# ===========================================================================
# Debouncer — 消抖器
# ===========================================================================


class Debouncer:
    """消抖器: 高频事件降频, 只在最后一次调用后 delay 秒执行。

    Example:
        >>> db = Debouncer(delay=0.5)
        >>> db.call(lambda: print("executed"))  # 0.5 秒内无新调用则执行
    """

    def __init__(self, delay: float = 0.3):
        self._delay = delay
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def call(self, fn, *args, **kwargs) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, fn, args, kwargs)
            self._timer.start()

    def cancel(self) -> None:
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None


# ===========================================================================
# RateLimiter — 统一限流接口
# ===========================================================================


class RateLimiter:
    """统一限流接口: 支持多策略组合。

    策略:
      - "token_bucket": 令牌桶 (平滑突发)
      - "sliding_window": 滑动窗口 (严格限制)
      - "leaky_bucket": 漏桶 (恒定速率)

    Example:
        >>> rl = RateLimiter(strategy="token_bucket", rate=100, burst=200)
        >>> rl.try_acquire()  # True
    """

    def __init__(self, strategy: str = "token_bucket", **kwargs):
        strategies = {
            "token_bucket": lambda: TokenBucket(
                kwargs.get("rate", 100),
                kwargs.get("burst", kwargs.get("rate", 100)),
            ),
            "sliding_window": lambda: SlidingWindow(
                kwargs.get("max_requests", 100),
                kwargs.get("window", 1.0),
            ),
            "leaky_bucket": lambda: LeakyBucket(
                kwargs.get("rate", 100),
                kwargs.get("capacity", kwargs.get("rate", 100)),
            ),
        }
        if strategy not in strategies:
            raise ValueError(f"未知策略: {strategy}, 可选: {list(strategies.keys())}")
        self._impl = strategies[strategy]()
        self._strategy = strategy

    def try_acquire(self) -> bool:
        if self._strategy == "token_bucket":
            return self._impl.try_consume(1)
        elif self._strategy == "sliding_window":
            return self._impl.try_acquire()
        elif self._strategy == "leaky_bucket":
            return self._impl.try_acquire(1)
        return False

    @property
    def current_count(self) -> float:
        if self._strategy == "token_bucket":
            return self._impl.available_tokens
        elif self._strategy == "sliding_window":
            return self._impl.current_count
        return 0.0