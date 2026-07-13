"""
LangGraph 节点函数单元测试。

测试模块: fnixagent.graph.nodes
覆盖:
    - perceive_node: 意图感知
    - make_search_node: 检索节点(闭包)
    - make_skill_select_node: 技能选择节点(闭包)
    - make_execute_node: 执行节点(闭包)
    - reflect_node: 反思节点
    - 节点名称常量
"""
import pytest

from fnixagent.graph.nodes import (
    NODE_EXECUTE,
    NODE_PERCEIVE,
    NODE_REFLECT,
    NODE_SEARCH,
    NODE_SKILL_SELECT,
    make_execute_node,
    make_search_node,
    make_skill_select_node,
    perceive_node,
    reflect_node,
)
from fnixagent.graph.state import create_initial_state


# ---------------------------------------------------------------------------
# 节点名称常量
# ---------------------------------------------------------------------------

class TestNodeConstants:
    """测试节点名称常量。"""

    def test_node_constants_are_strings(self):
        """节点名称常量应为字符串。"""
        assert NODE_PERCEIVE == "perceive"
        assert NODE_SEARCH == "search"
        assert NODE_SKILL_SELECT == "skill_select"
        assert NODE_EXECUTE == "execute"
        assert NODE_REFLECT == "reflect"

    def test_node_constants_unique(self):
        """节点名称常量应互不相同。"""
        names = {NODE_PERCEIVE, NODE_SEARCH, NODE_SKILL_SELECT, NODE_EXECUTE, NODE_REFLECT}
        assert len(names) == 5


# ---------------------------------------------------------------------------
# perceive_node
# ---------------------------------------------------------------------------

class TestPerceiveNode:
    """测试 perceive_node() 函数。"""

    def test_sets_current_goal(self):
        """perceive_node 应将 user_input 设为 current_goal。"""
        state = create_initial_state("搜索论文")
        result = perceive_node(state)
        assert result["current_goal"] == "搜索论文"

    def test_extracts_keywords_from_spaces(self):
        """perceive_node 应按空格分词提取关键词(长度>1)。"""
        state = create_initial_state("search GPT-4 papers")
        result = perceive_node(state)
        assert "search" in result["intent_keywords"]
        assert "GPT-4" in result["intent_keywords"]
        assert "papers" in result["intent_keywords"]

    def test_filters_short_keywords(self):
        """长度<=1 的词应被过滤。"""
        state = create_initial_state("a bb ccc")
        result = perceive_node(state)
        assert "a" not in result["intent_keywords"]
        assert "bb" in result["intent_keywords"]
        assert "ccc" in result["intent_keywords"]

    def test_creates_trace_when_empty(self):
        """state 中无 trace 时应创建新 trace。"""
        state = create_initial_state("搜索论文")
        result = perceive_node(state)
        trace = result["trace"]
        assert "trace_id" in trace
        assert "task_id" in trace
        assert trace["goal"] == "搜索论文"
        assert trace["success"] is False

    def test_updates_existing_trace_goal(self):
        """state 中已有 trace 时应更新 goal 字段。"""
        state = create_initial_state("搜索论文")
        state["trace"] = {"trace_id": "fixed-id", "goal": "old"}
        result = perceive_node(state)
        assert result["trace"]["trace_id"] == "fixed-id"
        assert result["trace"]["goal"] == "搜索论文"

    def test_returns_partial_update_keys(self):
        """返回的 dict 应包含 current_goal/intent_keywords/trace。"""
        state = create_initial_state("test")
        result = perceive_node(state)
        assert set(result.keys()) == {"current_goal", "intent_keywords", "trace"}


# ---------------------------------------------------------------------------
# make_search_node
# ---------------------------------------------------------------------------

class TestSearchNode:
    """测试 make_search_node() 闭包。"""

    def test_returns_callable(self, mock_search):
        """make_search_node 应返回可调用对象。"""
        node = make_search_node(mock_search)
        assert callable(node)

    def test_calls_search_engine(self, mock_search):
        """search_node 应调用 search_engine.search。"""
        node = make_search_node(mock_search)
        state = create_initial_state("搜索论文")
        state["current_goal"] = "搜索论文"
        node(state)
        assert mock_search.call_count == 1

    def test_uses_current_goal_as_query(self, mock_search):
        """search_node 应优先使用 current_goal 作为查询。"""
        node = make_search_node(mock_search)
        state = create_initial_state("原始输入")
        state["current_goal"] = "解析后的目标"
        node(state)
        assert mock_search.last_query == "解析后的目标"

    def test_falls_back_to_user_input(self, mock_search):
        """current_goal key 缺失时应使用 user_input 作为查询。"""
        node = make_search_node(mock_search)
        state = create_initial_state("用户输入")
        # search_node 使用 state.get("current_goal", fallback)，
        # 仅当 current_goal key 不存在时才回退(空字符串视为有效值)
        del state["current_goal"]
        node(state)
        assert mock_search.last_query == "用户输入"

    def test_passes_keywords(self, mock_search):
        """search_node 应传递 intent_keywords。"""
        node = make_search_node(mock_search)
        state = create_initial_state("test")
        state["current_goal"] = "test"
        state["intent_keywords"] = ["kw1", "kw2"]
        node(state)
        assert mock_search.last_keywords == ["kw1", "kw2"]

    def test_serializes_paths(self, mock_search):
        """search_node 应将 TopologyPath 序列化为 dict。"""
        node = make_search_node(mock_search)
        state = create_initial_state("test")
        state["current_goal"] = "test"
        result = node(state)
        assert len(result["topology_paths"]) == 1
        path_data = result["topology_paths"][0]
        assert path_data["nodes"] == ["L2:concept1", "L3:rule1"]
        assert path_data["edges"] == ["e1", "e2"]
        assert path_data["total_weight"] == 0.75
        assert path_data["depth"] == 2

    def test_extracts_concept_path(self, mock_search):
        """search_node 应提取路径中的节点 ID 作为 concept_path。"""
        node = make_search_node(mock_search)
        state = create_initial_state("test")
        state["current_goal"] = "test"
        result = node(state)
        assert "L2:concept1" in result["concept_path"]
        assert "L3:rule1" in result["concept_path"]

    def test_updates_trace_concept_path(self, mock_search):
        """search_node 应更新 trace 中的 concept_path。"""
        node = make_search_node(mock_search)
        state = create_initial_state("test")
        state["current_goal"] = "test"
        state["trace"] = {"trace_id": "t1"}
        result = node(state)
        assert result["trace"]["concept_path"] == ["L2:concept1", "L3:rule1"]

    def test_empty_paths_returns_empty_lists(self):
        """搜索引擎返回空路径时,concept_path 与 topology_paths 应为空。"""
        from tests.unit.test_graph.conftest import FakeSearchEngine
        empty_search = FakeSearchEngine(paths=[])
        node = make_search_node(empty_search)
        state = create_initial_state("test")
        state["current_goal"] = "test"
        result = node(state)
        assert result["concept_path"] == []
        assert result["topology_paths"] == []


# ---------------------------------------------------------------------------
# make_skill_select_node
# ---------------------------------------------------------------------------

class TestSkillSelectNode:
    """测试 make_skill_select_node() 闭包。"""

    def test_returns_callable(self, mock_scheduler):
        """make_skill_select_node 应返回可调用对象。"""
        node = make_skill_select_node(mock_scheduler)
        assert callable(node)

    def test_calls_scheduler_select_skills(self, mock_scheduler):
        """skill_select_node 应调用 scheduler.select_skills。"""
        node = make_skill_select_node(mock_scheduler)
        state = create_initial_state("test")
        state["topology_paths"] = [
            {"nodes": ["L2:c1"], "edges": ["e1"], "total_weight": 0.5, "depth": 1}
        ]
        node(state)
        assert mock_scheduler.call_count == 1
        assert mock_scheduler.last_top_k == 5

    def test_returns_skill_names(self, mock_scheduler):
        """skill_select_node 应返回技能名列表。"""
        node = make_skill_select_node(mock_scheduler)
        state = create_initial_state("test")
        state["topology_paths"] = [
            {"nodes": ["L2:c1"], "edges": ["e1"], "total_weight": 0.5, "depth": 1}
        ]
        result = node(state)
        assert result["selected_skills"] == ["search_paper"]

    def test_uses_binding_protocol_when_provided(self, mock_scheduler, mock_binding_protocol):
        """提供 binding_protocol 时应调用 compute_priority。"""
        node = make_skill_select_node(mock_scheduler, mock_binding_protocol)
        state = create_initial_state("test")
        state["topology_paths"] = [
            {"nodes": ["L2:c1"], "edges": ["e1"], "total_weight": 0.5, "depth": 1}
        ]
        result = node(state)
        assert mock_binding_protocol.call_count == 1
        assert result["skill_priorities"]["search_paper"] == 0.85

    def test_uses_tool_priority_without_binding(self, mock_scheduler):
        """无 binding_protocol 时应使用 tool_meta.priority。"""
        node = make_skill_select_node(mock_scheduler, None)
        state = create_initial_state("test")
        state["topology_paths"] = [
            {"nodes": ["L2:c1"], "edges": ["e1"], "total_weight": 0.5, "depth": 1}
        ]
        result = node(state)
        assert result["skill_priorities"]["search_paper"] == 0.7

    def test_handles_empty_topology_paths(self, mock_scheduler):
        """topology_paths 为空时应正常调用 scheduler(path=None)。"""
        node = make_skill_select_node(mock_scheduler)
        state = create_initial_state("test")
        state["topology_paths"] = []
        result = node(state)
        assert mock_scheduler.last_path is None
        assert result["selected_skills"] == ["search_paper"]


# ---------------------------------------------------------------------------
# make_execute_node
# ---------------------------------------------------------------------------

class TestExecuteNode:
    """测试 make_execute_node() 闭包。"""

    def test_returns_callable(self, mock_registry):
        """make_execute_node 应返回可调用对象。"""
        node = make_execute_node(mock_registry)
        assert callable(node)

    def test_no_skills_returns_error(self, mock_registry):
        """selected_skills 为空时应返回 error。"""
        node = make_execute_node(mock_registry)
        state = create_initial_state("test")
        state["selected_skills"] = []
        result = node(state)
        assert result["tool_results"] == []
        assert result["error"] == "无可用技能"

    def test_executes_registered_skill(self, mock_registry):
        """已注册的技能应被成功执行。"""
        node = make_execute_node(mock_registry)
        state = create_initial_state("test")
        state["selected_skills"] = ["search_paper"]
        result = node(state)
        assert len(result["tool_results"]) == 1
        assert result["tool_results"][0]["status"] == "success"
        assert result["tool_results"][0]["output"] == {"papers": ["paper1", "paper2"]}

    def test_unregistered_skill_returns_failed(self, mock_registry):
        """未注册的技能应返回 failed 状态。"""
        node = make_execute_node(mock_registry)
        state = create_initial_state("test")
        state["selected_skills"] = ["nonexistent_tool"]
        result = node(state)
        assert result["tool_results"][0]["status"] == "failed"
        assert "未注册" in result["tool_results"][0]["error"]

    def test_records_tool_calls_in_trace(self, mock_registry):
        """执行成功后应在 trace 中记录 tool_calls。"""
        node = make_execute_node(mock_registry)
        state = create_initial_state("test")
        state["selected_skills"] = ["search_paper"]
        state["trace"] = {"trace_id": "t1"}
        result = node(state)
        assert len(result["trace"]["tool_calls"]) == 1
        assert result["trace"]["tool_calls"][0]["name"] == "search_paper"
        assert result["trace"]["tool_calls"][0]["status"] == "success"

    def test_uses_executor_when_provided(self, mock_registry):
        """提供 executor 时应使用 executor.execute 而非 tool.func。"""
        class FakeExecutor:
            def __init__(self):
                self.call_count = 0
                self.last_name = None

            def execute(self, name, args):
                self.call_count += 1
                self.last_name = name
                return {"executed_by": "executor"}

        executor = FakeExecutor()
        node = make_execute_node(mock_registry, executor)
        state = create_initial_state("test")
        state["selected_skills"] = ["search_paper"]
        result = node(state)
        assert executor.call_count == 1
        assert executor.last_name == "search_paper"
        assert result["tool_results"][0]["output"] == {"executed_by": "executor"}

    def test_multiple_skills_execution(self, mock_registry):
        """多个技能应依次执行。"""
        from fnixagent.core.tools.protocol import ToolMetadata
        from fnixagent.core.types import ToolPermission

        def analyze_data(args):
            return {"analysis": "done"}

        mock_registry.register(
            ToolMetadata(name="analyze_data", description="数据分析"),
            analyze_data,
        )
        node = make_execute_node(mock_registry)
        state = create_initial_state("test")
        state["selected_skills"] = ["search_paper", "analyze_data"]
        result = node(state)
        assert len(result["tool_results"]) == 2
        assert result["tool_results"][0]["status"] == "success"
        assert result["tool_results"][1]["status"] == "success"


# ---------------------------------------------------------------------------
# reflect_node
# ---------------------------------------------------------------------------

class TestReflectNode:
    """测试 reflect_node() 函数。"""

    def test_all_success_stops_loop(self):
        """全部工具成功时应停止循环并生成最终答案。"""
        state = {
            "iteration": 0,
            "tool_results": [{"status": "success", "output": "结果1"}],
        }
        result = reflect_node(state)
        assert result["should_continue"] is False
        assert "结果1" in result["final_answer"]

    def test_all_success_sets_trace_success(self):
        """全部成功时 trace.success 应设为 True。"""
        state = {
            "iteration": 0,
            "tool_results": [{"status": "success", "output": "ok"}],
            "trace": {"trace_id": "t1"},
        }
        result = reflect_node(state)
        assert result["trace"]["success"] is True

    def test_failure_continues_loop(self):
        """有失败且迭代未达上限时应继续循环。"""
        state = {
            "iteration": 0,
            "tool_results": [{"status": "failed", "error": "err"}],
        }
        result = reflect_node(state)
        assert result["should_continue"] is True
        assert result["iteration"] == 1

    def test_failure_increments_iteration(self):
        """继续循环时 iteration 应 +1。"""
        state = {
            "iteration": 3,
            "tool_results": [{"status": "failed"}],
        }
        result = reflect_node(state)
        assert result["iteration"] == 4

    def test_max_iterations_stops_loop(self):
        """迭代达到上限时应停止循环并返回错误。"""
        state = {
            "iteration": 10,
            "tool_results": [{"status": "failed"}],
        }
        result = reflect_node(state)
        assert result["should_continue"] is False
        assert result["error"] == "max_iterations_exceeded"
        assert "10" in result["final_answer"]

    def test_max_iterations_sets_trace_failure(self):
        """达到上限时 trace.success 应设为 False。"""
        state = {
            "iteration": 10,
            "tool_results": [{"status": "failed"}],
            "trace": {"trace_id": "t1"},
        }
        result = reflect_node(state)
        assert result["trace"]["success"] is False

    def test_empty_tool_results_continues_loop(self):
        """无工具结果时应继续循环(非全部成功)。"""
        state = {
            "iteration": 0,
            "tool_results": [],
        }
        result = reflect_node(state)
        assert result["should_continue"] is True

    def test_final_answer_joins_multiple_outputs(self):
        """多个成功结果应拼接为最终答案。"""
        state = {
            "iteration": 0,
            "tool_results": [
                {"status": "success", "output": "A"},
                {"status": "success", "output": "B"},
            ],
        }
        result = reflect_node(state)
        assert "A" in result["final_answer"]
        assert "B" in result["final_answer"]
