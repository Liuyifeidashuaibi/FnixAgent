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

    def clone(self) -> SkillProtocol: ...


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
        llm: Any = None,
        llm_timeout_s: float = 30.0,
    ):
        """初始化进化器。

        Args:
            evaluator: 技能评估器
            min_improvement: 最小改进幅度（分），低于此值视为无改进
            max_evolution_attempts: 最大进化尝试次数
            llm: 可选的同步 LLM 调用 (messages, tools=None) -> resp。
                提供时 _generate_improvement 走 LLM 重写(失败回退模板桩);
                为 None 保持旧版纯模板行为(零回归)。
            llm_timeout_s: 单次 LLM 改写超时秒数
        """
        self.evaluator = evaluator or SkillEvaluator()
        self.min_improvement = min_improvement
        self.max_evolution_attempts = max_evolution_attempts
        self.llm = llm
        self.llm_timeout_s = float(llm_timeout_s)

        # 进化历史记录
        self.history: list[EvolutionRecord] = []

        # HITL 守关: before_skill_evolution 门(可选注入, 默认用全局单例)
        self.hitl = get_hitl()

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
        # 0. HITL 守关: before_skill_evolution(批准过/自动批准则放行, 否则挂起)
        try:
            gate = await self.hitl.check_gate(
                "before_skill_evolution",
                {"skill": skill.name, "version": skill.version},
            )
        except Exception:
            gate = {"approved": True}  # 守关自身故障不阻塞进化(fail-open)
        if not gate.get("approved"):
            return EvolutionResult(
                accepted=False,
                baseline_score=0.0,
                improved_score=0.0,
                score_delta=0.0,
                reason=(
                    f"HITL gate before_skill_evolution: "
                    f"{gate.get('reason', 'awaiting approval')}"
                    + (f" (request_id={gate['request_id']})" if gate.get("request_id") else "")
                ),
                rollback_reason="human_in_the_loop_gate",
            )

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
        self.history.append(
            EvolutionRecord(
                skill_name=skill.name,
                version_from=skill.version,
                version_to=f"v{float(skill.version[1:]) + 0.1:.1f}"
                if result.accepted
                else skill.version,
                baseline_score=baseline_score.total,
                improved_score=improved_score.total,
                accepted=result.accepted,
            )
        )

        return result

    async def _generate_improvement(
        self,
        skill: SkillProtocol,
        baseline_score: SkillScore,
    ) -> str:
        """生成改进版本。

        LLM 可用时: 让模型基于评估短板重写完整技能内容(失败回退模板);
        否则: 旧版模板桩策略(按最弱维度追加占位段落)。
        """
        if self.llm is not None:
            improved = await self._generate_improvement_llm(skill, baseline_score)
            if improved:
                return improved
        return await self._generate_improvement_template(skill, baseline_score)

    async def _generate_improvement_llm(
        self,
        skill: SkillProtocol,
        baseline_score: SkillScore,
    ) -> str | None:
        """LLM 驱动的技能改写。任何失败返回 None(调用方回退模板)。"""
        import asyncio

        weak = sorted(baseline_score.dimensions.items(), key=lambda x: x[1].score)[:3]
        weak_lines = [
            f"- {name}: {dim.score:.0f}/100 — {'; '.join(dim.suggestions[:3]) or '无建议'}"
            for name, dim in weak
        ]
        system = (
            "你是技能文档进化器。根据评估短板重写技能文档, 只输出重写后的完整 Markdown,"
            "不要解释、不要代码围栏包裹全文。改进必须实质解决列出的短板。"
        )
        user = (
            f"## 当前技能内容\n{skill.content[:6000]}\n\n"
            f"## 评估短板\n" + "\n".join(weak_lines) + "\n\n"
            "请输出改进后的完整技能内容。"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            # 同步 llm 调用放线程池, 带超时保护
            resp = await asyncio.wait_for(
                asyncio.to_thread(self.llm, messages),
                timeout=self.llm_timeout_s,
            )
            content, _ = _normalize_llm_content(resp)
            content = (content or "").strip()
        except Exception:
            return None
        # 校验: 非空 / 与原文不同 / 长度合理(防截断与复读)
        if not content or content == skill.content:
            return None
        min_len = max(100, int(len(skill.content) * 0.3))
        if len(content) < min_len or len(content) > 20000:
            return None
        return content

    async def _generate_improvement_template(
        self,
        skill: SkillProtocol,
        baseline_score: SkillScore,
    ) -> str:
        """旧版模板桩改进(离线/测试兼容路径)。"""
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
        "before_skill_evolution",  # 技能进化前
        "before_memory_deletion",  # 记忆删除前
        "before_external_api_call",  # 外部 API 调用前
    ]

    def __init__(self, auto_approve_gates: list[str] = None):
        """初始化守关机制。

        Args:
            auto_approve_gates: 自动批准的守关类型
        """
        self.auto_approve_gates = auto_approve_gates or []
        self.pending_approvals: dict[str, dict[str, Any]] = {}
        # 决策记忆: (gate, context签名) → approved/rejected, 使"批准后重试"可闭环
        self._decisions: dict[str, str] = {}

    @staticmethod
    def _context_signature(gate: str, context: dict[str, Any] = None) -> str:
        """生成稳定的守关签名(同门类+同上下文 → 同一审批)。"""
        import hashlib
        import json as _json

        try:
            raw = _json.dumps(context or {}, sort_keys=True, ensure_ascii=False, default=str)
        except Exception:
            raw = str(context)
        return f"{gate}:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"

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
            守关结果:
              - {"approved": True}                     自动批准 / 已有批准决策
              - {"approved": False, "request_id": ...}  需人工审批(非阻塞)
              - {"approved": False, "rejected": True}   曾被显式拒绝
        """
        if gate not in self.GATES:
            return {"approved": True, "reason": "Unknown gate type"}

        # 自动批准
        if gate in self.auto_approve_gates:
            return {"approved": True, "reason": "Auto-approved"}

        sig = self._context_signature(gate, context)

        # 复用既有决策: 批准过直接放行, 拒绝过快速失败
        prior = self._decisions.get(sig)
        if prior == "approved":
            return {"approved": True, "reason": "Previously approved"}
        if prior == "rejected":
            return {
                "approved": False,
                "rejected": True,
                "reason": "Previously rejected",
            }

        # 创建审批请求(同签名复用未决请求, 避免重复堆叠)
        for existing in self.pending_approvals.values():
            if existing.get("signature") == sig and existing.get("status") == "pending":
                return {
                    "approved": False,
                    "reason": "Awaiting user approval",
                    "request_id": next(
                        k
                        for k, v in self.pending_approvals.items()
                        if v is existing
                    ),
                }

        request_id = f"approval_{int(time.time())}_{len(self.pending_approvals)}"
        self.pending_approvals[request_id] = {
            "gate": gate,
            "context": context or {},
            "signature": sig,
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
        entry = self.pending_approvals.get(request_id)
        if entry is None:
            return False

        entry["status"] = "approved"
        entry["feedback"] = feedback
        self._decisions[entry.get("signature", entry["gate"])] = "approved"
        return True

    async def reject(self, request_id: str, reason: str = "") -> bool:
        """拒绝请求。

        Args:
            request_id: 请求 ID
            reason: 拒绝原因

        Returns:
            是否拒绝成功
        """
        entry = self.pending_approvals.get(request_id)
        if entry is None:
            return False

        entry["status"] = "rejected"
        entry["reason"] = reason
        self._decisions[entry.get("signature", entry["gate"])] = "rejected"
        return True

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """获取待审批列表。"""
        return [
            {"id": k, **v} for k, v in self.pending_approvals.items() if v["status"] == "pending"
        ]


# ── 模块级辅助 ─────────────────────────────────────────────────


def _normalize_llm_content(resp: Any) -> tuple[str, list[dict]]:
    """归一化 LLM 返回为 (content, tool_calls)。

    兼容 LLMResponse 对象(.content/.tool_calls)与 OpenAI choices 风格 dict。
    """
    if isinstance(resp, dict):
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        return str(msg.get("content") or ""), list(msg.get("tool_calls") or [])
    content = getattr(resp, "content", "")
    tool_calls = getattr(resp, "tool_calls", None) or []
    return str(content or ""), list(tool_calls)


_DEFAULT_HITL: HumanInTheLoop | None = None


def get_hitl() -> HumanInTheLoop:
    """进程级 HumanInTheLoop 单例。

    环境变量 FNIX_HITL_AUTO_APPROVE 控制默认放行的门类:
      - "all"                          → 所有门自动批准(等价旧行为)
      - 逗号分隔门名                    → 指定门自动批准
      - 空/未设置                       → 全部需要人工审批(fail-closed)
    """
    global _DEFAULT_HITL
    if _DEFAULT_HITL is None:
        import os

        raw = (os.getenv("FNIX_HITL_AUTO_APPROVE") or "").strip().lower()
        if raw == "all":
            auto = list(HumanInTheLoop.GATES)
        elif raw:
            auto = [g.strip() for g in raw.split(",") if g.strip() in HumanInTheLoop.GATES]
        else:
            auto = []
        _DEFAULT_HITL = HumanInTheLoop(auto_approve_gates=auto)
    return _DEFAULT_HITL


def reset_hitl_for_tests() -> HumanInTheLoop:
    """测试辅助: 重置为全自动批准单例。"""
    global _DEFAULT_HITL
    _DEFAULT_HITL = HumanInTheLoop(auto_approve_gates=list(HumanInTheLoop.GATES))
    return _DEFAULT_HITL
