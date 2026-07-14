"""
知识提炼引擎 — 从收集的情报中提炼关键洞见，分类整理，为飞轮升级提供输入

参考设计:
  - Hermes: 两文件系统 (MEMORY.md + USER.md) 压缩文本 + 权重衰减
  - OpenClaw: markdown 结构化技能 + 自动修正沉淀
  - GEPA: 遗传优化、评分选择、帕累托最优、随机突变
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from .collector import IntelligenceItem, IntelligenceCategory, Priority

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================

class KnowledgeItem(BaseModel):
    """单个知识条目"""
    item_id: str
    title: str
    url: str
    category: str
    priority: str
    summary: str
    key_insights: list[str]
    actionable: bool
    upgrade_suggestion: str
    source_name: str
    collected_at: str
    tags: list[str]
    relevance_score: float = 0.0  # 对当前系统的相关性 (0-1)
    status: str = "pending"  # pending/accepted/implemented/rejected
    implemented_at: Optional[str] = None
    implementation_notes: str = ""


class KnowledgeDigest(BaseModel):
    """一次提炼结果汇总"""
    digest_id: str
    digest_at: str
    total_items: int
    actionable_items: int
    critical_items: list[KnowledgeItem]
    high_items: list[KnowledgeItem]
    medium_items: list[KnowledgeItem]
    digest_summary: str
    system_upgrade: list[str]


# ============================================================
# 知识提炼器
# ============================================================

class KnowledgeExtractor:
    """从收集的情报中提炼知识，分类整理，评分排序"""

    def __init__(
        self,
        knowledge_dir: Optional[str] = None,
        relevance_threshold: float = 0.5,
    ):
        self.knowledge_dir = knowledge_dir or str(
            Path(__file__).parent.parent.parent.parent / "assets" / "knowledge"
        )
        self.relevance_threshold = relevance_threshold
        Path(self.knowledge_dir).mkdir(parents=True, exist_ok=True)

    def _calculate_relevance(self, item: IntelligenceItem) -> float:
        """计算情报对 FnixAgent 系统的相关性"""
        score = 0.0
        title_lower = item.title.lower()
        summary_lower = item.summary.lower()

        # 关键字权重
        high_weight_keywords = {
            "self-improving": 0.8, "self-evolution": 0.8, "evolution": 0.7,
            "continuous learning": 0.7, "skill learning": 0.6,
            "agent architecture": 0.6, "framework": 0.5, "protocol": 0.6,
            "memory system": 0.7, "reasoning": 0.5, "tool use": 0.5,
            "multi-agent": 0.5, "prompt engineering": 0.4,
            "openai agents sdk": 0.6, "langgraph": 0.4,
            "openclaw": 0.6, "hermes agent": 0.6, "sage": 0.6,
            "gepa": 0.7, "icml": 0.4, "iclr": 0.4, "neurips": 0.4,
        }

        for kw, weight in high_weight_keywords.items():
            if kw in title_lower:
                score += weight
            if kw in summary_lower:
                score += weight * 0.5

        # 优先级加成
        priority_map = {"critical": 0.2, "high": 0.1, "medium": 0.0, "low": -0.1}
        score += priority_map.get(item.priority, 0.0)

        # 归一化到 [0, 1]
        return min(score, 1.0)

    def extract_from_collection(self, collected_data: dict) -> KnowledgeDigest:
        """从采集结果中提取知识"""
        knowledge_items: list[KnowledgeItem] = []

        for result in collected_data.get("results", []):
            for item_data in result.get("items", []):
                # IntelligenceItem → KnowledgeItem
                item = KnowledgeItem(
                    item_id=item_data.get("id", ""),
                    title=item_data.get("title", ""),
                    url=item_data.get("url", ""),
                    category=item_data.get("category", "agent_framework"),
                    priority=item_data.get("priority", "medium"),
                    summary=item_data.get("summary", ""),
                    key_insights=item_data.get("key_insights", []),
                    actionable=item_data.get("actionable", False),
                    upgrade_suggestion=item_data.get("upgrade_suggestion", ""),
                    source_name=item_data.get("source_name", ""),
                    collected_at=item_data.get("collected_at", datetime.now(timezone.utc).isoformat()),
                    tags=item_data.get("tags", []),
                )
                item.relevance_score = self._calculate_relevance(item)
                knowledge_items.append(item)

        # 分类
        critical_items = [
            k for k in knowledge_items
            if k.priority == "critical" and k.relevance_score >= self.relevance_threshold
        ]
        high_items = [
            k for k in knowledge_items
            if k.priority == "high" and k.relevance_score >= self.relevance_threshold
                   and k not in critical_items
        ]
        medium_items = [
            k for k in knowledge_items
            if k.relevance_score >= self.relevance_threshold
               and k not in critical_items and k not in high_items
        ]

        # 生成摘要
        actionable = [k for k in knowledge_items if k.actionable]
        summary = self._generate_digest_summary(critical_items, high_items, actionable)

        digest = KnowledgeDigest(
            digest_id=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M"),
            digest_at=datetime.now(timezone.utc).isoformat(),
            total_items=len(knowledge_items),
            actionable_items=len(actionable),
            critical_items=critical_items,
            high_items=high_items,
            medium_items=medium_items,
            digest_summary=summary,
            system_upgrade=self._extract_upgrade_suggestions(critical_items + high_items),
        )

        return digest

    def _generate_digest_summary(
        self,
        critical: list[KnowledgeItem],
        high: list[KnowledgeItem],
        actionable: list[KnowledgeItem],
    ) -> str:
        """生成摘要文本"""
        lines = [
            f"本次采集: {len(critical) + len(high)} 条高优先级情报, {len(actionable)} 条可执行升级建议",
            "",
        ]
        if critical:
            lines.append("## 关键情报:")
            for item in critical:
                lines.append(f"- {item.title}")
                if item.key_insights:
                    for insight in item.key_insights[:2]:
                        lines.append(f"  • {insight}")
                lines.append(f"  → {item.url}")
                lines.append("")
        if high:
            lines.append("## 重要情报:")
            for item in high[:5]:
                lines.append(f"- {item.title}")
            if len(high) > 5:
                lines.append(f"- ... (+ {len(high) - 5} more)")
            lines.append("")
        return "\n".join(lines)

    def _extract_upgrade_suggestions(self, items: list[KnowledgeItem]) -> list[str]:
        """提取系统升级建议"""
        suggestions: list[str] = []
        for item in items:
            if item.upgrade_suggestion:
                suggestions.append(item.upgrade_suggestion)
            elif item.key_insights:
                for insight in item.key_insights[:2]:
                    suggestions.append(f"[{item.title}] {insight}")
        return suggestions[:20]

    def save_digest(self, digest: KnowledgeDigest) -> str:
        """保存提炼结果"""
        date_str = digest.digest_id
        output_path = Path(self.knowledge_dir) / f"digest_{date_str}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(digest.model_dump(), f, ensure_ascii=False, indent=2)
        logger.info(f"Knowledge digest saved to {output_path}")
        return str(output_path)

    def load_latest_digest(self) -> Optional[KnowledgeDigest]:
        """加载最新的提炼结果"""
        digest_files = sorted(
            Path(self.knowledge_dir).glob("digest_*.json"),
            reverse=True,
            key=lambda p: p.stat().st_mtime
        )
        if not digest_files:
            return None
        with open(digest_files[0], "r", encoding="utf-8") as f:
            data = json.load(f)
        return KnowledgeDigest(**data)


# ============================================================
# 飞轮知识库
# ============================================================

class FlywheelKnowledgeBase:
    """飞轮知识库 — 持久化存储提炼后的知识，供升级策略使用"""

    def __init__(self, kb_path: Optional[str] = None):
        self.kb_path = kb_path or str(
            Path(__file__).parent.parent.parent.parent / "assets" / "flywheel_kb"
        )
        Path(self.kb_path).mkdir(parents=True, exist_ok=True)
        self._index_path = Path(self.kb_path) / "knowledge_index.json"
        self._index: dict[str, dict] = self._load_index()

    def _load_index(self) -> dict:
        if not self._index_path.exists():
            return {}
        with open(self._index_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_index(self):
        with open(self._index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)

    def add_knowledge(self, item: KnowledgeItem, implementation_notes: str = ""):
        """添加一条知识到知识库"""
        entry = item.model_dump()
        entry["implemented_at"] = datetime.now(timezone.utc).isoformat()
        entry["implementation_notes"] = implementation_notes
        entry["status"] = "implemented"
        self._index[item.item_id] = entry
        self._save_index()

        entry_path = Path(self.kb_path) / f"{item.item_id}.json"
        with open(entry_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        logger.info(f"Added knowledge {item.item_id} to KB")

    def get_pending(self, limit: int = 20) -> list[KnowledgeItem]:
        """获取待实现的高优先级知识"""
        pending = [
            KnowledgeItem(**entry)
            for entry in self._index.values()
            if entry["status"] == "pending"
               and entry["priority"] in ["critical", "high"]
        ]
        pending.sort(key=lambda x: -float(x.get("relevance_score", 0.0)))
        return pending[:limit]

    def get_all_by_category(self, category: str) -> list[KnowledgeItem]:
        """按分类获取所有知识"""
        return [
            KnowledgeItem(**entry)
            for entry in self._index.values()
            if entry["category"] == category
        ]

    def get_statistics(self) -> dict:
        """知识库统计"""
        total = len(self._index)
        by_status = {}
        by_priority = {}
        for entry in self._index.values():
            s = entry["status"]
            by_status[s] = by_status.get(s, 0) + 1
            p = entry["priority"]
            by_priority[p] = by_priority.get(p, 0) + 1
        return {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
        }