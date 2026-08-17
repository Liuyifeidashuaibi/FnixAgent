"""
向量检索引擎 (Retrieval Engine)。

提供:
  - Embedder: 文本向量化(哈希 Embedding 降级方案 + 抽象接口)
  - VectorStore: 向量存储与检索(内存版 + Milvus 抽象接口)
  - HybridRetriever: 向量+关键词(BM25)混合检索 + RRF 融合

全部纯 Python 标准库实现,零第三方依赖。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.retrieval.embedder import (
    BaseEmbedder,
    HashingEmbedder,
)
from fnixagent.core.retrieval.hybrid import (
    BM25Retriever,
    HybridRetriever,
)
from fnixagent.core.retrieval.vectorstore import (
    BaseVectorStore,
    InMemoryVectorStore,
)

__all__ = [
    "BM25Retriever",
    "BaseEmbedder",
    "BaseVectorStore",
    "HashingEmbedder",
    "HybridRetriever",
    "InMemoryVectorStore",
]
