"""
知识拓扑图 (KTG) 增量写入存储。

遵循"只增不删不覆盖"原则:
    - 节点/边的新增永远追加写(JSONL 每行一条)
    - 权重修正不修改旧记录,而是新增"修正记录"(带时间戳与版本号)
    - 物理删除永久禁止,仅标记 deprecated=True

存储格式:
    - nodes.jsonl: 每行一个节点 JSON(追加写)
    - edges.jsonl: 每行一个边 JSON(追加写)
    - snapshots/<date>.json: 每日完整快照(覆盖写)

支持两种后端:
    - JSONFileStore: 纯 JSONL 文件(单机,开发期默认)
    - MemoryStore:   纯内存(单元测试用)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING

from fnixagent.core.exceptions import SnapshotError, TopologyError
from fnixagent.core.types import EdgeType, TopologyEdge, TopologyLayer, TopologyNode

if TYPE_CHECKING:
    from fnixagent.core.topology.graph import TopologyGraph

# ---------------------------------------------------------------------------
# 存储后端抽象接口
# ---------------------------------------------------------------------------


class TopologyStore:
    """拓扑图存储后端抽象基类。"""

    def append_node(self, node: TopologyNode) -> None:
        """追加写入节点(不覆盖已有)。"""
        raise NotImplementedError

    def append_edge(self, edge: TopologyEdge) -> None:
        """追加写入边。"""
        raise NotImplementedError

    def load_all_nodes(self) -> list[TopologyNode]:
        """加载全部节点。"""
        raise NotImplementedError

    def load_all_edges(self) -> list[TopologyEdge]:
        """加载全部边。"""
        raise NotImplementedError

    def save_snapshot(self, snapshot: dict, name: str | None = None) -> str:
        """保存快照。"""
        raise NotImplementedError

    def load_snapshot(self, name: str) -> dict:
        """加载快照。"""
        raise NotImplementedError

    def list_snapshots(self) -> list[str]:
        """列举全部快照名。"""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# 内存存储(单元测试用,不落盘)
# ---------------------------------------------------------------------------


class MemoryStore(TopologyStore):
    """纯内存存储(单元测试用)。"""

    def __init__(self) -> None:
        self._nodes: list[TopologyNode] = []
        self._edges: list[TopologyEdge] = []
        self._snapshots: dict[str, dict] = {}

    def append_node(self, node: TopologyNode) -> None:
        self._nodes.append(node)

    def append_edge(self, edge: TopologyEdge) -> None:
        self._edges.append(edge)

    def load_all_nodes(self) -> list[TopologyNode]:
        return list(self._nodes)

    def load_all_edges(self) -> list[TopologyEdge]:
        return list(self._edges)

    def save_snapshot(self, snapshot: dict, name: str | None = None) -> str:
        name = name or f"snapshot_{int(time.time())}"
        self._snapshots[name] = snapshot
        return name

    def load_snapshot(self, name: str) -> dict:
        if name not in self._snapshots:
            raise SnapshotError(f"快照不存在: {name}")
        return self._snapshots[name]

    def list_snapshots(self) -> list[str]:
        return list(self._snapshots.keys())


# ---------------------------------------------------------------------------
# JSONL 文件存储(单机生产用)
# ---------------------------------------------------------------------------


class JSONFileStore(TopologyStore):
    """JSONL 文件存储后端。

    文件布局:
        <base_dir>/
        ├── nodes.jsonl          追加写,每行一个节点
        ├── edges.jsonl          追加写,每行一个边
        └── snapshots/
            ├── 2026-07-04.json  每日快照
            └── ...
    """

    def __init__(self, base_dir: str) -> None:
        """初始化文件存储。

        Args:
            base_dir: 存储根目录(自动创建)
        """
        self._base_dir = base_dir
        self._nodes_file = os.path.join(base_dir, "nodes.jsonl")
        self._edges_file = os.path.join(base_dir, "edges.jsonl")
        self._snapshot_dir = os.path.join(base_dir, "snapshots")
        # 自动创建目录
        os.makedirs(self._snapshot_dir, exist_ok=True)

    def append_node(self, node: TopologyNode) -> None:
        """追加写入节点到 nodes.jsonl。"""
        record = self._node_to_dict(node)
        self._append_jsonl(self._nodes_file, record)

    def append_edge(self, edge: TopologyEdge) -> None:
        """追加写入边到 edges.jsonl。"""
        record = self._edge_to_dict(edge)
        self._append_jsonl(self._edges_file, record)

    def load_all_nodes(self) -> list[TopologyNode]:
        """从 nodes.jsonl 加载全部节点。"""
        if not os.path.exists(self._nodes_file):
            return []
        nodes = []
        for line in self._read_jsonl(self._nodes_file):
            nodes.append(self._dict_to_node(line))
        return nodes

    def load_all_edges(self) -> list[TopologyEdge]:
        """从 edges.jsonl 加载全部边。"""
        if not os.path.exists(self._edges_file):
            return []
        edges = []
        for line in self._read_jsonl(self._edges_file):
            edges.append(self._dict_to_edge(line))
        return edges

    def save_snapshot(self, snapshot: dict, name: str | None = None) -> str:
        """保存快照到 snapshots/<name>.json。"""
        name = name or time.strftime("%Y-%m-%d")
        path = os.path.join(self._snapshot_dir, f"{name}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except OSError as e:
            raise SnapshotError(f"快照保存失败: {e}") from e
        return name

    def load_snapshot(self, name: str) -> dict:
        """加载快照。"""
        path = os.path.join(self._snapshot_dir, f"{name}.json")
        if not os.path.exists(path):
            raise SnapshotError(f"快照不存在: {name}")
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise SnapshotError(f"快照加载失败: {e}") from e

    def list_snapshots(self) -> list[str]:
        """列举全部快照名(不含 .json 后缀)。"""
        if not os.path.exists(self._snapshot_dir):
            return []
        return [
            f[:-5]  # 去掉 .json
            for f in os.listdir(self._snapshot_dir)
            if f.endswith(".json")
        ]

    # -----------------------------------------------------------------------
    # 内部工具
    # -----------------------------------------------------------------------

    @staticmethod
    def _append_jsonl(path: str, record: dict) -> None:
        """追加写一行 JSON 到 JSONL 文件。"""
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            raise TopologyError(f"写入 {path} 失败: {e}") from e

    @staticmethod
    def _read_jsonl(path: str) -> list[dict]:
        """读取 JSONL 文件全部行。"""
        records = []
        try:
            with open(path, encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        raise TopologyError(f"{path} 第 {line_no} 行 JSON 解析失败: {e}") from e
        except OSError as e:
            raise TopologyError(f"读取 {path} 失败: {e}") from e
        return records

    @staticmethod
    def _node_to_dict(node: TopologyNode) -> dict:
        """节点序列化为 dict。"""
        return {
            "node_id": node.node_id,
            "layer": node.layer.value,
            "node_type": node.node_type.value,
            "name": node.name,
            "content": node.content,
            "weight": node.weight,
            "confidence": node.confidence,
            "use_count": node.use_count,
            "freshness": node.freshness,
            "deprecated": node.deprecated,
            "version": node.version,
            "metadata": node.metadata,
            "skill_binding": node.skill_binding,
            "created_at": node.created_at,
            "last_used_at": node.last_used_at,
            "op": "insert",  # 操作类型: 永远 insert
            "ts": time.time(),
        }

    @staticmethod
    def _edge_to_dict(edge: TopologyEdge) -> dict:
        """边序列化为 dict。"""
        return {
            "edge_id": edge.edge_id,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "edge_type": edge.edge_type.value,
            "weight": edge.weight,
            "version": edge.version,
            "deprecated": edge.deprecated,
            "metadata": edge.metadata,
            "created_at": edge.created_at,
            "op": "insert",
            "ts": time.time(),
        }

    @staticmethod
    def _dict_to_node(d: dict) -> TopologyNode:
        """dict 反序列化为节点。"""
        return TopologyNode(
            node_id=d["node_id"],
            layer=TopologyLayer(d["layer"]),
            node_type=__import__("fnixagent.core.types", fromlist=["NodeType"]).NodeType(
                d["node_type"]
            ),
            name=d["name"],
            content=d.get("content", ""),
            weight=d["weight"],
            confidence=d.get("confidence", 0.3),
            use_count=d.get("use_count", 0),
            freshness=d.get("freshness", 1.0),
            deprecated=d.get("deprecated", False),
            version=d.get("version", 1),
            metadata=d.get("metadata", {}),
            skill_binding=d.get("skill_binding"),
            created_at=d.get("created_at", 0.0),
            last_used_at=d.get("last_used_at", 0.0),
        )

    @staticmethod
    def _dict_to_edge(d: dict) -> TopologyEdge:
        """dict 反序列化为边。"""
        return TopologyEdge(
            edge_id=d["edge_id"],
            source_id=d["source_id"],
            target_id=d["target_id"],
            edge_type=EdgeType(d["edge_type"]),
            weight=d["weight"],
            version=d.get("version", 1),
            deprecated=d.get("deprecated", False),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", 0.0),
        )


# ---------------------------------------------------------------------------
# 存储管理器(封装"图 ↔ 存储"同步逻辑)
# ---------------------------------------------------------------------------


class TopologyStoreManager:
    """拓扑图与存储后端的同步管理器。

    职责:
        - 启动时从存储加载全部节点/边到内存图
        - 图变更时自动追加写存储(保持一致性)
        - 定期触发快照
    """

    def __init__(
        self,
        graph: TopologyGraph,
        store: TopologyStore,
        snapshot_interval: int = 100,
    ) -> None:
        """初始化存储管理器。

        Args:
            graph: 拓扑图实例
            store: 存储后端
            snapshot_interval: 每 N 次写入触发快照
        """
        # 延迟导入避免循环
        self._graph = graph
        self._store = store
        self._snapshot_interval = snapshot_interval
        self._write_count = 0

    def load_from_store(self) -> None:
        """从存储加载全部数据到内存图。"""
        # 用快照恢复更快,否则逐条加载
        snapshots = self._store.list_snapshots()
        if snapshots:
            # 取最新快照
            latest = sorted(snapshots)[-1]
            snapshot = self._store.load_snapshot(latest)
            self._graph.restore(snapshot)
        else:
            # 无快照,从 JSONL 逐条加载
            for node in self._store.load_all_nodes():
                if not self._graph.has_node(node.node_id):
                    # 直接注入图(已序列化,无需重新校验)
                    self._graph._nodes[node.node_id] = node
            for edge in self._store.load_all_edges():
                if edge.edge_id not in self._graph._edges:
                    self._graph._edges[edge.edge_id] = edge
                    self._graph._out_edges[edge.source_id].append(edge.edge_id)
                    self._graph._in_edges[edge.target_id].append(edge.edge_id)

    def persist_node(self, node: TopologyNode) -> None:
        """节点写入存储。"""
        self._store.append_node(node)
        self._write_count += 1
        self._maybe_snapshot()

    def persist_edge(self, edge: TopologyEdge) -> None:
        """边写入存储。"""
        self._store.append_edge(edge)
        self._write_count += 1
        self._maybe_snapshot()

    def save_snapshot(self, name: str | None = None) -> str:
        """手动触发快照。"""
        snapshot = self._graph.snapshot()
        return self._store.save_snapshot(snapshot, name)

    def _maybe_snapshot(self) -> None:
        """写入次数达到阈值时自动快照。"""
        if self._write_count > 0 and self._write_count % self._snapshot_interval == 0:
            self.save_snapshot()
