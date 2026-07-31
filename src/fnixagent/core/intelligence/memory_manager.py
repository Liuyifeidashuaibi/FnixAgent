"""L5 记忆层 (Memory Manager) — 对标 Letta/MemGPT。

核心思想 (Letta/MemGPT 范式):
  - Context = RAM:  当前对话上下文中的短期记忆
  - External = Disk: 持久化在外部的长期记忆
  - 系统自主管理记忆的写入、召回、巩固、遗忘

记忆类型 (对标认知科学):
  - episodic:   情景记忆 (具体任务执行经验)
  - semantic:   语义记忆 (提炼出的通用知识)
  - procedural: 程序记忆 (可复用的操作流程)
  - working:    工作记忆 (当前会话临时)

存储路径: {workspace}/.fnix/intelligence_memory/memories.json
零外部依赖 (无向量化, 与 self_optimizing.py 的 _tokenize 一致),
线程安全, 中文注释。

使用方式:
  >>> mgr = IntelligenceMemoryManager(workspace)
  >>> mgr.add_memory("task_x", "用户让重构模块X的方案", memory_type="episodic")
  >>> results = mgr.recall("重构 模块X")
  >>> mgr.consolidate()  # 短期记忆固化为长期
  >>> mgr.get_stats()
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 借鉴 self_optimizing.py 的 _STOPWORDS, 保持分词一致
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "to",
        "of",
        "and",
        "or",
        "in",
        "on",
        "for",
        "with",
        "by",
        "at",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "的",
        "了",
        "和",
        "是",
        "在",
        "我",
        "你",
        "他",
        "她",
        "它",
        "们",
        "个",
        "用",
        "把",
        "给",
        "对",
        "向",
        "从",
        "到",
        "于",
        "为",
        "与",
        "及",
        "或",
        "一",
        "二",
        "三",
        "这",
        "那",
        "有",
        "无",
        "要",
        "会",
        "能",
        "可",
        "可以",
    }
)


def _tokenize(text: str) -> set[str]:
    """简单分词: 英文按 \\w+, 中文按 2-3 字符滑窗。与 self_optimizing.py 一致。"""
    if not text:
        return set()
    tokens: set[str] = set()
    for m in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", text.lower()):
        if m not in _STOPWORDS and len(m) >= 2:
            tokens.add(m)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for seg in chinese:
        if len(seg) >= 2:
            tokens.add(seg[:2])
            if len(seg) >= 3:
                tokens.add(seg[:3])
    return tokens


# 支持的记忆类型
_VALID_TYPES = frozenset({"episodic", "semantic", "procedural", "working"})


@dataclass
class MemoryEntry:
    """一条记忆 (对标 MemGPT MemoryBlock 的轻量版)。"""

    memory_id: str
    key: str  # 记忆键 (任务签名/主题)
    content: str  # 记忆内容
    memory_type: str = "episodic"  # episodic/semantic/procedural/working
    created_at: float = 0.0
    last_accessed_at: float = 0.0
    access_count: int = 0
    importance: float = 0.5  # 0.0-1.0, 巩固时按此排序
    consolidated: bool = False  # 是否已固化为长期记忆
    tags: list[str] = field(default_factory=list)


class IntelligenceMemoryManager:
    """Intelligence 七层 L5 记忆层 — 持久化记忆管理。

    存储路径: {workspace}/.fnix/intelligence_memory/memories.json
    线程安全, 零外部依赖。

    对标 Letta/MemGPT:
      - recall()   ≈ MemGPT 的 context_window 检索
      - add_memory() ≈ MemGPT 的 memory_write
      - consolidate() ≈ MemGPT 的 memory_consolidation (短期→长期)
    """

    def __init__(self, workspace: str, state_dir: str = None):
        self.workspace = str(Path(workspace or "").expanduser().resolve())
        # state_dir 优先; 否则落到 workspace 下 .fnix/intelligence_memory
        if state_dir:
            self.dir = Path(state_dir)
        else:
            self.dir = Path(self.workspace) / ".fnix" / "intelligence_memory"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = self.dir / "memories.json"
        self.memories: list[MemoryEntry] = []
        self._lock = threading.RLock()
        self._load()

    # ============================================================
    # 持久化
    # ============================================================

    def _load(self) -> None:
        """从磁盘加载记忆"""
        with self._lock:
            if not self.file.exists():
                self.memories = []
                return
            try:
                data = json.loads(self.file.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    self.memories = []
                    return
                entries: list[MemoryEntry] = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    try:
                        entries.append(
                            MemoryEntry(
                                **{
                                    k: v
                                    for k, v in item.items()
                                    if k in MemoryEntry.__dataclass_fields__
                                }
                            )
                        )
                    except TypeError:
                        continue
                self.memories = entries
            except (OSError, ValueError):
                self.memories = []

    def _save(self) -> None:
        """持久化到磁盘 (失败静默, 不阻塞主路径)"""
        try:
            self.file.write_text(
                json.dumps(
                    [asdict(e) for e in self.memories],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ============================================================
    # 核心 API
    # ============================================================

    def add_memory(
        self,
        key: str,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> MemoryEntry | None:
        """写入持久化记忆。

        - 相同 key 覆盖 (对标 Voyager 同名覆盖)
        - memory_type 限定为 episodic/semantic/procedural/working
        - working 类型不固化, consolidate 时会被清理
        """
        if not key or not content:
            return None
        mtype = memory_type if memory_type in _VALID_TYPES else "episodic"
        now = time.time()
        entry = MemoryEntry(
            memory_id=f"mem_{hashlib.md5(f'{key}_{now}'.encode()).hexdigest()[:12]}",
            key=key.strip()[:200],
            content=content[:4000],
            memory_type=mtype,
            created_at=now,
            last_accessed_at=now,
            importance=max(0.0, min(1.0, float(importance))),
            tags=list(tags) if tags else [],
        )
        with self._lock:
            # 相同 key 覆盖旧记忆
            self.memories = [m for m in self.memories if m.key != entry.key]
            self.memories.append(entry)
            self._save()
        return entry

    def recall(self, query: str, top_k: int = 5) -> list[dict]:
        """简单关键词召回 (无向量化, 与 self_optimizing.py 一致)。

        评分: Jaccard 相似度 * importance * 时间衰减(30天半衰期)
        返回 list[dict], 每项含 key/content/memory_type/score。
        """
        if not self.memories or not query or not query.strip():
            return []
        qt = _tokenize(query)
        if not qt:
            return []
        with self._lock:
            scored: list[tuple[float, MemoryEntry]] = []
            for m in self.memories:
                # 同时匹配 key 和 content
                mt = _tokenize(m.key) | _tokenize(m.content)
                inter = len(qt & mt)
                if inter == 0:
                    continue
                sim = inter / max(len(qt | mt), 1)
                sim *= 0.5 + 0.5 * m.importance
                age_days = (time.time() - m.created_at) / 86400.0
                sim *= 0.5 ** (age_days / 30.0)
                scored.append((sim, m))
            scored.sort(key=lambda x: -x[0])
            result: list[dict] = []
            now = time.time()
            for sim, m in scored[: max(0, top_k)]:
                m.access_count += 1
                m.last_accessed_at = now
                result.append(
                    {
                        "memory_id": m.memory_id,
                        "key": m.key,
                        "content": m.content,
                        "memory_type": m.memory_type,
                        "score": round(sim, 4),
                        "importance": m.importance,
                    }
                )
            if result:
                self._save()
            return result

    def consolidate(self) -> dict:
        """把短期记忆固化为长期记忆 (对标 MemGPT memory_consolidation)。

        策略:
          1. working (工作记忆) 清理 (太短期, 不保留)
          2. episodic 高频访问且 importance>=0.6 → 标记 consolidated, 升级为 semantic
          3. 去重: 相似 key 合并保留 importance 最高的
        返回固化统计。
        """
        with self._lock:
            before = len(self.memories)
            # 1. 清理 working 记忆 (仅保留非 working)
            kept = [m for m in self.memories if m.memory_type != "working"]
            removed_working = before - len(kept)

            # 2. 高价值 episodic → semantic 并标记固化
            consolidated_count = 0
            for m in kept:
                if (
                    m.memory_type == "episodic"
                    and not m.consolidated
                    and m.importance >= 0.6
                    and m.access_count >= 1
                ):
                    m.memory_type = "semantic"
                    m.consolidated = True
                    consolidated_count += 1

            # 3. 按 key 去重 (相同 key 保留 importance 最高的)
            by_key: dict[str, MemoryEntry] = {}
            for m in kept:
                existing = by_key.get(m.key)
                if existing is None or m.importance > existing.importance:
                    by_key[m.key] = m
            deduped = list(by_key.values())
            dedup_removed = len(kept) - len(deduped)

            self.memories = deduped
            self._save()
            return {
                "before_total": before,
                "after_total": len(self.memories),
                "working_removed": removed_working,
                "consolidated_to_semantic": consolidated_count,
                "dedup_removed": dedup_removed,
            }

    def get_stats(self) -> dict:
        """统计"""
        with self._lock:
            by_type: dict[str, int] = {}
            for m in self.memories:
                by_type[m.memory_type] = by_type.get(m.memory_type, 0) + 1
            return {
                "total": len(self.memories),
                "by_type": by_type,
                "consolidated": sum(1 for m in self.memories if m.consolidated),
                "avg_importance": (
                    sum(m.importance for m in self.memories) / len(self.memories)
                    if self.memories
                    else 0.0
                ),
            }


__all__ = [
    "IntelligenceMemoryManager",
    "MemoryEntry",
]
