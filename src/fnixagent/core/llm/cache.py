"""
请求缓存 (Response Cache)。

对相同输入(messages + model + temperature)的 LLM 请求做精确缓存,
避免重复调用计费。采用 LRU + TTL 双重淘汰策略。

算法:
  - 精确匹配: 对 messages 序列化 + 参数做哈希(SHA-256)作为缓存键
  - LRU 淘汰: OrderedDict, 容量超限移除最久未访问
  - TTL 过期: 每条记录存入时间戳, get 时惰性检查
  - 线程安全: 所有操作加锁
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict

from fnixagent.core.types import LLMResponse


class ResponseCache:
    """LLM 响应精确缓存。

    采用 LRU + TTL 双重淘汰策略,所有读写操作均加锁,线程安全。

    Attributes:
        _max_size: 最大缓存条目数,超限按 LRU 淘汰。
        _ttl: 单条缓存存活秒数,0 表示永不过期。
        _store: OrderedDict,key 为 SHA-256 摘要,value 为 (response, timestamp)。
    """

    def __init__(self, max_size: int = 2048, ttl: int = 86400):
        """初始化缓存。

        Args:
            max_size: 最大缓存条目数,必须为正整数。
            ttl: 单条缓存存活秒数,0 表示永不过期,不能为负。

        Raises:
            TypeError: 参数类型错误。
            ValueError: max_size 非正或 ttl 为负。
        """
        if isinstance(max_size, bool) or not isinstance(max_size, int):
            raise TypeError(f"max_size must be int, got {type(max_size).__name__}")
        if isinstance(ttl, bool) or not isinstance(ttl, int):
            raise TypeError(f"ttl must be int, got {type(ttl).__name__}")
        if max_size <= 0:
            raise ValueError(f"max_size must be positive, got {max_size}")
        if ttl < 0:
            raise ValueError(f"ttl must be >= 0, got {ttl}")
        self._max_size = max_size
        self._ttl = ttl
        self._store: OrderedDict[str, tuple[LLMResponse, float]] = OrderedDict()
        self._lock = threading.Lock()
        # 统计
        self._hits = 0
        self._misses = 0

    # -- 键生成 ------------------------------------------------------------

    @staticmethod
    def make_key(messages: list[dict], model: str, temperature: float, **extra) -> str:
        """根据消息内容与参数生成缓存键。

        相同输入必然产生相同键,实现精确缓存。extra 中的可变结构需可 JSON 序列化
        且具有确定性(如用排序后的 list 替代 set)。

        Args:
            messages: 消息列表(provider 通用 dict 形式)。
            model: 模型名。
            temperature: 采样温度(内部 round 到 4 位以保证稳定性)。
            **extra: 其它影响结果的参数(如 max_tokens/tools/stop/think_mode)。

        Returns:
            str: 64 字符的 SHA-256 十六进制摘要。
        """
        # 标准化: 排序 extra 的键, 保证确定性
        payload = {
            "messages": messages,
            "model": model,
            "temperature": round(temperature, 4),
            "extra": {k: v for k, v in sorted(extra.items())},
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # -- 读写 --------------------------------------------------------------

    def get(self, key: str) -> LLMResponse | None:
        """查找缓存。命中且未过期则返回(标记 cached=True),否则返回 None。

        Args:
            key: 由 make_key 生成的缓存键。

        Returns:
            LLMResponse 或 None;命中时返回的是副本(避免外部修改污染缓存)。
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            response, ts = entry
            if self._ttl > 0 and (time.time() - ts) > self._ttl:
                # 已过期, 移除
                del self._store[key]
                self._misses += 1
                return None
            # LRU: 移到末尾(最近访问)
            self._store.move_to_end(key)
            self._hits += 1
            # 返回标记为 cached 的副本
            return LLMResponse(
                content=response.content,
                model=response.model,
                usage=response.usage,
                raw=response.raw,
                cached=True,
                finish_reason=response.finish_reason,
            )

    def set(self, key: str, response: LLMResponse) -> None:
        """写入缓存, 超容量时 LRU 淘汰最久未访问的条目。

        Args:
            key: 缓存键。
            response: 待缓存的响应(原引用存入,调用方不应再修改)。
        """
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (response, time.time())
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)  # 弹出最老的

    def clear(self) -> None:
        """清空全部缓存并重置命中/未命中计数。"""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    # -- 统计 --------------------------------------------------------------

    def stats(self) -> dict:
        """返回缓存命中率统计(线程安全快照)。"""
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / total if total > 0 else 0.0,
            }
