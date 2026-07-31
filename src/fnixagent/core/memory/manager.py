"""
记忆管理器 (Memory Manager) — 三层记忆统一管理。

组合 ShortTermMemory + LongTermMemory + EntityMemory,
对外提供统一接口: save / load_context / search / update_entity。

记忆注入 Prompt 的方式:
  短期 → PromptBuilder.set_history()
  长期 → PromptBuilder.set_memory()
  实体 → PromptBuilder.set_constraints() (用户画像作为约束注入)

并发安全:
  - 短期记忆/长期记忆/实体记忆各自持有锁,内部保证线程安全
  - MemoryManager 自身无状态,跨子模块组合调用安全
"""

from __future__ import annotations

from typing import Any

from fnixagent.core.config import MemoryConfig
from fnixagent.core.memory.entity import EntityMemory
from fnixagent.core.memory.long_term import LongTermMemory
from fnixagent.core.memory.short_term import ShortTermMemory
from fnixagent.core.retrieval.embedder import BaseEmbedder, HashingEmbedder
from fnixagent.core.types import Entity, MemoryItem, Message, MessageRole


class MemoryManager:
    """
    三层记忆统一管理器。

    用法:
        mgr = MemoryManager(embedder=HashingEmbedder(), config=mem_config)
        # 保存对话
        mgr.save("session_1", Message(role=MessageRole.USER, content="帮我搜论文"), user_id="u1")
        # 加载上下文
        ctx = mgr.load_context("session_1", query="搜论文", user_id="u1")
        # ctx["short_term"] -> list[Message]
        # ctx["long_term"] -> list[MemoryItem]
        # ctx["entities"] -> dict[str, Entity]

    参数校验:
      - user_id 非空校验:涉及长期记忆/实体记忆的方法要求 user_id 非空,
        避免匿名写入造成跨用户数据污染
    """

    def __init__(
        self,
        embedder: BaseEmbedder | None = None,
        config: MemoryConfig | None = None,
    ) -> None:
        self._config = config or MemoryConfig()
        self._embedder = embedder or HashingEmbedder()
        self._short = ShortTermMemory(
            max_tokens=self._config.short_term_max_tokens,
            max_messages=self._config.short_term_max_messages,
        )
        self._long = LongTermMemory(self._embedder, config=self._config)
        self._entity = EntityMemory(self._config)

    # -- 属性 --------------------------------------------------------------

    @property
    def short_term(self) -> ShortTermMemory:
        """短期记忆实例。"""
        return self._short

    @property
    def long_term(self) -> LongTermMemory:
        """长期记忆实例。"""
        return self._long

    @property
    def entity(self) -> EntityMemory:
        """实体记忆实例。"""
        return self._entity

    # -- 保存 --------------------------------------------------------------

    def save(
        self,
        session_id: str,
        message: Message,
        user_id: str = "",
        persist_long_term: bool = True,
    ) -> None:
        """
        保存一条消息:
        1. 追加到短期记忆(滑动窗口)
        2. 若 persist_long_term 且为 user/assistant 消息, 同步写入长期记忆

        Args:
            session_id: 会话 ID
            message: 待保存消息
            user_id: 用户 ID,持久化长期记忆时必填(为空则用 session_id 兜底)
            persist_long_term: 是否同步写入长期记忆

        Raises:
            ValueError: message 为 None
        """
        if message is None:
            raise ValueError("message 不能为 None")
        # 短期记忆:无需 user_id,直接追加
        self._short.add(message)

        if persist_long_term and message.role in (MessageRole.USER, MessageRole.ASSISTANT):
            content = f"[{message.role.value}] {message.content}"
            # user_id 为空时用 session_id 兜底(避免匿名写入污染全局)
            owner = user_id or session_id or "anonymous"
            self._long.add(
                user_id=owner,
                content=content,
                metadata={"session_id": session_id, "role": message.role.value},
            )

    # -- 加载上下文 --------------------------------------------------------

    def load_context(
        self,
        query: str = "",
        user_id: str = "",
    ) -> dict:
        """
        加载完整上下文(短期 + 长期 + 实体), 供 PromptBuilder 使用。

        Args:
            query: 检索查询(为空则跳过长期记忆检索)
            user_id: 用户 ID,长期记忆与实体记忆检索时必填

        Returns:
          {
            "short_term": list[Message],
            "long_term": list[MemoryItem],
            "entity": Optional[Entity],  # 用户画像
          }
        """
        context: dict[str, Any] = {}

        # 短期对话历史(无需 user_id)
        context["short_term"] = self._short.get_messages()

        # 长期记忆检索(需 user_id + query,缺任一则跳过)
        if query and user_id:
            try:
                context["long_term"] = self._long.search(
                    user_id, query, top_k=self._config.long_term_top_k
                )
            except Exception:
                # 长期记忆检索异常:降级为空,不影响其他上下文加载
                context["long_term"] = []
        else:
            context["long_term"] = []

        # 实体记忆(用户画像)
        if user_id:
            context["entity"] = self._entity.get("user_profile", user_id)
        else:
            context["entity"] = None

        return context

    # -- 检索 --------------------------------------------------------------

    def search(self, user_id: str, query: str, top_k: int = 5) -> list[MemoryItem]:
        """统一语义检索(长期向量记忆)。

        Args:
            user_id: 用户 ID,非空,用于过滤该用户的记忆
            query: 检索查询
            top_k: 返回条数

        Raises:
            ValueError: user_id 为空
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        return self._long.search(user_id, query, top_k=top_k)

    # -- 实体操作 ----------------------------------------------------------

    def update_entity(self, entity: Entity) -> tuple[bool, list[str]]:
        """更新实体记忆。"""
        return self._entity.upsert(entity)

    def get_entity(self, entity_type: str, name: str) -> Entity | None:
        """查询实体。"""
        return self._entity.get(entity_type, name)

    def get_user_profile(self, user_id: str) -> Entity | None:
        """快捷获取用户画像。

        Args:
            user_id: 用户 ID,作为 user_profile 实体的 name

        Raises:
            ValueError: user_id 为空
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        return self._entity.get("user_profile", user_id)

    # -- 维护 --------------------------------------------------------------

    def cleanup(self) -> int:
        """清理过期长期记忆。返回清理条数。"""
        return self._long.cleanup_expired()

    def reset(self) -> None:
        """重置短期记忆(新会话)。"""
        self._short.clear_all()

    def get_stats(self) -> dict:
        """统计信息。"""
        return {
            "short_term_count": self._short.message_count,
            "short_term_tokens": self._short.estimate_tokens(),
            "long_term_count": self._long.count(),
            "entity_count": self._entity.count,
            "entity_types": self._entity.type_counts(),
        }
