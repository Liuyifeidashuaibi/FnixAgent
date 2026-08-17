"""
知识拓扑图 (KTG) 权重体系。

本模块定义 KTG 的"固化"权重参数(运行期不可修改),
以及节点/边权重的衰减、强化、钳制、废弃标记等操作。

固化参数(来自计划文档第二部分 2.4):
    INITIAL_WEIGHT          = 0.5    新节点/边初始权重
    SINGLE_INCREMENT        = +0.02  单次有效推理路径增量
    SUCCESS_BONUS           = +0.05  技能执行成功奖励
    FAILURE_PENALTY         = -0.08  失败惩罚
    DAILY_DECAY             = 0.999  每日衰减系数
    DEPRECATE_THRESHOLD     = 0.05   低于此值标记废弃
    CONFIDENCE_INIT         = 0.3    新节点初始置信度
    CONFIDENCE_INCREMENT    = +0.02  命中时置信度增量
    MAX_WEIGHT              = 1.0    权重上限
    MIN_WEIGHT              = 0.0    权重下限(非负)
    DEPRECATED_WEIGHT       = 0.01   废弃节点权重(不删除,仅降权)
    STALE_FRESHNESS         = 0.3    低于此值标记 stale
    STALE_USE_COUNT         = 5      且 use_count 低于此值才降权
    STALE_PENALTY_FACTOR    = 0.95   stale 节点权重衰减因子
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import time

from fnixagent.core.types import TopologyEdge, TopologyNode

# ---------------------------------------------------------------------------
# 固化常量(永久不变,运行期只读)
# ---------------------------------------------------------------------------

INITIAL_WEIGHT: float = 0.5
SINGLE_INCREMENT: float = 0.02
SUCCESS_BONUS: float = 0.05
FAILURE_PENALTY: float = -0.08
DAILY_DECAY: float = 0.999
DEPRECATE_THRESHOLD: float = 0.05
CONFIDENCE_INIT: float = 0.3
CONFIDENCE_INCREMENT: float = 0.02
CONFIDENCE_MAX: float = 1.0
MAX_WEIGHT: float = 1.0
MIN_WEIGHT: float = 0.0
DEPRECATED_WEIGHT: float = 0.01
STALE_FRESHNESS: float = 0.3
STALE_USE_COUNT: int = 5
STALE_PENALTY_FACTOR: float = 0.95

# ---------------------------------------------------------------------------
# 权重操作(纯函数,不修改原对象,返回新值)
# ---------------------------------------------------------------------------

def clamp_weight(weight: float) -> float:
    """将权重钳制到 [MIN_WEIGHT, MAX_WEIGHT] 范围内。"""
    return max(MIN_WEIGHT, min(MAX_WEIGHT, weight))

def reinforce(weight: float, increment: float = SINGLE_INCREMENT) -> float:
    """强化权重(命中/成功时调用)。"""
    return clamp_weight(weight + increment)

def penalize(weight: float, penalty: float = FAILURE_PENALTY) -> float:
    """惩罚权重(失败时调用)。"""
    return clamp_weight(weight + penalty)  # FAILURE_PENALTY 为负数

def decay(weight: float, factor: float = DAILY_DECAY) -> float:
    """衰减权重(每日调用)。"""
    return clamp_weight(weight * factor)

def should_deprecate(weight: float) -> bool:
    """判断权重是否低于废弃阈值。"""
    return weight < DEPRECATE_THRESHOLD

def apply_success_bonus(weight: float) -> float:
    """技能执行成功的权重奖励。"""
    return clamp_weight(weight + SUCCESS_BONUS)

def apply_failure_penalty(weight: float) -> float:
    """技能执行失败的权重惩罚。"""
    return clamp_weight(weight + FAILURE_PENALTY)

# ---------------------------------------------------------------------------
# 节点权重操作(返回修改后的节点,原节点不变)
# ---------------------------------------------------------------------------

def node_on_hit(node: TopologyNode) -> TopologyNode:
    """节点被推理路径命中时的权重更新。

    - weight += SINGLE_INCREMENT
    - confidence += CONFIDENCE_INCREMENT(上限 1.0)
    - use_count += 1
    - freshness 重置为 1.0
    - last_used_at 更新为当前时间
    """
    node.weight = reinforce(node.weight, SINGLE_INCREMENT)
    node.confidence = min(CONFIDENCE_MAX, node.confidence + CONFIDENCE_INCREMENT)
    node.use_count += 1
    node.freshness = 1.0
    node.last_used_at = time.time()
    return node

def node_daily_decay(node: TopologyNode) -> TopologyNode:
    """节点每日衰减(freshness 衰减,权重按 stale 规则调整)。

    - freshness *= DAILY_DECAY
    - 若 freshness < STALE_FRESHNESS 且 use_count < STALE_USE_COUNT: weight *= STALE_PENALTY_FACTOR
    - 若 weight < DEPRECATE_THRESHOLD: 标记 deprecated,权重降至 DEPRECATED_WEIGHT
    """
    node.freshness *= DAILY_DECAY
    if node.freshness < STALE_FRESHNESS and node.use_count < STALE_USE_COUNT:
        node.weight = decay(node.weight, STALE_PENALTY_FACTOR)
    if should_deprecate(node.weight):
        node.deprecated = True
        node.weight = DEPRECATED_WEIGHT
    return node

def node_on_skill_success(node: TopologyNode) -> TopologyNode:
    """绑定的技能执行成功时的权重奖励。"""
    node.weight = apply_success_bonus(node.weight)
    return node

def node_on_skill_failure(node: TopologyNode) -> TopologyNode:
    """绑定的技能执行失败时的权重惩罚。"""
    node.weight = apply_failure_penalty(node.weight)
    if should_deprecate(node.weight):
        node.deprecated = True
        node.weight = DEPRECATED_WEIGHT
    return node

# ---------------------------------------------------------------------------
# 边权重操作
# ---------------------------------------------------------------------------

def edge_on_path_hit(edge: TopologyEdge) -> TopologyEdge:
    """边被推理路径命中时的权重强化。"""
    # MUTEX 和 CONTAINS 边权重固定,不参与强化
    if abs(edge.weight) < 1e-9 and edge.edge_type.value == "mutex":
        return edge
    if abs(edge.weight - 1.0) < 1e-9 and edge.edge_type.value == "contains":
        return edge
    edge.weight = reinforce(edge.weight, SINGLE_INCREMENT)
    return edge

def edge_on_failure(edge: TopologyEdge) -> TopologyEdge:
    """边所在路径执行失败时的权重惩罚。"""
    if abs(edge.weight) < 1e-9 and edge.edge_type.value == "mutex":
        return edge
    if abs(edge.weight - 1.0) < 1e-9 and edge.edge_type.value == "contains":
        return edge
    edge.weight = penalize(edge.weight, -0.03)  # 失败时边权重 -0.03
    return edge

def edge_daily_decay(edge: TopologyEdge) -> TopologyEdge:
    """边每日衰减。"""
    if abs(edge.weight) < 1e-9 and edge.edge_type.value == "mutex":
        return edge
    if abs(edge.weight - 1.0) < 1e-9 and edge.edge_type.value == "contains":
        return edge
    edge.weight = decay(edge.weight, DAILY_DECAY)
    if should_deprecate(edge.weight):
        edge.deprecated = True
    return edge
