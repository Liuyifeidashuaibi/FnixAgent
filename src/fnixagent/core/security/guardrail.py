"""统一 Guardrail 管道(借鉴 OpenAI Agents SDK input/output_guardrails)。

[注] 完整三层护栏体系(输入/执行/输出,含工具调用执行层)请使用
``core.guardrail.get_guardrail_registry()``(见 fnixagent.core.guardrail)。
本模块的 GuardrailPipeline 保留用于 LLM 调用粒度的输入/输出护栏管道,
二者可并存:GuardrailPipeline 聚焦单次 LLM 调用前后的文本护栏,
而 core.guardrail 面向 Agent 全链路的三层可插拔护栏(含执行层)。

将分散的 security/injection.py / moderation.py / desensitize.py / sensitive.py
收敛为统一的 Guardrail 管道,在每次 LLM 调用前后执行:
  - 输入方向(Input Guardrail):注入检测 + 敏感词 + 内容审核
  - 输出方向(Output Guardrail):内容审核 + PII 脱敏

核心设计:
  - BaseGuardrail:抽象基类,子类实现 _check
  - InputGuardrail / OutputGuardrail:方向标记基类
  - GuardrailPipeline:串行执行 + 短路(tripwire 触发即停止)
  - GuardrailResult:统一结果格式(passed/tripwire/sanitized_text/risk_score)

tripwire 语义(借鉴 OpenAI SDK):
  - tripwire_triggered=True 表示严重违规,立即短路 + 审计
  - passed=False 但 tripwire=False 表示软拦截(如脱敏后继续)

与现有 SecurityEngine 关系:
  - SecurityEngine 新增 guardrail_pipeline 属性,委托 GuardrailPipeline
  - 现有 check_input/review_output 保留兼容,内部改为调用 pipeline
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 结果与异常
# ---------------------------------------------------------------------------

@dataclass
class GuardrailResult:
    """单个 Guardrail 检查结果。

    Attributes:
        guardrail_name: Guardrail 名称(用于审计/日志)
        passed: 是否通过(False 表示拦截)
        tripwire_triggered: 是否触发 tripwire(严重违规,立即短路)
        blocked_reason: 拦截原因(passed=False 时填写)
        sanitized_text: 脱敏后的文本(输出方向可能修改文本)
        risk_score: 风险评分 0~1(0=安全,1=高危)
        details: 额外详情(命中词/违规类型等)
    """

    guardrail_name: str
    passed: bool = True
    tripwire_triggered: bool = False
    blocked_reason: str = ""
    sanitized_text: str = ""
    risk_score: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

@dataclass
class GuardrailPipelineResult:
    """管道整体结果(聚合多个 GuardrailResult)。

    Attributes:
        passed: 全部通过才为 True
        tripwire_triggered: 任一触发即为 True
        blocked_reason: 第一个拦截原因
        sanitized_text: 最后一个脱敏后的文本(链式脱敏)
        results: 各 Guardrail 的详细结果
        risk_score: 最大风险评分
    """

    passed: bool = True
    tripwire_triggered: bool = False
    blocked_reason: str = ""
    sanitized_text: str = ""
    results: list[GuardrailResult] = field(default_factory=list)
    risk_score: float = 0.0

class GuardrailTripwireError(Exception):
    """Guardrail tripwire 触发异常(严重违规,需短路 + 审计)。

    携带 GuardrailResult 信息,供调用方决策是返回拦截消息还是抛异常。
    """

    def __init__(self, result: GuardrailResult) -> None:
        self.result = result
        super().__init__(f"Guardrail '{result.guardrail_name}' tripwire: {result.blocked_reason}")

# ---------------------------------------------------------------------------
# BaseGuardrail 抽象基类
# ---------------------------------------------------------------------------

class BaseGuardrail(abc.ABC):
    """Guardrail 抽象基类。

    子类实现 _check(text, **context) 返回 GuardrailResult。
    公开 check() 方法统一处理 enabled 开关与异常捕获。

    设计:
      - enabled=False 时直接返回 passed=True
      - _check 抛异常时返回 tripwire=False, passed=False(降级而非崩溃)
    """

    def __init__(self, name: str, *, enabled: bool = True) -> None:
        self._name = name
        self._enabled = enabled

    @property
    def name(self) -> str:
        return self._name

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def check(self, text: str, **context: Any) -> GuardrailResult:
        """公开检查入口(含 enabled 开关与异常捕获)。"""
        if not self._enabled:
            return GuardrailResult(guardrail_name=self._name, passed=True)
        try:
            return self._check(text, **context)
        except Exception as e:
            # Guardrail 自身异常不应阻塞主流程,降级为软拦截
            return GuardrailResult(
                guardrail_name=self._name,
                passed=False,
                blocked_reason=f"Guardrail 内部错误: {e}",
                details={"exception": type(e).__name__},
            )

    @abc.abstractmethod
    def _check(self, text: str, **context: Any) -> GuardrailResult:
        """子类实现具体检查逻辑。"""
        ...

class InputGuardrail(BaseGuardrail):
    """输入方向 Guardrail 基类(LLM 调用前)。

    典型子类:注入检测 / 敏感词检测 / 输入内容审核
    """

    pass

class OutputGuardrail(BaseGuardrail):
    """输出方向 Guardrail 基类(LLM 调用后)。

    典型子类:输出内容审核 / PII 脱敏
    """

    pass

# ---------------------------------------------------------------------------
# 5 个适配类(包装现有 security 模块)
# ---------------------------------------------------------------------------

class InputInjectionGuardrail(InputGuardrail):
    """输入注入检测 Guardrail(包装 InjectionGuard)。"""

    def __init__(self, injection_guard: Any, *, enabled: bool = True) -> None:
        super().__init__("input_injection", enabled=enabled)
        self._guard = injection_guard

    def _check(self, text: str, **context: Any) -> GuardrailResult:
        result = self._guard.check(text)
        return GuardrailResult(
            guardrail_name=self._name,
            passed=result.passed,
            tripwire_triggered=not result.passed and result.risk_score >= 0.7,
            blocked_reason=(
                f"Prompt 注入风险(risk={result.risk_score}): {'; '.join(result.reasons)}"
                if not result.passed
                else ""
            ),
            risk_score=result.risk_score,
            details={"reasons": result.reasons},
        )

class InputSensitiveGuardrail(InputGuardrail):
    """输入敏感词检测 Guardrail(包装 SensitiveDetector)。"""

    def __init__(self, sensitive_detector: Any, *, enabled: bool = True) -> None:
        super().__init__("input_sensitive", enabled=enabled)
        self._detector = sensitive_detector

    def _check(self, text: str, **context: Any) -> GuardrailResult:
        hits = self._detector.detect(text)
        if not hits:
            return GuardrailResult(guardrail_name=self._name, passed=True)
        words = [w for w, _, _ in hits]
        return GuardrailResult(
            guardrail_name=self._name,
            passed=False,
            tripwire_triggered=False,  # 敏感词软拦截,不短路
            blocked_reason=f"敏感词命中: {words}",
            risk_score=0.5,
            details={"hits": words},
        )

class InputModerationGuardrail(InputGuardrail):
    """输入内容审核 Guardrail(包装 ContentModerator,输入方向)。"""

    def __init__(self, moderator: Any, *, enabled: bool = True) -> None:
        super().__init__("input_moderation", enabled=enabled)
        self._moderator = moderator

    def _check(self, text: str, **context: Any) -> GuardrailResult:
        result = self._moderator.review(text, auto_sanitize=False)
        return GuardrailResult(
            guardrail_name=self._name,
            passed=result.passed,
            tripwire_triggered=not result.passed and len(result.issues) >= 3,
            blocked_reason="; ".join(result.issues) if not result.passed else "",
            risk_score=0.8 if not result.passed else 0.0,
            details={"issues": result.issues},
        )

class OutputModerationGuardrail(OutputGuardrail):
    """输出内容审核 Guardrail(包装 ContentModerator,输出方向)。"""

    def __init__(self, moderator: Any, *, enabled: bool = True) -> None:
        super().__init__("output_moderation", enabled=enabled)
        self._moderator = moderator

    def _check(self, text: str, **context: Any) -> GuardrailResult:
        result = self._moderator.review(text, auto_sanitize=False)
        return GuardrailResult(
            guardrail_name=self._name,
            passed=result.passed,
            tripwire_triggered=not result.passed and len(result.issues) >= 3,
            blocked_reason="; ".join(result.issues) if not result.passed else "",
            sanitized_text=text,  # 审核不修改文本
            risk_score=0.8 if not result.passed else 0.0,
            details={"issues": result.issues, "pii_hits": result.pii_hits},
        )

class OutputDesensitizeGuardrail(OutputGuardrail):
    """输出 PII 脱敏 Guardrail(包装 Desensitizer)。"""

    def __init__(self, desensitizer: Any, *, enabled: bool = True) -> None:
        super().__init__("output_desensitize", enabled=enabled)
        self._desensitizer = desensitizer

    def _check(self, text: str, **context: Any) -> GuardrailResult:
        sanitized = self._desensitizer.mask_all(text)
        modified = sanitized != text
        return GuardrailResult(
            guardrail_name=self._name,
            passed=True,  # 脱敏不拦截,只修改文本
            tripwire_triggered=False,
            sanitized_text=sanitized,
            risk_score=0.0,
            details={"modified": modified},
        )

# ---------------------------------------------------------------------------
# GuardrailPipeline 管道
# ---------------------------------------------------------------------------

class GuardrailPipeline:
    """Guardrail 管道:串行执行 + 短路。

    输入方向(input_guardrails)和输出方向(output_guardrails)独立配置。
    任一 Guardrail 触发 tripwire 立即短路,不再执行后续 Guardrail。

    用法:
        pipeline = GuardrailPipeline()
        pipeline.add_input(InputInjectionGuardrail(injection_guard))
        pipeline.add_input(InputSensitiveGuardrail(sensitive_detector))
        pipeline.add_output(OutputModerationGuardrail(moderator))
        pipeline.add_output(OutputDesensitizeGuardrail(desensitizer))

        # LLM 调用前
        in_result = pipeline.run_input(user_text, user_id=...)
        if not in_result.passed:
            return in_result.blocked_reason

        # LLM 调用
        llm_output = llm.chat(...)

        # LLM 调用后
        out_result = pipeline.run_output(llm_output)
        return out_result.sanitized_text
    """

    def __init__(
        self,
        input_guardrails: list[InputGuardrail] | None = None,
        output_guardrails: list[OutputGuardrail] | None = None,
    ) -> None:
        self._input_guardrails: list[InputGuardrail] = list(input_guardrails or [])
        self._output_guardrails: list[OutputGuardrail] = list(output_guardrails or [])

    def add_input(self, guardrail: InputGuardrail) -> GuardrailPipeline:
        """追加输入 Guardrail(返回 self,链式调用)。"""
        self._input_guardrails.append(guardrail)
        return self

    def add_output(self, guardrail: OutputGuardrail) -> GuardrailPipeline:
        """追加输出 Guardrail(返回 self,链式调用)。"""
        self._output_guardrails.append(guardrail)
        return self

    @property
    def input_guardrails(self) -> list[InputGuardrail]:
        return list(self._input_guardrails)

    @property
    def output_guardrails(self) -> list[OutputGuardrail]:
        return list(self._output_guardrails)

    def run_input(self, text: str, **context: Any) -> GuardrailPipelineResult:
        """执行输入管道:串行执行 input_guardrails,tripwire 触发即短路。

        Args:
            text: 用户输入文本
            **context: 上下文(user_id/ip_address 等,传给各 Guardrail)

        Returns:
            GuardrailPipelineResult:聚合结果
        """
        return self._run(self._input_guardrails, text, **context)

    def run_output(self, text: str, **context: Any) -> GuardrailPipelineResult:
        """执行输出管道:串行执行 output_guardrails,tripwire 触发即短路。

        输出管道特殊:脱敏 Guardrail 会修改 text,后续 Guardrail 收到脱敏后的文本。

        Args:
            text: LLM 输出文本
            **context: 上下文

        Returns:
            GuardrailPipelineResult:聚合结果(含 sanitized_text)
        """
        return self._run(self._output_guardrails, text, **context)

    def _run(
        self,
        guardrails: list[BaseGuardrail],
        text: str,
        **context: Any,
    ) -> GuardrailPipelineResult:
        """管道执行核心逻辑。

        短路规则:
          - tripwire_triggered=True → 立即停止,强制 passed=False,返回聚合结果
          - passed=False 但 tripwire=False → 继续执行(软拦截累积)
          - passed=True → 继续执行

        文本传递:
          - 输出方向:前一个 Guardrail 的 sanitized_text 传给下一个
          - 输入方向:原样传递(输入一般不修改文本)

        Args:
            guardrails: 待执行的 Guardrail 列表
            text: 输入文本
            **context: 透传给各 Guardrail 的上下文(user_id/ip_address 等)

        Returns:
            GuardrailPipelineResult:聚合结果
        """
        result = GuardrailPipelineResult(sanitized_text=text)
        current_text = text

        for guardrail in guardrails:
            gr = guardrail.check(current_text, **context)
            result.results.append(gr)
            result.risk_score = max(result.risk_score, gr.risk_score)

            # 输出方向:更新 current_text 为脱敏后的文本
            if gr.sanitized_text:
                current_text = gr.sanitized_text
                result.sanitized_text = current_text

            if not gr.passed:
                result.passed = False
                if not result.blocked_reason:
                    result.blocked_reason = gr.blocked_reason

            if gr.tripwire_triggered:
                # tripwire 短路:强制 passed=False,立即停止后续 Guardrail
                result.tripwire_triggered = True
                result.passed = False
                break

        return result

# ---------------------------------------------------------------------------
# 便捷工厂:从现有 SecurityEngine 组件构建管道
# ---------------------------------------------------------------------------

def build_pipeline_from_engine(engine: Any) -> GuardrailPipeline:
    """从现有 SecurityEngine 组件构建 GuardrailPipeline。

    将 engine 的 _injection / _sensitive / _moderator / _desensitizer
    包装为对应的 Guardrail 适配类。

    Args:
        engine: SecurityEngine 实例(含 _injection/_sensitive/_moderator/_desensitizer)

    Returns:
        配置好的 GuardrailPipeline
    """
    pipeline = GuardrailPipeline()
    pipeline.add_input(InputInjectionGuardrail(engine.injection_guard))
    pipeline.add_input(InputSensitiveGuardrail(engine.sensitive_detector))
    pipeline.add_output(OutputModerationGuardrail(engine.content_moderator))
    pipeline.add_output(OutputDesensitizeGuardrail(engine._desensitizer))
    return pipeline
