"""
技能-拓扑突触协议 (STP) 反馈处理器。

技能执行结果反向更新拓扑权重(双向正反馈):
    成功:
        - 绑定 CONCEPT 节点 weight += SUCCESS_BONUS(+0.05)
        - 推理路径上的边 weight += SINGLE_INCREMENT(+0.02)
        - CONCEPT.confidence += 0.02
    失败:
        - 绑定 CONCEPT 节点 weight += FAILURE_PENALTY(-0.08)
        - 推理路径上的边 weight -= 0.03
        - 若 weight < DEPRECATE_THRESHOLD: 标记 deprecated

双向正反馈:
    拓扑权重高 → 技能优先级高 → 被选中概率高 → 执行成功 → 拓扑权重更高
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

from fnixagent.core.topology import weights as weights_mod
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    NodeType,
    ToolExecutionStatus,
    ToolResult,
    TopologyLayer,
    TopologyPath,
)


class SkillFeedbackHandler:
    """技能执行结果反馈处理器。

    用法:
        handler = SkillFeedbackHandler(graph)
        handler.on_skill_success("search_paper", path=TopologyPath(...))
        handler.on_skill_failure("convert_pdf", path=TopologyPath(...))
    """

    def __init__(self, graph: TopologyGraph) -> None:
        """初始化反馈处理器。

        Args:
            graph: 拓扑图实例(权重更新作用于该图)
        """
        self._graph = graph
        # 反馈窗口: 记录每个技能最近 N 次调用结果
        self._feedback_window: dict[str, list[bool]] = {}
        self._window_size = 50

    # -----------------------------------------------------------------------
    # 成功/失败反馈
    # -----------------------------------------------------------------------

    def on_skill_success(
        self,
        skill_name: str,
        path: TopologyPath | None = None,
        concept_node_id: str | None = None,
    ) -> dict[str, Any]:
        """技能执行成功 → 强化拓扑权重。

        Args:
            skill_name: 技能名
            path: 推理路径(路径上的边也会强化)
            concept_node_id: 指定概念节点(可选,默认查全部绑定节点)

        Returns:
            更新统计 {"concepts_reinforced": N, "edges_reinforced": M}

        Raises:
            ValueError: skill_name 为空
        """
        if not skill_name:
            raise ValueError("skill_name must be non-empty")
        stats: dict[str, Any] = {"concepts_reinforced": 0, "edges_reinforced": 0}

        # Step 1: 强化绑定的概念节点
        concept_ids = self._find_bound_concepts(skill_name, concept_node_id)
        for cid in concept_ids:
            node = self._graph.get_node(cid)
            weights_mod.node_on_skill_success(node)
            # 置信度也增加
            node.confidence = min(
                weights_mod.CONFIDENCE_MAX,
                node.confidence + weights_mod.CONFIDENCE_INCREMENT,
            )
            # 记录成功次数
            node.metadata["success_count"] = node.metadata.get("success_count", 0) + 1
            stats["concepts_reinforced"] += 1

        # Step 2: 强化路径上的边
        if path is not None:
            for edge_id in path.edges:
                edge = self._graph.get_edge(edge_id)
                weights_mod.edge_on_path_hit(edge)
                stats["edges_reinforced"] += 1

        # Step 3: 记录反馈窗口
        self._record_feedback(skill_name, True)

        return stats

    def on_skill_failure(
        self,
        skill_name: str,
        path: TopologyPath | None = None,
        concept_node_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """技能执行失败 → 惩罚拓扑权重。

        Args:
            skill_name: 技能名
            path: 推理路径
            concept_node_id: 指定概念节点
            error: 失败原因(记录到 metadata)

        Returns:
            更新统计 {"concepts_penalized": N, "edges_penalized": M, "deprecated": K}

        Raises:
            ValueError: skill_name 为空
        """
        if not skill_name:
            raise ValueError("skill_name must be non-empty")
        stats: dict[str, Any] = {
            "concepts_penalized": 0,
            "edges_penalized": 0,
            "deprecated": 0,
        }

        # Step 1: 惩罚绑定的概念节点
        concept_ids = self._find_bound_concepts(skill_name, concept_node_id)
        for cid in concept_ids:
            node = self._graph.get_node(cid)
            weights_mod.node_on_skill_failure(node)
            # 记录失败次数
            node.metadata["failure_count"] = node.metadata.get("failure_count", 0) + 1
            if error:
                node.metadata["last_error"] = error
            stats["concepts_penalized"] += 1
            if node.deprecated:
                stats["deprecated"] += 1

        # Step 2: 惩罚路径上的边
        if path is not None:
            for edge_id in path.edges:
                edge = self._graph.get_edge(edge_id)
                weights_mod.edge_on_failure(edge)
                stats["edges_penalized"] += 1
                if edge.deprecated:
                    stats["deprecated"] += 1

        # Step 3: 记录反馈窗口
        self._record_feedback(skill_name, False)

        return stats

    # -----------------------------------------------------------------------
    # 从 ToolResult 触发反馈
    # -----------------------------------------------------------------------

    def process_tool_result(
        self,
        skill_name: str,
        result: ToolResult,
        path: TopologyPath | None = None,
    ) -> dict[str, Any]:
        """从 ToolResult 自动触发成功/失败反馈。

        Args:
            skill_name: 技能名
            result: 工具执行结果
            path: 推理路径

        Returns:
            反馈统计
        """
        if result.status == ToolExecutionStatus.SUCCESS:
            return self.on_skill_success(skill_name, path)
        else:
            return self.on_skill_failure(skill_name, path, error=result.error)

    # -----------------------------------------------------------------------
    # 反馈窗口查询
    # -----------------------------------------------------------------------

    def get_success_rate(self, skill_name: str) -> float:
        """获取技能最近 N 次调用的成功率。"""
        history = self._feedback_window.get(skill_name, [])
        if not history:
            return 0.0
        success_count = sum(1 for r in history if r)
        return success_count / len(history)

    def get_feedback_history(self, skill_name: str) -> list[bool]:
        """获取技能反馈历史(True=成功, False=失败)。"""
        return list(self._feedback_window.get(skill_name, []))

    def get_all_success_rates(self) -> dict[str, float]:
        """获取全部技能的成功率。"""
        return {name: self.get_success_rate(name) for name in self._feedback_window}

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    def _find_bound_concepts(
        self,
        skill_name: str,
        concept_node_id: str | None = None,
    ) -> list[str]:
        """查找技能绑定的概念节点 ID 列表。"""
        if concept_node_id is not None:
            return [concept_node_id]

        # 从拓扑图查找所有绑定到该技能的概念节点
        concepts = self._graph.list_nodes(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
        )
        return [c.node_id for c in concepts if c.skill_binding == skill_name]

    def _record_feedback(self, skill_name: str, success: bool) -> None:
        """记录反馈到滑动窗口。"""
        if skill_name not in self._feedback_window:
            self._feedback_window[skill_name] = []
        history = self._feedback_window[skill_name]
        history.append(success)
        # 保持窗口大小
        if len(history) > self._window_size:
            history.pop(0)
