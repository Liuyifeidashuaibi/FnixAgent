"""
LangGraph 图装配与编译单元测试。

测试模块: fnixagent.graph.builder.GraphBuilder
覆盖:
    - GraphBuilder.build(): 装配并编译图
    - GraphBuilder.build_with_checkpointer(): 带检查点的图
    - 图的 invoke 端到端执行(使用 mock 组件)
"""
import pytest

from fnixagent.graph.builder import GraphBuilder
from fnixagent.graph.state import create_initial_state


class TestGraphBuilderInit:
    """测试 GraphBuilder 初始化。"""

    def test_init_stores_dependencies(self, mock_search, mock_scheduler, mock_registry):
        """GraphBuilder 应存储传入的依赖。"""
        builder = GraphBuilder(
            search_engine=mock_search,
            scheduler=mock_scheduler,
            registry=mock_registry,
        )
        assert builder._search_engine is mock_search
        assert builder._scheduler is mock_scheduler
        assert builder._registry is mock_registry

    def test_init_with_optional_dependencies(
        self, mock_search, mock_scheduler, mock_registry, mock_binding_protocol
    ):
        """GraphBuilder 应存储可选依赖。"""
        builder = GraphBuilder(
            search_engine=mock_search,
            scheduler=mock_scheduler,
            registry=mock_registry,
            binding_protocol=mock_binding_protocol,
        )
        assert builder._binding_protocol is mock_binding_protocol
        assert builder._executor is None


class TestGraphBuilderBuild:
    """测试 GraphBuilder.build() 方法。"""

    def test_build_returns_compiled_graph(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """build() 应返回编译后的图实例(非 None)。"""
        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build()
        assert graph is not None

    def test_built_graph_has_invoke_method(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """编译后的图应具有 invoke 方法。"""
        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build()
        assert hasattr(graph, "invoke")
        assert callable(graph.invoke)

    def test_built_graph_has_stream_method(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """编译后的图应具有 stream 方法。"""
        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build()
        assert hasattr(graph, "stream")

    def test_invoke_completes_full_pipeline(
        self, mock_search, mock_scheduler, mock_registry, mock_binding_protocol
    ):
        """使用 mock 组件 invoke 应完成完整流水线(感知→检索→选技能→执行→反思)。"""
        builder = GraphBuilder(
            mock_search, mock_scheduler, mock_registry, mock_binding_protocol
        )
        graph = builder.build()
        initial_state = create_initial_state("搜索论文")
        result = graph.invoke(initial_state)
        # 反思节点应设置 should_continue=False(全部成功)
        assert result.get("should_continue") is False
        # 应有最终答案
        assert result.get("final_answer")
        # 应执行了工具
        assert len(result.get("tool_results", [])) > 0

    def test_invoke_calls_search_engine(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """invoke 应触发 search_engine.search 调用。"""
        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build()
        graph.invoke(create_initial_state("搜索论文"))
        assert mock_search.call_count >= 1

    def test_invoke_calls_scheduler(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """invoke 应触发 scheduler.select_skills 调用。"""
        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build()
        graph.invoke(create_initial_state("搜索论文"))
        assert mock_scheduler.call_count >= 1

    def test_invoke_executes_tool(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """invoke 应执行已注册的工具并产出 tool_results。"""
        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build()
        result = graph.invoke(create_initial_state("搜索论文"))
        tool_results = result.get("tool_results", [])
        assert len(tool_results) == 1
        assert tool_results[0]["status"] == "success"
        assert tool_results[0]["output"] == {"papers": ["paper1", "paper2"]}


class TestGraphBuilderBuildWithCheckpointer:
    """测试 GraphBuilder.build_with_checkpointer() 方法。"""

    def test_build_with_memory_checkpointer(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """使用 MemorySaver 检查点应成功编译图。"""
        from langgraph.checkpoint.memory import MemorySaver

        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build_with_checkpointer(MemorySaver())
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_build_with_default_checkpointer(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """checkpointer=None 时应使用默认内存检查点。"""
        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build_with_checkpointer(None)
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_invoke_with_checkpointer_and_thread_id(
        self, mock_search, mock_scheduler, mock_registry
    ):
        """带检查点的图应支持 thread_id 配置。"""
        from langgraph.checkpoint.memory import MemorySaver

        builder = GraphBuilder(mock_search, mock_scheduler, mock_registry)
        graph = builder.build_with_checkpointer(MemorySaver())
        result = graph.invoke(
            create_initial_state("搜索论文"),
            config={"configurable": {"thread_id": "test-thread-1"}},
        )
        assert result.get("should_continue") is False
