"""
知识拓扑图 (KTG) 固定 Schema 定义与校验。

本模块定义 KTG 的"永久不变"结构:
    - 四层层级(L1 目标 / L2 概念 / L3 规则 / L4 事实)
    - 六类节点(GOAL / CONCEPT / RULE / FACT / CONSTRAINT / INFERENCE)
    - 六类边(CAUSAL / DEPENDS_ON / DERIVES / CONTAINS / PRECONDITION / MUTEX)

所有节点/边的创建必须通过本模块的校验,确保不违反固化规则。
校验规则:
    1. 节点的 node_type 必须与 layer 匹配(GOAL→L1, CONCEPT→L2, 其余→L3/L4)
    2. 边的源/目标节点必须存在,且不违反层级约束(CONTAINS 只能相邻层)
    3. MUTEX 边权重恒 -1.0,CONTAINS 边权重恒 1.0
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.exceptions import (
    TopologyLayerViolationError,
    TopologyValidationError,
)
from fnixagent.core.types import EdgeType, NodeType, TopologyEdge, TopologyLayer, TopologyNode

# ---------------------------------------------------------------------------
# 固定映射: 节点类型 → 允许的层级(永久不变)
# ---------------------------------------------------------------------------

NODE_TYPE_LAYER_MAP: dict[NodeType, TopologyLayer] = {
    NodeType.GOAL: TopologyLayer.L1_GOAL,
    NodeType.CONCEPT: TopologyLayer.L2_CONCEPT,
    NodeType.RULE: TopologyLayer.L3_RULE,
    NodeType.CONSTRAINT: TopologyLayer.L3_RULE,
    NodeType.INFERENCE: TopologyLayer.L3_RULE,
    NodeType.FACT: TopologyLayer.L4_FACT,
}

# 反向映射: 层级 → 允许的节点类型列表
LAYER_NODE_TYPES: dict[TopologyLayer, frozenset[NodeType]] = {
    TopologyLayer.L1_GOAL: frozenset({NodeType.GOAL}),
    TopologyLayer.L2_CONCEPT: frozenset({NodeType.CONCEPT}),
    TopologyLayer.L3_RULE: frozenset({NodeType.RULE, NodeType.CONSTRAINT, NodeType.INFERENCE}),
    TopologyLayer.L4_FACT: frozenset({NodeType.FACT}),
}

# 层级序号(用于判断相邻层)
LAYER_ORDER: dict[TopologyLayer, int] = {
    TopologyLayer.L1_GOAL: 1,
    TopologyLayer.L2_CONCEPT: 2,
    TopologyLayer.L3_RULE: 3,
    TopologyLayer.L4_FACT: 4,
}

# ---------------------------------------------------------------------------
# 固定映射: 边类型 → 权重约束(永久不变)
# ---------------------------------------------------------------------------

# 固定权重边类型(MUTEX 恒 -1.0,CONTAINS 恒 1.0)
FIXED_WEIGHT_EDGES: dict[EdgeType, float] = {
    EdgeType.MUTEX: -1.0,
    EdgeType.CONTAINS: 1.0,
}

# 可变权重边类型的合法范围
VARIABLE_WEIGHT_RANGE: tuple[float, float] = (0.0, 1.0)

# ---------------------------------------------------------------------------
# 层级约束: 哪些边类型允许跨层,哪些只能同层
# ---------------------------------------------------------------------------

# CONTAINS 边只允许相邻层(L1→L2, L2→L3, L3→L4)
# 其他边类型允许同层或跨层(但源/目标都必须存在)
CONTAINS_ADJACENT_ONLY: bool = True


def validate_node(node: TopologyNode) -> None:
    """校验节点是否符合固化 Schema。

    Args:
        node: 待校验节点

    Raises:
        TopologyValidationError: 节点类型与层级不匹配
    """
    expected_layer = NODE_TYPE_LAYER_MAP.get(node.node_type)
    if expected_layer is None:
        raise TopologyValidationError(f"未知节点类型: {node.node_type}(仅允许 6 种固定类型)")
    if node.layer != expected_layer:
        raise TopologyValidationError(
            f"节点类型 {node.node_type.value} 必须属于 {expected_layer.value},"
            f"实际为 {node.layer.value}"
        )
    # L2 概念节点才能绑定技能
    if node.skill_binding is not None and node.layer != TopologyLayer.L2_CONCEPT:
        raise TopologyValidationError(
            f"仅 L2 概念节点可绑定技能,当前节点 {node.node_id} 属于 {node.layer.value}"
        )


def validate_edge(
    edge: TopologyEdge,
    source: TopologyNode,
    target: TopologyNode,
) -> None:
    """校验边是否符合固化 Schema。

    Args:
        edge: 待校验边
        source: 起点节点(必须已存在)
        target: 终点节点(必须已存在)

    Raises:
        TopologyValidationError: 边类型/权重不合法
        TopologyLayerViolationError: 违反层级约束(如 CONTAINS 跨多层)
    """
    # 固定权重边类型: 权重必须等于固定值
    if edge.edge_type in FIXED_WEIGHT_EDGES:
        expected = FIXED_WEIGHT_EDGES[edge.edge_type]
        if abs(edge.weight - expected) > 1e-9:
            raise TopologyValidationError(
                f"边类型 {edge.edge_type.value} 权重必须为 {expected},实际为 {edge.weight}"
            )
    else:
        # 可变权重边: 必须在 [0, 1] 范围内
        lo, hi = VARIABLE_WEIGHT_RANGE
        if edge.weight < lo or edge.weight > hi:
            raise TopologyValidationError(
                f"边类型 {edge.edge_type.value} 权重必须在 [{lo}, {hi}] 范围内,实际为 {edge.weight}"
            )

    # CONTAINS 边: 只允许相邻层
    if edge.edge_type == EdgeType.CONTAINS and CONTAINS_ADJACENT_ONLY:
        src_order = LAYER_ORDER[source.layer]
        tgt_order = LAYER_ORDER[target.layer]
        if abs(src_order - tgt_order) != 1:
            raise TopologyLayerViolationError(
                f"CONTAINS 边只允许相邻层,当前 {source.layer.value}→{target.layer.value}"
            )


def is_valid_node_type_for_layer(node_type: NodeType, layer: TopologyLayer) -> bool:
    """快速判断节点类型是否属于指定层级。"""
    return node_type in LAYER_NODE_TYPES.get(layer, frozenset())


def get_layer_for_node_type(node_type: NodeType) -> TopologyLayer:
    """获取节点类型对应的固定层级。"""
    layer = NODE_TYPE_LAYER_MAP.get(node_type)
    if layer is None:
        raise TopologyValidationError(f"未知节点类型: {node_type}")
    return layer
