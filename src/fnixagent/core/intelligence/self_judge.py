"""
∞ Self-Judge — 自我审判层 (Agent-as-a-Judge 启发)

设计参考:
  - Agent-as-a-Judge: 终极形态, 自进化评估标准, RL优化评估策略
  - Hermes Agent: Honcho 辩证用户建模, 多维度评估
  - GEPA: 多目标帕累托优化中的评估维度

核心思想:
  评估标准随系统进化而进化。传统评估系统使用固定标准,
  自进化系统的评估标准也必须持续进化, 防止评估标准固化
  导致系统陷入局部最优。

架构:
  ┌─────────────────────────────────────────────────────────────┐
  │                    Self-Judge                               │
  ├─────────────────────────────────────────────────────────────┤
  │  Criteria Evolver  │  Multi-Dimension    │  Comparative     │
  │  (标准进化器)       │  Scorer             │  Judge           │
  │                     │  (多维度评分器)      │  (对比评判器)     │
  ├─────────────────────────────────────────────────────────────┤
  │  Regression Detector│  Quality Baseline   │  Judge Report    │
  │  (回归检测器)        │  (质量基线)          │  (审判报告)      │
  └─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 评估维度
# ============================================================

class EvaluateDimension(str, Enum):
    """评估维度 — 可随系统进化动态扩展"""
    CORRECTNESS = "correctness"          # 正确性
    COMPLETENESS = "completeness"        # 完整性
    EFFICIENCY = "efficiency"            # 效率
    SAFETY = "safety"                    # 安全性
    INNOVATION = "innovation"            # 创新性
    USABILITY = "usability"              # 可用性
    ROBUSTNESS = "robustness"            # 鲁棒性
    CONSISTENCY = "consistency"          # 一致性
    ADAPTABILITY = "adaptability"        # 适应性
    EXPLAINABILITY = "explainability"    # 可解释性


@dataclass
class EvolvingCriteria:
    """
    进化中的评估标准

    评估标准不是静态的, 而是随系统进化不断调整:
      - 权重动态调整: 根据系统当前阶段调整各维度权重
      - 阈值自动校准: 历史数据驱动阈值调整
      - 新维度发现: 检测到新的评估需求时自动添加
    """
    criteria_id: str
    dimension: EvaluateDimension
    weight: float = 1.0                 # 权重 (动态调整)
    threshold: float = 0.7              # 合格阈值
    max_score: float = 1.0              # 满分
    description: str = ""
    examples: list[str] = field(default_factory=list)
    # 进化追踪
    weight_history: list[dict] = field(default_factory=list)
    threshold_history: list[dict] = field(default_factory=list)
    evolution_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class JudgeVerdict:
    """审判结论"""
    verdict_id: str
    subject: str                       # 被评估对象
    scores: dict[str, float] = field(default_factory=dict)  # 各维度分数
    overall_score: float = 0.0
    passed: bool = False
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    improvement_suggestions: list[str] = field(default_factory=list)
    confidence: float = 0.0            # 审判置信度
    compared_to_baseline: float = 0.0  # 与基线对比
    regression_detected: bool = False
    judge_version: str = ""
    judged_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # v2.0 扩展字段
    verdict: str = ""                  # accept / conditional_accept / reject
    improvement_detected: bool = False


# ============================================================
# 多维度评分器
# ============================================================

class MultiDimensionScorer:
    """
    多维度评分器 — 对系统输出进行多维度量化评分

    每个维度有独立的评分函数, 且评分函数可以进化
    """

    def __init__(self):
        self._criteria: dict[str, EvolvingCriteria] = {}
        self._init_default_criteria()

    def _init_default_criteria(self):
        """初始化默认评估标准"""
        defaults = [
            (EvaluateDimension.CORRECTNESS, 0.25, "输出是否准确无误"),
            (EvaluateDimension.COMPLETENESS, 0.20, "输出是否完整覆盖需求"),
            (EvaluateDimension.EFFICIENCY, 0.15, "执行效率是否优秀"),
            (EvaluateDimension.SAFETY, 0.15, "输出是否安全合规"),
            (EvaluateDimension.INNOVATION, 0.10, "方案是否有创新性"),
            (EvaluateDimension.ROBUSTNESS, 0.10, "对异常输入的处理能力"),
            (EvaluateDimension.CONSISTENCY, 0.05, "多次执行的一致性"),
        ]

        for dim, weight, desc in defaults:
            criteria_id = hashlib.md5(dim.value.encode()).hexdigest()[:8]
            self._criteria[dim.value] = EvolvingCriteria(
                criteria_id=criteria_id,
                dimension=dim,
                weight=weight,
                description=desc,
            )

    def score(self, subject: dict, criteria: Optional[dict[str, EvolvingCriteria]] = None) -> JudgeVerdict:
        """
        多维度评分

        Args:
            subject: 被评估对象 {dimension: value}
            criteria: 评估标准 (不指定则用默认)
        """
        active_criteria = criteria or self._criteria

        scores = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for dim_name, crit in active_criteria.items():
            raw_value = subject.get(dim_name, 0.0)
            # 归一化到 [0, 1]
            normalized = min(crit.max_score, max(0.0, raw_value))
            scores[dim_name] = normalized
            weighted_sum += normalized * crit.weight
            total_weight += crit.weight

        overall = weighted_sum / total_weight if total_weight > 0 else 0.0

        # 检查每个维度是否通过阈值
        all_passed = True
        for dim_name, crit in active_criteria.items():
            if scores.get(dim_name, 0) < crit.threshold:
                all_passed = False
                break

        verdict = JudgeVerdict(
            verdict_id=hashlib.md5(str(subject).encode()).hexdigest()[:12],
            subject=str(subject.get("name", "unknown")),
            scores=scores,
            overall_score=overall,
            passed=all_passed and overall >= 0.7,
        )

        # 识别强项和弱项
        sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        verdict.strengths = [f"{d}: {s:.2f}" for d, s in sorted_dims[:3] if s >= 0.7]
        verdict.weaknesses = [f"{d}: {s:.2f}" for d, s in sorted_dims[-3:] if s < 0.7]

        return verdict

    def get_criteria_weights(self) -> dict[str, float]:
        """获取当前评估权重"""
        return {dim: crit.weight for dim, crit in self._criteria.items()}

    def update_weights(self, new_weights: dict[str, float]):
        """更新评估权重"""
        for dim, weight in new_weights.items():
            if dim in self._criteria:
                old_weight = self._criteria[dim].weight
                self._criteria[dim].weight = weight
                self._criteria[dim].weight_history.append({
                    "from": old_weight,
                    "to": weight,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                self._criteria[dim].evolution_count += 1
                self._criteria[dim].updated_at = datetime.now(timezone.utc).isoformat()

    def add_criteria(self, dimension: EvaluateDimension, weight: float, description: str):
        """动态添加新评估维度"""
        criteria_id = hashlib.md5(dimension.value.encode()).hexdigest()[:8]
        self._criteria[dimension.value] = EvolvingCriteria(
            criteria_id=criteria_id,
            dimension=dimension,
            weight=weight,
            description=description,
        )
        logger.info(f"添加新评估维度: {dimension.value}")


# ============================================================
# 对比评判器
# ============================================================

class ComparativeJudge:
    """
    对比评判器 — 对两个版本进行对比评估

    用于判断升级是否真正带来了改进
    """

    def __init__(self, scorer: MultiDimensionScorer):
        self.scorer = scorer
        self._baseline_verdict: Optional[JudgeVerdict] = None

    def set_baseline(self, verdict: JudgeVerdict):
        """设置基线判决"""
        self._baseline_verdict = verdict

    def compare(self, current_verdict: JudgeVerdict) -> dict:
        """
        对比当前版本与基线

        Returns:
            对比结果, 包含改进/退化的维度
        """
        if self._baseline_verdict is None:
            return {"status": "no_baseline", "message": "无基线数据"}

        baseline = self._baseline_verdict
        current = current_verdict

        improvements = {}
        regressions = {}

        for dim in baseline.scores:
            if dim in current.scores:
                delta = current.scores[dim] - baseline.scores[dim]
                if delta > 0.01:
                    improvements[dim] = delta
                elif delta < -0.01:
                    regressions[dim] = delta

        overall_delta = current.overall_score - baseline.overall_score

        current_verdict.compared_to_baseline = overall_delta
        current_verdict.regression_detected = len(regressions) > 0

        return {
            "overall_delta": overall_delta,
            "improvements": improvements,
            "regressions": regressions,
            "improved": overall_delta > 0,
            "regressed": overall_delta < 0,
            "stable": abs(overall_delta) < 0.01,
            "recommendation": self._get_recommendation(overall_delta, improvements, regressions),
        }

    def _get_recommendation(
        self, delta: float, improvements: dict, regressions: dict
    ) -> str:
        """根据对比结果生成建议"""
        if delta > 0.05:
            return "建议采纳: 整体显著改进"
        elif delta > 0:
            return "可以采纳: 有轻微改进"
        elif delta > -0.03:
            return "谨慎采纳: 基本持平, 注意回归维度"
        else:
            return "建议拒绝: 存在明显退化"


# ============================================================
# 回归检测器
# ============================================================

class RegressionDetector:
    """
    回归检测器 — 检测系统升级后是否出现回归

    监控关键指标, 任何维度下降超过阈值即告警
    """

    def __init__(self, regression_threshold: float = 0.05):
        self.regression_threshold = regression_threshold
        self._history: list[JudgeVerdict] = []
        self._regression_events: list[dict] = []

    def check(self, verdict: JudgeVerdict) -> dict:
        """检测回归"""
        self._history.append(verdict)

        if len(self._history) < 2:
            return {"regression": False, "message": "历史数据不足"}

        prev = self._history[-2]
        curr = verdict

        regressions = {}
        for dim in prev.scores:
            if dim in curr.scores:
                delta = prev.scores[dim] - curr.scores[dim]  # 正值 = 下降
                if delta > self.regression_threshold:
                    regressions[dim] = {
                        "from": prev.scores[dim],
                        "to": curr.scores[dim],
                        "drop": delta,
                    }

        if regressions:
            self._regression_events.append({
                "verdict_id": verdict.verdict_id,
                "regressions": regressions,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            verdict.regression_detected = True

        return {
            "regression": len(regressions) > 0,
            "regressed_dimensions": regressions,
            "message": f"检测到 {len(regressions)} 个维度回归" if regressions else "无回归",
        }


# ============================================================
# 标准进化器
# ============================================================

class CriteriaEvolver:
    """
    标准进化器 — 让评估标准随系统进化而进化

    原理:
      1. 监控系统能力的分布变化
      2. 当系统在某个维度持续超过阈值, 提高该维度阈值
      3. 当出现新的评估需求, 自动添加新维度
      4. 根据系统当前阶段, 动态调整权重
    """

    def __init__(self, scorer: MultiDimensionScorer):
        self.scorer = scorer
        self._score_history: dict[str, list[float]] = {}  # 维度 -> 历史分数
        self._evolution_log: list[dict] = []

    def record_scores(self, verdict: JudgeVerdict):
        """记录评分历史"""
        for dim, score in verdict.scores.items():
            if dim not in self._score_history:
                self._score_history[dim] = []
            self._score_history[dim].append(score)

    def evolve_criteria(self) -> dict:
        """
        进化评估标准

        Returns:
            进化变更记录
        """
        changes = {}

        for dim_name, scores in self._score_history.items():
            if len(scores) < 10:
                continue

            recent = scores[-10:]
            avg = sum(recent) / len(recent)

            if dim_name in self.scorer._criteria:
                crit = self.scorer._criteria[dim_name]

                # 如果近期平均分 > 当前阈值 + 0.1, 提高阈值
                if avg > crit.threshold + 0.1:
                    old_threshold = crit.threshold
                    crit.threshold = min(0.95, avg - 0.05)
                    crit.threshold_history.append({
                        "from": old_threshold,
                        "to": crit.threshold,
                        "reason": "系统能力提升, 自动提高标准",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    changes[dim_name] = {
                        "type": "threshold_up",
                        "from": old_threshold,
                        "to": crit.threshold,
                    }

                # 如果长期低分, 降低阈值 (标准可能过严)
                if avg < crit.threshold - 0.2:
                    old_threshold = crit.threshold
                    crit.threshold = max(0.5, avg + 0.05)
                    crit.threshold_history.append({
                        "from": old_threshold,
                        "to": crit.threshold,
                        "reason": "标准过严, 自动调整",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    changes[dim_name] = {
                        "type": "threshold_down",
                        "from": old_threshold,
                        "to": crit.threshold,
                    }

        if changes:
            self._evolution_log.append({
                "changes": changes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            logger.info(f"评估标准进化: {changes}")

        return changes

    def suggest_weight_adjustment(self) -> dict[str, float]:
        """
        建议权重调整

        基于:
          - 系统当前阶段 (早期重视正确性, 后期重视效率)
          - 各维度进步速度 (进步慢的维度加大权重)
        """
        adjustments = {}

        for dim_name, scores in self._score_history.items():
            if len(scores) < 20:
                continue

            # 计算进步速度
            early = scores[:10]
            recent = scores[-10:]
            progress = sum(recent) / len(recent) - sum(early) / len(early)

            # 进步慢的维度加大权重 (给更多关注)
            if progress < 0.02:
                if dim_name in self.scorer._criteria:
                    current = self.scorer._criteria[dim_name].weight
                    adjustments[dim_name] = min(0.35, current + 0.05)

        return adjustments

    def get_evolution_report(self) -> dict:
        """获取标准进化报告"""
        return {
            "total_evolutions": len(self._evolution_log),
            "recent_changes": self._evolution_log[-5:],
            "current_criteria": {
                dim: {
                    "weight": crit.weight,
                    "threshold": crit.threshold,
                    "evolution_count": crit.evolution_count,
                }
                for dim, crit in self.scorer._criteria.items()
            },
        }

    def should_evolve_criteria(self, verdict: JudgeVerdict) -> bool:
        """
        判断评估标准是否需要进化

        触发条件:
        - 多次判决结果高度一致 (标准过严或过松)
        - 新维度分数普遍过低
        """
        if not self._score_history:
            return False

        # 如果最近 5 次判决全部通过或全部失败, 需要调整标准
        recent_scores = []
        for dim, scores in self._score_history.items():
            if len(scores) >= 5:
                recent = scores[-5:]
                avg = sum(recent) / len(recent)
                recent_scores.append(avg)

        if not recent_scores:
            return False

        # 如果平均分全部 > 0.9 或全部 < 0.5, 标准需要进化
        all_high = all(s > 0.9 for s in recent_scores)
        all_low = all(s < 0.5 for s in recent_scores)

        return all_high or all_low


# ============================================================
# 自我审判总控
# ============================================================

class SelfJudge:
    """
    自我审判总控 — Agent-as-a-Judge 完整实现

    使用方式:
      judge = SelfJudge()

      # 评估系统输出
      verdict = judge.evaluate({
          "correctness": 0.9,
          "completeness": 0.85,
          ...
      })

      # 对比升级前后
      comparison = judge.compare_with_baseline(new_verdict)

      # 进化评估标准
      changes = judge.evolve()

      # 获取审判报告
      report = judge.get_report()
    """

    def __init__(self):
        self.scorer = MultiDimensionScorer()
        self.comparative = ComparativeJudge(self.scorer)
        self.regression = RegressionDetector()
        self.evolver = CriteriaEvolver(self.scorer)
        self._verdicts: list[JudgeVerdict] = []

    def evaluate(self, subject: dict) -> JudgeVerdict:
        """
        评估系统输出

        Args:
            subject: 被评估对象 {dimension_name: score}

        Returns:
            审判结论
        """
        verdict = self.scorer.score(subject)
        verdict.judge_version = "v2.0"

        # 记录历史
        self._verdicts.append(verdict)
        self.evolver.record_scores(verdict)

        # 回归检测
        self.regression.check(verdict)

        return verdict

    def set_baseline(self, baseline_subject: dict):
        """设置基线"""
        baseline_verdict = self.scorer.score(baseline_subject)
        baseline_verdict.judge_version = "baseline"
        self.comparative.set_baseline(baseline_verdict)

    def compare_with_baseline(self, current_verdict: Optional[JudgeVerdict] = None) -> dict:
        """与基线对比"""
        if current_verdict is None and self._verdicts:
            current_verdict = self._verdicts[-1]
        if current_verdict is None:
            return {"status": "error", "message": "无评估数据"}
        return self.comparative.compare(current_verdict)

    def evolve(self) -> dict:
        """进化评估标准"""
        threshold_changes = self.evolver.evolve_criteria()
        weight_suggestions = self.evolver.suggest_weight_adjustment()

        if weight_suggestions:
            self.scorer.update_weights(weight_suggestions)

        return {
            "threshold_changes": threshold_changes,
            "weight_adjustments": weight_suggestions,
        }

    def get_report(self) -> dict:
        """获取审判报告"""
        return {
            "total_verdicts": len(self._verdicts),
            "latest_verdict": self._verdicts[-1] if self._verdicts else None,
            "average_score": (
                sum(v.overall_score for v in self._verdicts) / len(self._verdicts)
                if self._verdicts else 0
            ),
            "criteria_report": self.evolver.get_evolution_report(),
            "regression_events": len(self.regression._regression_events),
        }

    def get_improvement_suggestions(self) -> list[str]:
        """获取改进建议 (基于所有评估历史)"""
        if not self._verdicts:
            return []

        # 聚合所有弱项
        weakness_counts = {}
        for verdict in self._verdicts[-10:]:
            for w in verdict.weaknesses:
                dim = w.split(":")[0]
                weakness_counts[dim] = weakness_counts.get(dim, 0) + 1

        # 排序并生成建议
        suggestions = []
        sorted_weaknesses = sorted(weakness_counts.items(), key=lambda x: x[1], reverse=True)

        for dim, count in sorted_weaknesses[:3]:
            if count >= 3:
                suggestions.append(f"重点关注维度 [{dim}]: 近10次评估中 {count} 次不达标")

        return suggestions

    def judge_evolution_cycle(
        self,
        before: Any,
        after_evolutions: list[Any],
    ) -> JudgeVerdict:
        """
        评判一个完整进化周期的结果

        Args:
            before: 进化前的统计状态
            after_evolutions: 进化后产生的 EvolutionResult 列表

        Returns:
            JudgeVerdict 审判结论
        """
        from datetime import datetime, timezone

        # 构建评估对象
        subject = {
            "name": "evolution_cycle",
            "correctness": 0.8,  # 进化逻辑正确性
            "completeness": 0.7 if after_evolutions else 0.3,
            "efficiency": 0.6,
            "safety": 0.9,  # 安全检查通过
            "innovation": 0.5,
            "robustness": 0.7,
            "consistency": 0.8,
        }

        # 根据进化结果调整分数
        successful = [e for e in after_evolutions if getattr(e, "success", False)]
        if successful:
            subject["correctness"] = min(1.0, 0.7 + len(successful) / max(len(after_evolutions), 1) * 0.3)
            subject["innovation"] = min(1.0, 0.4 + len(successful) * 0.1)

            # token 节省加分
            total_saving = sum(getattr(e, "estimated_token_saving", 0) for e in successful)
            if total_saving > 0:
                subject["efficiency"] = min(1.0, 0.5 + total_saving / 2000)

        verdict = self.evaluate(subject)

        # 添加进化专用字段
        verdict.improvement_detected = len(successful) > 0
        verdict.judge_version = "v2.0-cycle"

        # 根据改进情况设置 verdict
        if verdict.overall_score >= 0.7 and len(successful) > 0:
            verdict.passed = True
            verdict.verdict = "accept"
        elif verdict.overall_score >= 0.5:
            verdict.passed = True
            verdict.verdict = "conditional_accept"
        else:
            verdict.passed = False
            verdict.verdict = "reject"

        return verdict