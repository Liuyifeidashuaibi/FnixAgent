"""
概率数据结构 (Probabilistic Data Structures)
=============================================
纯 Python + stdlib 实现,零外部依赖。

数据精确度与内存的权衡: 用可接受的误差换取大幅内存节省。

模块清单:
  HyperLogLog      - 基数估算 (去重计数), 误差 ~2%, 内存 ~1.5KB
  CountMinSketch   - 频率估算 (Top-K), 误差 ε·n, 内存 O(log(1/δ)/ε)
  ReservoirSampling - 蓄水池抽样, 从流中等概率选取 k 个样本
  CuckooFilter     - 布谷鸟过滤器, 支持删除的布隆过滤器, 更省空间
  HeavyKeeper      - HeavyKeeper Top-K, 比 Count-Min 更精确的重元素检测
  SkipListIndex    - 跳表索引, O(log n) 概率平衡, 替代红黑树
"""
from __future__ import annotations

import hashlib
import math
import random
import struct
from typing import Generic, Iterable, TypeVar

T = TypeVar("T")


# ===========================================================================
# HyperLogLog — 基数估算
# ===========================================================================

class HyperLogLog:
    """HyperLogLog: 估算集合中不同元素的数量 (基数)。

    原理:
      1. 对每个元素计算哈希值, 观察前导零的个数 (ρ = HLL 的"桶")
      2. 每个桶记录最大 ρ 值
      3. 基数 ≈ α_m * m^2 / Σ(2^{-ρ_i}),  α_m 为修正因子

    性质:
      - 标准误差: 1.04 / √m  (m = 桶数)
      - 默认 m=2^14=16384 → 误差 ≈ 0.81%
      - 内存: O(m * log log N) ≈ m * 6 bits

    复杂度:
      - add: O(1)
      - count: O(m)  (m = 桶数)

    Example:
        >>> hll = HyperLogLog(p=14)
        >>> for x in range(100000):
        ...     hll.add(f"item_{x}")
        >>> hll.count()  # ≈ 100000 (误差 < 1%)
    """

    def __init__(self, p: int = 14):
        """初始化。

        Args:
            p: 精度参数, 桶数 m = 2^p。p 在 [4, 16] 之间。
        """
        if not (4 <= p <= 16):
            raise ValueError(f"p 必须在 [4, 16]: {p}")
        self._p = p
        self._m = 1 << p
        self._registers = [0] * self._m
        self._alpha = self._compute_alpha(self._m)

    @staticmethod
    def _compute_alpha(m: int) -> float:
        """修正因子。"""
        if m == 16:
            return 0.673
        elif m == 32:
            return 0.697
        elif m == 64:
            return 0.709
        else:
            return 0.7213 / (1 + 1.079 / m)

    def add(self, item: object) -> None:
        """添加元素。"""
        h = self._hash(item)
        idx = h & (self._m - 1)          # 低 p 位为桶索引
        w = h >> self._p                 # 高位计算前导零
        rho = (w.bit_length() + 1) if w > 0 else (64 - self._p + 1)
        if rho > self._registers[idx]:
            self._registers[idx] = rho

    def _hash(self, item: object) -> int:
        s = str(item).encode("utf-8")
        digest = hashlib.sha256(s).digest()
        return int.from_bytes(digest[:8], "little")

    def count(self) -> int:
        """估算基数。"""
        # 调和平均
        z = sum(2.0 ** (-r) for r in self._registers)
        raw = self._alpha * self._m * self._m / z
        # 小范围修正
        if raw <= 2.5 * self._m:
            # 线性计数修正
            zeros = self._registers.count(0)
            if zeros > 0:
                return int(self._m * math.log(self._m / zeros))
        return int(raw)

    def merge(self, other: HyperLogLog) -> HyperLogLog:
        """合并两个 HLL (取每个桶的最大值)。"""
        if self._p != other._p:
            raise ValueError(f"精度参数不一致: {self._p} vs {other._p}")
        result = HyperLogLog(self._p)
        for i in range(self._m):
            result._registers[i] = max(self._registers[i], other._registers[i])
        return result

    def __len__(self) -> int:
        return self.count()


# ===========================================================================
# CountMinSketch — 频率估算
# ===========================================================================

class CountMinSketch(Generic[T]):
    """Count-Min Sketch: 估算每个元素的频率 (计数)。

    原理:
      - d 行哈希表, 每行 w 个桶
      - 插入: 对每行, hash(item) 映射到桶, 桶计数 +1
      - 查询: 返回所有行中最小值 (保证 count ≤ estimate ≤ count + ε·N)

    性质:
      - 误差: ε = e/w (期望), 置信度 1-δ = 1 - e^{-d}
      - 默认 ε=0.001, δ=0.01 → w=2719, d=5

    复杂度:
      - add: O(d)
      - query: O(d)
      - 空间: O(d * w)

    Example:
        >>> cms = CountMinSketch[str](epsilon=0.01, delta=0.01)
        >>> cms.add("hello", 3)
        >>> cms.add("hello", 2)
        >>> cms.query("hello")  # 5 (精确)
        >>> cms.query("world")  # 0 (可能偏大)
    """

    def __init__(self, epsilon: float = 0.001, delta: float = 0.01):
        if not (0 < epsilon < 1):
            raise ValueError(f"epsilon 必须在 (0, 1): {epsilon}")
        if not (0 < delta < 1):
            raise ValueError(f"delta 必须在 (0, 1): {delta}")
        self._w = int(math.ceil(math.e / epsilon))
        self._d = int(math.ceil(math.log(1 / delta)))
        self._table: list[list[int]] = [[0] * self._w for _ in range(self._d)]
        self._total = 0
        self._hash_seeds = [random.randint(0, 2**31 - 1) for _ in range(self._d)]

    def _hash(self, item: object, seed: int) -> int:
        # 使用不同 seed 生成独立哈希值
        raw = str(hash(f"{seed}:{hash(item)}")).encode()
        return int.from_bytes(hashlib.md5(raw).digest()[:4], "little") % self._w

    def add(self, item: T, count: int = 1) -> None:
        """增加计数。"""
        self._total += count
        for i in range(self._d):
            col = self._hash(item, self._hash_seeds[i])
            self._table[i][col] += count

    def query(self, item: T) -> int:
        """估算频率 (可能偏大, 但不会偏小)。"""
        return min(self._table[i][self._hash(item, self._hash_seeds[i])]
                   for i in range(self._d))

    def __getitem__(self, item: T) -> int:
        return self.query(item)

    @property
    def total(self) -> int:
        return self._total


# ===========================================================================
# ReservoirSampling — 蓄水池抽样
# ===========================================================================

class ReservoirSampling(Generic[T]):
    """蓄水池抽样: 从流中随机选取 k 个样本, 等概率。

    原理 (Algorithm R):
      1. 前 k 个元素直接放入蓄水池
      2. 第 i 个元素 (i > k): 以 k/i 的概率替换蓄水池中随机位置

    性质:
      - 每个元素被选中的概率 = k/N
      - 不需要预知总数据量 N

    复杂度:
      - 每个元素: O(1)
      - 空间: O(k)

    Example:
        >>> rs = ReservoirSampling[str](k=100)
        >>> for item in large_stream:
        ...     rs.add(item)
        >>> sample = rs.sample  # 100 个等概率样本
    """

    def __init__(self, k: int, seed: int | None = None):
        if k <= 0:
            raise ValueError(f"k 必须为正: {k}")
        self._k = k
        self._reservoir: list[T] = []
        self._count = 0
        self._rng = random.Random(seed)

    def add(self, item: T) -> None:
        """添加一个元素到流中。"""
        self._count += 1
        if len(self._reservoir) < self._k:
            self._reservoir.append(item)
        else:
            j = self._rng.randint(0, self._count - 1)
            if j < self._k:
                self._reservoir[j] = item

    @property
    def sample(self) -> list[T]:
        """返回当前样本 (复制)。"""
        return list(self._reservoir)

    @property
    def count(self) -> int:
        return self._count

    def __len__(self) -> int:
        return len(self._reservoir)


# ===========================================================================
# WeightedReservoir — 加权蓄水池抽样
# ===========================================================================

class WeightedReservoir(Generic[T]):
    """加权蓄水池抽样 (A-Chao 算法)。

    每条数据带权重 w, 抽样概率 ∝ w。

    原理:
      1. 前 k 个元素放入蓄水池
      2. 计算总权重 W
      3. 第 i 个元素以 w_i / W 的概率替换蓄水池中元素

    Example:
        >>> wr = WeightedReservoir[str](k=100)
        >>> wr.add("important", weight=10.0)
        >>> wr.add("normal", weight=1.0)
    """

    def __init__(self, k: int, seed: int | None = None):
        if k <= 0:
            raise ValueError(f"k 必须为正: {k}")
        self._k = k
        self._reservoir: list[tuple[T, float]] = []  # (item, weight)
        self._total_weight = 0.0
        self._rng = random.Random(seed)

    def add(self, item: T, weight: float = 1.0) -> None:
        if weight <= 0:
            raise ValueError(f"权重必须为正: {weight}")
        self._total_weight += weight
        if len(self._reservoir) < self._k:
            self._reservoir.append((item, weight))
        else:
            p = weight / self._total_weight
            if self._rng.random() < p:
                # 按权重比例选择替换位置
                idx = self._weighted_random_index()
                self._reservoir[idx] = (item, weight)

    def _weighted_random_index(self) -> int:
        r = self._rng.random() * sum(w for _, w in self._reservoir)
        cumulative = 0.0
        for i, (_, w) in enumerate(self._reservoir):
            cumulative += w
            if r <= cumulative:
                return i
        return len(self._reservoir) - 1

    @property
    def sample(self) -> list[T]:
        return [item for item, _ in self._reservoir]

    @property
    def total_weight(self) -> float:
        return self._total_weight


# ===========================================================================
# CuckooFilter — 布谷鸟过滤器
# ===========================================================================

class CuckooFilter:
    """布谷鸟过滤器: 支持删除的近似集合, 比 BloomFilter 更省空间。

    原理:
      - 每个元素计算指纹 (fingerprint), 存入双候选桶
      - 冲突时踢出旧元素, 旧元素尝试另一候选桶
      - 删除: 直接移除指纹即可

    性质:
      - 假阳性率: ε ≈ 2^{b-8} / bucket_size  (b = 指纹位数)
      - 支持删除
      - 空间效率高于 BloomFilter (相同假阳性率下)

    复杂度:
      - 插入/查找/删除: O(1) 期望
      - 空间: O(n * b) bits

    Example:
        >>> cf = CuckooFilter(capacity=1000)
        >>> cf.insert("hello")
        >>> cf.contains("hello")  # True
        >>> cf.remove("hello")
        >>> cf.contains("hello")  # False
    """

    def __init__(self, capacity: int, bucket_size: int = 4, fingerprint_bits: int = 8):
        if capacity <= 0:
            raise ValueError(f"capacity 必须为正: {capacity}")
        if bucket_size <= 0:
            raise ValueError(f"bucket_size 必须为正: {bucket_size}")
        if not (4 <= fingerprint_bits <= 32):
            raise ValueError(f"fingerprint_bits 必须在 [4, 32]: {fingerprint_bits}")
        self._bucket_size = bucket_size
        self._fingerprint_bits = fingerprint_bits
        self._fp_mask = (1 << fingerprint_bits) - 1
        # 桶数: 容量 / 每桶大小, 向上取 2 的幂
        num_buckets = max(2, (capacity + bucket_size - 1) // bucket_size)
        self._num_buckets = 1 << (num_buckets - 1).bit_length()
        self._buckets: list[list[int]] = [[] for _ in range(self._num_buckets)]
        self._size = 0
        self._max_kicks = 500

    def _fingerprint(self, item: object) -> int:
        h = hashlib.md5(str(item).encode()).digest()
        fp = int.from_bytes(h[:4], "little") & self._fp_mask
        # 指纹不能为 0 (0 表示空)
        return fp if fp != 0 else 1

    def _hash(self, item: object) -> int:
        return int.from_bytes(hashlib.md5(str(item).encode()).digest()[:4], "little")

    def _index(self, item: object) -> int:
        return self._hash(item) % self._num_buckets

    def _alt_index(self, index: int, fp: int) -> int:
        """备选桶索引: i2 = i1 ^ hash(fp)。"""
        h = int.from_bytes(hashlib.md5(fp.to_bytes(4, "little")).digest()[:4], "little")
        return (index ^ h) % self._num_buckets

    def insert(self, item: object) -> bool:
        """插入元素, 返回是否成功。"""
        fp = self._fingerprint(item)
        i1 = self._index(item)
        i2 = self._alt_index(i1, fp)
        # 尝试两个候选桶
        if len(self._buckets[i1]) < self._bucket_size:
            self._buckets[i1].append(fp)
            self._size += 1
            return True
        if len(self._buckets[i2]) < self._bucket_size:
            self._buckets[i2].append(fp)
            self._size += 1
            return True
        # 踢出
        cur_i = i1 if random.random() < 0.5 else i2
        cur_fp = fp
        for _ in range(self._max_kicks):
            bucket = self._buckets[cur_i]
            kick_idx = random.randrange(len(bucket))
            bucket[kick_idx], cur_fp = cur_fp, bucket[kick_idx]
            cur_i = self._alt_index(cur_i, cur_fp)
            if len(self._buckets[cur_i]) < self._bucket_size:
                self._buckets[cur_i].append(cur_fp)
                self._size += 1
                return True
        return False  # 过滤器满

    def contains(self, item: object) -> bool:
        """判断元素是否存在。"""
        fp = self._fingerprint(item)
        i1 = self._index(item)
        i2 = self._alt_index(i1, fp)
        return fp in self._buckets[i1] or fp in self._buckets[i2]

    def remove(self, item: object) -> bool:
        """删除元素, 返回是否成功。"""
        fp = self._fingerprint(item)
        i1 = self._index(item)
        i2 = self._alt_index(i1, fp)
        if fp in self._buckets[i1]:
            self._buckets[i1].remove(fp)
            self._size -= 1
            return True
        if fp in self._buckets[i2]:
            self._buckets[i2].remove(fp)
            self._size -= 1
            return True
        return False

    def __len__(self) -> int:
        return self._size

    def __contains__(self, item: object) -> bool:
        return self.contains(item)


# ===========================================================================
# HeavyKeeper — Top-K 重元素检测
# ===========================================================================

class HeavyKeeper(Generic[T]):
    """HeavyKeeper: 比 Count-Min Sketch 更精确的重元素检测。

    原理:
      - 类似 Count-Min 的 d×w 表格, 但用指数衰减策略
      - 小元素自动衰减淘汰, 大元素保留
      - 查询时返回衰减后的计数

    优势:
      - 对小元素自动衰减, 不需要额外内存
      - 比 Count-Min 更精确 (小元素计数被衰减)

    复杂度:
      - add: O(d)
      - query: O(d)
      - 空间: O(d * w)

    Example:
        >>> hk = HeavyKeeper[str](k=10, width=256, depth=4)
        >>> for _ in range(100):
        ...     hk.add("hot_item")
        >>> for _ in range(10):
        ...     hk.add("cold_item")
        >>> hk.top_k(3)  # ["hot_item", ...]
    """

    def __init__(self, k: int = 100, width: int = 256, depth: int = 4, decay: float = 0.9):
        self._k = k
        self._width = width
        self._depth = depth
        self._decay = decay
        self._table: list[list[tuple[T, float]]] = [
            [(None, 0.0) for _ in range(width)]  # type: ignore[assignment]
            for _ in range(depth)
        ]
        self._hash_seeds = [random.randint(0, 2**31 - 1) for _ in range(depth)]
        self._total = 0

    def _hash(self, item: T, seed: int) -> int:
        raw = str(hash(f"{seed}:{hash(item)}")).encode()
        return int.from_bytes(hashlib.md5(raw).digest()[:4], "little") % self._width

    def add(self, item: T, count: float = 1.0) -> None:
        self._total += count
        min_count = float("inf")
        min_idx = -1
        min_row = -1
        for i in range(self._depth):
            col = self._hash(item, self._hash_seeds[i])
            stored_item, stored_count = self._table[i][col]
            if stored_item is None or stored_item == item:
                self._table[i][col] = (item, stored_count + count)
                return
            # 衰减
            self._table[i][col] = (stored_item, stored_count * self._decay)
            if stored_count * self._decay < min_count:
                min_count = stored_count * self._decay
                min_idx = col
                min_row = i
        # 替换最小者
        if min_idx >= 0 and count > min_count:
            self._table[min_row][min_idx] = (item, count)

    def query(self, item: T) -> float:
        return min(self._table[i][self._hash(item, self._hash_seeds[i])][1]
                   if self._table[i][self._hash(item, self._hash_seeds[i])][0] == item
                   else 0.0
                   for i in range(self._depth))

    def top_k(self, k: int | None = None) -> list[T]:
        """返回计数最高的 k 个元素。"""
        if k is None:
            k = self._k
        counts: dict[T, float] = {}
        for row in self._table:
            for item, count in row:
                if item is not None:
                    counts[item] = max(counts.get(item, 0), count)
        return sorted(counts, key=lambda x: counts[x], reverse=True)[:k]


# ===========================================================================
# SkipListIndex — 跳表索引
# ===========================================================================

class SkipListIndex(Generic[T]):
    """跳表索引: 概率平衡的有序索引, O(log n) 查找/插入/删除。

    原理:
      - 多层链表, 每层是下层的"快速通道"
      - 插入时随机决定层数 (概率 1/2 升级)
      - 期望高度 O(log n), 空间 O(n)

    对比红黑树: 实现更简单, 支持范围查询, 并发友好。

    复杂度:
      - 查找/插入/删除: O(log n) 期望
      - 空间: O(n) 期望

    Example:
        >>> sl = SkipListIndex[int]()
        >>> sl.insert(5); sl.insert(3); sl.insert(7)
        >>> 5 in sl  # True
        >>> sl.range(3, 7)  # [3, 5, 7]
    """

    class _Node:
        __slots__ = ("value", "forward")
        def __init__(self, value: T, level: int):
            self.value = value
            self.forward: list[SkipListIndex._Node | None] = [None] * (level + 1)

    def __init__(self):
        self._max_level = 16
        self._head = self._Node(None, self._max_level)  # type: ignore[arg-type]
        self._level = 0
        self._size = 0

    def _random_level(self) -> int:
        level = 0
        while random.random() < 0.5 and level < self._max_level:
            level += 1
        return level

    def insert(self, item: T) -> bool:
        """插入元素, 返回是否新增 (已存在则不插入)。"""
        update: list[SkipListIndex._Node | None] = [None] * (self._max_level + 1)
        current = self._head
        # 查找插入位置
        for i in range(self._level, -1, -1):
            while current.forward[i] is not None and current.forward[i].value < item:  # type: ignore[operator]
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if current is not None and current.value == item:
            return False
        # 随机层数
        new_level = self._random_level()
        if new_level > self._level:
            for i in range(self._level + 1, new_level + 1):
                update[i] = self._head
            self._level = new_level
        # 插入
        node = self._Node(item, new_level)
        for i in range(new_level + 1):
            node.forward[i] = update[i].forward[i]  # type: ignore[union-attr]
            update[i].forward[i] = node  # type: ignore[union-attr]
        self._size += 1
        return True

    def remove(self, item: T) -> bool:
        """删除元素, 返回是否成功。"""
        update: list[SkipListIndex._Node | None] = [None] * (self._max_level + 1)
        current = self._head
        for i in range(self._level, -1, -1):
            while current.forward[i] is not None and current.forward[i].value < item:  # type: ignore[operator]
                current = current.forward[i]
            update[i] = current
        current = current.forward[0]
        if current is None or current.value != item:
            return False
        for i in range(self._level + 1):
            if update[i].forward[i] != current:  # type: ignore[union-attr]
                break
            update[i].forward[i] = current.forward[i]  # type: ignore[union-attr]
        while self._level > 0 and self._head.forward[self._level] is None:
            self._level -= 1
        self._size -= 1
        return True

    def contains(self, item: T) -> bool:
        current = self._head
        for i in range(self._level, -1, -1):
            while current.forward[i] is not None and current.forward[i].value < item:  # type: ignore[operator]
                current = current.forward[i]
        current = current.forward[0]
        return current is not None and current.value == item

    def range(self, start: T, end: T) -> list[T]:
        """返回 [start, end] 范围内的所有元素。"""
        result = []
        current = self._head
        for i in range(self._level, -1, -1):
            while current.forward[i] is not None and current.forward[i].value < start:  # type: ignore[operator]
                current = current.forward[i]
        current = current.forward[0]
        while current is not None and current.value <= end:  # type: ignore[operator]
            result.append(current.value)
            current = current.forward[0]
        return result

    def __contains__(self, item: T) -> bool:
        return self.contains(item)

    def __len__(self) -> int:
        return self._size

    def __iter__(self):
        current = self._head.forward[0]
        while current is not None:
            yield current.value
            current = current.forward[0]