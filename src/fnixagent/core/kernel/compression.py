"""
压缩算法 (Compression Algorithms)
===================================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  HuffmanCodec     - Huffman 编码 (字符频率 → 前缀码)
  LZWCodec         - LZW 词典压缩 (流式, 通用性好)
  LZ77Codec        - LZ77 滑窗压缩 (匹配指针 + 字面量)
  RLE2             - 增强 RLE (多字节连续编码)
  BitWriter        - 位级写入器 (LSB 优先)
  BitReader        - 位级读取器 (LSB 优先)
  CompressionStats - 压缩统计 (比率/熵/理论下界)
"""
from __future__ import annotations

import heapq
from collections import Counter
from typing import Generic, TypeVar

T = TypeVar("T")


# ===========================================================================
# BitWriter / BitReader — 位级 I/O
# ===========================================================================

class BitWriter:
    """位级写入器: 逐 bit 写入, LSB 优先。

    Example:
        >>> bw = BitWriter()
        >>> bw.write_bits(5, 3)  # 写入 101 (3 bits)
        >>> bw.flush()  # b'\x05'
    """

    def __init__(self):
        self._bytes = bytearray()
        self._current = 0
        self._bit_pos = 0  # 当前字节已写入的 bit 数

    def write_bit(self, bit: int) -> None:
        if bit:
            self._current |= (1 << self._bit_pos)
        self._bit_pos += 1
        if self._bit_pos == 8:
            self._bytes.append(self._current)
            self._current = 0
            self._bit_pos = 0

    def write_bits(self, value: int, num_bits: int) -> None:
        """写入 num_bits 位 (LSB 优先)。"""
        for i in range(num_bits):
            self.write_bit((value >> i) & 1)

    def flush(self) -> bytes:
        """刷新剩余位, 返回完整字节串。"""
        if self._bit_pos > 0:
            self._bytes.append(self._current)
            self._current = 0
            self._bit_pos = 0
        return bytes(self._bytes)

    @property
    def bit_count(self) -> int:
        return len(self._bytes) * 8 + self._bit_pos


class BitReader:
    """位级读取器: 逐 bit 读取, LSB 优先。

    Example:
        >>> br = BitReader(b'\x05')
        >>> br.read_bits(3)  # 5 (读取 3 bits)
    """

    def __init__(self, data: bytes):
        self._data = data
        self._byte_pos = 0
        self._bit_pos = 0

    def read_bit(self) -> int | None:
        if self._byte_pos >= len(self._data):
            return None
        bit = (self._data[self._byte_pos] >> self._bit_pos) & 1
        self._bit_pos += 1
        if self._bit_pos == 8:
            self._bit_pos = 0
            self._byte_pos += 1
        return bit

    def read_bits(self, num_bits: int) -> int | None:
        result = 0
        for i in range(num_bits):
            bit = self.read_bit()
            if bit is None:
                return None
            result |= (bit << i)
        return result

    @property
    def remaining_bits(self) -> int:
        return (len(self._data) - self._byte_pos) * 8 - self._bit_pos


# ===========================================================================
# HuffmanCodec — Huffman 编码
# ===========================================================================

class HuffmanCodec:
    """Huffman 编码: 最优前缀码, 按字符频率构建。

    原理:
      1. 统计字符频率
      2. 构建优先队列, 每次取两个最小频率合并
      3. 回溯: 左子树标 0, 右子树标 1

    性质:
      - 编码长度: L = Σ f_i * l_i ≤ Σ f_i * (-log2 f_i / F) + 1
      - 压缩率: 取决于数据熵

    复杂度: O(n log n) 构建, O(n) 编码/解码

    Example:
        >>> encoded, tree = HuffmanCodec.encode(b"hello world")
        >>> HuffmanCodec.decode(encoded, tree)
        b'hello world'
    """

    class _Node:
        __slots__ = ("char", "freq", "left", "right")
        def __init__(self, char=None, freq=0, left=None, right=None):
            self.char = char
            self.freq = freq
            self.left = left
            self.right = right

        def __lt__(self, other):
            return self.freq < other.freq

    @staticmethod
    def _build_tree(data: bytes) -> _Node | None:
        if not data:
            return None
        freq = Counter(data)
        heap = [
            HuffmanCodec._Node(char=ch, freq=fr)
            for ch, fr in freq.items()
        ]
        heapq.heapify(heap)
        if len(heap) == 1:
            # 单字符特殊处理: 加一个虚拟节点
            node = heapq.heappop(heap)
            return HuffmanCodec._Node(freq=node.freq, left=node)
        while len(heap) > 1:
            left = heapq.heappop(heap)
            right = heapq.heappop(heap)
            merged = HuffmanCodec._Node(
                freq=left.freq + right.freq, left=left, right=right
            )
            heapq.heappush(heap, merged)
        return heap[0]

    @staticmethod
    def _build_codes(root: _Node | None) -> dict[int, str]:
        if root is None:
            return {}
        codes: dict[int, str] = {}
        if root.char is not None:
            # 叶子节点 (单字符树)
            codes[root.char] = "0"
            return codes
        HuffmanCodec._traverse(root, "", codes)
        return codes

    @staticmethod
    def _traverse(node: _Node, prefix: str, codes: dict[int, str]) -> None:
        if node.char is not None:
            codes[node.char] = prefix if prefix else "0"
            return
        if node.left:
            HuffmanCodec._traverse(node.left, prefix + "0", codes)
        if node.right:
            HuffmanCodec._traverse(node.right, prefix + "1", codes)

    @staticmethod
    def encode(data: bytes) -> tuple[bytes, _Node]:
        """编码: 返回 (压缩数据, Huffman 树)。"""
        if not data:
            return b"", None
        root = HuffmanCodec._build_tree(data)
        codes = HuffmanCodec._build_codes(root)
        # 用 BitWriter 写入
        writer = BitWriter()
        for byte in data:
            code = codes[byte]
            for bit in code:
                writer.write_bit(int(bit))
        compressed = writer.flush()
        return compressed, root

    @staticmethod
    def decode(compressed: bytes, root: _Node) -> bytes:
        """解码: 从 Huffman 树和压缩数据恢复原始数据。"""
        if root is None or not compressed:
            return b""
        # 处理单字符树
        if root.char is not None:
            # 需要知道原始长度, 暂用压缩数据位数
            reader = BitReader(compressed)
            result = bytearray()
            while reader.remaining_bits > 0:
                result.append(root.char)
            return bytes(result)
        reader = BitReader(compressed)
        result = bytearray()
        node = root
        while reader.remaining_bits > 0:
            bit = reader.read_bit()
            if bit is None:
                break
            node = node.left if bit == 0 else node.right
            if node is None:
                break
            if node.char is not None:
                result.append(node.char)
                node = root
        return bytes(result)


# ===========================================================================
# LZWCodec — LZW 词典压缩
# ===========================================================================

class LZWCodec:
    """LZW 压缩: 词典式压缩, 不需要传输码表。

    原理:
      1. 初始词典: 0-255 对应单字节
      2. 扫描输入, 找最长匹配 W
      3. 输出 W 的码字, 将 W+C 加入词典
      4. 下一次从 C 开始

    特点:
      - 解码器可从码流自动重建词典, 无需存储码表
      - 通用性好, GIF/TIFF 使用

    复杂度: O(n) 编码/解码

    Example:
        >>> compressed = LZWCodec.compress(b"ABABABA")
        >>> LZWCodec.decompress(compressed)
        b'ABABABA'
    """

    @staticmethod
    def compress(data: bytes, max_dict: int = 65536) -> list[int]:
        """LZW 压缩, 返回码字列表。"""
        if not data:
            return []
        # 初始词典: 单字节
        dictionary: dict[bytes, int] = {
            bytes([i]): i for i in range(256)
        }
        next_code = 256
        result: list[int] = []
        w = bytes([data[0]])
        for i in range(1, len(data)):
            c = bytes([data[i]])
            wc = w + c
            if wc in dictionary:
                w = wc
            else:
                result.append(dictionary[w])
                if next_code < max_dict:
                    dictionary[wc] = next_code
                    next_code += 1
                w = c
        result.append(dictionary[w])
        return result

    @staticmethod
    def decompress(codes: list[int]) -> bytes:
        """LZW 解压。"""
        if not codes:
            return b""
        # 初始词典: 码字 → 字节串
        dictionary: dict[int, bytes] = {
            i: bytes([i]) for i in range(256)
        }
        next_code = 256
        result = bytearray()
        w = dictionary[codes[0]]
        result.extend(w)
        for i in range(1, len(codes)):
            code = codes[i]
            if code in dictionary:
                entry = dictionary[code]
            elif code == next_code:
                entry = w + w[:1]
            else:
                raise ValueError(f"无效 LZW 码字: {code}")
            result.extend(entry)
            if next_code < 65536:
                dictionary[next_code] = w + entry[:1]
                next_code += 1
            w = entry
        return bytes(result)

    @staticmethod
    def compress_to_bytes(data: bytes) -> bytes:
        """压缩为字节串 (码字用变长编码)。"""
        codes = LZWCodec.compress(data)
        if not codes:
            return b""
        writer = BitWriter()
        # 写入码字数量
        writer.write_bits(len(codes), 32)
        # 码字用 16 位定长 (简化实现)
        for code in codes:
            writer.write_bits(code, 16)
        return writer.flush()

    @staticmethod
    def decompress_from_bytes(data: bytes) -> bytes:
        reader = BitReader(data)
        count = reader.read_bits(32)
        if count is None or count == 0:
            return b""
        codes = []
        for _ in range(count):
            code = reader.read_bits(16)
            if code is None:
                break
            codes.append(code)
        return LZWCodec.decompress(codes)


# ===========================================================================
# LZ77Codec — LZ77 滑窗压缩
# ===========================================================================

class LZ77Codec:
    """LZ77 滑窗压缩: 匹配指针 (offset, length) + 字面量。

    原理:
      - 滑动窗口: search buffer (已编码) + lookahead buffer (待编码)
      - 在 search buffer 中找最长匹配
      - 输出 (offset, length, next_char) 三元组

    复杂度: 编码 O(n * w), w = 窗口大小; 解码 O(n)

    Example:
        >>> compressed = LZ77Codec.compress(b"abracadabra")
        >>> LZ77Codec.decompress(compressed)
        b'abracadabra'
    """

    def __init__(self, window_size: int = 4096, lookahead_size: int = 16):
        self._window = window_size
        self._lookahead = lookahead_size

    def compress(self, data: bytes) -> list[tuple[int, int, int]]:
        """压缩, 返回 (offset, length, next_char) 三元组列表。"""
        result: list[tuple[int, int, int]] = []
        pos = 0
        n = len(data)
        while pos < n:
            best_offset = 0
            best_length = 0
            # 搜索窗口
            search_start = max(0, pos - self._window)
            max_match = min(self._lookahead, n - pos)
            for start in range(search_start, pos):
                match_len = 0
                while (
                    match_len < max_match
                    and pos + match_len < n
                    and data[start + match_len] == data[pos + match_len]
                ):
                    match_len += 1
                if match_len > best_length:
                    best_length = match_len
                    best_offset = pos - start
            next_char = data[pos + best_length] if pos + best_length < n else 0
            result.append((best_offset, best_length, next_char))
            pos += best_length + 1
        return result

    def decompress(
        self, tokens: list[tuple[int, int, int]]
    ) -> bytes:
        """解压。"""
        result = bytearray()
        for offset, length, char in tokens:
            if length > 0:
                start = len(result) - offset
                for i in range(length):
                    result.append(result[start + i])
            if char != 0 or length == 0:
                result.append(char)
        return bytes(result)

    def compress_to_bytes(self, data: bytes) -> bytes:
        tokens = self.compress(data)
        writer = BitWriter()
        writer.write_bits(len(tokens), 32)
        for offset, length, char in tokens:
            writer.write_bits(offset, 12)   # 窗口 4096 → 12 bits
            writer.write_bits(length, 4)    # lookahead 16 → 4 bits
            writer.write_bits(char, 8)
        return writer.flush()

    def decompress_from_bytes(self, data: bytes) -> bytes:
        reader = BitReader(data)
        count = reader.read_bits(32)
        if count is None or count == 0:
            return b""
        tokens = []
        for _ in range(count):
            offset = reader.read_bits(12)
            length = reader.read_bits(4)
            char = reader.read_bits(8)
            if offset is None or length is None or char is None:
                break
            tokens.append((offset, length, char))
        return self.decompress(tokens)


# ===========================================================================
# RLE2 — 增强游程编码
# ===========================================================================

class RLE2:
    """增强 RLE: 支持多字节连续编码, 处理非重复数据更优。

    编码格式:
      - 重复: [count(1-127), byte]  count=1..127 → 重复 count+1 次
      - 不重复: [count(128-255), data...]  count=128..255 → 后跟 (count-128) 个字面量

    Example:
        >>> compressed = RLE2.compress(b"aaaaabbbcddd")
        >>> RLE2.decompress(compressed)
        b'aaaaabbbcddd'
    """

    @staticmethod
    def compress(data: bytes) -> bytes:
        if not data:
            return b""
        result = bytearray()
        i = 0
        n = len(data)
        while i < n:
            # 计算重复长度
            run_len = 1
            while (
                i + run_len < n
                and run_len < 127
                and data[i] == data[i + run_len]
            ):
                run_len += 1
            if run_len >= 2:
                result.append(run_len - 1)
                result.append(data[i])
                i += run_len
            else:
                # 收集不重复字节
                literals = bytearray([data[i]])
                j = i + 1
                while (
                    j < n
                    and len(literals) < 127
                    and not (j + 1 < n and data[j] == data[j + 1])
                ):
                    literals.append(data[j])
                    j += 1
                result.append(128 + len(literals) - 1)
                result.extend(literals)
                i = j
        return bytes(result)

    @staticmethod
    def decompress(data: bytes) -> bytes:
        if not data:
            return b""
        result = bytearray()
        i = 0
        while i < len(data):
            count = data[i]
            i += 1
            if count < 128:
                # 重复: count+1 次
                result.extend([data[i]] * (count + 1))
                i += 1
            else:
                # 不重复: count-128+1 个字面量
                lit_count = count - 128 + 1
                result.extend(data[i:i + lit_count])
                i += lit_count
        return bytes(result)


# ===========================================================================
# CompressionStats — 压缩统计
# ===========================================================================

class CompressionStats:
    """压缩统计分析工具。

    Example:
        >>> CompressionStats.entropy(b"aaaaabbbbcccdd")
        1.846...
        >>> CompressionStats.ratio(100, 40)
        2.5
    """

    @staticmethod
    def entropy(data: bytes) -> float:
        """Shannon 熵 (bits/byte), 理论压缩下界。"""
        if not data:
            return 0.0
        freq = Counter(data)
        n = len(data)
        import math
        return -sum(
            (c / n) * math.log2(c / n) for c in freq.values()
        )

    @staticmethod
    def ratio(original_size: int, compressed_size: int) -> float:
        """压缩比 = 原始大小 / 压缩大小。"""
        if compressed_size == 0:
            return float("inf")
        return original_size / compressed_size

    @staticmethod
    def saving_percent(original_size: int, compressed_size: int) -> float:
        """空间节省百分比。"""
        if original_size == 0:
            return 0.0
        return (1 - compressed_size / original_size) * 100

    @staticmethod
    def theoretical_min_size(data: bytes) -> int:
        """理论最小压缩大小 (基于 Shannon 熵)。"""
        ent = CompressionStats.entropy(data)
        return int(len(data) * ent / 8) if ent > 0 else 0
