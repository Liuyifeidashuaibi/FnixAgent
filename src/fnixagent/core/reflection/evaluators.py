"""6 个加权评估器。

每个评估器实现统一的 evaluate() 接口,返回 0~1 的子分数。
ReflectionManager 并行调用所有启用的评估器,加权计算总分。

评估维度:
  1. LengthEvaluator    - 内容长度是否达标
  2. StructureEvaluator - 结构(段落/标题/列表/代码块)
  3. KeywordEvaluator   - 关键词覆盖率
  4. CitationEvaluator  - 引用完整性
  5. FormatEvaluator    - 格式规范(占位符/空行/尾部空白)
  6. LLMEvaluator       - LLM 综合评估(可选,默认关闭)

设计要点:
  - 全部继承 BaseEvaluator(abc.ABC)
  - evaluate() 为同步方法,由 manager 通过 asyncio.to_thread 并行调度
  - 单评估器异常不影响其他评估器(manager 层处理)
  - 超时由 manager 的 asyncio.wait_for 控制,评估器自身不感知超时
  - 正则预编译为模块级常量,避免每次 evaluate 重新编译
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
import json
import re
from typing import Any

from fnixagent.core.reflection.base import ReflectionConfig

# ---------------------------------------------------------------------------
# 预编译正则(模块级常量,避免每次 evaluate 重新编译)
# ---------------------------------------------------------------------------

# 结构评估器
_HEADING_RE = re.compile(r"^(?:#{1,6}\s+\S+|\d+\.\s+\S+)", re.MULTILINE)
_LIST_RE = re.compile(r"^\s*(?:[-*+]\s+\S+|\d+\.\s+\S+)", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```|^\s{4,}\S+", re.MULTILINE)
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")

# 引用评估器
_CITATION_MARK_RE = re.compile(r"\[\d+\]")
_REFERENCE_SECTION_RE = re.compile(r"参考文献|References|REFERENCES|Bibliography", re.IGNORECASE)
_DOI_URL_RE = re.compile(r"https?://\S+|doi:\s*\S+|10\.\d{4,}/\S+", re.IGNORECASE)

# 格式评估器
_PLACEHOLDER_RE = re.compile(r"\{\{[^}]+\}\}|TODO|待填写|待补充|XXX|<placeholder>", re.IGNORECASE)
_BLANK_LINES_RE = re.compile(r"\n\s*\n\s*\n")  # 连续 3+ 空行

# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class BaseEvaluator(abc.ABC):
    """评估器抽象基类。

    子类需实现:
      - name: 评估器名称(对应权重表 key)
      - evaluate(content, context, config): 返回 0~1 子分数
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """评估器名称(对应 manager 权重表 key,如 "length"/"format")。"""
        ...

    @abc.abstractmethod
    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        """评估内容,返回 0~1 子分数。

        Args:
            content: 待评估内容文本
            context: 评估上下文(可含 keywords/min_length/max_length/goal 等)
            config: 反思配置(子类可读取对应 enable_xxx 开关)

        Returns:
            子分数 0.0~1.0(越高越好)
        """
        ...

    @staticmethod
    def _clamp(score: float) -> float:
        """把分数 clamp 到 [0.0, 1.0]。"""
        try:
            s = float(score)
        except (TypeError, ValueError):
            return 0.0
        if s < 0.0:
            return 0.0
        if s > 1.0:
            return 1.0
        return s

# ---------------------------------------------------------------------------
# 1. LengthEvaluator
# ---------------------------------------------------------------------------

class LengthEvaluator(BaseEvaluator):
    """长度评估器。

    评分规则:
      - 0~50字符:   0.1~0.3 分(过短)
      - 50~200字符: 0.3~0.7 分(偏短)
      - 200+字符:   0.7~1.0 分(达标)

    context 可指定:
      - min_length: 最小长度(达到则满分,否则按达标率评分)
      - max_length: 最大长度(超过则扣分)
    """

    @property
    def name(self) -> str:
        return "length"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        if not content:
            return 0.1
        length = len(content)

        min_length = context.get("min_length") if context else None
        max_length = context.get("max_length") if context else None

        if isinstance(min_length, (int, float)) and min_length > 0:
            # 上下文指定 min_length 时按达标率评分
            ratio = min(length / float(min_length), 1.0)
            score = 0.3 + 0.7 * ratio
        else:
            # 默认分段评分规则
            if length < 50:
                score = 0.1 + (length / 50.0) * 0.2  # 0.1~0.3
            elif length < 200:
                score = 0.3 + ((length - 50) / 150.0) * 0.4  # 0.3~0.7
            else:
                # 200~500 字符映射到 0.7~1.0,超出 500 字符封顶 1.0
                score = 0.7 + min((length - 200) / 300.0, 0.3)

        # 超过 max_length 扣分(防止冗余内容)
        if isinstance(max_length, (int, float)) and max_length > 0 and length > max_length:
            overflow = (length - float(max_length)) / float(max_length)
            score -= min(overflow * 0.5, 0.3)

        return self._clamp(score)

# ---------------------------------------------------------------------------
# 2. StructureEvaluator
# ---------------------------------------------------------------------------

class StructureEvaluator(BaseEvaluator):
    """结构评估器。

    评分规则(累加,上限 1.0):
      - 有标题(#/数字编号): +0.3
      - 有段落划分(空行分隔,≥2 段): +0.3
      - 有列表(-/*/数字): +0.2
      - 有代码块: +0.2
    """

    @property
    def name(self) -> str:
        return "structure"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        if not content:
            return 0.0
        score = 0.0
        # 标题
        if _HEADING_RE.search(content):
            score += 0.3
        # 段落划分(空行分隔,段落数 >= 2 视为有结构化段落)
        paragraphs = [p for p in _PARAGRAPH_SPLIT_RE.split(content) if p.strip()]
        if len(paragraphs) >= 2:
            score += 0.3
        # 列表
        if _LIST_RE.search(content):
            score += 0.2
        # 代码块
        if _CODE_BLOCK_RE.search(content):
            score += 0.2
        return self._clamp(score)

# ---------------------------------------------------------------------------
# 3. KeywordEvaluator
# ---------------------------------------------------------------------------

class KeywordEvaluator(BaseEvaluator):
    """关键词覆盖评估器。

    从 context["keywords"] 获取期望关键词列表,计算命中率:
      - 无 keywords 配置时返回 1.0(不评估,不拖累总分)
      - 命中率 = 命中数 / 总数
      - 分数 = 0.3 + 0.7 * 命中率

    命中判断大小写不敏感(对 content 与 keyword 都做 .lower())
    """

    @property
    def name(self) -> str:
        return "keyword"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        if not context:
            return 1.0
        keywords = context.get("keywords")
        if not keywords or not isinstance(keywords, (list, tuple)):
            # 无关键词配置,不评估,返回满分(不拖累总分)
            return 1.0
        if not content:
            return 0.0
        total = len(keywords)
        if total == 0:
            return 1.0
        content_lower = content.lower()
        hits = sum(
            1
            for kw in keywords
            if isinstance(kw, str) and kw.strip() and kw.lower() in content_lower
        )
        hit_rate = hits / total
        return self._clamp(0.3 + 0.7 * hit_rate)

# ---------------------------------------------------------------------------
# 4. CitationEvaluator
# ---------------------------------------------------------------------------

class CitationEvaluator(BaseEvaluator):
    """引用完整性评估器。

    评分规则(累加,上限 1.0):
      - 有 [1]/[2] 等引用标记: +0.3
      - 有参考文献部分(含"参考文献"/"References"): +0.4
      - 有 DOI/URL: +0.3

    无任何引用特征时返回 0.0(若内容需要引用但缺失则扣分)
    """

    @property
    def name(self) -> str:
        return "citation"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        if not content:
            return 0.0
        score = 0.0
        if _CITATION_MARK_RE.search(content):
            score += 0.3
        if _REFERENCE_SECTION_RE.search(content):
            score += 0.4
        if _DOI_URL_RE.search(content):
            score += 0.3
        return self._clamp(score)

# ---------------------------------------------------------------------------
# 5. FormatEvaluator
# ---------------------------------------------------------------------------

class FormatEvaluator(BaseEvaluator):
    """格式规范评估器。

    评分规则(累加,上限 1.0):
      - 无占位符({{xxx}}/TODO/待填写/XXX): +0.4
      - 无多余空行(连续 3+ 空行): +0.3
      - 无尾部空白: +0.3
    """

    @property
    def name(self) -> str:
        return "format"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        if not content:
            return 0.0
        score = 0.0
        # 无占位符
        if not _PLACEHOLDER_RE.search(content):
            score += 0.4
        # 无连续 3+ 空行
        if not _BLANK_LINES_RE.search(content):
            score += 0.3
        # 无尾部空白(rstrip 后与原文比较)
        if content == content.rstrip():
            score += 0.3
        return self._clamp(score)

# ---------------------------------------------------------------------------
# 6. LLMEvaluator
# ---------------------------------------------------------------------------

class LLMEvaluator(BaseEvaluator):
    """LLM 综合评估器(可选,默认关闭)。

    调用 LLM 对内容做综合评估,评估维度: 完整性/逻辑性/准确性。

    依赖:
      - 构造时注入 LLM 客户端(任何带 chat(LLMRequest)->LLMResponse 接口的对象,
        如 LLMRouter)
      - 未注入 LLM 时返回 1.0(不评估,不拖累总分)

    超时/异常策略:
      - 评估器自身不感知超时,由 manager 的 asyncio.wait_for 控制
      - manager 超时后该评估器返回 1.0(不因慢评估惩罚)
      - LLM 调用异常时返回 1.0(不阻塞其他评估器)
    """

    def __init__(self, llm: Any = None) -> None:
        """初始化 LLM 评估器。

        Args:
            llm: LLM 客户端(需有 chat(request) -> response 接口,如 LLMRouter)。
                 为 None 时 evaluate 返回 1.0(不评估)。
        """
        self._llm = llm

    @property
    def name(self) -> str:
        return "llm"

    def evaluate(
        self,
        content: str,
        context: dict[str, Any],
        config: ReflectionConfig,
    ) -> float:
        if self._llm is None:
            # 未注入 LLM,不评估
            return 1.0
        if not content:
            return 0.0
        # 延迟导入,避免顶层循环依赖
        from fnixagent.core.llm.base import LLMRequest
        from fnixagent.core.types import Message, MessageRole

        goal = ""
        if context:
            goal = str(context.get("goal", ""))

        system_msg = Message(
            role=MessageRole.SYSTEM,
            content=(
                "你是内容质量评估器。请对以下内容从三个维度评分:\n"
                "1. 完整性: 是否完整回答了目标\n"
                "2. 逻辑性: 论述是否连贯、逻辑是否合理\n"
                "3. 准确性: 信息是否准确、有无明显错误\n\n"
                '输出 JSON: {"score": 0.0~1.0, "reason": "..."}'
            ),
        )
        user_msg = Message(
            role=MessageRole.USER,
            content=(
                f"目标: {goal}\n\n待评估内容:\n{content[:2000]}"  # 截断防超长 prompt
            ),
        )
        request = LLMRequest(
            messages=[system_msg, user_msg],
            temperature=0.2,  # 评估用低温度,提升确定性
        )
        try:
            response = self._llm.chat(request)
        except Exception:
            # LLM 调用失败:返回 1.0(不拖累总分,与超时策略一致)
            return 1.0
        if response is None:
            return 1.0
        raw = getattr(response, "content", "") or ""
        return self._parse_score(raw)

    @staticmethod
    def _parse_score(raw: str) -> float:
        """从 LLM 输出解析 score(0~1)。

        解析失败返回 1.0(不拖累总分,与超时策略一致)。
        """
        if not raw:
            return 1.0
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return 1.0
        try:
            data = json.loads(match.group())
        except (json.JSONDecodeError, ValueError):
            return 1.0
        if not isinstance(data, dict):
            return 1.0
        try:
            score = float(data.get("score", 1.0))
        except (TypeError, ValueError):
            return 1.0
        # clamp 到 [0, 1]
        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return score
