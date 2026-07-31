"""
飞轮 2: 知识固化环(实时,对话结束后触发)。

触发: 每次对话结束(飞轮 ① 完成后)
职责:
    1. 读取本次 TraceRecord
    2. 过滤规则(自动剔除垃圾): 临时话术/无实质推理/执行失败
    3. 知识萃取(LLM 提取): 新概念/新规则/新因果关系/新事实/新约束
    4. 增量写入拓扑: 新节点 INSERT(初始权重 0.5),现有路径权重 +0.02

彻底解决痛点: 普通 Agent 对话结束=知识清空;本 Agent 每次使用永久升级大脑结构。
"""

from __future__ import annotations

from typing import Any

from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    EdgeType,
    NodeType,
    TopologyLayer,
    TraceRecord,
)

# 过滤规则: 剔除的临时话术关键词
JUNK_KEYWORDS: frozenset[str] = frozenset(
    {
        "你好",
        "谢谢",
        "thanks",
        "hello",
        "hi",
        "ok",
        "好的",
        "再见",
        "bye",
        "嗯",
        "哦",
        "哈",
        "嘿",
    }
)

# 最低工具调用数(低于此值视为无实质推理)
MIN_TOOL_CALLS_FOR_SOLIDIFICATION: int = 1


class KnowledgeSolidificationFlywheel:
    """飞轮 ② 知识固化环。

    用法:
        flywheel2 = KnowledgeSolidificationFlywheel(graph)
        result = flywheel2.process(trace)
    """

    def __init__(
        self,
        graph: TopologyGraph,
        llm_router: Any = None,
    ) -> None:
        """初始化知识固化飞轮。

        Args:
            graph: 拓扑图实例(知识写入目标)
            llm_router: 可选的 LLM 路由器(用于知识萃取)
                        若为 None,使用规则式萃取(降级模式)
        """
        self._graph = graph
        self._llm = llm_router

    def process(self, trace: TraceRecord) -> dict:
        """处理单条轨迹,执行知识固化。

        Args:
            trace: 飞轮 ① 产出的执行轨迹

        Returns:
            固化统计 {
                "filtered": bool,           是否被过滤剔除
                "filter_reason": str,       过滤原因
                "new_nodes": int,           新增节点数
                "new_edges": int,           新增边数
                "reinforced_nodes": int,    强化的现有节点数
                "reinforced_edges": int,    强化的现有边数
            }
        """
        # Step 1: 过滤规则
        filtered, reason = self._filter_trace(trace)
        if filtered:
            return {
                "filtered": True,
                "filter_reason": reason,
                "new_nodes": 0,
                "new_edges": 0,
                "reinforced_nodes": 0,
                "reinforced_edges": 0,
            }

        # Step 2: 知识萃取
        extracted = self._extract_knowledge(trace)

        # Step 3: 增量写入拓扑
        stats = self._write_to_topology(trace, extracted)

        stats["filtered"] = False
        stats["filter_reason"] = ""
        return stats

    # -----------------------------------------------------------------------
    # Step 1: 过滤规则
    # -----------------------------------------------------------------------

    def _filter_trace(self, trace: TraceRecord) -> tuple[bool, str]:
        """过滤垃圾轨迹。

        剔除规则:
            1. 临时话术(含 JUNK_KEYWORDS)
            2. 无实质推理(工具调用数 < MIN_TOOL_CALLS_FOR_SOLIDIFICATION)
            3. 执行失败的轨迹
        """
        # 执行失败
        if not trace.success:
            return True, "execution_failed"

        # 临时话术
        goal_lower = trace.goal.lower().strip()
        for keyword in JUNK_KEYWORDS:
            if keyword in goal_lower and len(goal_lower) <= len(keyword) + 5:
                return True, f"junk_greeting({keyword})"

        # 无实质推理
        if len(trace.tool_calls) < MIN_TOOL_CALLS_FOR_SOLIDIFICATION:
            return True, "no_substantive_reasoning"

        return False, ""

    # -----------------------------------------------------------------------
    # Step 2: 知识萃取
    # -----------------------------------------------------------------------

    def _extract_knowledge(self, trace: TraceRecord) -> dict:
        """从轨迹中萃取知识(新概念/新规则/新因果关系/新事实/新约束)。

        若有 LLM 路由器,使用 LLM 萃取;否则使用规则式萃取(降级模式)。

        Returns:
            {
                "concepts": [{"name": str, "content": str}],
                "rules": [{"name": str, "content": str, "precondition": str}],
                "causal_relations": [{"from": str, "to": str, "reason": str}],
                "facts": [{"name": str, "content": str, "source": str}],
                "constraints": [{"name": str, "threshold": float, "rule_type": str}],
            }
        """
        if self._llm is not None:
            return self._llm_extract(trace)
        return self._rule_based_extract(trace)

    def _llm_extract(self, trace: TraceRecord) -> dict:
        """LLM 萃取(实际部署时使用)。

        Prompt: "从以下推理轨迹中提取: ① 新概念 ② 新规则 ③ 新因果关系 ④ 新事实 ⑤ 新约束。
                 仅输出结构化 JSON。"
        """
        # 构造 LLM 提示
        prompt = self._build_extraction_prompt(trace)
        try:
            # 调用 LLM(假设 router 有 chat 方法)
            response = self._llm.chat(messages=[{"role": "user", "content": prompt}])
            import json

            result = json.loads(response.content)
            return result
        except Exception:
            # LLM 失败时降级为规则式
            return self._rule_based_extract(trace)

    def _rule_based_extract(self, trace: TraceRecord) -> dict:
        """规则式萃取(降级模式,无需 LLM)。

        从轨迹的工具调用中提取:
            - 工具名 → 概念(L2)
            - 工具参数 → 事实(L4)
            - 工具调用顺序 → 因果关系
        """
        concepts = []
        rules = []
        causal_relations = []
        facts = []
        constraints = []

        # 从工具调用提取概念与事实
        seen_concepts = set()
        for i, call in enumerate(trace.tool_calls):
            tool_name = call.get("name", f"tool_{i}")
            args = call.get("args", {})
            call.get("status", "unknown")

            # 工具名 → 概念
            if tool_name not in seen_concepts:
                concepts.append(
                    {
                        "name": tool_name,
                        "content": f"技能: {tool_name}",
                    }
                )
                seen_concepts.add(tool_name)

            # 工具参数 → 事实
            if args:
                facts.append(
                    {
                        "name": f"{tool_name}_params_{i}",
                        "content": str(args),
                        "source": tool_name,
                    }
                )

            # 工具调用顺序 → 因果关系
            if i > 0:
                prev_tool = trace.tool_calls[i - 1].get("name", f"tool_{i - 1}")
                causal_relations.append(
                    {
                        "from": prev_tool,
                        "to": tool_name,
                        "reason": f"{prev_tool} 后调用 {tool_name}",
                    }
                )

        return {
            "concepts": concepts,
            "rules": rules,
            "causal_relations": causal_relations,
            "facts": facts,
            "constraints": constraints,
        }

    def _build_extraction_prompt(self, trace: TraceRecord) -> str:
        """构造 LLM 知识萃取提示。"""
        return f"""从以下推理轨迹中提取知识,仅输出结构化 JSON。

轨迹:
- 目标: {trace.goal}
- 推理模式: {trace.mode}
- 概念路径: {trace.concept_path}
- 工具调用: {trace.tool_calls}
- 是否成功: {trace.success}

请提取以下五类知识:
1. concepts: 新概念(名称 + 描述)
2. rules: 新规则(名称 + 前置条件 + 约束)
3. causal_relations: 新因果关系(from + to + 原因)
4. facts: 新事实(名称 + 内容 + 来源)
5. constraints: 新约束(名称 + 阈值 + 规则类型)

输出格式:
{{"concepts": [{{"name": "...", "content": "..."}}], "rules": [...], "causal_relations": [...], "facts": [...], "constraints": [...]}}"""

    # -----------------------------------------------------------------------
    # Step 3: 增量写入拓扑
    # -----------------------------------------------------------------------

    def _write_to_topology(self, trace: TraceRecord, extracted: dict) -> dict:
        """将萃取的知识增量写入拓扑图。

        写入规则:
            - 新节点: INSERT,初始权重 INITIAL_WEIGHT=0.5,置信度 CONFIDENCE_INIT=0.3
            - 新边: INSERT,初始权重 0.5
            - 现有路径上的节点/边: 权重 +SINGLE_INCREMENT(+0.02)
        """
        new_nodes = 0
        new_edges = 0
        reinforced_nodes = 0
        reinforced_edges = 0

        # 写入新概念(L2)
        concept_id_map: dict[str, str] = {}  # name → node_id
        for concept in extracted.get("concepts", []):
            name = concept.get("name", "")
            content = concept.get("content", "")
            if not name:
                continue
            # 检查是否已存在同名概念
            existing = self._find_node_by_name(name, TopologyLayer.L2_CONCEPT, NodeType.CONCEPT)
            if existing is not None:
                # 强化现有节点
                self._graph.reinforce_node(existing.node_id)
                reinforced_nodes += 1
                concept_id_map[name] = existing.node_id
            else:
                # 新增节点
                node = self._graph.add_node(
                    layer=TopologyLayer.L2_CONCEPT,
                    node_type=NodeType.CONCEPT,
                    name=name,
                    content=content,
                )
                new_nodes += 1
                concept_id_map[name] = node.node_id

        # 写入新规则(L3)
        for rule in extracted.get("rules", []):
            name = rule.get("name", "")
            content = rule.get("content", "")
            if not name:
                continue
            existing = self._find_node_by_name(name, TopologyLayer.L3_RULE, NodeType.RULE)
            if existing is not None:
                self._graph.reinforce_node(existing.node_id)
                reinforced_nodes += 1
            else:
                self._graph.add_node(
                    layer=TopologyLayer.L3_RULE,
                    node_type=NodeType.RULE,
                    name=name,
                    content=content,
                    metadata={"precondition": rule.get("precondition", "")},
                )
                new_nodes += 1

        # 写入新约束(L3 CONSTRAINT)
        for constraint in extracted.get("constraints", []):
            name = constraint.get("name", "")
            if not name:
                continue
            existing = self._find_node_by_name(name, TopologyLayer.L3_RULE, NodeType.CONSTRAINT)
            if existing is not None:
                self._graph.reinforce_node(existing.node_id)
                reinforced_nodes += 1
            else:
                self._graph.add_node(
                    layer=TopologyLayer.L3_RULE,
                    node_type=NodeType.CONSTRAINT,
                    name=name,
                    content=name,
                    metadata={
                        "threshold": constraint.get("threshold"),
                        "rule_type": constraint.get("rule_type", "generic"),
                    },
                )
                new_nodes += 1

        # 写入新事实(L4)
        for fact in extracted.get("facts", []):
            name = fact.get("name", "")
            content = fact.get("content", "")
            source = fact.get("source", "")
            if not name:
                continue
            existing = self._find_node_by_name(name, TopologyLayer.L4_FACT, NodeType.FACT)
            if existing is not None:
                self._graph.reinforce_node(existing.node_id)
                reinforced_nodes += 1
            else:
                self._graph.add_node(
                    layer=TopologyLayer.L4_FACT,
                    node_type=NodeType.FACT,
                    name=name,
                    content=content,
                    metadata={"source": source},
                )
                new_nodes += 1

        # 写入因果关系边
        for causal in extracted.get("causal_relations", []):
            from_name = causal.get("from", "")
            to_name = causal.get("to", "")
            reason = causal.get("reason", "")
            from_id = concept_id_map.get(from_name)
            to_id = concept_id_map.get(to_name)
            if from_id and to_id and from_id != to_id:
                # 检查是否已有同类型边
                existing_edge = self._find_edge(from_id, to_id, EdgeType.CAUSAL)
                if existing_edge is not None:
                    self._graph.reinforce_edge(existing_edge.edge_id)
                    reinforced_edges += 1
                else:
                    self._graph.add_edge(
                        source_id=from_id,
                        target_id=to_id,
                        edge_type=EdgeType.CAUSAL,
                        metadata={"reason": reason},
                    )
                    new_edges += 1

        # 强化当前推理路径上的节点
        for node_id in trace.concept_path:
            if self._graph.has_node(node_id):
                self._graph.reinforce_node(node_id)
                reinforced_nodes += 1

        return {
            "new_nodes": new_nodes,
            "new_edges": new_edges,
            "reinforced_nodes": reinforced_nodes,
            "reinforced_edges": reinforced_edges,
        }

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    def _find_node_by_name(
        self,
        name: str,
        layer: TopologyLayer,
        node_type: NodeType,
    ) -> Any | None:
        """按名称查找节点(同层同类)。"""
        nodes = self._graph.list_nodes(layer=layer, node_type=node_type)
        for node in nodes:
            if node.name == name:
                return node
        return None

    def _find_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
    ) -> Any | None:
        """查找同源同目标同类型的边。"""
        out_edges = self._graph.get_out_edges(source_id, edge_type=edge_type)
        for edge in out_edges:
            if edge.target_id == target_id:
                return edge
        return None
