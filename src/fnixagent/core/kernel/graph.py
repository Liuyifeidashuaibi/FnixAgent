"""
图算法 (Graph Algorithms)
===========================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  Graph          - 通用图 (有向/无向/加权), 邻接表存储
  BFS            - 广度优先搜索, O(V+E)
  DFS            - 深度优先搜索, O(V+E)
  Dijkstra       - 单源最短路径 (非负权), O((V+E)logV)
  BellmanFord    - 单源最短路径 (含负权), O(VE)
  FloydWarshall  - 全对最短路径, O(V^3)
  AStar          - A* 启发式搜索, O(b^d)
  TopologicalSort - 拓扑排序 (Kahn 算法), O(V+E)
  KruskalMST     - 最小生成树 (Kruskal), O(ElogE)
  PrimMST        - 最小生成树 (Prim), O(ElogV)
  TarjanSCC      - 强连通分量 (Tarjan), O(V+E)
  CycleDetection - 环检测 (DFS 三色标记)
"""
from __future__ import annotations

import heapq
from collections import defaultdict, deque
from typing import Callable, Generic, Hashable, TypeVar

T = TypeVar("T", bound=Hashable)


# ===========================================================================
# Graph — 通用图数据结构
# ===========================================================================

class Graph(Generic[T]):
    """通用图: 支持有向/无向、加权/无权, 邻接表存储。

    复杂度:
      - 添加边: O(1)
      - 查询邻居: O(1)
      - 空间: O(V + E)

    Example:
        >>> g = Graph[str](directed=True)
        >>> g.add_edge("A", "B", weight=5)
        >>> g.add_edge("B", "C", weight=3)
        >>> g.neighbors("A")  # {"B": 5}
    """

    def __init__(self, directed: bool = False):
        self._directed = directed
        self._adj: dict[T, dict[T, float]] = defaultdict(dict)
        self._nodes: set[T] = set()

    @property
    def directed(self) -> bool:
        return self._directed

    def add_node(self, node: T) -> None:
        self._nodes.add(node)

    def add_edge(self, u: T, v: T, weight: float = 1.0) -> None:
        """添加边 u→v (有向) 或 u-v (无向)。"""
        self._nodes.add(u)
        self._nodes.add(v)
        self._adj[u][v] = weight
        if not self._directed:
            self._adj[v][u] = weight

    def remove_edge(self, u: T, v: T) -> None:
        self._adj[u].pop(v, None)
        if not self._directed:
            self._adj[v].pop(u, None)

    def neighbors(self, node: T) -> dict[T, float]:
        """返回邻居 → 权重。"""
        return dict(self._adj.get(node, {}))

    def has_edge(self, u: T, v: T) -> bool:
        return v in self._adj.get(u, {})

    def weight(self, u: T, v: T) -> float:
        return self._adj.get(u, {}).get(v, float("inf"))

    @property
    def nodes(self) -> set[T]:
        return set(self._nodes)

    @property
    def edge_count(self) -> int:
        total = sum(len(adj) for adj in self._adj.values())
        return total if self._directed else total // 2

    def edges(self) -> list[tuple[T, T, float]]:
        """返回所有边 (u, v, weight)。"""
        result = []
        seen = set()
        for u, neighbors in self._adj.items():
            for v, w in neighbors.items():
                if self._directed or (v, u) not in seen:
                    result.append((u, v, w))
                    seen.add((u, v))
        return result


# ===========================================================================
# BFS — 广度优先搜索
# ===========================================================================

class BFS(Generic[T]):
    """广度优先搜索: 逐层遍历, 可求无权图最短路径。

    复杂度: O(V + E)

    Example:
        >>> g = Graph[int]()
        >>> g.add_edge(0, 1); g.add_edge(0, 2); g.add_edge(1, 3)
        >>> BFS.traverse(g, 0)  # [0, 1, 2, 3]
        >>> BFS.shortest_path(g, 0, 3)  # [0, 1, 3]
    """

    @staticmethod
    def traverse(graph: Graph[T], start: T) -> list[T]:
        """从 start 出发 BFS 遍历, 返回访问顺序。"""
        if start not in graph.nodes:
            return []
        visited: set[T] = {start}
        queue: deque[T] = deque([start])
        result: list[T] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in graph.neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return result

    @staticmethod
    def shortest_path(graph: Graph[T], start: T, end: T) -> list[T] | None:
        """无权图最短路径 (BFS 自然性质)。"""
        if start not in graph.nodes or end not in graph.nodes:
            return None
        if start == end:
            return [start]
        visited: set[T] = {start}
        parent: dict[T, T | None] = {start: None}
        queue: deque[T] = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in graph.neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    parent[neighbor] = node
                    if neighbor == end:
                        # 回溯路径
                        path: list[T] = []
                        cur: T | None = end
                        while cur is not None:
                            path.append(cur)
                            cur = parent[cur]
                        path.reverse()
                        return path
                    queue.append(neighbor)
        return None

    @staticmethod
    def distances(graph: Graph[T], start: T) -> dict[T, int]:
        """从 start 到所有可达节点的跳数。"""
        if start not in graph.nodes:
            return {}
        dist: dict[T, int] = {start: 0}
        queue: deque[T] = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in graph.neighbors(node):
                if neighbor not in dist:
                    dist[neighbor] = dist[node] + 1
                    queue.append(neighbor)
        return dist


# ===========================================================================
# DFS — 深度优先搜索
# ===========================================================================

class DFS(Generic[T]):
    """深度优先搜索: 递归/迭代遍历, 连通分量, 环检测。

    复杂度: O(V + E)

    Example:
        >>> g = Graph[int]()
        >>> g.add_edge(0, 1); g.add_edge(1, 2)
        >>> DFS.traverse(g, 0)  # [0, 1, 2]
        >>> DFS.connected_components(g)  # [[0, 1, 2]]
    """

    @staticmethod
    def traverse(graph: Graph[T], start: T) -> list[T]:
        """迭代 DFS (避免递归深度限制)。"""
        if start not in graph.nodes:
            return []
        visited: set[T] = set()
        result: list[T] = []
        stack: list[T] = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            result.append(node)
            # 逆序入栈, 保证访问顺序与递归一致
            for neighbor in sorted(graph.neighbors(node), reverse=True):
                if neighbor not in visited:
                    stack.append(neighbor)
        return result

    @staticmethod
    def connected_components(graph: Graph[T]) -> list[list[T]]:
        """求无向图连通分量。"""
        visited: set[T] = set()
        components: list[list[T]] = []
        for node in graph.nodes:
            if node not in visited:
                component: list[T] = []
                stack = [node]
                while stack:
                    cur = stack.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    component.append(cur)
                    for neighbor in graph.neighbors(cur):
                        if neighbor not in visited:
                            stack.append(neighbor)
                components.append(component)
        return components


# ===========================================================================
# Dijkstra — 单源最短路径 (非负权)
# ===========================================================================

class Dijkstra(Generic[T]):
    """Dijkstra 最短路径: 优先队列实现, 要求非负权。

    复杂度: O((V + E) log V)

    Example:
        >>> g = Graph[str](directed=True)
        >>> g.add_edge("A", "B", 1); g.add_edge("B", "C", 2); g.add_edge("A", "C", 5)
        >>> Dijkstra.shortest_path(g, "A", "C")  # (3, ["A", "B", "C"])
    """

    @staticmethod
    def shortest_distances(graph: Graph[T], source: T) -> dict[T, float]:
        """单源最短距离。"""
        if source not in graph.nodes:
            return {}
        dist: dict[T, float] = {source: 0.0}
        heap: list[tuple[float, T]] = [(0.0, source)]
        while heap:
            d, node = heapq.heappop(heap)
            if d > dist.get(node, float("inf")):
                continue
            for neighbor, w in graph.neighbors(node).items():
                new_dist = d + w
                if new_dist < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_dist
                    heapq.heappush(heap, (new_dist, neighbor))
        return dist

    @staticmethod
    def shortest_path(
        graph: Graph[T], source: T, target: T
    ) -> tuple[float, list[T]] | None:
        """单源最短路径 (含路径回溯)。

        Returns:
            (总距离, 路径节点列表) 或 None
        """
        if source not in graph.nodes or target not in graph.nodes:
            return None
        dist: dict[T, float] = {source: 0.0}
        parent: dict[T, T | None] = {source: None}
        heap: list[tuple[float, T]] = [(0.0, source)]
        while heap:
            d, node = heapq.heappop(heap)
            if node == target:
                # 回溯路径
                path: list[T] = []
                cur: T | None = target
                while cur is not None:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                return (d, path)
            if d > dist.get(node, float("inf")):
                continue
            for neighbor, w in graph.neighbors(node).items():
                new_dist = d + w
                if new_dist < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_dist
                    parent[neighbor] = node
                    heapq.heappush(heap, (new_dist, neighbor))
        return None


# ===========================================================================
# BellmanFord — 单源最短路径 (含负权)
# ===========================================================================

class BellmanFord(Generic[T]):
    """Bellman-Ford: 支持负权边, 可检测负环。

    复杂度: O(V * E)

    Example:
        >>> g = Graph[str](directed=True)
        >>> g.add_edge("A", "B", 1)
        >>> g.add_edge("B", "C", -2)
        >>> g.add_edge("A", "C", 2)
        >>> BellmanFord.shortest_distances(g, "A")  # {"A": 0, "B": 1, "C": -1}
    """

    @staticmethod
    def shortest_distances(
        graph: Graph[T], source: T
    ) -> tuple[dict[T, float], bool]:
        """单源最短距离。

        Returns:
            (距离字典, 是否存在负环)
        """
        if source not in graph.nodes:
            return {}, False
        dist: dict[T, float] = {n: float("inf") for n in graph.nodes}
        dist[source] = 0.0
        edges = graph.edges()
        nodes = list(graph.nodes)
        # 松弛 V-1 次
        for _ in range(len(nodes) - 1):
            updated = False
            for u, v, w in edges:
                if dist[u] + w < dist.get(v, float("inf")):
                    dist[v] = dist[u] + w
                    updated = True
            if not updated:
                break
        # 检测负环
        has_negative_cycle = False
        for u, v, w in edges:
            if dist[u] + w < dist.get(v, float("inf")):
                has_negative_cycle = True
                break
        return dist, has_negative_cycle


# ===========================================================================
# FloydWarshall — 全对最短路径
# ===========================================================================

class FloydWarshall(Generic[T]):
    """Floyd-Warshall: 所有节点对之间的最短路径。

    复杂度: O(V^3), 适合稠密图小规模 (< 500 节点)。

    Example:
        >>> g = Graph[int](directed=True)
        >>> g.add_edge(0, 1, 3); g.add_edge(1, 2, 1); g.add_edge(0, 2, 10)
        >>> FloydWarshall.all_pairs(g)[0][2]  # 4 (0→1→2)
    """

    @staticmethod
    def all_pairs(graph: Graph[T]) -> dict[T, dict[T, float]]:
        """返回 dist[u][v] = 最短距离。"""
        nodes = list(graph.nodes)
        dist: dict[T, dict[T, float]] = {
            u: {v: (0.0 if u == v else float("inf")) for v in nodes}
            for u in nodes
        }
        for u, v, w in graph.edges():
            dist[u][v] = min(dist[u][v], w)
        for k in nodes:
            for i in nodes:
                if dist[i][k] == float("inf"):
                    continue
                for j in nodes:
                    if dist[k][j] == float("inf"):
                        continue
                    new_dist = dist[i][k] + dist[k][j]
                    if new_dist < dist[i][j]:
                        dist[i][j] = new_dist
        return dist


# ===========================================================================
# AStar — A* 启发式搜索
# ===========================================================================

class AStar(Generic[T]):
    """A* 算法: 启发式最短路径, Dijkstra 的加速版。

    原理:
      - 优先队列按 f(n) = g(n) + h(n) 排序
      - g(n) = 起点到 n 的实际距离
      - h(n) = n 到终点的启发式估计 (admissible: h(n) ≤ 实际距离)

    复杂度: O(b^d) (b = 分支因子, d = 解深度), 启发式好时远优于 Dijkstra。

    Example:
        >>> g = Graph[str](directed=True)
        >>> g.add_edge("A", "B", 1); g.add_edge("B", "C", 1); g.add_edge("A", "C", 5)
        >>> heuristic = lambda n: 0  # 退化为 Dijkstra
        >>> AStar.find_path(g, "A", "C", heuristic)  # (2, ["A", "B", "C"])
    """

    @staticmethod
    def find_path(
        graph: Graph[T],
        start: T,
        goal: T,
        heuristic: Callable[[T], float],
    ) -> tuple[float, list[T]] | None:
        """A* 寻路。

        Args:
            graph: 图
            start: 起点
            goal: 终点
            heuristic: 启发函数 h(node) → 估计到终点的距离

        Returns:
            (总距离, 路径列表) 或 None
        """
        if start not in graph.nodes or goal not in graph.nodes:
            return None
        g_score: dict[T, float] = {start: 0.0}
        f_score: dict[T, float] = {start: heuristic(start)}
        parent: dict[T, T | None] = {start: None}
        open_set: list[tuple[float, T]] = [(f_score[start], start)]
        closed: set[T] = set()
        while open_set:
            _, current = heapq.heappop(open_set)
            if current == goal:
                path: list[T] = []
                cur: T | None = goal
                while cur is not None:
                    path.append(cur)
                    cur = parent[cur]
                path.reverse()
                return (g_score[goal], path)
            if current in closed:
                continue
            closed.add(current)
            for neighbor, w in graph.neighbors(current).items():
                if neighbor in closed:
                    continue
                tentative_g = g_score[current] + w
                if tentative_g < g_score.get(neighbor, float("inf")):
                    parent[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score[neighbor] = tentative_g + heuristic(neighbor)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))
        return None


# ===========================================================================
# TopologicalSort — 拓扑排序
# ===========================================================================

class TopologicalSort(Generic[T]):
    """拓扑排序 (Kahn 算法): 有向无环图线性化。

    复杂度: O(V + E)

    Example:
        >>> g = Graph[str](directed=True)
        >>> g.add_edge("A", "B"); g.add_edge("A", "C"); g.add_edge("B", "D"); g.add_edge("C", "D")
        >>> TopologicalSort.sort(g)  # ["A", "B", "C", "D"] 或 ["A", "C", "B", "D"]
    """

    @staticmethod
    def sort(graph: Graph[T]) -> list[T] | None:
        """返回拓扑序, 存在环则返回 None。"""
        in_degree: dict[T, int] = {n: 0 for n in graph.nodes}
        for u, v, _ in graph.edges():
            in_degree[v] = in_degree.get(v, 0) + 1
        queue: deque[T] = deque(
            n for n in graph.nodes if in_degree.get(n, 0) == 0
        )
        result: list[T] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in graph.neighbors(node):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        if len(result) != len(graph.nodes):
            return None  # 存在环
        return result


# ===========================================================================
# KruskalMST — 最小生成树 (Kruskal)
# ===========================================================================

class KruskalMST(Generic[T]):
    """Kruskal 最小生成树: 贪心选最小边, 并查集判环。

    复杂度: O(E log E)

    Example:
        >>> g = Graph[str]()
        >>> g.add_edge("A", "B", 4); g.add_edge("A", "C", 1); g.add_edge("B", "C", 2)
        >>> KruskalMST.mst(g)  # [("A", "C", 1), ("B", "C", 2)]
    """

    @staticmethod
    def mst(graph: Graph[T]) -> list[tuple[T, T, float]]:
        """返回最小生成树的边集 (无向图)。"""
        if graph.directed:
            raise ValueError("Kruskal 需要无向图")
        edges = sorted(graph.edges(), key=lambda e: e[2])
        parent: dict[T, T] = {n: n for n in graph.nodes}

        def find(x: T) -> T:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: T, y: T) -> bool:
            rx, ry = find(x), find(y)
            if rx == ry:
                return False
            parent[rx] = ry
            return True

        result: list[tuple[T, T, float]] = []
        for u, v, w in edges:
            if union(u, v):
                result.append((u, v, w))
        return result


# ===========================================================================
# PrimMST — 最小生成树 (Prim)
# ===========================================================================

class PrimMST(Generic[T]):
    """Prim 最小生成树: 从任意起点扩展, 优先队列选最小边。

    复杂度: O(E log V)
    """

    @staticmethod
    def mst(graph: Graph[T]) -> list[tuple[T, T, float]]:
        if graph.directed:
            raise ValueError("Prim 需要无向图")
        nodes = list(graph.nodes)
        if not nodes:
            return []
        start = nodes[0]
        in_tree: set[T] = {start}
        heap: list[tuple[float, T, T]] = []  # (weight, from, to)
        for neighbor, w in graph.neighbors(start).items():
            heapq.heappush(heap, (w, start, neighbor))
        result: list[tuple[T, T, float]] = []
        while heap and len(in_tree) < len(nodes):
            w, u, v = heapq.heappop(heap)
            if v in in_tree:
                continue
            in_tree.add(v)
            result.append((u, v, w))
            for neighbor, nw in graph.neighbors(v).items():
                if neighbor not in in_tree:
                    heapq.heappush(heap, (nw, v, neighbor))
        return result


# ===========================================================================
# TarjanSCC — 强连通分量
# ===========================================================================

class TarjanSCC(Generic[T]):
    """Tarjan 强连通分量: 单次 DFS, 低链接值。

    复杂度: O(V + E)

    Example:
        >>> g = Graph[int](directed=True)
        >>> g.add_edge(0, 1); g.add_edge(1, 2); g.add_edge(2, 0); g.add_edge(2, 3)
        >>> TarjanSCC.sccs(g)  # [[3], [0, 1, 2]]
    """

    @staticmethod
    def sccs(graph: Graph[T]) -> list[list[T]]:
        """返回所有强连通分量。"""
        index_counter = [0]
        stack: list[T] = []
        on_stack: set[T] = set()
        index: dict[T, int] = {}
        lowlink: dict[T, int] = {}
        result: list[list[T]] = []

        def strongconnect(node: T) -> None:
            index[node] = index_counter[0]
            lowlink[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack.add(node)
            for successor in graph.neighbors(node):
                if successor not in index:
                    strongconnect(successor)
                    lowlink[node] = min(lowlink[node], lowlink[successor])
                elif successor in on_stack:
                    lowlink[node] = min(lowlink[node], index[successor])
            if lowlink[node] == index[node]:
                component: list[T] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == node:
                        break
                result.append(component)

        for node in graph.nodes:
            if node not in index:
                strongconnect(node)
        return result


# ===========================================================================
# CycleDetection — 环检测
# ===========================================================================

class CycleDetection(Generic[T]):
    """环检测: DFS 三色标记法 (白/灰/黑)。

    复杂度: O(V + E)

    Example:
        >>> g = Graph[int](directed=True)
        >>> g.add_edge(0, 1); g.add_edge(1, 2); g.add_edge(2, 0)
        >>> CycleDetection.has_cycle(g)  # True
    """

    @staticmethod
    def has_cycle(graph: Graph[T]) -> bool:
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[T, int] = {n: WHITE for n in graph.nodes}

        def dfs(node: T) -> bool:
            color[node] = GRAY
            for neighbor in graph.neighbors(node):
                if color.get(neighbor, WHITE) == GRAY:
                    return True
                if color.get(neighbor, WHITE) == WHITE:
                    if dfs(neighbor):
                        return True
            color[node] = BLACK
            return False

        for node in graph.nodes:
            if color[node] == WHITE:
                if dfs(node):
                    return True
        return False

    @staticmethod
    def find_cycle(graph: Graph[T]) -> list[T] | None:
        """返回一个环的节点序列, 无环返回 None。"""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[T, int] = {n: WHITE for n in graph.nodes}
        parent: dict[T, T | None] = {n: None for n in graph.nodes}

        def dfs(node: T) -> T | None:
            color[node] = GRAY
            for neighbor in graph.neighbors(node):
                if color.get(neighbor, WHITE) == GRAY:
                    return neighbor  # 找到回边
                if color.get(neighbor, WHITE) == WHITE:
                    parent[neighbor] = node
                    result = dfs(neighbor)
                    if result is not None:
                        return result
            color[node] = BLACK
            return None

        for node in graph.nodes:
            if color[node] == WHITE:
                cycle_start = dfs(node)
                if cycle_start is not None:
                    # 回溯环路径
                    cycle: list[T] = [cycle_start]
                    cur = parent.get(cycle_start)
                    while cur is not None and cur != cycle_start:
                        cycle.append(cur)
                        cur = parent[cur]
                    cycle.append(cycle_start)
                    cycle.reverse()
                    return cycle
        return None
