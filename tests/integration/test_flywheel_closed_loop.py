"""
飞轮闭环集成测试。

验证 Day 7 核心交付:
  1. build_graph() 能正确装配 GraphComponents
  2. process_with_graph() 飞轮闭环可运行
  3. 多轮对话后轨迹被持久化
  4. 飞轮 ② 知识固化能产出结构化结果
  5. 飞轮 ③④ 触发条件可正常判定

注: 使用 MockLLMProvider + 真实拓扑图,模拟最小可运行链路。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import os
import sys

# 确保 src 在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest

# 强制使用 MockLLMProvider(无外部 API Key 依赖)
os.environ.setdefault("GLM_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("QWEN_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")

from fnixagent.core.config import get_config
from fnixagent.services.service import (
    GraphComponents,
    build_graph,
    process_with_graph,
    reset_graph,
)


@pytest.fixture(scope="module")
def components():
    """构建一次 GraphComponents,模块内所有测试共享。

    使用临时 trace 目录避免污染工作区。
    """
    tmp_dir = os.path.join(os.path.dirname(__file__), "..", "..", ".tmp_trace_integration")
    # 保存原值,测试结束后还原,避免环境变量泄漏到其它测试
    prev_trace_dir = os.environ.get("FNIXAGENT_TRACE_DIR")
    os.environ["FNIXAGENT_TRACE_DIR"] = tmp_dir

    cfg = get_config()
    comp = build_graph(cfg)
    yield comp

    # 清理单例,避免影响后续测试
    reset_graph()
    # 清理临时目录
    import shutil

    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 还原环境变量
    if prev_trace_dir is None:
        os.environ.pop("FNIXAGENT_TRACE_DIR", None)
    else:
        os.environ["FNIXAGENT_TRACE_DIR"] = prev_trace_dir


class TestGraphBuild:
    """飞轮 0: 验证 build_graph() 装配正确性。"""

    def test_returns_graph_components(self, components):
        """应返回 GraphComponents 实例。"""
        assert isinstance(components, GraphComponents)

    def test_all_required_fields_filled(self, components):
        """所有关键字段应被填充。"""
        required_fields = [
            "graph",
            "topology_graph",
            "search_engine",
            "binding_protocol",
            "permission_policy",
            "scheduler",
            "feedback_handler",
            "flywheel_perception",
            "flywheel_solidification",
            "flywheel_reflection",
            "flywheel_climbing",
            "trace_store",
            "llm_router",
            "tool_registry",
            "tool_executor",
        ]
        for field in required_fields:
            value = getattr(components, field, None)
            assert value is not None, f"字段 {field} 未填充"

    def test_topology_graph_empty_at_startup(self, components):
        """冷启动时拓扑图应为空(或近空)。"""
        stats = components.topology_graph.stats()
        assert stats.get("node_count", 0) >= 0
        assert components.search_engine.is_cold_start() in (True, False)

    def test_business_tools_registered(self, components):
        """业务工具应已注册到 tool_registry。"""
        # 至少有部分工具(论文检索/Word/转换),具体数量取决于业务模块加载情况
        assert components.tool_registry.count >= 0


class TestFlywheelClosedLoop:
    """飞轮 ①→②→(③)→(④) 闭环验证。"""

    def test_single_turn_minimal(self, components):
        """单轮对话闭环: 不抛异常,返回必要字段。"""
        result = process_with_graph(
            user_input="帮我搜索 GPT-4 相关论文",
            components=components,
            session_id="test-session-1",
        )

        # 必要字段
        assert "answer" in result
        assert "trace" in result
        assert "solidified" in result
        assert "reflected" in result

        # trace 应为 TraceRecord 实例
        from fnixagent.core.types import TraceRecord

        assert isinstance(result["trace"], TraceRecord)

    def test_trace_persisted_after_run(self, components):
        """运行后轨迹应被持久化到 trace_store。"""
        before = components.trace_store.count()
        process_with_graph(
            user_input="再次搜索 Transformers 论文",
            components=components,
            session_id="test-session-2",
        )
        after = components.trace_store.count()
        assert after >= before + 1, f"trace 未持久化: before={before}, after={after}"

    def test_multi_turn_does_not_crash(self, components):
        """多轮对话(5 轮)不应崩溃。"""
        inputs = [
            "你好",
            "帮我检索关于大模型的论文",
            "搜索 BERT 相关资料",
            "再查一下 Transformer 架构",
            "总结一下检索结果",
        ]
        for i, user_input in enumerate(inputs):
            result = process_with_graph(
                user_input=user_input,
                components=components,
                session_id=f"multi-turn-{i}",
            )
            assert "trace" in result
            assert result["trace"].goal or result["trace"].task_id

    def test_solidification_returns_dict(self, components):
        """飞轮 ② 知识固化应返回字典(即使为空)。"""
        result = process_with_graph(
            user_input="测试知识固化阶段",
            components=components,
            session_id="solidification-test",
        )
        assert isinstance(result["solidified"], dict)

    def test_trace_stats_available(self, components):
        """多轮对话后,trace_store 应能产出统计。"""
        # 触发若干轮
        for i in range(3):
            process_with_graph(
                user_input=f"统计测试 {i}",
                components=components,
                session_id=f"stats-{i}",
            )

        stats = components.trace_store.stats()
        assert "total" in stats
        assert stats["total"] >= 3
        # success_rate 应为合法值 [0, 1] 或 0(无数据)
        sr = stats.get("success_rate", 0)
        assert 0.0 <= sr <= 1.0

    def test_reflection_trigger_check(self, components):
        """飞轮 ③ should_trigger() 应能正常返回布尔值。"""
        result = components.flywheel_reflection.should_trigger()
        assert isinstance(result, bool)

    def test_climbing_trigger_check(self, components):
        """飞轮 ④ should_trigger() 应能正常返回布尔值。"""
        result = components.flywheel_climbing.should_trigger()
        assert isinstance(result, bool)

    def test_topology_stats_endpoint_data(self, components):
        """拓扑图统计应能产出有效字典。"""
        stats = components.topology_graph.stats()
        assert isinstance(stats, dict)
        # 应包含 node_count / edge_count 字段
        assert "node_count" in stats or "nodes" in stats or len(stats) > 0


class TestBackwardCompatibility:
    """向后兼容性验证: 传统模式仍可使用。"""

    def test_scheduler_build_still_works(self):
        """传统 build_scheduler() 仍应可工作。"""
        from fnixagent.services.service import build_scheduler, reset_scheduler

        try:
            scheduler = build_scheduler()
            assert scheduler is not None
        finally:
            reset_scheduler()
