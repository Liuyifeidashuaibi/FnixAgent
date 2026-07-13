"""工具检索器(P2-4)。

从 ToolRegistry 中检索与用户查询语义相关的工具,供 LLM function-calling。
核心思想:
  1. 把每个 ToolMetadata 的 description 用 Embedder 编码为向量,构建索引
  2. 用户查询(query)同样编码,与索引做余弦相似度
  3. L1_OFFICE 层加权(l1_boost),让 LLM 优先选择 Office 专家能力
  4. 支持按 layer 过滤(L1/L2/INFRA)、按 min_score 过滤、按 top_k 截断
  5. 支持拓扑路径回退(retrieve_with_fallback):向量检索无结果时用 topology_path 命中

设计:
  - 增量索引:工具 add/remove 时自动更新,无需重建
  - 零拷贝:向量缓存到 ToolMetadata.description_embedding 字段(由 build_index 写入)
  - 线程安全:RLock 保护
  - 不依赖外部向量库:用 list + 余弦相似度(由 core.mathops 加速)
"""
from __future__ import annotations

import threading
from typing import Any, Optional

from fnixagent.core.mathops import batch_cosine_similarity, top_k_with_scores
from fnixagent.core.retrieval.embedder import BaseEmbedder, HashingEmbedder
from fnixagent.core.tools.protocol import ToolLayer, ToolMetadata


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class ToolRetrieverError(Exception):
    """工具检索器基础异常。"""


# ---------------------------------------------------------------------------
# ToolRetriever
# ---------------------------------------------------------------------------


class ToolRetriever:
    """工具检索器:基于向量相似度 + L1 加权。

    用法:
        from fnixagent.core.retrieval.embedder import HashingEmbedder
        retriever = ToolRetriever(
            tool_registry=registry,
            embedder=HashingEmbedder(dim=256),
            top_k=5,
            min_score=0.3,
            l1_boost=0.15,
        )
        retriever.build_index()  # 初始构建

        # 检索
        results = retriever.retrieve("把这份 Word 转成 PDF")
        for metadata, score in results:
            print(f"{metadata.name}: {score:.3f}")

        # 带过滤的检索
        results = retriever.retrieve(
            "发送邮件",
            layer_filter=ToolLayer.L2_ECOSYSTEM,
            top_k=3,
        )

        # 回退检索(向量无结果时用拓扑路径)
        results = retriever.retrieve_with_fallback(
            "查询天气",
            topology_path=["L1_ROOT", "L1_WEATHER"],
        )
    """

    def __init__(
        self,
        tool_registry: Any,
        embedder: Optional[BaseEmbedder] = None,
        top_k: int = 5,
        min_score: float = 0.3,
        l1_boost: float = 0.15,
    ) -> None:
        """
        Args:
            tool_registry: ToolRegistry 实例(需实现 list_tools/get_tool)
            embedder: Embedder(默认 HashingEmbedder(dim=256),零依赖降级)
            top_k: 默认返回前 K 个
            min_score: 最低相似度阈值(过滤噪声)
            l1_boost: L1_OFFICE 层加权(0.0-1.0,默认 0.15,让 L1 工具优先)
        """
        self._registry = tool_registry
        self._embedder = embedder or HashingEmbedder(dim=256)
        self._top_k = top_k
        self._min_score = min_score
        self._l1_boost = l1_boost
        # 索引:name → (metadata, vector)
        self._index: dict[str, tuple[ToolMetadata, list[float]]] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 索引管理
    # ------------------------------------------------------------------

    def build_index(self) -> int:
        """全量构建索引(从 registry 拉取全部工具)。

        会清空旧索引,重新编码全部工具描述。
        返回索引工具数。
        """
        with self._lock:
            self._index.clear()
            tools = self._registry.list_tools()
            for tool in tools:
                self._add_to_index_locked(tool)
            return len(self._index)

    def add_tool(self, metadata: ToolMetadata) -> None:
        """添加单个工具到索引(注册时调用)。"""
        with self._lock:
            self._add_to_index_locked(metadata)

    def remove_tool(self, name: str) -> bool:
        """从索引移除工具(注销时调用)。"""
        with self._lock:
            return self._index.pop(name, None) is not None

    def reembed(self, name: Optional[str] = None) -> int:
        """重新编码工具描述(描述变更后调用)。

        Args:
            name: 指定工具名;None 表示全量重建

        Returns:
            重新编码的工具数
        """
        with self._lock:
            if name is not None:
                tool = self._registry.get_tool(name) if hasattr(self._registry, "get_tool") else None
                # ToolRegistry.get_tool 返回 RegisteredTool 或 None;list_tools 返回 [ToolMetadata]
                if tool is None:
                    # 回退到 list_tools 查找
                    for t in self._registry.list_tools():
                        if t.name == name:
                            tool = t
                            break
                elif hasattr(tool, "metadata"):
                    tool = tool.metadata
                if tool is None:
                    return 0
                self._add_to_index_locked(tool)
                return 1
            else:
                return self.build_index()

    def _add_to_index_locked(self, metadata: ToolMetadata) -> None:
        """加锁添加到索引(已持有 _lock)。"""
        # 优先复用 metadata.description_embedding(避免重复编码)
        if metadata.description_embedding is not None:
            vector = list(metadata.description_embedding)
        else:
            text = self._embed_text(metadata)
            vector = self._embedder.embed(text)
            # 缓存到 metadata(零拷贝)
            try:
                metadata.description_embedding = list(vector)
            except Exception:
                pass  # dataclass 不可变时忽略
        self._index[metadata.name] = (metadata, vector)

    def _embed_text(self, metadata: ToolMetadata) -> str:
        """构造用于 embedding 的文本(name + category + description)。"""
        parts = [metadata.name, metadata.category, metadata.description]
        return " ".join(p for p in parts if p)

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        layer_filter: Optional[ToolLayer] = None,
        min_score: Optional[float] = None,
    ) -> list[tuple[ToolMetadata, float]]:
        """向量检索:返回 [(metadata, score)] 列表(score 越高越相关)。

        Args:
            query: 用户查询文本
            top_k: 返回前 K 个(None 用默认 self._top_k)
            layer_filter: 仅返回指定层级的工具(None 不限)
            min_score: 最低相似度阈值(None 用默认 self._min_score)

        Returns:
            [(ToolMetadata, score)] 列表,按 score 降序
        """
        top_k = top_k if top_k is not None else self._top_k
        min_score = min_score if min_score is not None else self._min_score
        if not query or not self._index:
            return []
        with self._lock:
            # 1. 编码查询
            query_vec = self._embedder.embed(query)
            # 2. 过滤 + 收集候选
            candidates: list[tuple[ToolMetadata, list[float]]] = []
            for name, (metadata, vec) in self._index.items():
                # 跳过禁用工具
                if not metadata.enabled:
                    continue
                # 按层级过滤
                if layer_filter is not None and metadata.layer != layer_filter:
                    continue
                candidates.append((metadata, vec))
            if not candidates:
                return []
            # 3. 批量计算相似度
            matrix = [vec for _, vec in candidates]
            scores = batch_cosine_similarity(query_vec, matrix)
            # 4. L1 加权(让 L1_OFFICE 层工具优先)
            weighted_scores: list[float] = []
            for i, (metadata, _) in enumerate(candidates):
                score = scores[i]
                if metadata.layer == ToolLayer.L1_OFFICE:
                    score += self._l1_boost
                # 成本评分作为负向因子(越便宜的工具略加权)
                # cost_score 0.0-1.0,0 表示最便宜
                cost_penalty = metadata.cost_score * 0.05
                score -= cost_penalty
                weighted_scores.append(score)
            # 5. top_k + min_score 过滤
            indexed = list(enumerate(weighted_scores))
            indexed.sort(key=lambda x: x[1], reverse=True)
            results: list[tuple[ToolMetadata, float]] = []
            for idx, score in indexed[:top_k]:
                if score < min_score:
                    continue
                results.append((candidates[idx][0], round(score, 4)))
            return results

    def retrieve_with_fallback(
        self,
        query: str,
        topology_path: Optional[list[str]] = None,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> list[tuple[ToolMetadata, float]]:
        """带回退的检索:向量检索无结果时,用 topology_path 命中绑定工具。

        Args:
            query: 用户查询文本
            topology_path: 拓扑路径(如 ["L1_ROOT", "L1_OFFICE", "L1_WORD"])

        Returns:
            [(ToolMetadata, score)] 列表
        """
        # 1. 先做向量检索
        results = self.retrieve(
            query, top_k=top_k, min_score=min_score
        )
        if results:
            return results
        # 2. 向量检索无结果,回退到拓扑路径
        if not topology_path:
            return []
        with self._lock:
            fallback: list[tuple[ToolMetadata, float]] = []
            for metadata, _ in self._index.values():
                if not metadata.enabled:
                    continue
                # 拓扑绑定匹配
                if metadata.topology_binding and metadata.topology_binding in topology_path:
                    fallback.append((metadata, 0.5))  # 回退给固定 0.5 分
            fallback.sort(key=lambda x: x[1], reverse=True)
            return fallback[: top_k or self._top_k]

    # ------------------------------------------------------------------
    # 索引查询
    # ------------------------------------------------------------------

    def get_indexed_tool(self, name: str) -> Optional[ToolMetadata]:
        """从索引获取工具(不存在返回 None)。"""
        with self._lock:
            entry = self._index.get(name)
            return entry[0] if entry else None

    def list_indexed_tools(
        self,
        layer: Optional[ToolLayer] = None,
    ) -> list[ToolMetadata]:
        """列出索引中的工具(可选按层级过滤)。"""
        with self._lock:
            tools = [m for m, _ in self._index.values()]
            if layer is not None:
                tools = [t for t in tools if t.layer == layer]
            return tools

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def set_params(
        self,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        l1_boost: Optional[float] = None,
    ) -> None:
        """更新检索参数(运行时调优)。"""
        with self._lock:
            if top_k is not None:
                self._top_k = top_k
            if min_score is not None:
                self._min_score = min_score
            if l1_boost is not None:
                self._l1_boost = l1_boost

    @property
    def params(self) -> dict[str, Any]:
        """当前检索参数。"""
        with self._lock:
            return {
                "top_k": self._top_k,
                "min_score": self._min_score,
                "l1_boost": self._l1_boost,
                "embedder_dim": self._embedder.dim,
                "index_size": len(self._index),
            }

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """检索器统计。"""
        with self._lock:
            tools = list(self._index.values())
            by_layer: dict[str, int] = {}
            by_source: dict[str, int] = {}
            for metadata, _ in tools:
                layer = metadata.layer.value if metadata.layer else "unknown"
                by_layer[layer] = by_layer.get(layer, 0) + 1
                by_source[metadata.source] = by_source.get(metadata.source, 0) + 1
            return {
                "index_size": len(tools),
                "by_layer": by_layer,
                "by_source": by_source,
                "embedder_dim": self._embedder.dim,
            }
