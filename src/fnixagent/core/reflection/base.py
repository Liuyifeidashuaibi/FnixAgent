"""多评估器反思质量系统 - 核心数据结构。

定义反思配置/问题/结果的基础数据类,供 evaluators 与 manager 使用。

注意: 此处 ReflectionResult 与 core.types.ReflectionResult 为不同类:
  - core.types.ReflectionResult: 旧版简单反思结果(passed/score/reason)
  - core.reflection.base.ReflectionResult: 新版多评估器反思结果
    (sub_scores/issues/should_reflect/feedback_message)

P0-04 新增,参考 kaoyan-ai-platform 的 reflection/manager.py 设计。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReflectionConfig:
    """反思配置。

    控制多评估器反思系统的行为:启用开关/分数阈值/最大反思次数/
    各评估器开关。

    Attributes:
        enabled: 总开关(关闭后 evaluate 直接返回满分结果)
        min_score_threshold: 触发反思的分数阈值(总分 < 该值 → should_reflect=True)
        max_reflections: 单任务最大反思次数(防止无限循环)
        enable_length_eval: 启用长度评估器
        enable_structure_eval: 启用结构评估器
        enable_keyword_eval: 启用关键词评估器
        enable_citation_eval: 启用引用评估器
        enable_format_eval: 启用格式评估器
        enable_llm_eval: 启用 LLM 评估器(默认关闭,成本高)
    """

    enabled: bool = True
    min_score_threshold: float = 0.7
    max_reflections: int = 2
    enable_length_eval: bool = True
    enable_structure_eval: bool = True
    enable_keyword_eval: bool = True
    enable_citation_eval: bool = True
    enable_format_eval: bool = True
    enable_llm_eval: bool = False


@dataclass
class ReflectionIssue:
    """单个评估问题。

    一个评估器可产生多个 issue(如格式评估器发现既有占位符又有空行)。

    Attributes:
        evaluator: 评估器名称(如 "length"/"format")
        severity: 严重等级 critical / warning
        message: 问题描述
        suggestion: 修正建议(供 LLM 修正使用)
        score_impact: 分数影响(0~1,该问题对子分数的扣分量)
    """

    evaluator: str
    severity: str  # critical / warning
    message: str
    suggestion: str
    score_impact: float


@dataclass
class ReflectionResult:
    """多评估器反思评估结果。

    与 core.types.ReflectionResult 区别:
      - 包含各评估器子分数(sub_scores)
      - 包含具体问题列表(issues)
      - 包含反思反馈消息(feedback_message,供 LLM 修正)
      - 用 should_reflect 替代 needs_replan(语义更清晰)

    Attributes:
        score: 总分 0~1(各子分数加权平均)
        sub_scores: 各评估器子分数 {evaluator_name: score}
        issues: 评估发现的问题列表
        should_reflect: 是否需要反思重做
        feedback_message: 反思反馈消息(供 LLM 修正使用)
    """

    score: float = 1.0
    sub_scores: dict[str, float] = field(default_factory=dict)
    issues: list[ReflectionIssue] = field(default_factory=list)
    should_reflect: bool = False
    feedback_message: str = ""

    def add_issue(
        self,
        evaluator: str,
        severity: str,
        message: str,
        suggestion: str,
        score_impact: float,
    ) -> None:
        """添加一个评估问题。

        Args:
            evaluator: 评估器名称
            severity: 严重等级 critical / warning(其他值规范化为 warning)
            message: 问题描述
            suggestion: 修正建议
            score_impact: 分数影响(0~1,越界自动 clamp)
        """
        # severity 校验(允许 critical/warning,其他值规范化为 warning)
        if severity not in ("critical", "warning"):
            severity = "warning"
        # score_impact clamp 到 [0, 1]
        try:
            impact = float(score_impact)
        except (TypeError, ValueError):
            impact = 0.0
        if impact < 0.0:
            impact = 0.0
        elif impact > 1.0:
            impact = 1.0
        self.issues.append(
            ReflectionIssue(
                evaluator=evaluator,
                severity=severity,
                message=message,
                suggestion=suggestion,
                score_impact=impact,
            )
        )
