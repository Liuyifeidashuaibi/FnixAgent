"""
知识拓扑图 (KTG) 存储后端单元测试。

测试模块: fnixagent.core.topology.store
覆盖:
    - TopologyStore: 抽象基类(所有方法应 raise NotImplementedError)
    - MemoryStore: 内存存储(追加写、加载、快照)
    - JSONFileStore: JSONL 文件存储(使用 tmp_path fixture)
    - TopologyStoreManager: 图与存储同步管理器
"""
import json
import os

import pytest

from fnixagent.core.exceptions import SnapshotError, TopologyError
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.topology.store import (
    JSONFileStore,
    MemoryStore,
    TopologyStore,
    TopologyStoreManager,
)
from fnixagent.core.types import (
    EdgeType,
    NodeType,
    TopologyEdge,
    TopologyLayer,
    TopologyNode,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_node(node_id="L1:g1", name="目标"):
    """创建测试用节点。"""
    return TopologyNode(
        node_id=node_id,
        layer=TopologyLayer.L1_GOAL,
        node_type=NodeType.GOAL,
        name=name,
    )


def _make_edge(edge_id="e1", source="L1:g1", target="L2:c1"):
    """创建测试用边。"""
    return TopologyEdge(
        edge_id=edge_id,
        source_id=source,
        target_id=target,
        edge_type=EdgeType.CAUSAL,
        weight=0.5,
    )


# ---------------------------------------------------------------------------
# TopologyStore 抽象基类
# ---------------------------------------------------------------------------

class TestTopologyStoreAbstract:
    """测试 TopologyStore 抽象基类。"""

    def test_append_node_not_implemented(self):
        """抽象基类的 append_node 应抛 NotImplementedError。"""
        store = TopologyStore()
        with pytest.raises(NotImplementedError):
            store.append_node(_make_node())

    def test_append_edge_not_implemented(self):
        """抽象基类的 append_edge 应抛 NotImplementedError。"""
        store = TopologyStore()
        with pytest.raises(NotImplementedError):
            store.append_edge(_make_edge())

    def test_load_all_nodes_not_implemented(self):
        """抽象基类的 load_all_nodes 应抛 NotImplementedError。"""
        store = TopologyStore()
        with pytest.raises(NotImplementedError):
            store.load_all_nodes()

    def test_load_all_edges_not_implemented(self):
        """抽象基类的 load_all_edges 应抛 NotImplementedError。"""
        store = TopologyStore()
        with pytest.raises(NotImplementedError):
            store.load_all_edges()

    def test_save_snapshot_not_implemented(self):
        """抽象基类的 save_snapshot 应抛 NotImplementedError。"""
        store = TopologyStore()
        with pytest.raises(NotImplementedError):
            store.save_snapshot({})

    def test_load_snapshot_not_implemented(self):
        """抽象基类的 load_snapshot 应抛 NotImplementedError。"""
        store = TopologyStore()
        with pytest.raises(NotImplementedError):
            store.load_snapshot("test")

    def test_list_snapshots_not_implemented(self):
        """抽象基类的 list_snapshots 应抛 NotImplementedError。"""
        store = TopologyStore()
        with pytest.raises(NotImplementedError):
            store.list_snapshots()


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

class TestMemoryStore:
    """测试 MemoryStore 内存存储。"""

    def test_append_and_load_nodes(self):
        """追加写节点后应能加载全部节点。"""
        store = MemoryStore()
        n1 = _make_node("L1:g1", "目标1")
        n2 = _make_node("L1:g2", "目标2")
        store.append_node(n1)
        store.append_node(n2)
        nodes = store.load_all_nodes()
        assert len(nodes) == 2
        assert nodes[0].node_id == "L1:g1"
        assert nodes[1].node_id == "L1:g2"

    def test_append_and_load_edges(self):
        """追加写边后应能加载全部边。"""
        store = MemoryStore()
        e1 = _make_edge("e1")
        e2 = _make_edge("e2")
        store.append_edge(e1)
        store.append_edge(e2)
        edges = store.load_all_edges()
        assert len(edges) == 2
        assert edges[0].edge_id == "e1"

    def test_load_empty_nodes(self):
        """空存储加载节点应返回空列表。"""
        store = MemoryStore()
        assert store.load_all_nodes() == []

    def test_load_empty_edges(self):
        """空存储加载边应返回空列表。"""
        store = MemoryStore()
        assert store.load_all_edges() == []

    def test_save_and_load_snapshot(self):
        """保存并加载快照。"""
        store = MemoryStore()
        snapshot = {"nodes": [{"node_id": "L1:g1"}], "edges": []}
        name = store.save_snapshot(snapshot, name="test_snap")
        assert name == "test_snap"
        loaded = store.load_snapshot("test_snap")
        assert loaded == snapshot

    def test_save_snapshot_auto_name(self):
        """不指定名称时自动生成快照名。"""
        store = MemoryStore()
        name = store.save_snapshot({"nodes": [], "edges": []})
        assert name.startswith("snapshot_")

    def test_load_nonexistent_snapshot(self):
        """加载不存在的快照应抛 SnapshotError。"""
        store = MemoryStore()
        with pytest.raises(SnapshotError, match="快照不存在"):
            store.load_snapshot("nonexistent")

    def test_list_snapshots_empty(self):
        """空存储列举快照应返回空列表。"""
        store = MemoryStore()
        assert store.list_snapshots() == []

    def test_list_snapshots(self):
        """列举已保存的快照名。"""
        store = MemoryStore()
        store.save_snapshot({}, name="snap1")
        store.save_snapshot({}, name="snap2")
        snapshots = store.list_snapshots()
        assert len(snapshots) == 2
        assert "snap1" in snapshots
        assert "snap2" in snapshots

    def test_load_all_nodes_returns_copy(self):
        """load_all_nodes 应返回副本(修改不影响内部存储)。"""
        store = MemoryStore()
        store.append_node(_make_node())
        nodes = store.load_all_nodes()
        nodes.clear()
        assert len(store.load_all_nodes()) == 1


# ---------------------------------------------------------------------------
# JSONFileStore
# ---------------------------------------------------------------------------

class TestJSONFileStore:
    """测试 JSONFileStore 文件存储(使用 tmp_path fixture)。"""

    def test_init_creates_snapshot_dir(self, tmp_path):
        """初始化时应自动创建 snapshots 子目录。"""
        store = JSONFileStore(str(tmp_path))
        assert os.path.isdir(os.path.join(str(tmp_path), "snapshots"))

    def test_append_and_load_nodes(self, tmp_path):
        """追加写节点后应能从文件加载全部节点。"""
        store = JSONFileStore(str(tmp_path))
        store.append_node(_make_node("L1:g1", "目标1"))
        store.append_node(_make_node("L1:g2", "目标2"))
        nodes = store.load_all_nodes()
        assert len(nodes) == 2
        assert nodes[0].node_id == "L1:g1"
        assert nodes[1].name == "目标2"

    def test_append_and_load_edges(self, tmp_path):
        """追加写边后应能从文件加载全部边。"""
        store = JSONFileStore(str(tmp_path))
        store.append_edge(_make_edge("e1"))
        store.append_edge(_make_edge("e2"))
        edges = store.load_all_edges()
        assert len(edges) == 2
        assert edges[0].edge_id == "e1"
        assert edges[1].edge_type == EdgeType.CAUSAL

    def test_load_empty_nodes(self, tmp_path):
        """文件不存在时加载节点应返回空列表。"""
        store = JSONFileStore(str(tmp_path))
        assert store.load_all_nodes() == []

    def test_load_empty_edges(self, tmp_path):
        """文件不存在时加载边应返回空列表。"""
        store = JSONFileStore(str(tmp_path))
        assert store.load_all_edges() == []

    def test_node_round_trip_preserves_fields(self, tmp_path):
        """节点序列化/反序列化应保留全部字段。"""
        store = JSONFileStore(str(tmp_path))
        original = TopologyNode(
            node_id="L2:c1",
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="概念",
            content="内容",
            weight=0.7,
            confidence=0.5,
            use_count=3,
            freshness=0.8,
            deprecated=False,
            version=2,
            metadata={"key": "val"},
            skill_binding="my_skill",
        )
        store.append_node(original)
        loaded = store.load_all_nodes()
        assert len(loaded) == 1
        n = loaded[0]
        assert n.node_id == "L2:c1"
        assert n.layer == TopologyLayer.L2_CONCEPT
        assert n.node_type == NodeType.CONCEPT
        assert n.name == "概念"
        assert n.content == "内容"
        assert n.weight == 0.7
        assert n.confidence == 0.5
        assert n.use_count == 3
        assert n.freshness == 0.8
        assert n.deprecated is False
        assert n.version == 2
        assert n.metadata == {"key": "val"}
        assert n.skill_binding == "my_skill"

    def test_edge_round_trip_preserves_fields(self, tmp_path):
        """边序列化/反序列化应保留全部字段。"""
        store = JSONFileStore(str(tmp_path))
        original = TopologyEdge(
            edge_id="e1",
            source_id="L1:g1",
            target_id="L2:c1",
            edge_type=EdgeType.DEPENDS_ON,
            weight=0.6,
            version=2,
            deprecated=False,
            metadata={"reason": "test"},
        )
        store.append_edge(original)
        loaded = store.load_all_edges()
        assert len(loaded) == 1
        e = loaded[0]
        assert e.edge_id == "e1"
        assert e.source_id == "L1:g1"
        assert e.target_id == "L2:c1"
        assert e.edge_type == EdgeType.DEPENDS_ON
        assert e.weight == 0.6
        assert e.version == 2
        assert e.metadata == {"reason": "test"}

    def test_save_and_load_snapshot(self, tmp_path):
        """保存并从文件加载快照。"""
        store = JSONFileStore(str(tmp_path))
        snapshot = {"nodes": [{"node_id": "L1:g1"}], "edges": []}
        name = store.save_snapshot(snapshot, name="test_snap")
        assert name == "test_snap"
        loaded = store.load_snapshot("test_snap")
        assert loaded == snapshot

    def test_save_snapshot_auto_name(self, tmp_path):
        """不指定名称时自动生成日期快照名。"""
        store = JSONFileStore(str(tmp_path))
        name = store.save_snapshot({"nodes": [], "edges": []})
        # 默认格式为 %Y-%m-%d
        assert len(name) == 10  # "YYYY-MM-DD"

    def test_load_nonexistent_snapshot(self, tmp_path):
        """加载不存在的快照应抛 SnapshotError。"""
        store = JSONFileStore(str(tmp_path))
        with pytest.raises(SnapshotError, match="快照不存在"):
            store.load_snapshot("nonexistent")

    def test_list_snapshots_empty(self, tmp_path):
        """无快照时列举应返回空列表。"""
        store = JSONFileStore(str(tmp_path))
        assert store.list_snapshots() == []

    def test_list_snapshots(self, tmp_path):
        """列举已保存的快照名(不含 .json 后缀)。"""
        store = JSONFileStore(str(tmp_path))
        store.save_snapshot({}, name="snap1")
        store.save_snapshot({}, name="snap2")
        snapshots = store.list_snapshots()
        assert len(snapshots) == 2
        assert "snap1" in snapshots
        assert "snap2" in snapshots

    def test_nodes_jsonl_file_exists(self, tmp_path):
        """追加节点后 nodes.jsonl 文件应存在。"""
        store = JSONFileStore(str(tmp_path))
        store.append_node(_make_node())
        assert os.path.isfile(os.path.join(str(tmp_path), "nodes.jsonl"))

    def test_edges_jsonl_file_exists(self, tmp_path):
        """追加边后 edges.jsonl 文件应存在。"""
        store = JSONFileStore(str(tmp_path))
        store.append_edge(_make_edge())
        assert os.path.isfile(os.path.join(str(tmp_path), "edges.jsonl"))

    def test_snapshot_file_exists(self, tmp_path):
        """保存快照后 snapshots/<name>.json 文件应存在。"""
        store = JSONFileStore(str(tmp_path))
        store.save_snapshot({"nodes": [], "edges": []}, name="my_snap")
        assert os.path.isfile(
            os.path.join(str(tmp_path), "snapshots", "my_snap.json")
        )


# ---------------------------------------------------------------------------
# TopologyStoreManager
# ---------------------------------------------------------------------------

class TestTopologyStoreManager:
    """测试 TopologyStoreManager 存储管理器。"""

    def test_persist_node(self):
        """持久化节点应写入存储。"""
        graph = TopologyGraph()
        store = MemoryStore()
        manager = TopologyStoreManager(graph, store, snapshot_interval=100)
        node = graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            node_id="L1:g1",
        )
        manager.persist_node(node)
        assert len(store.load_all_nodes()) == 1

    def test_persist_edge(self):
        """持久化边应写入存储。"""
        graph = TopologyGraph()
        store = MemoryStore()
        manager = TopologyStoreManager(graph, store, snapshot_interval=100)
        graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="g",
            node_id="L1:g1",
        )
        graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="c",
            node_id="L2:c1",
        )
        edge = graph.add_edge("L1:g1", "L2:c1", EdgeType.CAUSAL, edge_id="e1")
        manager.persist_edge(edge)
        assert len(store.load_all_edges()) == 1

    def test_save_snapshot_manual(self):
        """手动保存快照。"""
        graph = TopologyGraph()
        store = MemoryStore()
        manager = TopologyStoreManager(graph, store)
        graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            node_id="L1:g1",
        )
        name = manager.save_snapshot(name="manual_snap")
        assert name == "manual_snap"
        assert "manual_snap" in store.list_snapshots()

    def test_load_from_store_without_snapshots(self):
        """无快照时从 JSONL 逐条加载。"""
        # 第一个图:写入数据
        graph1 = TopologyGraph()
        store = MemoryStore()
        manager1 = TopologyStoreManager(graph1, store, snapshot_interval=100)
        n1 = graph1.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            node_id="L1:g1",
        )
        manager1.persist_node(n1)
        n2 = graph1.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="概念",
            node_id="L2:c1",
        )
        manager1.persist_node(n2)
        e1 = graph1.add_edge("L1:g1", "L2:c1", EdgeType.CAUSAL, edge_id="e1")
        manager1.persist_edge(e1)

        # 第二个图:从存储加载
        graph2 = TopologyGraph()
        manager2 = TopologyStoreManager(graph2, store)
        manager2.load_from_store()

        assert graph2.has_node("L1:g1")
        assert graph2.has_node("L2:c1")
        assert len(graph2.list_edges()) == 1

    def test_load_from_store_with_snapshots(self):
        """有快照时从最新快照加载。"""
        graph1 = TopologyGraph()
        store = MemoryStore()
        manager1 = TopologyStoreManager(graph1, store)
        graph1.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="目标",
            node_id="L1:g1",
        )
        manager1.save_snapshot(name="snap_001")

        graph2 = TopologyGraph()
        manager2 = TopologyStoreManager(graph2, store)
        manager2.load_from_store()
        assert graph2.has_node("L1:g1")

    def test_load_from_store_latest_snapshot(self):
        """应加载按名称排序的最新快照。"""
        graph1 = TopologyGraph()
        store = MemoryStore()
        manager1 = TopologyStoreManager(graph1, store)
        # 第一个快照:1 个节点
        graph1.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="g1",
            node_id="L1:g1",
        )
        manager1.save_snapshot(name="snap_001")
        # 第二个快照:2 个节点
        graph1.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name="c1",
            node_id="L2:c1",
        )
        manager1.save_snapshot(name="snap_002")

        graph2 = TopologyGraph()
        manager2 = TopologyStoreManager(graph2, store)
        manager2.load_from_store()
        # 应加载 snap_002(排序最大)
        assert graph2.has_node("L1:g1")
        assert graph2.has_node("L2:c1")

    def test_auto_snapshot_at_interval(self):
        """写入次数达到阈值时应自动快照。"""
        graph = TopologyGraph()
        store = MemoryStore()
        manager = TopologyStoreManager(graph, store, snapshot_interval=2)

        n1 = graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="g1",
            node_id="L1:g1",
        )
        manager.persist_node(n1)
        assert len(store.list_snapshots()) == 0  # 1 次,未达阈值

        n2 = graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="g2",
            node_id="L1:g2",
        )
        manager.persist_node(n2)
        assert len(store.list_snapshots()) == 1  # 2 次,达到阈值

    def test_auto_snapshot_multiple_cycles(self):
        """多次达到阈值应触发多次快照(同名快照会覆盖)。"""
        graph = TopologyGraph()
        store = MemoryStore()
        manager = TopologyStoreManager(graph, store, snapshot_interval=1)

        for i in range(3):
            n = graph.add_node(
                layer=TopologyLayer.L1_GOAL,
                node_type=NodeType.GOAL,
                name=f"g{i}",
                node_id=f"L1:g{i}",
            )
            manager.persist_node(n)

        # 自动快照名基于 int(time.time()),同一秒内会覆盖
        # 但至少应触发过快照
        assert len(store.list_snapshots()) >= 1
        # 验证快照内容包含最新图状态
        snap_names = store.list_snapshots()
        latest_snap = store.load_snapshot(sorted(snap_names)[-1])
        assert len(latest_snap["nodes"]) == 3

    def test_load_from_store_empty(self):
        """空存储加载不应报错。"""
        graph = TopologyGraph()
        store = MemoryStore()
        manager = TopologyStoreManager(graph, store)
        manager.load_from_store()
        assert graph.list_nodes(include_deprecated=True) == []
        assert graph.list_edges(include_deprecated=True) == []

    def test_load_from_store_skips_existing_nodes(self):
        """从 JSONL 加载时应跳过已存在的节点。"""
        graph = TopologyGraph()
        store = MemoryStore()
        # 预置一个节点
        graph.add_node(
            layer=TopologyLayer.L1_GOAL,
            node_type=NodeType.GOAL,
            name="已有",
            node_id="L1:g1",
        )
        # 存储中也有同 ID 节点
        store.append_node(_make_node("L1:g1", "存储中的"))
        manager = TopologyStoreManager(graph, store)
        manager.load_from_store()
        # 应保留图中已有节点,不覆盖
        assert graph.get_node("L1:g1").name == "已有"
