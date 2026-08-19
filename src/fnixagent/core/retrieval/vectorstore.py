"""
向量存储 (Vector Store)。

提供:
  - BaseVectorStore: 抽象基类(子类对接 Milvus/FAISS/Chroma)
  - InMemoryVectorStore: 纯 Python 内存版,基于 mathops 做余弦检索

内存版设计:
  - 数据结构: list[_VectorRecord(id, vector, metadata)]
  - 检索: batch_cosine_similarity + top_k_with_scores (部分排序)
  - 过滤: metadata 的 key=value 等值过滤(如 tenant_id/user_id)
  - 线程安全: threading.RLock 保护所有读写与索引更新
  - 维度校验: 入库与查询时校验向量维度一致性,避免错误结果

性能:
  - 检索复杂度 O(n*dim + n log k),n 为候选集大小
  - 对万级以下数据足够;更大规模请用 Milvus/FAISS
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
import threading
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.mathops import batch_cosine_similarity, top_k_with_scores
from fnixagent.core.types import MemoryItem


@dataclass
class _VectorRecord:
    """内部向量记录。

    vector 用 list[float] 存储以兼容 mathops 的 Sequence 接口;
    若需进一步压缩内存可改用 array.array('f', ...)。
    """

    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseVectorStore(abc.ABC):
    """向量库抽象基类。"""

    @abc.abstractmethod
    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> int:
        """批量插入向量。返回插入条数。"""
        ...

    @abc.abstractmethod
    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[MemoryItem]:
        """检索 top-k 最相似的。filter 做 metadata 等值过滤。"""
        ...

    @abc.abstractmethod
    def delete(self, ids: list[str]) -> int:
        """按 id 删除。返回删除条数。"""
        ...

    @abc.abstractmethod
    def count(self) -> int:
        """返回总条数。"""
        ...


class InMemoryVectorStore(BaseVectorStore):
    """
    内存向量库 — Milvus/FAISS 的轻量平替。

    适用于:
      - 开发测试(无需部署 Milvus)
      - 小规模数据(万级以下)
      - 内核独立分发(零基础设施依赖)

    线程安全:
      - 所有公开方法(add/search/delete/count/get_by_id)均在 _lock 下执行
      - search 内部对候选集做快照,避免迭代时被并发修改
    """

    def __init__(self) -> None:
        self._records: list[_VectorRecord] = []
        self._id_index: dict[str, int] = {}  # id -> records 中的索引
        # 维度记录:首条入库向量决定,后续入库校验一致性
        self._dim: int | None = None
        self._lock = threading.RLock()

    def _check_dim(self, vector: list[float], *, allow_init: bool = True) -> None:
        """校验向量维度与库内已有维度一致。

        Args:
            vector: 待校验向量
            allow_init: 库为空时是否允许初始化维度

        Raises:
            ValueError: 维度不一致
        """
        v_len = len(vector)
        if v_len == 0:
            raise ValueError("vector 不能为空")
        if self._dim is None:
            if allow_init:
                self._dim = v_len
            return
        if v_len != self._dim:
            raise ValueError(f"向量维度不一致: got {v_len}, expected {self._dim}")

    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> int:
        """批量插入向量。

        Raises:
            ValueError: ids/vectors 长度不一致或维度不匹配
        """
        if len(ids) != len(vectors):
            raise ValueError("ids 和 vectors 长度不一致")
        if metadatas is None:
            metadatas = [{}] * len(ids)
        # 索引更新加锁:避免并发 add 造成 _id_index 与 _records 不一致
        with self._lock:
            inserted = 0
            for rid, vec, meta in zip(ids, vectors, metadatas):
                # 维度校验(首条初始化库维度)
                self._check_dim(vec, allow_init=True)
                if rid in self._id_index:
                    # 已存在则覆盖(原地更新,索引不变)
                    idx = self._id_index[rid]
                    self._records[idx] = _VectorRecord(rid, list(vec), dict(meta))
                else:
                    self._id_index[rid] = len(self._records)
                    self._records.append(_VectorRecord(rid, list(vec), dict(meta)))
                inserted += 1
            return inserted

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filter: dict | None = None,
    ) -> list[MemoryItem]:
        """
        检索最相似的 top_k 条记录。

        算法:
          1. query_vector 维度校验(与库内维度一致)
          2. 若有 filter, 先按 metadata 等值过滤候选集
          3. 对候选集做批量余弦相似度计算(O(n*dim))
          4. 用堆排序取 top-k(部分排序, O(n + n log k))

        Raises:
            ValueError: query_vector 维度与库不一致
        """
        with self._lock:
            # 查询向量维度校验(库为空时直接返回)
            if self._dim is not None:
                if len(query_vector) != self._dim:
                    raise ValueError(
                        f"query_vector 维度不一致: got {len(query_vector)}, expected {self._dim}"
                    )
            # 过滤候选集(在锁内快照,避免迭代时被并发修改)
            if filter:
                candidates = [
                    r
                    for r in self._records
                    if all(r.metadata.get(k) == v for k, v in filter.items())
                ]
            else:
                candidates = list(self._records)

            if not candidates:
                return []

            # 批量余弦相似度计算
            matrix = [r.vector for r in candidates]
            try:
                scores = batch_cosine_similarity(query_vector, matrix)
            except Exception:
                # 向量检索异常捕获:返回空结果而非抛出,避免阻断上层流程
                return []

            # top-k 部分排序(堆排序,O(n + n log k))
            k = min(max(top_k, 0), len(candidates))
            if k == 0:
                return []
            ranked = top_k_with_scores(scores, k)

            return [
                MemoryItem(
                    id=candidates[idx].id,
                    content=candidates[idx].metadata.get("content", ""),
                    score=scores[idx],
                    metadata=candidates[idx].metadata,
                )
                for idx, _ in ranked
            ]

    def delete(self, ids: list[str]) -> int:
        """按 id 删除(标记式,重建索引)。

        索引更新加锁:删除后重建 _id_index,保证一致性。
        """
        with self._lock:
            id_set = set(ids)
            before = len(self._records)
            self._records = [r for r in self._records if r.id not in id_set]
            # 重建索引(O(n))
            self._id_index = {r.id: i for i, r in enumerate(self._records)}
            return before - len(self._records)

    def count(self) -> int:
        """返回存储的向量总数。"""
        with self._lock:
            return len(self._records)

    def get_by_id(self, rid: str) -> _VectorRecord | None:
        """按 id 查单条。"""
        with self._lock:
            idx = self._id_index.get(rid)
            if idx is None:
                return None
            return self._records[idx]

    @property
    def dim(self) -> int | None:
        """库内向量维度(空库时为 None)。"""
        with self._lock:
            return self._dim

    def clear(self) -> int:
        """清空全部记录。返回清理前的条数。"""
        with self._lock:
            n = len(self._records)
            self._records.clear()
            self._id_index.clear()
            self._dim = None
            return n


# 便捷别名:默认内存向量库实现
VectorStore = InMemoryVectorStore
