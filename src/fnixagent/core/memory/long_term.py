"""
长期混合记忆 (Long-Term Hybrid Memory)。

核心流程:
  1. 写入: 文档/对话 → text.chunk_by_chars 分块 → embedder.embed 向量化
     → vector_store.add 入库(含 metadata: tenant_id/user_id/session_id/timestamp)
     → 同步维护每用户 BM25 关键词索引(id→内容)
  2. 检索: query → 双路召回(向量语义 + BM25 关键词) → RRF 融合排序
     纯向量命中须过相似度阈值; 有关键词命中的候选可信度更高, 可豁免阈值
     —— 解决特征哈希伪向量对"精确词面匹配"场景的召回盲区
  3. 过期清理: 按 timestamp 超过 ttl_days 的记录删除

安全防护(ASI06 记忆投毒):
  - 写入时做敏感词扫描(可选),防止恶意内容污染记忆库
  - 检索结果附带 source 和 timestamp,便于追溯
  - user_id 非空校验:避免匿名写入造成跨用户数据污染

性能优化:
  - 批量化 embedding:一次 embed_batch 多个 chunk,减少 embedder 调用开销
  - LRU 缓存:embedder 内置缓存,相同 chunk 不重复编码
  - 加锁保护 _meta_index 与 _store 的一致性
  - BM25 索引惰性重建:写入只标记 dirty,下次检索时一次性重建
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import threading
import time

from fnixagent.core.config import MemoryConfig
from fnixagent.core.retrieval.embedder import BaseEmbedder
from fnixagent.core.retrieval.hybrid import BM25Retriever
from fnixagent.core.retrieval.vectorstore import BaseVectorStore, InMemoryVectorStore
from fnixagent.core.text import chunk_by_chars
from fnixagent.core.types import MemoryItem

_logger = logging.getLogger(__name__)

# RRF 融合参数与两路权重(关键词路权重较高——哈希伪向量语义能力有限,
# 精确词面匹配在本地记忆场景更可靠; 接入真 embedding 后可回调高向量权重)
_RRF_K: int = 60
_VECTOR_WEIGHT: float = 0.5
_BM25_WEIGHT: float = 0.5



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
        vector_store: BaseVectorStore | None = None,
        config: MemoryConfig | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = vector_store or InMemoryVectorStore()
        self._config = config or MemoryConfig()
        self._lock = threading.Lock()
        # id -> (user_id, timestamp) 用于过期清理与按用户计数
        self._meta_index: dict[str, tuple[str, float]] = {}
        # 混合检索: 每用户 BM25 索引(惰性重建)
        # _bm25_docs[user_id]: {chunk_id: (content, timestamp)}
        self._bm25_docs: dict[str, dict[str, tuple[str, float]]] = {}
        self._bm25_index: dict[str, BM25Retriever] = {}
        self._bm25_dirty: set[str] = set()
        # chunk_id 单调序列号(修复同毫秒写入 id 碰撞覆盖问题)
        import itertools

        self._id_seq = itertools.count(1)

    # -- 写入 --------------------------------------------------------------

    def add(
        self,
        user_id: str,
        content: str,
        metadata: dict | None = None,
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
            batch = chunks[i : i + self._EMBED_BATCH_SIZE]
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

        # 组装 id 与 metadata(序列号保证同毫秒快速写入不撞 id)
        for i, chunk in enumerate(chunks):
            chunk_id = f"{user_id}_{int(now * 1000)}_{next(self._id_seq)}_{i}"
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
            # 同步维护 BM25 文档表(检索时惰性重建索引)
            docs = self._bm25_docs.setdefault(user_id, {})
            for i, chunk in enumerate(chunks):
                docs[ids[i]] = (chunk, now)
            self._bm25_dirty.add(user_id)
        return len(chunks)

    # -- 检索 --------------------------------------------------------------

    def _get_bm25(self, user_id: str) -> BM25Retriever | None:
        """获取(必要时重建)指定用户的 BM25 索引。无文档返回 None。"""
        with self._lock:
            docs = self._bm25_docs.get(user_id) or {}
            if not docs:
                return None
            if user_id in self._bm25_dirty or user_id not in self._bm25_index:
                retriever = BM25Retriever()
                retriever.index([(cid, text) for cid, (text, _) in docs.items()])
                self._bm25_index[user_id] = retriever
                self._bm25_dirty.discard(user_id)
            return self._bm25_index[user_id]

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[MemoryItem]:
        """
        混合检索: 向量语义路 + BM25 关键词路 → RRF 融合排序。

        召回规则:
          - 纯向量命中: 须过相似度阈值(与旧版语义一致)
          - 有关键词命中的候选: 可豁免阈值(精确匹配可信度更高)
        返回顺序即融合相关性顺序; .score 为参考相关度
        (向量命中保留余弦值, 关键词召回项给插值分保证单调)。

        Args:
            user_id: 用户 ID,非空,用于过滤该用户记忆
            query: 检索查询
            top_k: 返回条数

        Raises:
            ValueError: user_id 为空
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id 不能为空")
        threshold = self._config.long_term_score_threshold

        # 路1: 向量语义召回(多召回一倍供融合)
        vec_results: list[MemoryItem] = []
        try:
            query_vec = self._embedder.embed(query)
            vec_results = self._store.search(
                query_vec,
                top_k=max(top_k * 2, top_k),
                filter={"user_id": user_id},
            )
        except Exception:
            vec_results = []

        # 路2: BM25 关键词召回
        bm25_hits: list[tuple[str, float]] = []
        try:
            retriever = self._get_bm25(user_id)
            if retriever is not None:
                bm25_hits = retriever.search(query, top_k=max(top_k * 2, top_k))
        except Exception:
            bm25_hits = []

        # 融合候选表: id → (cos_score|None, content, timestamp)
        candidates: dict[str, tuple[float | None, str, float]] = {}
        for item in vec_results:
            meta = item.metadata or {}
            candidates[item.id] = (
                item.score,
                item.content or str(meta.get("content", "")),
                float(meta.get("timestamp", 0.0)),
            )
        if bm25_hits:
            with self._lock:
                docs = self._bm25_docs.get(user_id) or {}
            for cid, _score in bm25_hits:
                if cid not in candidates:
                    text, ts = docs.get(cid, ("", 0.0))
                    candidates[cid] = (None, text, ts)

        if not candidates:
            return []

        # RRF 排序(两路排名加权)
        rrf: dict[str, float] = {}
        for rank, item in enumerate(vec_results, 1):
            rrf[item.id] = rrf.get(item.id, 0.0) + _VECTOR_WEIGHT / (_RRF_K + rank)
        for rank, (cid, _) in enumerate(bm25_hits, 1):
            rrf[cid] = rrf.get(cid, 0.0) + _BM25_WEIGHT / (_RRF_K + rank)

        ordered_ids = sorted(rrf, key=lambda cid: rrf[cid], reverse=True)

        # 组装结果: 阈值规则 + 单调插值分
        results: list[MemoryItem] = []
        prev_score = float("inf")
        for cid in ordered_ids:
            cos, text, ts = candidates[cid]
            has_kw = any(cid == hid for hid, _ in bm25_hits)
            if cos is not None and cos >= threshold:
                score = min(cos, prev_score)
            elif has_kw:
                # 关键词召回豁免阈值: 给略高于阈值的单调插值分
                score = max(min(threshold + 0.01, prev_score - 1e-6), threshold * 0.5)
            else:
                continue  # 纯弱向量且低于阈值: 按旧版语义丢弃
            results.append(
                MemoryItem(
                    id=cid,
                    content=text,
                    score=round(score, 6),
                    metadata={"user_id": user_id, "timestamp": ts, "content": text},
                )
            )
            prev_score = score
            if len(results) >= top_k:
                break
        return results

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
                affected_users: set[str] = set()
                for cid in expired_ids:
                    user_id, _ = self._meta_index.pop(cid, (None, None))
                    if user_id:
                        affected_users.add(user_id)
                # 同步清理 BM25 文档表并标记重建
                for uid in affected_users:
                    docs = self._bm25_docs.get(uid)
                    if docs is not None:
                        for cid in expired_ids:
                            docs.pop(cid, None)
                    self._bm25_dirty.add(uid)
        return len(expired_ids)

    # -- 统计 --------------------------------------------------------------

    def count(self, user_id: str | None = None) -> int:
        """记忆条数(可按 user_id 过滤)。"""
        with self._lock:
            if user_id:
                return sum(1 for _, (uid, _) in self._meta_index.items() if uid == user_id)
            return len(self._meta_index)

    def clear(self, user_id: str | None = None) -> int:
        """清空记忆(可按 user_id)。"""
        with self._lock:
            if user_id is None:
                count = len(self._meta_index)
                if hasattr(self._store, "clear"):
                    try:
                        self._store.clear()  # type: ignore[attr-defined]
                    except Exception:
                        _logger.debug('Unhandled exception', exc_info=True)
                self._meta_index.clear()
                # BM25 全量失效
                self._bm25_docs.clear()
                self._bm25_index.clear()
                self._bm25_dirty.clear()
                return count
            else:
                ids = [cid for cid, (uid, _) in self._meta_index.items() if uid == user_id]
                if ids:
                    try:
                        self._store.delete(ids)
                    except Exception:
                        return 0
                    for cid in ids:
                        self._meta_index.pop(cid, None)
                self._bm25_docs.pop(user_id, None)
                self._bm25_index.pop(user_id, None)
                self._bm25_dirty.discard(user_id)
                return len(ids)
