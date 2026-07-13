"""
哈希与指纹算法 (Hashing & Fingerprinting)
===========================================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  SimHash          - 局部敏感哈希, 用于文本去重/近似匹配
  MinHash          - 集合相似度 (Jaccard) 估算
  RollingHash      - 滚动哈希 (Rabin-Karp), 用于子串匹配
  ConsistentHash   - 一致性哈希, 用于分布式负载均衡
  CuckooHash       - 布谷鸟哈希, 高负载因子 (> 90%)
  XXHash           - 非加密快速哈希 (xxhash 简化版)
  FNVHash          - FNV-1a 哈希, 极简实现
  MurmurHash3      - 非加密哈希, 分布均匀性好
"""
from __future__ import annotations

import hashlib
import math
import random
import struct
from bisect import bisect_right
from collections import defaultdict
from typing import Callable, Generic, Iterable, Sequence, TypeVar

T = TypeVar("T")


# ===========================================================================
# SimHash — 局部敏感哈希 (文本去重/近似匹配)
# ===========================================================================


class SimHash:
    """SimHash: 将高维向量/文本降维到固定长度二进制指纹。

    原理:
      1. 对每个特征计算传统哈希值 (如 MD5 的 64-bit)
      2. 按位加权累加: 位为 1 则 +weight, 位为 0 则 -weight
      3. 最终向量每位正→1, 负→0, 得到 fingerprint

    性质:
      - 汉明距离 ≈ 原始余弦距离 (LSH 性质)
      - 64-bit fingerprint 可存为 int

    复杂度:
      - 计算: O(n * d)  (n = 特征数, d = 64)
      - 匹配: O(1) 异或 + popcount

    Example:
        >>> sh = SimHash()
        >>> fp1 = sh.compute(["hello", "world", "python"])
        >>> fp2 = sh.compute(["hello", "world", "rust"])
        >>> sh.hamming_distance(fp1, fp2)  # 小 (相似)
    """

    def __init__(self, bits: int = 64):
        if bits <= 0 or bits % 8 != 0:
            raise ValueError(f"bits 必须为正且为 8 的倍数: {bits}")
        self._bits = bits

    def compute(self, features: Iterable[str], weights: Iterable[float] | None = None) -> int:
        """计算 SimHash 指纹。

        Args:
            features: 特征列表 (单词/ngram/...)
            weights:  每个特征的权重 (默认均等)

        Returns:
            int 指纹 (bits 位)
        """
        vec = [0] * self._bits
        features = list(features)
        if weights is None:
            weights = [1.0] * len(features)
        for feat, w in zip(features, weights):
            h = self._hash_feature(feat)
            for i in range(self._bits):
                if (h >> i) & 1:
                    vec[i] += w
                else:
                    vec[i] -= w
        fp = 0
        for i in range(self._bits):
            if vec[i] > 0:
                fp |= (1 << i)
        return fp

    def _hash_feature(self, feature: str) -> int:
        """特征的 64-bit 哈希。"""
        digest = hashlib.md5(feature.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "little")

    @staticmethod
    def hamming_distance(a: int, b: int) -> int:
        """汉明距离 (popcount of XOR)。"""
        return (a ^ b).bit_count()

    def is_similar(self, a: int, b: int, max_distance: int = 3) -> bool:
        """判断是否相似 (汉明距离 <= max_distance)。"""
        return self.hamming_distance(a, b) <= max_distance


# ===========================================================================
# MinHash — 集合相似度估算
# ===========================================================================


class MinHash:
    """MinHash: 估算两个集合的 Jaccard 相似度。

    原理:
      1. 用 k 个独立哈希函数对集合元素求哈希值
      2. 每个哈希函数取最小值 (min-hash)
      3. 两个集合的 min-hash 签名一致率 ≈ Jaccard 相似度

    复杂度:
      - 签名: O(k * n)
      - 相似度: O(k)

    Example:
        >>> mh = MinHash(num_perm=128)
        >>> sig1 = mh.signature(set("hello world"))
        >>> sig2 = mh.signature(set("hello python"))
        >>> mh.jaccard(sig1, sig2)  # ≈ 0.33
    """

    def __init__(self, num_perm: int = 128, seed: int = 42):
        if num_perm <= 0:
            raise ValueError(f"num_perm 必须为正: {num_perm}")
        self._num_perm = num_perm
        # 生成 k 组 (a, b) 参数, 用于哈希函数 h(x) = (a*x + b) mod M
        rng = random.Random(seed)
        self._M = (1 << 61) - 1  # 梅森素数
        self._a = [rng.randint(1, self._M - 1) for _ in range(num_perm)]
        self._b = [rng.randint(0, self._M - 1) for _ in range(num_perm)]

    def _hash(self, item: object, i: int) -> int:
        """第 i 个哈希函数。"""
        h = hash(item) & 0xFFFFFFFFFFFFFFFF
        return (self._a[i] * h + self._b[i]) % self._M

    def signature(self, items: set) -> list[int]:
        """计算 min-hash 签名。"""
        sig = [self._M] * self._num_perm
        for item in items:
            for i in range(self._num_perm):
                h = self._hash(item, i)
                if h < sig[i]:
                    sig[i] = h
        return sig

    def jaccard(self, sig1: list[int], sig2: list[int]) -> float:
        """估算 Jaccard 相似度 = 签名一致率。"""
        if len(sig1) != len(sig2):
            raise ValueError(f"签名长度不一致: {len(sig1)} vs {len(sig2)}")
        matches = sum(1 for a, b in zip(sig1, sig2) if a == b)
        return matches / len(sig1)


# ===========================================================================
# RollingHash — 滚动哈希 (Rabin-Karp)
# ===========================================================================


class RollingHash:
    """滚动哈希: 滑动窗口 O(1) 更新哈希值。

    原理:
      - hash(s[i+1 : i+1+L]) = (hash(s[i : i+L]) - base^(L-1)*s[i]) * base + s[i+L]
      - 模运算避免溢出

    应用:
      - 子串匹配 (Rabin-Karp)
      - 重复片段检测 (chunk 去重)
      - 可变长度分块 (CDC)

    Example:
        >>> rh = RollingHash()
        >>> h1 = rh.compute("hello")
        >>> h2 = rh.roll(h1, "hello", "h", "!")

    Args:
        base: 基数 (通常 256 或 257)
        mod:  模数 (大素数, 如 2^61-1)
    """

    def __init__(self, base: int = 256, mod: int | None = None):
        self._base = base
        self._mod = mod or ((1 << 61) - 1)

    def compute(self, s: Sequence[int | str]) -> int:
        """计算字符串/字节的完整哈希。"""
        h = 0
        for ch in s:
            val = ord(ch) if isinstance(ch, str) else ch
            h = (h * self._base + val) % self._mod
        return h

    def roll(self, old_hash: int, old_seq: Sequence[int | str], old_char: int | str, new_char: int | str) -> int:
        """滚动哈希: 移除 old_char, 加入 new_char。

        Args:
            old_hash: 当前窗口哈希值
            old_seq:  当前窗口序列 (用于计算 base^(len-1) 的权重)
            old_char: 滑出窗口的字符
            new_char: 滑入窗口的字符

        Returns:
            新哈希值

        Example:
            >>> rh = RollingHash()
            >>> h = rh.compute("abc")
            >>> h2 = rh.roll(h, "abc", "a", "d")  # "bcd" 的哈希
        """
        old_val = ord(old_char) if isinstance(old_char, str) else old_char
        new_val = ord(new_char) if isinstance(new_char, str) else new_char
        # 计算 base^(len-1) mod mod
        n = len(old_seq) - 1
        power = pow(self._base, n, self._mod)
        h = (old_hash - power * old_val) % self._mod
        h = (h * self._base + new_val) % self._mod
        return h


# ===========================================================================
# ConsistentHash — 一致性哈希
# ===========================================================================


class ConsistentHash:
    """一致性哈希: 分布式负载均衡, 节点增删时仅重映射少量键。

    原理:
      - 将节点映射到环上 (hash ring)
      - 键顺时针找第一个节点
      - 虚拟节点 (vnodes) 均衡分布

    复杂度:
      - 添加/移除节点: O(vnodes * log(total_vnodes))
      - 查找节点: O(log(total_vnodes))

    Example:
        >>> ch = ConsistentHash(vnodes=150)
        >>> ch.add_node("server1")
        >>> ch.add_node("server2")
        >>> ch.get_node("my_key")  # "server1" 或 "server2"
    """

    def __init__(self, vnodes: int = 150, hash_fn: Callable[[str], int] | None = None):
        self._vnodes = vnodes
        self._hash_fn = hash_fn or self._default_hash
        self._ring: list[int] = []          # 排序的哈希值
        self._ring_map: dict[int, str] = {}  # 哈希值 → 节点
        self._nodes: set[str] = set()

    @staticmethod
    def _default_hash(key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: str) -> None:
        if node in self._nodes:
            return
        self._nodes.add(node)
        for i in range(self._vnodes):
            vnode_key = f"{node}:vnode:{i}"
            h = self._hash_fn(vnode_key)
            self._ring_map[h] = node
            self._ring.append(h)
        self._ring.sort()

    def remove_node(self, node: str) -> None:
        if node not in self._nodes:
            return
        self._nodes.discard(node)
        for i in range(self._vnodes):
            h = self._hash_fn(f"{node}:vnode:{i}")
            self._ring_map.pop(h, None)
        self._ring = [h for h in self._ring if h in self._ring_map]

    def get_node(self, key: str) -> str | None:
        """返回 key 对应的节点 (顺时针第一个)。"""
        if not self._ring:
            return None
        h = self._hash_fn(key)
        idx = bisect_right(self._ring, h)
        if idx == len(self._ring):
            idx = 0
        return self._ring_map[self._ring[idx]]

    def get_nodes(self, key: str, count: int) -> list[str]:
        """返回 key 对应的 count 个节点 (用于副本)。"""
        if not self._ring or count <= 0:
            return []
        h = self._hash_fn(key)
        idx = bisect_right(self._ring, h)
        result = []
        seen = set()
        for i in range(len(self._ring)):
            ring_idx = (idx + i) % len(self._ring)
            node = self._ring_map[self._ring[ring_idx]]
            if node not in seen:
                result.append(node)
                seen.add(node)
                if len(result) == count:
                    break
        return result

    def __len__(self) -> int:
        return len(self._nodes)


# ===========================================================================
# CuckooHash — 布谷鸟哈希
# ===========================================================================


class CuckooHash(Generic[T]):
    """布谷鸟哈希: 双哈希表, 负载因子 > 90%, O(1) 期望查找。

    原理:
      - 两个哈希表 T1, T2, 两个哈希函数 h1, h2
      - 插入 x: 放入 T1[h1(x)], 如果冲突则踢出旧元素, 旧元素放入 T2 备用位
      - 循环踢出直到稳定或重新哈希

    复杂度:
      - 查找: O(1) 保证
      - 插入: O(1) 期望, 最坏 O(n) (触发 rehash)
    """

    def __init__(self, capacity: int = 16):
        self._capacity = max(4, capacity)
        self._size = 0
        self._t1: list[tuple[object, object] | None] = [None] * self._capacity
        self._t2: list[tuple[object, object] | None] = [None] * self._capacity

    def _h1(self, key: object) -> int:
        return hash(("h1", key)) % self._capacity

    def _h2(self, key: object) -> int:
        return hash(("h2", key)) % self._capacity

    def insert(self, key: object, value: object) -> None:
        """插入键值对。"""
        if self._size >= self._capacity * 0.9:
            self._rehash()
        cur_key, cur_val = key, value
        max_iters = self._capacity * 4
        for _ in range(max_iters):
            # 尝试 T1
            idx = self._h1(cur_key)
            if self._t1[idx] is None:
                self._t1[idx] = (cur_key, cur_val)
                self._size += 1
                return
            cur_key, cur_val, self._t1[idx] = self._t1[idx][0], self._t1[idx][1], (cur_key, cur_val)
            # 尝试 T2
            idx = self._h2(cur_key)
            if self._t2[idx] is None:
                self._t2[idx] = (cur_key, cur_val)
                self._size += 1
                return
            cur_key, cur_val, self._t2[idx] = self._t2[idx][0], self._t2[idx][1], (cur_key, cur_val)
        self._rehash()
        self.insert(key, value)

    def lookup(self, key: object) -> object | None:
        """查找键对应的值。"""
        idx = self._h1(key)
        if self._t1[idx] and self._t1[idx][0] == key:
            return self._t1[idx][1]
        idx = self._h2(key)
        if self._t2[idx] and self._t2[idx][0] == key:
            return self._t2[idx][1]
        return None

    def _rehash(self) -> None:
        old_t1, old_t2 = self._t1, self._t2
        self._capacity *= 2
        self._t1 = [None] * self._capacity
        self._t2 = [None] * self._capacity
        self._size = 0
        for bucket in (old_t1 + old_t2):
            if bucket:
                self.insert(bucket[0], bucket[1])

    def __len__(self) -> int:
        return self._size

    def __contains__(self, key: object) -> bool:
        return self.lookup(key) is not None


# ===========================================================================
# FNVHash / MurmurHash3 — 非加密快速哈希
# ===========================================================================


class FNVHash:
    """FNV-1a 哈希, 极简实现, 适合小键 (如字符串)。"""

    _FNV_PRIME_64 = 0x100000001B3
    _FNV_OFFSET_64 = 0xCBF29CE484222325

    @staticmethod
    def hash64(data: bytes | str) -> int:
        if isinstance(data, str):
            data = data.encode()
        h = FNVHash._FNV_OFFSET_64
        for byte in data:
            h ^= byte
            h = (h * FNVHash._FNV_PRIME_64) & 0xFFFFFFFFFFFFFFFF
        return h


class MurmurHash3:
    """MurmurHash3 简化版 (32-bit), 分布均匀性好。"""

    @staticmethod
    def hash32(data: bytes | str, seed: int = 0) -> int:
        if isinstance(data, str):
            data = data.encode()
        h = seed
        c1 = 0xCC9E2D51
        c2 = 0x1B873593
        # 4 字节块
        for i in range(0, len(data) - len(data) % 4, 4):
            k = struct.unpack_from("<I", data, i)[0]
            k = (k * c1) & 0xFFFFFFFF
            k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
            k = (k * c2) & 0xFFFFFFFF
            h ^= k
            h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
            h = (h * 5 + 0xE6546B64) & 0xFFFFFFFF
        # 尾部
        tail = data[-(len(data) % 4):] if len(data) % 4 else b""
        k1 = 0
        for idx, byte in enumerate(tail):
            k1 |= byte << (idx * 8)
        k1 = (k1 * c1) & 0xFFFFFFFF
        k1 = ((k1 << 15) | (k1 >> 17)) & 0xFFFFFFFF
        k1 = (k1 * c2) & 0xFFFFFFFF
        h ^= k1
        # 最终混合
        h ^= len(data)
        h ^= (h >> 16)
        h = (h * 0x85EBCA6B) & 0xFFFFFFFF
        h ^= (h >> 13)
        h = (h * 0xC2B2AE35) & 0xFFFFFFFF
        h ^= (h >> 16)
        return h


# ===========================================================================
# XXHash — 非加密快速哈希 (xxhash 简化版)
# ===========================================================================


class XXHash:
    """XXHash32 简化实现, 比 MurmurHash3 更快。

    Example:
        >>> XXHash.hash32(b"hello world")  # 快速哈希值
    """

    _PRIME32_1 = 0x9E3779B1
    _PRIME32_2 = 0x85EBCA77
    _PRIME32_3 = 0xC2B2AE3D
    _PRIME32_4 = 0x27D4EB2F
    _PRIME32_5 = 0x165667B1

    @staticmethod
    def hash32(data: bytes | str, seed: int = 0) -> int:
        if isinstance(data, str):
            data = data.encode()
        n = len(data)
        h = seed + n + XXHash._PRIME32_5
        # 4 字节块
        for i in range(0, n - n % 4, 4):
            k = struct.unpack_from("<I", data, i)[0]
            k = (k * XXHash._PRIME32_2) & 0xFFFFFFFF
            k = ((k << 13) | (k >> 19)) & 0xFFFFFFFF
            k = (k * XXHash._PRIME32_1) & 0xFFFFFFFF
            h ^= k
            h = ((h << 17) | (h >> 15)) & 0xFFFFFFFF
            h = (h * XXHash._PRIME32_4 + XXHash._PRIME32_3) & 0xFFFFFFFF
        # 尾部
        for i in range(n - n % 4, n):
            h ^= data[i] * XXHash._PRIME32_5
            h = ((h << 11) | (h >> 21)) & 0xFFFFFFFF
            h = (h * XXHash._PRIME32_1) & 0xFFFFFFFF
        # 最终混合
        h ^= (h >> 15)
        h = (h * XXHash._PRIME32_2) & 0xFFFFFFFF
        h ^= (h >> 13)
        h = (h * XXHash._PRIME32_3) & 0xFFFFFFFF
        h ^= (h >> 16)
        return h