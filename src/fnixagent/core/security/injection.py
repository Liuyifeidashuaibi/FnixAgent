"""
Prompt 注入防护 (Injection Guard)。

通过多策略正则匹配检测 Prompt 注入攻击:
  1. 角色劫持: "ignore previous", "disregard above", "you are now"
  2. 指令覆盖: 伪造 "system:", "### instruction" 等分隔符
  3. 分隔符注入: 伪造 "---END---", "</system>" 等标记
  4. 编码攻击: Base64 隐藏指令, unicode 混淆
  5. 命令注入: shell 命令(rm, curl, eval 等)

每策略返回 (risk_score, reason),综合评分超阈值则拦截。

性能优化: 所有正则在模块级预编译一次,避免每次 check() 重复编译。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 模块级预编译正则(避免每次 check() 重复编译,提升检测性能)
# ---------------------------------------------------------------------------

# 策略1: 角色劫持 — 试图覆盖 AI 角色设定("ignore previous instructions" 等)
_ROLE_HIJACK_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)ignore\s+(all\s+)?previous\s+(instructions|prompts)"),
    re.compile(r"(?i)disregard\s+(the\s+)?above"),
    re.compile(r"(?i)forget\s+(everything|all\s+previous)"),
    re.compile(r"(?i)you\s+are\s+now\s+(a|an)\s+\w+"),
    re.compile(r"(?i)从现在起(你是|你扮演)"),
    re.compile(r"(?i)忽略(以上|之前)(所有)?(指令|提示)"),
    re.compile(r"(?i)重新定义你的角色"),
    re.compile(r"(?i)你的新身份是"),
)

# 策略2: 指令覆盖 — 伪造系统级指令(行首 "system:" / "### instruction" 等)
_INSTRUCTION_OVERRIDE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)^[\s#]*system\s*:", re.MULTILINE),
    re.compile(r"(?i)^[\s#]*(instruction|directive)\s*:", re.MULTILINE),
    re.compile(r"(?i)###\s*(system|instruction|admin)"),
    re.compile(r"(?i)\[system\]"),
    re.compile(r"(?i)新(指令|规则):"),
)

# 策略3: 分隔符注入 — 伪造消息边界标记(</system> / ---END--- 等)
_DELIMITER_INJECTION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)-{3,}\s*END\s*-{3,}"),
    re.compile(r"(?i)</s?ystem>"),
    re.compile(r"(?i)</?assistant>"),
    re.compile(r"(?i)</?user>"),
    re.compile(r"(?i)==+\s*END\s*==+"),
    re.compile(r"(?i)\[\/?(system|user|assistant)\]"),
)

# 策略4: 编码攻击 — Base64 隐藏指令(40+ 字符的 Base64 串) + Unicode 零宽字符
_B64_PATTERN: re.Pattern = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
# Unicode 零宽字符(U+200B/200C/200D/FEFF)用于混淆检测
_ZERO_WIDTH_PATTERN: re.Pattern = re.compile(r"[\u200b\u200c\u200d\ufeff]")
# Base64 解码后检查的可疑关键词(小写匹配)
_B64_SUSPICIOUS_KEYWORDS: tuple[str, ...] = (
    "ignore",
    "system",
    "admin",
    "execute",
    "rm ",
)

# 策略5: 命令注入 — 试图执行系统命令(rm -rf / curl / eval / subprocess 等)
_COMMAND_INJECTION_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"(?i)\brm\s+-rf?\b"),
    re.compile(r"(?i)\bcurl\s+"),
    re.compile(r"(?i)\bwget\s+"),
    re.compile(r"(?i)\beval\s*\("),
    re.compile(r"(?i)\bexec\s*\("),
    re.compile(r"(?i)\bsubprocess\b"),
    re.compile(r"(?i)\bos\.system\b"),
    re.compile(r"(?i)\b__import__\b"),
    re.compile(r"(?i)\bnc\s+-"),
    re.compile(r"(?i)\bchmod\s+\d+"),
    re.compile(r"(?i)\bsudo\s+"),
)


@dataclass
class InjectionCheckResult:
    """注入检测结果。

    Attributes:
        passed: 是否通过(未检测到注入)
        risk_score: 综合风险评分 [0, 1]
        reasons: 命中原因列表
        matched_patterns: 命中的策略名列表
    """

    passed: bool  # 是否通过(未检测到注入)
    risk_score: float  # 综合风险评分 [0, 1]
    reasons: list[str] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)


class InjectionGuard:
    """多策略 Prompt 注入防护。

    Args:
        threshold: 风险评分阈值 [0, 1],超过则 passed=False(默认 0.5)

    Raises:
        ValueError: threshold 不在 [0, 1] 范围内
    """

    def __init__(self, threshold: float = 0.5):
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"threshold 必须在 [0.0, 1.0] 范围内, 实为 {threshold}")
        self._threshold = threshold

    # -- 检测策略 ----------------------------------------------------------

    def _detect_role_hijack(self, text: str) -> tuple[float, str]:
        """策略1: 角色劫持 — 试图覆盖 AI 角色设定。

        匹配 "ignore previous instructions" / "你现在是..." 等模式。
        风险评分 0.9(高危)。
        """
        for p in _ROLE_HIJACK_PATTERNS:
            if p.search(text):
                return (0.9, f"角色劫持: 匹配 {p.pattern}")
        return (0.0, "")

    def _detect_instruction_override(self, text: str) -> tuple[float, str]:
        """策略2: 指令覆盖 — 伪造系统级指令。

        匹配行首 "system:" / "### instruction" / "[system]" 等伪造标记。
        风险评分 0.85(高危)。
        """
        for p in _INSTRUCTION_OVERRIDE_PATTERNS:
            if p.search(text):
                return (0.85, f"指令覆盖: 匹配 {p.pattern}")
        return (0.0, "")

    def _detect_delimiter_injection(self, text: str) -> tuple[float, str]:
        """策略3: 分隔符注入 — 伪造消息边界标记。

        匹配 "</system>" / "---END---" / "[/user]" 等伪造的对话分隔符。
        风险评分 0.8(中高危)。
        """
        for p in _DELIMITER_INJECTION_PATTERNS:
            if p.search(text):
                return (0.8, f"分隔符注入: 匹配 {p.pattern}")
        return (0.0, "")

    def _detect_encoding_attack(self, text: str) -> tuple[float, str]:
        """策略4: 编码攻击 — Base64 隐藏指令或 Unicode 混淆。

        检测逻辑:
          1. 找到 40+ 字符的 Base64 串,尝试解码
          2. 解码内容含可疑关键词(ignore/system/admin 等)→ 0.95 分
          3. Unicode 零宽字符(U+200B 等)→ 0.7 分
        """
        # 查找所有疑似 Base64 字符串
        matches = _B64_PATTERN.findall(text)
        for m in matches:
            # 尝试解码,检查是否包含可疑关键词
            try:
                decoded = base64.b64decode(m).decode("utf-8", errors="ignore")
                decoded_lower = decoded.lower()
                if any(kw in decoded_lower for kw in _B64_SUSPICIOUS_KEYWORDS):
                    return (0.95, "Base64 隐藏指令: 解码含可疑关键词")
            except Exception:
                # 解码失败,跳过(非 Base64 或编码异常)
                _logger.debug('Unhandled exception', exc_info=True)
        # Unicode 零宽字符检测(用于绕过关键词过滤)
        if _ZERO_WIDTH_PATTERN.search(text):
            return (0.7, "Unicode 零宽字符注入")
        return (0.0, "")

    def _detect_command_injection(self, text: str) -> tuple[float, str]:
        """策略5: 命令注入 — 试图执行系统命令。

        匹配 rm -rf / curl / eval() / subprocess / os.system 等危险调用。
        风险评分 0.9(高危)。
        """
        for p in _COMMAND_INJECTION_PATTERNS:
            if p.search(text):
                return (0.9, f"命令注入: 匹配 {p.pattern}")
        return (0.0, "")

    # -- 综合检测 ----------------------------------------------------------

    def check(self, text: str) -> InjectionCheckResult:
        """运行全部检测策略,综合评分。

        评分算法: risk_score = max(各策略分数),超 threshold 则 passed=False。
        多策略并行检测,任一命中即记录,取最高分为综合评分。

        Args:
            text: 待检测文本

        Returns:
            InjectionCheckResult:含 passed/risk_score/reasons/matched_patterns
        """
        strategies = [
            ("role_hijack", self._detect_role_hijack),
            ("instruction_override", self._detect_instruction_override),
            ("delimiter_injection", self._detect_delimiter_injection),
            ("encoding_attack", self._detect_encoding_attack),
            ("command_injection", self._detect_command_injection),
        ]

        max_score = 0.0
        reasons: list[str] = []
        matched: list[str] = []

        for name, strategy in strategies:
            score, reason = strategy(text)
            if score > 0:
                reasons.append(reason)
                matched.append(name)
                if score > max_score:
                    max_score = score

        passed = max_score < self._threshold
        return InjectionCheckResult(
            passed=passed,
            risk_score=max_score,
            reasons=reasons,
            matched_patterns=matched,
        )
