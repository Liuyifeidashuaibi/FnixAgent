"""反思管理器(ReflectionManager)。

协调 6 个加权评估器,并行执行评估,加权计算总分,决策是否触发反思重做。

参考 kaoyan-ai-platform 的 reflection/manager.py 设计:
  - 并行执行所有启用的评估器(asyncio.gather + return_exceptions=True)
  - 单评估器超时/异常不阻塞其他评估器
  - 权重归一化(仅计算启用的评估器)
  - 子分数 < 0.6 自动添加问题
  - 反馈消息含具体问题列表 + 修正建议(供 LLM 修正)

并发安全:
  - 配置更新通过 threading.Lock + dataclasses.replace(copy + modify + replace)
  - 单例使用双重检查锁定(double-checked locking)

P0-04 新增。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import dataclasses
import logging
import threading
from typing import Any

from fnixagent.core.reflection.base import (
    ReflectionConfig,
    ReflectionResult,
)
from fnixagent.core.reflection.evaluators import (
    BaseEvaluator,
    CitationEvaluator,
    FormatEvaluator,
    KeywordEvaluator,
    LengthEvaluator,
    LLMEvaluator,
    StructureEvaluator,
)

logger = logging.getLogger(__name__)


class ReflectionManager:
    """反思管理器 - 协调各评估器,决定是否触发反思重做。

    默认权重(对应 6 个评估器):
      - length:     0.15
      - structure:  0.20
      - keyword:    0.20
      - citation:   0.15
      - format:     0.20
      - llm:        0.10

    用法:
        manager = get_reflection_manager()
        result = await manager.evaluate(content, context={"keywords": [...]})
        if result.should_reflect:
            # 用 result.feedback_message 让 LLM 修正内容
            ...

    并发安全:
      - update_config 线程安全(Lock + dataclasses.replace)
      - evaluate 异步,内部不修改共享状态(只读 config 快照)
    """

    _DEFAULT_WEIGHTS: dict[str, float] = {
        "length": 0.15,
        "structure": 0.20,
        "keyword": 0.20,
        "citation": 0.15,
        "format": 0.20,
        "llm": 0.10,
    }

    # 配置字段名 → 评估器名映射(用于按 enable_xxx 过滤)
    _ENABLE_FIELD_MAP: dict[str, str] = {
        "length": "enable_length_eval",
        "structure": "enable_structure_eval",
        "keyword": "enable_keyword_eval",
        "citation": "enable_citation_eval",
        "format": "enable_format_eval",
        "llm": "enable_llm_eval",
    }

    # 单评估器超时(秒)— 超过此时间返回 1.0
    _EVALUATOR_TIMEOUT: float = 10.0

    # 子分数低于该阈值自动添加问题
    _ISSUE_SCORE_THRESHOLD: float = 0.6

    def __init__(
        self,
        config: ReflectionConfig | None = None,
        weights: dict[str, float] | None = None,
        llm: Any = None,
        evaluators: list[BaseEvaluator] | None = None,
    ) -> None:
        """初始化反思管理器。

        Args:
            config: 反思配置(默认 ReflectionConfig())
            weights: 评估器权重覆盖(默认 _DEFAULT_WEIGHTS,只覆盖已知 key)
            llm: LLM 客户端(注入 LLMEvaluator,仅当 config.enable_llm_eval=True 时生效)
            evaluators: 自定义评估器列表(默认创建 6 个内置评估器)
        """
        self._config: ReflectionConfig = config or ReflectionConfig()
        self._weights: dict[str, float] = dict(self._DEFAULT_WEIGHTS)
        if weights:
            # 合并用户权重(只覆盖已知 key,忽略未知 key)
            for k, v in weights.items():
                if k in self._weights and isinstance(v, (int, float)):
                    self._weights[k] = float(v)
        self._llm = llm
        self._lock = threading.Lock()
        # 评估器实例(构造时创建,后续只读访问)
        if evaluators is not None:
            self._evaluators: dict[str, BaseEvaluator] = {e.name: e for e in evaluators}
        else:
            self._evaluators = self._build_default_evaluators(llm)
        # 自定义评估器可能引入不在 _DEFAULT_WEIGHTS 中的名字,
        # 为其分配默认权重 0.1(用户可通过 weights 参数显式覆盖)
        for ename in self._evaluators.keys():
            if ename not in self._weights:
                self._weights[ename] = 0.1

    def _build_default_evaluators(self, llm: Any) -> dict[str, BaseEvaluator]:
        """构建 6 个内置评估器实例。"""
        evaluators: list[BaseEvaluator] = [
            LengthEvaluator(),
            StructureEvaluator(),
            KeywordEvaluator(),
            CitationEvaluator(),
            FormatEvaluator(),
            LLMEvaluator(llm=llm),
        ]
        return {e.name: e for e in evaluators}

    # ------------------------------------------------------------------
    # 核心入口:evaluate
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        content: str,
        context: dict[str, Any] | None = None,
        config: ReflectionConfig | None = None,
    ) -> ReflectionResult:
        """评估内容质量 - 并行执行所有启用的评估器。

        Args:
            content: 待评估内容文本
            context: 评估上下文(可含 keywords/min_length/max_length/goal 等)
            config: 单次评估配置覆盖(不修改 manager 自身配置,None 用 self._config)

        Returns:
            ReflectionResult(含总分/子分数/问题列表/反馈消息)

        实现要点:
          1. 极短内容快速判定(< 50 字符 → 直接低分 + 添加 critical 问题)
          2. 并行执行评估器(asyncio.gather + return_exceptions=True)
          3. 单评估器超时(asyncio.wait_for + asyncio.to_thread) → 返回 1.0
          4. 单评估器异常 → 不阻塞其他,返回 1.0
          5. 权重归一化(仅计算启用的评估器)
          6. 子分数 < 0.6 添加问题
          7. 决策是否反思(总分 < min_score_threshold)
          8. 构建反馈消息(含具体问题列表 + 修正建议)
        """
        # 配置快照(单次评估不修改 self._config)
        cfg = config if config is not None else self._config
        # 系统关闭:直接返回满分
        if not cfg.enabled:
            return ReflectionResult(
                score=1.0,
                should_reflect=False,
                feedback_message="反思系统已关闭",
            )

        ctx = context or {}
        result = ReflectionResult()

        # 1. 极短内容快速判定(< 50 字符)
        content_len = len(content) if content else 0
        if content_len < 50:
            result.score = 0.2
            result.sub_scores = dict.fromkeys(self._evaluators, 0.2)
            result.add_issue(
                evaluator="length",
                severity="critical",
                message=(f"内容过短(仅 {content_len} 字符),无法构成完整回答"),
                suggestion=("请补充更多内容,确保覆盖目标要求的核心信息(建议至少 200 字符)"),
                score_impact=0.8,
            )
            result.should_reflect = self.should_reflect(result, 0, cfg.max_reflections)
            result.feedback_message = self._build_feedback(result)
            return result

        # 2. 收集启用的评估器
        enabled_names = self._get_enabled_evaluators(cfg)
        if not enabled_names:
            # 无评估器启用,返回满分
            result.score = 1.0
            result.feedback_message = "无启用的评估器"
            return result

        # 3. 并行执行评估器
        sub_scores = await self._run_evaluators_parallel(content, ctx, cfg, enabled_names)
        result.sub_scores = sub_scores

        # 4. 权重归一化 + 加权计算总分
        result.score = self._weighted_score(sub_scores, enabled_names)

        # 5. 子分数 < 0.6 添加问题
        self._add_issues_for_low_scores(result, sub_scores)

        # 6. 决策是否反思
        result.should_reflect = self.should_reflect(result, 0, cfg.max_reflections)

        # 7. 构建反馈消息
        result.feedback_message = self._build_feedback(result)

        return result

    async def _run_evaluators_parallel(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
        enabled_names: list[str],
    ) -> dict[str, float]:
        """并行执行所有启用的评估器。

        使用 asyncio.gather(return_exceptions=True) 收集结果,
        单评估器异常/超时不阻塞其他评估器。

        Returns:
            {evaluator_name: sub_score}
        """
        tasks: list[Any] = []
        names_in_order: list[str] = []
        for name in enabled_names:
            evaluator = self._evaluators.get(name)
            if evaluator is None:
                continue
            names_in_order.append(name)
            tasks.append(self._safe_eval_one(evaluator, content, context, config))
        if not tasks:
            return {}
        # 并行执行,return_exceptions=True 保证单失败不阻塞其他
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        sub_scores: dict[str, float] = {}
        for name, raw in zip(names_in_order, raw_results):
            if isinstance(raw, Exception):
                # 评估器抛异常 → 返回 1.0(不拖累总分,记录日志)
                logger.warning(
                    "评估器 %s 执行异常: %s: %s",
                    name,
                    type(raw).__name__,
                    raw,
                )
                sub_scores[name] = 1.0
            elif isinstance(raw, (int, float)):
                sub_scores[name] = float(raw)
            else:
                # 未预期的返回类型,降级为 1.0
                sub_scores[name] = 1.0
        return sub_scores

    async def _safe_eval_one(
        self,
        evaluator: BaseEvaluator,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        """执行单个评估器,带超时保护。

        - 超时(asyncio.TimeoutError)→ 返回 1.0(不因慢评估惩罚)
        - 评估器内部异常 → 透传给上层 _run_evaluators_parallel
          (gather 的 return_exceptions=True 会捕获)
        """
        try:
            score = await asyncio.wait_for(
                asyncio.to_thread(evaluator.evaluate, content, context, config),
                timeout=self._EVALUATOR_TIMEOUT,
            )
        except TimeoutError:
            logger.warning(
                "评估器 %s 超时(>%ss),返回 1.0",
                evaluator.name,
                self._EVALUATOR_TIMEOUT,
            )
            return 1.0
        # 评估器内部异常透传(gather 的 return_exceptions 会捕获)
        return float(score) if isinstance(score, (int, float)) else 1.0

    # ------------------------------------------------------------------
    # 决策与反馈
    # ------------------------------------------------------------------

    def should_reflect(
        self,
        result: ReflectionResult,
        reflection_count: int = 0,
        max_reflections: int | None = None,
    ) -> bool:
        """决策是否触发反思重做。

        触发反思的条件(任一满足即触发,前提是未达最大反思次数):
          1. 存在 critical 问题 → True(必须修复)
          2. 总分 < min_score_threshold → True

        不触发反思的条件:
          - 已达最大反思次数(reflection_count >= max_reflections)
          - 无 critical 问题 且 总分 >= min_score_threshold

        Args:
            result: 评估结果
            reflection_count: 已反思次数(0=首次评估)
            max_reflections: 最大反思次数(None 用 self._config.max_reflections)

        Returns:
            True 表示需要反思重做
        """
        max_refl = max_reflections
        if max_refl is None:
            max_refl = self._config.max_reflections
        if reflection_count >= max_refl:
            return False
        # critical 问题强制反思
        has_critical = any(issue.severity == "critical" for issue in result.issues)
        if has_critical:
            return True
        # 总分低于阈值
        return result.score < self._config.min_score_threshold

    def _add_issues_for_low_scores(
        self,
        result: ReflectionResult,
        sub_scores: dict[str, float],
    ) -> None:
        """对子分数 < 阈值的评估器自动添加问题。"""
        suggestions_map: dict[str, str] = {
            "length": "建议补充内容长度,确保覆盖目标要求(目标 200+ 字符)",
            "structure": "建议增加标题/段落/列表等结构化元素,提升可读性",
            "keyword": "建议覆盖更多目标关键词,确保内容相关性",
            "citation": "建议补充引用标记([1]/[2])与参考文献部分",
            "format": "建议清理占位符/多余空行/尾部空白",
            "llm": "建议改进内容的完整性/逻辑性/准确性",
        }
        messages_map: dict[str, str] = {
            "length": "内容长度不足",
            "structure": "内容结构不清晰",
            "keyword": "关键词覆盖不足",
            "citation": "引用不完整",
            "format": "格式存在不规范",
            "llm": "LLM 综合评估分数偏低",
        }
        for name, score in sub_scores.items():
            if score < self._ISSUE_SCORE_THRESHOLD:
                severity = "critical" if score < 0.3 else "warning"
                impact = self._ISSUE_SCORE_THRESHOLD - score
                result.add_issue(
                    evaluator=name,
                    severity=severity,
                    message=messages_map.get(name, f"{name} 评估分数偏低: {score:.2f}"),
                    suggestion=suggestions_map.get(name, f"建议改进 {name} 维度"),
                    score_impact=impact,
                )

    def _build_feedback(self, result: ReflectionResult) -> str:
        """构建反思反馈消息(供 LLM 修正使用)。

        格式:
          【反思反馈】
          总分: 0.65 (阈值 0.70, 低于阈值,需反思)
          子分数:
            - length: 0.45
            - format: 0.60
            ...
          问题列表:
            [critical] [length] 内容长度不足
              建议: 建议补充内容长度...
            [warning] [format] 格式存在不规范
              建议: 建议清理占位符...
          请根据以上反馈修正内容。
        """
        if not result.issues:
            return f"【反思反馈】总分 {result.score:.2f},未发现明显问题,内容质量达标。"
        parts: list[str] = []
        parts.append("【反思反馈】")
        threshold = self._config.min_score_threshold
        status = "低于阈值,需反思" if result.should_reflect else "达标"
        parts.append(f"总分: {result.score:.2f} (阈值 {threshold:.2f}, {status})")
        if result.sub_scores:
            parts.append("子分数:")
            for name, score in result.sub_scores.items():
                parts.append(f"  - {name}: {score:.2f}")
        parts.append("问题列表:")
        # critical 优先,其次按 score_impact 降序
        sorted_issues = sorted(
            result.issues,
            key=lambda i: (0 if i.severity == "critical" else 1, -i.score_impact),
        )
        for issue in sorted_issues:
            parts.append(f"  [{issue.severity}] [{issue.evaluator}] {issue.message}")
            parts.append(f"    建议: {issue.suggestion}")
        parts.append("请根据以上反馈修正内容。")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 配置与权重
    # ------------------------------------------------------------------

    def _get_enabled_evaluators(self, cfg: ReflectionConfig) -> list[str]:
        """根据配置返回启用的评估器名列表(保持权重表顺序)。

        - 内置 6 个评估器:按对应 enable_xxx 配置字段过滤
        - 自定义评估器(无对应配置字段):始终启用(无开关可关)
        """
        enabled: list[str] = []
        for name in self._weights.keys():
            # 仅评估实际存在的评估器(忽略权重表中残留但无实例的 key)
            if name not in self._evaluators:
                continue
            field_name = self._ENABLE_FIELD_MAP.get(name)
            if field_name is None:
                # 自定义评估器无对应配置开关,始终启用
                enabled.append(name)
                continue
            if getattr(cfg, field_name, False):
                enabled.append(name)
        return enabled

    def _weighted_score(
        self,
        sub_scores: dict[str, float],
        enabled_names: list[str],
    ) -> float:
        """加权计算总分(仅计算启用的评估器,权重归一化)。

        归一化: enabled_names 的权重之和可能 < 1.0(如关闭 llm 后总和=0.9),
        需除以实际权重和,确保总分在 [0, 1]。
        """
        total_weight = 0.0
        weighted_sum = 0.0
        for name in enabled_names:
            weight = self._weights.get(name, 0.0)
            score = sub_scores.get(name, 1.0)
            weighted_sum += weight * score
            total_weight += weight
        if total_weight <= 0.0:
            return 1.0
        score = weighted_sum / total_weight
        # clamp
        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return score

    def update_config(self, **kwargs: Any) -> None:
        """线程安全更新配置(copy + modify + replace)。

        用法:
            manager.update_config(min_score_threshold=0.8, enable_llm_eval=True)

        实现细节:
          - 用 threading.Lock 保证并发安全
          - 用 dataclasses.replace 创建新实例(避免半修改状态)
          - 过滤掉非 ReflectionConfig 字段的 kwarg(避免 TypeError)

        Args:
            **kwargs: ReflectionConfig 字段名 = 新值
        """
        with self._lock:
            current = self._config
            # 过滤掉非配置字段的 kwarg(避免 TypeError)
            valid_fields = {f.name for f in dataclasses.fields(current)}
            filtered = {k: v for k, v in kwargs.items() if k in valid_fields}
            if not filtered:
                return
            self._config = dataclasses.replace(current, **filtered)
            logger.debug("反思配置已更新: %s", filtered)

    @property
    def config(self) -> ReflectionConfig:
        """当前配置(只读视图,修改请用 update_config)。"""
        return self._config

    @property
    def weights(self) -> dict[str, float]:
        """权重表(只读副本)。"""
        return dict(self._weights)

    # ------------------------------------------------------------------
    # 统计(P2-02: 监控指标暴露)
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """返回反思管理器运行时统计(线程安全快照)。

        供 fnixagent.core.observability.stats 聚合器采集,
        不修改任何内部状态。

        Returns:
            包含启用状态、阈值、评估器数量与权重表的字典。
        """
        with self._lock:
            return {
                "enabled": self._config.enabled,
                "min_score_threshold": self._config.min_score_threshold,
                "max_reflections": self._config.max_reflections,
                "evaluator_count": len(self._evaluators),
                "evaluators": list(self._evaluators.keys()),
                "weights": dict(self._weights),
            }


# ---------------------------------------------------------------------------
# 单例(双重检查锁定)
# ---------------------------------------------------------------------------

_singleton_lock = threading.Lock()
_singleton_manager: ReflectionManager | None = None


def get_reflection_manager(
    config: ReflectionConfig | None = None,
    llm: Any = None,
) -> ReflectionManager:
    """获取全局 ReflectionManager 单例。

    首次调用时创建实例(双重检查锁定),后续调用返回同一实例。
    首次调用传入的 config/llm 才生效;后续调用传入的参数被忽略
    (避免单例被意外替换导致并发问题)。

    Args:
        config: 反思配置(仅首次调用生效)
        llm: LLM 客户端(仅首次调用生效)

    Returns:
        全局 ReflectionManager 实例
    """
    global _singleton_manager
    if _singleton_manager is not None:
        return _singleton_manager
    with _singleton_lock:
        # 双重检查:拿到锁后再检查一次,防止并发时重复创建
        if _singleton_manager is not None:
            return _singleton_manager
        _singleton_manager = ReflectionManager(config=config, llm=llm)
        return _singleton_manager


def reset_reflection_manager() -> None:
    """重置全局单例(主要供测试使用)。

    重置后,下次 get_reflection_manager() 会重新创建实例。
    """
    global _singleton_manager
    with _singleton_lock:
        _singleton_manager = None
