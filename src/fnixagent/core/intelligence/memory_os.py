"""
FnixAgent ∞ 记忆操作系统 (Memory OS) — Layer 5

设计参考:
  - Letta/MemGPT (UCB): Context=RAM, External Storage=Disk, Agent自主管理内存
  - MemOS (MemTensor): Self-evolving Memory OS, 35.24% token节省
  - MemRL (2026): 运行时RL在情景记忆上自进化, Two-Phase检索
  - EverMemOS (2026): Engram启发的自组织记忆生命周期
  - agentmemory (23k★): 持久化记忆引擎, 自动捕获
  - Hermes Agent: dual-file memory, 跨会话深度记忆

核心思想:
  将Agent记忆视为操作系统资源管理:
  ┌─────────────────────────────────────────────────────────────────┐
  │                     Memory OS 三层架构                          │
  ├─────────────────────────────────────────────────────────────────┤
  │  Core Memory (核心内存)  ← 当前活跃上下文 (RAM)                │
  │  │  最近对话 | 当前任务状态 | 活跃技能 | 用户偏好               │
  │  │  容量: ~10K tokens | 速度: 即时 | 过期: 会话结束             │
  ├─────────────────────────────────────────────────────────────────┤
  │  Recall Memory (检索缓存)  ← 近期记忆 (Disk Cache)              │
  │  │  近期对话 | 执行轨迹 | 成功/失败模式 | 短期经验              │
  │  │  容量: ~100K tokens | 速度: 毫秒级 | 过期: 7天              │
  ├─────────────────────────────────────────────────────────────────┤
  │  Archival Memory (归档存储)  ← 长期记忆 (Cold Storage)          │
  │  │  历史会话摘要 | 技能DNA | 进化轨迹 | 知识图谱                │
  │  │  容量: 无限 | 速度: 秒级 | 过期: 永不                        │
  └─────────────────────────────────────────────────────────────────┘

  MemRL Two-Phase Retrieval:
    Phase 1: 快速过滤 (过滤噪声, 保留高相关性记忆)
    Phase 2: 效用评分 (RL评估记忆效用, 选择最优策略)

  Letta-style Memory Management:
    - 核心内存: 类似RAM, 快速读写, 容量有限
    - 检索缓存: 类似Disk Cache, 近期访问的记忆
    - 归档存储: 类似Cold Storage, 压缩后的长期记忆
    - Agent自主管理: Agent决定何时swap in/out, 何时consolidate
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 记忆类型
# ============================================================

class MemoryTier(str, Enum):
    CORE = "core"          # 核心内存 (RAM)
    RECALL = "recall"      # 检索缓存 (Disk Cache)
    ARCHIVAL = "archival"  # 归档存储 (Cold Storage)


class MemoryType(str, Enum):
    CONVERSATION = "conversation"   # 对话记忆
    TASK = "task"                   # 任务记忆
    SKILL = "skill"                 # 技能记忆
    KNOWLEDGE = "knowledge"         # 知识记忆
    EXPERIENCE = "experience"       # 经验记忆
    USER_PREFERENCE = "user_preference"  # 用户偏好
    EXECUTION_TRACE = "execution_trace"  # 执行轨迹
    EVOLUTION = "evolution"         # 进化记忆
    SYSTEM = "system"               # 系统记忆


# ============================================================
# 记忆条目
# ============================================================

@dataclass
class MemoryEntry:
    """一条记忆"""
    memory_id: str
    content: str
    memory_type: MemoryType
    tier: MemoryTier = MemoryTier.CORE

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expire_at: Optional[str] = None

    # 元数据
    source: str = ""               # 来源 (task_id, conversation_id, loop_id)
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5        # 重要性 0-1
    access_count: int = 0

    # MemRL 效用评分
    utility_score: float = 0.5     # RL效用评分
    confidence: float = 0.5        # 置信度

    # 嵌入向量 (用于语义检索)
    embedding: Optional[List[float]] = None

    # 关联
    related_memories: List[str] = field(default_factory=list)  # 关联记忆ID列表
    parent_memory_id: Optional[str] = None  # 父记忆 (如果是从其他记忆总结的)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "tier": self.tier.value,
            "created_at": self.created_at,
            "last_accessed_at": self.last_accessed_at,
            "expire_at": self.expire_at,
            "source": self.source,
            "tags": self.tags,
            "importance": self.importance,
            "access_count": self.access_count,
            "utility_score": self.utility_score,
            "confidence": self.confidence,
            "related_memories": self.related_memories,
            "parent_memory_id": self.parent_memory_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEntry":
        return cls(
            memory_id=data["memory_id"],
            content=data["content"],
            memory_type=MemoryType(data["memory_type"]),
            tier=MemoryTier(data["tier"]),
            created_at=data.get("created_at", ""),
            last_accessed_at=data.get("last_accessed_at", ""),
            expire_at=data.get("expire_at"),
            source=data.get("source", ""),
            tags=data.get("tags", []),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
            utility_score=data.get("utility_score", 0.5),
            confidence=data.get("confidence", 0.5),
            related_memories=data.get("related_memories", []),
            parent_memory_id=data.get("parent_memory_id"),
        )


# ============================================================
# 记忆操作系统
# ============================================================

class MemoryOS:
    """
    Memory OS — 记忆操作系统

    实现:
    - Letta/MemGPT三层记忆架构
    - MemRL Two-Phase检索 (快速过滤 + 效用评分)
    - 自动记忆生命周期管理 (创建→访问→衰退→巩固→归档)
    - 记忆压缩与去重
    - 35%+ token节省 (通过精准记忆检索)
    """

    def __init__(
        self,
        storage_dir: str = "data/memory_os",
        core_max_items: int = 50,
        recall_max_items: int = 500,
        archival_max_items: int = 10000,
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 容量限制
        self.core_max_items = core_max_items
        self.recall_max_items = recall_max_items
        self.archival_max_items = archival_max_items

        # 三层记忆存储
        self._core: Dict[str, MemoryEntry] = {}       # 核心内存
        self._recall: Dict[str, MemoryEntry] = {}     # 检索缓存
        self._archival: Dict[str, MemoryEntry] = {}   # 归档存储

        # 索引
        self._tag_index: Dict[str, List[str]] = {}    # 标签→记忆ID
        self._type_index: Dict[str, List[str]] = {}   # 类型→记忆ID

        # 加载
        self._load_all()

    # ============================================================
    # CRUD
    # ============================================================

    def store(
        self,
        content: str,
        memory_type: MemoryType,
        tier: MemoryTier = MemoryTier.CORE,
        source: str = "",
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        related_memories: Optional[List[str]] = None,
    ) -> MemoryEntry:
        """存储一条记忆"""
        memory_id = self._generate_id(content, memory_type, source)

        entry = MemoryEntry(
            memory_id=memory_id,
            content=content,
            memory_type=memory_type,
            tier=tier,
            source=source,
            tags=tags or [],
            importance=importance,
            related_memories=related_memories or [],
        )

        self._place_in_tier(entry)
        self._update_indexes(entry, add=True)
        self._save_tier(tier)

        logger.debug(f"存储记忆: {memory_id} → {tier.value}")
        return entry

    def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """检索单条记忆"""
        for storage in [self._core, self._recall, self._archival]:
            if memory_id in storage:
                entry = storage[memory_id]
                entry.access_count += 1
                entry.last_accessed_at = datetime.now(timezone.utc).isoformat()
                return entry
        return None

    def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        importance: Optional[float] = None,
        utility_score: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[MemoryEntry]:
        """更新记忆"""
        entry = self.retrieve(memory_id)
        if entry is None:
            return None

        if content is not None:
            entry.content = content
        if importance is not None:
            entry.importance = importance
        if utility_score is not None:
            entry.utility_score = utility_score
        if tags is not None:
            entry.tags = tags

        # 可能触发层级迁移
        self._check_tier_migration(entry)
        self._save_tier(entry.tier)

        return entry

    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        for storage in [self._core, self._recall, self._archival]:
            if memory_id in storage:
                entry = storage.pop(memory_id)
                self._update_indexes(entry, add=False)
                self._save_tier(entry.tier)
                return True
        return False

    # ============================================================
    # 智能检索 (MemRL Two-Phase)
    # ============================================================

    def search(
        self,
        query: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        tags: Optional[List[str]] = None,
        min_importance: float = 0.0,
        min_utility: float = 0.0,
        top_k: int = 10,
        use_rl_ranking: bool = True,
    ) -> List[MemoryEntry]:
        """
        MemRL Two-Phase检索:

        Phase 1: 快速过滤 (基于标签、类型、重要性预筛选)
        Phase 2: 效用评分 (基于RL训练的utility_score排序, 选择最优策略)
        """
        # Phase 1: 快速过滤
        candidates: List[MemoryEntry] = []

        # 标签索引
        if tags:
            for tag in tags:
                for mid in self._tag_index.get(tag, []):
                    entry = self.retrieve(mid)
                    if entry:
                        candidates.append(entry)
        else:
            # 从所有三层收集
            for storage in [self._core, self._recall, self._archival]:
                candidates.extend(storage.values())

        # 过滤
        if memory_type:
            candidates = [c for c in candidates if c.memory_type == memory_type]
        candidates = [c for c in candidates if c.importance >= min_importance]

        # 去重
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c.memory_id not in seen:
                seen.add(c.memory_id)
                unique_candidates.append(c)
        candidates = unique_candidates

        # Phase 2: 效用评分排序
        if use_rl_ranking:
            # 基于utility_score + 时间衰减 + 重要性
            now = datetime.now(timezone.utc)
            def memrl_score(entry: MemoryEntry) -> float:
                try:
                    created = datetime.fromisoformat(entry.created_at)
                    age_days = (now - created).total_seconds() / 86400
                    # 时间衰减 (sigmoid)
                    time_decay = 1.0 / (1.0 + 0.1 * age_days)
                    # 综合评分: 效用 * 0.4 + 重要性 * 0.3 + 访问频率 * 0.2 + 时间衰减 * 0.1
                    return (
                        entry.utility_score * 0.4 +
                        entry.importance * 0.3 +
                        min(entry.access_count / 100, 1.0) * 0.2 +
                        time_decay * 0.1
                    )
                except Exception:
                    return entry.utility_score

            candidates.sort(key=memrl_score, reverse=True)
        else:
            candidates.sort(key=lambda e: e.importance, reverse=True)

        # 更新访问时间
        for entry in candidates[:top_k]:
            entry.access_count += 1
            entry.last_accessed_at = datetime.now(timezone.utc).isoformat()

        return candidates[:top_k]

    def search_by_type(self, memory_type: MemoryType, top_k: int = 20) -> List[MemoryEntry]:
        """按类型检索"""
        mids = self._type_index.get(memory_type.value, [])
        entries = []
        for mid in mids:
            entry = self.retrieve(mid)
            if entry:
                entries.append(entry)
        entries.sort(key=lambda e: e.importance, reverse=True)
        return entries[:top_k]

    # ============================================================
    # 层级管理 (Letta/MemGPT风格)
    # ============================================================

    def _place_in_tier(self, entry: MemoryEntry):
        """将记忆放入对应层级"""
        if entry.tier == MemoryTier.CORE:
            self._core[entry.memory_id] = entry
            self._evict_if_needed(MemoryTier.CORE)
        elif entry.tier == MemoryTier.RECALL:
            self._recall[entry.memory_id] = entry
            self._evict_if_needed(MemoryTier.RECALL)
        else:
            self._archival[entry.memory_id] = entry
            self._evict_if_needed(MemoryTier.ARCHIVAL)

    def _check_tier_migration(self, entry: MemoryEntry):
        """检查是否需要层级迁移"""
        # 高重要性 + 高访问次数 → 升级到Core
        if entry.importance > 0.8 and entry.access_count > 10:
            if entry.tier != MemoryTier.CORE:
                self._migrate(entry, MemoryTier.CORE)

        # 低重要性 + 低访问次数 → 降级到Archival
        elif entry.importance < 0.2 and entry.access_count < 3:
            if entry.tier == MemoryTier.CORE:
                self._migrate(entry, MemoryTier.RECALL)
            elif entry.tier == MemoryTier.RECALL:
                self._migrate(entry, MemoryTier.ARCHIVAL)

    def _migrate(self, entry: MemoryEntry, target_tier: MemoryTier):
        """迁移记忆到目标层级"""
        old_tier = entry.tier

        # 从旧层级移除
        if old_tier == MemoryTier.CORE:
            self._core.pop(entry.memory_id, None)
        elif old_tier == MemoryTier.RECALL:
            self._recall.pop(entry.memory_id, None)
        else:
            self._archival.pop(entry.memory_id, None)

        # 放入新层级
        entry.tier = target_tier
        self._place_in_tier(entry)

        logger.info(f"记忆迁移: {entry.memory_id} {old_tier.value} → {target_tier.value}")

    def _evict_if_needed(self, tier: MemoryTier):
        """容量淘汰"""
        storage = self._get_storage(tier)
        max_items = {
            MemoryTier.CORE: self.core_max_items,
            MemoryTier.RECALL: self.recall_max_items,
            MemoryTier.ARCHIVAL: self.archival_max_items,
        }[tier]

        if len(storage) <= max_items:
            return

        # LRU淘汰: 按最后访问时间排序
        entries = sorted(
            storage.values(),
            key=lambda e: (e.importance, e.last_accessed_at),
        )
        to_evict = entries[:len(storage) - max_items]

        for entry in to_evict:
            if tier == MemoryTier.CORE:
                # Core → Recall
                self._migrate(entry, MemoryTier.RECALL)
            elif tier == MemoryTier.RECALL:
                # Recall → Archival (压缩)
                self._migrate(entry, MemoryTier.ARCHIVAL)
            else:
                # Archival → 删除
                self.delete(entry.memory_id)

    def _get_storage(self, tier: MemoryTier) -> Dict[str, MemoryEntry]:
        return {
            MemoryTier.CORE: self._core,
            MemoryTier.RECALL: self._recall,
            MemoryTier.ARCHIVAL: self._archival,
        }[tier]

    # ============================================================
    # 记忆巩固 (Consolidation)
    # ============================================================

    def consolidate(self):
        """
        记忆巩固 — 短期→长期记忆转换

        - 将Core中过期的记忆迁移到Recall
        - 将Recall中长时间未访问的迁移到Archival
        - 将相似记忆合并总结
        - 清理过期记忆
        """
        now = datetime.now(timezone.utc)
        consolidated = 0

        # Core → Recall: 超过1小时未访问
        for entry in list(self._core.values()):
            try:
                last_access = datetime.fromisoformat(entry.last_accessed_at)
                if (now - last_access) > timedelta(hours=1):
                    self._migrate(entry, MemoryTier.RECALL)
                    consolidated += 1
            except Exception:
                pass

        # Recall → Archival: 超过7天未访问
        for entry in list(self._recall.values()):
            try:
                last_access = datetime.fromisoformat(entry.last_accessed_at)
                if (now - last_access) > timedelta(days=7):
                    self._migrate(entry, MemoryTier.ARCHIVAL)
                    consolidated += 1
            except Exception:
                pass

        # 清理明确过期的记忆
        for entry in list(self._recall.values()):
            if entry.expire_at:
                try:
                    expire = datetime.fromisoformat(entry.expire_at)
                    if now > expire:
                        self.delete(entry.memory_id)
                        consolidated += 1
                except Exception:
                    pass

        if consolidated > 0:
            logger.info(f"记忆巩固完成: {consolidated} 条记忆处理")

        return consolidated

    def consolidate_by_type(self, memory_type: MemoryType):
        """
        按类型巩固 — 将同类型Core记忆合并为Archival摘要
        GenericAgent风格: 将执行路径结晶为技能
        """
        core_entries = [
            e for e in self._core.values()
            if e.memory_type == memory_type
        ]

        if len(core_entries) < 3:
            return

        # 合并为摘要
        contents = [e.content for e in core_entries]
        summary = self._summarize(contents)

        # 存储摘要到Archival
        self.store(
            content=summary,
            memory_type=memory_type,
            tier=MemoryTier.ARCHIVAL,
            source="consolidation",
            tags=[memory_type.value, "summary"],
            importance=0.7,
            related_memories=[e.memory_id for e in core_entries],
        )

        # 标记原始记忆的父级
        for e in core_entries:
            e.parent_memory_id = summary

        logger.info(f"巩固 {memory_type.value}: {len(core_entries)} → 1 摘要")

    def _summarize(self, contents: List[str]) -> str:
        """简单合并 (实际由LLM完成)"""
        return " | ".join(contents[:5])

    # ============================================================
    # MemRL 效用更新
    # ============================================================

    def update_utility(self, memory_id: str, reward: float):
        """
        MemRL: 更新记忆效用评分

        基于环境反馈(reward)更新utility_score
        使用指数移动平均: new_score = old_score * 0.9 + reward * 0.1
        """
        entry = self.retrieve(memory_id)
        if entry:
            entry.utility_score = entry.utility_score * 0.9 + reward * 0.1
            entry.utility_score = max(0.0, min(1.0, entry.utility_score))
            self._save_tier(entry.tier)

    # ============================================================
    # 统计
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        return {
            "core_size": len(self._core),
            "recall_size": len(self._recall),
            "archival_size": len(self._archival),
            "total": len(self._core) + len(self._recall) + len(self._archival),
            "by_type": {
                mt.value: len(self.search_by_type(mt, top_k=10000))
                for mt in MemoryType
            },
            "core_capacity": self.core_max_items,
            "recall_capacity": self.recall_max_items,
            "archival_capacity": self.archival_max_items,
        }

    # ============================================================
    # 内部辅助
    # ============================================================

    def _generate_id(self, content: str, memory_type: MemoryType, source: str) -> str:
        raw = f"{content}_{memory_type.value}_{source}_{time.time()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def _update_indexes(self, entry: MemoryEntry, add: bool = True):
        """更新索引"""
        # 标签索引
        for tag in entry.tags:
            if add:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                if entry.memory_id not in self._tag_index[tag]:
                    self._tag_index[tag].append(entry.memory_id)
            else:
                if tag in self._tag_index:
                    self._tag_index[tag] = [
                        mid for mid in self._tag_index[tag]
                        if mid != entry.memory_id
                    ]

        # 类型索引
        if add:
            if entry.memory_type.value not in self._type_index:
                self._type_index[entry.memory_type.value] = []
            if entry.memory_id not in self._type_index[entry.memory_type.value]:
                self._type_index[entry.memory_type.value].append(entry.memory_id)
        else:
            if entry.memory_type.value in self._type_index:
                self._type_index[entry.memory_type.value] = [
                    mid for mid in self._type_index[entry.memory_type.value]
                    if mid != entry.memory_id
                ]

    def _save_tier(self, tier: MemoryTier):
        """持久化单一层级"""
        storage = self._get_storage(tier)
        file_path = self.storage_dir / f"{tier.value}.json"
        data = {mid: entry.to_dict() for mid, entry in storage.items()}
        file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _load_all(self):
        """加载所有层级"""
        for tier in MemoryTier:
            file_path = self.storage_dir / f"{tier.value}.json"
            if file_path.exists():
                try:
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    storage = self._get_storage(tier)
                    for mid, entry_data in data.items():
                        entry = MemoryEntry.from_dict(entry_data)
                        storage[mid] = entry
                        self._update_indexes(entry, add=True)
                    logger.info(f"加载 {tier.value} 记忆: {len(storage)} 条")
                except Exception as e:
                    logger.warning(f"加载 {tier.value} 记忆失败: {e}")

    def save_all(self):
        """保存所有层级"""
        for tier in MemoryTier:
            self._save_tier(tier)


# ============================================================
# 记忆工厂
# ============================================================

class MemoryFactory:
    """记忆工厂 — 从各种源创建记忆条目"""

    def __init__(self, memory_os: MemoryOS):
        self.memory_os = memory_os

    def from_conversation(
        self, content: str, source: str = "", importance: float = 0.5
    ) -> MemoryEntry:
        return self.memory_os.store(
            content=content,
            memory_type=MemoryType.CONVERSATION,
            tier=MemoryTier.CORE,
            source=source,
            tags=["conversation"],
            importance=importance,
        )

    def from_task_result(
        self, content: str, task_id: str, success: bool = True
    ) -> MemoryEntry:
        return self.memory_os.store(
            content=content,
            memory_type=MemoryType.TASK,
            tier=MemoryTier.RECALL,
            source=task_id,
            tags=["task", "success" if success else "failure"],
            importance=0.7 if success else 0.9,  # 失败记忆更重要
        )

    def from_execution_trace(
        self, trace: str, loop_id: str
    ) -> MemoryEntry:
        return self.memory_os.store(
            content=trace,
            memory_type=MemoryType.EXECUTION_TRACE,
            tier=MemoryTier.RECALL,
            source=loop_id,
            tags=["trace", "execution"],
            importance=0.6,
        )

    def from_evolution(
        self, content: str, evolution_id: str
    ) -> MemoryEntry:
        return self.memory_os.store(
            content=content,
            memory_type=MemoryType.EVOLUTION,
            tier=MemoryTier.ARCHIVAL,
            source=evolution_id,
            tags=["evolution", "gene"],
            importance=0.8,
        )

    def from_user_preference(
        self, content: str
    ) -> MemoryEntry:
        return self.memory_os.store(
            content=content,
            memory_type=MemoryType.USER_PREFERENCE,
            tier=MemoryTier.CORE,
            tags=["user", "preference"],
            importance=0.9,
        )