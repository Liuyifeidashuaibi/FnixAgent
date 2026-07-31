"""
飞轮 4: 爬坡进化环(后台异步,每日触发)。

触发: 每日定时任务 或 每 100 次对话
职责:
    1. 批量分析全部历史 TraceRecord
    2. 自动总结:
        - 高频任务范式(出现 ≥ 3 次的相似任务模式)
        - 常用推理链路(权重 Top-10 路径)
        - 高频技能组合(经常一起调用的技能)
    3. 自动优化三件套:
        - 重构知识拓扑薄弱链路(低权重但高频使用 → 权重提升)
        - 调整 Skills 调用优先级权重(高频成功技能 → 优先级提升)
        - 沉淀专属任务思维范式(高频范式固化为 L3 规则节点)
    4. 全局旧知识自动衰减:
        - 所有节点 freshness × 0.999
        - freshness < 0.3 且 use_count < 5: weight × 0.95
        - 连续 30 天未命中: 标记 stale=True(不删除,仅降权)
"""

from __future__ import annotations

import time
from collections import Counter
from typing import Any

from fnixagent.core.exceptions import EvolutionRollbackError
from fnixagent.core.flywheel.trace import TraceStore
from fnixagent.core.topology import weights as weights_mod
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.types import (
    EvolutionSnapshot,
    FlywheelStage,
    NodeType,
    TopologyLayer,
    TraceRecord,
)

# 默认触发间隔(对话数)
DEFAULT_EVOLUTION_INTERVAL: int = 100

# 高频范式阈值(出现次数)
PATTERN_FREQUENCY_THRESHOLD: int = 3

# 常用路径 Top-N
TOP_PATHS_LIMIT: int = 10

# 高频技能组合阈值
SKILL_COMBO_THRESHOLD: int = 3


class HillClimbingFlywheel:
    """飞轮 ④ 爬坡进化环。

    用法:
        flywheel4 = HillClimbingFlywheel(graph, trace_store, snapshot_manager)
        result = flywheel4.run()
    """

    def __init__(
        self,
        graph: TopologyGraph,
        trace_store: TraceStore | None = None,
        snapshot_manager: Any = None,
        evolution_interval: int = DEFAULT_EVOLUTION_INTERVAL,
    ) -> None:
        """初始化爬坡进化飞轮。

        Args:
            graph: 拓扑图实例
            trace_store: 轨迹存储
            snapshot_manager: 快照管理器(用于回滚)
            evolution_interval: 进化检查间隔(任务数)
        """
        self._graph = graph
        self._trace_store = trace_store
        self._snapshot_manager = snapshot_manager
        self._evolution_interval = evolution_interval
        self._task_count = 0
        self._evolution_history: list[EvolutionSnapshot] = []

    def should_trigger(self) -> bool:
        """判断是否应触发进化。"""
        self._task_count += 1
        return self._task_count >= self._evolution_interval

    def run(self, traces: list[TraceRecord] | None = None) -> dict:
        """执行爬坡进化。

        Returns:
            进化结果 {
                "analyzed_traces": int,         分析的轨迹数
                "patterns_detected": int,       检测到的高频范式数
                "top_paths": int,               常用路径数
                "skill_combos": int,            高频技能组合数
                "weak_links_fixed": int,        修复的薄弱链路数
                "skills_adjusted": int,         调整优先级的技能数
                "patterns_solidified": int,     固化的范式数
                "decayed_nodes": int,           衰减的节点数
                "stale_nodes": int,             标记 stale 的节点数
                "snapshot_created": bool,       是否创建快照
                "rolled_back": bool,            是否回滚
            }
        """
        # 加载轨迹
        if traces is None and self._trace_store is not None:
            traces = self._trace_store.load_all()
        if not traces:
            traces = []

        # Step 0: 创建进化前快照(用于回滚)
        pre_snapshot_name = None
        if self._snapshot_manager is not None:
            try:
                pre_snapshot_name = self._snapshot_manager.create_snapshot(
                    name=f"pre_evolution_{int(time.time())}"
                )
            except Exception:
                pre_snapshot_name = None

        result = {
            "analyzed_traces": len(traces),
            "patterns_detected": 0,
            "top_paths": 0,
            "skill_combos": 0,
            "weak_links_fixed": 0,
            "skills_adjusted": 0,
            "patterns_solidified": 0,
            "decayed_nodes": 0,
            "stale_nodes": 0,
            "snapshot_created": False,
            "rolled_back": False,
        }

        try:
            # Step 1: 自动总结
            patterns = self._detect_patterns(traces)
            top_paths = self._find_top_paths()
            skill_combos = self._detect_skill_combos(traces)
            result["patterns_detected"] = len(patterns)
            result["top_paths"] = len(top_paths)
            result["skill_combos"] = len(skill_combos)

            # Step 2: 自动优化三件套
            result["weak_links_fixed"] = self._fix_weak_links(traces)
            result["skills_adjusted"] = self._adjust_skill_priorities(traces)
            result["patterns_solidified"] = self._solidify_patterns(patterns)

            # Step 3: 全局旧知识衰减
            decayed, stale = self._apply_global_decay()
            result["decayed_nodes"] = decayed
            result["stale_nodes"] = stale

            # Step 4: 创建进化后快照
            if self._snapshot_manager is not None:
                try:
                    self._snapshot_manager.create_snapshot(
                        name=f"post_evolution_{int(time.time())}"
                    )
                    result["snapshot_created"] = True
                except Exception:
                    pass

            # Step 5: 评估进化效果
            post_stats = self._compute_evolution_metrics(traces)
            snapshot = EvolutionSnapshot(
                snapshot_id=f"evo_{int(time.time())}",
                stage=FlywheelStage.HILL_CLIMBING,
                node_count=self._graph.stats()["active_nodes"],
                edge_count=self._graph.stats()["active_edges"],
                skill_count=len(
                    self._graph.list_nodes(
                        layer=TopologyLayer.L2_CONCEPT,
                        node_type=NodeType.CONCEPT,
                    )
                ),
                avg_success_rate=post_stats["success_rate"],
                avg_token_efficiency=post_stats["token_efficiency"],
                payload=self._graph.snapshot(),
                created_at=time.time(),
            )
            self._evolution_history.append(snapshot)

            # Step 6: 检查是否需要回滚
            if self._should_rollback(snapshot):
                self._rollback(pre_snapshot_name)
                result["rolled_back"] = True

        except Exception as e:
            # 进化失败 → 回滚
            if pre_snapshot_name is not None:
                self._rollback(pre_snapshot_name)
                result["rolled_back"] = True
            raise EvolutionRollbackError(f"爬坡进化失败,已回滚: {e}") from e

        # 重置计数器
        self._task_count = 0

        return result

    # -----------------------------------------------------------------------
    # Step 1: 自动总结
    # -----------------------------------------------------------------------

    def _detect_patterns(self, traces: list[TraceRecord]) -> list[dict]:
        """检测高频任务范式(出现 ≥ 3 次的相似任务模式)。

        策略: 按目标文本的前 20 字符分组,统计出现次数。
        """
        if not traces:
            return []
        goal_counter: Counter = Counter()
        for trace in traces:
            # 用前 20 字符作为模式签名
            pattern_sig = trace.goal[:20]
            goal_counter[pattern_sig] += 1

        patterns = []
        for sig, count in goal_counter.most_common():
            if count >= PATTERN_FREQUENCY_THRESHOLD:
                # 找一个完整的目标作为代表
                representative = next(t for t in traces if t.goal[:20] == sig)
                patterns.append(
                    {
                        "signature": sig,
                        "count": count,
                        "representative_goal": representative.goal,
                        "success_rate": sum(1 for t in traces if t.goal[:20] == sig and t.success)
                        / count,
                    }
                )
        return patterns

    def _find_top_paths(self) -> list[dict]:
        """查找常用推理链路(权重 Top-10 路径)。"""
        # 获取全部 L2 概念节点,按权重降序
        concepts = self._graph.list_nodes(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
        )
        concepts.sort(key=lambda n: n.weight, reverse=True)
        top_paths = []
        for concept in concepts[:TOP_PATHS_LIMIT]:
            # 获取该概念节点的出边
            out_edges = self._graph.get_out_edges(concept.node_id)
            for edge in out_edges:
                if edge.deprecated:
                    continue
                try:
                    target = self._graph.get_node(edge.target_id)
                    top_paths.append(
                        {
                            "concept": concept.name,
                            "concept_weight": concept.weight,
                            "edge_type": edge.edge_type.value,
                            "edge_weight": edge.weight,
                            "target": target.name,
                        }
                    )
                except Exception:
                    continue
        return top_paths

    def _detect_skill_combos(self, traces: list[TraceRecord]) -> list[dict]:
        """检测高频技能组合(经常一起调用的技能)。"""
        if not traces:
            return []
        combo_counter: Counter = Counter()
        for trace in traces:
            skill_names = [c.get("name", "") for c in trace.tool_calls if c.get("name")]
            if len(skill_names) >= 2:
                # 技能组合(排序后作为 key,避免顺序影响)
                combo = tuple(sorted(set(skill_names)))
                combo_counter[combo] += 1

        combos = []
        for combo, count in combo_counter.most_common():
            if count >= SKILL_COMBO_THRESHOLD:
                combos.append(
                    {
                        "skills": list(combo),
                        "count": count,
                    }
                )
        return combos

    # -----------------------------------------------------------------------
    # Step 2: 自动优化三件套
    # -----------------------------------------------------------------------

    def _fix_weak_links(self, traces: list[TraceRecord]) -> int:
        """重构知识拓扑薄弱链路。

        策略: 低权重但高频使用的路径 → 权重提升。
        """
        fixed = 0
        # 统计每个概念节点的使用频次
        usage_counter: Counter = Counter()
        for trace in traces:
            for node_id in trace.concept_path:
                usage_counter[node_id] += 1

        # 检查低权重但高频使用的节点
        for node_id, usage_count in usage_counter.items():
            if not self._graph.has_node(node_id):
                continue
            node = self._graph.get_node(node_id)
            if node.weight < 0.3 and usage_count >= 3:
                # 薄弱但高频 → 提升
                node.weight = weights_mod.reinforce(node.weight, 0.1)
                fixed += 1
        return fixed

    def _adjust_skill_priorities(self, traces: list[TraceRecord]) -> int:
        """调整 Skills 调用优先级权重。

        策略: 高频成功技能 → 优先级提升(通过提升绑定概念节点权重)。
        """
        if not traces:
            return 0
        # 统计每个技能的成功率
        skill_stats: dict[str, dict] = {}
        for trace in traces:
            for call in trace.tool_calls:
                name = call.get("name", "")
                if not name:
                    continue
                if name not in skill_stats:
                    skill_stats[name] = {"success": 0, "total": 0}
                skill_stats[name]["total"] += 1
                if call.get("status") == "success":
                    skill_stats[name]["success"] += 1

        adjusted = 0
        for skill_name, stats in skill_stats.items():
            if stats["total"] < 3:
                continue
            success_rate = stats["success"] / stats["total"]
            if success_rate > 0.8:
                # 高成功率技能 → 提升绑定概念节点权重
                concepts = self._graph.list_nodes(
                    layer=TopologyLayer.L2_CONCEPT,
                    node_type=NodeType.CONCEPT,
                )
                for concept in concepts:
                    if concept.skill_binding == skill_name:
                        concept.weight = weights_mod.reinforce(concept.weight, 0.05)
                        adjusted += 1
        return adjusted

    def _solidify_patterns(self, patterns: list[dict]) -> int:
        """沉淀专属任务思维范式(高频范式固化为 L3 规则节点)。"""
        solidified = 0
        for pattern in patterns:
            if pattern["success_rate"] < 0.5:
                continue  # 成功率低的范式不固化
            # 检查是否已有同名规则
            name = f"pattern:{pattern['signature']}"
            existing = self._find_node_by_name(name, TopologyLayer.L3_RULE, NodeType.RULE)
            if existing is not None:
                continue  # 已固化
            self._graph.add_node(
                layer=TopologyLayer.L3_RULE,
                node_type=NodeType.RULE,
                name=name,
                content=pattern["representative_goal"],
                metadata={
                    "source": "hill_climbing",
                    "frequency": pattern["count"],
                    "success_rate": pattern["success_rate"],
                },
            )
            solidified += 1
        return solidified

    # -----------------------------------------------------------------------
    # Step 3: 全局旧知识衰减
    # -----------------------------------------------------------------------

    def _apply_global_decay(self) -> tuple[int, int]:
        """全局旧知识自动衰减。

        Returns:
            (衰减的节点数, 标记 stale 的节点数)
        """
        decayed = 0
        stale = 0
        current_time = time.time()
        30 * 24 * 3600

        for node in self._graph.list_nodes(include_deprecated=False):
            # freshness 衰减
            weights_mod.node_daily_decay(node)
            decayed += 1

            # 检查是否连续 30 天未命中
            if node.last_used_at > 0:
                days_since_used = (current_time - node.last_used_at) / 86400
                if days_since_used > 30:
                    node.metadata["stale"] = True
                    node.weight = weights_mod.decay(node.weight, 0.95)
                    stale += 1
            elif node.created_at > 0:
                days_since_created = (current_time - node.created_at) / 86400
                if days_since_created > 30 and node.use_count == 0:
                    node.metadata["stale"] = True
                    node.weight = weights_mod.decay(node.weight, 0.95)
                    stale += 1

        return decayed, stale

    # -----------------------------------------------------------------------
    # Step 4-6: 快照与回滚
    # -----------------------------------------------------------------------

    def _compute_evolution_metrics(self, traces: list[TraceRecord]) -> dict:
        """计算进化后的性能指标。"""
        if not traces:
            return {"success_rate": 0.0, "token_efficiency": 0.0}
        success_count = sum(1 for t in traces if t.success)
        total_tokens = sum(t.usage_tokens for t in traces)
        success_rate = success_count / len(traces)
        token_efficiency = success_count / max(1, total_tokens) * 1000  # 每 1000 token 的成功数
        return {
            "success_rate": success_rate,
            "token_efficiency": token_efficiency,
        }

    def _should_rollback(self, snapshot: EvolutionSnapshot) -> bool:
        """判断是否需要回滚(性能回退)。

        策略: 若当前成功率低于历史平均的 90%,则回滚。
        """
        if not self._evolution_history:
            return False
        # 与上一个快照对比
        prev = self._evolution_history[-1]
        if prev.avg_success_rate > 0 and snapshot.avg_success_rate < prev.avg_success_rate * 0.9:
            return True
        return False

    def _rollback(self, snapshot_name: str | None) -> None:
        """回滚到指定快照。"""
        if snapshot_name is None or self._snapshot_manager is None:
            return
        try:
            snapshot_data = self._snapshot_manager.restore_snapshot(snapshot_name)
            self._graph.restore(snapshot_data)
        except Exception as e:
            raise EvolutionRollbackError(f"回滚失败: {e}") from e

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    def _find_node_by_name(
        self,
        name: str,
        layer: TopologyLayer,
        node_type: NodeType,
    ) -> Any | None:
        """按名称查找节点。"""
        nodes = self._graph.list_nodes(layer=layer, node_type=node_type)
        for node in nodes:
            if node.name == name:
                return node
        return None

    def get_evolution_history(self) -> list[EvolutionSnapshot]:
        """获取进化历史。"""
        return list(self._evolution_history)
