"""
Skill Evaluator - 技能 9 维评估器。

对技能进行 9 个维度的评估。

维度：
1. structure_quality: 结构质量（SKILL.md 格式规范性）
2. executive_effectiveness: 执行效果（任务成功率）
3. failure_mode_encoding: 失败模式编码（错误处理完备性）
4. actionable_specificity: 可执行具体性（指令明确程度）
5. context_appropriateness: 上下文适当性（场景匹配度）
6. edge_case_handling: 边界情况处理
7. resource_efficiency: 资源效率（Token/时间消耗）
8. user_feedback: 用户反馈（满意度）
9. regression_safety: 回归安全性（不引入新问题）

高风险行动黑名单：
- rm -rf /
- DROP TABLE
- sudo chmod 777
- 等等

LLM 复核（可选）：
参考 bench/judge.py 的两级判定模式 —— 启发式全量打分，可选让 LLM 对
"内容质量/可执行性/安全性"三个维度做语义复核，按 0.6/0.4 加权合成。
任何 LLM 失败（超时/解析错误/异常）均静默回退纯启发式结果，零回归。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

_logger = logging.getLogger(__name__)

# LLM 单次复核超时（秒），可经 config["llm_timeout"] 覆盖
DEFAULT_LLM_TIMEOUT = 30.0


class SkillProtocol(Protocol):
    """技能协议。"""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def content(self) -> str: ...

    @property
    def metadata(self) -> dict[str, Any]: ...


class TraceProtocol(Protocol):
    """执行轨迹协议。"""

    @property
    def success(self) -> bool: ...

    @property
    def duration_ms(self) -> float: ...

    @property
    def tokens_used(self) -> int: ...

    @property
    def errors(self) -> list[str]: ...

    @property
    def user_feedback(self) -> dict[str, Any]: ...


class Dimension(str, Enum):
    """评估维度。"""

    STRUCTURE_QUALITY = "structure_quality"
    EXECUTIVE_EFFECTIVENESS = "executive_effectiveness"
    FAILURE_MODE_ENCODING = "failure_mode_encoding"
    ACTIONABLE_SPECIFICITY = "actionable_specificity"
    CONTEXT_APPROPRIATENESS = "context_appropriateness"
    EDGE_CASE_HANDLING = "edge_case_handling"
    RESOURCE_EFFICIENCY = "resource_efficiency"
    USER_FEEDBACK = "user_feedback"
    REGRESSION_SAFETY = "regression_safety"


@dataclass
class DimensionScore:
    """单维度评分。"""

    dimension: Dimension
    score: float  # 0.0 - 100.0
    reason: str = ""
    suggestions: list[str] = field(default_factory=list)
    source: str = "heuristic"  # 评分来源: heuristic / llm_blend


@dataclass
class SkillScore:
    """技能综合评分。"""

    total: float  # 0.0 - 100.0
    dimensions: dict[Dimension, DimensionScore] = field(default_factory=dict)
    failure_modes: list[str] = field(default_factory=list)
    blacklist_violations: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        """评级。"""
        if self.total >= 90:
            return "A+"
        elif self.total >= 80:
            return "A"
        elif self.total >= 70:
            return "B"
        elif self.total >= 60:
            return "C"
        elif self.total >= 50:
            return "D"
        else:
            return "F"


class SkillEvaluator:
    """技能 9 维评估器。"""

    # 维度权重
    DIMENSION_WEIGHTS = {
        Dimension.STRUCTURE_QUALITY: 0.10,
        Dimension.EXECUTIVE_EFFECTIVENESS: 0.20,
        Dimension.FAILURE_MODE_ENCODING: 0.10,
        Dimension.ACTIONABLE_SPECIFICITY: 0.15,
        Dimension.CONTEXT_APPROPRIATENESS: 0.10,
        Dimension.EDGE_CASE_HANDLING: 0.10,
        Dimension.RESOURCE_EFFICIENCY: 0.10,
        Dimension.USER_FEEDBACK: 0.10,
        Dimension.REGRESSION_SAFETY: 0.05,
    }

    # 高风险行动黑名单
    HIGH_RISK_BLACKLIST = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+\*",
        r"DROP\s+TABLE",
        r"DROP\s+DATABASE",
        r"sudo\s+chmod\s+777",
        r"mkfs\.",
        r"dd\s+if=.+of=/dev/",
        r":\(\)\s*\{:\|:&\};:",  # fork bomb
        r"format\s+[a-zA-Z]:",
        r"del\s+/[fqs]",
    ]

    # SKILL.md 必需字段
    REQUIRED_SKILL_FIELDS = [
        "name",
        "description",
    ]

    # 推荐的可选字段
    RECOMMENDED_FIELDS = [
        "triggers",
        "parameters",
        "examples",
        "error_handling",
        "limitations",
    ]

    # LLM 复核维度 → 评估维度的映射
    JUDGE_DIMENSION_MAP = {
        "content_quality": Dimension.STRUCTURE_QUALITY,      # 内容质量 → 结构质量
        "executability": Dimension.ACTIONABLE_SPECIFICITY,   # 可执行性 → 可执行具体性
        "safety": Dimension.REGRESSION_SAFETY,               # 安全性   → 回归安全性
    }

    # 合成权重：final = 0.6 * 启发式 + 0.4 * LLM（LLM 可用时）
    BLEND_WEIGHT_HEURISTIC = 0.6
    BLEND_WEIGHT_LLM = 0.4

    def __init__(
        self,
        config: dict[str, Any] = None,
        llm: Callable[..., Any] | None = None,
    ):
        """初始化评估器。

        Args:
            config: 配置参数
                - weights: 自定义维度权重
                - blacklist: 自定义黑名单
                - passing_threshold: 通过阈值 (默认 60)
                - llm_timeout: LLM 复核超时秒数 (默认 30)
            llm: 可选的评审模型调用函数 (async, OpenAI 兼容签名，
                 约定同 bench/judge.Judge)。为 None 时行为与纯启发式完全一致。
        """
        self.config = config or {}
        self.llm = llm

        # 合并权重
        self.weights = dict(self.DIMENSION_WEIGHTS)
        if "weights" in self.config:
            self.weights.update(self.config["weights"])

        # 合并黑名单
        self.blacklist = list(self.HIGH_RISK_BLACKLIST)
        if "blacklist" in self.config:
            self.blacklist.extend(self.config["blacklist"])

        self.passing_threshold = self.config.get("passing_threshold", 60)
        self.llm_timeout = float(self.config.get("llm_timeout", DEFAULT_LLM_TIMEOUT))

    async def evaluate(
        self,
        skill: SkillProtocol,
        trace: TraceProtocol = None,
    ) -> SkillScore:
        """执行 9 维评估。

        Args:
            skill: 技能实例
            trace: 执行轨迹（可选）

        Returns:
            SkillScore: 综合评分
        """
        dimension_scores = {}

        # 评估各维度
        dimension_scores[Dimension.STRUCTURE_QUALITY] = self._evaluate_structure(skill)
        dimension_scores[Dimension.ACTIONABLE_SPECIFICITY] = self._evaluate_actionable(skill)
        dimension_scores[Dimension.CONTEXT_APPROPRIATENESS] = self._evaluate_context(skill)
        dimension_scores[Dimension.EDGE_CASE_HANDLING] = self._evaluate_edge_cases(skill)
        dimension_scores[Dimension.REGRESSION_SAFETY] = self._evaluate_regression_safety(skill)

        # 需要 trace 的维度
        if trace:
            dimension_scores[Dimension.EXECUTIVE_EFFECTIVENESS] = self._evaluate_effectiveness(
                trace
            )
            dimension_scores[Dimension.FAILURE_MODE_ENCODING] = self._evaluate_failure_modes(
                skill, trace
            )
            dimension_scores[Dimension.RESOURCE_EFFICIENCY] = self._evaluate_resource_efficiency(
                trace
            )
            dimension_scores[Dimension.USER_FEEDBACK] = self._evaluate_user_feedback(trace)
        else:
            # 无 trace 时给默认分
            for dim in [
                Dimension.EXECUTIVE_EFFECTIVENESS,
                Dimension.FAILURE_MODE_ENCODING,
                Dimension.RESOURCE_EFFICIENCY,
                Dimension.USER_FEEDBACK,
            ]:
                dimension_scores[dim] = DimensionScore(
                    dimension=dim,
                    score=50.0,
                    reason="No execution trace available",
                )

        # 检测失败模式
        failure_modes = self._detect_failure_modes(skill)

        # 检测黑名单违规
        blacklist_violations = self._check_blacklist(skill)

        # 计算总分
        total = self._calculate_total(dimension_scores)

        # 黑名单违规直接降级
        if blacklist_violations:
            total = max(0, total - 30)

        # 生成建议
        suggestions = self._generate_suggestions(
            dimension_scores, failure_modes, blacklist_violations
        )

        return SkillScore(
            total=total,
            dimensions=dimension_scores,
            failure_modes=failure_modes,
            blacklist_violations=blacklist_violations,
            suggestions=suggestions,
        )

    # ------------------------------------------------------------------
    # LLM 复核（参考 bench/judge.py 的两级判定模式）
    # ------------------------------------------------------------------

    async def evaluate_with_judge(
        self,
        skill: SkillProtocol,
        trace: TraceProtocol = None,
        llm: Callable[..., Any] | None = None,
    ) -> SkillScore:
        """启发式打分 + 可选 LLM 复核的两级评估。

        流程：
          1. 先跑现有启发式 9 维打分（与 evaluate() 完全一致）
          2. 若有可用 LLM，构造紧凑 prompt 让其对内容质量/可执行性/安全性
             三维度给 0-100 分和一句理由（严格 JSON 输出）
          3. 对命中的三个维度按 0.6*启发式 + 0.4*LLM 合成，
             DimensionScore.source 标注为 llm_blend，其余维度保持 heuristic

        任何 LLM 失败（超时/异常/JSON 解析失败）均静默回退纯启发式结果。

        Args:
            skill: 技能实例
            trace: 执行轨迹（可选）
            llm: 本次复核使用的 LLM callable；为 None 时回退构造函数传入的 self.llm

        Returns:
            SkillScore: 综合评分
        """
        base = await self.evaluate(skill, trace)
        judge_llm = llm or self.llm
        if judge_llm is None:
            return base

        try:
            llm_scores = await asyncio.wait_for(
                self._llm_judge_scores(skill, trace, judge_llm),
                timeout=self.llm_timeout,
            )
        except Exception as exc:
            _logger.warning("LLM 技能复核不可用，退回纯启发式: %s", exc)
            return base

        if not llm_scores:
            return base
        return self._blend_with_llm(base, llm_scores)

    def _build_judge_prompt(self, skill: SkillProtocol, trace: TraceProtocol) -> str:
        """构造紧凑的 LLM 复核 prompt。"""
        content = skill.content[:2000]
        trace_summary = "无执行轨迹"
        if trace is not None:
            trace_summary = (
                f"success={getattr(trace, 'success', None)}, "
                f"duration_ms={getattr(trace, 'duration_ms', 0)}, "
                f"tokens_used={getattr(trace, 'tokens_used', 0)}, "
                f"errors={list(getattr(trace, 'errors', []) or [])[:5]}"
            )
        return f"""你是技能质量评审专家。请对以下技能文档做三个维度的语义评估。

【技能名称】{skill.name}
【技能描述】{(skill.description or '')[:300]}
【技能内容（截断）】
{content}

【最近一次执行摘要】
{trace_summary}

请严格只输出如下 JSON（不要输出其他任何内容）：
{{
  "content_quality": {{"score": <0-100>, "reason": "<一句话理由>"}},
  "executability": {{"score": <0-100>, "reason": "<一句话理由>"}},
  "safety": {{"score": <0-100>, "reason": "<一句话理由>"}}
}}
判定标准：
- content_quality: 结构完整性、表述清晰度、信息密度
- executability: 指令是否明确可照做、步骤与输入输出是否完备
- safety: 是否含高风险命令、是否给出必要的警告与防护"""

    async def _llm_judge_scores(
        self,
        skill: SkillProtocol,
        trace: TraceProtocol,
        judge_llm: Callable[..., Any],
    ) -> dict[str, dict[str, Any]] | None:
        """调用 LLM 获取三维度评分；失败返回 None（静默回退）。"""
        prompt = self._build_judge_prompt(skill, trace)
        try:
            resp = await judge_llm([{"role": "user", "content": prompt}], tools=None)
            content = ""
            if isinstance(resp, dict):
                choices = resp.get("choices") or []
                if choices:
                    content = (choices[0].get("message") or {}).get("content", "") or ""
            elif hasattr(resp, "content"):
                content = resp.content or ""
            payload = _extract_json(content)
            if not payload:
                _logger.warning("LLM 复核返回无法解析的 JSON，退回纯启发式")
                return None
            return payload
        except Exception as exc:
            _logger.warning("LLM 复核调用失败，退回纯启发式: %s", exc)
            return None

    def _blend_with_llm(
        self,
        base: SkillScore,
        llm_scores: dict[str, dict[str, Any]],
    ) -> SkillScore:
        """将 LLM 三维评分与启发式结果按 0.6/0.4 加权合成。"""
        blended_dims: dict[Dimension, DimensionScore] = {}
        for dim, dim_score in base.dimensions.items():
            blended_dims[dim] = DimensionScore(
                dimension=dim_score.dimension,
                score=dim_score.score,
                reason=dim_score.reason,
                suggestions=list(dim_score.suggestions),
                source=dim_score.source,
            )

        for key, dim in self.JUDGE_DIMENSION_MAP.items():
            entry = llm_scores.get(key)
            if not isinstance(entry, dict):
                continue  # 该维度 LLM 未给出 → 保持启发式分
            try:
                llm_score = float(entry.get("score"))
            except (TypeError, ValueError):
                continue
            llm_score = min(100.0, max(0.0, llm_score))
            heuristic = blended_dims[dim]
            final = (
                self.BLEND_WEIGHT_HEURISTIC * heuristic.score
                + self.BLEND_WEIGHT_LLM * llm_score
            )
            llm_reason = str(entry.get("reason", "")).strip()[:120]
            blended_dims[dim] = DimensionScore(
                dimension=dim,
                score=min(100.0, max(0.0, final)),
                reason=(
                    f"{heuristic.reason}; LLM: {llm_reason}"
                    if llm_reason else heuristic.reason
                ),
                suggestions=list(heuristic.suggestions),
                source="llm_blend",
            )

        total = self._calculate_total(blended_dims)

        # 黑名单违规降级逻辑与 evaluate() 保持一致
        if base.blacklist_violations:
            total = max(0, total - 30)

        return SkillScore(
            total=total,
            dimensions=blended_dims,
            failure_modes=list(base.failure_modes),
            blacklist_violations=list(base.blacklist_violations),
            suggestions=list(base.suggestions),
        )

    def _evaluate_structure(self, skill: SkillProtocol) -> DimensionScore:
        """评估结构质量。"""
        score = 100.0
        suggestions = []

        content = skill.content

        # 检查必需字段
        for field_name in self.REQUIRED_SKILL_FIELDS:
            if field_name not in content.lower():
                score -= 10
                suggestions.append(f"Missing required field: {field_name}")

        # 检查推荐字段
        for field_name in self.RECOMMENDED_FIELDS:
            if field_name not in content.lower():
                score -= 3
                suggestions.append(f"Consider adding: {field_name}")

        # 检查格式
        if not content.startswith("#"):
            score -= 5
            suggestions.append("SKILL.md should start with a heading")

        # 检查长度
        if len(content) < 100:
            score -= 10
            suggestions.append("SKILL.md is too short, add more details")
        elif len(content) > 10000:
            score -= 5
            suggestions.append("SKILL.md is too long, consider splitting")

        return DimensionScore(
            dimension=Dimension.STRUCTURE_QUALITY,
            score=max(0, score),
            reason=f"Structure check: {len(content)} chars",
            suggestions=suggestions,
        )

    def _evaluate_actionable(self, skill: SkillProtocol) -> DimensionScore:
        """评估可执行具体性。"""
        score = 50.0  # 基础分
        suggestions = []

        content = skill.content.lower()

        # 检查是否有具体步骤
        step_indicators = ["step", "步骤", "1.", "first", "首先", "- [ ]"]
        step_count = sum(1 for ind in step_indicators if ind in content)
        score += min(step_count * 10, 30)

        # 检查是否有代码示例
        if "```" in content:
            score += 15
        else:
            suggestions.append("Add code examples for clarity")

        # 检查是否有明确输入输出
        io_indicators = ["input", "output", "输入", "输出", "parameter", "return"]
        io_count = sum(1 for ind in io_indicators if ind in content)
        score += min(io_count * 5, 20)

        return DimensionScore(
            dimension=Dimension.ACTIONABLE_SPECIFICITY,
            score=min(100, score),
            reason=f"Actionable indicators: steps={step_count}, io={io_count}",
            suggestions=suggestions,
        )

    def _evaluate_context(self, skill: SkillProtocol) -> DimensionScore:
        """评估上下文适当性。"""
        score = 70.0  # 基础分
        suggestions = []

        content = skill.content.lower()

        # 检查是否描述了适用场景
        context_indicators = ["when", "适用", "场景", "use case", "适合"]
        if any(ind in content for ind in context_indicators):
            score += 15
        else:
            suggestions.append("Describe when to use this skill")

        # 检查是否描述了限制
        limit_indicators = ["limitation", "限制", "not for", "不适合", "caveat"]
        if any(ind in content for ind in limit_indicators):
            score += 15
        else:
            suggestions.append("Describe limitations and caveats")

        return DimensionScore(
            dimension=Dimension.CONTEXT_APPROPRIATENESS,
            score=min(100, score),
            suggestions=suggestions,
        )

    def _evaluate_edge_cases(self, skill: SkillProtocol) -> DimensionScore:
        """评估边界情况处理。"""
        score = 50.0  # 基础分
        suggestions = []

        content = skill.content.lower()

        # 检查是否处理了错误情况
        error_indicators = ["error", "错误", "fail", "失败", "exception", "异常"]
        if any(ind in content for ind in error_indicators):
            score += 20
        else:
            suggestions.append("Add error handling guidance")

        # 检查是否处理了边界情况
        edge_indicators = ["edge case", "边界", "empty", "空", "null", "none"]
        if any(ind in content for ind in edge_indicators):
            score += 20
        else:
            suggestions.append("Add edge case handling")

        # 检查是否有 fallback
        fallback_indicators = ["fallback", "备选", "alternative", "如果"]
        if any(ind in content for ind in fallback_indicators):
            score += 10

        return DimensionScore(
            dimension=Dimension.EDGE_CASE_HANDLING,
            score=min(100, score),
            suggestions=suggestions,
        )

    def _evaluate_regression_safety(self, skill: SkillProtocol) -> DimensionScore:
        """评估回归安全性。"""
        score = 80.0  # 基础分
        suggestions = []

        content = skill.content

        # 检查是否有破坏性命令
        destructive_patterns = [
            r"rm\s+-rf",
            r"DROP\s+TABLE",
            r"DELETE\s+FROM",
            r"truncate",
        ]

        for pattern in destructive_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                score -= 20
                suggestions.append(f"Destructive command detected: {pattern}")

        # 检查是否有安全提示
        safety_indicators = ["warning", "警告", "caution", "注意", "danger", "危险"]
        if destructive_patterns and not any(ind in content.lower() for ind in safety_indicators):
            score -= 10
            suggestions.append("Add safety warnings for destructive operations")

        return DimensionScore(
            dimension=Dimension.REGRESSION_SAFETY,
            score=max(0, score),
            suggestions=suggestions,
        )

    def _evaluate_effectiveness(self, trace: TraceProtocol) -> DimensionScore:
        """评估执行效果。"""
        if trace.success:
            score = 90.0
            reason = "Execution successful"
        else:
            score = 30.0
            reason = "Execution failed"

        return DimensionScore(
            dimension=Dimension.EXECUTIVE_EFFECTIVENESS,
            score=score,
            reason=reason,
        )

    def _evaluate_failure_modes(
        self,
        skill: SkillProtocol,
        trace: TraceProtocol,
    ) -> DimensionScore:
        """评估失败模式编码。"""
        score = 50.0
        suggestions = []

        # 检查 skill 是否包含错误处理指导
        content = skill.content.lower()
        error_indicators = ["error", "错误", "fail", "失败", "troubleshoot"]

        if any(ind in content for ind in error_indicators):
            score += 30
        else:
            suggestions.append("Add error handling guidance")

        # 检查 trace 中的错误是否被预期
        if trace.errors:
            # 有错误发生
            if any(ind in content for ind in error_indicators):
                score += 20  # 错误被预期
            else:
                score -= 10  # 错误未被预期
                suggestions.append("Unexpected errors occurred")

        return DimensionScore(
            dimension=Dimension.FAILURE_MODE_ENCODING,
            score=min(100, max(0, score)),
            suggestions=suggestions,
        )

    def _evaluate_resource_efficiency(self, trace: TraceProtocol) -> DimensionScore:
        """评估资源效率。"""
        score = 70.0  # 基础分

        # Token 效率
        if trace.tokens_used > 0:
            if trace.tokens_used < 1000:
                score += 20
            elif trace.tokens_used > 10000:
                score -= 20

        # 时间效率
        if trace.duration_ms > 0:
            if trace.duration_ms < 5000:
                score += 10
            elif trace.duration_ms > 60000:
                score -= 10

        return DimensionScore(
            dimension=Dimension.RESOURCE_EFFICIENCY,
            score=min(100, max(0, score)),
            reason=f"Tokens: {trace.tokens_used}, Duration: {trace.duration_ms}ms",
        )

    def _evaluate_user_feedback(self, trace: TraceProtocol) -> DimensionScore:
        """评估用户反馈。"""
        feedback = trace.user_feedback

        if not feedback:
            return DimensionScore(
                dimension=Dimension.USER_FEEDBACK,
                score=50.0,
                reason="No user feedback available",
            )

        # 从反馈中提取评分
        rating = feedback.get("rating", 3)  # 1-5
        score = rating * 20  # 转换为 0-100

        return DimensionScore(
            dimension=Dimension.USER_FEEDBACK,
            score=score,
            reason=f"User rating: {rating}/5",
        )

    def _detect_failure_modes(self, skill: SkillProtocol) -> list[str]:
        """检测失败模式。"""
        modes = []
        content = skill.content.lower()

        # 检查常见问题
        if "todo" in content or "fixme" in content:
            modes.append("incomplete_implementation")

        if "hack" in content or "workaround" in content:
            modes.append("uses_workarounds")

        if len(content) < 50:
            modes.append("insufficient_detail")

        return modes

    def _check_blacklist(self, skill: SkillProtocol) -> list[str]:
        """检查黑名单违规。"""
        violations = []
        content = skill.content

        for pattern in self.blacklist:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append(pattern)

        return violations

    def _calculate_total(self, scores: dict[Dimension, DimensionScore]) -> float:
        """计算加权总分。"""
        total = 0.0

        for dim, score in scores.items():
            weight = self.weights.get(dim, 0.1)
            total += score.score * weight

        return total

    def _generate_suggestions(
        self,
        scores: dict[Dimension, DimensionScore],
        failure_modes: list[str],
        blacklist_violations: list[str],
    ) -> list[str]:
        """生成改进建议。"""
        suggestions = []

        # 收集各维度的建议
        for dim, score in scores.items():
            if score.score < 70:
                suggestions.extend(score.suggestions)

        # 失败模式建议
        if "incomplete_implementation" in failure_modes:
            suggestions.append("Complete TODO/FIXME items")

        if "insufficient_detail" in failure_modes:
            suggestions.append("Add more detail to SKILL.md")

        # 黑名单建议
        if blacklist_violations:
            suggestions.append("CRITICAL: Remove high-risk commands from skill")

        return suggestions[:10]  # 最多 10 条建议


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 回复中提取 JSON 对象（容忍 markdown 围栏），同 bench/judge.py。"""
    text = re.sub(r"```(?:json)?\s*|\s*```", "", text or "")
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
