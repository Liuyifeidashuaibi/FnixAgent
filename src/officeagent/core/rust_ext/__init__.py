"""Rust PyO3 扩展探测与回退包(P1-06)。

本包为 OfficeAgent 性能敏感热路径(FNV-64a / Simhash / 令牌桶)提供
Rust 扩展预留接口。模块在 import 时自动探测 ``officeagent_rust`` 扩展,
不可用时回退到现有纯 Python 实现,实现零侵入加速。

公共 API:
  - RUST_AVAILABLE: Rust 扩展是否已加载(模块级常量)
  - has_rust_ext(): 同上的函数式查询
  - get_rust_version(): 获取扩展版本号(不可用返回 None)
  - try_rust_fnv64a / try_rust_simhash / try_rust_token_bucket_check:
    优先 Rust、回退 Python 的探测函数,调用方传入 python_fallback 即可

环境变量:
  - OFFICEAGENT_FORCE_RUST=1: 强制启用(加载失败抛错)
  - OFFICEAGENT_FORCE_RUST=0: 强制禁用(始终回退 Python)
"""
from __future__ import annotations

from officeagent.core.rust_ext.probe import (
    RUST_AVAILABLE,
    get_rust_error,
    get_rust_version,
    has_rust_ext,
    try_rust_fnv64a,
    try_rust_hamming_distance,
    try_rust_simhash,
    try_rust_token_bucket_check,
)

__all__ = [
    "RUST_AVAILABLE",
    "has_rust_ext",
    "get_rust_version",
    "get_rust_error",
    "try_rust_fnv64a",
    "try_rust_simhash",
    "try_rust_hamming_distance",
    "try_rust_token_bucket_check",
]
