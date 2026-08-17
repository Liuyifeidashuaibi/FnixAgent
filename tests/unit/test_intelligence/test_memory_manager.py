"""L5 记忆层 (IntelligenceMemoryManager) 单元测试。

用 tmp_path 隔离, 不污染真实 workspace。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.intelligence.memory_manager import (
    IntelligenceMemoryManager,
    MemoryEntry,
)


class TestIntelligenceMemoryManager:
    """IntelligenceMemoryManager 核心功能测试。"""

    def test_add_and_recall(self, tmp_path):
        """添加记忆后能按关键词召回。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        # 初始为空
        assert mgr.recall("anything") == []
        # 写入两条记忆
        mgr.add_memory(
            "重构模块X", "用户让重构模块X的认证逻辑, 采用了策略A", memory_type="episodic"
        )
        mgr.add_memory("数据分析", "对销售数据做了透视表分析", memory_type="episodic")
        # 召回
        results = mgr.recall("重构 模块X", top_k=5)
        assert isinstance(results, list)
        assert len(results) >= 1
        # 命中的应包含"重构模块X"
        hit_contents = [r.get("content", "") for r in results]
        assert any("重构模块X" in c for c in hit_contents)
        # 召回结构含必要字段
        first = results[0]
        assert "memory_id" in first
        assert "key" in first
        assert "content" in first
        assert "memory_type" in first
        assert "score" in first

    def test_add_memory_overwrites_same_key(self, tmp_path):
        """相同 key 的记忆应覆盖旧的 (Voyager 同名覆盖)。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        mgr.add_memory("task_a", "旧内容", memory_type="episodic")
        mgr.add_memory("task_a", "新内容", memory_type="episodic")
        stats = mgr.get_stats()
        assert stats["total"] == 1  # 覆盖, 不重复
        results = mgr.recall("task_a", top_k=5)
        assert len(results) == 1
        assert "新内容" in results[0]["content"]

    def test_add_memory_rejects_empty(self, tmp_path):
        """空 key/content 应被拒绝。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        assert mgr.add_memory("", "content") is None
        assert mgr.add_memory("key", "") is None
        assert mgr.add_memory(None, "content") is None  # type: ignore[arg-type]

    def test_add_memory_invalid_type_falls_back(self, tmp_path):
        """非法 memory_type 应回退为 episodic。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        entry = mgr.add_memory("k", "v", memory_type="unknown_type")
        assert entry is not None
        assert entry.memory_type == "episodic"

    def test_consolidate(self, tmp_path):
        """consolidate 把高价值 episodic 固化为 semantic, 清理 working。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        # 高价值 episodic (importance>=0.6) 且被访问过
        mgr.add_memory("high_value", "重要经验, 已被访问", memory_type="episodic", importance=0.8)
        # 先召回一次, 让 access_count >= 1
        mgr.recall("high_value", top_k=5)
        # working 记忆 (应被清理)
        mgr.add_memory("temp", "临时工作记忆", memory_type="working", importance=0.9)
        # 低价值 episodic (保留但不固化)
        mgr.add_memory("low_value", "普通经验", memory_type="episodic", importance=0.3)

        result = mgr.consolidate()
        assert isinstance(result, dict)
        assert "before_total" in result
        assert "after_total" in result
        assert "working_removed" in result
        assert "consolidated_to_semantic" in result
        assert result["working_removed"] >= 1  # working 被清理
        assert result["consolidated_to_semantic"] >= 1  # 高价值被固化

        # 验证固化后 memory_type 变为 semantic
        stats = mgr.get_stats()
        assert stats["consolidated"] >= 1
        assert "semantic" in stats["by_type"]

    def test_consolidate_dedup(self, tmp_path):
        """consolidate 应按 key 去重。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        # 相同 key 多次写入 (add_memory 已覆盖, 这里测 consolidate 内部去重逻辑)
        mgr.add_memory("dup", "内容1", importance=0.7)
        # 手动注入同 key 不同 id 的记忆以测去重
        import time

        mgr.memories.append(
            MemoryEntry(
                memory_id="mem_dup2",
                key="dup",
                content="内容2",
                memory_type="episodic",
                created_at=time.time(),
                importance=0.5,
            )
        )
        before = len(mgr.memories)
        result = mgr.consolidate()
        assert before >= 2
        assert result["after_total"] < before  # 去重后变少

    def test_get_stats(self, tmp_path):
        """get_stats 返回正确统计结构。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        # 空库
        stats = mgr.get_stats()
        assert isinstance(stats, dict)
        assert stats["total"] == 0
        assert stats["consolidated"] == 0
        assert stats["avg_importance"] == 0.0
        assert stats["by_type"] == {}
        # 写入后
        mgr.add_memory("k1", "c1", memory_type="episodic", importance=0.6)
        mgr.add_memory("k2", "c2", memory_type="semantic", importance=0.9)
        stats2 = mgr.get_stats()
        assert stats2["total"] == 2
        assert stats2["by_type"].get("episodic") == 1
        assert stats2["by_type"].get("semantic") == 1
        assert 0.0 < stats2["avg_importance"] <= 1.0

    def test_persistence_across_instances(self, tmp_path):
        """记忆应跨实例持久化 (写磁盘)。"""
        mgr1 = IntelligenceMemoryManager(str(tmp_path))
        mgr1.add_memory("persist_test", "持久化内容", memory_type="episodic")
        # 新实例加载同一 workspace
        mgr2 = IntelligenceMemoryManager(str(tmp_path))
        assert mgr2.get_stats()["total"] == 1
        results = mgr2.recall("persist_test", top_k=5)
        assert len(results) == 1
        assert "持久化内容" in results[0]["content"]

    def test_recall_empty_query(self, tmp_path):
        """空 query 应返回空列表。"""
        mgr = IntelligenceMemoryManager(str(tmp_path))
        mgr.add_memory("k", "内容", memory_type="episodic")
        assert mgr.recall("") == []
        assert mgr.recall("   ") == []
