"""
Retrieval Gate - 智能检索门控。

避免不必要的检索开销，智能判断是否需要检索记忆。

检索条件（满足任一即检索）：
1. 查询包含时间/人物/地点等实体词
2. 查询包含"记得"/"之前"/"上次"等记忆指示词
3. 上下文缺少相关实体信息
4. 查询复杂度 > 阈值

不检索条件：
1. 简单问候/闲聊
2. 纯计算/格式化任务
3. 上下文中已有充分信息
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievalDecision:
    """检索决策结果。"""

    should_retrieve: bool
    reason: str
    confidence: float = 0.0  # 0.0 - 1.0
    suggested_categories: list[str] = field(default_factory=list)


class RetrievalGate:
    """智能检索门控。

    判断是否需要检索记忆，避免不必要的开销。
    """

    # 记忆指示词（中文）
    MEMORY_INDICATORS_ZH = [
        "记得",
        "之前",
        "上次",
        "以前",
        "过去",
        "我的",
        "你的",
        "他的",
        "她的",
        "喜欢",
        "不喜欢",
        "偏好",
        "习惯",
        "名字",
        "地址",
        "电话",
        "邮箱",
        "生日",
        "年龄",
        "工作",
        "公司",
    ]

    # 记忆指示词（英文）
    MEMORY_INDICATORS_EN = [
        "remember",
        "before",
        "last time",
        "previously",
        "my",
        "your",
        "his",
        "her",
        "like",
        "dislike",
        "prefer",
        "usually",
        "name",
        "address",
        "phone",
        "email",
        "birthday",
        "age",
        "work",
        "company",
    ]

    # 简单任务模式（不需要检索）
    SIMPLE_TASK_PATTERNS = [
        r"^(你好|hello|hi|hey|嗨|哈喽)\s*[!！。.？?]*$",
        r"^(谢谢|thanks|thank you|thx)\s*[!！。.？?]*$",
        r"^(再见|bye|goodbye|拜拜)\s*[!！。.？?]*$",
        r"^\d+\s*[\+\-\*\/]\s*\d+\s*[=是多少]*\s*[?？]*$",  # 简单计算
        r"^(今天|现在|当前).*(几点|日期|星期|天气)",  # 时间查询
    ]

    # 实体词模式（需要检索）
    ENTITY_PATTERNS = [
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}",  # 日期
        r"\d{1,2}:\d{2}",  # 时间
        r"[\w.-]+@[\w.-]+\.\w+",  # 邮箱
        r"1[3-9]\d{9}",  # 手机号
        r"\d{17}[\dXx]",  # 身份证号
    ]

    def __init__(self, config: dict[str, Any] = None):
        """初始化门控。

        Args:
            config: 配置参数
                - complexity_threshold: 复杂度阈值 (默认 0.5)
                - enable_entity_detection: 是否启用实体检测 (默认 True)
                - enable_context_check: 是否启用上下文检查 (默认 True)
        """
        self.config = config or {}
        self.complexity_threshold = self.config.get("complexity_threshold", 0.5)
        self.enable_entity_detection = self.config.get("enable_entity_detection", True)
        self.enable_context_check = self.config.get("enable_context_check", True)

    def should_retrieve(
        self,
        query: str,
        context: dict[str, Any] = None,
    ) -> RetrievalDecision:
        """判断是否需要检索。

        Args:
            query: 用户查询
            context: 当前上下文 (包含 history, entities 等)

        Returns:
            RetrievalDecision: 检索决策
        """
        context = context or {}

        # 1. 快速路径：简单任务不检索
        if self._is_simple_task(query):
            return RetrievalDecision(
                should_retrieve=False,
                reason="simple_task",
                confidence=0.9,
            )

        # 2. 记忆指示词检测
        indicator_result = self._check_memory_indicators(query)
        if indicator_result.should_retrieve:
            return indicator_result

        # 3. 实体词检测
        if self.enable_entity_detection:
            entity_result = self._check_entity_patterns(query)
            if entity_result.should_retrieve:
                return entity_result

        # 4. 上下文完整性检查
        if self.enable_context_check:
            context_result = self._check_context_sufficiency(query, context)
            if context_result.should_retrieve:
                return context_result

        # 5. 复杂度评估
        complexity = self._estimate_complexity(query)
        if complexity > self.complexity_threshold:
            return RetrievalDecision(
                should_retrieve=True,
                reason="high_complexity",
                confidence=complexity,
            )

        # 默认不检索
        return RetrievalDecision(
            should_retrieve=False,
            reason="default_skip",
            confidence=0.5,
        )

    def _is_simple_task(self, query: str) -> bool:
        """判断是否为简单任务。"""
        query_lower = query.strip().lower()

        for pattern in self.SIMPLE_TASK_PATTERNS:
            if re.match(pattern, query_lower, re.IGNORECASE):
                return True

        # 短查询（< 5 字符）且无问号
        if len(query.strip()) < 5 and "?" not in query and "？" not in query:
            return True

        return False

    def _check_memory_indicators(self, query: str) -> RetrievalDecision:
        """检查记忆指示词。"""
        query_lower = query.lower()

        # 中文指示词
        zh_matches = [word for word in self.MEMORY_INDICATORS_ZH if word in query]

        # 英文指示词
        en_matches = [word for word in self.MEMORY_INDICATORS_EN if word in query_lower]

        matches = zh_matches + en_matches

        if matches:
            return RetrievalDecision(
                should_retrieve=True,
                reason=f"memory_indicators: {', '.join(matches[:3])}",
                confidence=0.8,
                suggested_categories=["fact", "preference", "event"],
            )

        return RetrievalDecision(
            should_retrieve=False,
            reason="no_memory_indicators",
            confidence=0.5,
        )

    def _check_entity_patterns(self, query: str) -> RetrievalDecision:
        """检查实体词模式。"""
        matches = []

        for pattern in self.ENTITY_PATTERNS:
            if re.search(pattern, query):
                matches.append(pattern)

        if matches:
            return RetrievalDecision(
                should_retrieve=True,
                reason="entity_detected",
                confidence=0.7,
                suggested_categories=["entity", "fact"],
            )

        return RetrievalDecision(
            should_retrieve=False,
            reason="no_entity",
            confidence=0.5,
        )

    def _check_context_sufficiency(
        self,
        query: str,
        context: dict[str, Any],
    ) -> RetrievalDecision:
        """检查上下文是否充分。"""
        # 检查是否有相关实体
        entities = context.get("entities", {})

        # 提取查询中的关键词
        keywords = self._extract_keywords(query)

        # 检查实体是否覆盖关键词
        covered = 0
        for keyword in keywords:
            if keyword in entities:
                covered += 1

        # 如果关键词覆盖率 < 50%，需要检索
        if keywords and covered / len(keywords) < 0.5:
            return RetrievalDecision(
                should_retrieve=True,
                reason="insufficient_context",
                confidence=0.6,
            )

        return RetrievalDecision(
            should_retrieve=False,
            reason="context_sufficient",
            confidence=0.5,
        )

    def _extract_keywords(self, query: str) -> list[str]:
        """提取查询关键词。"""
        # 简单实现：按空格和标点分割
        words = re.split(r"[\s,，。！？!?]+", query)

        # 过滤短词
        keywords = [w for w in words if len(w) >= 2]

        return keywords[:10]  # 最多 10 个关键词

    def _estimate_complexity(self, query: str) -> float:
        """估计查询复杂度。"""
        score = 0.0

        # 长度因素
        if len(query) > 50:
            score += 0.2
        if len(query) > 100:
            score += 0.2

        # 句子数量
        sentences = len(re.split(r"[。！？.!?]", query))
        if sentences > 2:
            score += 0.2

        # 问号数量（多问题）
        questions = query.count("？") + query.count("?")
        if questions > 1:
            score += 0.2

        # 条件词
        conditionals = ["如果", "假如", "when", "if", "unless"]
        if any(word in query.lower() for word in conditionals):
            score += 0.2

        return min(score, 1.0)
