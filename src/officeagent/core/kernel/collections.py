"""
高性能数据结构 (High-Performance Collections)
==============================================
纯 Python + stdlib 实现,零外部依赖,可直接拷贝到任何项目。

模块清单:
  BloomFilter    - 布隆过滤器 (概率集合, O(k) 判断)
  LRUCache       - 线程安全 LRU 缓存 (O(1) 存取)
  RingBuffer     - 固定大小环形缓冲区 (O(1) 读写)
  SkipList       - 跳表 (O(log n) 插入/查找/删除)
  Trie           - 前缀树 (O(k) 插入/查找)
  BitArray       - 紧凑位数组 (~1/64 内存)
  SparseVector   - 稀疏向量 (hash 实现, 高维稀疏高效)
  DisjointSet    - 并查集 (O(α(n)) 合并/查找)
  MinMaxHeap     - 双端堆 (O(1) 最小值+最大值, O(log n) 插入)
  SortedSet      - 有序集合 (二分插入, O(log n) 查找)
"""
from __future__ import annotations

import heapq
import math
import random
import threading
from collections import OrderedDict
from typing import Any, Generic, Iterable, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

# ===========================================================================
# BloomFilter — 布隆过滤器
# ===========================================================================


class BloomFilter:
    """布隆过滤器: 概率集合, 判断元素"可能存在"或"一定不存在"。

    原理:
      - 用 k 个哈希函数将元素映射到 m 位位数组
      - 插入: 置 k 位为 1
      - 查询: 所有 k 位为 1 → "可能存在"; 任一位为 0 → "一定不存在"
      - 假阳性率 ε ≈ (1 - e^(-kn/m))^k

    复杂度:
      - 插入: O(k)
      - 查询: O(k)
      - 空间: O(m/8) 字节

    Args:
        capacity: 预期元素数量
        false_positive_rate: 目标假阳性率 (0 < ε < 1)

    Example:
        >>> bf = BloomFilter(1000, 0.01)
        >>> bf.add("hello")
        >>> "hello" in bf  # True
        >>> "world" in bf  # False (大概率)
    """

    def __init__(self, capacity: int, false_positive_rate: float = 0.01) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity 必须为正: {capacity}")
        if not (0 < false_positive_rate < 1):
            raise ValueError(f"false_positive_rate 必须在 (0, 1): {false_positive_rate}")

        # 最优位数组大小: m = -n*ln(ε) / (ln2)^2
        self._m = max(1, int(-capacity * math.log(false_positive_rate) / (math.log(2) ** 2)))
        # 最优哈希函数数: k = (m/n) * ln2
        self._k = max(1, int(self._m / capacity * math.log(2)))
        # 位数组 (bytearray, 每个元素 1 bit)
        self._bits = bytearray((self._m + 7) // 8)
        self._count = 0

    def _hash(self, item: object) -> list[int]:
        """双哈希函数生成 k 个哈希位置 (Kirsch-Mitzenmacher 方法)。"""
        raw = hash(str(item).encode())
        h1 = raw & 0xFFFFFFFF
        h2 = (raw >> 32) & 0xFFFFFFFF
        return [(h1 + i * h2) % self._m for i in range(self._k)]

    def add(self, item: object) -> None:
        """插入元素。"""
        for pos in self._hash(item):
            byte_idx = pos >> 3
            bit_idx = pos & 7
            self._bits[byte_idx] |= (1 << bit_idx)
        self._count += 1

    def __contains__(self, item: object) -> bool:
        """判断元素可能存在。"""
        for pos in self._hash(item):
            byte_idx = pos >> 3
            bit_idx = pos & 7
            if not (self._bits[byte_idx] & (1 << bit_idx)):
                return False
        return True

    def __len__(self) -> int:
        return self._count

    @property
    def false_positive_rate(self) -> float:
        """当前假阳性率估算。"""
        if self._count == 0:
            return 0.0
        return (1.0 - math.exp(-self._k * self._count / self._m)) ** self._k


# ===========================================================================
# LRUCache — 线程安全 LRU 缓存
# ===========================================================================


class LRUCache(Generic[K, V]):
    """线程安全 LRU (最近最少使用) 缓存。

    算法:
      - OrderedDict 维护插入顺序, move_to_end 实现 O(1) 访问排到队尾
      - 队首为最久未使用, 容量满时淘汰

    复杂度:
      - get: O(1)
      - put: O(1)

    Args:
        capacity: 最大容量 (必须为正)
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity 必须为正: {capacity}")
        self._capacity = capacity
        self._store: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: K) -> V | None:
        """获取值, 命中则排到队尾 (最近使用)。"""
        with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    def put(self, key: K, value: V) -> None:
        """写入/更新, 容量满时淘汰最久未使用。"""
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            if len(self._store) > self._capacity:
                self._store.popitem(last=False)

    def pop(self, key: K) -> V | None:
        """移除并返回值。"""
        with self._lock:
            return self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._store

    def keys(self) -> list[K]:
        with self._lock:
            return list(self._store.keys())


# ===========================================================================
# RingBuffer — 固定大小环形缓冲区
# ===========================================================================


class RingBuffer(Generic[T]):
    """固定大小环形缓冲区 (FIFO)。

    复杂度:
      - push: O(1)
      - pop: O(1)
      - 空间: O(capacity)

    Args:
        capacity: 缓冲区容量 (必须为正)

    Example:
        >>> rb = RingBuffer[int](3)
        >>> rb.push(1); rb.push(2); rb.push(3)
        >>> rb.push(4)  # 覆盖 1
        >>> list(rb)  # [2, 3, 4]
    """

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity 必须为正: {capacity}")
        self._capacity = capacity
        self._buffer: list[T | None] = [None] * capacity
        self._head = 0  # 读指针
        self._tail = 0  # 写指针
        self._size = 0

    def push(self, item: T) -> None:
        """写入元素, 满时覆盖最旧元素。"""
        self._buffer[self._tail] = item
        self._tail = (self._tail + 1) % self._capacity
        if self._size < self._capacity:
            self._size += 1
        else:
            self._head = (self._head + 1) % self._capacity

    def pop(self) -> T | None:
        """读取并移除最旧元素。"""
        if self._size == 0:
            return None
        item = self._buffer[self._head]
        self._buffer[self._head] = None
        self._head = (self._head + 1) % self._capacity
        self._size -= 1
        return item

    def peek(self) -> T | None:
        """查看最旧元素 (不移除)。"""
        if self._size == 0:
            return None
        return self._buffer[self._head]

    def __len__(self) -> int:
        return self._size

    def __iter__(self):
        for i in range(self._size):
            yield self._buffer[(self._head + i) % self._capacity]

    def __bool__(self) -> bool:
        return self._size > 0

    def clear(self) -> None:
        self._buffer = [None] * self._capacity
        self._head = self._tail = self._size = 0


# ===========================================================================
# Trie — 前缀树
# ===========================================================================


class TrieNode:
    """Trie 节点。"""
    __slots__ = ("children", "is_end", "value")

    def __init__(self):
        self.children: dict[str, TrieNode] = {}
        self.is_end: bool = False
        self.value: Any = None


class Trie:
    """前缀树 (字典树)。

    复杂度:
      - 插入: O(k)  (k = 键长度)
      - 查找: O(k)
      - 前缀搜索: O(k + m)  (m = 子树大小)

    Example:
        >>> t = Trie()
        >>> t.insert("hello", 1)
        >>> t.search("hello")  # 1
        >>> t.starts_with("hel")  # ["hello"]
    """

    def __init__(self):
        self._root = TrieNode()
        self._size = 0

    def insert(self, key: str, value: Any = None) -> None:
        """插入键值对。"""
        node = self._root
        for ch in key:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        if not node.is_end:
            self._size += 1
        node.is_end = True
        node.value = value

    def search(self, key: str) -> Any | None:
        """精确查找, 返回 value 或 None。"""
        node = self._root
        for ch in key:
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node.value if node.is_end else None

    def starts_with(self, prefix: str) -> list[str]:
        """返回所有以 prefix 开头的键。"""
        node = self._root
        for ch in prefix:
            if ch not in node.children:
                return []
            node = node.children[ch]
        result: list[str] = []
        self._collect(node, prefix, result)
        return result

    def _collect(self, node: TrieNode, prefix: str, result: list[str]) -> None:
        if node.is_end:
            result.append(prefix)
        for ch, child in node.children.items():
            self._collect(child, prefix + ch, result)

    def remove(self, key: str) -> bool:
        """删除键, 返回是否成功。"""
        path: list[tuple[TrieNode, str]] = []
        node = self._root
        for ch in key:
            if ch not in node.children:
                return False
            path.append((node, ch))
            node = node.children[ch]
        if not node.is_end:
            return False
        node.is_end = False
        self._size -= 1
        # 清理无用节点 (从叶子到根, 删到有子节点或 is_end 的节点为止)
        for parent, ch in reversed(path):
            child = parent.children[ch]
            if child.children or child.is_end:
                break
            del parent.children[ch]
        return True

    def __len__(self) -> int:
        return self._size

    def __contains__(self, key: str) -> bool:
        return self.search(key) is not None


# ===========================================================================
# BitArray — 紧凑位数组
# ===========================================================================


class BitArray:
    """紧凑位数组, 内存约为 Python list[bool] 的 1/64。

    复杂度:
      - get/set: O(1)
      - 空间: O(n/8) 字节

    Example:
        >>> ba = BitArray(100)
        >>> ba[0] = 1
        >>> ba[0]  # True
        >>> ba.popcount()  # 1
    """

    def __init__(self, size: int):
        if size < 0:
            raise ValueError(f"size 不能为负: {size}")
        self._size = size
        self._bits = bytearray((size + 7) // 8)

    def __getitem__(self, index: int) -> bool:
        if not (0 <= index < self._size):
            raise IndexError(f"索引 {index} 超出范围 [0, {self._size})")
        byte_idx = index >> 3
        bit_idx = index & 7
        return bool(self._bits[byte_idx] & (1 << bit_idx))

    def __setitem__(self, index: int, value: bool) -> None:
        if not (0 <= index < self._size):
            raise IndexError(f"索引 {index} 超出范围 [0, {self._size})")
        byte_idx = index >> 3
        bit_idx = index & 7
        if value:
            self._bits[byte_idx] |= (1 << bit_idx)
        else:
            self._bits[byte_idx] &= ~(1 << bit_idx)

    def __len__(self) -> int:
        return self._size

    def popcount(self) -> int:
        """返回 1 的个数 (内置 int.bit_count 逐 byte 累加)。"""
        return sum(b.bit_count() for b in self._bits)

    def set_all(self, value: bool) -> None:
        """全部置为 0 或 1。"""
        v = 0xFF if value else 0x00
        for i in range(len(self._bits)):
            self._bits[i] = v

    def __repr__(self) -> str:
        n = min(64, self._size)
        bits = "".join("1" if self[i] else "0" for i in range(n))
        suffix = f"... ({self._size} bits)" if self._size > 64 else ""
        return f"BitArray({bits}{suffix})"


# ===========================================================================
# SparseVector — 稀疏向量
# ===========================================================================


class SparseVector:
    """稀疏向量 (hash map 实现), 高维向量节省内存。

    复杂度:
      - dot: O(min(|A|, |B|))
      - 空间: O(非零元数)

    Example:
        >>> sv = SparseVector({0: 1.0, 100: 2.0})
        >>> sv.dot(SparseVector({0: 0.5, 100: 1.0}))  # 2.5
    """

    def __init__(self, values: dict[int, float] | None = None):
        self._data: dict[int, float] = dict(values) if values else {}

    def dot(self, other: SparseVector) -> float:
        """点积 (遍历较短向量)。"""
        if len(self._data) > len(other._data):
            return other.dot(self)
        return sum(v * other._data.get(k, 0.0) for k, v in self._data.items())

    def norm(self) -> float:
        return math.sqrt(sum(v * v for v in self._data.values()))

    def cosine_similarity(self, other: SparseVector) -> float:
        na, nb = self.norm(), other.norm()
        if na < 1e-12 or nb < 1e-12:
            return 0.0
        return self.dot(other) / (na * nb)

    def __getitem__(self, index: int) -> float:
        return self._data.get(index, 0.0)

    def __setitem__(self, index: int, value: float) -> None:
        if value == 0.0:
            self._data.pop(index, None)
        else:
            self._data[index] = value

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data.items())


# ===========================================================================
# DisjointSet — 并查集
# ===========================================================================


class DisjointSet:
    """并查集 (Union-Find), 路径压缩 + 按秩合并。

    复杂度:
      - find:  O(α(n))  (逆阿克曼函数, 近似 O(1))
      - union: O(α(n))

    Example:
        >>> ds = DisjointSet(5)
        >>> ds.union(0, 2)
        >>> ds.connected(0, 2)  # True
    """

    def __init__(self, n: int = 0):
        self._parent = list(range(n))
        self._rank = [0] * n
        self._count = n

    def find(self, x: int) -> int:
        """查找 x 的根 (含路径压缩)。"""
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # 路径压缩 (跳两步)
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> bool:
        """合并 x 和 y 所在集合, 返回是否合并成功。"""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        # 按秩合并: 小树挂大树下
        if self._rank[rx] < self._rank[ry]:
            self._parent[rx] = ry
        elif self._rank[rx] > self._rank[ry]:
            self._parent[ry] = rx
        else:
            self._parent[ry] = rx
            self._rank[rx] += 1
        self._count -= 1
        return True

    def connected(self, x: int, y: int) -> bool:
        return self.find(x) == self.find(y)

    def add(self) -> int:
        """添加一个新元素, 返回其索引。"""
        idx = len(self._parent)
        self._parent.append(idx)
        self._rank.append(0)
        self._count += 1
        return idx

    def __len__(self) -> int:
        return len(self._parent)

    @property
    def components(self) -> int:
        """连通分量个数。"""
        return self._count

    def groups(self) -> list[list[int]]:
        """返回所有连通分量。"""
        groups: dict[int, list[int]] = {}
        for i in range(len(self._parent)):
            groups.setdefault(self.find(i), []).append(i)
        return list(groups.values())


# ===========================================================================
# MinMaxHeap — 双端堆
# ===========================================================================


class MinMaxHeap(Generic[T]):
    """双端堆: O(1) 同时获取最小值和最大值, O(log n) 插入/删除。

    内部用两个堆 + 懒删除标记实现, 避免维护复杂平衡树。
    """
    def __init__(self, items: Iterable[T] | None = None):
        self._min_heap: list[T] = []
        self._max_heap: list[T] = []
        self._deleted: dict[T, int] = {}
        if items:
            for item in items:
                self.push(item)

    def push(self, item: T) -> None:
        heapq.heappush(self._min_heap, item)
        heapq.heappush(self._max_heap, _Reverse(item))

    def pop_min(self) -> T:
        self._clean()
        if not self._min_heap:
            raise IndexError("pop from empty MinMaxHeap")
        item = heapq.heappop(self._min_heap)
        self._deleted[item] = self._deleted.get(item, 0) + 1
        return item

    def pop_max(self) -> T:
        self._clean()
        if not self._max_heap:
            raise IndexError("pop from empty MinMaxHeap")
        item = heapq.heappop(self._max_heap).value
        self._deleted[item] = self._deleted.get(item, 0) + 1
        return item

    def peek_min(self) -> T:
        self._clean()
        if not self._min_heap:
            raise IndexError("peek from empty MinMaxHeap")
        return self._min_heap[0]

    def peek_max(self) -> T:
        self._clean()
        if not self._max_heap:
            raise IndexError("peek from empty MinMaxHeap")
        return self._max_heap[0].value

    def _clean(self) -> None:
        while self._min_heap and self._deleted.get(self._min_heap[0], 0) > 0:
            item = heapq.heappop(self._min_heap)
            self._deleted[item] -= 1
            if self._deleted[item] == 0:
                del self._deleted[item]
        while self._max_heap and self._deleted.get(self._max_heap[0].value, 0) > 0:
            item = heapq.heappop(self._max_heap).value
            self._deleted[item] -= 1
            if self._deleted[item] == 0:
                del self._deleted[item]

    def __len__(self) -> int:
        return len(self._min_heap) - sum(self._deleted.values())

    def __bool__(self) -> bool:
        return len(self) > 0


class _Reverse(Generic[T]):
    """包裹器: 反转比较顺序, 用于 max-heap。"""
    __slots__ = ("value",)

    def __init__(self, value: T):
        self.value = value

    def __lt__(self, other: _Reverse) -> bool:
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Reverse):
            return NotImplemented
        return self.value == other.value


# ===========================================================================
# SortedSet — 有序集合
# ===========================================================================


class SortedSet(Generic[T]):
    """有序集合: 二分插入 + 二分查找, O(log n) 查找/插入, O(n) 删除。

    适用于小到中等规模 (n < 10^4), 更大规模用 bisect + 链表。
    """
    def __init__(self, items: Iterable[T] | None = None):
        self._data: list[T] = []
        if items:
            self._data = sorted(items)

    def add(self, item: T) -> bool:
        """插入元素, 返回是否新增。"""
        import bisect
        idx = bisect.bisect_left(self._data, item)
        if idx < len(self._data) and self._data[idx] == item:
            return False
        self._data.insert(idx, item)
        return True

    def remove(self, item: T) -> bool:
        import bisect
        idx = bisect.bisect_left(self._data, item)
        if idx < len(self._data) and self._data[idx] == item:
            self._data.pop(idx)
            return True
        return False

    def __contains__(self, item: T) -> bool:
        import bisect
        idx = bisect.bisect_left(self._data, item)
        return idx < len(self._data) and self._data[idx] == item

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def __getitem__(self, index: int) -> T:
        return self._data[index]

    def floor(self, item: T) -> T | None:
        """返回 <= item 的最大元素。"""
        import bisect
        idx = bisect.bisect_right(self._data, item) - 1
        return self._data[idx] if 0 <= idx < len(self._data) else None

    def ceil(self, item: T) -> T | None:
        """返回 >= item 的最小元素。"""
        import bisect
        idx = bisect.bisect_left(self._data, item)
        return self._data[idx] if idx < len(self._data) else None