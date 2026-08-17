"""
Skill Evolver - 技能进化器（棘轮机制）。

只保留改进，自动回滚退步。


流程：
1. 基线评估（当前版本）
2. 生成改进版本
3. 测试改进版本
4. 对比评估
5. 棘轮决策：保留改进 / 回滚
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from fnixagent.core.skills.evaluator import SkillEvaluator, SkillScore


class SkillProtocol(Protocol):
    """技能协议。"""

    @property
    def name(self) -> str: ...

    @property
    def content(self) -> str: ...

    @content.setter
    def content(self, value: str) -> None: ...

    @property
    def version(self) -> str: ...

    def clone(self) -> "SkillProtocol": ...


class TraceProtocol(Protocol):
    """执行轨迹协议。"""

    @property
    def success(self) -> bool: ...

    @property
    def tokens_used(self) -> int: ...

    @property
    def duration_ms(self) -> float: ...


@dataclass
class EvolutionResult:
    """进化结果。"""

    accepted: bool
    baseline_score: float
    improved_score: float
    score_delta: float
    reason: str = ""
    timestamp: float = field(default_factory=time.time)
    rollback_reason: str = ""


@dataclass
class EvolutionRecord:
    """进化记录。"""

    skill_name: str
    version_from: str
    version_to: str
    baseline_score: float
    improved_score: float
    accepted: bool
    timestamp: float = field(default_factory=time.time)


class SkillEvolver:
    """技能进化器（棘轮机制）。

    只保留改进，自动回滚退步。
    """

    def __init__(
        self,
        evaluator: SkillEvaluator = None,
        min_improvement: float = 2.0,
        max_evolution_attempts: int = 3,
    ):
        """初始化进化器。

        Args:
            evaluator: 技能评估器
            min_improvement: 最小改进幅度（分），低于此值视为无改进
            max_evolution_attempts: 最大进化尝试次数
        """
        self.evaluator = evaluator or SkillEvaluator()
        self.min_improvement = min_improvement
        self.max_evolution_attempts = max_evolution_attempts

        # 进化历史记录
        self.history: list[EvolutionRecord] = []

    async def evolve(
        self,
        skill: SkillProtocol,
        test_trace: TraceProtocol = None,
    ) -> EvolutionResult:
        """执行技能进化。

        Args:
            skill: 技能实例
            test_trace: 测试执行轨迹

        Returns:
            EvolutionResult: 进化结果
        """
        # 1. 基线评估
        baseline_score = await self.evaluator.evaluate(skill, test_trace)

        # 2. 克隆技能用于改进
        improved_skill = skill.clone()

        # 3. 生成改进版本
        improved_content = await self._generate_improvement(skill, baseline_score)
        improved_skill.content = improved_content

        # 4. 测试改进版本
        improved_trace = test_trace  # 简化：使用相同 trace
        improved_score = await self.evaluator.evaluate(improved_skill, improved_trace)

        # 5. 棘轮决策
        score_delta = improved_score.total - baseline_score.total

        if score_delta >= self.min_improvement:
            # 保留改进
            skill.content = improved_content
            result = EvolutionResult(
                accepted=True,
                baseline_score=baseline_score.total,
                improved_score=improved_score.total,
                score_delta=score_delta,
                reason=f"Improved by {score_delta:.1f} points",
            )
        else:
            # 回滚（不应用改进）
            result = EvolutionResult(
                accepted=False,
                baseline_score=baseline_score.total,
                improved_score=improved_score.total,
                score_delta=score_delta,
                reason="No significant improvement",
                rollback_reason=f"Delta {score_delta:.1f} < threshold {self.min_improvement}",
            )

        # 记录历史
        self.history.append(EvolutionRecord(
            skill_name=skill.name,
            version_from=skill.version,
            version_to=f"v{float(skill.version[1:]) + 0.1:.1f}" if result.accepted else skill.version,
            baseline_score=baseline_score.total,
            improved_score=improved_score.total,
            accepted=result.accepted,
        ))

        return result

    async def _generate_improvement(
        self,
        skill: SkillProtocol,
        baseline_score: SkillScore,
    ) -> str:
        """生成改进版本。

        基于评估结果生成改进建议。
        """
        content = skill.content

        # 根据最弱维度生成改进
        weakest_dim = min(
            baseline_score.dimensions.items(),
            key=lambda x: x[1].score,
        )

        dim_name, dim_score = weakest_dim

        # 简单改进策略
        if dim_score.score < 60:
            suggestions = dim_score.suggestions

            if "Add code examples" in suggestions:
                content += "\n\n## Example\n\n```python\n# TODO: Add example\n```\n"

            if "Add error handling" in suggestions:
                content += "\n\n## Error Handling\n\nHandle common errors gracefully.\n"

            if "Describe limitations" in suggestions:
                content += "\n\n## Limitations\n\n- Known limitations\n"

        return content

    async def batch_evolve(
        self,
        skills: list[SkillProtocol],
        traces: dict[str, TraceProtocol] = None,
    ) -> list[EvolutionResult]:
        """批量进化技能。

        Args:
            skills: 技能列表
            traces: 技能名到 trace 的映射

        Returns:
            进化结果列表
        """
        traces = traces or {}
        results = []

        for skill in skills:
            trace = traces.get(skill.name)
            result = await self.evolve(skill, trace)
            results.append(result)

        return results

    def get_evolution_history(self, skill_name: str = None) -> list[EvolutionRecord]:
        """获取进化历史。

        Args:
            skill_name: 可选，过滤特定技能

        Returns:
            进化记录列表
        """
        if skill_name:
            return [r for r in self.history if r.skill_name == skill_name]
        return self.history

    def get_success_rate(self) -> float:
        """获取进化成功率。"""
        if not self.history:
            return 0.0

        accepted = sum(1 for r in self.history if r.accepted)
        return accepted / len(self.history)


class HumanInTheLoop:
    """Human-in-the-Loop 守关机制。

    关键阶段强制暂停等用户确认。
    """

    # 守关类型
    GATES = [
        "before_high_risk_action",  # 高风险操作前
        "before_skill_evolution",   # 技能进化前
        "before_memory_deletion",   # 记忆删除前
        "before_external_api_call", # 外部 API 调用前
    ]

    def __init__(self, auto_approve_gates: list[str] = None):
        """初始化守关机制。

        Args:
            auto_approve_gates: 自动批准的守关类型
        """
        self.auto_approve_gates = auto_approve_gates or []
        self.pending_approvals: dict[str, dict[str, Any]] = {}

    async def check_gate(
        self,
        gate: str,
        context: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """检查守关。

        Args:
            gate: 守关类型
            context: 上下文信息

        Returns:
            守关结果
        """
        if gate not in self.GATES:
            return {"approved": True, "reason": "Unknown gate type"}

        # 自动批准
        if gate in self.auto_approve_gates:
            return {"approved": True, "reason": "Auto-approved"}

        # 创建审批请求
        request_id = f"approval_{int(time.time())}"
        self.pending_approvals[request_id] = {
            "gate": gate,
            "context": context or {},
            "timestamp": time.time(),
            "status": "pending",
        }

        # 返回等待状态
        return {
            "approved": False,
            "reason": "Awaiting user approval",
            "request_id": request_id,
        }

    async def approve(self, request_id: str, feedback: str = "") -> bool:
        """批准请求。

        Args:
            request_id: 请求 ID
            feedback: 用户反馈

        Returns:
            是否批准成功
        """
        if request_id not in self.pending_approvals:
            return False

        self.pending_approvals[request_id]["status"] = "approved"
        self.pending_approvals[request_id]["feedback"] = feedback
        return True

    async def reject(self, request_id: str, reason: str = "") -> bool:
        """拒绝请求。

        Args:
            request_id: 请求 ID
            reason: 拒绝原因

        Returns:
            是否拒绝成功
        """
        if request_id not in self.pending_approvals:
            return False

        self.pending_approvals[request_id]["status"] = "rejected"
        self.pending_approvals[request_id]["reason"] = reason
        return True

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """获取待审批列表。"""
        return [
            {"id": k, **v}
            for k, v in self.pending_approvals.items()
            if v["status"] == "pending"
        ]
