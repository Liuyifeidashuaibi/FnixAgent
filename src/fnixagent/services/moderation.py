"""
独立审核服务 (Moderation Service) - Phase 3.2。

将内容审核从主请求路径解耦,提供:
  1. 统一入口(moderate_input / moderate_output)
  2. 单例模式(全局复用,避免重复初始化敏感词库)
  3. 配置开关(运行时启停)
  4. 性能保障(目标 <100ms)
  5. 异步批量审核(预留给后台任务)
  6. 自动接入审计日志

设计要点:
  - 服务层不直接依赖 FastAPI,可在任意 Python 进程中使用
  - 复用 ContentModerator,但封装业务策略(配置、开关、统计)
  - 线程安全,适合多线程并发
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from fnixagent.core.security.moderation import (
    ContentModerator,
    ModerationResult,
)

# ---------------------------------------------------------------------------
# 服务配置
# ---------------------------------------------------------------------------


@dataclass
class ModerationConfig:
    """审核服务配置。"""

    enabled: bool = True  # 总开关
    input_enabled: bool = True  # 输入审核开关
    output_enabled: bool = True  # 输出审核开关
    auto_sanitize: bool = True  # 自动脱敏开关
    block_high_risk_only: bool = False  # 仅拦截高风险(risk_score >= 40)
    high_risk_threshold: int = 40  # 高风险阈值


# ---------------------------------------------------------------------------
# 服务统计
# ---------------------------------------------------------------------------


@dataclass
class ModerationStats:
    """审核服务统计(线程安全计数)。"""

    total_input: int = 0
    total_output: int = 0
    blocked_input: int = 0
    blocked_output: int = 0
    sanitized: int = 0
    total_duration_ms: int = 0
    category_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_input": self.total_input,
            "total_output": self.total_output,
            "blocked_input": self.blocked_input,
            "blocked_output": self.blocked_output,
            "sanitized": self.sanitized,
            "avg_duration_ms": (
                round(self.total_duration_ms / max(1, self.total_input + self.total_output), 2)
            ),
            "category_counts": dict(self.category_counts),
        }


# ---------------------------------------------------------------------------
# 服务实现
# ---------------------------------------------------------------------------


class ModerationService:
    """独立审核服务(单例)。

    用法:
        from fnixagent.services.moderation import get_moderation_service
        svc = get_moderation_service()

        # 输入审核
        result = svc.moderate_input(user_text, user_id=42, ip_address="1.2.3.4")
        if not result.passed:
            raise ValueError(f"输入被拦截: {result.issues}")

        # 输出审核
        result = svc.moderate_output(llm_output, user_id=42)
        return result.sanitized_text
    """

    def __init__(
        self,
        config: ModerationConfig | None = None,
        moderator: ContentModerator | None = None,
    ):
        self._config = config or ModerationConfig()
        self._moderator = moderator or ContentModerator()
        self._stats = ModerationStats()
        self._lock = threading.Lock()

    # -- 配置管理 ----------------------------------------------------------

    @property
    def config(self) -> ModerationConfig:
        return self._config

    def update_config(self, **kwargs) -> None:
        """更新配置(运行时热更新)。"""
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self._config, k):
                    setattr(self._config, k, v)

    # -- 审核入口 ----------------------------------------------------------

    def moderate_input(
        self,
        text: str,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> ModerationResult:
        """用户输入审核。

        Returns:
            ModerationResult.passed=False 表示应拦截该输入。
            即便拦截,sanitized_text 仍返回脱敏后的文本(供日志展示)。
        """
        if not self._config.enabled or not self._config.input_enabled:
            return ModerationResult(passed=True, sanitized_text=text)

        result = self._moderator.review_input(
            text=text,
            user_id=user_id,
            ip_address=ip_address,
            auto_sanitize=self._config.auto_sanitize,
        )

        # 仅拦截高风险模式(可选)
        if self._config.block_high_risk_only and not result.passed:
            if result.risk_score < self._config.high_risk_threshold:
                result.passed = True

        self._record_stats(result, is_input=True)
        return result

    def moderate_output(
        self,
        text: str,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> ModerationResult:
        """LLM 输出审核。

        Returns:
            ModerationResult.passed=False 表示输出不应展示给用户。
            sanitized_text 始终返回脱敏后的文本(若有 PII)。
        """
        if not self._config.enabled or not self._config.output_enabled:
            return ModerationResult(passed=True, sanitized_text=text)

        result = self._moderator.review(
            text=text,
            auto_sanitize=self._config.auto_sanitize,
            user_id=user_id,
            ip_address=ip_address,
        )

        # 仅拦截高风险模式(可选)
        if self._config.block_high_risk_only and not result.passed:
            if result.risk_score < self._config.high_risk_threshold:
                result.passed = True

        self._record_stats(result, is_input=False)
        return result

    # -- 统计 --------------------------------------------------------------

    def get_stats(self) -> dict:
        """获取审核服务统计。"""
        with self._lock:
            return self._stats.to_dict()

    def reset_stats(self) -> None:
        """重置统计(测试用)。"""
        with self._lock:
            self._stats = ModerationStats()

    # -- 内部 --------------------------------------------------------------

    def _record_stats(self, result: ModerationResult, is_input: bool) -> None:
        with self._lock:
            if is_input:
                self._stats.total_input += 1
                if not result.passed:
                    self._stats.blocked_input += 1
            else:
                self._stats.total_output += 1
                if not result.passed:
                    self._stats.blocked_output += 1

            if result.sanitized_text != result.sanitized_text or result.pii_hits:
                # 脱敏计数(有 PII 命中即认为发生了脱敏)
                if result.pii_hits:
                    self._stats.sanitized += 1

            self._stats.total_duration_ms += result.duration_ms

            for cat in result.categories:
                self._stats.category_counts[cat] = self._stats.category_counts.get(cat, 0) + 1

    # -- 工具方法 ----------------------------------------------------------

    def load_sensitive_words(self, words: list[str]) -> int:
        """加载敏感词库到检测器。返回加载数量。"""
        return self._moderator._sensitive.add_words(words)

    def load_default_sensitive_words(self) -> int:
        """加载默认敏感词表。"""
        return self._moderator._sensitive.load_default_words()

    @property
    def moderator(self) -> ContentModerator:
        """底层审核器(供高级用法使用)。"""
        return self._moderator


# ---------------------------------------------------------------------------
# 单例工厂
# ---------------------------------------------------------------------------


_moderation_service: ModerationService | None = None
_service_lock = threading.Lock()


def get_moderation_service() -> ModerationService:
    """获取审核服务全局单例(双重检查锁定,懒加载)。"""
    global _moderation_service
    if _moderation_service is None:
        with _service_lock:
            if _moderation_service is None:
                _moderation_service = ModerationService()
    return _moderation_service


def reset_moderation_service() -> None:
    """重置审核服务单例(测试用)。"""
    global _moderation_service
    with _service_lock:
        _moderation_service = None
