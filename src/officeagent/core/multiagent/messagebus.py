"""消息总线 —— P3-4。

借鉴:
  - AgentScope:MessageBus 抽象 + Msg + 路由字段(send_to / cause_by)
  - MetaGPT:Message pub-sub + Environment 共享黑板
  - OpenAI Agents SDK:Handoff 机制(消息在 Agent 间显式传递)

设计要点:
  1. MessageBus 是发布订阅抽象,topic-based(不直接耦合 Agent)
  2. InMemoryMessageBus 默认实现(同进程;分布式用 RedisMessageBus 子类)
  3. subscribe 返回 sub_id,便于 unsubscribe(避免 handler 引用泄漏)
  4. publish 支持 topic 通配(如 "action.*" 匹配 "action.search")
  5. handler 可以是同步或异步(MaybeAwaitable 兼容)
  6. 消息投递语义:at-most-once(默认);失败不重试(由调用方决定)

Topic 约定(与 Msg.cause_by 对齐):
  - "message.user"       用户消息
  - "message.assistant"  助手消息
  - "action.{name}"      Action 触发(对应 cause_by)
  - "handoff"            Handoff 事件
  - "system"             系统消息

用例:
    bus = InMemoryMessageBus()
    sub_id = bus.subscribe("action.search", lambda msg: print(msg))
    bus.publish("action.search", user_msg("hello"))
    bus.unsubscribe(sub_id)
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

from officeagent.core.types_msg import Msg

logger = logging.getLogger(__name__)

# handler 类型:接受 Msg,返回 None 或 Awaitable[None]
MessageHandler = Callable[[Msg], Union[None, Any]]

# 消息大小上限(字节),防止恶意大消息撑爆内存
_MAX_MESSAGE_SIZE = 1_048_576  # 1 MB


# ---------------------------------------------------------------------------
# MessageBus 抽象基类
# ---------------------------------------------------------------------------


class MessageBus:
    """消息总线抽象基类。

    子类需实现:
      - _do_subscribe(topic, handler) -> sub_id
      - _do_unsubscribe(sub_id) -> bool
      - _do_publish(topic, msg) -> int  # 返回投递到的订阅者数量

    本基类提供:
      - sub_id 生成与注册表管理
      - topic 通配匹配
      - 公共 API(publish / subscribe / unsubscribe)
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, tuple[str, str, MessageHandler]] = {}
        # sub_id → (topic_pattern, topic_exact, handler)
        # topic_pattern 用于通配匹配;topic_exact 用于精确匹配(优化)
        # 并发安全:_lock 保护 _subscriptions 的读写,publish 遍历时也持锁
        self._lock = threading.RLock()

    # -- 公共 API ----------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
    ) -> str:
        """订阅 topic。

        Args:
            topic:   topic 名(支持通配符 *,如 "action.*");必须非空
            handler: 消息处理函数(同步或异步)

        Returns:
            sub_id(用于 unsubscribe)

        Raises:
            ValueError: topic 为空或 handler 不可调用
        """
        if not topic or not isinstance(topic, str):
            raise ValueError("topic must be a non-empty string")
        if not callable(handler):
            raise ValueError("handler must be callable")
        sub_id = uuid.uuid4().hex[:16]
        with self._lock:
            self._subscriptions[sub_id] = (topic, topic, handler)
        self._do_subscribe(topic, handler, sub_id)
        logger.debug("subscribed sub_id=%s to topic=%s", sub_id, topic)
        return sub_id

    def unsubscribe(self, sub_id: str) -> bool:
        """取消订阅。

        Args:
            sub_id: subscribe 返回的 ID

        Returns:
            是否成功取消(未找到返回 False)
        """
        with self._lock:
            if sub_id not in self._subscriptions:
                return False
            topic, _, _ = self._subscriptions.pop(sub_id)
        self._do_unsubscribe(sub_id)
        logger.debug("unsubscribed sub_id=%s from topic=%s", sub_id, topic)
        return True

    def publish(self, topic: str, msg: Msg) -> int:
        """发布消息到 topic。

        Args:
            topic: topic 名(精确,不含通配符);必须非空
            msg:   Msg 实例

        Returns:
            投递到的订阅者数量

        Raises:
            ValueError: topic 为空
        """
        if not topic or not isinstance(topic, str):
            raise ValueError("topic must be a non-empty string")
        # 消息大小限制(防止恶意大消息)
        self._check_message_size(msg)
        count = self._do_publish(topic, msg)
        logger.debug("published to topic=%s, delivered to %d subscribers", topic, count)
        return count

    def list_subscriptions(self) -> list[tuple[str, str]]:
        """列出全部订阅(sub_id, topic)。"""
        with self._lock:
            return [(sid, tup[0]) for sid, tup in self._subscriptions.items()]

    def clear(self) -> None:
        """清空全部订阅。"""
        with self._lock:
            self._subscriptions.clear()

    # -- 子类实现 ----------------------------------------------------------

    def _do_subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        sub_id: str,
    ) -> None:
        """子类实现:注册订阅。"""
        pass  # InMemoryMessageBus 在 publish 时遍历,无需预注册

    def _do_unsubscribe(self, sub_id: str) -> None:
        """子类实现:移除订阅。"""
        pass

    def _do_publish(self, topic: str, msg: Msg) -> int:
        """子类实现:发布消息,返回投递数量。"""
        raise NotImplementedError

    # -- 内部:topic 匹配 --------------------------------------------------

    @staticmethod
    def _topic_matches(pattern: str, topic: str) -> bool:
        """判断 topic 是否匹配 pattern(支持 * 通配)。

        通配匹配算法(基于 fnmatch,Unix shell-style):
          1. 精确匹配优先:pattern == topic 时直接返回 True(O(1) 快路径,
             避免对大量精确订阅调用 fnmatch 的开销)
          2. 通配匹配:pattern 含 "*" 时用 fnmatch.fnmatch(topic, pattern)
             - "*" 匹配任意字符序列(含分隔符 ".",不跨层级限制)
             - "?" 匹配单个字符
             - "[seq]" 匹配 seq 中任一字符
             例:
               "action.*"        匹配 "action.search" / "action.write"
               "action.[sw]*"    匹配 "action.search" / "action.write"
               "*"               匹配全部 topic(全订阅)
          3. 无通配符且不等:返回 False

        Args:
            pattern: 订阅时的 topic 模式(可能含通配符)
            topic:   publish 时的精确 topic(不含通配符)

        Returns:
            是否匹配
        """
        # 快路径:精确匹配(O(1),避免 fnmatch 开销)
        if pattern == topic:
            return True
        # 仅当 pattern 含通配符时才走 fnmatch(避免无谓调用)
        if "*" in pattern or "?" in pattern or "[" in pattern:
            return fnmatch.fnmatch(topic, pattern)
        return False

    # -- 内部:消息大小校验 ------------------------------------------------

    @staticmethod
    def _check_message_size(msg: Msg) -> None:
        """校验消息大小是否超限。

        用 repr(msg) 估算序列化后大小(保守估计,实际序列化可能更大)。
        超限抛 ValueError,防止恶意大消息撑爆内存或拖慢 publish。

        Args:
            msg: 待发布的 Msg 实例

        Raises:
            ValueError: 消息大小超过 _MAX_MESSAGE_SIZE(1 MB)
        """
        try:
            size = len(repr(msg))
        except Exception:
            # repr 失败时无法判定大小,放行(避免因校验本身崩溃)
            return
        if size > _MAX_MESSAGE_SIZE:
            raise ValueError(
                f"message size {size} exceeds max {_MAX_MESSAGE_SIZE} bytes"
            )


# ---------------------------------------------------------------------------
# InMemoryMessageBus(同进程实现)
# ---------------------------------------------------------------------------


class InMemoryMessageBus(MessageBus):
    """同进程内存消息总线。

    特点:
      - 同步 publish:handler 立即执行(同步 handler 直接调用;异步 handler 创建 task)
      - 无持久化:进程退出消息丢失
      - 无顺序保证:多个 handler 的执行顺序不保证(按订阅顺序)
      - 并发安全:_do_publish 遍历订阅时取锁内快照,避免与 subscribe/unsubscribe 并发修改

    适用场景:
      - 单进程多 Agent 协作
      - 测试 / 开发
      - 单机部署
    """

    def __init__(self) -> None:
        super().__init__()
        # 异步 handler 的 task 引用(避免被 GC 回收导致 task 取消)
        # 注:task 完成后仍会留在列表中,需定期清理
        self._async_tasks: list[Any] = []

    def _do_publish(self, topic: str, msg: Msg) -> int:
        """发布消息:遍历全部订阅,匹配 topic 的调用 handler。

        并发安全:遍历前在 self._lock 内取 _subscriptions 的快照副本,
        避免 publish 期间其他线程 subscribe/unsubscribe 修改字典导致
        RuntimeError: dictionary changed size during iteration。

        异常隔离:单个 handler 抛异常不影响其他 handler 和 publish 返回,
        异常仅记录日志(任务要求:"MessageBus handler 异常不中断 publish")。
        """
        count = 0
        # 关键:取锁内快照,避免并发修改导致迭代错误
        # 快照为 (sub_id, (pattern, exact, handler)) 列表副本
        with self._lock:
            snapshot = list(self._subscriptions.items())

        for sub_id, (pattern, _, handler) in snapshot:
            if not self._topic_matches(pattern, topic):
                continue
            count += 1
            try:
                result = handler(msg)
                # 若 handler 返回协程,调度异步执行
                if asyncio.iscoroutine(result):
                    self._schedule_async(result)
            except Exception as e:
                # 异常隔离:单个 handler 失败不影响其他 handler
                logger.error(
                    "messagebus handler error (sub_id=%s, topic=%s): %s",
                    sub_id, topic, e,
                    exc_info=True,
                )
        return count

    def _schedule_async(self, coro: Any) -> None:
        """调度异步 handler 执行。

        优先用运行中的事件循环;无事件循环时创建新线程跑 loop。
        task 引用存入 _async_tasks 防止 GC,并定期清理已完成 task 防泄漏。
        """
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            self._async_tasks.append(task)
            # 清理已完成 task,防止 _async_tasks 无限增长(内存泄漏)
            # 注:此处不加锁,publish 通常单线程驱动;多线程 publish 风险可控
            # (最坏情况是重复清理,无数据竞争;list 重建是原子的)
            self._async_tasks = [
                t for t in self._async_tasks if not t.done()
            ]
        except RuntimeError:
            # 无运行中的事件循环,在新线程跑
            import threading

            def _run() -> None:
                new_loop = asyncio.new_event_loop()
                try:
                    new_loop.run_until_complete(coro)
                except Exception as e:
                    logger.error("async handler error: %s", e, exc_info=True)
                finally:
                    new_loop.close()

            t = threading.Thread(target=_run, daemon=True)
            t.start()

    def cleanup_async_tasks(self) -> int:
        """清理已完成的异步 task,返回清理后的 task 数量。

        长期运行的进程应定期调用此方法(如每 N 次 publish 后),
        避免 _async_tasks 列表持有已完成 task 的引用导致内存泄漏。
        """
        self._async_tasks = [t for t in self._async_tasks if not t.done()]
        return len(self._async_tasks)


# ---------------------------------------------------------------------------
# Topic 工具函数
# ---------------------------------------------------------------------------


def topic_for_action(action_name: str) -> str:
    """根据 Action 名生成 topic。"""
    return f"action.{action_name}"


def topic_for_role(role_name: str) -> str:
    """根据 Role 名生成 topic。"""
    return f"role.{role_name}"


__all__ = [
    "MessageBus",
    "InMemoryMessageBus",
    "MessageHandler",
    "topic_for_action",
    "topic_for_role",
]
