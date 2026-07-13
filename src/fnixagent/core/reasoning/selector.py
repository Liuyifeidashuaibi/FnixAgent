"""推理模式选择器(P2-6 改造为策略模式)。

提供两套接口:
  - 旧版(向后兼容):select(goal, tools) → ReasoningMode
  - 新版(P2-6):select_strategy(...) → BaseStrategy

新版策略选择决策:
  1. 用户显式偏好(user_preference)优先 → 直接返回对应策略
  2. 任务敏感度(sensitivity=high)→ ComplianceStrategy
  3. 任务复杂度高(多工具/多步骤)→ PreciseStrategy
  4. 任务简单(少工具/无复杂关键词)→ FastStrategy
  5. 批处理场景(extra['batch_mode']=True)→ CheapStrategy
  6. 默认 → FastStrategy

策略注册表:
  - register_strategy:动态注册新策略
  - get_strategy:按名获取
  - list_strategies:列出全部已注册策略

性能优化:
  - 策略选择通过 _strategies dict O(1) 查表(避免线性扫描)
  - _score_complexity 缓存 re.split 结果(同一 goal 多次调用复用)
  - 复杂度评分正则预编译为模块级常量

fallback 链(BUG 修复):
  原实现在用户偏好/Compliance/Precise/Cheap/Fast 全部未注册时,
  返回临时 FastStrategy() 实例,但该实例未进入注册表,
  导致后续 get_strategy('fast') 仍返回 None。现统一保证至少返回
  已注册策略,极端情况(注册表为空)显式抛 ValueError。
"""
from __future__ import annotations

import re
from typing import Optional

from fnixagent.core.config import ReasoningConfig
from fnixagent.core.reasoning.strategies import (
    BaseStrategy,
    CheapStrategy,
    ComplianceStrategy,
    FastStrategy,
    PreciseStrategy,
    StrategyContext,
    StrategyType,
)
from fnixagent.core.types import ReasoningMode


# 模块级预编译正则(避免每次 _score_complexity 都重新编译)
_SENTENCE_SPLIT_RE = re.compile(r"[.!?。！？；\n]")


class ReasoningSelector:
    """推理策略选择器(P2-6 策略模式)。

    用法(新版):
        selector = ReasoningSelector()
        ctx = StrategyContext(goal="...", available_tools=8, sensitivity="high")
        strategy = selector.select_strategy(ctx)
        trace = strategy.execute(ctx)

    用法(旧版,向后兼容):
        mode = selector.select("帮我搜3篇AI论文并生成PDF", available_tools=8)
        # -> ReasoningMode.PLAN_EXECUTE
    """

    # 复杂度关键词(出现说明任务可能需要多步骤)
    _COMPLEX_KEYWORDS: tuple[str, ...] = (
        "然后", "接着", "之后", "最后", "并", "同时",
        "多个", "批量", "全部", "完整", "端到端",
        "步骤", "流程", "工作流", "依次",
    )

    # 质量要求关键词(出现说明需要自我纠错)
    _QUALITY_KEYWORDS: tuple[str, ...] = (
        "精确", "准确", "校验", "验证", "重要", "正式",
        "检查", "确认", "确保", "无误", "严格",
    )

    def __init__(self, config: Optional[ReasoningConfig] = None):
        self._config = config or ReasoningConfig()
        # 策略注册表(P2-6):O(1) 查表
        self._strategies: dict[str, BaseStrategy] = {}
        # 复杂度评分缓存(同一 goal 多次评分复用,性能优化)
        self._complexity_cache: dict[str, float] = {}
        # 注册默认 4 个策略
        self._register_default_strategies()

    # ------------------------------------------------------------------
    # P2-6:策略注册表
    # ------------------------------------------------------------------

    def _register_default_strategies(self) -> None:
        """注册内置 4 个策略。"""
        self.register_strategy(FastStrategy())
        self.register_strategy(CheapStrategy())
        self.register_strategy(PreciseStrategy())
        self.register_strategy(ComplianceStrategy())

    def register_strategy(self, strategy: BaseStrategy) -> "ReasoningSelector":
        """注册新策略(同名覆盖)。

        Args:
            strategy: 策略实例,需实现 BaseStrategy 接口

        Returns:
            self(链式调用)
        """
        if not isinstance(strategy, BaseStrategy):
            raise TypeError(
                f"strategy 必须为 BaseStrategy 实例,实际: "
                f"{type(strategy).__name__}"
            )
        self._strategies[strategy.name] = strategy
        return self

    def unregister_strategy(self, name: str) -> Optional[BaseStrategy]:
        """注销策略。

        Args:
            name: 策略名(如 "fast" / "precise")

        Returns:
            被移除的策略实例;若不存在返回 None
        """
        return self._strategies.pop(name, None)

    def get_strategy(self, name: str) -> Optional[BaseStrategy]:
        """按名获取策略(O(1) 查表)。"""
        return self._strategies.get(name)

    def list_strategies(self) -> list[BaseStrategy]:
        """列出全部已注册策略。"""
        return list(self._strategies.values())

    # ------------------------------------------------------------------
    # P2-6:策略选择
    # ------------------------------------------------------------------

    def select_strategy(self, ctx: StrategyContext) -> BaseStrategy:
        """选择最合适的策略。

        决策优先级(fallback 链,任一环节命中即返回):
          1. 用户显式偏好 → 对应策略(若已注册且 is_applicable)
          2. Compliance(sensitivity=high 或敏感关键词)
          3. Precise(复杂任务)
          4. Cheap(批处理)
          5. Fast(默认)
          6. 兜底:取第一个已注册策略
          7. 极端:注册表为空 → 抛 ValueError(BUG 修复:原返回临时实例
             未入注册表,导致后续 get_strategy 失败)

        Args:
            ctx: StrategyContext(至少填 goal / available_tools / sensitivity)

        Returns:
            BaseStrategy 实例
        """
        # 1. 用户显式偏好(O(1) 查表)
        if ctx.user_preference:
            preferred = self._strategies.get(ctx.user_preference)
            if preferred is not None and preferred.is_applicable(ctx):
                return preferred

        # 2. Compliance(敏感任务)— O(1) 查表
        compliance = self._strategies.get(StrategyType.COMPLIANCE.value)
        if compliance is not None and compliance.is_applicable(ctx):
            return compliance

        # 3. Precise(复杂任务)— O(1) 查表
        precise = self._strategies.get(StrategyType.PRECISE.value)
        if precise is not None and precise.is_applicable(ctx):
            return precise

        # 4. Cheap(批处理)— O(1) 查表
        if ctx.extra.get("batch_mode"):
            cheap = self._strategies.get(StrategyType.CHEAP.value)
            if cheap is not None and cheap.is_applicable(ctx):
                return cheap

        # 5. Fast(默认)— O(1) 查表
        fast = self._strategies.get(StrategyType.FAST.value)
        if fast is not None:
            return fast

        # 6. 兜底:取第一个已注册策略(避免返回未入注册表的临时实例)
        if self._strategies:
            return next(iter(self._strategies.values()))

        # 7. 极端情况:无策略注册
        # BUG 修复:原返回 FastStrategy() 临时实例,但该实例未入注册表,
        # 导致后续 get_strategy('fast') 返回 None。现显式抛异常让上层感知。
        raise ValueError(
            "ReasoningSelector 无已注册策略,请先 register_strategy()"
        )

    def select_by_complexity(
        self,
        goal: str,
        available_tools: int = 0,
    ) -> BaseStrategy:
        """根据复杂度选择策略(便捷方法,内部构造 StrategyContext)。

        Args:
            goal: 任务目标
            available_tools: 可用工具数

        Returns:
            BaseStrategy 实例
        """
        complexity = self._score_complexity(goal)
        has_quality = self._has_quality_keywords(goal)
        ctx = StrategyContext(
            goal=goal,
            available_tools=available_tools,
            sensitivity="medium" if has_quality else "low",
            user_preference="precise" if has_quality else None,
            extra={"complexity_score": complexity},
        )
        return self.select_strategy(ctx)

    # ------------------------------------------------------------------
    # 旧版接口(向后兼容)
    # ------------------------------------------------------------------

    def select(self, goal: str, available_tools: int = 0) -> ReasoningMode:
        """选择推理模式(旧版接口,向后兼容)。

        决策优先级:
        1. 质量要求 + 反思启用 → Self-Reflect
        2. 工具数超阈值 或 复杂度超阈值 → Plan&Execute
        3. 默认 → ReAct
        """
        complexity = self._score_complexity(goal)
        has_quality = self._has_quality_keywords(goal)

        if has_quality and self._config.reflection_enabled:
            return ReasoningMode.SELF_REFLECT

        if (
            available_tools >= self._config.plan_threshold_tools
            or complexity >= self._config.plan_threshold_complexity
        ):
            return ReasoningMode.PLAN_EXECUTE

        return ReasoningMode.REACT

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _score_complexity(self, goal: str) -> float:
        """任务复杂度评分(0~1)。

        性能优化:
          - 同一 goal 多次评分走缓存(避免重复正则切分)
          - 句子切分用模块级预编译正则
        """
        if not goal:
            return 0.0
        # 缓存命中:直接返回历史评分
        if goal in self._complexity_cache:
            return self._complexity_cache[goal]

        score = 0.0
        # 长度因子(最长 0.3)
        score += min(len(goal) / 200.0, 0.3)
        # 复杂关键词命中(每个 0.15,最多 0.4)
        hits = sum(1 for kw in self._COMPLEX_KEYWORDS if kw in goal)
        score += min(hits * 0.15, 0.4)
        # 句子数因子(每句 0.1,最多 0.3)
        sentences = _SENTENCE_SPLIT_RE.split(goal)
        count = len([s for s in sentences if s.strip()])
        score += min(count * 0.1, 0.3)

        score = min(score, 1.0)
        # 写入缓存(避免无界增长:仅缓存前 1000 个 goal)
        if len(self._complexity_cache) < 1000:
            self._complexity_cache[goal] = score
        return score

    def _has_quality_keywords(self, goal: str) -> bool:
        """判断目标是否包含质量要求相关关键词。"""
        return any(kw in goal for kw in self._QUALITY_KEYWORDS)

    def explain(self, goal: str, available_tools: int = 0) -> dict:
        """返回选择详情(调试用)。"""
        complexity = self._score_complexity(goal)
        mode = self.select(goal, available_tools)
        # 同时给出策略选择详情
        ctx = StrategyContext(
            goal=goal,
            available_tools=available_tools,
            sensitivity="medium" if self._has_quality_keywords(goal) else "low",
        )
        strategy = self.select_strategy(ctx)
        return {
            "goal": goal[:100],
            "complexity_score": round(complexity, 4),
            "complexity_threshold": self._config.plan_threshold_complexity,
            "available_tools": available_tools,
            "tools_threshold": self._config.plan_threshold_tools,
            "has_quality_req": self._has_quality_keywords(goal),
            "selected_mode": mode.value,
            "selected_strategy": strategy.name,
            "think_mode": strategy.think_mode,
        }
