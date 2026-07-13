"""
异常熔断器 (Circuit Breaker)。

算法原理 — 三态状态机:
  CLOSED (关闭/正常放行)
    → 连续失败达 failure_threshold 次 → 切换到 OPEN
  OPEN (开启/快速失败)
    → 经过 recovery_timeout 秒 → 切换到 HALF_OPEN
  HALF_OPEN (半开/探测)
    → 放行少量探测请求
    → 连续成功 success_threshold 次 → 切换到 CLOSED (恢复)
    → 任一失败 → 切换回 OPEN (再次熔断)

线程安全: 所有状态读写加锁。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from fnixagent.core.types import CircuitState


@dataclass
class _BreakerState:
    """熔断器内部运行时状态。"""
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0       # 半开态下的连续成功
    last_failure_time: float = 0.0       # 最近一次失败的时间戳
    opened_at: float = 0.0               # 进入 OPEN 的时间戳


class CircuitBreaker:
    """熔断器。

    配合 LLMRouter 使用: 每个 provider 绑定一个独立熔断器,
    当某 provider 连续故障时自动熔断,流量转移到健康 provider。

    线程安全: 所有状态读写均通过 self._lock 保护,避免 check-then-act 竞态。

    Attributes:
        _failure_threshold: CLOSED 态连续失败多少次后熔断(转 OPEN)。
        _recovery_timeout: OPEN 态经过多少秒后转 HALF_OPEN 探测。
        _success_threshold: HALF_OPEN 态连续成功多少次后恢复(转 CLOSED)。
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ):
        """初始化熔断器。

        Args:
            failure_threshold: 连续失败阈值,必须为正整数。
            recovery_timeout: 恢复探测等待秒数,必须为正。
            success_threshold: 半开态连续成功阈值,必须为正整数。

        Raises:
            TypeError: 参数类型错误。
            ValueError: 参数非正数。
        """
        if isinstance(failure_threshold, bool) or not isinstance(failure_threshold, int):
            raise TypeError(
                f"failure_threshold must be int, got {type(failure_threshold).__name__}"
            )
        if isinstance(success_threshold, bool) or not isinstance(success_threshold, int):
            raise TypeError(
                f"success_threshold must be int, got {type(success_threshold).__name__}"
            )
        if isinstance(recovery_timeout, bool) or not isinstance(recovery_timeout, (int, float)):
            raise TypeError(
                f"recovery_timeout must be numeric, got {type(recovery_timeout).__name__}"
            )
        if failure_threshold <= 0:
            raise ValueError(f"failure_threshold must be positive, got {failure_threshold}")
        if success_threshold <= 0:
            raise ValueError(f"success_threshold must be positive, got {success_threshold}")
        if recovery_timeout <= 0:
            raise ValueError(f"recovery_timeout must be positive, got {recovery_timeout}")
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._state = _BreakerState()
        self._lock = threading.Lock()

    # -- 状态查询 ----------------------------------------------------------

    def get_state(self) -> CircuitState:
        """获取当前熔断状态(会自动检查是否该从 OPEN 转 HALF_OPEN)。"""
        with self._lock:
            self._maybe_half_open()
            return self._state.state

    def allow_request(self) -> bool:
        """判断是否允许请求通过。

        - CLOSED → True
        - OPEN → False(除非已过恢复期自动转 HALF_OPEN)
        - HALF_OPEN → True(放行探测)

        注:HALF_OPEN 态下并发调用可能同时放行多个探测请求,这是设计取舍——
        由 success_threshold 计数器确保恢复前必须有足够数量的成功探测。
        """
        with self._lock:
            self._maybe_half_open()
            if self._state.state == CircuitState.OPEN:
                return False
            return True

    # -- 事件记录 ----------------------------------------------------------

    def record_success(self) -> None:
        """记录一次成功调用。

        HALF_OPEN 态下连续成功达 success_threshold 则恢复为 CLOSED。
        """
        with self._lock:
            self._maybe_half_open()
            self._state.consecutive_failures = 0
            if self._state.state == CircuitState.HALF_OPEN:
                self._state.consecutive_successes += 1
                if self._state.consecutive_successes >= self._success_threshold:
                    self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """记录一次失败调用。

        HALF_OPEN 态下任一失败立即重新熔断(转 OPEN);
        CLOSED 态下连续失败达 failure_threshold 则熔断(转 OPEN)。
        """
        with self._lock:
            self._maybe_half_open()
            now = time.monotonic()
            self._state.consecutive_failures += 1
            self._state.consecutive_successes = 0
            self._state.last_failure_time = now
            if self._state.state == CircuitState.HALF_OPEN:
                # 探测失败,立即重新熔断
                self._transition(CircuitState.OPEN)
            elif self._state.consecutive_failures >= self._failure_threshold:
                self._transition(CircuitState.OPEN)

    # -- 内部状态转换 -------------------------------------------------------

    def _maybe_half_open(self) -> None:
        """检查 OPEN 状态是否已过恢复期,自动转为 HALF_OPEN。调用者需持锁。"""
        if self._state.state != CircuitState.OPEN:
            return
        elapsed = time.monotonic() - self._state.opened_at
        if elapsed >= self._recovery_timeout:
            self._transition(CircuitState.HALF_OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        """执行状态转换,重置相关计数器。调用者需持锁。"""
        old = self._state.state
        if old == new_state:
            return
        self._state.state = new_state
        if new_state == CircuitState.OPEN:
            self._state.opened_at = time.monotonic()
            self._state.consecutive_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._state.consecutive_failures = 0
            self._state.consecutive_successes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._state.consecutive_successes = 0

    def reset(self) -> None:
        """手动重置为 CLOSED(清空全部计数)。"""
        with self._lock:
            self._state = _BreakerState()

    def __repr__(self) -> str:
        return (
            f"<CircuitBreaker state={self._state.state.value} "
            f"failures={self._state.consecutive_failures}>"
        )
