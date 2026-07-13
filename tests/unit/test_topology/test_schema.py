"""
知识拓扑图 (KTG) Schema 校验单元测试。

测试模块: officeagent.core.topology.schema
覆盖:
    - 固定映射常量: NODE_TYPE_LAYER_MAP, LAYER_NODE_TYPES, FIXED_WEIGHT_EDGES
    - validate_node(): 正常 / 边界 / 异常
    - validate_edge(): 正常 / 边界 / 异常(含层级约束)
    - is_valid_node_type_for_layer()
    - get_layer_for_node_type()
"""
import pytest

from officeagent.core.exceptions import (
    TopologyLayerViolationError,
    TopologyValidationError,
)
from officeagent.core.topology import schema
from officeagent.core.types import (
    EdgeType,
    NodeType,
    TopologyEdge,
    TopologyLayer,
    TopologyNode,
)


# ---------------------------------------------------------------------------
# 固定映射常量
# ---------------------------------------------------------------------------

class TestNodeLayerMappings:
    """测试节点类型与层级的固定映射。"""

    def test_node_type_layer_map_complete(self):
        """NODE_TYPE_LAYER_MAP 应包含全部 6 种节点类型。"""
        assert len(schema.NODE_TYPE_LAYER_MAP) == 6
        assert NodeType.GOAL in schema.NODE_TYPE_LAYER_MAP
        assert NodeType.CONCEPT in schema.NODE_TYPE_LAYER_MAP
        assert NodeType.RULE in schema.NODE_TYPE_LAYER_MAP
        assert NodeType.FACT in schema.NODE_TYPE_LAYER_MAP
        assert NodeType.CONSTRAINT in schema.NODE_TYPE_LAYER_MAP
        assert NodeType.INFERENCE in schema.NODE_TYPE_LAYER_MAP

    def test_node_type_layer_map_values(self):
        """每种节点类型应映射到正确的层级。"""
        assert schema.NODE_TYPE_LAYER_MAP[NodeType.GOAL] == TopologyLayer.L1_GOAL
        assert schema.NODE_TYPE_LAYER_MAP[NodeType.CONCEPT] == TopologyLayer.L2_CONCEPT
        assert schema.NODE_TYPE_LAYER_MAP[NodeType.RULE] == TopologyLayer.L3_RULE
        assert schema.NODE_TYPE_LAYER_MAP[NodeType.CONSTRAINT] == TopologyLayer.L3_RULE
        assert schema.NODE_TYPE_LAYER_MAP[NodeType.INFERENCE] == TopologyLayer.L3_RULE
        assert schema.NODE_TYPE_LAYER_MAP[NodeType.FACT] == TopologyLayer.L4_FACT

    def test_layer_node_types_complete(self):
        """LAYER_NODE_TYPES 应包含全部 4 层。"""
        assert len(schema.LAYER_NODE_TYPES) == 4

    def test_layer_node_types_values(self):
        """每层应包含正确的节点类型集合。"""
        assert schema.LAYER_NODE_TYPES[TopologyLayer.L1_GOAL] == frozenset({NodeType.GOAL})
        assert schema.LAYER_NODE_TYPES[TopologyLayer.L2_CONCEPT] == frozenset({NodeType.CONCEPT})
        assert schema.LAYER_NODE_TYPES[TopologyLayer.L3_RULE] == frozenset(
            {NodeType.RULE, NodeType.CONSTRAINT, NodeType.INFERENCE}
        )
        assert schema.LAYER_NODE_TYPES[TopologyLayer.L4_FACT] == frozenset({NodeType.FACT})

    def test_layer_node_types_are_frozenset(self):
        """LAYER_NODE_TYPES 的值应为 frozenset(不可变)。"""
        for layer, types in schema.LAYER_NODE_TYPES.items():
            assert isinstance(types, frozenset), f"{layer} 的节点类型集合应为 frozenset"


class TestFixedWeightEdges:
    """测试固定权重边类型映射。"""

    def test_fixed_weight_edges_contents(self):
        """FIXED_WEIGHT_EDGES 应包含 MUTEX(-1.0) 和 CONTAINS(1.0)。"""
        assert schema.FIXED_WEIGHT_EDGES[EdgeType.MUTEX] == -1.0
        assert schema.FIXED_WEIGHT_EDGES[EdgeType.CONTAINS] == 1.0

    def test_fixed_weight_edges_count(self):
        """FIXED_WEIGHT_EDGES 应只有 2 种边类型。"""
        assert len(schema.FIXED_WEIGHT_EDGES) == 2

    def test_variable_weight_range(self):
        """可变权重边的合法范围应为 (0.0, 1.0)。"""
        assert schema.VARIABLE_WEIGHT_RANGE == (0.0, 1.0)


# ---------------------------------------------------------------------------
# validate_node
# ---------------------------------------------------------------------------

class TestValidateNode:
    """测试 validate_node() 函数。"""

    def test_valid_goal_node(self):
        """合法的 L1 GOAL 节点应通过校验。"""
        node = TopologyNode(
            node_id="L1:g1",
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
        )
        schema.validate_node(node)  # 不抛异常即通过

    def test_valid_concept_node_with_skill(self):
        """L2 CONCEPT 节点可绑定技能,应通过校验。"""
        node = TopologyNode(
            node_id="L2:c1",
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="概念",
            skill_binding="my_skill",
        )
        schema.validate_node(node)

    def test_valid_rule_node(self):
        """合法的 L3 RULE 节点应通过校验。"""
        node = TopologyNode(
            node_id="L3:r1",
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.RULE,
            name="规则",
        )
        schema.validate_node(node)

    def test_valid_constraint_node(self):
        """合法的 L3 CONSTRAINT 节点应通过校验。"""
        node = TopologyNode(
            node_id="L3:con1",
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.CONSTRAINT,
            name="约束",
        )
        schema.validate_node(node)

    def test_valid_inference_node(self):
        """合法的 L3 INFERENCE 节点应通过校验。"""
        node = TopologyNode(
            node_id="L3:inf1",
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.INFERENCE,
            name="推理",
        )
        schema.validate_node(node)

    def test_valid_fact_node(self):
        """合法的 L4 FACT 节点应通过校验。"""
        node = TopologyNode(
            node_id="L4:f1",
            layer=TopologyLayer.L4_FACT,
            node_type=NodeType.FACT,
            name="事实",
        )
        schema.validate_node(node)

    def test_wrong_layer_for_goal(self):
        """GOAL 节点放在 L2 应抛 TopologyValidationError。"""
        node = TopologyNode(
            node_id="L2:g1",
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.GOAL,
            name="错误层级",
        )
        with pytest.raises(TopologyValidationError, match="必须属于"):
            schema.validate_node(node)

    def test_wrong_layer_for_concept(self):
        """CONCEPT 节点放在 L1 应抛 TopologyValidationError。"""
        node = TopologyNode(
            node_id="L1:c1",
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.CONCEPT,
            name="错误层级",
        )
        with pytest.raises(TopologyValidationError):
            schema.validate_node(node)

    def test_wrong_layer_for_fact(self):
        """FACT 节点放在 L3 应抛 TopologyValidationError。"""
        node = TopologyNode(
            node_id="L3:f1",
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.FACT,
            name="错误层级",
        )
        with pytest.raises(TopologyValidationError):
            schema.validate_node(node)

    def test_skill_binding_on_non_l2_node(self):
        """非 L2 节点绑定技能应抛 TopologyValidationError。"""
        node = TopologyNode(
            node_id="L1:g1",
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            skill_binding="should_fail",
        )
        with pytest.raises(TopologyValidationError, match="仅 L2 概念节点可绑定技能"):
            schema.validate_node(node)

    def test_skill_binding_on_l3_rule(self):
        """L3 RULE 节点绑定技能应抛 TopologyValidationError。"""
        node = TopologyNode(
            node_id="L3:r1",
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.RULE,
            name="规则",
            skill_binding="should_fail",
        )
        with pytest.raises(TopologyValidationError):
            schema.validate_node(node)

    def test_skill_binding_none_on_non_l2(self):
        """非 L2 节点不绑定技能(skill_binding=None)应通过校验。"""
        node = TopologyNode(
            node_id="L1:g1",
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            skill_binding=None,
        )
        schema.validate_node(node)


# ---------------------------------------------------------------------------
# validate_edge
# ---------------------------------------------------------------------------

class TestValidateEdge:
    """测试 validate_edge() 函数。"""

    @staticmethod
    def _make_node(node_id, layer, node_type):
        return TopologyNode(
            node_id=node_id,
            layer=layer,
            node_type=node_type,
            name=node_id,
        )

    def test_valid_causal_edge(self):
        """合法的 CAUSAL 边(权重在 [0,1])应通过校验。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.CAUSAL,
            weight=0.5,
        )
        schema.validate_edge(edge, source, target)

    def test_valid_depends_on_edge(self):
        """合法的 DEPENDS_ON 边应通过校验。"""
        source = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        target = self._make_node("L3:r1", TopologyLayer.L3_RULE, NodeType.RULE)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L2:c1",
            target_id="L3:r1",
            edge_type=EdgeType.DEPENDS_ON,
            weight=0.8,
        )
        schema.validate_edge(edge, source, target)

    def test_valid_mutex_edge(self):
        """合法的 MUTEX 边(权重 -1.0)应通过校验。"""
        source = self._make_node("L3:r1", TopologyLayer.L3_RULE, NodeType.RULE)
        target = self._make_node("L3:r2", TopologyLayer.L3_RULE, NodeType.RULE)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L3:r1",
            target_id="L3:r2",
            edge_type=EdgeType.MUTEX,
            weight=-1.0,
        )
        schema.validate_edge(edge, source, target)

    def test_mutex_wrong_weight(self):
        """MUTEX 边权重不为 -1.0 应抛 TopologyValidationError。"""
        source = self._make_node("L3:r1", TopologyLayer.L3_RULE, NodeType.RULE)
        target = self._make_node("L3:r2", TopologyLayer.L3_RULE, NodeType.RULE)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L3:r1",
            target_id="L3:r2",
            edge_type=EdgeType.MUTEX,
            weight=0.5,
        )
        with pytest.raises(TopologyValidationError, match="权重必须为"):
            schema.validate_edge(edge, source, target)

    def test_valid_contains_edge_adjacent(self):
        """CONTAINS 边在相邻层(L1→L2)应通过校验。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.CONTAINS,
            weight=1.0,
        )
        schema.validate_edge(edge, source, target)

    def test_contains_wrong_weight(self):
        """CONTAINS 边权重不为 1.0 应抛 TopologyValidationError。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.CONTAINS,
            weight=0.5,
        )
        with pytest.raises(TopologyValidationError, match="权重必须为"):
            schema.validate_edge(edge, source, target)

    def test_contains_non_adjacent_layer(self):
        """CONTAINS 边跨多层(L1→L3)应抛 TopologyLayerViolationError。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L3:r1", TopologyLayer.L3_RULE, NodeType.RULE)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L3:r1",
            edge_type=EdgeType.CONTAINS,
            weight=1.0,
        )
        with pytest.raises(TopologyLayerViolationError, match="相邻层"):
            schema.validate_edge(edge, source, target)

    def test_contains_l2_to_l4_non_adjacent(self):
        """CONTAINS 边 L2→L4(跨多层)应抛 TopologyLayerViolationError。"""
        source = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        target = self._make_node("L4:f1", TopologyLayer.L4_FACT, NodeType.FACT)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L2:c1",
            target_id="L4:f1",
            edge_type=EdgeType.CONTAINS,
            weight=1.0,
        )
        with pytest.raises(TopologyLayerViolationError):
            schema.validate_edge(edge, source, target)

    def test_contains_same_layer(self):
        """CONTAINS 边在同层(L3→L3)应抛 TopologyLayerViolationError。"""
        source = self._make_node("L3:r1", TopologyLayer.L3_RULE, NodeType.RULE)
        target = self._make_node("L3:r2", TopologyLayer.L3_RULE, NodeType.RULE)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L3:r1",
            target_id="L3:r2",
            edge_type=EdgeType.CONTAINS,
            weight=1.0,
        )
        with pytest.raises(TopologyLayerViolationError):
            schema.validate_edge(edge, source, target)

    def test_variable_weight_above_max(self):
        """可变权重边权重 > 1.0 应抛 TopologyValidationError。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.CAUSAL,
            weight=1.5,
        )
        with pytest.raises(TopologyValidationError, match="范围内"):
            schema.validate_edge(edge, source, target)

    def test_variable_weight_below_min(self):
        """可变权重边权重 < 0.0 应抛 TopologyValidationError。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.CAUSAL,
            weight=-0.1,
        )
        with pytest.raises(TopologyValidationError):
            schema.validate_edge(edge, source, target)

    def test_variable_weight_at_boundaries(self):
        """可变权重边权重在边界值 0.0 和 1.0 应通过校验。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L2:c1", TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
        edge_min = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.CAUSAL,
            weight=0.0,
        )
        schema.validate_edge(edge_min, source, target)

        edge_max = TopologyEdge(
            edge_id="e2",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.CAUSAL,
            weight=1.0,
        )
        schema.validate_edge(edge_max, source, target)

    def test_non_contains_cross_layer_allowed(self):
        """非 CONTAINS 边类型(如 CAUSAL)跨多层应允许(L1→L4)。"""
        source = self._make_node("L1:g1", TopologyLayer.L1_GOAL, NodeType.GOAL)
        target = self._make_node("L4:f1", TopologyLayer.L4_FACT, NodeType.FACT)
        edge = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L4:f1",
            edge_type=EdgeType.DERIVES,
            weight=0.5,
        )
        schema.validate_edge(edge, source, target)


# ---------------------------------------------------------------------------
# is_valid_node_type_for_layer
# ---------------------------------------------------------------------------

class TestIsValidNodeTypeForLayer:
    """测试 is_valid_node_type_for_layer() 函数。"""

    def test_goal_in_l1(self):
        """GOAL 在 L1 应返回 True。"""
        assert schema.is_valid_node_type_for_layer(NodeType.GOAL, TopologyLayer.L1_GOAL) is True

    def test_concept_in_l2(self):
        """CONCEPT 在 L2 应返回 True。"""
        assert schema.is_valid_node_type_for_layer(NodeType.CONCEPT, TopologyLayer.L2_CONCEPT) is True

    def test_rule_in_l3(self):
        """RULE 在 L3 应返回 True。"""
        assert schema.is_valid_node_type_for_layer(NodeType.RULE, TopologyLayer.L3_RULE) is True

    def test_constraint_in_l3(self):
        """CONSTRAINT 在 L3 应返回 True。"""
        assert schema.is_valid_node_type_for_layer(NodeType.CONSTRAINT, TopologyLayer.L3_RULE) is True

    def test_inference_in_l3(self):
        """INFERENCE 在 L3 应返回 True。"""
        assert schema.is_valid_node_type_for_layer(NodeType.INFERENCE, TopologyLayer.L3_RULE) is True

    def test_fact_in_l4(self):
        """FACT 在 L4 应返回 True。"""
        assert schema.is_valid_node_type_for_layer(NodeType.FACT, TopologyLayer.L4_FACT) is True

    def test_goal_not_in_l2(self):
        """GOAL 不在 L2 应返回 False。"""
        assert schema.is_valid_node_type_for_layer(NodeType.GOAL, TopologyLayer.L2_CONCEPT) is False

    def test_concept_not_in_l1(self):
        """CONCEPT 不在 L1 应返回 False。"""
        assert schema.is_valid_node_type_for_layer(NodeType.CONCEPT, TopologyLayer.L1_GOAL) is False

    def test_fact_not_in_l3(self):
        """FACT 不在 L3 应返回 False。"""
        assert schema.is_valid_node_type_for_layer(NodeType.FACT, TopologyLayer.L3_RULE) is False


# ---------------------------------------------------------------------------
# get_layer_for_node_type
# ---------------------------------------------------------------------------

class TestGetLayerForNodeType:
    """测试 get_layer_for_node_type() 函数。"""

    def test_goal_returns_l1(self):
        """GOAL → L1。"""
        assert schema.get_layer_for_node_type(NodeType.GOAL) == TopologyLayer.L1_GOAL

    def test_concept_returns_l2(self):
        """CONCEPT → L2。"""
        assert schema.get_layer_for_node_type(NodeType.CONCEPT) == TopologyLayer.L2_CONCEPT

    def test_rule_returns_l3(self):
        """RULE → L3。"""
        assert schema.get_layer_for_node_type(NodeType.RULE) == TopologyLayer.L3_RULE

    def test_constraint_returns_l3(self):
        """CONSTRAINT → L3。"""
        assert schema.get_layer_for_node_type(NodeType.CONSTRAINT) == TopologyLayer.L3_RULE

    def test_inference_returns_l3(self):
        """INFERENCE → L3。"""
        assert schema.get_layer_for_node_type(NodeType.INFERENCE) == TopologyLayer.L3_RULE

    def test_fact_returns_l4(self):
        """FACT → L4。"""
        assert schema.get_layer_for_node_type(NodeType.FACT) == TopologyLayer.L4_FACT
