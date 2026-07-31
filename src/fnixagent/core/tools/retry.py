"""结构化重试策略(补全现有容错,借鉴 PydanticAI 重试 + CrewAI Task 级配置)。

区分可重试错误(超时/429/网络)与不可重试错误(参数校验/权限拒绝):
  - 可重试错误:指数退避 + 抖动,最多 N 次重试
  - 不可重试错误:立即失败,不重试

核心组件:
  - RetryableError / NonRetryableError:错误分类基类
  - RetryPolicy:重试策略(max_attempts/backoff/jitter/retryable_exceptions)
  - with_retry:通用重试装饰器/函数
  - 3 个预定义策略:DEFAULT / NETWORK / NO_RETRY

与 ToolCallState 配合:
  - 重试前检查 ToolCall.can_retry()(仅 FAILED 可重试)
  - 重试时 attempts += 1,transition_to(EXECUTING)
  - 达到 max_attempts 仍失败 → transition_to(CANCELLED)
"""

from __future__ import annotations

import asyncio
import functools
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from fnixagent.core.exceptions import fnixagentError
from fnixagent.core.types import ToolCallState

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 错误分类
# ---------------------------------------------------------------------------


class RetryableError(fnixagentError):
    """可重试错误(超时/429/网络抖动等瞬时故障)。

    重试策略:指数退避 + 抖动,最多 max_attempts 次。
    """

    pass


class NonRetryableError(fnixagentError):
    """不可重试错误(参数校验/权限拒绝/逻辑错误等永久故障)。

    重试策略:立即失败,不重试。
    """

    pass


# ---------------------------------------------------------------------------
# RetryPolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """重试策略(不可变,frozen=True)。

    Attributes:
        max_attempts: 最大尝试次数(含首次,如 3 表示首次 + 2 次重试)
        initial_delay: 首次重试前延迟(秒)
        max_delay: 最大延迟上限(秒,避免退避过大)
        backoff_factor: 退避因子(delay *= backoff_factor 每次重试)
        jitter: 抖动比例(0~1,避免重试风暴)
        retryable_exceptions: 可重试异常类型元组

    compute_delay(attempt) 计算:
        delay = min(initial_delay * (backoff_factor ** (attempt - 1)), max_delay)
        delay *= (1 ± jitter * random)
    """

    max_attempts: int = 3
    initial_delay: float = 0.5
    max_delay: float = 10.0
    backoff_factor: float = 2.0
    jitter: float = 0.1
    retryable_exceptions: tuple = (RetryableError,)

    def __post_init__(self) -> None:
        """构造后校验:max_attempts >= 1,延迟非负,jitter 在 [0, 1]。

        frozen dataclass 通过 object.__setattr__ 绕过不可变约束。

        Raises:
            ValueError: max_attempts < 1 或参数非法
        """
        if not isinstance(self.max_attempts, int) or self.max_attempts < 1:
            raise ValueError(f"max_attempts 必须为 >= 1 的整数, 实为 {self.max_attempts}")
        if self.initial_delay < 0:
            raise ValueError("initial_delay 不能为负")
        if self.max_delay < 0:
            raise ValueError("max_delay 不能为负")
        if self.backoff_factor < 0:
            raise ValueError("backoff_factor 不能为负")
        if not (0.0 <= self.jitter <= 1.0):
            raise ValueError("jitter 必须在 [0.0, 1.0] 范围内")

    def compute_delay(self, attempt: int) -> float:
        """计算第 attempt 次重试前的延迟(秒)。

        Args:
            attempt: 重试序号(1 = 首次重试,2 = 第二次重试,...)

        Returns:
            延迟秒数(含抖动)
        """
        # 指数退避:initial_delay * backoff_factor^(attempt-1)
        base_delay = self.initial_delay * (self.backoff_factor ** (attempt - 1))
        base_delay = min(base_delay, self.max_delay)
        # 抖动:±jitter 比例(避免重试风暴)
        if self.jitter > 0:
            jitter_factor = 1.0 + random.uniform(-self.jitter, self.jitter)
            base_delay *= jitter_factor
        return max(0.0, base_delay)

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """判断是否应该重试。

        Args:
            error: 捕获的异常
            attempt: 当前尝试序号(1 = 首次)

        Returns:
            True 表示应该重试
        """
        # 达到最大次数不重试
        if attempt >= self.max_attempts:
            return False
        # 不可重试异常立即失败
        if isinstance(error, NonRetryableError):
            return False
        # 可重试异常重试
        if isinstance(error, self.retryable_exceptions):
            return True
        # 其他异常默认不重试(避免对未知错误盲目重试)
        return False


# ---------------------------------------------------------------------------
# 预定义策略
# ---------------------------------------------------------------------------

DEFAULT_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    initial_delay=0.5,
    max_delay=10.0,
    backoff_factor=2.0,
    jitter=0.1,
    retryable_exceptions=(RetryableError, TimeoutError, ConnectionError),
)

NETWORK_RETRY_POLICY = RetryPolicy(
    max_attempts=5,
    initial_delay=1.0,
    max_delay=30.0,
    backoff_factor=2.0,
    jitter=0.2,
    retryable_exceptions=(RetryableError, TimeoutError, ConnectionError, OSError),
)

NO_RETRY_POLICY = RetryPolicy(
    max_attempts=1,
    initial_delay=0.0,
    max_delay=0.0,
    backoff_factor=1.0,
    jitter=0.0,
    retryable_exceptions=(),
)


# ---------------------------------------------------------------------------
# with_retry 通用重试函数
# ---------------------------------------------------------------------------


def with_retry(
    func: Callable[..., T],
    *args: Any,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    on_retry: Callable[[int, Exception], None] | None = None,
    **kwargs: Any,
) -> T:
    """同步重试执行函数。

    Args:
        func: 要执行的函数
        *args: 函数位置参数
        policy: 重试策略(默认 DEFAULT_RETRY_POLICY)
        on_retry: 重试回调(attempt, error),用于日志/指标
        **kwargs: 函数关键字参数

    Returns:
        函数返回值

    Raises:
        最后一次尝试的异常(如果全部失败)
    """
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if not policy.should_retry(e, attempt):
                raise
            if on_retry is not None:
                on_retry(attempt, e)
            delay = policy.compute_delay(attempt)
            if delay > 0:
                time.sleep(delay)
    # 理论上不会走到这里(should_retry 在最后一次返回 False)
    if last_error is not None:
        raise last_error
    raise RuntimeError("with_retry: unreachable")


async def async_with_retry(
    func: Callable[..., Any],
    *args: Any,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    on_retry: Callable[[int, Exception], None] | None = None,
    **kwargs: Any,
) -> Any:
    """异步重试执行函数。

    Args:
        func: 要执行的异步函数(coro)
        *args: 函数位置参数
        policy: 重试策略
        on_retry: 重试回调(attempt, error)
        **kwargs: 函数关键字参数

    Returns:
        函数返回值

    Raises:
        最后一次尝试的异常
    """
    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            last_error = e
            if not policy.should_retry(e, attempt):
                raise
            if on_retry is not None:
                on_retry(attempt, e)
            delay = policy.compute_delay(attempt)
            if delay > 0:
                await asyncio.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("async_with_retry: unreachable")


# ---------------------------------------------------------------------------
# 装饰器形式
# ---------------------------------------------------------------------------


def retryable(
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """重试装饰器(同步函数)。

    用法:
        @retryable(policy=NETWORK_RETRY_POLICY)
        def call_api(url):
            return requests.get(url)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return with_retry(func, *args, policy=policy, on_retry=on_retry, **kwargs)

        return wrapper

    return decorator


def async_retryable(
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """重试装饰器(异步函数)。

    用法:
        @async_retryable(policy=NETWORK_RETRY_POLICY)
        async def call_api(url):
            return await client.get(url)
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await async_with_retry(func, *args, policy=policy, on_retry=on_retry, **kwargs)

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 工具调用专用重试(与 ToolCallState 配合)
# ---------------------------------------------------------------------------


def execute_with_retry(
    tool_call: Any,
    execute_fn: Callable[[Any], T],
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """工具调用专用重试(同步,与 ToolCallState 状态机配合)。

    流程:
      1. tool_call.transition_to(EXECUTING)
      2. 执行 execute_fn(tool_call)
      3. 成功 → tool_call.transition_to(SUCCESS),返回结果
      4. 失败且 should_retry → tool_call.attempts += 1,重试
      5. 失败且不可重试 → tool_call.transition_to(FAILED),抛异常
      6. 达到 max_attempts → tool_call.transition_to(CANCELLED),抛异常

    Args:
        tool_call: ToolCall 实例(含 state 状态机)
        execute_fn: 执行函数,签名为 (tool_call) -> result
        policy: 重试策略
        on_retry: 重试回调

    Returns:
        执行结果

    Raises:
        最后一次异常
    """
    # 状态流转:CREATED/APPROVED → EXECUTING
    if tool_call.state in (ToolCallState.CREATED, ToolCallState.APPROVED, ToolCallState.FAILED):
        tool_call.transition_to(ToolCallState.EXECUTING)

    last_error: Exception | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = execute_fn(tool_call)
            tool_call.transition_to(ToolCallState.SUCCESS)
            return result
        except Exception as e:
            last_error = e
            if not policy.should_retry(e, attempt):
                tool_call.transition_to(ToolCallState.FAILED)
                raise
            # 可重试:增加 attempts,等待后重试
            tool_call.attempts = attempt + 1
            if on_retry is not None:
                on_retry(attempt, e)
            delay = policy.compute_delay(attempt)
            if delay > 0:
                time.sleep(delay)

    # 达到最大次数仍失败
    tool_call.transition_to(ToolCallState.CANCELLED)
    if last_error is not None:
        raise last_error
    raise RuntimeError("execute_with_retry: unreachable")
