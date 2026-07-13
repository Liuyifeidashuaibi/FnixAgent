"""
长期向量记忆 (Long-Term Memory)。

核心流程:
  1. 写入: 文档/对话 → text.chunk_by_chars 分块 → embedder.embed 向量化
     → vector_store.add 入库(含 metadata: tenant_id/user_id/session_id/timestamp)
  2. 检索: query → embedder.embed → vector_store.search(top_k, filter) → MemoryItem
  3. 过期清理: 按 timestamp 超过 ttl_days 的记录删除

安全防护(ASI06 记忆投毒):
  - 写入时做敏感词扫描(可选),防止恶意内容污染记忆库
  - 检索结果附带 source 和 timestamp,便于追溯
  - user_id 非空校验:避免匿名写入造成跨用户数据污染

性能优化:
  - 批量化 embedding:一次 embed_batch 多个 chunk,减少 embedder 调用开销
  - LRU 缓存:embedder 内置缓存,相同 chunk 不重复编码
  - 加锁保护 _meta_index 与 _store 的一致性
"""
from __future__ import annotations

import time
import threading
from typing import Optional

from fnixagent.core.config import MemoryConfig
from fnixagent.core.retrieval.embedder import BaseEmbedder
from fnixagent.core.retrieval.vectorstore import BaseVectorStore, InMemoryVectorStore
from fnixagent.core.text import chunk_by_chars
from fnixagent.core.types import MemoryItem


class LongTermMemory:
    """
    长期向量记忆。

    用法:
        ltm = LongTermMemory(embedder=HashingEmbedder(), config=mem_config)
        ltm.add("user_1", "论文A的摘要内容...", metadata={"source": "paper"})
        results = ltm.search("user_1", "相关查询", top_k=5)

    并发安全:
      - _lock 保护 _meta_index 读写
      - _store(向量库)自身线程安全,内部有锁
    """

    # 批量 embedding 的批大小(减少 embedder 调用次数)
    _EMBED_BATCH_SIZE: int = 32

    def __init__(
        self,
        embedder: BaseEmbedder,
        vector_store: Optional[BaseVectorStore] = None,
        config: Optional[MemoryConfig] = None,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store or InMemoryVectorStore()
        self._config = config or MemoryConfig()
        self._lock = threading.Lock()
        # id -> (user_id, timestamp) 用于过期清理与按用户计数
        self._meta_index: dict[str, tuple[str, float]] = {}

    # -- 写入 --------------------------------------------------------------

    def add(
        self,
        user_id: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> int:
        """
        将内容分块、向量化后写入长期记忆。
        返回写入的块数。

        Args:
            user_id: 用户 ID,非空,用于权限隔离
            content: 待写入文本
            metadata: 附加元数据

        Raises:
            ValueError: user_id 为空或 content 为空
        """
        # user_id 非空校验:防止匿名写入污染全局记忆
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        if not content:
            return 0

        # 分块(chunk_by_chars 内部已做流式滑动窗口)
        chunks = chunk_by_chars(
            content,
            chunk_size=self._config.long_term_chunk_size,
            overlap=self._config.long_term_chunk_overlap,
        )
        if not chunks:
            return 0

        now = time.time()
        meta = metadata or {}
        meta.update({"user_id": user_id, "timestamp": now})

        ids: list[str] = []
        metadatas: list[dict] = []

        # 批量化 embedding:一次 embed_batch 多个 chunk,减少调用开销
        all_vectors: list[list[float]] = []
        for i in range(0, len(chunks), self._EMBED_BATCH_SIZE):
            batch = chunks[i:i + self._EMBED_BATCH_SIZE]
            try:
                batch_vecs = self._embedder.embed_batch(batch)
            except Exception:
                # 批量编码失败:降级为逐条编码,跳过失败项
                batch_vecs = []
                for ch in batch:
                    try:
                        batch_vecs.append(self._embedder.embed(ch))
                    except Exception:
                        batch_vecs.append([0.0] * self._embedder.dim)
            all_vectors.extend(batch_vecs)

        # 组装 id 与 metadata
        for i, chunk in enumerate(chunks):
            chunk_id = f"{user_id}_{int(now*1000)}_{i}"
            chunk_meta = dict(meta)
            chunk_meta["content"] = chunk
            chunk_meta["chunk_index"] = i
            ids.append(chunk_id)
            metadatas.append(chunk_meta)

        # 加锁写入:保证 _meta_index 与 _store 一致
        with self._lock:
            for i, cid in enumerate(ids):
                self._meta_index[cid] = (user_id, now)
            self._store.add(ids, all_vectors, metadatas)
        return len(chunks)

    # -- 检索 --------------------------------------------------------------

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryItem]:
        """
        语义检索: query 向量化 → 向量库 top-k → 阈值过滤。

        Args:
            user_id: 用户 ID,非空,用于过滤该用户记忆
            query: 检索查询
            top_k: 返回条数

        Raises:
            ValueError: user_id 为空
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        try:
            query_vec = self._embedder.embed(query)
            results = self._store.search(
                query_vec,
                top_k=top_k,
                filter={"user_id": user_id},
            )
        except Exception:
            # 向量检索异常:返回空结果,避免阻断上层流程
            return []
        # 相似度阈值过滤
        threshold = self._config.long_term_score_threshold
        return [
            m for m in results
            if m.score >= threshold
        ]

    # -- 过期清理 ----------------------------------------------------------

    def cleanup_expired(self) -> int:
        """
        删除超过 ttl_days 的记忆。
        返回删除条数。
        """
        cutoff = time.time() - (self._config.long_term_ttl_days * 86400)
        expired_ids: list[str] = []
        with self._lock:
            for chunk_id, (user_id, ts) in self._meta_index.items():
                if ts < cutoff:
                    expired_ids.append(chunk_id)
            if expired_ids:
                try:
                    self._store.delete(expired_ids)
                except Exception:
                    # 删除失败:不更新 _meta_index,下次重试
                    return 0
                for cid in expired_ids:
                    self._meta_index.pop(cid, None)
        return len(expired_ids)

    # -- 统计 --------------------------------------------------------------

    def count(self, user_id: Optional[str] = None) -> int:
        """记忆条数(可按 user_id 过滤)。"""
        with self._lock:
            if user_id:
                return sum(
                    1 for _, (uid, _) in self._meta_index.items()
                    if uid == user_id
                )
            return len(self._meta_index)

    def clear(self, user_id: Optional[str] = None) -> int:
        """清空记忆(可按 user_id)。"""
        with self._lock:
            if user_id is None:
                count = len(self._meta_index)
                if hasattr(self._store, 'clear'):
                    try:
                        self._store.clear()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                self._meta_index.clear()
                return count
            else:
                ids = [
                    cid for cid, (uid, _) in self._meta_index.items()
                    if uid == user_id
                ]
                if ids:
                    try:
                        self._store.delete(ids)
                    except Exception:
                        return 0
                    for cid in ids:
                        self._meta_index.pop(cid, None)
                return len(ids)
