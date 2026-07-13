"""
编解码与压缩 (Encoding, Compression & Serialization)
=====================================================
纯 Python + stdlib 实现,零外部依赖。

算法清单:
  VarInt           - 可变长度整数编码 (protobuf 风格)
  DeltaEncoding    - 增量编码 (时序数据压缩)
  RunLengthEncoding - 游程编码 (连续重复值压缩)
  HexEncoding      - 十六进制编解码
  Base64URL        - URL 安全 Base64 编解码
  BinaryWriter     - 紧凑二进制写入器
  BinaryReader     - 紧凑二进制读取器
  ZigZag           - 有符号整数映射到无符号 (配合 VarInt)
"""
from __future__ import annotations

import base64
import struct
from io import BytesIO
from typing import Any, Iterable


# ===========================================================================
# VarInt — 可变长度整数编码 (protobuf 风格)
# ===========================================================================


class VarInt:
    """VarInt 编码: 小整数用 1 字节, 大整数用更多字节。

    协议:
      - 每字节低 7 位为数据, 最高位为继续标志 (1=还有, 0=结束)
      - 小端序 (低位在前)

    Example:
        >>> VarInt.encode(300)  # b'\\xac\\x02'
        >>> VarInt.decode(b'\\xac\\x02')  # (300, 2)
    """

    @staticmethod
    def encode(value: int) -> bytes:
        """编码一个整数为 VarInt 字节。"""
        if value < 0:
            raise ValueError("VarInt 不支持负数, 请使用 ZigZag 编码")
        result = bytearray()
        while value > 0x7F:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value & 0x7F)
        return bytes(result)

    @staticmethod
    def decode(data: bytes | bytearray, offset: int = 0) -> tuple[int, int]:
        """解码 VarInt, 返回 (值, 消耗字节数)。"""
        value = 0
        shift = 0
        for i in range(offset, len(data)):
            byte = data[i]
            value |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                return value, i - offset + 1
            shift += 7
        raise ValueError("VarInt 数据不完整")


class ZigZag:
    """ZigZag 编码: 将有符号整数映射为无符号, 配合 VarInt 使用。

    映射:
      - 0 → 0, -1 → 1, 1 → 2, -2 → 3, 2 → 4, ...

    Example:
        >>> ZigZag.encode(-1)  # 1
        >>> ZigZag.decode(1)   # -1
    """

    @staticmethod
    def encode(value: int) -> int:
        return (value << 1) ^ (value >> 63)  # 64-bit 算术右移

    @staticmethod
    def decode(value: int) -> int:
        return (value >> 1) ^ -(value & 1)


# ===========================================================================
# DeltaEncoding — 增量编码 (时序数据压缩)
# ===========================================================================


class DeltaEncoding:
    """增量编码: 存储相邻值的差值, 适用于单调递增/递减序列。

    原理:
      - 原始序列: [100, 102, 105, 110, 118]
      - 差值序列:  [100, 2, 3, 5, 8]  (第一个值保留原始值)
      - 差值可用 VarInt 进一步压缩

    Example:
        >>> DeltaEncoding.encode([100, 102, 105, 110, 118])
        [(100, True), (2, False), (3, False), (5, False), (8, False)]
    """

    @staticmethod
    def encode(values: Iterable[int]) -> list[tuple[int, bool]]:
        """编码为 (值, 是否原始值) 列表。"""
        encoded = []
        prev = None
        for v in values:
            if prev is None:
                encoded.append((v, True))
            else:
                encoded.append((v - prev, False))
            prev = v
        return encoded

    @staticmethod
    def decode(encoded: Iterable[tuple[int, bool]]) -> list[int]:
        """解码还原为原始序列。"""
        values = []
        cur = 0
        for delta, is_original in encoded:
            if is_original:
                cur = delta
            else:
                cur += delta
            values.append(cur)
        return values

    @staticmethod
    def double_delta_encode(values: Iterable[int]) -> list[tuple[int, bool]]:
        """二阶增量编码: 对差值再做一次增量。"""
        first = DeltaEncoding.encode(values)
        return DeltaEncoding.encode(delta for delta, _ in first)


# ===========================================================================
# RunLengthEncoding — 游程编码
# ===========================================================================


class RunLengthEncoding:
    """游程编码: 连续重复值压缩。

    Example:
        >>> RLE.encode([1, 1, 1, 2, 2, 3])
        [(1, 3), (2, 2), (3, 1)]
        >>> RLE.decode([(1, 3), (2, 2), (3, 1)])
        [1, 1, 1, 2, 2, 3]
    """

    @staticmethod
    def encode(values: Iterable[Any]) -> list[tuple[Any, int]]:
        """编码为 (值, 重复次数) 列表。"""
        result = []
        for v in values:
            if result and result[-1][0] == v:
                result[-1] = (v, result[-1][1] + 1)
            else:
                result.append((v, 1))
        return result

    @staticmethod
    def decode(encoded: Iterable[tuple[Any, int]]) -> list[Any]:
        """解码还原为原始序列。"""
        result = []
        for v, count in encoded:
            result.extend([v] * count)
        return result


# ===========================================================================
# HexEncoding — 十六进制编解码
# ===========================================================================


class HexEncoding:
    """十六进制编解码, 纯算法实现 (不依赖 binascii)。

    Example:
        >>> HexEncoding.encode(b"hello")
        '68656c6c6f'
        >>> HexEncoding.decode("68656c6c6f")
        b'hello'
    """

    _HEX = "0123456789abcdef"

    @staticmethod
    def encode(data: bytes) -> str:
        return "".join(
            HexEncoding._HEX[b >> 4] + HexEncoding._HEX[b & 0x0F]
            for b in data
        )

    @staticmethod
    def decode(hex_str: str) -> bytes:
        if len(hex_str) % 2 != 0:
            raise ValueError(f"十六进制字符串长度必须为偶数: {len(hex_str)}")
        result = bytearray(len(hex_str) // 2)
        for i in range(0, len(hex_str), 2):
            hi = HexEncoding._HEX.index(hex_str[i].lower())
            lo = HexEncoding._HEX.index(hex_str[i + 1].lower())
            result[i // 2] = (hi << 4) | lo
        return bytes(result)


# ===========================================================================
# Base64URL — URL 安全 Base64
# ===========================================================================


class Base64URL:
    """Base64URL 编解码: 替换 +/ 为 -_, 去除 = 填充。

    Example:
        >>> Base64URL.encode(b"hello")
        'aGVsbG8'
    """

    @staticmethod
    def encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def decode(encoded: str) -> bytes:
        # 补齐 = 填充到 4 的倍数
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += "=" * padding
        return base64.urlsafe_b64decode(encoded.encode("ascii"))


# ===========================================================================
# BinaryWriter / BinaryReader — 紧凑二进制序列化
# ===========================================================================


class BinaryWriter:
    """紧凑二进制写入器。

    写入方法:
      - write_byte / write_uint16 / write_uint32 / write_uint64
      - write_varint / write_signed_varint (ZigZag + VarInt)
      - write_bytes / write_string
      - write_float32 / write_float64

    Example:
        >>> buf = BinaryWriter()
        >>> buf.write_uint32(42)
        >>> buf.write_string("hello")
        >>> buf.bytes()  # b'...'
    """

    def __init__(self):
        self._buf = BytesIO()

    def write_byte(self, value: int) -> None:
        self._buf.write(struct.pack("<B", value))

    def write_uint16(self, value: int) -> None:
        self._buf.write(struct.pack("<H", value))

    def write_uint32(self, value: int) -> None:
        self._buf.write(struct.pack("<I", value))

    def write_uint64(self, value: int) -> None:
        self._buf.write(struct.pack("<Q", value))

    def write_varint(self, value: int) -> None:
        self._buf.write(VarInt.encode(value))

    def write_signed_varint(self, value: int) -> None:
        self.write_varint(ZigZag.encode(value))

    def write_float32(self, value: float) -> None:
        self._buf.write(struct.pack("<f", value))

    def write_float64(self, value: float) -> None:
        self._buf.write(struct.pack("<d", value))

    def write_bytes(self, data: bytes) -> None:
        self.write_varint(len(data))
        self._buf.write(data)

    def write_string(self, s: str) -> None:
        self.write_bytes(s.encode("utf-8"))

    def write_int32_slice(self, values: Iterable[int]) -> None:
        """批量写入 int32 (先写长度, 再写数据)。"""
        vals = list(values)
        self.write_varint(len(vals))
        for v in vals:
            self._buf.write(struct.pack("<i", v))

    def write_float32_slice(self, values: Iterable[float]) -> None:
        """批量写入 float32 (先写长度, 再写数据)。"""
        vals = list(values)
        self.write_varint(len(vals))
        for v in vals:
            self._buf.write(struct.pack("<f", v))

    def bytes(self) -> bytes:
        return self._buf.getvalue()

    def __len__(self) -> int:
        return self._buf.tell()


class BinaryReader:
    """紧凑二进制读取器。

    Example:
        >>> reader = BinaryReader(b'...')
        >>> reader.read_uint32()
    """

    def __init__(self, data: bytes):
        self._buf = BytesIO(data)
        self._size = len(data)

    def read_byte(self) -> int:
        return struct.unpack("<B", self._read(1))[0]

    def read_uint16(self) -> int:
        return struct.unpack("<H", self._read(2))[0]

    def read_uint32(self) -> int:
        return struct.unpack("<I", self._read(4))[0]

    def read_uint64(self) -> int:
        return struct.unpack("<Q", self._read(8))[0]

    def read_varint(self) -> int:
        value, consumed = VarInt.decode(self._remainder())
        self._buf.seek(consumed, 1)
        return value

    def read_signed_varint(self) -> int:
        return ZigZag.decode(self.read_varint())

    def read_float32(self) -> float:
        return struct.unpack("<f", self._read(4))[0]

    def read_float64(self) -> float:
        return struct.unpack("<d", self._read(8))[0]

    def read_bytes(self) -> bytes:
        length = self.read_varint()
        return self._read(length)

    def read_string(self) -> str:
        return self.read_bytes().decode("utf-8")

    def read_int32_slice(self) -> list[int]:
        length = self.read_varint()
        return [struct.unpack("<i", self._read(4))[0] for _ in range(length)]

    def read_float32_slice(self) -> list[float]:
        length = self.read_varint()
        return [struct.unpack("<f", self._read(4))[0] for _ in range(length)]

    def _read(self, n: int) -> bytes:
        data = self._buf.read(n)
        if len(data) < n:
            raise EOFError(f"数据不足: 期望 {n} 字节, 实际 {len(data)} 字节")
        return data

    def _remainder(self) -> bytes:
        pos = self._buf.tell()
        self._buf.seek(0, 2)
        end = self._buf.tell()
        self._buf.seek(pos)
        return self._buf.read(end - pos)

    def eof(self) -> bool:
        return self._buf.tell() >= self._size