"""
飞轮 ② 知识固化环单元测试。

测试模块: fnixagent.core.flywheel.stage2_knowledge
覆盖:
    - 垃圾过滤(临时话术/执行失败/无实质推理)
    - 知识萃取(规则式: 概念/事实/因果关系)
    - 增量写入拓扑(新节点/强化节点/新边)
    - 常量: JUNK_KEYWORDS, MIN_TOOL_CALLS_FOR_SOLIDIFICATION
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.flywheel.stage2_knowledge import (
    JUNK_KEYWORDS,
    MIN_TOOL_CALLS_FOR_SOLIDIFICATION,
    KnowledgeSolidificationFlywheel,
)
from fnixagent.core.types import EdgeType, NodeType, TopologyLayer


class TestStage2Constants:
    """测试模块常量。"""

    def test_junk_keywords_is_frozenset(self):
        """JUNK_KEYWORDS 应为 frozenset。"""
        assert isinstance(JUNK_KEYWORDS, frozenset)

    def test_junk_keywords_contains_common_greetings(self):
        """JUNK_KEYWORDS 应包含常见问候语。"""
        assert "你好" in JUNK_KEYWORDS
        assert "hello" in JUNK_KEYWORDS
        assert "hi" in JUNK_KEYWORDS

    def test_min_tool_calls_value(self):
        """MIN_TOOL_CALLS_FOR_SOLIDIFICATION 应为 1。"""
        assert MIN_TOOL_CALLS_FOR_SOLIDIFICATION == 1


class TestStage2Filtering:
    """测试垃圾轨迹过滤。"""

    def test_failed_trace_filtered(self, sample_graph, failed_trace):
        """执行失败的轨迹应被过滤。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        result = fw.process(failed_trace)
        assert result["filtered"] is True
        assert result["filter_reason"] == "execution_failed"
        assert result["new_nodes"] == 0

    def test_junk_greeting_filtered(self, sample_graph, junk_trace):
        """临时话术(问候语)应被过滤。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        result = fw.process(junk_trace)
        assert result["filtered"] is True
        assert "junk_greeting" in result["filter_reason"]

    def test_no_tool_calls_filtered(self, sample_graph, no_tool_trace):
        """无工具调用(无实质推理)应被过滤。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        result = fw.process(no_tool_trace)
        assert result["filtered"] is True
        assert result["filter_reason"] == "no_substantive_reasoning"

    def test_valid_trace_not_filtered(self, sample_graph, sample_trace):
        """有效轨迹(成功+有工具调用)不应被过滤。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        result = fw.process(sample_trace)
        assert result["filtered"] is False
        assert result["filter_reason"] == ""


class TestStage2RuleBasedExtraction:
    """测试规则式知识萃取。"""

    def test_extracts_concepts_from_tool_names(self, sample_graph, sample_trace):
        """规则式萃取应从工具名提取概念。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        extracted = fw._rule_based_extract(sample_trace)
        concept_names = [c["name"] for c in extracted["concepts"]]
        assert "search_paper" in concept_names
        assert "analyze_data" in concept_names

    def test_extracts_facts_from_tool_args(self, sample_graph, sample_trace):
        """规则式萃取应从工具参数提取事实。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        extracted = fw._rule_based_extract(sample_trace)
        # sample_trace 有 2 次带 args 的工具调用
        assert len(extracted["facts"]) == 2

    def test_extracts_causal_relations(self, sample_graph, sample_trace):
        """规则式萃取应从工具调用顺序提取因果关系。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        extracted = fw._rule_based_extract(sample_trace)
        # 2 次工具调用 → 1 条因果关系
        assert len(extracted["causal_relations"]) == 1
        relation = extracted["causal_relations"][0]
        assert relation["from"] == "search_paper"
        assert relation["to"] == "analyze_data"

    def test_no_causal_relations_for_single_tool(self, sample_graph):
        """单次工具调用不应产生因果关系。"""
        from fnixagent.core.types import ReasoningMode, TraceRecord

        trace = TraceRecord(
            trace_id="t1",
            task_id="tk1",
            goal="测试",
            mode=ReasoningMode.REACT,
            concept_path=["L2:concept1"],
            tool_calls=[{"name": "search_paper", "args": {"q": "x"}, "status": "success"}],
            success=True,
            duration_ms=100.0,
            usage_tokens=10,
            reflection_score=0.0,
            created_at=0.0,
        )
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        extracted = fw._rule_based_extract(trace)
        assert len(extracted["causal_relations"]) == 0

    def test_deduplicates_concepts(self, sample_graph):
        """重复调用的工具名应去重为单个概念。"""
        from fnixagent.core.types import ReasoningMode, TraceRecord

        trace = TraceRecord(
            trace_id="t1",
            task_id="tk1",
            goal="测试",
            mode=ReasoningMode.REACT,
            concept_path=[],
            tool_calls=[
                {"name": "search_paper", "args": {}, "status": "success"},
                {"name": "search_paper", "args": {}, "status": "success"},
            ],
            success=True,
            duration_ms=100.0,
            usage_tokens=10,
            reflection_score=0.0,
            created_at=0.0,
        )
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        extracted = fw._rule_based_extract(trace)
        assert len(extracted["concepts"]) == 1


class TestStage2WriteToTopology:
    """测试增量写入拓扑图。"""

    def test_adds_new_concept_nodes(self, sample_graph, sample_trace):
        """新概念应作为 L2 CONCEPT 节点写入。"""
        initial_count = len(
            sample_graph.list_nodes(layer=TopologyLayer.L2_CONCEPT, node_type=NodeType.CONCEPT)
        )
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        result = fw.process(sample_trace)
        after_count = len(
            sample_graph.list_nodes(layer=TopologyLayer.L2_CONCEPT, node_type=NodeType.CONCEPT)
        )
        assert result["new_nodes"] > 0
        assert after_count > initial_count

    def test_reinforces_existing_path_nodes(self, sample_graph, sample_trace):
        """concept_path 中的现有节点应被强化。"""
        node = sample_graph.get_node("L2:concept1")
        original_weight = node.weight
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        fw.process(sample_trace)
        assert node.weight > original_weight

    def test_adds_causal_edge(self, sample_graph, sample_trace):
        """因果关系应写入为 CAUSAL 边。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        result = fw.process(sample_trace)
        assert result["new_edges"] >= 1
        causal_edges = sample_graph.list_edges(edge_type=EdgeType.CAUSAL)
        assert len(causal_edges) >= 1

    def test_reinforces_existing_concept_node(self, sample_graph, sample_trace):
        """重复处理同名概念时应强化现有节点而非新增。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        # 第一次处理 → 新增
        result1 = fw.process(sample_trace)
        assert result1["new_nodes"] > 0
        # 第二次处理 → 强化
        result2 = fw.process(sample_trace)
        assert result2["reinforced_nodes"] > 0

    def test_returns_expected_keys(self, sample_graph, sample_trace):
        """process 返回的 dict 应包含全部预期键。"""
        fw = KnowledgeSolidificationFlywheel(sample_graph)
        result = fw.process(sample_trace)
        expected_keys = {
            "filtered",
            "filter_reason",
            "new_nodes",
            "new_edges",
            "reinforced_nodes",
            "reinforced_edges",
        }
        assert expected_keys.issubset(set(result.keys()))


class TestStage2LLMExtraction:
    """测试 LLM 萃取(降级模式)。"""

    def test_llm_failure_falls_back_to_rules(self, sample_graph, sample_trace):
        """LLM 调用失败时应降级为规则式萃取。"""

        class FailingLLM:
            def chat(self, messages):
                raise RuntimeError("LLM unavailable")

        fw = KnowledgeSolidificationFlywheel(sample_graph, llm_router=FailingLLM())
        result = fw.process(sample_trace)
        # 降级后仍应正常萃取
        assert result["filtered"] is False
        assert result["new_nodes"] > 0
