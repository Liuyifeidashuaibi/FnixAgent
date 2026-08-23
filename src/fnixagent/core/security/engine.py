"""
安全引擎总控 (Security Engine)。

统一安全入口,串联输入安全检查与输出内容审核:
  - check_input:  敏感词 + 注入检测 → 返回 SecurityCheckResult
  - review_output: 内容审核 + 脱敏 → 返回 SecurityCheckResult

设计: 组合而非继承,各子组件可独立替换。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.config import SecurityConfig
from fnixagent.core.security.desensitize import Desensitizer
from fnixagent.core.security.guardrail import (
    GuardrailPipeline,
    GuardrailPipelineResult,
    build_pipeline_from_engine,
)
from fnixagent.core.security.injection import InjectionGuard
from fnixagent.core.security.moderation import ContentModerator
from fnixagent.core.security.sensitive import SensitiveDetector

# ---------------------------------------------------------------------------
# Phase 2.5: 安全事件审计日志
# ---------------------------------------------------------------------------


def _audit_security(
    action: str,
    user_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """安全事件写入审计日志(失败不影响主流程)。

    Args:
        action: 审计动作常量(如 "injection.blocked")
        user_id: 用户 ID(可选)
        detail: 详情字典(可选)
        ip_address: 客户端 IP(可选)
    """
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(
            action=action,
            user_id=user_id,
            detail=detail or {},
            ip_address=ip_address,
        )
    except Exception:
        pass


@dataclass
class SecurityCheckResult:
    """安全检查统一结果。

    Attributes:
        passed: 是否通过
        blocked_reason: 拦截原因(passed=False 时填写)
        sanitized_text: 脱敏后的文本
        details: 详细信息字典
    """

    passed: bool
    blocked_reason: str = ""
    sanitized_text: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class SecurityEngine:
    """
    安全引擎总控。

    用法:
        engine = SecurityEngine(config=security_config)
        # 输入检查
        in_result = engine.check_input(user_text)
        if not in_result.passed:
            return "请求被拦截"
        # 输出审核
        out_result = engine.review_output(llm_output)
        return out_result.sanitized_text
    """

    def __init__(
        self,
        config: SecurityConfig | None = None,
        sensitive: SensitiveDetector | None = None,
        injection: InjectionGuard | None = None,
        moderator: ContentModerator | None = None,
        desensitizer: Desensitizer | None = None,
    ) -> None:
        """初始化安全引擎。

        Args:
            config: 安全配置(None 用默认 SecurityConfig)
            sensitive: 敏感词检测器(None 用默认 SensitiveDetector)
            injection: 注入防护器(None 用默认 InjectionGuard)
            moderator: 内容审核器(None 用默认 ContentModerator)
            desensitizer: 脱敏器(None 用默认 Desensitizer)
        """
        self._config = config or SecurityConfig()
        self._sensitive = sensitive or SensitiveDetector()
        self._injection = injection or InjectionGuard()
        self._desensitizer = desensitizer or Desensitizer()
        self._moderator = moderator or ContentModerator(
            sensitive_detector=self._sensitive,
            desensitizer=self._desensitizer,
        )
        # P0-2: 统一 Guardrail 管道(包装现有组件)
        self._guardrail_pipeline: GuardrailPipeline = build_pipeline_from_engine(self)

    # -- 输入安全检查 ------------------------------------------------------

    def check_input(
        self,
        text: str,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> SecurityCheckResult:
        """
        对用户输入做安全检查:
        1. Prompt 注入检测
        2. 敏感词检测
        任一不通过则拦截。

        Phase 2.5:拦截时自动写入审计日志(user_id/ip_address 可选)。
        """
        details: dict = {}
        blocked_reason = ""

        # 1. 注入检测
        if self._config.injection_enabled:
            inj_result = self._injection.check(text)
            details["injection"] = {
                "passed": inj_result.passed,
                "risk_score": inj_result.risk_score,
                "reasons": inj_result.reasons,
            }
            if not inj_result.passed:
                blocked_reason = (
                    f"Prompt 注入风险(risk={inj_result.risk_score}): "
                    f"{'; '.join(inj_result.reasons)}"
                )
                _audit_security(
                    "injection.blocked",
                    user_id=user_id,
                    detail={
                        "risk_score": inj_result.risk_score,
                        "reasons": inj_result.reasons,
                        "text_preview": text[:200],
                    },
                    ip_address=ip_address,
                )
                # Phase 2.10: 记录注入拦截指标
                try:
                    from fnixagent.core.observability.metrics import record_injection_blocked

                    record_injection_blocked(injection_type="prompt_injection")
                except Exception:
                    pass
                return SecurityCheckResult(
                    passed=False,
                    blocked_reason=blocked_reason,
                    details=details,
                )

        # 2. 敏感词检测
        if self._config.sensitive_enabled and self._sensitive.word_count > 0:
            hits = self._sensitive.detect(text)
            if hits:
                words = [w for w, _, _ in hits]
                details["sensitive"] = {"hits": words}
                blocked_reason = f"敏感词命中: {words}"
                _audit_security(
                    "sensitive.hit",
                    user_id=user_id,
                    detail={
                        "hits": words,
                        "text_preview": text[:200],
                    },
                    ip_address=ip_address,
                )
                # Phase 2.10: 记录敏感词命中指标
                try:
                    from fnixagent.core.observability.metrics import record_sensitive_hit

                    for w in words:
                        record_sensitive_hit(category=w)
                except Exception:
                    pass
                return SecurityCheckResult(
                    passed=False,
                    blocked_reason=blocked_reason,
                    details=details,
                )

        return SecurityCheckResult(passed=True, details=details)

    # -- 输出审核 ----------------------------------------------------------

    def review_output(self, text: str) -> SecurityCheckResult:
        """
        对 LLM 输出做合规审核:
        1. 有害内容检测
        2. PII 泄露检测 + 自动脱敏
        返回脱敏后的文本(sanitized_text)。
        """
        if not self._config.moderation_enabled:
            return SecurityCheckResult(passed=True, sanitized_text=text)

        mod_result = self._moderator.review(text, auto_sanitize=self._config.desensitize_enabled)
        details = {
            "issues": mod_result.issues,
            "sensitive_hits": mod_result.sensitive_hits,
            "pii_hits": mod_result.pii_hits,
        }
        return SecurityCheckResult(
            passed=mod_result.passed,
            blocked_reason="" if mod_result.passed else "; ".join(mod_result.issues),
            sanitized_text=mod_result.sanitized_text,
            details=details,
        )

    # -- 工具方法 ----------------------------------------------------------

    def desensitize(self, text: str) -> str:
        """直接调用脱敏器。"""
        return self._desensitizer.mask_all(text)

    @property
    def sensitive_detector(self) -> SensitiveDetector:
        """敏感词检测器实例。"""
        return self._sensitive

    @property
    def injection_guard(self) -> InjectionGuard:
        """Prompt 注入防护器实例。"""
        return self._injection

    @property
    def content_moderator(self) -> ContentModerator:
        """内容审核器实例。"""
        return self._moderator

    # -- P0-2: Guardrail 管道入口 ------------------------------------------

    @property
    def guardrail_pipeline(self) -> GuardrailPipeline:
        """统一 Guardrail 管道(P0-2)。

        供 SecurityMiddleware / LLMRouter 调用,实现每次 LLM 调用前后
        统一的输入/输出 Guardrail 校验。
        """
        return self._guardrail_pipeline

    def run_input_guardrails(
        self,
        text: str,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> GuardrailPipelineResult:
        """执行输入 Guardrail 管道(注入检测 + 敏感词 + 内容审核)。

        tripwire 触发时自动写审计日志。

        Args:
            text: 用户输入文本
            user_id: 用户 ID(审计用)
            ip_address: 客户端 IP(审计用)

        Returns:
            GuardrailPipelineResult:聚合结果(passed/tripwire/blocked_reason)
        """
        result = self._guardrail_pipeline.run_input(text, user_id=user_id, ip_address=ip_address)
        if result.tripwire_triggered:
            _audit_security(
                "guardrail.input.tripwire",
                user_id=user_id,
                detail={
                    "blocked_reason": result.blocked_reason,
                    "risk_score": result.risk_score,
                    "text_preview": text[:200],
                },
                ip_address=ip_address,
            )
        return result

    def run_output_guardrails(
        self,
        text: str,
        user_id: int | None = None,
    ) -> GuardrailPipelineResult:
        """执行输出 Guardrail 管道(内容审核 + PII 脱敏)。

        返回 result.sanitized_text 为脱敏后的文本,应替换原 LLM 输出。

        Args:
            text: LLM 输出文本
            user_id: 用户 ID(审计用)

        Returns:
            GuardrailPipelineResult:聚合结果(含 sanitized_text)
        """
        result = self._guardrail_pipeline.run_output(text, user_id=user_id)
        if result.tripwire_triggered:
            _audit_security(
                "guardrail.output.tripwire",
                user_id=user_id,
                detail={
                    "blocked_reason": result.blocked_reason,
                    "risk_score": result.risk_score,
                    "text_preview": text[:200],
                },
            )
        return result
