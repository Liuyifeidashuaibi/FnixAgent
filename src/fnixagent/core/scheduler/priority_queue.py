"""优先级任务队列 (Priority Task Queue) — P1-05。

借鉴 zhua 项目 scheduler/kernel.py 的 ScheduleItem + 优先级队列设计,
为 fnixagent 任务管道提供优先级调度、插队、持久化与崩溃恢复能力。

特性:
  1. 优先级调度: priority 值越大越优先出队(heapq 大顶堆,基于负值实现)
  2. forefront 插队: 高优任务可立即插队到队首(LIFO 栈,最新插队的最先出)
  3. 持久化: Redis ZSet(score=priority) + Hash(item 数据),跨进程可见;
     Redis 不可用时降级到纯内存堆
  4. 崩溃恢复: active 任务超时未完成 → reclaim_stale() 回收回 pending
  5. 去重: 相同 fingerprint 的任务不重复入队(dont_filter=True 可跳过)
  6. 批量入队: put_batch() 支持批量添加任务
  7. 自动重试: mark_done(success=False) 时若 retry_count < max_retries 自动重入队

设计要点:
  - 内存为单一事实源(in-process);Redis 为跨进程可见的"最佳努力"镜像
  - 线程安全: threading.Condition() 内置锁 + wait/notify 实现阻塞 get
  - Redis 操作全部 try/except 包裹,失败时降级到纯内存(不影响主流程)
  - 惰性单例 get_priority_queue() / reset_priority_queue()

Redis 数据结构:
  - 待执行队列:
      ZSET ``redis_key``           score=priority, member=task_id
      HASH ``redis_key + ":items"`` field=task_id, value=序列化 item
  - 执行中集合:
      ZSET ``active_key``          score=started_at, member=task_id
      HASH ``active_key + ":items"`` field=task_id, value=序列化 item
  使用 task_id 作为 member/field,便于按 task_id 精确移除(mark_done 仅传入 task_id)。

依赖: 仅标准库(threading / heapq / json / logging / dataclasses / uuid / time /
collections),Redis 客户端为可选注入(Any 类型,duck typing)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import heapq
import json
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# 调度任务项
# ============================================================================

@dataclass
class ScheduleItem:
    """调度任务项 — 队列中的单个任务单元。

    Attributes:
        task_id: 任务唯一标识(自动生成 UUID)。
        task_type: 任务类型(search/generate/convert 等),用于路由。
        payload: 任务参数(可 JSON 序列化的 dict)。
        priority: 优先级(越大越优先出队,默认 0)。
        dont_filter: 是否跳过去重(True 时不检查 fingerprint)。
        forefront: 是否插队到队首(True 时进入 LIFO 栈,优先于堆出队)。
        retry_count: 已重试次数(失败重入队时 +1)。
        max_retries: 最大重试次数(超出后丢弃)。
        created_at: 创建时间戳(time.time, wall clock)。
        started_at: 开始执行时间戳(mark_active 时设置)。
        fingerprint: 去重指纹(空字符串=不参与去重)。
        timeout_seconds: 执行超时(秒),供 reclaim_stale 使用。
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    dont_filter: bool = False
    forefront: bool = False
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    fingerprint: str = ""
    timeout_seconds: float = 300.0

    def __lt__(self, other: ScheduleItem) -> bool:
        """堆比较: priority 大的先出(用负值实现大顶堆)。

        heapq 是小顶堆,``__lt__`` 返回 ``self.priority > other.priority``
        使高优先级 item "更小" → 位于堆顶 → 先出队。
        """
        return -self.priority < -other.priority

# ============================================================================
# 优先级任务队列
# ============================================================================

class PriorityTaskQueue:
    """优先级任务队列 — 内存堆 + 可选 Redis ZSet 双写。

    使用内存堆(heapq, O(log n) 入队/出队)做实时调度,可选 Redis ZSet
    做 cross-process 可见与崩溃恢复。Redis 不可用或操作失败时降级到纯内存。

    用法::

        queue = PriorityTaskQueue(redis_client=redis_client)
        queue.put(ScheduleItem(task_type="search", priority=10))
        item = queue.get(timeout=5.0)
        if item:
            queue.mark_active(item)
            try:
                ...  # 执行任务
                queue.mark_done(item.task_id, success=True)
            except Exception:
                queue.mark_done(item.task_id, success=False)
        queue.reclaim_stale()  # 定期回收超时任务
    """

    def __init__(
        self,
        redis_client: Any = None,
        redis_key: str = "fnixagent:task_queue",
        active_key: str = "fnixagent:task_active",
        enable_dedup: bool = True,
        stale_timeout: float = 300.0,
    ) -> None:
        """初始化优先级任务队列。

        Args:
            redis_client: Redis 客户端实例(redis-py 的 Redis 对象),
                None 时降级到纯内存模式。duck typing,需支持 zadd/zrem/
                hset/hget/hdel/zrangebyscore/zcard/hlen/delete。
            redis_key: 待执行队列的 Redis 键前缀(ZSET)。
            active_key: 执行中集合的 Redis 键前缀(ZSET)。
            enable_dedup: 是否启用 fingerprint 去重。
            stale_timeout: active 任务超时阈值(秒),超过则可被 reclaim_stale 回收。
        """
        self._redis: Any = redis_client
        self._redis_key: str = redis_key
        self._redis_items_key: str = f"{redis_key}:items"
        self._active_key: str = active_key
        self._active_items_key: str = f"{active_key}:items"
        self._enable_dedup: bool = enable_dedup
        self._stale_timeout: float = stale_timeout

        # 内存数据结构
        self._heap: list[ScheduleItem] = []
        self._forefront: deque[ScheduleItem] = deque()
        self._active: dict[str, ScheduleItem] = {}
        self._fingerprints: set[str] = set()

        # 统计计数(原子,受 _cond 保护)
        self._total_enqueued: int = 0
        self._total_dequeued: int = 0
        self._total_reclaimed: int = 0
        self._total_dedup_filtered: int = 0
        self._total_retried: int = 0
        self._total_dropped: int = 0

        # Condition 兼作锁 + 阻塞通知(get 的 wait/notify)
        self._cond: threading.Condition = threading.Condition()
        self._shutdown: bool = False

    # ------------------------------------------------------------------
    # 内部:Redis 序列化辅助
    # ------------------------------------------------------------------

    def _serialize_item(self, item: ScheduleItem) -> str | None:
        """将 ScheduleItem 序列化为 JSON 字符串。

        Args:
            item: 调度任务项。

        Returns:
            JSON 字符串;payload 不可序列化时返回 None。
        """
        try:
            return json.dumps(
                {
                    "task_id": item.task_id,
                    "task_type": item.task_type,
                    "payload": item.payload,
                    "priority": item.priority,
                    "dont_filter": item.dont_filter,
                    "forefront": item.forefront,
                    "retry_count": item.retry_count,
                    "max_retries": item.max_retries,
                    "created_at": item.created_at,
                    "started_at": item.started_at,
                    "fingerprint": item.fingerprint,
                    "timeout_seconds": item.timeout_seconds,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
        except (TypeError, ValueError) as e:
            logger.warning(
                "ScheduleItem 序列化失败 task_id=%s: %s",
                item.task_id,
                e,
            )
            return None

    @staticmethod
    def _deserialize_item(data: str) -> ScheduleItem | None:
        """从 JSON 字符串反序列化 ScheduleItem。

        Args:
            data: JSON 字符串。

        Returns:
            ScheduleItem 实例;反序列化失败返回 None。
        """
        try:
            d = json.loads(data)
            return ScheduleItem(**d)
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning("ScheduleItem 反序列化失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 内部:Redis 写操作(best effort,失败降级)
    # ------------------------------------------------------------------

    def _redis_add_to_queue(self, item: ScheduleItem) -> None:
        """将 item 写入 Redis 待执行队列(ZSET + HASH)。"""
        if self._redis is None:
            return
        serialized = self._serialize_item(item)
        if serialized is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.zadd(self._redis_key, {item.task_id: item.priority})
            pipe.hset(self._redis_items_key, item.task_id, serialized)
            pipe.execute()
        except Exception as e:
            logger.warning(
                "Redis 写入待执行队列失败 task_id=%s: %s",
                item.task_id,
                e,
            )

    def _redis_remove_from_queue(self, task_id: str) -> None:
        """从 Redis 待执行队列移除 task_id(ZREM + HDEL)。"""
        if self._redis is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.zrem(self._redis_key, task_id)
            pipe.hdel(self._redis_items_key, task_id)
            pipe.execute()
        except Exception as e:
            logger.warning(
                "Redis 移除待执行队列失败 task_id=%s: %s",
                task_id,
                e,
            )

    def _redis_add_to_active(self, item: ScheduleItem) -> None:
        """将 item 写入 Redis 执行中集合(ZSET score=started_at + HASH)。"""
        if self._redis is None:
            return
        serialized = self._serialize_item(item)
        if serialized is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.zadd(self._active_key, {item.task_id: item.started_at})
            pipe.hset(self._active_items_key, item.task_id, serialized)
            pipe.execute()
        except Exception as e:
            logger.warning(
                "Redis 写入 active 集合失败 task_id=%s: %s",
                item.task_id,
                e,
            )

    def _redis_remove_from_active(self, task_id: str) -> None:
        """从 Redis 执行中集合移除 task_id(ZREM + HDEL)。"""
        if self._redis is None:
            return
        try:
            pipe = self._redis.pipeline()
            pipe.zrem(self._active_key, task_id)
            pipe.hdel(self._active_items_key, task_id)
            pipe.execute()
        except Exception as e:
            logger.warning(
                "Redis 移除 active 集合失败 task_id=%s: %s",
                task_id,
                e,
            )

    # ------------------------------------------------------------------
    # 内部:入队核心逻辑(调用者需持锁)
    # ------------------------------------------------------------------

    def _put_locked(self, item: ScheduleItem) -> bool:
        """入队核心逻辑(调用者需持有 _cond 锁)。

        Returns:
            True=成功入队;False=被去重过滤。
        """
        # 去重检查
        if self._enable_dedup and item.fingerprint and not item.dont_filter:
            if item.fingerprint in self._fingerprints:
                self._total_dedup_filtered += 1
                return False
            self._fingerprints.add(item.fingerprint)

        # 入内存结构
        if item.forefront:
            # 插队到队首(LIFO 栈:append 到右侧,get 时从右侧 pop)
            self._forefront.append(item)
        else:
            heapq.heappush(self._heap, item)

        # 同步到 Redis(best effort)
        self._redis_add_to_queue(item)

        self._total_enqueued += 1
        return True

    def _get_nowait_locked(self) -> ScheduleItem | None:
        """非阻塞出队(调用者需持有 _cond 锁)。

        优先从 forefront 栈弹出,其次从堆弹出。

        Returns:
            ScheduleItem 或 None(队列为空)。
        """
        if self._forefront:
            item = self._forefront.pop()
            self._redis_remove_from_queue(item.task_id)
            self._total_dequeued += 1
            return item
        if self._heap:
            item = heapq.heappop(self._heap)
            self._redis_remove_from_queue(item.task_id)
            self._total_dequeued += 1
            return item
        return None

    # ------------------------------------------------------------------
    # 公共:入队
    # ------------------------------------------------------------------

    def put(self, item: ScheduleItem) -> bool:
        """入队(线程安全)。

        Args:
            item: 调度任务项。

        Returns:
            True=成功入队;False=被去重过滤(且 dont_filter=False)。
        """
        with self._cond:
            if self._shutdown:
                raise RuntimeError("PriorityTaskQueue 已 shutdown, 无法 put")
            success = self._put_locked(item)
            if success:
                self._cond.notify()
            return success

    def put_batch(self, items: list[ScheduleItem]) -> int:
        """批量入队(线程安全,单次加锁)。

        Args:
            items: 调度任务项列表。

        Returns:
            成功入队数量(被去重过滤的不计入)。
        """
        if not items:
            return 0
        with self._cond:
            if self._shutdown:
                raise RuntimeError("PriorityTaskQueue 已 shutdown, 无法 put_batch")
            count = 0
            for item in items:
                if self._put_locked(item):
                    count += 1
            if count > 0:
                self._cond.notify_all()
            return count

    # ------------------------------------------------------------------
    # 公共:出队
    # ------------------------------------------------------------------

    def get(self, timeout: float = 0.0) -> ScheduleItem | None:
        """出队(线程安全,可阻塞)。

        Args:
            timeout: 阻塞等待秒数;0=非阻塞(立即返回,队列空则返回 None);
                >0=等待最多 timeout 秒,期间被 put 唤醒则立即返回。

        Returns:
            ScheduleItem 或 None(超时或队列空)。

        Raises:
            RuntimeError: 队列已 shutdown。
        """
        with self._cond:
            if self._shutdown:
                raise RuntimeError("PriorityTaskQueue 已 shutdown, 无法 get")

            # 非阻塞模式
            if timeout <= 0.0:
                return self._get_nowait_locked()

            # 阻塞模式:等待 timeout 秒
            end_time = time.monotonic() + timeout
            while True:
                item = self._get_nowait_locked()
                if item is not None:
                    return item
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)

    def peek(self) -> ScheduleItem | None:
        """查看队首(不出队,线程安全)。

        Returns:
            下一个将出队的 ScheduleItem,或 None(队列空)。
        """
        with self._cond:
            if self._forefront:
                return self._forefront[-1]
            if self._heap:
                return self._heap[0]
            return None

    # ------------------------------------------------------------------
    # 公共:执行中管理
    # ------------------------------------------------------------------

    def mark_active(self, item: ScheduleItem) -> None:
        """标记任务为执行中(写入 active 集合)。

        设置 item.started_at = time.time(),并同步到内存 active dict + Redis。

        Args:
            item: 刚出队、即将执行的 ScheduleItem。
        """
        with self._cond:
            item.started_at = time.time()
            self._active[item.task_id] = item
            self._redis_add_to_active(item)

    def mark_done(self, task_id: str, success: bool = True) -> None:
        """标记任务完成(从 active 集合移除)。

        Args:
            task_id: 任务 ID。
            success: 是否成功。False 时若 retry_count < max_retries 自动重入队
                (retry_count +1,started_at 清零);否则丢弃并移除去重指纹。
        """
        with self._cond:
            item = self._active.pop(task_id, None)
            if item is None:
                # 内存中无此 task(active 可能由其他进程写入 Redis)
                # 仍尝试清理 Redis
                self._redis_remove_from_active(task_id)
                return

            self._redis_remove_from_active(task_id)

            if success:
                # 成功:移除去重指纹(允许后续相同任务再次入队)
                if item.fingerprint:
                    self._fingerprints.discard(item.fingerprint)
                return

            # 失败:判断是否需要重试
            if item.retry_count < item.max_retries:
                item.retry_count += 1
                item.started_at = 0.0
                # 重入队(内部 _put_locked 会同步 Redis)
                # 注意:重试任务不再次检查去重(已经在 _fingerprints 中或无指纹)
                if item.forefront:
                    self._forefront.append(item)
                else:
                    heapq.heappush(self._heap, item)
                self._redis_add_to_queue(item)
                self._total_retried += 1
                self._cond.notify()
                logger.info(
                    "任务 %s 失败,重试 %d/%d",
                    task_id,
                    item.retry_count,
                    item.max_retries,
                )
            else:
                # 超出重试上限:丢弃,移除去重指纹
                if item.fingerprint:
                    self._fingerprints.discard(item.fingerprint)
                self._total_dropped += 1
                logger.warning(
                    "任务 %s 超出最大重试次数 %d,已丢弃",
                    task_id,
                    item.max_retries,
                )

    # ------------------------------------------------------------------
    # 公共:崩溃恢复
    # ------------------------------------------------------------------

    def reclaim_stale(self) -> int:
        """回收超时任务(active 中超过 stale_timeout 的任务)。

        同时检查内存 active dict 与 Redis active ZSET(跨进程崩溃恢复):
          - 内存 active 中的超时任务:直接 reclaim
          - Redis active 中、内存无的超时任务:反序列化后 reclaim
            (适用于其他进程崩溃后遗留的任务)

        回收逻辑:
          - retry_count < max_retries:重入队(retry_count +1)
          - retry_count >= max_retries:丢弃

        Returns:
            回收的任务数量。
        """
        reclaimed = 0
        now = time.time()
        stale_threshold = now - self._stale_timeout

        with self._cond:
            # 1) 检查内存 active dict
            stale_ids: list[str] = []
            for task_id, item in self._active.items():
                if item.started_at > 0 and item.started_at < stale_threshold:
                    stale_ids.append(task_id)

            for task_id in stale_ids:
                item = self._active.pop(task_id, None)
                if item is None:
                    continue
                self._redis_remove_from_active(task_id)
                self._reclaim_item_locked(item)
                reclaimed += 1

            # 2) 检查 Redis active ZSET(跨进程)
            if self._redis is not None:
                reclaimed += self._reclaim_redis_stale_locked(stale_threshold)

            if reclaimed > 0:
                self._total_reclaimed += reclaimed
                self._cond.notify_all()

        if reclaimed > 0:
            logger.info("reclaim_stale 回收了 %d 个超时任务", reclaimed)
        return reclaimed

    def _reclaim_item_locked(self, item: ScheduleItem) -> None:
        """回收单个 item(调用者需持锁)。

        retry_count < max_retries 时重入队,否则丢弃。
        """
        if item.retry_count < item.max_retries:
            item.retry_count += 1
            item.started_at = 0.0
            if item.forefront:
                self._forefront.append(item)
            else:
                heapq.heappush(self._heap, item)
            self._redis_add_to_queue(item)
            self._total_retried += 1
            logger.info(
                "任务 %s 超时回收,重试 %d/%d",
                item.task_id,
                item.retry_count,
                item.max_retries,
            )
        else:
            if item.fingerprint:
                self._fingerprints.discard(item.fingerprint)
            self._total_dropped += 1
            logger.warning(
                "任务 %s 超时且超出最大重试次数 %d,已丢弃",
                item.task_id,
                item.max_retries,
            )

    def _reclaim_redis_stale_locked(self, stale_threshold: float) -> int:
        """从 Redis active ZSET 回收跨进程超时任务(调用者需持锁)。

        查找 score < stale_threshold 的 task_id,反序列化后重入队。
        这些任务通常由其他进程崩溃后遗留。

        Returns:
            回收数量。
        """
        if self._redis is None:
            return 0
        try:
            # ZRANGEBYSCORE active_key 0 stale_threshold
            stale_task_ids: list[str] = self._redis.zrangebyscore(
                self._active_key, 0, stale_threshold
            )
        except Exception as e:
            logger.warning("Redis zrangebyscore active 失败: %s", e)
            return 0

        if not stale_task_ids:
            return 0

        reclaimed = 0
        for task_id_bytes in stale_task_ids:
            # redis-py 返回 bytes 或 str(取决于 decode_responses 配置)
            task_id = (
                task_id_bytes.decode("utf-8") if isinstance(task_id_bytes, bytes) else task_id_bytes
            )
            # 跳过已在内存中处理的(避免重复)
            if task_id in self._active:
                continue

            try:
                data = self._redis.hget(self._active_items_key, task_id)
            except Exception as e:
                logger.warning(
                    "Redis hget active items 失败 task_id=%s: %s",
                    task_id,
                    e,
                )
                continue

            if data is None:
                # items hash 中无数据,仅清理 ZSET
                try:
                    self._redis.zrem(self._active_key, task_id)
                except Exception:
                    pass
                continue

            data_str = data.decode("utf-8") if isinstance(data, bytes) else data
            item = self._deserialize_item(data_str)
            if item is None:
                # 反序列化失败:清理避免脏数据残留
                try:
                    self._redis.zrem(self._active_key, task_id)
                    self._redis.hdel(self._active_items_key, task_id)
                except Exception:
                    pass
                continue

            # 清理 Redis active,重入 Redis + 内存 queue
            self._redis_remove_from_active(task_id)
            self._reclaim_item_locked(item)
            reclaimed += 1

        return reclaimed

    # ------------------------------------------------------------------
    # 公共:查询
    # ------------------------------------------------------------------

    def qsize(self) -> int:
        """待执行队列长度(forefront + heap)。"""
        with self._cond:
            return len(self._forefront) + len(self._heap)

    def active_size(self) -> int:
        """活跃任务数(内存 active dict 大小)。"""
        with self._cond:
            return len(self._active)

    def get_stats(self) -> dict[str, Any]:
        """返回运行统计信息。

        Returns:
            包含队列大小、active 数、各类计数与 Redis 状态的字典。
        """
        with self._cond:
            return {
                "qsize": len(self._forefront) + len(self._heap),
                "forefront_size": len(self._forefront),
                "heap_size": len(self._heap),
                "active_size": len(self._active),
                "fingerprints": len(self._fingerprints),
                "redis_enabled": self._redis is not None,
                "stale_timeout": self._stale_timeout,
                "enable_dedup": self._enable_dedup,
                "total_enqueued": self._total_enqueued,
                "total_dequeued": self._total_dequeued,
                "total_reclaimed": self._total_reclaimed,
                "total_retried": self._total_retried,
                "total_dropped": self._total_dropped,
                "total_dedup_filtered": self._total_dedup_filtered,
                "shutdown": self._shutdown,
            }

    # ------------------------------------------------------------------
    # 公共:生命周期
    # ------------------------------------------------------------------

    def clear(self) -> int:
        """清空待执行队列(forefront + heap),返回清除数量。

        不清空 active 集合(执行中的任务不中断)。清除去重指纹。
        同时尝试清空 Redis 待执行队列键。
        """
        with self._cond:
            count = len(self._forefront) + len(self._heap)
            self._forefront.clear()
            self._heap.clear()
            self._fingerprints.clear()

            # 清空 Redis 待执行队列(best effort)
            if self._redis is not None:
                try:
                    self._redis.delete(
                        self._redis_key,
                        self._redis_items_key,
                    )
                except Exception as e:
                    logger.warning("Redis 清空待执行队列失败: %s", e)

            logger.info("PriorityTaskQueue 清空了 %d 个待执行任务", count)
            return count

    def reset(self) -> None:
        """重置到初始状态。

        清空所有内存数据(heap / forefront / active / fingerprints)与统计计数。
        尝试清空 Redis 键。不改变 shutdown 标志。
        """
        with self._cond:
            self._forefront.clear()
            self._heap.clear()
            self._active.clear()
            self._fingerprints.clear()
            self._total_enqueued = 0
            self._total_dequeued = 0
            self._total_reclaimed = 0
            self._total_retried = 0
            self._total_dropped = 0
            self._total_dedup_filtered = 0

            if self._redis is not None:
                try:
                    self._redis.delete(
                        self._redis_key,
                        self._redis_items_key,
                        self._active_key,
                        self._active_items_key,
                    )
                except Exception as e:
                    logger.warning("Redis 重置清空失败: %s", e)

    def shutdown(self) -> None:
        """关闭队列。

        标记为已 shutdown,后续 put/get 将抛 RuntimeError。
        唤醒所有阻塞在 get() 上的线程(使其检查 shutdown 标志后退出)。
        """
        with self._cond:
            self._shutdown = True
            self._cond.notify_all()

# ============================================================================
# 模块级单例
# ============================================================================

_default_queue: PriorityTaskQueue | None = None
_default_lock = threading.Lock()

def get_priority_queue(
    redis_client: Any = None,
    redis_key: str = "fnixagent:task_queue",
    active_key: str = "fnixagent:task_active",
    enable_dedup: bool = True,
    stale_timeout: float = 300.0,
) -> PriorityTaskQueue:
    """获取全局默认优先级任务队列(惰性单例,线程安全)。

    Args:
        redis_client: 仅在首次创建时生效;后续调用传入的参数会被忽略
            (已存在单例时返回原实例)。None 时使用纯内存模式。
        redis_key: 待执行队列 Redis 键前缀。
        active_key: 执行中集合 Redis 键前缀。
        enable_dedup: 是否启用去重。
        stale_timeout: 超时回收阈值(秒)。

    Returns:
        全局默认 PriorityTaskQueue 实例。
    """
    global _default_queue
    if _default_queue is None:
        with _default_lock:
            if _default_queue is None:
                _default_queue = PriorityTaskQueue(
                    redis_client=redis_client,
                    redis_key=redis_key,
                    active_key=active_key,
                    enable_dedup=enable_dedup,
                    stale_timeout=stale_timeout,
                )
    return _default_queue

def reset_priority_queue() -> None:
    """重置全局默认优先级任务队列单例(释放引用,下次 get_priority_queue 重建)。

    如需清空运行时状态而非重建实例,请对 ``get_priority_queue()`` 调用
    ``reset()`` 或 ``clear()``。
    """
    global _default_queue
    with _default_lock:
        _default_queue = None
