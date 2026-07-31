"""
LLM 驱动的知识合成引擎 — 将采集信息转化为可执行的升级方案

设计参考:
  - GPT-Researcher: 多Agent分阶段研究, 生成结构化报告
  - AI-Researcher: 智能文献评估, 自动实验设计
  - PaperOrchestra: 多Agent专业分工, 迭代改进

工作流程:
  采集数据 → LLM 提取关键信息 → 语义去重 → 分类归档
  → LLM 对比当前系统差距 → 生成升级建议 → 优先级排序
  → 注入 KTG 知识拓扑 → 触发 STP 技能更新 → 驱动 MFP 飞轮
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .continuous_collector import SourceCategory, SourceItem

logger = logging.getLogger(__name__)


# ============================================================
# 提取结果模型
# ============================================================


class InsightType(str, Enum):
    """洞察类型"""

    NEW_FRAMEWORK = "new_framework"  # 新框架/工具
    NEW_TECHNIQUE = "new_technique"  # 新技术/算法
    BEST_PRACTICE = "best_practice"  # 最佳实践
    ARCHITECTURE_PATTERN = "architecture_pattern"  # 架构模式
    RESEARCH_BREAKTHROUGH = "research_breakthrough"  # 研究突破
    BENCHMARK_RESULT = "benchmark_result"  # 基准测试结果
    PROTOCOL_UPDATE = "protocol_update"  # 协议更新
    SECURITY_ADVISORY = "security_advisory"  # 安全公告
    DEPRECATION = "deprecation"  # 废弃通知
    COMMUNITY_TREND = "community_trend"  # 社区趋势


@dataclass
class ExtractedInsight:
    """LLM 提取的洞察"""

    insight_id: str
    insight_type: InsightType
    title: str
    description: str
    source_items: list[str]  # 引用源 item_id
    confidence: float  # 置信度 0-1
    impact_on_fnixagent: str  # 对 FnixAgent 的影响
    upgrade_priority: str  # critical/high/medium/low
    suggested_action: str  # 建议行动
    related_modules: list[str]  # 受影响模块
    code_snippet: str = ""  # 如有代码示例
    extracted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class SynthesisReport:
    """一次合成报告"""

    report_id: str
    generated_at: str
    total_sources: int
    total_insights: int
    critical_insights: list[ExtractedInsight]
    high_insights: list[ExtractedInsight]
    medium_insights: list[ExtractedInsight]
    executive_summary: str
    upgrade_roadmap: str
    ktg_injections: list[dict]  # 注入 KTG 的新知识节点

    def count_insights_by_urgency(self, urgency: str) -> int:
        """按紧急程度统计洞察数量"""
        if urgency == "critical":
            return len(self.critical_insights)
        elif urgency == "high":
            return len(self.high_insights)
        elif urgency == "medium":
            return len(self.medium_insights)
        return 0

    def save_to_file(self, output_dir: str | None = None) -> str:
        """将报告保存到文件"""
        from pathlib import Path

        dir_path = Path(output_dir) if output_dir else Path("data/synthesis")
        dir_path.mkdir(parents=True, exist_ok=True)

        path = dir_path / f"{self.report_id}.json"
        data = {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "total_sources": self.total_sources,
            "total_insights": self.total_insights,
            "executive_summary": self.executive_summary,
            "upgrade_roadmap": self.upgrade_roadmap,
            "critical_insights": [
                {
                    "insight_id": i.insight_id,
                    "title": i.title,
                    "description": i.description,
                    "upgrade_priority": i.upgrade_priority,
                    "suggested_action": i.suggested_action,
                    "related_modules": i.related_modules,
                }
                for i in self.critical_insights
            ],
            "high_insights": [
                {
                    "insight_id": i.insight_id,
                    "title": i.title,
                    "upgrade_priority": i.upgrade_priority,
                }
                for i in self.high_insights
            ],
            "medium_insights": [
                {
                    "insight_id": i.insight_id,
                    "title": i.title,
                    "upgrade_priority": i.upgrade_priority,
                }
                for i in self.medium_insights
            ],
            "ktg_injections": self.ktg_injections,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)


# ============================================================
# 规则提取器 (无需LLM, 快速预筛选)
# ============================================================


class RuleBasedExtractor:
    """基于规则的快速预提取 — 在 LLM 之前过滤噪声"""

    # 高价值关键词 (出现即标记为高优先级)
    HIGH_VALUE_KEYWORDS = [
        "self-improving",
        "self-evolving",
        "self-play",
        "self-correcting",
        "autonomous agent",
        "agentic",
        "multi-agent",
        "agent orchestration",
        "tool use",
        "function calling",
        "tool calling",
        "tool augmentation",
        "memory system",
        "persistent memory",
        "long-term memory",
        "context window",
        "reasoning",
        "chain-of-thought",
        "plan-and-execute",
        "react",
        "skill learning",
        "skill creation",
        "skill library",
        "skill reuse",
        "reinforcement learning",
        "rlhf",
        "dpo",
        "preference optimization",
        "retrieval augmented",
        "rag",
        "vector database",
        "embedding",
        "prompt engineering",
        "prompt optimization",
        "genetic algorithm",
        "mcp",
        "model context protocol",
        "a2a",
        "agent-to-agent",
        "sandbox",
        "code execution",
        "code interpreter",
        "evaluation",
        "benchmark",
        "gaia",
        "swe-bench",
        "agentbench",
    ]

    # 噪声模式 (低价值内容)
    NOISE_PATTERNS = [
        r"tutorial",
        r"introduction to",
        r"getting started",
        r"hello world",
        r"course",
        r"bootcamp",
        r"workshop",
        r"webinar",
        r"sponsor",
        r"advertisement",
        r"promotion",
        r"discount",
    ]

    def extract(self, items: list[SourceItem]) -> list[ExtractedInsight]:
        """快速规则提取"""
        insights = []
        for item in items:
            combined = f"{item.title} {item.raw_text}".lower()

            # 噪声过滤
            if any(re.search(p, combined) for p in self.NOISE_PATTERNS):
                continue

            # 关键词匹配
            matched_keywords = [kw for kw in self.HIGH_VALUE_KEYWORDS if kw in combined]
            if not matched_keywords:
                continue

            # 判断洞察类型
            insight_type = self._classify(item, combined, matched_keywords)

            # 计算置信度
            confidence = min(len(matched_keywords) / 5.0, 1.0)

            # 影响评估
            impact, priority = self._assess_impact(item, matched_keywords)

            insights.append(
                ExtractedInsight(
                    insight_id=f"ins_{item.source_id}",
                    insight_type=insight_type,
                    title=item.title[:120],
                    description=item.summary[:300],
                    source_items=[item.source_id],
                    confidence=confidence,
                    impact_on_fnixagent=impact,
                    upgrade_priority=priority,
                    suggested_action=self._suggest_action(item, insight_type),
                    related_modules=self._map_modules(item, matched_keywords),
                )
            )

        return insights

    def _classify(self, item: SourceItem, combined: str, keywords: list[str]) -> InsightType:
        if any(kw in combined for kw in ["framework", "library", "sdk", "open source"]):
            return InsightType.NEW_FRAMEWORK
        if any(kw in combined for kw in ["algorithm", "technique", "method", "approach"]):
            return InsightType.NEW_TECHNIQUE
        if any(kw in combined for kw in ["architecture", "design pattern", "system design"]):
            return InsightType.ARCHITECTURE_PATTERN
        if any(kw in combined for kw in ["paper", "arxiv", "research", "study"]):
            return InsightType.RESEARCH_BREAKTHROUGH
        if any(kw in combined for kw in ["benchmark", "evaluation", "score", "sota"]):
            return InsightType.BENCHMARK_RESULT
        if any(kw in combined for kw in ["mcp", "a2a", "protocol", "standard"]):
            return InsightType.PROTOCOL_UPDATE
        if any(kw in combined for kw in ["vulnerability", "security", "cve"]):
            return InsightType.SECURITY_ADVISORY
        return InsightType.BEST_PRACTICE

    def _assess_impact(self, item: SourceItem, keywords: list[str]) -> tuple[str, str]:
        if any(
            kw in keywords
            for kw in ["self-improving", "self-evolving", "skill learning", "skill creation"]
        ):
            return "核心自进化能力直接相关，可显著提升飞轮效率", "critical"
        if any(kw in keywords for kw in ["multi-agent", "agent orchestration", "mcp", "a2a"]):
            return "多Agent协作能力相关，可扩展系统架构", "critical"
        if any(kw in keywords for kw in ["memory system", "persistent memory", "reasoning"]):
            return "记忆/推理能力相关，可增强核心引擎", "high"
        if any(kw in keywords for kw in ["tool use", "sandbox", "code execution"]):
            return "工具/沙箱能力相关，可提升执行层", "high"
        return "一般性改进，可参考设计思路", "medium"

    def _suggest_action(self, item: SourceItem, insight_type: InsightType) -> str:
        actions = {
            InsightType.NEW_FRAMEWORK: f"评估 {item.title[:50]} 的设计理念，考虑借鉴其核心架构",
            InsightType.NEW_TECHNIQUE: f"研究 {item.title[:50]} 的技术方案，评估是否可集成到 FnixAgent",
            InsightType.ARCHITECTURE_PATTERN: f"分析 {item.title[:50]} 的架构模式，对比当前系统设计",
            InsightType.RESEARCH_BREAKTHROUGH: f"深入阅读 {item.title[:50]} 论文，提取可落地的创新点",
            InsightType.BENCHMARK_RESULT: f"参考 {item.title[:50]} 的基准测试，优化 FnixAgent 性能",
            InsightType.PROTOCOL_UPDATE: f"跟进 {item.title[:50]} 协议变更，确保 FnixAgent 兼容",
            InsightType.SECURITY_ADVISORY: f"评估 {item.title[:50]} 安全风险，及时修补",
            InsightType.BEST_PRACTICE: f"学习 {item.title[:50]} 的最佳实践，纳入开发规范",
        }
        return actions.get(insight_type, f"关注 {item.title[:50]}")

    def _map_modules(self, item: SourceItem, keywords: list[str]) -> list[str]:
        module_map = {
            "self-improving": ["core/flywheel", "core/skills", "core/topology"],
            "self-evolving": ["core/flywheel", "core/topology"],
            "multi-agent": ["core/multiagent", "core/orchestrator"],
            "memory": ["core/memory"],
            "reasoning": ["core/reasoning", "core/reflection"],
            "tool": ["core/tools", "core/security/sandbox"],
            "mcp": ["core/mcp"],
            "a2a": ["core/multiagent"],
            "prompt": ["core/prompt"],
            "skill": ["core/skills"],
            "retrieval": ["core/retrieval"],
            "vector": ["core/retrieval"],
            "sandbox": ["core/security/sandbox"],
            "security": ["core/security"],
            "benchmark": ["core/observability"],
        }
        modules = set()
        for kw, mods in module_map.items():
            if kw in keywords:
                modules.update(mods)
        return list(modules) if modules else ["core/flywheel"]


# ============================================================
# LLM 增强合成器 (深度分析)
# ============================================================


class LLMSynthesizer:
    """LLM 驱动的深度合成 — 理解语义, 生成结构化升级方案"""

    SYNTHESIS_PROMPT = """你是 FnixAgent 自进化系统的高级知识合成器。请分析以下 AI Agent 领域的最新情报，生成结构化报告。

## 当前系统状态
FnixAgent 是一个智能办公 Agent 平台，核心架构:
- KTG 知识拓扑图 (4层权重路径搜索，替代向量相似度)
- STP 技能-拓扑突触协议 (L2概念绑定技能，权重驱动调度)
- MFP 四阶进化飞轮 (感知执行→知识固化→元反思→爬山进化)
- 三层记忆 (短期Redis/长期Milvus/实体PostgreSQL)
- 六道安全纵深防御
- 自进化飞轮系统 (Intelligence & Auto-Evolution)

## 最新情报
{source_items}

## 任务要求
1. 提取每条情报的核心创新点 (1-2句话)
2. 评估对 FnixAgent 的具体影响 (注明受影响模块)
3. 按优先级排序 (critical > high > medium)
4. 生成具体的升级行动建议
5. 识别可以注入 KTG 拓扑的新知识节点

## 输出格式 (JSON)
{{
  "executive_summary": "本次情报汇总，1-2段",
  "insights": [
    {{
      "title": "情报标题",
      "core_innovation": "核心创新点",
      "impact_assessment": "对FnixAgent的影响",
      "affected_modules": ["模块列表"],
      "upgrade_priority": "critical|high|medium|low",
      "action_plan": "具体行动步骤",
      "ktg_nodes": [{{"level": "L1|L2|L3|L4", "content": "节点内容"}}]
    }}
  ],
  "upgrade_roadmap": "升级路线图，按优先级排列"
}}
"""

    def __init__(self, llm_client: Any = None):
        self.llm = llm_client

    async def synthesize(self, items: list[SourceItem]) -> SynthesisReport:
        """LLM 深度合成"""

        # 先规则预筛选
        extractor = RuleBasedExtractor()
        rule_insights = extractor.extract(items)

        # 构建源材料
        source_text = self._build_source_text(items[:30])

        # 尝试 LLM 分析 (如果可用)
        llm_insights = []
        if self.llm:
            try:
                prompt = self.SYNTHESIS_PROMPT.format(source_items=source_text)
                response = await self.llm.generate(prompt)
                parsed = json.loads(self._extract_json(response))
                llm_insights = self._parse_llm_insights(parsed)
            except Exception as e:
                logger.warning(f"LLM synthesis failed, falling back to rule-based: {e}")

        # 合并规则 + LLM 结果
        all_insights = rule_insights + llm_insights
        all_insights = self._deduplicate_insights(all_insights)

        # 分类
        critical = [i for i in all_insights if i.upgrade_priority == "critical"]
        high = [i for i in all_insights if i.upgrade_priority == "high"]
        medium = [i for i in all_insights if i.upgrade_priority == "medium"]

        # 生成 KTG 注入
        ktg_injections = self._generate_ktg_injections(all_insights)

        return SynthesisReport(
            report_id=datetime.now(UTC).strftime("syn_%Y%m%d_%H%M"),
            generated_at=datetime.now(UTC).isoformat(),
            total_sources=len(items),
            total_insights=len(all_insights),
            critical_insights=critical,
            high_insights=high,
            medium_insights=medium,
            executive_summary=self._generate_summary(all_insights, critical),
            upgrade_roadmap=self._generate_roadmap(critical + high),
            ktg_injections=ktg_injections,
        )

    def _build_source_text(self, items: list[SourceItem]) -> str:
        lines = []
        for i, item in enumerate(items[:30], 1):
            lines.append(f"{i}. [{item.source_type.value}] {item.title}")
            lines.append(f"   URL: {item.url}")
            lines.append(f"   Summary: {item.summary[:300]}")
            if item.authors:
                lines.append(f"   Authors: {', '.join(item.authors[:5])}")
            if item.citation_count:
                lines.append(f"   Citations: {item.citation_count}")
            lines.append("")
        return "\n".join(lines)

    def _extract_json(self, text: str) -> str:
        match = re.search(r"\{[\s\S]*\}", text)
        return match.group(0) if match else "{}"

    def _parse_llm_insights(self, parsed: dict) -> list[ExtractedInsight]:
        insights = []
        for item in parsed.get("insights", []):
            insights.append(
                ExtractedInsight(
                    insight_id=f"llm_{hash(item.get('title', ''))}",
                    insight_type=InsightType.BEST_PRACTICE,
                    title=item.get("title", "")[:120],
                    description=item.get("core_innovation", ""),
                    source_items=[],
                    confidence=0.8,
                    impact_on_fnixagent=item.get("impact_assessment", ""),
                    upgrade_priority=item.get("upgrade_priority", "medium"),
                    suggested_action=item.get("action_plan", ""),
                    related_modules=item.get("affected_modules", []),
                )
            )
        return insights

    def _deduplicate_insights(self, insights: list[ExtractedInsight]) -> list[ExtractedInsight]:
        seen_titles = set()
        unique = []
        for ins in insights:
            key = ins.title[:50]
            if key not in seen_titles:
                seen_titles.add(key)
                unique.append(ins)
        return unique

    def _generate_summary(
        self, all_insights: list[ExtractedInsight], critical: list[ExtractedInsight]
    ) -> str:
        lines = [
            f"本报告从 {len(all_insights)} 条情报中提取了关键洞察。",
            f"其中 {len(critical)} 条为关键优先级，建议立即关注。",
            "",
        ]
        if critical:
            lines.append("## 关键洞察:")
            for ins in critical[:5]:
                lines.append(f"- {ins.title}")
                lines.append(f"  影响: {ins.impact_on_fnixagent[:150]}")
                lines.append("")
        return "\n".join(lines)

    def _generate_roadmap(self, priority_insights: list[ExtractedInsight]) -> str:
        lines = ["## 升级路线图", ""]
        for i, ins in enumerate(priority_insights[:10], 1):
            lines.append(f"{i}. [{ins.upgrade_priority.upper()}] {ins.title}")
            lines.append(f"   行动: {ins.suggested_action}")
            lines.append(f"   模块: {', '.join(ins.related_modules)}")
            lines.append("")
        return "\n".join(lines)

    def _generate_ktg_injections(self, insights: list[ExtractedInsight]) -> list[dict]:
        injections = []
        for ins in insights[:10]:
            # L2 概念节点
            if ins.insight_type in (InsightType.NEW_FRAMEWORK, InsightType.NEW_TECHNIQUE):
                injections.append(
                    {
                        "level": "L2",
                        "concept": ins.title[:80],
                        "weight": 0.6 if ins.upgrade_priority == "critical" else 0.4,
                        "source": "intelligence_synthesis",
                        "related_skills": [],
                    }
                )
            # L3 规则节点
            if ins.insight_type == InsightType.BEST_PRACTICE:
                injections.append(
                    {
                        "level": "L3",
                        "rule": ins.description[:120],
                        "weight": 0.5,
                        "source": "intelligence_synthesis",
                    }
                )
        return injections


# ============================================================
# 合成引擎入口
# ============================================================


class SynthesisEngine:
    """合成引擎 — 采集 → 提取 → 合成 → 注入 KTG"""

    def __init__(self, llm_client: Any = None, output_dir: str | None = None):
        self.extractor = RuleBasedExtractor()
        self.synthesizer = LLMSynthesizer(llm_client)
        self.output_dir = output_dir or str(
            Path(__file__).parent.parent.parent.parent / "assets" / "synthesis"
        )
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    async def synthesize_from_collection(self, collected_data: dict) -> SynthesisReport:
        """从采集结果合成"""
        items = [
            SourceItem(
                source_id=it["source_id"],
                title=it["title"],
                url=it["url"],
                source_type=SourceCategory(it["source_type"]),
                raw_text=it.get("summary", ""),
                summary=it.get("summary", ""),
                authors=it.get("authors", []),
                citation_count=it.get("citation_count", 0),
                star_count=it.get("star_count", 0),
                tags=it.get("tags", []),
                metadata=it.get("metadata", {}),
            )
            for it in collected_data.get("items", [])
        ]
        return await self.synthesizer.synthesize(items)

    def save_report(self, report: SynthesisReport) -> str:
        """保存合成报告"""
        path = Path(self.output_dir) / f"{report.report_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            # 序列化 dataclass
            data = {
                "report_id": report.report_id,
                "generated_at": report.generated_at,
                "total_sources": report.total_sources,
                "total_insights": report.total_insights,
                "executive_summary": report.executive_summary,
                "upgrade_roadmap": report.upgrade_roadmap,
                "critical_insights": [
                    {
                        "insight_id": i.insight_id,
                        "title": i.title,
                        "description": i.description,
                        "upgrade_priority": i.upgrade_priority,
                        "suggested_action": i.suggested_action,
                        "related_modules": i.related_modules,
                    }
                    for i in report.critical_insights
                ],
                "high_insights": [
                    {
                        "insight_id": i.insight_id,
                        "title": i.title,
                        "upgrade_priority": i.upgrade_priority,
                    }
                    for i in report.high_insights
                ],
                "ktg_injections": report.ktg_injections,
            }
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(path)
