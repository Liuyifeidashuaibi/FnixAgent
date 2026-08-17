"""
知识拓扑图 (KTG) 权重优先推理路径搜索。

替代向量相似度检索,基于节点/边权重的 BFS 路径搜索:
    1. 意图解析: 从 query 提取关键词 → 匹配 L2 概念节点(按权重降序)
    2. 路径展开: 从匹配的 L2 节点出发,沿 DEPENDS_ON/PRECONDITION 边向下展开
    3. 权重排序: 路径权重 = Π(边权重) × Σ(节点置信度)
    4. 约束过滤: 检查路径上的 CONSTRAINT 节点,剔除不满足条件的路径
    5. 互斥排除: 若路径含 MUTEX 边,降权 0.5
    6. 返回: 权重最高的 Top-K 路径(K=3)

冷启动兜底: 拓扑图空时,返回空路径(由上层回退到向量召回)。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    EdgeType,
    NodeType,
    TopologyLayer,
    TopologyNode,
    TopologyPath,
)

# 路径搜索默认向下展开的边类型(从 L2 向 L3/L4)
DOWNWARD_EDGE_TYPES: tuple[EdgeType, ...] = (
    EdgeType.DEPENDS_ON,
    EdgeType.PRECONDITION,
    EdgeType.CONTAINS,
    EdgeType.DERIVES,
    EdgeType.CAUSAL,
)

# 互斥边降权因子
MUTEX_PENALTY: float = 0.5

# 默认 Top-K
DEFAULT_TOP_K: int = 3

# 默认最大搜索深度
DEFAULT_MAX_DEPTH: int = 6

# 路径最低权重阈值(低于此值不返回)
DEFAULT_MIN_WEIGHT: float = 0.05


class TopologySearch:
    """权重优先推理路径搜索引擎。"""

    def __init__(
        self,
        graph: TopologyGraph,
        top_k: int = DEFAULT_TOP_K,
        max_depth: int = DEFAULT_MAX_DEPTH,
        min_weight: float = DEFAULT_MIN_WEIGHT,
    ) -> None:
        """初始化搜索引擎。

        Args:
            graph: 拓扑图实例
            top_k: 返回候选路径数上限
            max_depth: BFS 最大深度(边数)
            min_weight: 路径最低权重阈值
        """
        self._graph = graph
        self._top_k = top_k
        self._max_depth = max_depth
        self._min_weight = min_weight

    # -----------------------------------------------------------------------
    # 意图匹配: 从 query 匹配 L2 概念节点
    # -----------------------------------------------------------------------

    def match_concepts(
        self,
        query: str,
        keywords: list[str] | None = None,
    ) -> list[TopologyNode]:
        """从用户查询匹配 L2 概念节点(按权重降序)。

        匹配策略:
            1. 若提供 keywords,用关键词匹配节点 name/content
            2. 否则从 query 切分中英文词元 + 全文子串双向匹配
            3. 按 node.weight 降序排列
            4. 仅返回未废弃的 CONCEPT 节点
        """
        import re

        concepts = self._graph.list_nodes(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            include_deprecated=False,
        )
        if not concepts:
            return []

        query_lower = (query or "").lower()
        if keywords:
            search_terms = [str(k).lower() for k in keywords if k]
        else:
            search_terms = [query_lower]
            search_terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}", query_lower))
        # 去重保序
        seen: set[str] = set()
        terms: list[str] = []
        for t in search_terms:
            if t and t not in seen:
                seen.add(t)
                terms.append(t)

        matched = []
        for node in concepts:
            name_lower = node.name.lower()
            content_lower = node.content.lower()
            hit = False
            for term in terms:
                if (
                    term in name_lower
                    or term in content_lower
                    or name_lower in query_lower
                    or (len(name_lower) >= 2 and name_lower in term)
                ):
                    hit = True
                    break
            # 办公别名：周报/Word → 文档编辑 等
            aliases = {
                "文档编辑": ("周报", "word", "docx", "文档", "摘要", "笔记"),
                "表格分析": ("excel", "xlsx", "表格", "报表"),
                "演示文稿": ("ppt", "pptx", "演示", "幻灯"),
                "pdf 文档": ("pdf", "转换"),
                "论文检索": ("论文", "arxiv", "文献", "检索"),
                "学习辅助": ("学习", "教育", "概念"),
            }
            for alias_name, keys in aliases.items():
                if alias_name in name_lower or name_lower in alias_name:
                    if any(k in query_lower for k in keys):
                        hit = True
                        break
            if hit:
                matched.append(node)

        matched.sort(key=lambda n: n.weight, reverse=True)
        return matched

    # -----------------------------------------------------------------------
    # 路径搜索: BFS + 权重剪枝
    # -----------------------------------------------------------------------

    def search(
        self,
        query: str,
        keywords: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[TopologyPath]:
        """权重优先推理路径搜索。

        Args:
            query: 用户查询
            keywords: 可选关键词(LLM 意图解析产出)
            top_k: 覆盖默认返回数

        Returns:
            按权重降序排列的 Top-K 路径列表
        """
        k = top_k if top_k is not None else self._top_k

        # Step 1: 意图匹配 L2 概念节点
        concepts = self.match_concepts(query, keywords)
        if not concepts:
            return []  # 冷启动: 无匹配,上层回退向量召回

        # Step 2-5: 从每个匹配的概念节点出发,DFS 展开路径
        all_paths: list[TopologyPath] = []
        for concept in concepts:
            paths = self._expand_paths(concept)
            all_paths.extend(paths)

        # Step 6: 按权重降序,取 Top-K
        all_paths.sort(key=lambda p: p.total_weight, reverse=True)
        result = [p for p in all_paths[:k] if p.total_weight >= self._min_weight]

        return result

    def _expand_paths(self, start_node: TopologyNode) -> list[TopologyPath]:
        """从起始节点 DFS 展开所有路径(带权重剪枝)。

        路径权重 = Π(边权重) × Σ(节点置信度)
        含 MUTEX 边的路径权重 × MUTEX_PENALTY
        """
        paths: list[TopologyPath] = []
        # DFS 栈: (当前节点, 路径节点列表, 路径边列表, 累积边权重乘积, 累积节点置信度和, 是否含 MUTEX)
        stack: list[tuple[TopologyNode, list[str], list[str], float, float, bool]] = [
            (start_node, [start_node.node_id], [], 1.0, start_node.confidence, False)
        ]

        while stack:
            node, node_ids, edge_ids, edge_product, conf_sum, has_mutex = stack.pop()

            # 到达 L4 事实层 或 深度达上限 → 形成完整路径
            if node.layer == TopologyLayer.L4_FACT or len(edge_ids) >= self._max_depth:
                if edge_ids:  # 至少有一条边才构成路径
                    path_weight = edge_product * conf_sum
                    if has_mutex:
                        path_weight *= MUTEX_PENALTY
                    paths.append(
                        TopologyPath(
                            nodes=list(node_ids),
                            edges=list(edge_ids),
                            total_weight=path_weight,
                            depth=len(edge_ids),
                        )
                    )
                continue

            # 向下展开: 遍历出边
            out_edges = self._graph.get_out_edges(node.node_id)
            for edge in out_edges:
                if edge.deprecated:
                    continue
                if edge.edge_type not in DOWNWARD_EDGE_TYPES:
                    continue
                target = self._graph.get_node(edge.target_id)
                if target.deprecated:
                    continue
                if target.node_id in node_ids:
                    continue  # 避免环

                new_edge_product = edge_product * max(edge.weight, 0.01)  # 边权重非负
                new_conf_sum = conf_sum + target.confidence
                new_has_mutex = has_mutex or (edge.edge_type == EdgeType.MUTEX)

                stack.append(
                    (
                        target,
                        node_ids + [target.node_id],
                        edge_ids + [edge.edge_id],
                        new_edge_product,
                        new_conf_sum,
                        new_has_mutex,
                    )
                )

        return paths

    # -----------------------------------------------------------------------
    # 约束检查: 验证路径上的 CONSTRAINT 节点
    # -----------------------------------------------------------------------

    def check_constraints(
        self,
        path: TopologyPath,
        context: dict | None = None,
    ) -> tuple[bool, str]:
        """检查路径上的 CONSTRAINT 节点是否满足。

        CONSTRAINT 节点的 metadata 中可包含:
            - threshold: 阈值
            - rule_type: 规则类型
            - precondition: 前置条件描述

        Args:
            path: 待检查的路径
            context: 可选的上下文(用于条件判断)

        Returns:
            (是否通过, 失败原因)
        """
        context = context or {}
        for node_id in path.nodes:
            try:
                node = self._graph.get_node(node_id)
            except Exception:
                continue
            if node.node_type != NodeType.CONSTRAINT:
                continue
            # 简单阈值检查: 若 metadata 含 threshold 且 context 含对应字段
            threshold = node.metadata.get("threshold")
            rule_type = node.metadata.get("rule_type", "generic")
            if threshold is not None and rule_type in context:
                ctx_value = context[rule_type]
                if isinstance(threshold, (int, float)) and isinstance(ctx_value, (int, float)):
                    if ctx_value > threshold:
                        return False, f"约束 {node.name} 不满足: {ctx_value} > {threshold}"
        return True, ""

    # -----------------------------------------------------------------------
    # 冷启动检测
    # -----------------------------------------------------------------------

    def is_cold_start(self) -> bool:
        """判断是否处于冷启动状态(拓扑图概念节点 < 5)。"""
        concepts = self._graph.list_nodes(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
        )
        return len(concepts) < 5

    # -----------------------------------------------------------------------
    # 统计
    # -----------------------------------------------------------------------

    def search_stats(self, query: str, keywords: list[str] | None = None) -> dict:
        """返回搜索统计信息(调试用)。"""
        concepts = self.match_concepts(query, keywords)
        paths = self.search(query, keywords)
        return {
            "query": query,
            "matched_concepts": len(concepts),
            "concept_names": [c.name for c in concepts],
            "found_paths": len(paths),
            "top_path_weight": paths[0].total_weight if paths else 0.0,
            "is_cold_start": self.is_cold_start(),
        }
