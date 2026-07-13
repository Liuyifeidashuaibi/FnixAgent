"""
知识拓扑图 (KTG) 路径搜索单元测试。

测试模块: fnixagent.core.topology.search.TopologySearch
覆盖:
    - match_concepts(): 意图匹配 L2 概念节点
    - search(): BFS 权重优先路径搜索
    - check_constraints(): 路径约束检查
    - is_cold_start(): 冷启动检测
    - search_stats(): 搜索统计
"""
import pytest

from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.topology.search import TopologySearch
from fnixagent.core.types import (
    EdgeType,
    NodeType,
    TopologyLayer,
    TopologyPath,
)


# ---------------------------------------------------------------------------
# match_concepts
# ---------------------------------------------------------------------------

class TestMatchConcepts:
    """测试 match_concepts() 方法。"""

    def test_match_by_query_substring(self, sample_graph):
        """用 query 子串匹配概念节点名称。"""
        search = TopologySearch(sample_graph)
        matched = search.match_concepts("文献检索", keywords=None)
        # 不传 keywords 时,用 query 本身做子串匹配
        assert len(matched) == 1
        assert matched[0].name == "文献检索"

    def test_match_by_keywords(self, sample_graph):
        """用关键词列表匹配概念节点。"""
        search = TopologySearch(sample_graph)
        matched = search.match_concepts("无关查询", keywords=["文献"])
        assert len(matched) == 1
        assert matched[0].node_id == "L2:concept1"

    def test_match_by_content(self, sample_graph):
        """关键词可匹配节点 content。"""
        search = TopologySearch(sample_graph)
        matched = search.match_concepts("any", keywords=["检索相关"])
        assert len(matched) == 1

    def test_no_match(self, sample_graph):
        """无匹配时返回空列表。"""
        search = TopologySearch(sample_graph)
        matched = search.match_concepts("完全不相关的内容")
        assert matched == []

    def test_no_match_with_keywords(self, sample_graph):
        """关键词无匹配时返回空列表。"""
        search = TopologySearch(sample_graph)
        matched = search.match_concepts("any", keywords=["不存在的关键词"])
        assert matched == []

    def test_empty_graph(self, empty_graph):
        """空图匹配应返回空列表。"""
        search = TopologySearch(empty_graph)
        assert search.match_concepts("anything") == []

    def test_sorted_by_weight_descending(self, empty_graph):
        """匹配结果应按权重降序排列。"""
        # 添加两个 CONCEPT 节点,权重不同
        n1 = empty_graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="搜索",
            node_id="L2:c1",
        )
        n2 = empty_graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="搜索高级",
            node_id="L2:c2",
        )
        # 调整权重:n2 权重高于 n1
        n1.weight = 0.3
        n2.weight = 0.8

        search = TopologySearch(empty_graph)
        matched = search.match_concepts("搜索")
        assert len(matched) == 2
        assert matched[0].weight >= matched[1].weight
        assert matched[0].node_id == "L2:c2"

    def test_deprecated_excluded(self, sample_graph):
        """废弃的概念节点不应出现在匹配结果中。"""
        sample_graph.deprecate_node("L2:concept1")
        search = TopologySearch(sample_graph)
        matched = search.match_concepts("文献检索")
        assert matched == []

    def test_case_insensitive_match(self, empty_graph):
        """匹配应不区分大小写。"""
        empty_graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="Search Engine",
            node_id="L2:c1",
        )
        search = TopologySearch(empty_graph)
        matched = search.match_concepts("search")
        assert len(matched) == 1


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearch:
    """测试 search() 方法。"""

    def test_search_returns_paths(self, sample_graph):
        """正常搜索应返回路径列表。"""
        search = TopologySearch(sample_graph)
        paths = search.search("文献检索")
        assert len(paths) > 0
        for path in paths:
            assert isinstance(path, TopologyPath)
            assert path.depth > 0
            assert len(path.nodes) > 1

    def test_search_path_starts_from_concept(self, sample_graph):
        """搜索路径应从 L2 概念节点开始。"""
        search = TopologySearch(sample_graph)
        paths = search.search("文献检索")
        assert len(paths) > 0
        for path in paths:
            first_node = sample_graph.get_node(path.nodes[0])
            assert first_node.layer == TopologyLayer.L2_CONCEPT

    def test_search_path_reaches_l4(self, sample_graph):
        """搜索路径应能到达 L4 事实层。"""
        search = TopologySearch(sample_graph)
        paths = search.search("文献检索")
        assert len(paths) > 0
        for path in paths:
            last_node = sample_graph.get_node(path.nodes[-1])
            assert last_node.layer == TopologyLayer.L4_FACT

    def test_search_sorted_by_weight_descending(self, sample_graph):
        """搜索结果应按路径权重降序排列。"""
        search = TopologySearch(sample_graph)
        paths = search.search("文献检索")
        assert len(paths) > 1
        for i in range(len(paths) - 1):
            assert paths[i].total_weight >= paths[i + 1].total_weight

    def test_search_top_k_default(self, sample_graph):
        """默认 top_k=3 应限制返回路径数。"""
        search = TopologySearch(sample_graph, top_k=3)
        paths = search.search("文献检索")
        assert len(paths) <= 3

    def test_search_top_k_override(self, sample_graph):
        """top_k 参数应覆盖默认值。"""
        search = TopologySearch(sample_graph, top_k=3)
        paths = search.search("文献检索", top_k=1)
        assert len(paths) <= 1

    def test_search_no_match_returns_empty(self, sample_graph):
        """无匹配概念时返回空列表(冷启动回退)。"""
        search = TopologySearch(sample_graph)
        paths = search.search("完全不相关的内容")
        assert paths == []

    def test_search_empty_graph(self, empty_graph):
        """空图搜索应返回空列表。"""
        search = TopologySearch(empty_graph)
        assert search.search("anything") == []

    def test_search_min_weight_filter(self, sample_graph):
        """低于 min_weight 的路径应被过滤。"""
        search = TopologySearch(sample_graph, min_weight=0.95)
        paths = search.search("文献检索")
        # sample_graph 中最高路径权重为 0.9,低于 0.95
        for path in paths:
            assert path.total_weight >= 0.95
        # 可能全部被过滤
        # 最强路径: 1.0 * (0.3+0.3+0.3) = 0.9,所以 min_weight=0.95 会过滤掉所有路径

    def test_search_min_weight_low_threshold(self, sample_graph):
        """较低的 min_weight 阈值应保留路径。"""
        search = TopologySearch(sample_graph, min_weight=0.01)
        paths = search.search("文献检索")
        assert len(paths) > 0

    def test_search_with_keywords(self, sample_graph):
        """使用关键词搜索应正常返回路径。"""
        search = TopologySearch(sample_graph)
        paths = search.search("any", keywords=["文献"])
        assert len(paths) > 0

    def test_search_max_depth_limit(self, sample_graph):
        """max_depth=1 应限制路径深度为 1。"""
        search = TopologySearch(sample_graph, max_depth=1)
        paths = search.search("文献检索")
        for path in paths:
            assert path.depth <= 1

    def test_search_deprecated_edge_excluded(self, sample_graph):
        """废弃的边不应出现在搜索路径中。"""
        # 废弃所有从 L2 到 L3 的 CONTAINS 边
        sample_graph.deprecate_edge("e2")
        search = TopologySearch(sample_graph)
        paths = search.search("文献检索")
        for path in paths:
            assert "e2" not in path.edges

    def test_search_deprecated_target_excluded(self, sample_graph):
        """废弃的目标节点不应出现在搜索路径中。"""
        sample_graph.deprecate_node("L3:rule1")
        search = TopologySearch(sample_graph)
        paths = search.search("文献检索")
        # L3:rule1 废弃后,从 L2 无法展开到 L3
        for path in paths:
            assert "L3:rule1" not in path.nodes


# ---------------------------------------------------------------------------
# check_constraints
# ---------------------------------------------------------------------------

class TestCheckConstraints:
    """测试 check_constraints() 方法。"""

    @staticmethod
    def _build_constraint_graph():
        """构建含 CONSTRAINT 节点的测试图。

        结构:
            L2:concept1 → L3:constraint1 (CONSTRAINT, threshold=10)
        """
        graph = TopologyGraph()
        graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="概念",
            node_id="L2:c1",
        )
        graph.add_node(
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.CONSTRAINT,
            name="数量上限约束",
            content="count 不得超过 10",
            node_id="L3:con1",
            metadata={"threshold": 10, "rule_type": "count"},
        )
        graph.add_edge(
            "L2:c1", "L3:con1", EdgeType.DEPENDS_ON, weight=0.5, edge_id="e1"
        )
        return graph

    def test_no_constraint_nodes(self, sample_graph):
        """路径无 CONSTRAINT 节点时应通过。"""
        search = TopologySearch(sample_graph)
        path = TopologyPath(nodes=["L2:concept1", "L3:rule1"], edges=["e2"])
        passed, reason = search.check_constraints(path, {})
        assert passed is True
        assert reason == ""

    def test_constraint_satisfied(self):
        """CONSTRAINT 节点的阈值满足时应通过。"""
        graph = self._build_constraint_graph()
        search = TopologySearch(graph)
        path = TopologyPath(nodes=["L2:c1", "L3:con1"], edges=["e1"])
        # context count=5, threshold=10, 5 > 10? No → 通过
        passed, reason = search.check_constraints(path, {"count": 5})
        assert passed is True
        assert reason == ""

    def test_constraint_violated(self):
        """CONSTRAINT 节点的阈值被超过时应不通过。"""
        graph = self._build_constraint_graph()
        search = TopologySearch(graph)
        path = TopologyPath(nodes=["L2:c1", "L3:con1"], edges=["e1"])
        # context count=15, threshold=10, 15 > 10? Yes → 不通过
        passed, reason = search.check_constraints(path, {"count": 15})
        assert passed is False
        assert "不满足" in reason
        assert "15" in reason

    def test_constraint_at_boundary(self):
        """context 值等于阈值时应通过(严格大于才失败)。"""
        graph = self._build_constraint_graph()
        search = TopologySearch(graph)
        path = TopologyPath(nodes=["L2:c1", "L3:con1"], edges=["e1"])
        # context count=10, threshold=10, 10 > 10? No → 通过
        passed, reason = search.check_constraints(path, {"count": 10})
        assert passed is True

    def test_constraint_no_context(self):
        """无 context 时应通过。"""
        graph = self._build_constraint_graph()
        search = TopologySearch(graph)
        path = TopologyPath(nodes=["L2:c1", "L3:con1"], edges=["e1"])
        passed, reason = search.check_constraints(path, None)
        assert passed is True
        assert reason == ""

    def test_constraint_context_missing_field(self):
        """context 缺少对应字段时应通过。"""
        graph = self._build_constraint_graph()
        search = TopologySearch(graph)
        path = TopologyPath(nodes=["L2:c1", "L3:con1"], edges=["e1"])
        # context 有其他字段但没有 count
        passed, reason = search.check_constraints(path, {"other": 100})
        assert passed is True

    def test_path_with_nonexistent_node(self, sample_graph):
        """路径含不存在的节点时应跳过(不报错)。"""
        search = TopologySearch(sample_graph)
        path = TopologyPath(
            nodes=["L2:concept1", "L3:nonexistent"], edges=["e2"]
        )
        passed, reason = search.check_constraints(path, {})
        assert passed is True

    def test_empty_path(self, sample_graph):
        """空路径应通过约束检查。"""
        search = TopologySearch(sample_graph)
        path = TopologyPath()
        passed, reason = search.check_constraints(path, {})
        assert passed is True


# ---------------------------------------------------------------------------
# is_cold_start
# ---------------------------------------------------------------------------

class TestIsColdStart:
    """测试 is_cold_start() 方法。"""

    def test_cold_start_with_few_concepts(self, sample_graph):
        """概念节点 < 5 时应判定为冷启动。"""
        search = TopologySearch(sample_graph)
        # sample_graph 只有 1 个 CONCEPT 节点
        assert search.is_cold_start() is True

    def test_cold_start_empty_graph(self, empty_graph):
        """空图应判定为冷启动。"""
        search = TopologySearch(empty_graph)
        assert search.is_cold_start() is True

    def test_not_cold_start_with_enough_concepts(self, empty_graph):
        """概念节点 >= 5 时不应判定为冷启动。"""
        for i in range(5):
            empty_graph.add_node(
                layer=TopologyLayer.L2_CONCEPT,
                node_type=NodeType.CONCEPT,
                name=f"概念{i}",
                node_id=f"L2:c{i}",
            )
        search = TopologySearch(empty_graph)
        assert search.is_cold_start() is False

    def test_cold_start_boundary_four_concepts(self, empty_graph):
        """概念节点恰好 4 个时仍为冷启动。"""
        for i in range(4):
            empty_graph.add_node(
                layer=TopologyLayer.L2_CONCEPT,
                node_type=NodeType.CONCEPT,
                name=f"概念{i}",
                node_id=f"L2:c{i}",
            )
        search = TopologySearch(empty_graph)
        assert search.is_cold_start() is True

    def test_not_cold_start_excludes_deprecated(self, empty_graph):
        """废弃的概念节点不计入冷启动判断。"""
        for i in range(5):
            empty_graph.add_node(
                layer=TopologyLayer.L2_CONCEPT,
                node_type=NodeType.CONCEPT,
                name=f"概念{i}",
                node_id=f"L2:c{i}",
            )
        # 废弃一个,有效概念数 4 < 5
        empty_graph.deprecate_node("L2:c0")
        search = TopologySearch(empty_graph)
        assert search.is_cold_start() is True


# ---------------------------------------------------------------------------
# search_stats
# ---------------------------------------------------------------------------

class TestSearchStats:
    """测试 search_stats() 方法。"""

    def test_stats_structure(self, sample_graph):
        """search_stats 应返回包含全部键的字典。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("文献检索")
        expected_keys = {
            "query",
            "matched_concepts",
            "concept_names",
            "found_paths",
            "top_path_weight",
            "is_cold_start",
        }
        assert expected_keys.issubset(set(stats.keys()))

    def test_stats_query(self, sample_graph):
        """stats 中的 query 应与输入一致。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("文献检索")
        assert stats["query"] == "文献检索"

    def test_stats_matched_concepts(self, sample_graph):
        """stats 中 matched_concepts 应为匹配数。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("文献检索")
        assert stats["matched_concepts"] == 1

    def test_stats_concept_names(self, sample_graph):
        """stats 中 concept_names 应包含匹配概念名。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("文献检索")
        assert "文献检索" in stats["concept_names"]

    def test_stats_found_paths(self, sample_graph):
        """stats 中 found_paths 应为搜索到的路径数。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("文献检索")
        assert stats["found_paths"] > 0

    def test_stats_top_path_weight(self, sample_graph):
        """stats 中 top_path_weight 应为最高路径权重。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("文献检索")
        assert stats["top_path_weight"] > 0.0

    def test_stats_is_cold_start(self, sample_graph):
        """stats 中 is_cold_start 应反映冷启动状态。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("文献检索")
        assert stats["is_cold_start"] is True  # 只有 1 个概念

    def test_stats_no_match(self, sample_graph):
        """无匹配时 stats 应正确反映。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("完全不相关")
        assert stats["matched_concepts"] == 0
        assert stats["found_paths"] == 0
        assert stats["top_path_weight"] == 0.0

    def test_stats_empty_graph(self, empty_graph):
        """空图 stats 应正确反映。"""
        search = TopologySearch(empty_graph)
        stats = search.search_stats("anything")
        assert stats["matched_concepts"] == 0
        assert stats["found_paths"] == 0
        assert stats["top_path_weight"] == 0.0
        assert stats["is_cold_start"] is True

    def test_stats_with_keywords(self, sample_graph):
        """使用关键词时 stats 应正确反映。"""
        search = TopologySearch(sample_graph)
        stats = search.search_stats("any", keywords=["文献"])
        assert stats["matched_concepts"] == 1
        assert stats["found_paths"] > 0
