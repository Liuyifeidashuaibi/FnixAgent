"""
Embedding 模型封装。

提供:
  - BaseEmbedder: 抽象基类,子类对接 OpenAI/Qwen/BGE 等真实 Embedding 模型
  - HashingEmbedder: 纯 Python 特征哈希(Feature Hashing)实现,
    无需外部模型即可将文本映射为固定维度向量,作为降级方案

特征哈希原理:
  对文本的每个 token(中文按字,英文按词)计算哈希,
  将哈希值映射到 [0, dim) 区间,对应维度累加(带符号)。
  最终 L2 归一化,得到单位向量。
  优点: 零依赖、确定性、维度可控、O(n) 复杂度(n 为 token 数);
  缺点: 无语义理解能力,仅适用于无外部模型时的降级。

性能优化:
  - 哈希计算 O(n):每个 token 一次 MD5 + 一次取模,无嵌套循环
  - 结果缓存:相同文本直接命中缓存,避免重复哈希
  - 批量化:embed_batch 逐条调用 embed,但缓存可减少跨批次重复计算
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
import hashlib
import struct
from collections import OrderedDict

from fnixagent.core.mathops import (
    batch_cosine_similarity,
    l2_normalize,
    top_k_with_scores,
)
from fnixagent.core.text import tokenize

Vector = list[float]

# Embedding 缓存默认上限(条),超出按 LRU 淘汰
DEFAULT_CACHE_SIZE: int = 1024

class BaseEmbedder(abc.ABC):
    """Embedding 模型抽象基类。

    所有具体 Embedder 应实现 embed/embed_batch。
    内置 LRU 缓存,子类可直接复用 _cached_embed 避免重复计算。
    """

    def __init__(self, cache_size: int = DEFAULT_CACHE_SIZE) -> None:
        # LRU 缓存:text -> vector。容量超出时淘汰最久未使用项
        self._cache: OrderedDict[str, Vector] = OrderedDict()
        self._cache_size = max(0, int(cache_size))

    @property
    @abc.abstractmethod
    def dim(self) -> int:
        """向量维度。"""
        ...

    @abc.abstractmethod
    def _embed_raw(self, text: str) -> Vector:
        """子类实现的实际编码逻辑(不含缓存)。"""
        ...

    def embed(self, text: str) -> Vector:
        """将单条文本编码为向量(带 LRU 缓存)。

        Args:
            text: 待编码文本,不能为 None

        Returns:
            固定维度的向量

        Raises:
            ValueError: text 为 None
        """
        if text is None:
            raise ValueError("text 不能为 None")
        # 空文本走 _embed_raw(子类可短路返回零向量)
        if self._cache_size == 0:
            return self._embed_raw(text)
        # 命中缓存:move_to_end 标记为最近使用
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        # 未命中:计算并写入缓存,必要时淘汰
        vec = self._embed_raw(text)
        self._cache[text] = vec
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)  # 淘汰最久未使用
        return vec

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        """批量编码。默认逐条调用 embed(命中缓存),子类可优化为批量 API。"""
        return [self.embed(t) for t in texts]

    def clear_cache(self) -> None:
        """清空 embedding 缓存。"""
        self._cache.clear()

class HashingEmbedder(BaseEmbedder):
    """
    特征哈希 Embedder — 零依赖降级方案。

    算法(O(n), n = len(tokens)):
      1. 对文本分词(tokenize: 中文按字,英文按词)— O(n)
      2. 对每个 token 计算 MD5 哈希,取前 8 字节为 uint64 — O(n) 次哈希
      3. 用哈希值确定:
         - 维度索引 = hash % dim        (一次取模)
         - 符号位    = (hash >> 63) & 1  (最高位决定 +1 / -1,带符号哈希减少冲突)
      4. 累加到对应维度 — O(1) per token
      5. L2 归一化 — O(dim)

    相同文本必然产生相同向量; 相似文本因共享 token 而有较高余弦相似度。
    时间复杂度 O(n + dim),空间复杂度 O(dim)。
    """

    def __init__(
        self,
        dim: int = 1024,
        normalize: bool = True,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        if dim <= 0:
            raise ValueError(f"dim 必须为正, got {dim}")
        super().__init__(cache_size=cache_size)
        self._dim = dim
        self._normalize = normalize

    @property
    def dim(self) -> int:
        """向量维度。"""
        return self._dim

    def _embed_raw(self, text: str) -> Vector:
        """将文本编码为向量(分词→带符号哈希累加→L2 归一化)。"""
        # 空文本直接返回零向量(避免无谓计算)
        if not text:
            return [0.0] * self._dim
        # 初始化维度向量(O(dim))
        vec: list[float] = [0.0] * self._dim
        tokens = tokenize(text)
        # 对每个 token 做一次哈希映射,累加到对应维度(O(n))
        for token in tokens:
            self._hash_token(token, vec)
        if self._normalize:
            vec = l2_normalize(vec)
        return vec

    def _hash_token(self, token: str, vec: list[float]) -> None:
        """
        将单个 token 哈希映射到向量的某个维度(带符号哈希)。

        - 维度索引: hash % dim
        - 符号: hash 的最高位决定 +1 / -1 (带符号哈希减少冲突偏置)

        该步骤 O(1):一次 MD5 + 一次取模 + 一次数组累加。
        """
        # MD5 哈希,取前 8 字节转为 uint64
        h = hashlib.md5(token.encode("utf-8")).digest()
        val = struct.unpack("<Q", h[:8])[0]
        # 维度索引:取模映射到 [0, dim)
        idx = val % self._dim
        # 最高位决定符号: 0→+1, 1→-1(带符号哈希避免所有 token 同向偏置)
        sign = 1.0 if (val >> 63) == 0 else -1.0
        vec[idx] += sign

    def embed_batch(self, texts: list[str]) -> list[Vector]:
        """批量编码(逐条调用 embed, 命中 LRU 缓存以减少重复哈希)。"""
        return [self.embed(t) for t in texts]

# ---------------------------------------------------------------------------
# 检索便捷函数
# ---------------------------------------------------------------------------

def retrieve(
    query_vector: Vector,
    candidate_vectors: list[Vector],
    top_k: int = 5,
) -> list[tuple[int, float]]:
    """
    给定查询向量,从候选向量集合中检索 top-k 最相似的。
    返回 [(index, score), ...] 按相似度降序。

    使用 mathops.top_k_with_scores 做部分排序,复杂度 O(n + n log k),
    优于完整排序的 O(n log n)。
    """
    if top_k <= 0 or not candidate_vectors:
        return []
    scores = batch_cosine_similarity(query_vector, candidate_vectors)
    return top_k_with_scores(scores, top_k)
