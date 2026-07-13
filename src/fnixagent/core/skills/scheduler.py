"""
技能-拓扑突触协议 (STP) 调度器。

基于拓扑权重换算的优先级进行技能调度:
    1. 从 ToolRegistry 获取全部已注册技能
    2. 根据当前推理路径,用 SkillBindingProtocol 计算每个技能的优先级
    3. 按权限策略过滤(自动/确认/禁用)
    4. 按优先级降序返回 Top-K 技能

调度逻辑独立于 LangGraph,定义为纯 Python 接口,可迁移至任意编排框架。
"""
from __future__ import annotations

from typing import Optional

from fnixagent.core.skills.levels import SkillPermissionPolicy
from fnixagent.core.skills.protocol import SkillBindingProtocol
from fnixagent.core.tools.protocol import ToolMetadata
from fnixagent.core.tools.registry import ToolRegistry
from fnixagent.core.types import SkillLevel, TopologyPath


class SkillScheduler:
    """拓扑权重驱动的技能调度器。

    用法:
        scheduler = SkillScheduler(registry, binding_protocol, permission_policy)
        selected = scheduler.select_skills(path=TopologyPath(...), top_k=3)
    """

    def __init__(
        self,
        registry: ToolRegistry,
        binding_protocol: SkillBindingProtocol,
        permission_policy: Optional[SkillPermissionPolicy] = None,
    ) -> None:
        """初始化技能调度器。

        Args:
            registry: 工具注册中心(获取已注册技能)
            binding_protocol: 技能-拓扑绑定协议(计算优先级)
            permission_policy: 权限策略(默认创建)
        """
        self._registry = registry
        self._binding = binding_protocol
        self._policy = permission_policy or SkillPermissionPolicy()

    # -----------------------------------------------------------------------
    # 技能选择
    # -----------------------------------------------------------------------

    def select_skills(
        self,
        path: Optional[TopologyPath] = None,
        top_k: int = 5,
        category: Optional[str] = None,
        auto_invoke_only: bool = False,
    ) -> list[ToolMetadata]:
        """根据拓扑权重优先级选择 Top-K 技能。

        Args:
            path: 当前推理路径(用于计算优先级)
            top_k: 返回技能数上限(必须 > 0)
            category: 可选,按分类过滤
            auto_invoke_only: 仅返回可自动调用的技能(跳过需确认/禁用的)

        Returns:
            按优先级降序排列的 ToolMetadata 列表

        Raises:
            ValueError: top_k <= 0
        """
        if top_k <= 0:
            raise ValueError(f"top_k must be > 0, got {top_k}")
        # Step 1: 获取全部已注册工具元数据
        all_tools = self._registry.list_tools(category=category)
        if not all_tools:
            return []

        # Step 2: 计算每个技能的优先级 + 权限过滤
        candidates: list[tuple[ToolMetadata, float, str]] = []
        for tool in all_tools:
            if not tool.enabled:
                continue

            # 解析技能级别
            skill_level = self._parse_skill_level(tool.skill_level)

            # 权限检查
            allowed, reason = self._policy.check_invoke_permission(
                tool.name, skill_level
            )
            if not allowed:
                if auto_invoke_only or reason == "forbidden":
                    continue
                # needs_confirmation 的技能仍加入候选,但标记需确认

            # 计算优先级
            priority = self._binding.compute_priority(tool.name, path)
            # 若工具自身有 priority 字段,取较大值(兼容未绑定拓扑的工具)
            priority = max(priority, tool.priority)

            candidates.append((tool, priority, reason))

        # Step 3: 按优先级降序排列
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Step 4: 取 Top-K
        return [c[0] for c in candidates[:top_k]]

    def select_by_concept(
        self,
        concept_node_id: str,
        top_k: int = 3,
    ) -> list[ToolMetadata]:
        """根据指定的 L2 概念节点选择绑定的技能。

        Args:
            concept_node_id: L2 概念节点 ID(非空)
            top_k: 返回技能数上限

        Returns:
            绑定到该概念的技能列表(通常为 1 个,因一对一绑定)

        Raises:
            ValueError: concept_node_id 为空或 top_k <= 0
        """
        if not concept_node_id:
            raise ValueError("concept_node_id must be non-empty")
        if top_k <= 0:
            raise ValueError(f"top_k must be > 0, got {top_k}")
        skill_name = self._binding.get_bound_skill(concept_node_id)
        if skill_name is None:
            return []
        if not self._registry.has(skill_name):
            return []
        tool = self._registry.get(skill_name)
        return [tool.metadata]

    def select_for_path(
        self,
        path: TopologyPath,
        top_k: int = 5,
    ) -> list[ToolMetadata]:
        """为指定推理路径选择最优技能组合。

        遍历路径上的所有 L2 概念节点,收集其绑定的技能,
        按优先级降序返回 Top-K。

        Args:
            path: 推理路径
            top_k: 返回技能数上限

        Returns:
            按优先级降序排列的技能列表
        """
        # 收集路径上所有概念节点绑定的技能
        skill_names: set[str] = set()
        for node_id in path.nodes:
            skill_name = self._binding.get_bound_skill(node_id)
            if skill_name is not None:
                skill_names.add(skill_name)

        if not skill_names:
            return []

        # 计算优先级并排序
        priorities = self._binding.compute_priorities(list(skill_names), path)

        # 获取 ToolMetadata
        result: list[ToolMetadata] = []
        for skill_name, priority in priorities[:top_k]:
            if self._registry.has(skill_name):
                tool = self._registry.get(skill_name)
                result.append(tool.metadata)
        return result

    # -----------------------------------------------------------------------
    # 调度信息
    # -----------------------------------------------------------------------

    def describe_schedule(
        self,
        path: Optional[TopologyPath] = None,
        top_k: int = 5,
    ) -> list[dict]:
        """返回调度详情(调试用)。"""
        all_tools = self._registry.list_tools()
        info = []
        for tool in all_tools[:top_k * 2]:  # 多取一些用于排序
            skill_level = self._parse_skill_level(tool.skill_level)
            allowed, reason = self._policy.check_invoke_permission(
                tool.name, skill_level
            )
            priority = self._binding.compute_priority(tool.name, path)
            info.append({
                "name": tool.name,
                "skill_level": skill_level.value,
                "priority": round(priority, 4),
                "allowed": allowed,
                "reason": reason,
                "bound_concepts": [
                    c.node_id for c in self._binding.get_bound_concepts(tool.name)
                ],
            })
        info.sort(key=lambda x: x["priority"], reverse=True)
        return info[:top_k]

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_skill_level(level_str: str) -> SkillLevel:
        """从字符串解析技能级别(容错)。"""
        try:
            return SkillLevel(level_str)
        except ValueError:
            return SkillLevel.BASIC
