"""Rust PyO3 扩展探测占位包（S1.2.8 — 简化版）。

PyO3 接入留待 Spec 5 神经符号 PDG 一起做。当前保留最小探测 API，
让 deduplicator 等模块的 try_rust_xxx import 路径不破坏。

公共 API：
  - RUST_AVAILABLE: Rust 扩展是否已加载
  - has_rust_ext(): 同上的函数式查询
  - get_rust_version(): 扩展版本号（不可用返回 None）
  - try_rust_fnv64a / try_rust_simhash / try_rust_hamming_distance /
    try_rust_token_bucket_check: 优先 Rust、回退 Python 的探测函数
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# 环境变量控制
_FORCE_RUST = os.environ.get("fnixagent_FORCE_RUST", "").lower()
_FORCE_RUST_OFF = _FORCE_RUST in ("0", "false", "no", "off")

_rust_module: Any | None = None
_rust_load_error: str | None = None

if not _FORCE_RUST_OFF:
    try:
        import fnixagent_rust  # type: ignore[import-not-found]

        _rust_module = fnixagent_rust
        logger.info(
            "Rust 扩展加载成功: %s",
            getattr(fnixagent_rust, "__version__", "unknown"),
        )
    except ImportError as e:
        _rust_load_error = str(e)
        logger.debug("Rust 扩展不可用(回退到 Python): %s", e)
    except Exception as e:
        _rust_load_error = str(e)
        logger.warning("Rust 扩展加载异常: %s", e)

# 公开属性
RUST_AVAILABLE = _rust_module is not None


def has_rust_ext() -> bool:
    """Rust 扩展是否可用。"""
    return _rust_module is not None


def get_rust_version() -> str | None:
    """获取 Rust 扩展版本号。"""
    if _rust_module is None:
        return None
    return getattr(_rust_module, "__version__", None)


def try_rust_fnv64a(data: str, python_fallback: Callable[[str], int] | None = None) -> int:
    """FNV-64a 哈希，优先 Rust，回退 Python。"""
    if _rust_module is not None and hasattr(_rust_module, "fnv64a"):
        return _rust_module.fnv64a(data)
    if python_fallback is not None:
        return python_fallback(data)
    raise RuntimeError("Rust 扩展不可用且未提供 Python fallback")


def try_rust_simhash(text: str, python_fallback: Callable[[str], int] | None = None) -> int:
    """Simhash，优先 Rust，回退 Python。"""
    if _rust_module is not None and hasattr(_rust_module, "simhash"):
        return _rust_module.simhash(text)
    if python_fallback is not None:
        return python_fallback(text)
    raise RuntimeError("Rust 扩展不可用且未提供 Python fallback")


def try_rust_hamming_distance(
    a: int,
    b: int,
    python_fallback: Callable[[int, int], int] | None = None,
) -> int:
    """汉明距离，优先 Rust，回退 Python。"""
    if _rust_module is not None and hasattr(_rust_module, "hamming_distance"):
        return _rust_module.hamming_distance(a, b)
    if python_fallback is not None:
        return python_fallback(a, b)
    raise RuntimeError("Rust 扩展不可用且未提供 Python fallback")


def try_rust_token_bucket_check(
    tokens: float,
    capacity: float,
    rate: float,
    last_refill: float,
    now: float,
    python_fallback: Callable[[float, float, float, float, float], tuple[bool, float, float]]
    | None = None,
) -> tuple[bool, float, float]:
    """令牌桶检查，优先 Rust，回退 Python。"""
    if _rust_module is not None and hasattr(_rust_module, "token_bucket_check"):
        return _rust_module.token_bucket_check(tokens, capacity, rate, last_refill, now)
    if python_fallback is not None:
        return python_fallback(tokens, capacity, rate, last_refill, now)
    raise RuntimeError("Rust 扩展不可用且未提供 Python fallback")


__all__ = [
    "RUST_AVAILABLE",
    "get_rust_version",
    "has_rust_ext",
    "try_rust_fnv64a",
    "try_rust_hamming_distance",
    "try_rust_simhash",
    "try_rust_token_bucket_check",
]
