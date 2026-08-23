"""
升级引擎 — 分析差距，生成升级建议，自动执行升级

设计思路:
  - 自动技能创建方案 (Skill Factory), 遗传优化遗传优化
  - 自进化技能, 错误修正沉淀
  - 强化学习方案 skill selection, 奖赏驱动
  - 遗传优化: 遗传帕累托Prompt进化, 交叉+突变, 败因分析
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from .knowledge import FlywheelKnowledgeBase, KnowledgeItem

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================


class UpgradeType(str, Enum):
    """升级类型"""

    PROMPT_OPTIMIZATION = "prompt_optimization"  # Prompt 优化
    SKILL_ADDITION = "skill_addition"  # 新增技能
    SKILL_IMPROVEMENT = "skill_improvement"  # 技能改进
    MEMORY_ENHANCEMENT = "memory_enhancement"  # 记忆增强
    REASONING_STRATEGY = "reasoning_strategy"  # 推理策略
    TOOL_INTEGRATION = "tool_integration"  # 工具集成
    ARCHITECTURE_UPGRADE = "architecture_upgrade"  # 架构升级
    SECURITY_IMPROVEMENT = "security_improvement"  # 安全改进
    PERFORMANCE_TUNING = "performance_tuning"  # 性能优化
    PROTOCOL_UPDATE = "protocol_update"  # 协议更新


class UpgradeImpact(str, Enum):
    """升级影响等级"""

    CRITICAL = "critical"  # 核心功能升级
    HIGH = "high"  # 重要功能增强
    MEDIUM = "medium"  # 一般改进
    LOW = "low"  # 微调
    COSMETIC = "cosmetic"  # 表面优化


@dataclass
class UpgradeProposal:
    """升级建议"""

    proposal_id: str
    title: str
    upgrade_type: UpgradeType
    impact: UpgradeImpact
    description: str
    source_knowledge: list[str]  # 引用知识item_id
    current_state: str  # 当前系统状态
    target_state: str  # 目标状态
    implementation_steps: list[str]
    code_changes: list[str]  # 需要修改的文件
    estimated_effort: str  # 估计工作量
    risk_level: str  # 风险等级
    rollback_plan: str  # 回滚方案
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "draft"  # draft/approved/implementing/implemented/rejected


# ============================================================
# 升级引擎
# ============================================================


class UpgradeEngine:
    """升级引擎 — 分析差距，生成升级建议，追踪执行"""

    def __init__(
        self,
        kb: FlywheelKnowledgeBase,
        proposals_dir: str | None = None,
    ):
        self.kb = kb
        self.proposals_dir = proposals_dir or str(
            Path(__file__).parent.parent.parent.parent / "assets" / "upgrade_proposals"
        )
        Path(self.proposals_dir).mkdir(parents=True, exist_ok=True)
        self._proposals: dict[str, UpgradeProposal] = self._load_proposals()

    def _load_proposals(self) -> dict[str, UpgradeProposal]:
        proposals: dict = {}
        for f in Path(self.proposals_dir).glob("proposal_*.json"):
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            proposals[data["proposal_id"]] = UpgradeProposal(**data)
        return proposals

    def _save_proposal(self, proposal: UpgradeProposal):
        path = Path(self.proposals_dir) / f"proposal_{proposal.proposal_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                {k: v.value if isinstance(v, Enum) else v for k, v in proposal.__dict__.items()},
                f,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        self._proposals[proposal.proposal_id] = proposal

    def analyze_gap(self, knowledge: KnowledgeItem) -> UpgradeProposal | None:
        """分析单条知识与当前系统的差距"""
        title_lower = knowledge.title.lower()
        summary_lower = knowledge.summary.lower()

        # 规则匹配
        rules = [
            # Prompt优化
            (
                r"prompt|template|instruction|system message",
                UpgradeType.PROMPT_OPTIMIZATION,
                UpgradeImpact.HIGH,
            ),
            # 技能系统
            (
                r"skill|auto.?skill|skill.?factory|skill.?creation",
                UpgradeType.SKILL_ADDITION,
                UpgradeImpact.CRITICAL,
            ),
            (
                r"skill.?improve|skill.?enhance|skill.?refine",
                UpgradeType.SKILL_IMPROVEMENT,
                UpgradeImpact.HIGH,
            ),
            # 记忆系统
            (
                r"memory|context.?window|persistent.?memory|entity.?memory",
                UpgradeType.MEMORY_ENHANCEMENT,
                UpgradeImpact.HIGH,
            ),
            # 推理
            (
                r"reasoning|chain.?of.?thought|react|plan.?and.?execute",
                UpgradeType.REASONING_STRATEGY,
                UpgradeImpact.HIGH,
            ),
            # 工具
            (
                r"tool|executor|sandbox|function.?call",
                UpgradeType.TOOL_INTEGRATION,
                UpgradeImpact.MEDIUM,
            ),
            # 协议
            (
                r"a2a|agent.?to.?agent|mcp|model.?context.?protocol",
                UpgradeType.PROTOCOL_UPDATE,
                UpgradeImpact.CRITICAL,
            ),
            # 架构
            (
                r"architecture|framework|orchestrat|multi.?agent",
                UpgradeType.ARCHITECTURE_UPGRADE,
                UpgradeImpact.HIGH,
            ),
            # 安全
            (
                r"security|guardrail|safety|sandbox|injection",
                UpgradeType.SECURITY_IMPROVEMENT,
                UpgradeImpact.HIGH,
            ),
            # 性能
            (
                r"performance|latency|throughput|cache",
                UpgradeType.PERFORMANCE_TUNING,
                UpgradeImpact.MEDIUM,
            ),
        ]

        for pattern, upgrade_type, impact in rules:
            if re.search(pattern, title_lower) or re.search(pattern, summary_lower):
                proposal = self._create_proposal(knowledge, upgrade_type, impact)
                self._save_proposal(proposal)
                return proposal

        return None

    def _create_proposal(
        self,
        knowledge: KnowledgeItem,
        upgrade_type: UpgradeType,
        impact: UpgradeImpact,
    ) -> UpgradeProposal:
        proposal_id = f"up_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{knowledge.item_id[:8]}"
        return UpgradeProposal(
            proposal_id=proposal_id,
            title=f"[{upgrade_type.value}] {knowledge.title[:80]}",
            upgrade_type=upgrade_type,
            impact=impact,
            description=knowledge.summary[:500],
            source_knowledge=[knowledge.item_id],
            current_state="待评估",
            target_state=knowledge.key_insights[0]
            if knowledge.key_insights
            else knowledge.summary[:200],
            implementation_steps=[],
            code_changes=[],
            estimated_effort="待评估",
            risk_level="medium",
            rollback_plan="通过 git revert 回退",
        )

    def generate_batch(self, pending_knowledge: list[KnowledgeItem]) -> list[UpgradeProposal]:
        """批量生成升级建议"""
        proposals: list[UpgradeProposal] = []
        for item in pending_knowledge:
            proposal = self.analyze_gap(item)
            if proposal:
                proposals.append(proposal)
        return proposals

    def get_pending_proposals(self) -> list[UpgradeProposal]:
        """获取待审批的升级建议"""
        return [p for p in self._proposals.values() if p.status == "draft"]

    def get_implemented_proposals(self) -> list[UpgradeProposal]:
        return [p for p in self._proposals.values() if p.status == "implemented"]

    def approve_proposal(self, proposal_id: str):
        if proposal_id in self._proposals:
            self._proposals[proposal_id].status = "approved"
            self._save_proposal(self._proposals[proposal_id])

    def mark_implemented(self, proposal_id: str, notes: str = ""):
        if proposal_id in self._proposals:
            proposal = self._proposals[proposal_id]
            proposal.status = "implemented"
            self._save_proposal(proposal)
            # 同步到知识库
            for item_id in proposal.source_knowledge:
                self.kb.add_knowledge(
                    KnowledgeItem(
                        item_id=item_id,
                        title=proposal.title,
                        url="",
                        category="",
                        priority="",
                        summary=proposal.description,
                        key_insights=[],
                        actionable=False,
                        upgrade_suggestion="",
                        source_name="upgrade_engine",
                        collected_at=proposal.created_at,
                        tags=[],
                    ),
                    implementation_notes=notes,
                )

    def get_statistics(self) -> dict:
        total = len(self._proposals)
        by_type = {}
        by_status = {}
        for p in self._proposals.values():
            t = p.upgrade_type.value
            by_type[t] = by_type.get(t, 0) + 1
            s = p.status
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": total,
            "by_type": by_type,
            "by_status": by_status,
        }
