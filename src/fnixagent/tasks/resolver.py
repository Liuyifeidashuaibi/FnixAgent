"""答案/内容恢复器(Phase 5.5)。

针对题库 docx 中答案字段乱码(格式如 ``NAMEACONTENTMIPSNAMEBCONTENTMFLOPS``,
即所有选项的"字母+内容"拼接,丢失正确答案标记)的多级恢复策略。

乱码不可逆向恢复,因此采用多级策略链(L1 → L2 → L3):
  - L1 题库匹配: 通过题干指纹(年份+前N字hash)在已注册题库中查找正确答案
  - L2 LLM解题: 调用 fnixagent.core.llm 的 LLMRouter 解题,返回字母+置信度
  - L3 人工标记: L1/L2 都失败或置信度低时,标记 needs_manual=True

设计:
  - GarbageReport: 乱码检测报告
  - GarbageDetector: 乱码检测器(识别 name_content/encoding/placeholder/normal)
  - ResolveResult: 答案恢复结果
  - AnswerResolver: 答案恢复器(多级策略链)

降级策略:
  - LLM 调用用 try/except 包裹,失败降级到 L3,绝不崩溃
  - 题库为空时直接跳过 L1
  - LLMRouter 未注入时 _llm_solve 返回 None,自动降级到 L3
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from fnixagent.office.base import BaseExpert, ExpertResult

__all__ = [
    "AnswerResolver",
    "GarbageDetector",
    "GarbageReport",
    "ResolveResult",
]

# ---------------------------------------------------------------------------
# 正则模式
# ---------------------------------------------------------------------------

# NAME{X}CONTENT{Y} 拼接模式,匹配 NAMEACONTENTxxxNAMEBCONTENTyyy 形式
# 使用前瞻 (?=NAME[A-Z]CONTENT|$) 定位下一个选项的起始位置
_NAME_CONTENT_PATTERN = re.compile(r"NAME([A-Z])CONTENT(.+?)(?=NAME[A-Z]CONTENT|$)")

# 编码乱码:连续的 Latin-1 补充字符(Âè Ã¦ 等)或 Unicode 替换符 \ufffd
_ENCODING_GARBLE_PATTERN = re.compile(r"[\u00c0-\u00ff]{2,}|\ufffd")

# 占位符:{{answer}} 或 {ANSWER} 形式
_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^}]+\}\}|\{[A-Z_]{2,}\}")

# 年份提取:4位数字(20xx 或 19xx)
_YEAR_PATTERN = re.compile(r"(20\d{2}|19\d{2})")

# 年份(含可选"年"后缀),用于从题干中移除年份前缀
_YEAR_STRIP_PATTERN = re.compile(r"(?:20\d{2}|19\d{2})年?")

# 括号中的字母答案:（B）或 (B) 或 （ABC）
_BRACKET_ANSWER_PATTERN = re.compile(r"[（(]([A-Z]+)[)）]")

# 文本中独立的单个大写字母
_STANDALONE_LETTER_PATTERN = re.compile(r"\b([A-Z])\b")

# 置信度阈值:低于此值标记 needs_manual
_CONFIDENCE_THRESHOLD = 0.7

# 题干指纹取前 N 个字符
_FINGERPRINT_HEAD_LEN = 50

# ---------------------------------------------------------------------------
# 乱码检测报告
# ---------------------------------------------------------------------------

@dataclass
class GarbageReport:
    """乱码检测报告。

    Attributes:
        is_garbled: 是否为乱码
        garble_type: 乱码类型,取值:
            "name_content" — NAMEACONTENT 拼接(不可恢复)
            "encoding"     — 编码乱码如 Âè(可尝试修复)
            "placeholder"  — {{answer}} 占位符(不可恢复)
            "normal"       — 正常文本
        recoverable: 是否可从乱码本身恢复(不含题库/LLM 等外部恢复)
        parsed_options: 解析出的(字母,内容)对,仅 name_content 类型有效
        raw_text: 原始文本
    """

    is_garbled: bool = False
    garble_type: str = "normal"
    recoverable: bool = True
    parsed_options: list[tuple[str, str]] = field(default_factory=list)
    raw_text: str = ""

# ---------------------------------------------------------------------------
# 乱码检测器
# ---------------------------------------------------------------------------

class GarbageDetector(BaseExpert):
    """乱码检测器。

    识别答案字段中的乱码类型,为后续恢复策略提供判断依据:

      - name_content: ``NAMEACONTENTxxx`` 拼接形式,选项内容拼接但丢失
        正确答案标记,不可从乱码本身恢复(recoverable=False)
      - encoding: 编码乱码(如 ``Âè``),可尝试编码修复(recoverable=True)
      - placeholder: ``{{answer}}`` 占位符,不可恢复(recoverable=False)
      - normal: 正常文本(recoverable=True)
    """

    @property
    def name(self) -> str:
        return "garbage_detector"

    def detect(self, answer_text: str) -> GarbageReport:
        """检测答案文本是否为乱码。

        按优先级依次检测:name_content → placeholder → encoding → normal。
        name_content 优先级最高,因为它是题库场景最典型的乱码形式。

        Args:
            answer_text: 待检测的答案文本

        Returns:
            GarbageReport: 检测报告
        """
        raw = answer_text or ""

        # 1. name_content 模式(最典型的题库乱码)
        if _NAME_CONTENT_PATTERN.search(raw):
            options = self.parse_name_content(raw)
            return GarbageReport(
                is_garbled=True,
                garble_type="name_content",
                recoverable=False,
                parsed_options=options,
                raw_text=raw,
            )

        # 2. 占位符 {{answer}} 或 {ANSWER}
        if _PLACEHOLDER_PATTERN.search(raw):
            return GarbageReport(
                is_garbled=True,
                garble_type="placeholder",
                recoverable=False,
                parsed_options=[],
                raw_text=raw,
            )

        # 3. 编码乱码(连续 Latin-1 补充字符)
        if _ENCODING_GARBLE_PATTERN.search(raw):
            return GarbageReport(
                is_garbled=True,
                garble_type="encoding",
                recoverable=True,
                parsed_options=[],
                raw_text=raw,
            )

        # 4. 正常文本
        return GarbageReport(
            is_garbled=False,
            garble_type="normal",
            recoverable=True,
            parsed_options=[],
            raw_text=raw,
        )

    def parse_name_content(self, text: str) -> list[tuple[str, str]]:
        """解析 ``NAMEACONTENTxxx`` 为 ``[(A, xxx), ...]``。

        利用前瞻正则定位每个选项的边界,提取字母与内容。

        Args:
            text: NAME{X}CONTENT{Y} 拼接的乱码文本

        Returns:
            解析出的(字母,内容)对列表;非匹配格式返回空列表
        """
        if not text:
            return []
        pairs: list[tuple[str, str]] = []
        for m in _NAME_CONTENT_PATTERN.finditer(text):
            letter = m.group(1)
            content = m.group(2).strip()
            pairs.append((letter, content))
        return pairs

# ---------------------------------------------------------------------------
# 答案恢复结果
# ---------------------------------------------------------------------------

@dataclass
class ResolveResult:
    """答案恢复结果。

    Attributes:
        question_num: 题号
        answer: 恢复的答案字母(如 "B");None 表示未恢复
        confidence: 置信度 0-1
        source: 恢复来源("question_bank"/"llm"/"manual"/"none")
        needs_manual: 是否需要人工确认
    """

    question_num: str = ""
    answer: str | None = None
    confidence: float = 0.0
    source: str = "none"
    needs_manual: bool = True

# ---------------------------------------------------------------------------
# 答案恢复器
# ---------------------------------------------------------------------------

class AnswerResolver(BaseExpert):
    """答案恢复器(多级策略链)。

    恢复策略链(L1 → L2 → L3):

      - L1 题库匹配: 通过题干指纹(年份+前N字hash)在已注册题库中查找。
        命中时返回答案,置信度 0.95(精确匹配)或 0.9(指纹匹配)。
      - L2 LLM解题: 调用 LLMRouter 构造选择题 prompt,解析返回提取字母。
        LLM 不可用时返回 None,自动降级到 L3。
      - L3 人工标记: L1/L2 都失败或置信度低于阈值时,标记 needs_manual=True。

    LLM 调用为可选,通过 ``__init__(llm_router=...)`` 或 ``set_llm_router()``
    注入。未注入时 _llm_solve 直接返回 None,不影响 L1/L3 正常工作。
    """

    def __init__(self, llm_router: Any | None = None) -> None:
        """初始化答案恢复器。

        Args:
            llm_router: 可选的 LLMRouter 实例;None 时 L2 降级跳过
        """
        # 题库:键为 (年份, 题干指纹) → 答案字母
        self._question_bank: dict[tuple[str, str], str] = {}
        self._llm_router = llm_router

    @property
    def name(self) -> str:
        return "answer_resolver"

    def set_llm_router(self, router: Any) -> None:
        """注入 LLMRouter 实例(可选,用于 L2 解题)。

        Args:
            router: LLMRouter 实例
        """
        self._llm_router = router

    # ------------------------------------------------------------------
    # 主入口:多级恢复
    # ------------------------------------------------------------------

    def resolve(
        self,
        question_num: str,
        stem: str,
        options: list[str],
        garbled_answer: str,
    ) -> ResolveResult:
        """多级策略恢复答案。

        依次尝试 L1(题库)→ L2(LLM)→ L3(人工),首个成功策略返回结果。

        Args:
            question_num: 题号
            stem: 题干文本
            options: 选项列表(如 ["MIPS", "FLOPS", ...])
            garbled_answer: 乱码答案文本(用于上下文参考,本方法不依赖其解析)

        Returns:
            ResolveResult: 恢复结果(needs_manual=True 时需人工确认)
        """
        # L1: 题库匹配
        matched = self._match_question_bank(stem)
        if matched is not None:
            answer, confidence = matched
            return ResolveResult(
                question_num=question_num,
                answer=answer,
                confidence=confidence,
                source="question_bank",
                needs_manual=confidence < _CONFIDENCE_THRESHOLD,
            )

        # L2: LLM 解题
        solved = self._llm_solve(stem, options)
        if solved is not None:
            answer, confidence = solved
            # 置信度足够时直接返回;不足时保留答案但标记需人工
            return ResolveResult(
                question_num=question_num,
                answer=answer,
                confidence=confidence,
                source="llm",
                needs_manual=confidence < _CONFIDENCE_THRESHOLD,
            )

        # L3: 人工标记
        return ResolveResult(
            question_num=question_num,
            answer=None,
            confidence=0.0,
            source="none",
            needs_manual=True,
        )

    # ------------------------------------------------------------------
    # 题库管理
    # ------------------------------------------------------------------

    def register_question_bank(self, entries: list[dict]) -> ExpertResult:
        """批量注册题库。

        每条 entry 需包含:
          - year: 年份(如 "2024"),可为空串
          - stem: 题干文本
          - answer: 正确答案字母(如 "B")

        Args:
            entries: 题库条目列表

        Returns:
            ExpertResult: output 为 {"registered": int, "errors": list[str]}
        """
        if not isinstance(entries, list):
            return self._failure("entries must be a list")

        registered = 0
        errors: list[str] = []
        for i, entry in enumerate(entries):
            try:
                year = str(entry.get("year", "")).strip()
                stem = str(entry.get("stem", "")).strip()
                answer = str(entry.get("answer", "")).strip().upper()
                if not stem or not answer:
                    errors.append(f"entry[{i}]: missing stem or answer")
                    continue
                # 指纹前移除年份,使同一题目(含/不含年份前缀)指纹一致
                stem_clean = self._strip_year(stem)
                fp = self._stem_fingerprint(stem_clean)
                self._question_bank[(year, fp)] = answer
                registered += 1
            except (AttributeError, TypeError) as e:
                errors.append(f"entry[{i}]: {e}")

        return self._success(
            output={"registered": registered, "errors": errors},
            registered=registered,
            error_count=len(errors),
        )

    # ------------------------------------------------------------------
    # L1: 题库指纹匹配
    # ------------------------------------------------------------------

    def _match_question_bank(self, stem: str) -> tuple[str, float] | None:
        """指纹匹配题库。

        从题干中提取年份(4位数字)+题干指纹,在题库中查找。
        若题干无年份或精确匹配失败,则遍历所有年份做指纹匹配。

        Args:
            stem: 题干文本

        Returns:
            (答案, 置信度) 或 None;精确匹配置信度 0.95,指纹匹配 0.9
        """
        if not self._question_bank or not stem:
            return None

        # 指纹前移除年份,使同一题目(含/不含年份前缀)指纹一致
        fp = self._stem_fingerprint(self._strip_year(stem))

        # 优先:年份+指纹 精确匹配
        year_match = _YEAR_PATTERN.search(stem)
        if year_match:
            year = year_match.group(1)
            key = (year, fp)
            if key in self._question_bank:
                return (self._question_bank[key], 0.95)

        # 回退:无年份或精确未命中,遍历所有年份做指纹匹配
        for (y, f), answer in self._question_bank.items():
            if f == fp:
                return (answer, 0.9)

        return None

    # ------------------------------------------------------------------
    # L2: LLM 解题
    # ------------------------------------------------------------------

    def _llm_solve(self, stem: str, options: list[str]) -> tuple[str, float] | None:
        """调用 LLM 解题。

        构造选择题 prompt,调用 LLMRouter,解析返回提取字母与置信度。
        LLM 不可用或调用失败时返回 None(降级到 L3),绝不抛异常。

        置信度规则:
          - 整个返回就是单个字母(如 "B")        → 0.85
          - 整个返回是 2-4 个字母(多选如 "AB")   → 0.80
          - 括号中的字母(如 "答案是（B）")       → 0.70
          - 文本中独立单字母(如 "选 B 因为...")   → 0.60
          - 包含 uncertain/不确定                → 0.30(或 None)

        Args:
            stem: 题干文本
            options: 选项列表

        Returns:
            (答案字母, 置信度) 或 None
        """
        if not stem or not options:
            return None

        router = self._llm_router
        if router is None:
            return None

        # 构造 prompt
        option_lines: list[str] = []
        for i, opt in enumerate(options):
            letter = chr(ord("A") + i)
            option_lines.append(f"{letter}. {opt}")
        prompt = (
            f"题干: {stem}\n"
            f"选项:\n" + "\n".join(option_lines) + "\n\n"
            "请只返回答案字母(如 B)。如果不确定,返回 uncertain。"
        )

        try:
            from fnixagent.core.llm.base import LLMRequest
            from fnixagent.core.types import Message, MessageRole

            request = LLMRequest(
                messages=[
                    Message(
                        role=MessageRole.SYSTEM,
                        content="你是一个考试答题助手,只返回答案字母。",
                    ),
                    Message(role=MessageRole.USER, content=prompt),
                ],
                temperature=0.0,
                max_tokens=32,
            )
            response = router.chat(request)
            text = (response.content or "").strip()
        except Exception:
            # LLM 调用失败(依赖缺失/熔断/超时/无 provider),降级到 L3
            return None

        return self._parse_llm_response(text)

    @staticmethod
    def _parse_llm_response(text: str) -> tuple[str, float] | None:
        """解析 LLM 返回,提取答案字母与置信度。

        Args:
            text: LLM 返回的原始文本

        Returns:
            (字母, 置信度) 或 None(无法解析)
        """
        if not text:
            return None

        stripped = text.strip()
        upper = stripped.upper()
        lower = stripped.lower()

        # 不确定:尝试提取可能提及的字母,置信度 0.3
        if "uncertain" in lower or "不确定" in stripped:
            m = _BRACKET_ANSWER_PATTERN.search(upper)
            if m:
                return (m.group(1), 0.3)
            m = _STANDALONE_LETTER_PATTERN.search(upper)
            if m:
                return (m.group(1), 0.3)
            return None

        # 整个返回就是单个字母 → 高置信度
        if re.fullmatch(r"[A-Z]", upper):
            return (upper, 0.85)

        # 整个返回是 2-4 个字母(多选)→ 高置信度
        if re.fullmatch(r"[A-Z]{2,4}", upper):
            return (upper, 0.80)

        # 括号中的字母 → 中高置信度
        m = _BRACKET_ANSWER_PATTERN.search(upper)
        if m:
            return (m.group(1), 0.70)

        # 文本中独立单字母 → 中置信度
        m = _STANDALONE_LETTER_PATTERN.search(upper)
        if m:
            return (m.group(1), 0.60)

        return None

    # ------------------------------------------------------------------
    # 题干指纹
    # ------------------------------------------------------------------

    def _stem_fingerprint(self, stem: str) -> str:
        """题干指纹(去空白标点+取前N字+MD5 hash)。

        移除所有非文字字符(空白、标点、符号)后取前 50 个字符,
        MD5 取前 16 位作为指纹。容忍题干末尾标点差异(如 "?" vs 无标点)。

        Args:
            stem: 题干文本

        Returns:
            指纹字符串(MD5 前 16 位十六进制)
        """
        # \w 在 Python3 默认 UNICODE 模式下匹配字母、数字、下划线和 CJK 字符
        cleaned = re.sub(r"[^\w]", "", stem or "")
        head = cleaned[:_FINGERPRINT_HEAD_LEN]
        return hashlib.md5(head.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _strip_year(stem: str) -> str:
        """从题干中移除年份,使指纹不依赖年份前缀。

        同一题目(含 "2024年" 前缀或不含)应产生相同指纹,
        因此在计算指纹前统一移除 4 位年份及紧跟的 "年" 字。

        Args:
            stem: 题干文本

        Returns:
            移除年份后的题干文本
        """
        return _YEAR_STRIP_PATTERN.sub("", stem or "")
