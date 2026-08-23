"""诚实边界设计(P2-11)。

顶级 Agent 必须明确知道"自己能做什么、不能做什么",对越界任务诚实告知而非胡编。
本模块实现能力边界声明 + 意图评估 + 响应策略:

  - BoundaryDecision:      WITHIN(范围内)/PARTIAL(部分可做)/OUT_OF_SCOPE(越界)/NEEDS_HUMAN(需人工)
  - ResponseStrategy:      REFUSE_POLITELY(礼貌拒绝)/DEGRADE_AND_EXPLAIN(降级解释)
                           /TRANSFER_TO_HUMAN(转人工)/SUGGEST_ALTERNATIVE(建议替代方案)
  - CapabilityDeclaration: 单个能力的声明(支持/不支持/已知限制)
  - IntentAssessment:      对用户请求的评估结果(意图/决策/置信度/建议响应策略)
  - CapabilityBoundary:    边界管理器(declare/assess_intent/generate_response/...)

设计原则:
  - L1 Office 顶级专家 + L2 办公生态 + 越界诚实告知(不冒充全能)
  - 默认 conservative:不确定时倾向 PARTIAL 或 NEEDS_HUMAN,不强行作答
  - 全部决策可解释(每条 IntentAssessment 携带 reason)
  - 落库审计(assess_intent 与 generate_response 调用都应被 audit 记录)

与外部模块关系:
  - 入口:AgentRunner/Lifecycle 在收到用户请求后,先调 assess_intent 评估边界
  - 工具检索:assess_intent 接收 available_tools 列表,判断是否在能力范围内
  - 输出:generate_response 根据 assessment 生成给用户的回复文本
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class BoundaryDecision(str, Enum):
    """边界评估决策。"""

    WITHIN = "within"  # 完全在能力范围内
    PARTIAL = "partial"  # 部分可做(某些子任务越界)
    OUT_OF_SCOPE = "out_of_scope"  # 完全越界(不在能力范围)
    NEEDS_HUMAN = "needs_human"  # 需要人工介入(敏感/低置信度)


class ResponseStrategy(str, Enum):
    """响应策略(对应不同决策)。"""

    REFUSE_POLITELY = "refuse_politely"  # 礼貌拒绝(OUT_OF_SCOPE)
    DEGRADE_AND_EXPLAIN = "degrade_and_explain"  # 降级并解释(PARTIAL)
    TRANSFER_TO_HUMAN = "transfer_to_human"  # 转人工(NEEDS_HUMAN)
    SUGGEST_ALTERNATIVE = "suggest_alternative"  # 建议替代方案(OUT_OF_SCOPE 但有替代)
    DIRECT_ANSWER = "direct_answer"  # 直接作答(WITHIN)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class CapabilityDeclaration:
    """能力声明。

    每个声明描述一类能力(如 "word_editing" / "email_sending" / "knowledge_search")。

    字段:
      - name:                  能力名(唯一标识)
      - supported_intents:     支持的意图关键词列表(用于 assess_intent 匹配)
      - unsupported_intents:   明确不支持的意图(优先级高于 supported)
      - max_input_tokens:      单次输入 token 上限
      - supported_languages:   支持的语言
      - supported_file_types:  支持的文件类型
      - known_limitations:     已知限制(给用户看的说明)
      - sensitivity:           敏感度(low/medium/high,影响 NEEDS_HUMAN 判定)
      - fallback_capability:   越界时建议的替代能力名(可选)
    """

    name: str
    supported_intents: list[str] = field(default_factory=list)
    unsupported_intents: list[str] = field(default_factory=list)
    max_input_tokens: int = 8192
    supported_languages: list[str] = field(default_factory=lambda: ["zh", "en"])
    supported_file_types: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    sensitivity: str = "low"
    fallback_capability: str | None = None


@dataclass
class IntentAssessment:
    """意图评估结果。

    由 CapabilityBoundary.assess_intent 返回,供 generate_response 使用。
    """

    intent: str = ""  # 识别出的意图(如 "word_editing")
    decision: BoundaryDecision = BoundaryDecision.WITHIN
    confidence: float = 1.0  # 0.0-1.0
    matched_capability: CapabilityDeclaration | None = None
    reason: str = ""  # 决策原因(可解释)
    suggested_strategy: ResponseStrategy = ResponseStrategy.DIRECT_ANSWER
    missing_sub_capabilities: list[str] = field(default_factory=list)  # PARTIAL 时列出缺失子能力
    user_facing_explanation: str = ""  # 给用户看的解释(可中文)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class BoundaryError(Exception):
    """边界评估异常。"""


class CapabilityNotFoundError(BoundaryError):
    """能力声明不存在。"""


# ---------------------------------------------------------------------------
# 默认能力声明(fnixagent 顶级 Office + 办公生态定位)
# ---------------------------------------------------------------------------


def _default_l1_office_capabilities() -> list[CapabilityDeclaration]:
    """L1 Office 顶级专家层默认能力声明。"""
    return [
        CapabilityDeclaration(
            name="word_editing",
            supported_intents=["word", "docx", "文档", "段落", "样式", "目录", "页眉页脚"],
            unsupported_intents=["加密破解", "宏病毒", "vba 注入"],
            supported_file_types=[".docx", ".doc", ".md", ".txt"],
            known_limitations=[
                "不支持 .doc 旧版二进制格式的复杂排版",
                "宏(VBA)编辑仅支持只读解析,不支持写入",
            ],
            sensitivity="low",
        ),
        CapabilityDeclaration(
            name="excel_processing",
            supported_intents=["excel", "xlsx", "表格", "公式", "图表", "数据透视", "vlookup"],
            unsupported_intents=["实时股票行情", "联网数据库直连"],
            supported_file_types=[".xlsx", ".xls", ".csv"],
            known_limitations=[
                "不支持 .xls 旧版格式的复杂图表",
                "单表数据量上限 100 万行(超出建议分片)",
            ],
            sensitivity="low",
        ),
        CapabilityDeclaration(
            name="ppt_generation",
            supported_intents=["ppt", "pptx", "幻灯片", "演示", "讲稿"],
            unsupported_intents=["动画复杂路径", "3D 模型渲染"],
            supported_file_types=[".pptx"],
            known_limitations=[
                "动画效果仅支持基础进入/退出",
                "不支持嵌入 3D 模型",
            ],
            sensitivity="low",
        ),
        CapabilityDeclaration(
            name="pdf_operation",
            supported_intents=["pdf", "合并", "拆分", "水印", "提取", "转换"],
            unsupported_intents=["破解密码保护", "篡改签名文档"],
            supported_file_types=[".pdf"],
            known_limitations=[
                "不支持密码保护 PDF 的解密",
                "数字签名 PDF 仅支持验证,不支持篡改",
            ],
            sensitivity="medium",
        ),
        CapabilityDeclaration(
            name="knowledge_search",
            supported_intents=["搜索", "检索", "查询", "论文", "资料", "文献"],
            unsupported_intents=["实时新闻", "股票行情", "天气"],
            known_limitations=[
                "搜索结果依赖本地知识库,无法访问付费数据库",
                "实时性数据(新闻/天气/股票)不在能力范围",
            ],
            sensitivity="low",
        ),
    ]


def _default_l2_ecosystem_capabilities() -> list[CapabilityDeclaration]:
    """L2 办公生态层默认能力声明。"""
    return [
        CapabilityDeclaration(
            name="email_sending",
            supported_intents=["邮件", "email", "发送", "抄送", "群发"],
            unsupported_intents=["匿名邮件", "钓鱼邮件", "批量垃圾邮件"],
            known_limitations=[
                "群发单次上限 100 人(防滥用)",
                "附件大小上限 25MB",
            ],
            sensitivity="high",
            fallback_capability="email_drafting",
        ),
        CapabilityDeclaration(
            name="email_drafting",
            supported_intents=["起草邮件", "写邮件", "邮件草稿"],
            unsupported_intents=[],
            known_limitations=["仅起草,不直接发送,需用户确认后发送"],
            sensitivity="low",
        ),
        CapabilityDeclaration(
            name="calendar_management",
            supported_intents=["日程", "会议", "提醒", "日历", "预约"],
            unsupported_intents=["跨组织日程协调"],
            known_limitations=[
                "跨组织日程协调需双方授权",
                "不支持非办公日历(如节假日融合)",
            ],
            sensitivity="medium",
        ),
        CapabilityDeclaration(
            name="im_messaging",
            supported_intents=["飞书", "钉钉", "企业微信", "im", "消息"],
            unsupported_intents=["个人微信", "个人 QQ"],
            known_limitations=[
                "仅支持企业 IM(飞书/钉钉/企业微信)",
                "不支持个人社交账号消息",
            ],
            sensitivity="high",
        ),
    ]


# ---------------------------------------------------------------------------
# 明确越界的意图(任何能力都不支持)
# ---------------------------------------------------------------------------

_OUT_OF_SCOPE_INTENTS: list[str] = [
    # 实时性数据
    "实时新闻",
    "股票行情",
    "天气预报",
    "航班动态",
    "汇率实时",
    # 个人社交
    "个人微信",
    "个人 QQ",
    "微博发帖",
    "朋友圈",
    # 违法违规
    "破解密码",
    "网络攻击",
    "钓鱼",
    "木马",
    "爬取个人隐私",
    # 医疗法律专业建议
    "医疗诊断",
    "法律咨询",
    "投资建议",
    # 物理世界操作
    "控制硬件",
    "打电话",
    "发短信",
]

# ---------------------------------------------------------------------------
# CapabilityBoundary
# ---------------------------------------------------------------------------


class CapabilityBoundary:
    """能力边界管理器。

    用法:
        boundary = CapabilityBoundary()
        # 默认已注册 L1 Office + L2 办公生态能力声明

        # 评估用户请求
        assessment = boundary.assess_intent(
            user_request="帮我把这份 Word 转 PDF",
            available_tools=["word_to_pdf", "search_paper"],
        )
        # assessment.decision == BoundaryDecision.WITHIN

        # 生成回复
        response = boundary.generate_response(assessment, user_request)
        print(response)
    """

    def __init__(
        self,
        declarations: list[CapabilityDeclaration] | None = None,
        conservative_threshold: float = 0.5,
    ) -> None:
        """
        Args:
            declarations: 能力声明列表(None 表示用默认 L1+L2 声明)
            conservative_threshold: 置信度阈值(低于此值倾向 NEEDS_HUMAN)
        """
        if declarations is None:
            declarations = _default_l1_office_capabilities() + _default_l2_ecosystem_capabilities()
        self._declarations: dict[str, CapabilityDeclaration] = {d.name: d for d in declarations}
        self._conservative_threshold = conservative_threshold
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 声明管理
    # ------------------------------------------------------------------

    def declare(self, declaration: CapabilityDeclaration) -> int:
        """添加或更新能力声明。

        Returns:
            当前能力声明总数
        """
        with self._lock:
            self._declarations[declaration.name] = declaration
            return len(self._declarations)

    def declare_from_registry(
        self,
        tool_registry: Any,
        layer_filter: str | None = None,
    ) -> int:
        """从 ToolRegistry 自动生成能力声明(按 category 分组)。

        Args:
            tool_registry: ToolRegistry 实例(需实现 list_tools)
            layer_filter: 仅包含指定层级的工具(None 全部)

        Returns:
            新增能力声明数
        """

        with self._lock:
            tools = tool_registry.list_tools()
            # 按 category 分组
            by_category: dict[str, list[Any]] = {}
            for tool in tools:
                if layer_filter is not None:
                    layer = getattr(tool, "layer", None)
                    if layer is None or layer.value != layer_filter:
                        continue
                cat = tool.category or "general"
                by_category.setdefault(cat, []).append(tool)
            added = 0
            for cat, cat_tools in by_category.items():
                # 已存在的声明不覆盖
                if cat in self._declarations:
                    continue
                supported_intents = [t.name for t in cat_tools]
                decl = CapabilityDeclaration(
                    name=cat,
                    supported_intents=supported_intents,
                    known_limitations=[
                        f"包含 {len(cat_tools)} 个工具:{', '.join(supported_intents[:5])}{'...' if len(supported_intents) > 5 else ''}",
                    ],
                )
                self._declarations[cat] = decl
                added += 1
            return added

    def get_declaration(self, name: str) -> CapabilityDeclaration | None:
        """按名获取能力声明。"""
        with self._lock:
            return self._declarations.get(name)

    def list_declarations(self) -> list[CapabilityDeclaration]:
        """列出全部能力声明。"""
        with self._lock:
            return list(self._declarations.values())

    # ------------------------------------------------------------------
    # 意图评估
    # ------------------------------------------------------------------

    def assess_intent(
        self,
        user_request: str,
        available_tools: list[str] | None = None,
    ) -> IntentAssessment:
        """评估用户请求是否在能力范围内。

        决策流程(每步命中即返回,后续步骤不再执行):
          1. 越界意图检测(命中 _OUT_OF_SCOPE_INTENTS → OUT_OF_SCOPE)
          2. 不支持意图检测(命中某声明的 unsupported_intents → OUT_OF_SCOPE)
          3. 支持意图匹配(命中某声明的 supported_intents → WITHIN/PARTIAL)
          4. 敏感度检查(high 敏感度 + 无可用工具 → NEEDS_HUMAN)
          5. 置信度评估(无任何匹配 → 低置信度 → NEEDS_HUMAN)

        Args:
            user_request: 用户原始请求文本
            available_tools: 当前可用的工具名列表(影响 PARTIAL 判定)

        Returns:
            IntentAssessment(包含决策/置信度/建议响应策略/给用户的解释)

        Raises:
            ValueError: user_request 为 None
        """
        if not user_request:
            return IntentAssessment(
                decision=BoundaryDecision.NEEDS_HUMAN,
                confidence=0.0,
                reason="空请求",
                suggested_strategy=ResponseStrategy.TRANSFER_TO_HUMAN,
                user_facing_explanation="您似乎没有提出具体问题,请补充您的需求。",
            )

        request_lower = user_request.lower()
        available_tools = available_tools or []

        with self._lock:
            declarations = list(self._declarations.values())

        # 1. 越界意图检测(最高优先级)
        for oob_intent in _OUT_OF_SCOPE_INTENTS:
            if oob_intent in user_request or oob_intent in request_lower:
                # 检查是否有 fallback_capability
                fallback = self._find_fallback(oob_intent, declarations)
                strategy = (
                    ResponseStrategy.SUGGEST_ALTERNATIVE
                    if fallback
                    else ResponseStrategy.REFUSE_POLITELY
                )
                return IntentAssessment(
                    intent=oob_intent,
                    decision=BoundaryDecision.OUT_OF_SCOPE,
                    confidence=0.95,
                    reason=f"命中越界意图:{oob_intent}",
                    suggested_strategy=strategy,
                    user_facing_explanation=(
                        f"'{oob_intent}' 不在我的能力范围内。"
                        + (f" 您可以尝试:{fallback}" if fallback else "")
                    ),
                )

        # 2. 不支持意图检测
        for decl in declarations:
            for unsupported in decl.unsupported_intents:
                if unsupported in user_request or unsupported in request_lower:
                    fallback = decl.fallback_capability
                    strategy = (
                        ResponseStrategy.SUGGEST_ALTERNATIVE
                        if fallback
                        else ResponseStrategy.REFUSE_POLITELY
                    )
                    return IntentAssessment(
                        intent=decl.name,
                        decision=BoundaryDecision.OUT_OF_SCOPE,
                        confidence=0.9,
                        matched_capability=decl,
                        reason=f"能力 {decl.name} 不支持:{unsupported}",
                        suggested_strategy=strategy,
                        user_facing_explanation=(
                            f"'{decl.name}' 能力明确不支持 '{unsupported}'。"
                            + (f" 建议:{fallback}" if fallback else "")
                        ),
                    )

        # 3. 支持意图匹配
        best_match: CapabilityDeclaration | None = None
        best_score = 0.0
        for decl in declarations:
            score = self._score_match(request_lower, decl)
            if score > best_score:
                best_score = score
                best_match = decl

        if best_match is None or best_score < 0.1:
            # 无任何匹配
            return IntentAssessment(
                decision=BoundaryDecision.NEEDS_HUMAN,
                confidence=0.2,
                reason="无任何能力声明匹配用户请求",
                suggested_strategy=ResponseStrategy.TRANSFER_TO_HUMAN,
                user_facing_explanation=(
                    "我不太确定如何处理您的请求。"
                    "请告诉我更多细节,或尝试以下能力:" + self._capability_summary(declarations)
                ),
            )

        # 4. 敏感度检查
        if best_match.sensitivity == "high" and not available_tools:
            return IntentAssessment(
                intent=best_match.name,
                decision=BoundaryDecision.NEEDS_HUMAN,
                confidence=0.6,
                matched_capability=best_match,
                reason=f"高敏感能力 {best_match.name} 但无可用工具,需人工确认",
                suggested_strategy=ResponseStrategy.TRANSFER_TO_HUMAN,
                user_facing_explanation=(
                    f"您的请求涉及高敏感操作({best_match.name}),需要人工确认后才能执行。"
                ),
            )

        # 5. PARTIAL vs WITHIN 判定
        # 检查请求是否包含多个子任务,其中某些可能越界
        sub_intents = self._extract_sub_intents(user_request, declarations)
        missing = [
            s for s in sub_intents if not any(s in d.supported_intents for d in declarations)
        ]
        if missing:
            return IntentAssessment(
                intent=best_match.name,
                decision=BoundaryDecision.PARTIAL,
                confidence=best_score,
                matched_capability=best_match,
                reason=f"部分子任务无能力声明:{missing}",
                suggested_strategy=ResponseStrategy.DEGRADE_AND_EXPLAIN,
                missing_sub_capabilities=missing,
                user_facing_explanation=(
                    f"我可以处理您请求中关于 {best_match.name} 的部分,"
                    f"但以下子任务超出我的能力:{', '.join(missing)}。"
                    "我会对能做的部分给出结果,其余部分需要您自行处理。"
                ),
            )

        # 6. 置信度阈值检查
        if best_score < self._conservative_threshold:
            return IntentAssessment(
                intent=best_match.name,
                decision=BoundaryDecision.NEEDS_HUMAN,
                confidence=best_score,
                matched_capability=best_match,
                reason=f"置信度 {best_score:.2f} 低于阈值 {self._conservative_threshold}",
                suggested_strategy=ResponseStrategy.TRANSFER_TO_HUMAN,
                user_facing_explanation=(
                    "我对您的请求理解不够明确,建议提供更多细节或咨询人工支持。"
                ),
            )

        # WITHIN
        return IntentAssessment(
            intent=best_match.name,
            decision=BoundaryDecision.WITHIN,
            confidence=best_score,
            matched_capability=best_match,
            reason=f"匹配能力 {best_match.name},置信度 {best_score:.2f}",
            suggested_strategy=ResponseStrategy.DIRECT_ANSWER,
            user_facing_explanation="",
        )

    # ------------------------------------------------------------------
    # 响应生成
    # ------------------------------------------------------------------

    def generate_response(
        self,
        assessment: IntentAssessment,
        user_request: str = "",
    ) -> str:
        """根据评估结果生成给用户的回复文本。

        Args:
            assessment: assess_intent 的返回值
            user_request: 用户原始请求(用于个性化回复)

        Returns:
            回复文本(可中文)
        """
        strategy = assessment.suggested_strategy
        if strategy == ResponseStrategy.DIRECT_ANSWER:
            # WITHIN:不生成拒绝文本(由后续 LLM/工具直接处理)
            return ""
        elif strategy == ResponseStrategy.REFUSE_POLITELY:
            return self.refuse_politely(user_request, assessment.reason)
        elif strategy == ResponseStrategy.DEGRADE_AND_EXPLAIN:
            return self._degrade_and_explain(assessment)
        elif strategy == ResponseStrategy.TRANSFER_TO_HUMAN:
            return self._transfer_to_human(assessment)
        elif strategy == ResponseStrategy.SUGGEST_ALTERNATIVE:
            return self.suggest_alternative(
                user_request,
                [d for d in self._declarations.values()],
            )
        return ""

    def refuse_politely(self, user_request: str, reason: str) -> str:
        """礼貌拒绝模板。"""
        return (
            "抱歉,您的请求超出了我的能力范围。\n\n"
            f"原因:{reason}\n\n"
            "我专注于办公场景(Word/Excel/PPT/PDF 等文档处理,"
            "以及邮件/日程/IM 等办公生态操作)。\n"
            "如需其他类型的帮助,建议咨询对应领域的专业工具或人工支持。"
        )

    def suggest_alternative(
        self,
        user_request: str,
        available_capabilities: list[CapabilityDeclaration],
    ) -> str:
        """建议替代方案模板。"""
        if not available_capabilities:
            return self.refuse_politely(user_request, "无可用替代方案")
        cap_names = [d.name for d in available_capabilities[:5]]
        return (
            "抱歉,您的请求不在我的能力范围内,但我可以建议以下替代方案:\n\n"
            + "\n".join(f"  - {name}" for name in cap_names)
            + "\n\n您可以尝试用上述能力重新描述您的需求。"
        )

    # ------------------------------------------------------------------
    # 报告
    # ------------------------------------------------------------------

    def boundary_report(self) -> dict[str, Any]:
        """生成边界报告(供 UI/调试展示)。"""
        with self._lock:
            declarations = list(self._declarations.values())
        return {
            "total_capabilities": len(declarations),
            "capabilities": [d.__dict__ for d in declarations],
            "out_of_scope_intents": list(_OUT_OF_SCOPE_INTENTS),
            "conservative_threshold": self._conservative_threshold,
        }

    def known_limitations_summary(self) -> str:
        """生成已知限制摘要(给用户看的"诚实告知")。"""
        with self._lock:
            declarations = list(self._declarations.values())
        lines = ["我的能力边界(诚实告知):", ""]
        for d in declarations:
            lines.append(f"【{d.name}】")
            if d.known_limitations:
                for lim in d.known_limitations:
                    lines.append(f"  - 限制:{lim}")
            if d.unsupported_intents:
                lines.append(f"  - 不支持:{', '.join(d.unsupported_intents)}")
            lines.append("")
        lines.append("【明确越界】")
        for oob in _OUT_OF_SCOPE_INTENTS:
            lines.append(f"  - {oob}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _score_match(
        self,
        request_lower: str,
        decl: CapabilityDeclaration,
    ) -> float:
        """计算请求与能力声明的匹配分数(0.0-1.0)。

        匹配算法:
          - 遍历声明的 supported_intents,统计在请求文本中出现的数量
          - 分数 = sqrt(hits / total) * 1.5,用 sqrt 缓和(单命中也给较高分)
          - 上限 1.0
        """
        if not decl.supported_intents:
            return 0.0
        hits = sum(1 for intent in decl.supported_intents if intent.lower() in request_lower)
        if hits == 0:
            return 0.0
        # 命中数 / 总意图数,但用 sqrt 缓和(单命中也给较高分)
        import math

        return min(math.sqrt(hits / max(len(decl.supported_intents), 1)) * 1.5, 1.0)

    def _find_fallback(
        self,
        intent: str,
        declarations: list[CapabilityDeclaration],
    ) -> str | None:
        """为越界意图寻找 fallback 能力(简化实现:返回第一个 fallback_capability)。"""
        for d in declarations:
            if d.fallback_capability:
                return d.fallback_capability
        return None

    def _extract_sub_intents(
        self,
        user_request: str,
        declarations: list[CapabilityDeclaration],
    ) -> list[str]:
        """从用户请求中提取子任务关键词(用于 PARTIAL 判定)。

        简化实现:用顿号/逗号/分号/换行分割,提取每段的关键词。
        """
        # 分割符:中文标点 + 换行
        parts = re.split(r"[,，;；\n。]", user_request)
        sub_intents: list[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 每段提取首个名词关键词(简化:取前 4 字)
            if len(part) >= 2:
                sub_intents.append(part[:4])
        return sub_intents

    def _capability_summary(
        self,
        declarations: list[CapabilityDeclaration],
    ) -> str:
        """生成能力摘要(给 NEEDS_HUMAN 时的提示)。"""
        names = [d.name for d in declarations[:5]]
        return ", ".join(names)

    def _degrade_and_explain(self, assessment: IntentAssessment) -> str:
        """降级并解释模板。"""
        missing = (
            ", ".join(assessment.missing_sub_capabilities)
            if assessment.missing_sub_capabilities
            else "部分子任务"
        )
        return (
            f"我可以处理您请求中关于 {assessment.intent} 的部分,\n"
            f"但以下子任务超出我的能力:{missing}。\n\n"
            "我会对能做的部分给出结果,其余部分需要您自行处理或咨询人工支持。"
        )

    def _transfer_to_human(self, assessment: IntentAssessment) -> str:
        """转人工模板。"""
        return (
            "我需要将您的请求转给人工处理。\n\n"
            f"原因:{assessment.reason}\n"
            f"置信度:{assessment.confidence:.2f}\n\n"
            "请稍候,人工客服将为您服务。"
        )
