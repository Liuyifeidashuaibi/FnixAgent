"""
AgentState 与 create_initial_state 单元测试。

测试模块: fnixagent.graph.state
覆盖:
    - AgentState TypedDict 构造
    - create_initial_state 字段初始化
    - create_initial_state 消息历史
"""

from fnixagent.graph.state import AgentState, create_initial_state


class TestCreateInitialState:
    """测试 create_initial_state() 函数。"""

    def test_returns_dict(self):
        """create_initial_state 应返回 dict(TypedDict 实例)。"""
        state = create_initial_state("hello")
        assert isinstance(state, dict)

    def test_preserves_user_input(self):
        """user_input 字段应保留原始输入。"""
        state = create_initial_state("搜索论文")
        assert state["user_input"] == "搜索论文"

    def test_initializes_messages_with_user_role(self):
        """messages 应包含一条 role=user 的消息。"""
        state = create_initial_state("搜索论文")
        assert len(state["messages"]) == 1
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][0]["content"] == "搜索论文"

    def test_initializes_empty_collections(self):
        """集合类字段应初始化为空。"""
        state = create_initial_state("test")
        assert state["intent_keywords"] == []
        assert state["concept_path"] == []
        assert state["topology_paths"] == []
        assert state["selected_skills"] == []
        assert state["skill_priorities"] == {}
        assert state["tool_calls"] == []
        assert state["tool_results"] == []

    def test_initializes_control_flow_fields(self):
        """控制流字段应正确初始化。"""
        state = create_initial_state("test")
        assert state["current_goal"] == ""
        assert state["iteration"] == 0
        assert state["should_continue"] is True
        assert state["final_answer"] == ""
        assert state["error"] is None

    def test_initializes_trace_to_empty_dict(self):
        """trace 字段应初始化为空 dict。"""
        state = create_initial_state("test")
        assert state["trace"] == {}

    def test_empty_string_input(self):
        """空字符串输入应正常处理。"""
        state = create_initial_state("")
        assert state["user_input"] == ""
        assert state["messages"][0]["content"] == ""


class TestAgentStateTypedDict:
    """测试 AgentState TypedDict 行为。"""

    def test_partial_construction(self):
        """TypedDict(total=False) 允许部分构造。"""
        state: AgentState = {"user_input": "test"}
        assert state["user_input"] == "test"

    def test_full_construction_from_create_initial_state(self):
        """create_initial_state 产出的 state 应包含全部字段。"""
        state = create_initial_state("test")
        expected_keys = {
            "messages",
            "user_input",
            "current_goal",
            "intent_keywords",
            "concept_path",
            "topology_paths",
            "selected_skills",
            "skill_priorities",
            "tool_calls",
            "tool_results",
            "trace",
            "iteration",
            "should_continue",
            "final_answer",
            "error",
        }
        assert expected_keys.issubset(set(state.keys()))
