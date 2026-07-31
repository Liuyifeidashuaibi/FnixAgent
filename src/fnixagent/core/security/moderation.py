"""
内容审核 (Content Moderator) - Phase 3.2 增强。

支持双向审核:
  - review_input():  用户输入侧(敏感词/有害内容/PII 一律拦截)
  - review():        LLM 输出侧(PII 仅脱敏,不拦截)

审核维度:
  1. 敏感词扫描(复用 SensitiveDetector,DFA 算法)
  2. 有害内容检测 — 5 大类:
       - 自伤/自杀
       - 暴力/武器
       - 色情/低俗
       - 政治/极端
       - 诈骗/违法
  3. PII 泄露检测(手机号/邮箱/身份证/银行卡)
  4. 自动脱敏(对检测到的 PII 调用 Desensitizer)
  5. 审计日志(违规时自动写入审计链,失败不影响主流程)

Phase 2.11 验收:违规输入 100ms 内拦截,违规输出不展示,审计可查。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from fnixagent.core.security.desensitize import Desensitizer
from fnixagent.core.security.sensitive import SensitiveDetector

# ---------------------------------------------------------------------------
# 审核类别常量
# ---------------------------------------------------------------------------

CATEGORY_SELF_HARM: str = "self_harm"  # 自伤/自杀
CATEGORY_VIOLENCE: str = "violence"  # 暴力/武器
CATEGORY_PORNOGRAPHY: str = "pornography"  # 色情/低俗
CATEGORY_POLITICAL: str = "political"  # 政治/极端
CATEGORY_FRAUD: str = "fraud"  # 诈骗/违法
CATEGORY_PII: str = "pii"  # PII 泄露
CATEGORY_SENSITIVE: str = "sensitive_word"  # 敏感词

ALL_CATEGORIES: tuple[str, ...] = (
    CATEGORY_SELF_HARM,
    CATEGORY_VIOLENCE,
    CATEGORY_PORNOGRAPHY,
    CATEGORY_POLITICAL,
    CATEGORY_FRAUD,
    CATEGORY_PII,
    CATEGORY_SENSITIVE,
)


# ---------------------------------------------------------------------------
# 审核结果 DTO
# ---------------------------------------------------------------------------


@dataclass
class ModerationResult:
    """内容审核结果。"""

    passed: bool  # 是否通过
    issues: list[str] = field(default_factory=list)
    sanitized_text: str = ""  # 脱敏后的文本
    sensitive_hits: list[str] = field(default_factory=list)
    pii_hits: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)  # 命中的违规类别
    risk_score: int = 0  # 风险评分 0-100
    duration_ms: int = 0  # 审核耗时


# ---------------------------------------------------------------------------
# 有害内容模式库(按类别分组)
# ---------------------------------------------------------------------------

_HARMFUL_PATTERNS: list[tuple[str, re.Pattern]] = [
    # 自伤/自杀
    (
        CATEGORY_SELF_HARM,
        re.compile(
            r"(?i)(自杀|自残|自伤|割腕|安眠药|跳楼|轻生|结束生命|想死|kill\s+yourself|commit\s+suicide)"
        ),
    ),
    # 暴力/武器
    (
        CATEGORY_VIOLENCE,
        re.compile(
            r"(?i)(炸弹制作|制毒|制枪|黑客教程|杀人方法|buy\s+gun|how\s+to\s+make\s+bomb|explosive\s+recipe)"
        ),
    ),
    # 色情/低俗
    (
        CATEGORY_PORNOGRAPHY,
        re.compile(r"(?i)(色情|黄色电影|裸聊|一夜情| AV |成人视频|porn|xxx|nude|sexual\s+content)"),
    ),
    # 政治/极端
    (
        CATEGORY_POLITICAL,
        re.compile(
            r"(?i)(颠覆|煽动|分裂国家|反动|极端主义|恐怖主义|邪教|法轮|terrorist\s+attack|extremism)"
        ),
    ),
    # 诈骗/违法
    (
        CATEGORY_FRAUD,
        re.compile(
            r"(?i)(传销|诈骗|洗钱|贩毒|走私|贿赂|fake\s+id|money\s+laundering|drug\s+trafficking)"
        ),
    ),
]

# PII 正则
_PHONE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
_ID_CARD = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_BANK_CARD = re.compile(r"(?<!\d)(\d{4})\d{8,12}(\d{4})(?!\d)")


# ---------------------------------------------------------------------------
# 审计日志辅助(延迟导入避免循环依赖)
# ---------------------------------------------------------------------------


def _audit_moderation(
    action: str,
    text: str,
    categories: list[str],
    risk_score: int,
    user_id: int | None = None,
    ip_address: str | None = None,
    direction: str = "output",
) -> None:
    """将审核违规写入审计日志(失败不影响主流程)。

    Args:
        action: 审计动作常量(如 "moderation.input_blocked")
        text: 原始文本(仅记录前 200 字符预览)
        categories: 命中的违规类别
        risk_score: 风险评分
        user_id: 触发用户 ID(可选)
        ip_address: 客户端 IP(可选)
        direction: "input" 或 "output"
    """
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(
            action=action,
            user_id=user_id,
            detail={
                "direction": direction,
                "categories": categories,
                "risk_score": risk_score,
                "text_preview": text[:200],
            },
            ip_address=ip_address,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 审核器
# ---------------------------------------------------------------------------


class ContentModerator:
    """内容审核器(双向:输入/输出)。

    用法:
        moderator = ContentModerator()
        # 输入侧审核(用户输入)
        in_result = moderator.review_input(user_text, user_id=42, ip_address="1.2.3.4")
        if not in_result.passed:
            return "请求被拦截"
        # 输出侧审核(LLM 输出,PII 仅脱敏)
        out_result = moderator.review(llm_output)
        return out_result.sanitized_text
    """

    def __init__(
        self,
        sensitive_detector: SensitiveDetector | None = None,
        desensitizer: Desensitizer | None = None,
    ) -> None:
        """初始化内容审核器。

        Args:
            sensitive_detector: 敏感词检测器(None 用默认)
            desensitizer: 脱敏器(None 用默认)
        """
        self._sensitive = sensitive_detector or SensitiveDetector()
        self._desensitizer = desensitizer or Desensitizer()

    # -- 输入侧审核 --------------------------------------------------------

    def review_input(
        self,
        text: str,
        user_id: int | None = None,
        ip_address: str | None = None,
        auto_sanitize: bool = True,
    ) -> ModerationResult:
        """对用户输入做严格审核。

        与输出审核的区别:
          - PII 命中也算违规(防止用户在对话中泄露他人隐私)
          - 任何类别命中即 passed=False
          - 自动写入审计日志(moderation.input_blocked)
        """
        start = time.monotonic()
        issues: list[str] = []
        sensitive_hits: list[str] = []
        pii_hits: list[str] = []
        categories: list[str] = []

        # 1. 敏感词扫描
        if self._sensitive.word_count > 0:
            hits = self._sensitive.detect(text)
            for word, _, _ in hits:
                sensitive_hits.append(word)
            if sensitive_hits:
                issues.append(f"敏感词命中: {sensitive_hits}")
                categories.append(CATEGORY_SENSITIVE)

        # 2. 有害内容检测(5 大类)
        for category, pattern in _HARMFUL_PATTERNS:
            m = pattern.search(text)
            if m:
                issues.append(f"有害内容[{category}]: {m.group()}")
                categories.append(category)

        # 3. PII 泄露检测(输入侧也拦截)
        phone_hits = _PHONE.findall(text)
        if phone_hits:
            pii_hits.extend([f"{p[0]}****{p[1]}" for p in phone_hits])
            issues.append("检测到手机号泄露")
            categories.append(CATEGORY_PII)

        if _EMAIL.search(text):
            pii_hits.append("邮箱")
            issues.append("检测到邮箱泄露")
            categories.append(CATEGORY_PII)

        if _ID_CARD.search(text):
            pii_hits.append("身份证号")
            issues.append("检测到身份证号泄露")
            categories.append(CATEGORY_PII)

        if _BANK_CARD.search(text):
            pii_hits.append("银行卡号")
            issues.append("检测到银行卡号泄露")
            categories.append(CATEGORY_PII)

        # 4. 自动脱敏(即使拦截也返回脱敏文本,供日志展示)
        sanitized = text
        if auto_sanitize and pii_hits:
            sanitized = self._desensitizer.mask_all(text)

        # 5. 判定 + 风险评分
        passed = len(categories) == 0
        risk_score = self._compute_risk_score(categories, sensitive_hits, pii_hits)

        # 6. 审计日志(违规时写入)
        if not passed:
            _audit_moderation(
                "moderation.input_blocked",
                text=text,
                categories=categories,
                risk_score=risk_score,
                user_id=user_id,
                ip_address=ip_address,
                direction="input",
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return ModerationResult(
            passed=passed,
            issues=issues,
            sanitized_text=sanitized,
            sensitive_hits=sensitive_hits,
            pii_hits=pii_hits,
            categories=categories,
            risk_score=risk_score,
            duration_ms=duration_ms,
        )

    # -- 输出侧审核 --------------------------------------------------------

    def review(
        self,
        text: str,
        auto_sanitize: bool = True,
        user_id: int | None = None,
        ip_address: str | None = None,
    ) -> ModerationResult:
        """对 LLM 输出做合规审核。

        与输入审核的区别:
          - PII 命中仅脱敏,不算违规(因 LLM 可能合理引用)
          - 敏感词/有害内容仍拦截
          - 自动写入审计日志(moderation.output_blocked)
        """
        start = time.monotonic()
        issues: list[str] = []
        sensitive_hits: list[str] = []
        pii_hits: list[str] = []
        categories: list[str] = []

        # 1. 敏感词扫描
        if self._sensitive.word_count > 0:
            hits = self._sensitive.detect(text)
            for word, _, _ in hits:
                sensitive_hits.append(word)
            if sensitive_hits:
                issues.append(f"敏感词命中: {sensitive_hits}")
                categories.append(CATEGORY_SENSITIVE)

        # 2. 有害内容检测(5 大类)
        for category, pattern in _HARMFUL_PATTERNS:
            m = pattern.search(text)
            if m:
                issues.append(f"有害内容[{category}]: {m.group()}")
                categories.append(category)

        # 3. PII 泄露检测(仅记录,不拦截)
        phone_hits = _PHONE.findall(text)
        if phone_hits:
            pii_hits.extend([f"{p[0]}****{p[1]}" for p in phone_hits])
            issues.append("检测到手机号泄露")

        if _EMAIL.search(text):
            pii_hits.append("邮箱")
            issues.append("检测到邮箱泄露")

        if _ID_CARD.search(text):
            pii_hits.append("身份证号")
            issues.append("检测到身份证号泄露")

        if _BANK_CARD.search(text):
            pii_hits.append("银行卡号")
            issues.append("检测到银行卡号泄露")

        # 4. 自动脱敏
        sanitized = text
        if auto_sanitize and pii_hits:
            sanitized = self._desensitizer.mask_all(text)

        # 5. 判定:敏感词或有害内容不通过;PII 仅脱敏
        blocking_categories = [c for c in categories if c != CATEGORY_PII]
        passed = len(blocking_categories) == 0
        risk_score = self._compute_risk_score(categories, sensitive_hits, pii_hits)

        # 6. 审计日志(仅拦截时写入)
        if not passed:
            _audit_moderation(
                "moderation.output_blocked",
                text=text,
                categories=blocking_categories,
                risk_score=risk_score,
                user_id=user_id,
                ip_address=ip_address,
                direction="output",
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return ModerationResult(
            passed=passed,
            issues=issues,
            sanitized_text=sanitized,
            sensitive_hits=sensitive_hits,
            pii_hits=pii_hits,
            categories=categories,
            risk_score=risk_score,
            duration_ms=duration_ms,
        )

    # -- 工具方法 ----------------------------------------------------------

    @staticmethod
    def _compute_risk_score(
        categories: list[str],
        sensitive_hits: list[str],
        pii_hits: list[str],
    ) -> int:
        """根据命中类别计算风险评分 0-100。

        评分规则:
          - 自伤/政治/诈骗:每命中 40 分(高危)
          - 暴力/色情:每命中 30 分(中危)
          - 敏感词:每命中 10 分
          - PII:每命中 5 分
        """
        score = 0
        high_risk = {CATEGORY_SELF_HARM, CATEGORY_POLITICAL, CATEGORY_FRAUD}
        mid_risk = {CATEGORY_VIOLENCE, CATEGORY_PORNOGRAPHY}

        for cat in categories:
            if cat in high_risk:
                score += 40
            elif cat in mid_risk:
                score += 30
            elif cat == CATEGORY_SENSITIVE:
                score += 10 * len(sensitive_hits)
            elif cat == CATEGORY_PII:
                score += 5 * len(pii_hits)

        return min(100, score)
