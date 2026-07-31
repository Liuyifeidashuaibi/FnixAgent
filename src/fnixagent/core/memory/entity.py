"""
实体记忆 (Entity Memory)。

存储结构化业务数据(用户画像/论文/项目/笔记等), 跨会话长期持有。
与短期/长期记忆的区别:
  - 短期: 原始对话历史
  - 长期: 向量化的语义记忆(模糊检索)
  - 实体: 结构化 key-value, 精确查询(用户偏好/订单状态/设备信息)

安全(OWASP ASI06 记忆投毒):
  - 只接受白名单字段(防止注入恶意属性)
  - 实体类型受限(只允许预定义的 entity_type)
  - 写入加锁(RLock)保证并发安全

重复抽取防护:
  - upsert 按 (entity_type, name) 主键去重,同一实体不会重复创建
  - merge=True 时合并属性而非覆盖,避免多次抽取丢失已有字段
"""

from __future__ import annotations

import threading
from typing import Any

from fnixagent.core.config import MemoryConfig
from fnixagent.core.types import Entity

# 允许的实体类型白名单(防止注入非法类型)
_ALLOWED_ENTITY_TYPES = {
    "user_profile",  # 用户画像
    "paper",  # 论文
    "project",  # 项目
    "note",  # 笔记
    "task",  # 任务
    "document",  # 文档
    "knowledge",  # 知识条目
}

# 每种实体类型的允许字段白名单
_ALLOWED_FIELDS: dict[str, set[str]] = {
    "user_profile": {"name", "role", "preferences", "research_area", "timezone"},
    "paper": {"title", "authors", "doi", "abstract", "year", "venue", "keywords"},
    "project": {"name", "status", "deadline", "members", "description"},
    "note": {"title", "content", "tags", "created_at"},
    "task": {"title", "status", "priority", "assignee", "deadline"},
    "document": {"name", "type", "path", "summary", "keywords"},
    "knowledge": {"topic", "content", "source", "confidence"},
}


class EntityMemory:
    """
    实体记忆存储。

    用法:
        em = EntityMemory()
        em.upsert(Entity(
            entity_type="user_profile",
            name="user_123",
            attributes={"name": "张三", "research_area": "NLP"},
        ))
        user = em.get("user_profile", "user_123")
        all_papers = em.list_by_type("paper")

    重复抽取处理:
        同一 (entity_type, name) 的多次 upsert 默认覆盖整个 attributes;
        若 merge=True,则合并新旧 attributes(新值覆盖同名旧值,
        保留新值中不存在的旧字段),避免多次抽取丢失已积累的属性。
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        self._config = config or MemoryConfig()
        # (entity_type, name) -> Entity
        self._store: dict[tuple[str, str], Entity] = {}
        # RLock 允许同线程递归加锁,便于嵌套调用
        self._lock = threading.RLock()

    def _validate(self, entity: Entity) -> list[str]:
        """校验实体类型和字段是否在白名单内。返回违规列表。"""
        violations: list[str] = []
        if entity.entity_type not in _ALLOWED_ENTITY_TYPES:
            violations.append(
                f"未知实体类型: '{entity.entity_type}', 允许: {_ALLOWED_ENTITY_TYPES}"
            )
            return violations

        allowed = _ALLOWED_FIELDS.get(entity.entity_type, set())
        for key in entity.attributes:
            if key not in allowed:
                violations.append(f"实体 '{entity.entity_type}' 不允许字段: '{key}'")
        return violations

    # -- CRUD --------------------------------------------------------------

    def upsert(
        self,
        entity: Entity,
        merge: bool = False,
    ) -> tuple[bool, list[str]]:
        """
        插入或更新实体。
        返回 (是否成功, 违规列表)。

        Args:
            entity: 待写入实体
            merge: 是否合并属性(默认 False 整体覆盖)。
                True 时保留旧实体中存在但新实体中不存在的字段,
                适用于多次抽取同一实体时累积属性,避免重复抽取丢失数据。

        Returns:
            (成功标志, 违规列表);违规时成功标志为 False
        """
        violations = self._validate(entity)
        if violations:
            return (False, violations)

        with self._lock:
            key = (entity.entity_type, entity.name)
            # 容量限制:仅新实体计入计数,已有实体更新不触发
            if key not in self._store:
                count = sum(1 for (t, _) in self._store if t == entity.entity_type)
                if count >= self._config.entity_max_per_user:
                    return (
                        False,
                        [f"实体类型 '{entity.entity_type}' 超过最大数量限制"],
                    )

            # 生成 ID(若未提供)
            if not entity.id:
                entity.id = f"{entity.entity_type}_{entity.name}"

            # merge 模式:合并属性,避免重复抽取丢失已有字段
            if merge and key in self._store:
                old = self._store[key]
                merged_attrs = dict(old.attributes)
                merged_attrs.update(entity.attributes)
                entity.attributes = merged_attrs

            self._store[key] = entity

        return (True, [])

    def get(self, entity_type: str, name: str) -> Entity | None:
        """精确查询实体。"""
        with self._lock:
            return self._store.get((entity_type, name))

    def delete(self, entity_type: str, name: str) -> bool:
        """删除实体。"""
        with self._lock:
            key = (entity_type, name)
            if key in self._store:
                del self._store[key]
                return True
            return False

    def list_by_type(self, entity_type: str) -> list[Entity]:
        """列出某类型的所有实体。"""
        with self._lock:
            return [e for (t, _), e in self._store.items() if t == entity_type]

    def search_by_attribute(self, entity_type: str, attr_key: str, attr_value: Any) -> list[Entity]:
        """按属性值精确匹配查询。"""
        with self._lock:
            return [
                e
                for (t, _), e in self._store.items()
                if t == entity_type and e.attributes.get(attr_key) == attr_value
            ]

    def get_user_profile(self, user_id: str) -> Entity | None:
        """快捷获取用户画像。"""
        return self.get("user_profile", user_id)

    # -- 统计 --------------------------------------------------------------

    @property
    def count(self) -> int:
        """当前存储的实体总数。"""
        with self._lock:
            return len(self._store)

    def type_counts(self) -> dict[str, int]:
        """各类型实体数量。"""
        with self._lock:
            counts: dict[str, int] = {}
            for t, _ in self._store:
                counts[t] = counts.get(t, 0) + 1
            return counts

    def clear(self) -> None:
        """清空全部实体。"""
        with self._lock:
            self._store.clear()
