"""
飞轮 ① 感知-执行环单元测试。

测试模块: fnixagent.core.flywheel.stage1_perception
覆盖:
    - PerceptionFlywheel.run(): 完整感知-执行流程(使用 mock graph)
    - PerceptionFlywheel.run_stream(): 流式执行
    - trace_to_dict() / trace_from_dict(): 序列化/反序列化
"""

from fnixagent.core.flywheel.stage1_perception import (
    PerceptionFlywheel,
    trace_from_dict,
    trace_to_dict,
)
from fnixagent.core.types import ReasoningMode, TraceRecord


class TestPerceptionFlywheelInit:
    """测试 PerceptionFlywheel 初始化。"""

    def test_init_stores_graph(self, fake_graph):
        """PerceptionFlywheel 应存储传入的 graph。"""
        fw = PerceptionFlywheel(fake_graph)
        assert fw._graph is fake_graph

    def test_init_default_reasoning_mode(self, fake_graph):
        """默认推理模式应为 REACT。"""
        fw = PerceptionFlywheel(fake_graph)
        assert fw._reasoning_mode == ReasoningMode.REACT

    def test_init_custom_reasoning_mode(self, fake_graph):
        """应支持自定义推理模式。"""
        fw = PerceptionFlywheel(fake_graph, ReasoningMode.PLAN_EXECUTE)
        assert fw._reasoning_mode == ReasoningMode.PLAN_EXECUTE


class TestPerceptionFlywheelRun:
    """测试 PerceptionFlywheel.run() 方法。"""

    def test_run_returns_trace_record(self, fake_graph):
        """run() 应返回 TraceRecord 实例。"""
        fw = PerceptionFlywheel(fake_graph)
        trace = fw.run("搜索论文")
        assert isinstance(trace, TraceRecord)

    def test_run_invokes_graph(self, fake_graph):
        """run() 应调用 graph.invoke。"""
        fw = PerceptionFlywheel(fake_graph)
        fw.run("搜索论文")
        assert fake_graph.invoke_count == 1

    def test_run_preserves_user_input_as_goal(self, fake_graph):
        """run() 应将 user_input 设为 trace.goal。"""
        fw = PerceptionFlywheel(fake_graph)
        trace = fw.run("搜索 GPT-4 论文")
        assert trace.goal == "搜索 GPT-4 论文"

    def test_run_successful_execution(self, fake_graph):
        """graph 成功执行时 trace.success 应为 True。"""
        fw = PerceptionFlywheel(fake_graph)
        trace = fw.run("搜索论文")
        assert trace.success is True

    def test_run_extracts_concept_path(self, fake_graph):
        """run() 应从 final_state 提取 concept_path。"""
        fw = PerceptionFlywheel(fake_graph)
        trace = fw.run("搜索论文")
        assert trace.concept_path == ["L2:concept1"]

    def test_run_extracts_tool_calls(self, fake_graph):
        """run() 应从 trace 数据提取 tool_calls。"""
        fw = PerceptionFlywheel(fake_graph)
        trace = fw.run("搜索论文")
        assert len(trace.tool_calls) == 1
        assert trace.tool_calls[0]["name"] == "search_paper"

    def test_run_sets_reasoning_mode(self, fake_graph):
        """run() 应将推理模式写入 trace.mode。"""
        fw = PerceptionFlywheel(fake_graph, ReasoningMode.SELF_REFLECT)
        trace = fw.run("搜索论文")
        assert trace.mode == ReasoningMode.SELF_REFLECT

    def test_run_duration_ms_positive(self, fake_graph):
        """run() 应记录正的执行耗时。"""
        fw = PerceptionFlywheel(fake_graph)
        trace = fw.run("搜索论文")
        assert trace.duration_ms > 0

    def test_run_handles_graph_exception(self, fake_graph_failure):
        """graph 抛异常时 trace.success 应为 False。"""
        fw = PerceptionFlywheel(fake_graph_failure)
        trace = fw.run("搜索论文")
        assert trace.success is False

    def test_run_passes_session_id_in_config(self, fake_graph):
        """session_id 应通过 config 传递给 graph.invoke。"""
        fw = PerceptionFlywheel(fake_graph)
        fw.run("搜索论文", session_id="session-123")
        assert fake_graph.last_config is not None
        assert fake_graph.last_config.get("configurable", {}).get("thread_id") == "session-123"

    def test_run_without_session_id_no_config(self, fake_graph):
        """无 session_id 时 config 应为空 dict。"""
        fw = PerceptionFlywheel(fake_graph)
        fw.run("搜索论文")
        assert fake_graph.last_config == {}

    def test_run_merges_extra_config(self, fake_graph):
        """额外 config 应合并到 invoke_config。"""
        fw = PerceptionFlywheel(fake_graph)
        fw.run("搜索论文", session_id="s1", config={"recursion_limit": 25})
        assert fake_graph.last_config.get("recursion_limit") == 25
        assert fake_graph.last_config["configurable"]["thread_id"] == "s1"


class TestPerceptionFlywheelRunStream:
    """测试 PerceptionFlywheel.run_stream() 方法。"""

    def test_run_stream_yields_events(self):
        """run_stream 应 yield 传入的事件。"""
        from tests.unit.test_flywheel.conftest import FakeGraph

        events = [{"node": "perceive", "data": 1}, {"node": "search", "data": 2}]
        graph = FakeGraph(events=events)
        fw = PerceptionFlywheel(graph)
        results = list(fw.run_stream("搜索论文"))
        assert results == events

    def test_run_stream_empty_events(self):
        """无事件时应 yield 空迭代。"""
        from tests.unit.test_flywheel.conftest import FakeGraph

        graph = FakeGraph(events=[])
        fw = PerceptionFlywheel(graph)
        results = list(fw.run_stream("搜索论文"))
        assert results == []


class TestTraceSerialization:
    """测试 trace_to_dict() 与 trace_from_dict() 函数。"""

    def test_trace_to_dict_returns_dict(self, sample_trace):
        """trace_to_dict 应返回 dict。"""
        d = trace_to_dict(sample_trace)
        assert isinstance(d, dict)

    def test_trace_to_dict_contains_all_fields(self, sample_trace):
        """trace_to_dict 应包含全部字段。"""
        d = trace_to_dict(sample_trace)
        expected_keys = {
            "trace_id",
            "task_id",
            "goal",
            "mode",
            "concept_path",
            "tool_calls",
            "success",
            "duration_ms",
            "usage_tokens",
            "reflection_score",
            "created_at",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_trace_to_dict_serializes_mode_to_value(self, sample_trace):
        """trace_to_dict 应将 ReasoningMode 序列化为字符串值。"""
        d = trace_to_dict(sample_trace)
        assert d["mode"] == "react"

    def test_trace_from_dict_returns_trace_record(self, sample_trace):
        """trace_from_dict 应返回 TraceRecord 实例。"""
        d = trace_to_dict(sample_trace)
        trace = trace_from_dict(d)
        assert isinstance(trace, TraceRecord)

    def test_round_trip_preserves_fields(self, sample_trace):
        """序列化/反序列化往返应保留字段值。"""
        d = trace_to_dict(sample_trace)
        restored = trace_from_dict(d)
        assert restored.trace_id == sample_trace.trace_id
        assert restored.task_id == sample_trace.task_id
        assert restored.goal == sample_trace.goal
        assert restored.mode == sample_trace.mode
        assert restored.concept_path == sample_trace.concept_path
        assert restored.tool_calls == sample_trace.tool_calls
        assert restored.success == sample_trace.success
        assert restored.duration_ms == sample_trace.duration_ms
        assert restored.usage_tokens == sample_trace.usage_tokens
        assert restored.reflection_score == sample_trace.reflection_score
        assert restored.created_at == sample_trace.created_at

    def test_trace_from_dict_invalid_mode_defaults_react(self):
        """无效的 mode 字符串应回退为 REACT。"""
        d = {
            "trace_id": "t1",
            "task_id": "tk1",
            "goal": "test",
            "mode": "invalid_mode",
        }
        trace = trace_from_dict(d)
        assert trace.mode == ReasoningMode.REACT

    def test_trace_from_dict_missing_optional_fields(self):
        """缺失可选字段时应使用默认值。"""
        d = {
            "trace_id": "t1",
            "task_id": "tk1",
            "goal": "test",
            "mode": "react",
        }
        trace = trace_from_dict(d)
        assert trace.concept_path == []
        assert trace.tool_calls == []
        assert trace.success is False
        assert trace.duration_ms == 0.0
        assert trace.usage_tokens == 0
        assert trace.reflection_score == 0.0
