"""
混合检索 (Hybrid Retrieval)。

包含两个核心算法:
  1. BM25Retriever — Okapi BM25 关键词检索算法
  2. HybridRetriever — 向量+关键词融合检索,用 RRF 融合排序

== BM25 算法 ==
Okapi BM25 是经典基于词频的检索排序函数:
  score(q, d) = sum_{t in q} IDF(t) * (tf(t,d) * (k1+1)) / (tf(t,d) + k1*(1 - b + b*|d|/avgdl))
其中:
  - IDF(t) = ln(1 + (N - n(t) + 0.5) / (n(t) + 0.5))   (N=文档总数, n(t)=包含t的文档数)
  - tf(t,d): 词 t 在文档 d 中的频次
  - |d|: 文档 d 的长度(词数)
  - avgdl: 全部文档的平均长度
  - k1=1.5: 词频饱和参数(控制 tf 的上限)
  - b=0.75: 文档长度归一化参数(0=不归一,1=完全归一)

== RRF 融合算法 ==
Reciprocal Rank Fusion:
  给定多路检索结果,每路返回的文档有一个排名 rank(从1开始),
  融合分数 = sum_{each ranklist} 1 / (k + rank_i)
  k 为平滑常数(默认60),降低高排名的权重,使各路更均衡。
  最终按融合分数降序排列。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import math
from collections import Counter, defaultdict

from fnixagent.core.retrieval.embedder import BaseEmbedder
from fnixagent.core.retrieval.vectorstore import BaseVectorStore
from fnixagent.core.text import tokenize
from fnixagent.core.types import MemoryItem

# ---------------------------------------------------------------------------
# BM25 关键词检索
# ---------------------------------------------------------------------------


class BM25Retriever:
    """
    Okapi BM25 关键词检索器。

    纯 Python 实现,无外部依赖。
    支持 index + search 两阶段: 先建索引,后查询。
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        # 参数校验:k1 控制词频饱和,b 控制文档长度归一化强度
        if k1 < 0:
            raise ValueError(f"k1 不能为负: {k1}")
        if not (0.0 <= b <= 1.0):
            raise ValueError(f"b 应在 [0,1] 区间: {b}")
        self._k1 = k1
        self._b = b
        # 索引数据
        self._doc_ids: list[str] = []
        self._doc_tokens: list[list[str]] = []  # 每篇文档的 token 列表
        self._doc_lengths: list[int] = []  # 每篇文档长度
        self._avgdl: float = 0.0  # 平均文档长度
        self._term_freqs: list[Counter] = []  # 每篇文档的词频
        self._df: dict[str, int] = defaultdict(int)  # 文档频率: 包含某词的文档数
        self._n_docs: int = 0
        self._idf_cache: dict[str, float] = {}

    def index(self, documents: list[tuple[str, str]]) -> None:
        """
        构建 BM25 索引。
        documents: [(doc_id, text), ...]

        索引构建复杂度 O(N * L),N 为文档数,L 为平均文档长度。
        """
        self._doc_ids = []
        self._doc_tokens = []
        self._doc_lengths = []
        self._term_freqs = []
        self._df = defaultdict(int)
        self._idf_cache = {}

        for doc_id, text in documents:
            tokens = tokenize(text)
            tf = Counter(tokens)
            self._doc_ids.append(doc_id)
            self._doc_tokens.append(tokens)
            self._doc_lengths.append(len(tokens))
            self._term_freqs.append(tf)
            # 更新文档频率(每个词在多少篇文档中出现)
            for term in tf:
                self._df[term] += 1

        self._n_docs = len(self._doc_ids)
        self._avgdl = sum(self._doc_lengths) / self._n_docs if self._n_docs > 0 else 0.0

    def _idf(self, term: str) -> float:
        """
        计算 IDF:
        IDF(t) = ln(1 + (N - n(t) + 0.5) / (n(t) + 0.5))
        N=文档总数, n(t)=包含 t 的文档数

        IDF 缓存:同一 term 多次查询只算一次。
        """
        if term in self._idf_cache:
            return self._idf_cache[term]
        n_t = self._df.get(term, 0)
        # +1e-10 避免除零;+0.5 平滑使 IDF 始终为正
        idf = math.log(1.0 + (self._n_docs - n_t + 0.5) / (n_t + 0.5 + 1e-10))
        self._idf_cache[term] = idf
        return idf

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """
        用 BM25 公式对文档打分,返回 top-k [(doc_id, score)]。

        打分复杂度 O(Q * N),Q 为查询词数,N 为文档数。
        异常时返回空列表,不向上抛出。
        """
        if self._n_docs == 0 or top_k <= 0:
            return []
        query_terms = tokenize(query)
        if not query_terms:
            return []

        try:
            scores: list[float] = [0.0] * self._n_docs

            # 对每个查询词,累加其 BM25 贡献到每篇文档
            for term in query_terms:
                idf = self._idf(term)
                for i in range(self._n_docs):
                    tf = self._term_freqs[i].get(term, 0)
                    if tf == 0:
                        continue
                    # BM25 打分公式:
                    # score = IDF * (tf * (k1+1)) / (tf + k1*(1 - b + b*|d|/avgdl))
                    dl = self._doc_lengths[i]
                    denom = tf + self._k1 * (1.0 - self._b + self._b * dl / max(self._avgdl, 1e-10))
                    score = idf * (tf * (self._k1 + 1.0)) / denom
                    scores[i] += score

            # top-k 排序(仅取正分文档)
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
            return [(self._doc_ids[i], s) for i, s in ranked if s > 0]
        except Exception:
            # 关键词检索异常捕获:返回空结果,避免阻断混合检索流程
            return []


# ---------------------------------------------------------------------------
# 混合检索器
# ---------------------------------------------------------------------------


class HybridRetriever:
    """
    向量+关键词混合检索,用 RRF 融合。

    用法:
        bm25 = BM25Retriever()
        bm25.index([(id, text), ...])
        hybrid = HybridRetriever(
            vector_store=in_memory_store,
            keyword_retriever=bm25,
            embedder=hashing_embedder,
            bm25_weight=0.3,
            vector_weight=0.7,
        )
        results = hybrid.search("查询文本", top_k=5)

    分数融合(RRF):
        对每路检索结果,按排名 rank 计算 1/(k+rank),
        加权汇总后取 top-k。两路互补:向量路捕获语义,
        关键词路捕获精确匹配,RRF 平滑各路权重。
    """

    def __init__(
        self,
        vector_store: BaseVectorStore,
        keyword_retriever: BM25Retriever,
        embedder: BaseEmbedder,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
        rrf_k: int = 60,
    ) -> None:
        # 权重校验:非负,允许任一为 0(单路检索)
        if vector_weight < 0 or bm25_weight < 0:
            raise ValueError("权重不能为负")
        if rrf_k <= 0:
            raise ValueError(f"rrf_k 必须为正: {rrf_k}")
        self._vs = vector_store
        self._bm25 = keyword_retriever
        self._embedder = embedder
        self._v_weight = vector_weight
        self._b_weight = bm25_weight
        self._rrf_k = rrf_k  # RRF 平滑常数

    def search(
        self,
        query_text: str,
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[MemoryItem]:
        """
        同时跑向量检索和 BM25 检索,用 RRF 融合后返回 top-k。

        异常隔离:任一路检索失败不影响另一路,确保混合检索可用性。
        """
        if top_k <= 0:
            return []

        # 1. 向量检索路(语义匹配)
        vec_results: list[MemoryItem] = []
        try:
            query_vec = self._embedder.embed(query_text)
            # 多召回 2 倍,给 RRF 融合更大候选池
            vec_results = self._vs.search(query_vec, top_k=top_k * 2, filter=filter)
        except Exception:
            # 向量检索异常:降级为空,仅用 BM25 路
            vec_results = []
        # vec_results: list[MemoryItem], 已按相似度降序

        # 2. BM25 检索路(关键词精确匹配)
        bm25_results: list[tuple[str, float]] = []
        try:
            bm25_results = self._bm25.search(query_text, top_k=top_k * 2)
        except Exception:
            # BM25 检索异常:降级为空,仅用向量路
            bm25_results = []
        # bm25_results: list[(doc_id, score)], 按分数降序

        # 3. RRF 融合
        # 每路结果按排名(从1开始)计算 RRF 分数,加权后汇总
        rrf_scores: dict[str, float] = defaultdict(float)

        # 向量路: rank 从 1 开始
        for rank, item in enumerate(vec_results, 1):
            rrf_scores[item.id] += self._v_weight * (1.0 / (self._rrf_k + rank))

        # BM25 路
        for rank, (doc_id, _) in enumerate(bm25_results, 1):
            rrf_scores[doc_id] += self._b_weight * (1.0 / (self._rrf_k + rank))

        # 4. 按融合分数排序取 top-k
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        # 5. 构造 MemoryItem 返回(从向量结果中取 metadata, BM25 路只有 id)
        vec_map = {item.id: item for item in vec_results}
        results: list[MemoryItem] = []
        for doc_id, score in ranked:
            if doc_id in vec_map:
                item = vec_map[doc_id]
                results.append(
                    MemoryItem(
                        id=item.id,
                        content=item.content,
                        score=score,
                        metadata=item.metadata,
                    )
                )
            else:
                # 来自 BM25 但不在向量结果中(需要从存储取内容)
                results.append(
                    MemoryItem(
                        id=doc_id,
                        content="",
                        score=score,
                        metadata={},
                    )
                )
        return results
