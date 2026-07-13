"""
短期会话记忆 (Short-Term Memory)。

核心算法: 滑动窗口裁剪(LRU 式淘汰)
  - 维护当前会话的消息列表
  - 当总 token 超过 max_tokens 时,从最早的非 system 消息开始删除
  - 保留 system 消息 + 最近若干轮对话
  - 支持手动设置 token 预算

设计要点:
  - 纯内存,用 list 存储,线程安全(threading.Lock 保护所有读写)
  - 估算 token 用 text.estimate_tokens(无精确 tokenizer 时的近似)
  - 精确计数由 LLM 层回填到 Message.token_count
  - LRU 淘汰:按"最近访问时间"淘汰最久未访问的非 system 消息;
    新消息插入时 access_time = 当前时间,读取时刷新 access_time

边界处理:
  - max_messages >= 1,max_tokens >= 1(构造时校验)
  - 单条消息 token 超过 max_tokens 时保留该消息(避免记忆清空)
  - 仅 system 消息时不淘汰
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from fnixagent.core.text import estimate_tokens
from fnixagent.core.types import Message, MessageRole


class ShortTermMemory:
    """
    短期会话记忆(滑动窗口 + LRU 淘汰)。

    用法:
        stm = ShortTermMemory(max_tokens=6000, max_messages=20)
        stm.add(Message(role=MessageRole.USER, content="帮我搜索论文"))
        stm.add(Message(role=MessageRole.ASSISTANT, content="已找到3篇..."))
        messages = stm.get_messages()  # 给 PromptBuilder 用

    淘汰策略:
      - 条数超限:淘汰最久未访问的非 system 消息
      - token 超限:淘汰最久未访问的非 system 消息
      - system 消息永不被淘汰(系统提示词需常驻)
    """

    def __init__(
        self,
        max_tokens: int = 6000,
        max_messages: int = 20,
    ) -> None:
        # 窗口边界校验:防止 0 或负值导致裁剪逻辑异常
        if max_tokens < 1:
            raise ValueError(f"max_tokens 必须 >= 1, got {max_tokens}")
        if max_messages < 1:
            raise ValueError(f"max_messages 必须 >= 1, got {max_messages}")
        self._max_tokens = max_tokens
        self._max_messages = max_messages
        self._messages: list[Message] = []
        # 每条消息的最近访问时间(单调时钟),用于 LRU 淘汰
        self._access_times: list[float] = []
        self._lock = threading.Lock()
        # 增量维护 token 总数,避免每次 add 都 O(n) 全量重算
        self._total_tokens: int = 0

    # -- 写入 --------------------------------------------------------------

    def add(self, message: Message) -> None:
        """添加一条消息,自动裁剪。

        Args:
            message: 待添加消息,不能为 None

        Raises:
            ValueError: message 为 None
        """
        if message is None:
            raise ValueError("message 不能为 None")
        with self._lock:
            now = time.monotonic()
            self._messages.append(message)
            self._access_times.append(now)
            self._total_tokens += estimate_tokens(message.content) + 4
            self._trim()
            # 单条消息 token 超限:不淘汰该消息(避免记忆清空),
            # 但记录不会主动截断,由上层 LLM 层处理超长 prompt

    def add_many(self, messages: list[Message]) -> None:
        """批量添加。"""
        if not messages:
            return
        with self._lock:
            now = time.monotonic()
            for m in messages:
                if m is None:
                    continue
                self._messages.append(m)
                self._access_times.append(now)
                self._total_tokens += estimate_tokens(m.content) + 4
            self._trim()

    def set_messages(self, messages: list[Message]) -> None:
        """替换全部消息。"""
        with self._lock:
            now = time.monotonic()
            self._messages = [m for m in messages if m is not None]
            self._access_times = [now] * len(self._messages)
            self._total_tokens = sum(
                estimate_tokens(m.content) + 4 for m in self._messages
            )
            self._trim()

    # -- 读取 --------------------------------------------------------------

    def get_messages(self) -> list[Message]:
        """获取当前消息列表(副本),并刷新所有消息的访问时间(LRU)。"""
        with self._lock:
            now = time.monotonic()
            # 刷新访问时间:被读取视为最近使用
            for i in range(len(self._access_times)):
                self._access_times[i] = now
            return list(self._messages)

    def get_recent(self, n: int = 5) -> list[Message]:
        """获取最近 n 条消息,并刷新其访问时间(LRU)。

        Args:
            n: 返回条数,若 n <= 0 返回空列表
        """
        if n <= 0:
            return []
        with self._lock:
            now = time.monotonic()
            n = min(n, len(self._messages))
            # 刷新末尾 n 条的访问时间
            start = len(self._access_times) - n
            for i in range(max(start, 0), len(self._access_times)):
                self._access_times[i] = now
            return list(self._messages[-n:])

    @property
    def message_count(self) -> int:
        """当前消息条数。"""
        with self._lock:
            return len(self._messages)

    def estimate_tokens(self) -> int:
        """估算当前总 token 数(O(1),使用增量维护的计数器)。"""
        with self._lock:
            return self._total_tokens

    # -- 裁剪算法 ----------------------------------------------------------

    def _trim(self) -> None:
        """
        滑动窗口裁剪(LRU 式淘汰,O(n) 均摊):
        1. 若消息条数 > max_messages, 淘汰最久未访问的非 system 消息
        2. 若总 token > max_tokens, 淘汰最久未访问的非 system 消息
        3. system 消息永不被淘汰;仅 system 消息时停止淘汰

        边界:单条非 system 消息 token 超过 max_tokens 时,
        保留该消息(避免记忆清空),由上层处理超长。
        """
        # 条数限制:淘汰最久未访问的非 system 消息
        while len(self._messages) > self._max_messages:
            victim = self._find_lru_victim()
            if victim is None:
                break  # 仅 system 消息,停止淘汰
            self._remove_at(victim)

        # Token 限制(使用增量计数器,无需全量重算)
        # 边界:至少保留 1 条非 system 消息(避免清空)
        while self._total_tokens > self._max_tokens:
            non_system_count = sum(
                1 for m in self._messages if m.role != MessageRole.SYSTEM
            )
            if non_system_count <= 1:
                break  # 仅剩 1 条非 system,保留避免清空
            victim = self._find_lru_victim()
            if victim is None:
                break
            self._remove_at(victim)

    def _find_lru_victim(self) -> Optional[int]:
        """找到最久未访问的非 system 消息索引(LRU)。

        Returns:
            被淘汰消息的索引;无非 system 消息时返回 None
        """
        victim_idx: Optional[int] = None
        victim_time: float = float("inf")
        for i, msg in enumerate(self._messages):
            if msg.role == MessageRole.SYSTEM:
                continue
            if self._access_times[i] < victim_time:
                victim_time = self._access_times[i]
                victim_idx = i
        return victim_idx

    def _remove_at(self, idx: int) -> None:
        """删除指定索引的消息(同步维护 access_times 与 total_tokens)。"""
        if idx < 0 or idx >= len(self._messages):
            return
        removed = self._messages.pop(idx)
        self._access_times.pop(idx)
        self._total_tokens -= estimate_tokens(removed.content) + 4
        # 防御性:计数器不可为负
        if self._total_tokens < 0:
            self._total_tokens = 0

    # -- 清理 --------------------------------------------------------------

    def clear(self) -> None:
        """清空(保留 system 消息)。"""
        with self._lock:
            keep_msgs: list[Message] = []
            keep_times: list[float] = []
            now = time.monotonic()
            for i, m in enumerate(self._messages):
                if m.role == MessageRole.SYSTEM:
                    keep_msgs.append(m)
                    keep_times.append(now)
            self._messages = keep_msgs
            self._access_times = keep_times
            self._total_tokens = sum(
                estimate_tokens(m.content) + 4 for m in self._messages
            )

    def clear_all(self) -> None:
        """完全清空。"""
        with self._lock:
            self._messages = []
            self._access_times = []
            self._total_tokens = 0
