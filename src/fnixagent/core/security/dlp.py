"""
DLP 出口拦截 (Data Loss Prevention Gateway) - P2 安全模块。

参考 MyDLP + 商业 DLP,在 LLM 输出与文件下载出口处拦截:
  - 按通道(chat/file/mail/api)配置策略
  - PII 检测:邮箱 / 手机号 / 身份证 / 银行卡 / 护照(正则匹配 + 置信度评分)
  - 关键词词典检测(机密 / 绝密 / confidential 等)
  - 策略动作:ALLOW / BLOCK / REDACT / WARN

脱敏规则:
  - email:     a***@b.com
  - phone:     138****8888
  - id_card:   110***********1234
  - bank_card: 6222************1234

设计原则:
  - 零依赖(仅用标准库 re),正则在类级预编译
  - 文件检查:支持文本类文件,二进制文件跳过
  - 所有异常不外泄,捕获后返回 ALLOW(避免阻断业务)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


class DLPAction(Enum):
    """DLP 策略动作。"""

    ALLOW = "allow"
    BLOCK = "block"
    REDACT = "redact"
    WARN = "warn"


@dataclass
class DLPPolicy:
    """DLP 策略(按通道配置)。

    Attributes:
        name: 策略名
        channel: 通道(chat/file/mail/api)
        enabled: 是否启用
        pii_patterns: PII 模式名列表(email/phone/id_card/bank_card/passport)
        sensitive_keywords: 敏感关键词列表
        action: 命中后的动作
        min_confidence: 最小置信度阈值(低于此值忽略)
    """

    name: str
    channel: str
    enabled: bool = True
    pii_patterns: list[str] = field(
        default_factory=lambda: ["email", "phone", "id_card", "bank_card"]
    )
    sensitive_keywords: list[str] = field(
        default_factory=lambda: ["机密", "绝密", "内部", "confidential", "top secret"]
    )
    action: DLPAction = DLPAction.WARN
    min_confidence: float = 0.7


@dataclass
class DLPDetection:
    """单次检测结果。

    Attributes:
        pattern_name: 命中模式名(如 email / keyword:机密)
        matched_text: 命中文本(已脱敏,避免日志泄露)
        position: (start, end) 偏移
        confidence: 置信度(0.0-1.0)
        severity: 严重程度(info/low/medium/high)
    """

    pattern_name: str
    matched_text: str
    position: tuple[int, int]
    confidence: float
    severity: str


@dataclass
class DLPResult:
    """DLP 检查结果。

    Attributes:
        allowed: 是否放行(BLOCK 动作时为 False)
        action: 实际动作
        detections: 命中检测列表
        sanitized_output: 脱敏后的内容(REDACT 动作时填充)
        reason: 判定原因
    """

    allowed: bool
    action: DLPAction
    detections: list[DLPDetection]
    sanitized_output: str | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# DLPGateway
# ---------------------------------------------------------------------------


class DLPGateway:
    """DLP 出口拦截网关。

    用法:
        gateway = DLPGateway()
        # 检查 LLM 输出
        result = gateway.inspect(llm_output, channel="chat")
        if not result.allowed:
            return "内容被 DLP 拦截"
        if result.sanitized_output:
            return result.sanitized_output  # 使用脱敏后的内容
        # 检查文件
        result = gateway.inspect_file("/tmp/report.txt", channel="file")
    """

    # 内置 PII 正则(类级预编译,避免重复编译开销)
    PII_PATTERNS: dict[str, str] = {
        "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        "phone": r"1[3-9]\d{9}",  # 中国手机号
        "id_card": r"\d{17}[\dXx]",  # 身份证(18 位)
        "bank_card": r"\d{16,19}",  # 银行卡(16-19 位)
        "passport": r"[A-Z]\d{8}",  # 护照
    }

    # 预编译正则
    _COMPILED: dict[str, re.Pattern] = {name: re.compile(pat) for name, pat in PII_PATTERNS.items()}

    # 模式 → 默认严重程度
    _SEVERITY: dict[str, str] = {
        "email": "medium",
        "phone": "medium",
        "id_card": "high",
        "bank_card": "high",
        "passport": "high",
    }

    # 支持文本检查的文件扩展名
    _TEXT_EXTS = (".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".xml", ".html", ".log")

    # 单文件检查大小上限(10 MB,防止 OOM)
    _MAX_FILE_SIZE = 10 * 1024 * 1024

    def __init__(self, policies: list[DLPPolicy] | None = None) -> None:
        self._policies: list[DLPPolicy] = list(policies) if policies else []
        # 未配置策略时注册默认策略
        if not self._policies:
            self._policies = self._default_policies()

    # -- 公开接口 ----------------------------------------------------------

    def inspect(self, content: str, channel: str = "chat") -> DLPResult:
        """检查文本内容,返回 DLPResult。

        Args:
            content: 待检查文本(LLM 输出 / 邮件正文等)
            channel: 通道(chat/file/mail/api)
        """
        if not content:
            return DLPResult(
                allowed=True,
                action=DLPAction.ALLOW,
                detections=[],
                reason="空内容",
            )
        policy = self._match_policy(channel)
        if policy is None or not policy.enabled:
            return DLPResult(
                allowed=True,
                action=DLPAction.ALLOW,
                detections=[],
                reason="无匹配策略或已禁用",
            )
        # 检测 PII + 关键词
        detections = self._detect_pii(content, policy.pii_patterns)
        detections.extend(self._detect_keywords(content, policy.sensitive_keywords))
        # 过滤低置信度
        detections = [d for d in detections if d.confidence >= policy.min_confidence]
        if not detections:
            return DLPResult(
                allowed=True,
                action=DLPAction.ALLOW,
                detections=[],
                reason="未命中敏感内容",
            )
        # 按策略动作处理
        return self._apply_action(content, policy.action, detections)

    def inspect_file(self, file_path: str, channel: str = "file") -> DLPResult:
        """检查文件内容(仅文本类文件,二进制跳过)。

        Args:
            file_path: 文件路径
            channel: 通道(默认 file)
        """
        try:
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                return DLPResult(
                    allowed=True,
                    action=DLPAction.ALLOW,
                    detections=[],
                    reason="文件不存在",
                )
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in self._TEXT_EXTS:
                return DLPResult(
                    allowed=True,
                    action=DLPAction.ALLOW,
                    detections=[],
                    reason=f"非文本文件({ext}),跳过检查",
                )
            size = os.path.getsize(file_path)
            if size > self._MAX_FILE_SIZE:
                return DLPResult(
                    allowed=True,
                    action=DLPAction.ALLOW,
                    detections=[],
                    reason=f"文件过大({size} bytes),跳过检查",
                )
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
            return self.inspect(content, channel=channel)
        except Exception as exc:
            logger.warning("[dlp] 文件检查异常 %s: %s", file_path, exc)
            return DLPResult(
                allowed=True,
                action=DLPAction.ALLOW,
                detections=[],
                reason=f"检查异常: {exc}",
            )

    def redact(self, content: str, detections: list[DLPDetection]) -> str:
        """对命中的检测项做脱敏处理。

        按位置倒序替换,避免偏移变化。
        """
        # 倒序排列,从后向前替换
        sorted_dets = sorted(detections, key=lambda d: d.position[0], reverse=True)
        result = content
        for det in sorted_dets:
            start, end = det.position
            if start < 0 or end > len(result) or start >= end:
                continue
            masked = self._mask_segment(det.pattern_name, result[start:end])
            result = result[:start] + masked + result[end:]
        return result

    def add_policy(self, policy: DLPPolicy) -> None:
        """添加策略。"""
        self._policies.append(policy)

    def list_policies(self) -> list[DLPPolicy]:
        """列出所有策略。"""
        return list(self._policies)

    # -- 内部:检测 --------------------------------------------------------

    def _detect_pii(self, content: str, patterns: list[str]) -> list[DLPDetection]:
        """PII 正则检测,返回检测列表。"""
        detections: list[DLPDetection] = []
        for name in patterns:
            regex = self._COMPILED.get(name)
            if regex is None:
                continue
            try:
                for m in regex.finditer(content):
                    matched = m.group(0)
                    # 过滤明显误报:银行卡/id_card 要求纯数字(不夹在更长的字母串中)
                    if name in ("bank_card", "id_card"):
                        # 检查前后字符是否为字母(避免匹配 hash/版本号)
                        s, e = m.start(), m.end()
                        before = content[s - 1] if s > 0 else ""
                        after = content[e] if e < len(content) else ""
                        if before.isalpha() or after.isalpha():
                            continue
                    confidence = self._score_confidence(name, matched)
                    detections.append(
                        DLPDetection(
                            pattern_name=name,
                            matched_text=self._mask_segment(name, matched),
                            position=(m.start(), m.end()),
                            confidence=confidence,
                            severity=self._SEVERITY.get(name, "medium"),
                        )
                    )
            except Exception:
                continue
        return detections

    def _detect_keywords(self, content: str, keywords: list[str]) -> list[DLPDetection]:
        """关键词检测(简单字符串匹配,大小写不敏感)。"""
        detections: list[DLPDetection] = []
        lower = content.lower()
        for kw in keywords:
            if not kw:
                continue
            start = 0
            kw_lower = kw.lower()
            while True:
                idx = lower.find(kw_lower, start)
                if idx < 0:
                    break
                detections.append(
                    DLPDetection(
                        pattern_name=f"keyword:{kw}",
                        matched_text=kw,
                        position=(idx, idx + len(kw)),
                        confidence=0.9,
                        severity="high",
                    )
                )
                start = idx + len(kw)
        return detections

    @staticmethod
    def _score_confidence(pattern_name: str, matched: str) -> float:
        """置信度评分:完全格式匹配 0.9,长度边界 0.7。"""
        if pattern_name == "email" and "@" in matched and "." in matched:
            return 0.9
        if pattern_name == "phone" and len(matched) == 11:
            return 0.9
        if pattern_name == "id_card" and len(matched) == 18:
            return 0.9
        if pattern_name == "bank_card" and 16 <= len(matched) <= 19:
            return 0.85
        if pattern_name == "passport" and len(matched) == 9:
            return 0.85
        return 0.7

    # -- 内部:脱敏 --------------------------------------------------------

    @staticmethod
    def _mask_segment(pattern_name: str, text: str) -> str:
        """对单段文本按模式脱敏。"""
        if not text:
            return text
        try:
            if pattern_name == "email":
                # a***@b.com
                if "@" in text:
                    name, _, domain = text.partition("@")
                    if len(name) <= 1:
                        return text
                    return name[0] + "*" * (len(name) - 1) + "@" + domain
                return text
            if pattern_name == "phone":
                # 138****8888
                if len(text) == 11:
                    return text[:3] + "****" + text[7:]
                return text
            if pattern_name == "id_card":
                # 110***********1234
                if len(text) == 18:
                    return text[:3] + "*" * 11 + text[14:]
                return text
            if pattern_name == "bank_card":
                # 6222************1234
                if len(text) >= 8:
                    return text[:4] + "*" * (len(text) - 8) + text[-4:]
                return text
            if pattern_name == "passport":
                # A********
                if len(text) == 9:
                    return text[0] + "*" * 8
                return text
        except Exception:
            pass
        # 关键词或其他:统一掩码中间
        if len(text) <= 2:
            return "*" * len(text)
        return text[0] + "*" * (len(text) - 2) + text[-1]

    # -- 内部:策略匹配与动作 ---------------------------------------------

    def _match_policy(self, channel: str) -> DLPPolicy | None:
        """匹配通道对应的策略(第一个匹配的 enabled 策略)。"""
        for p in self._policies:
            if p.channel == channel and p.enabled:
                return p
        # 回退:匹配通用通道 "*"
        for p in self._policies:
            if p.channel == "*" and p.enabled:
                return p
        return None

    def _apply_action(
        self,
        content: str,
        action: DLPAction,
        detections: list[DLPDetection],
    ) -> DLPResult:
        """根据动作生成 DLPResult。"""
        if action == DLPAction.ALLOW:
            return DLPResult(
                allowed=True,
                action=action,
                detections=detections,
                reason="策略允许通过",
            )
        if action == DLPAction.WARN:
            logger.warning(
                "[dlp] 命中 %d 处敏感内容(WARN): %s",
                len(detections),
                [d.pattern_name for d in detections][:5],
            )
            return DLPResult(
                allowed=True,
                action=action,
                detections=detections,
                reason=f"命中 {len(detections)} 处敏感内容,已告警",
            )
        if action == DLPAction.REDACT:
            sanitized = self.redact(content, detections)
            return DLPResult(
                allowed=True,
                action=action,
                detections=detections,
                sanitized_output=sanitized,
                reason=f"已脱敏 {len(detections)} 处敏感内容",
            )
        # BLOCK
        logger.warning(
            "[dlp] 内容被阻断(BLOCK),命中 %d 处敏感内容",
            len(detections),
        )
        self._audit_block(detections)
        return DLPResult(
            allowed=False,
            action=action,
            detections=detections,
            reason=f"内容被 DLP 阻断(命中 {len(detections)} 处敏感内容)",
        )

    @staticmethod
    def _audit_block(detections: list[DLPDetection]) -> None:
        """将 DLP 阻断事件写入审计日志(失败不影响主流程)。"""
        try:
            from fnixagent.core.audit import AuditLogger

            AuditLogger().log(
                action="dlp.blocked",
                detail={
                    "count": len(detections),
                    "patterns": [d.pattern_name for d in detections[:10]],
                },
            )
        except Exception:
            pass

    # -- 内部:默认策略 ----------------------------------------------------

    @staticmethod
    def _default_policies() -> list[DLPPolicy]:
        """生成默认策略集(各通道默认 WARN)。"""
        return [
            DLPPolicy(
                name="chat-default",
                channel="chat",
                action=DLPAction.WARN,
            ),
            DLPPolicy(
                name="file-default",
                channel="file",
                action=DLPAction.REDACT,
            ),
            DLPPolicy(
                name="mail-default",
                channel="mail",
                action=DLPAction.BLOCK,
                pii_patterns=["email", "phone", "id_card", "bank_card", "passport"],
            ),
            DLPPolicy(
                name="api-default",
                channel="api",
                action=DLPAction.WARN,
            ),
        ]
