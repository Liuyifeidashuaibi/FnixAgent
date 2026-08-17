"""
Memory Consolidation - 定期记忆提炼。

每 N 次对话后自动 consolidate，提取关键事实写入 MEMORY.md。
参考 EverOS 的记忆整合设计。

流程：
1. 读取最近 N 条对话
2. LLM 提取关键事实/决策/偏好
3. 去重合并到 MEMORY.md
4. 更新 SQLite 索引
5. 更新向量索引
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMAware(Protocol):
    """LLM 接口协议。"""
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """生成文本。"""
        ...


@dataclass
class ExtractedFact:
    """提取的事实。"""
    
    content: str
    category: str = "fact"  # fact, decision, preference, insight
    confidence: float = 0.8
    tags: list[str] = field(default_factory=list)
    source_episodes: list[str] = field(default_factory=list)


@dataclass
class ConsolidationResult:
    """提炼结果。"""
    
    facts_extracted: list[ExtractedFact]
    facts_merged: int
    facts_deduplicated: int
    memory_updated: bool
    timestamp: float = field(default_factory=time.time)


class MemoryConsolidator:
    """记忆提炼器。
    
    定期从对话历史中提取关键事实，合并到长期记忆。
    """
    
    # 提炼提示词模板
    EXTRACTION_PROMPT = """你是一个记忆提炼助手。请从以下对话历史中提取关键事实、决策、偏好和洞察。

对话历史：
{history}

请提取以下内容：
1. 事实 (fact): 客观信息，如用户姓名、职业、偏好等
2. 决策 (decision): 用户做出的重要决定
3. 偏好 (preference): 用户的喜好、习惯
4. 洞察 (insight): 值得记住的模式或规律

对于每个提取的内容，请提供：
- content: 具体内容
- category: 类别 (fact/decision/preference/insight)
- confidence: 置信度 (0.0-1.0)
- tags: 标签列表

以 JSON 格式输出：
[
  {{"content": "...", "category": "fact", "confidence": 0.9, "tags": ["tag1", "tag2"]}},
  ...
]

只输出 JSON，不要其他内容。
"""
    
    def __init__(
        self,
        llm: LLMAware = None,
        threshold: int = 10,
        max_facts_per_consolidation: int = 20,
    ):
        """初始化提炼器。
        
        Args:
            llm: LLM 实例
            threshold: 触发提炼的对话轮数阈值
            max_facts_per_consolidation: 每次提炼最大事实数
        """
        self.llm = llm
        self.threshold = threshold
        self.max_facts_per_consolidation = max_facts_per_consolidation
    
    async def should_consolidate(self, episode_count: int) -> bool:
        """判断是否应该提炼。"""
        return episode_count >= self.threshold
    
    async def extract_facts(
        self,
        episodes: list[dict[str, Any]],
    ) -> list[ExtractedFact]:
        """从对话历史中提取事实。
        
        Args:
            episodes: 对话历史列表，每条包含 role 和 content
        
        Returns:
            提取的事实列表
        """
        if not self.llm:
            return []
        
        # 格式化对话历史
        history_text = self._format_episodes(episodes)
        
        # 生成提示词
        prompt = self.EXTRACTION_PROMPT.format(history=history_text)
        
        # 调用 LLM
        try:
            response = await self.llm.generate(prompt, temperature=0.3)
            facts = self._parse_llm_response(response)
            return facts[:self.max_facts_per_consolidation]
        except Exception as e:
            print(f"Failed to extract facts: {e}")
            return []
    
    async def consolidate(
        self,
        episodes: list[dict[str, Any]],
        memory_store: Any,  # MarkdownMemoryStore
    ) -> ConsolidationResult:
        """执行记忆提炼。
        
        Args:
            episodes: 对话历史
            memory_store: Markdown 记忆存储
        
        Returns:
            提炼结果
        """
        # 1. 提取事实
        facts = await self.extract_facts(episodes)
        
        if not facts:
            return ConsolidationResult(
                facts_extracted=[],
                facts_merged=0,
                facts_deduplicated=0,
                memory_updated=False,
            )
        
        # 2. 读取现有记忆
        existing_entries = memory_store.parse_memory()
        
        # 3. 去重合并
        new_facts = []
        deduplicated_count = 0
        
        for fact in facts:
            if self._is_duplicate(fact, existing_entries):
                deduplicated_count += 1
            else:
                new_facts.append(fact)
        
        # 4. 写入 MEMORY.md
        for fact in new_facts:
            from fnixagent.core.memory.markdown_store import MemoryEntry
            
            entry = MemoryEntry(
                id=f"fact_{int(time.time())}_{hash(fact.content) % 10000:04d}",
                content=fact.content,
                category=fact.category,
                tags=fact.tags,
                timestamp=time.time(),
            )
            memory_store.append_memory(entry)
        
        # 5. 追加历史
        memory_store.append_history(
            f"Memory consolidation: extracted {len(facts)} facts, "
            f"added {len(new_facts)}, deduplicated {deduplicated_count}",
            metadata={"facts_count": len(facts), "new_count": len(new_facts)},
        )
        
        return ConsolidationResult(
            facts_extracted=facts,
            facts_merged=len(new_facts),
            facts_deduplicated=deduplicated_count,
            memory_updated=len(new_facts) > 0,
        )
    
    def _format_episodes(self, episodes: list[dict[str, Any]]) -> str:
        """格式化对话历史。"""
        lines = []
        for ep in episodes:
            role = ep.get("role", "unknown")
            content = ep.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
    
    def _parse_llm_response(self, response: str) -> list[ExtractedFact]:
        """解析 LLM 响应。"""
        import json
        
        # 尝试提取 JSON
        try:
            # 查找 JSON 数组
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                data = json.loads(json_str)
                
                facts = []
                for item in data:
                    facts.append(ExtractedFact(
                        content=item.get("content", ""),
                        category=item.get("category", "fact"),
                        confidence=float(item.get("confidence", 0.8)),
                        tags=item.get("tags", []),
                    ))
                return facts
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse LLM response: {e}")
        
        return []
    
    def _is_duplicate(
        self,
        fact: ExtractedFact,
        existing_entries: list[Any],
    ) -> bool:
        """检查是否与现有记忆重复。"""
        # 简单相似度检查
        fact_lower = fact.content.lower()
        
        for entry in existing_entries:
            entry_lower = entry.content.lower()
            
            # 完全匹配
            if fact_lower == entry_lower:
                return True
            
            # 包含关系
            if fact_lower in entry_lower or entry_lower in fact_lower:
                return True
            
            # 关键词重叠
            fact_words = set(fact_lower.split())
            entry_words = set(entry_lower.split())
            overlap = len(fact_words & entry_words)
            if overlap > min(len(fact_words), len(entry_words)) * 0.7:
                return True
        
        return False


class ReflectionEngine:
    """记忆反思引擎。
    
    定期分析记忆，合并相似项，提炼模式。
    """
    
    REFLECTION_PROMPT = """你是一个记忆分析助手。请分析以下记忆条目，找出可以合并的相似项和可以提炼的模式。

记忆条目：
{memories}

请输出：
1. 可以合并的相似条目对
2. 可以提炼的高层模式或规律

以 JSON 格式输出：
{{
  "merge_pairs": [["id1", "id2"], ...],
  "patterns": ["pattern1", "pattern2", ...]
}}

只输出 JSON，不要其他内容。
"""
    
    def __init__(self, llm: LLMAware = None):
        self.llm = llm
    
    async def reflect(self, memory_store: Any) -> dict[str, Any]:
        """执行记忆反思。
        
        Args:
            memory_store: Markdown 记忆存储
        
        Returns:
            反思结果
        """
        if not self.llm:
            return {"merge_pairs": [], "patterns": []}
        
        # 读取现有记忆
        entries = memory_store.parse_memory()
        
        if len(entries) < 5:
            return {"merge_pairs": [], "patterns": []}
        
        # 格式化记忆
        memories_text = "\n".join([
            f"[{e.id}] ({e.category}) {e.content}"
            for e in entries[-50:]  # 只分析最近 50 条
        ])
        
        # 调用 LLM
        prompt = self.REFLECTION_PROMPT.format(memories=memories_text)
        
        try:
            response = await self.llm.generate(prompt, temperature=0.3)
            return self._parse_reflection_response(response)
        except Exception as e:
            print(f"Failed to reflect: {e}")
            return {"merge_pairs": [], "patterns": []}
    
    def _parse_reflection_response(self, response: str) -> dict[str, Any]:
        """解析反思响应。"""
        import json
        
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass
        
        return {"merge_pairs": [], "patterns": []}
