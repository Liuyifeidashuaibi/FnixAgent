#!/usr/bin/env python3
"""生成 Fnix Desktop 应用图标 (1024x1024 PNG，仅 stdlib)。"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps" / "workbench" / "app-icon.png"

# Fnix 品牌色 #1a6b5c
BG = (26, 107, 92)
ACCENT = (255, 255, 255)


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_png(path: Path, width: int, height: int) -> None:
    """简单几何 Logo：深绿底 + 白色 F 形块。"""
    rows: list[bytes] = []
    cx, cy = width // 2, height // 2
    bar_w = width // 6
    bar_h = height // 6

    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            # 竖条
            in_v = (cx - bar_w <= x <= cx + bar_w // 3) and (cy - height // 3 <= y <= cy + height // 3)
            # 上横
            in_h1 = (cx - bar_w <= x <= cx + width // 4) and (cy - height // 3 <= y <= cy - height // 3 + bar_h)
            # 中横
            in_h2 = (cx - bar_w <= x <= cx + width // 6) and (cy - bar_h // 2 <= y <= cy - bar_h // 2 + bar_h)
            if in_v or in_h1 or in_h2:
                row.extend(ACCENT)
            else:
                row.extend(BG)
        rows.append(bytes(row))

    raw = b"".join(rows)
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", compressed) + _chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    print(f"[icon] wrote {path} ({width}x{height})")


if __name__ == "__main__":
    write_png(OUT, 1024, 1024)
