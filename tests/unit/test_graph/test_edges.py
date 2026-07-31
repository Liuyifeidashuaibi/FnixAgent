"""
LangGraph 条件边路由函数单元测试。

测试模块: fnixagent.graph.edges
覆盖:
    - route_after_reflect: 反思后路由(循环回感知 vs 结束)
    - should_stop_on_error: 错误检查路由
    - 边名称常量
"""

from fnixagent.graph.edges import (
    EDGE_LOOP_BACK,
    EDGE_TO_END,
    EDGE_TO_EXECUTE,
    EDGE_TO_REFLECT,
    EDGE_TO_SEARCH,
    EDGE_TO_SKILL_SELECT,
    route_after_reflect,
    should_stop_on_error,
)

# ---------------------------------------------------------------------------
# 边名称常量
# ---------------------------------------------------------------------------


class TestEdgeConstants:
    """测试边名称常量。"""

    def test_edge_constants_values(self):
        """边名称常量应具有预期值。"""
        assert EDGE_TO_SEARCH == "to_search"
        assert EDGE_TO_SKILL_SELECT == "to_skill_select"
        assert EDGE_TO_EXECUTE == "to_execute"
        assert EDGE_TO_REFLECT == "to_reflect"
        assert EDGE_LOOP_BACK == "loop_back"
        assert EDGE_TO_END == "to_end"

    def test_edge_constants_unique(self):
        """边名称常量应互不相同。"""
        edges = {
            EDGE_TO_SEARCH,
            EDGE_TO_SKILL_SELECT,
            EDGE_TO_EXECUTE,
            EDGE_TO_REFLECT,
            EDGE_LOOP_BACK,
            EDGE_TO_END,
        }
        assert len(edges) == 6


# ---------------------------------------------------------------------------
# route_after_reflect
# ---------------------------------------------------------------------------


class TestRouteAfterReflect:
    """测试 route_after_reflect() 函数。"""

    def test_should_continue_true_returns_loop_back(self):
        """should_continue=True 时应返回 loop_back。"""
        state = {"should_continue": True}
        assert route_after_reflect(state) == EDGE_LOOP_BACK

    def test_should_continue_false_returns_to_end(self):
        """should_continue=False 时应返回 to_end。"""
        state = {"should_continue": False}
        assert route_after_reflect(state) == EDGE_TO_END

    def test_missing_should_continue_defaults_to_end(self):
        """should_continue 缺失时(默认 False)应返回 to_end。"""
        state = {}
        assert route_after_reflect(state) == EDGE_TO_END

    def test_returns_string(self):
        """返回值应为字符串。"""
        state = {"should_continue": True}
        result = route_after_reflect(state)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# should_stop_on_error
# ---------------------------------------------------------------------------


class TestShouldStopOnError:
    """测试 should_stop_on_error() 函数。"""

    def test_max_iterations_error_returns_to_end(self):
        """error=max_iterations_exceeded 时应返回 to_end。"""
        state = {"error": "max_iterations_exceeded"}
        assert should_stop_on_error(state) == EDGE_TO_END

    def test_no_error_returns_continue(self):
        """无 error 时应返回 continue。"""
        state = {"error": None}
        assert should_stop_on_error(state) == "continue"

    def test_missing_error_returns_continue(self):
        """error 字段缺失时应返回 continue。"""
        state = {}
        assert should_stop_on_error(state) == "continue"

    def test_other_error_returns_continue(self):
        """非 max_iterations_exceeded 的其他错误应返回 continue。"""
        state = {"error": "some_other_error"}
        assert should_stop_on_error(state) == "continue"

    def test_empty_string_error_returns_continue(self):
        """error 为空字符串时应返回 continue。"""
        state = {"error": ""}
        assert should_stop_on_error(state) == "continue"

    def test_returns_string(self):
        """返回值应为字符串。"""
        state = {"error": None}
        result = should_stop_on_error(state)
        assert isinstance(result, str)
