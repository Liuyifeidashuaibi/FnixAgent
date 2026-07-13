"""Rust PyO3 扩展探测与回退(P1-06)。

设计原则(借鉴 zhua):
  1. 自动探测: import 时尝试加载 Rust 扩展模块
  2. 优雅降级: 扩展不可用时回退到 Python 实现
  3. 零侵入: 调用方通过 try_rust_xxx() 函数使用,不直接 import Rust 模块
  4. 可开关: 支持 OFFICEAGENT_FORCE_RUST 环境变量强制启用/禁用

Rust 扩展模块名: officeagent_rust
预期接口(由 Rust PyO3 实现):
  - fnv64a(data: str) -> int
  - simhash(text: str) -> int
  - hamming_distance(a: int, b: int) -> int
  - token_bucket_check(tokens: float, capacity: float, rate: float, last_refill: float, now: float) -> tuple[bool, float, float]
    返回: (allowed, new_tokens, new_last_refill)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 环境变量控制
_FORCE_RUST = os.environ.get("OFFICEAGENT_FORCE_RUST", "").lower()
_FORCE_RUST_ON = _FORCE_RUST in ("1", "true", "yes", "on")
_FORCE_RUST_OFF = _FORCE_RUST in ("0", "false", "no", "off")

# 尝试加载 Rust 扩展
_rust_module: Optional[Any] = None
_rust_load_attempted = False
_rust_load_error: Optional[str] = None


def _try_load_rust() -> Optional[Any]:
    """尝试加载 Rust 扩展模块(仅尝试一次)。"""
    global _rust_module, _rust_load_attempted, _rust_load_error

    if _rust_load_attempted:
        return _rust_module

    _rust_load_attempted = True

    if _FORCE_RUST_OFF:
        _rust_load_error = "disabled by OFFICEAGENT_FORCE_RUST=0"
        logger.info("Rust 扩展已通过环境变量禁用")
        return None

    try:
        import officeagent_rust

        _rust_module = officeagent_rust
        logger.info(
            "Rust 扩展加载成功: %s",
            getattr(officeagent_rust, "__version__", "unknown"),
        )
    except ImportError as e:
        _rust_load_error = str(e)
        if _FORCE_RUST_ON:
            logger.error("OFFICEAGENT_FORCE_RUST=1 但扩展加载失败: %s", e)
        else:
            logger.debug("Rust 扩展不可用(回退到 Python): %s", e)
    except Exception as e:
        _rust_load_error = str(e)
        logger.warning("Rust 扩展加载异常: %s", e)

    return _rust_module


# 惰性加载
_rust_module = _try_load_rust()

# 公开属性
RUST_AVAILABLE = _rust_module is not None


def has_rust_ext() -> bool:
    """Rust 扩展是否可用。"""
    return _rust_module is not None


def get_rust_version() -> Optional[str]:
    """获取 Rust 扩展版本号。"""
    if _rust_module is None:
        return None
    return getattr(_rust_module, "__version__", None)


def get_rust_error() -> Optional[str]:
    """获取加载失败原因(调试用)。"""
    return _rust_load_error


# ---------------------------------------------------------------------------
# 探测函数: 优先 Rust,回退 Python
# ---------------------------------------------------------------------------


def try_rust_fnv64a(data: str, python_fallback: Optional[Callable[[str], int]] = None) -> int:
    """计算 FNV-64a 哈希,优先使用 Rust 实现。

    Args:
        data: 输入字符串。
        python_fallback: Python 实现函数(无 Rust 时调用)。

    Returns:
        64 位哈希值。

    Raises:
        RuntimeError: Rust 扩展不可用且未提供 python_fallback。
    """
    if _rust_module is not None and hasattr(_rust_module, "fnv64a"):
        return _rust_module.fnv64a(data)
    if python_fallback is not None:
        return python_fallback(data)
    # 无 fallback 时抛出,调用方应始终提供 fallback
    raise RuntimeError("Rust 扩展不可用且未提供 Python fallback")


def try_rust_simhash(text: str, python_fallback: Optional[Callable[[str], int]] = None) -> int:
    """计算 Simhash,优先使用 Rust 实现。

    Args:
        text: 输入文本。
        python_fallback: Python 实现函数(无 Rust 时调用)。

    Returns:
        64 位 Simhash 值。

    Raises:
        RuntimeError: Rust 扩展不可用且未提供 python_fallback。
    """
    if _rust_module is not None and hasattr(_rust_module, "simhash"):
        return _rust_module.simhash(text)
    if python_fallback is not None:
        return python_fallback(text)
    raise RuntimeError("Rust 扩展不可用且未提供 Python fallback")


def try_rust_hamming_distance(
    a: int,
    b: int,
    python_fallback: Optional[Callable[[int, int], int]] = None,
) -> int:
    """计算汉明距离,优先使用 Rust 实现。

    Args:
        a: 第一个 Simhash 值。
        b: 第二个 Simhash 值。
        python_fallback: Python 实现函数(无 Rust 时调用)。

    Returns:
        汉明距离(0 ~ 64)。

    Raises:
        RuntimeError: Rust 扩展不可用且未提供 python_fallback。
    """
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
    python_fallback: Optional[
        Callable[[float, float, float, float, float], tuple[bool, float, float]]
    ] = None,
) -> tuple[bool, float, float]:
    """令牌桶检查,优先使用 Rust 实现。

    Args:
        tokens: 当前令牌数。
        capacity: 桶容量。
        rate: 每秒补充速率。
        last_refill: 上次补充时间戳。
        now: 当前时间戳。
        python_fallback: Python 实现函数(无 Rust 时调用)。

    Returns:
        (allowed, new_tokens, new_last_refill)。

    Raises:
        RuntimeError: Rust 扩展不可用且未提供 python_fallback。
    """
    if _rust_module is not None and hasattr(_rust_module, "token_bucket_check"):
        return _rust_module.token_bucket_check(tokens, capacity, rate, last_refill, now)
    if python_fallback is not None:
        return python_fallback(tokens, capacity, rate, last_refill, now)
    raise RuntimeError("Rust 扩展不可用且未提供 Python fallback")


# ---------------------------------------------------------------------------
# Rust 扩展构建配置模板
# ---------------------------------------------------------------------------

PYPROJECT_RUST_TEMPLATE = """
[tool.maturin]
# Rust 扩展构建配置(需安装 maturin: pip install maturin)
# 构建: maturin develop --release
# 发布: maturin build --release
module-name = "officeagent_rust"
python-source = "python"
features = ["pyo3/extension-module"]
"""

CARGO_TOML_TEMPLATE = """
[package]
name = "officeagent-rust"
version = "0.1.0"
edition = "2021"

[lib]
name = "officeagent_rust"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.21", features = ["extension-module"] }

[profile.release]
opt-level = 3
lto = true
"""

RUST_LIB_TEMPLATE = '''// officeagent_rust/src/lib.rs
// Rust PyO3 扩展: 高性能哈希与令牌桶运算
use pyo3::prelude::*;

/// FNV-64a 哈希
#[pyfunction]
fn fnv64a(data: &str) -> u64 {
    let mut hash: u64 = 0xCBF29CE484222325;
    for byte in data.as_bytes() {
        hash ^= *byte as u64;
        hash = hash.wrapping_mul(0x100000001B3);
    }
    hash
}

/// Simhash 计算(简化版)
#[pyfunction]
fn simhash(text: &str) -> u64 {
    // ... word-level simhash implementation
    0 // placeholder
}

/// 汉明距离
#[pyfunction]
fn hamming_distance(a: u64, b: u64) -> u32 {
    (a ^ b).count_ones()
}

/// 令牌桶检查
#[pyfunction]
fn token_bucket_check(
    tokens: f64,
    capacity: f64,
    rate: f64,
    last_refill: f64,
    now: f64,
) -> (bool, f64, f64) {
    let elapsed = now - last_refill;
    let new_tokens = (capacity).min(tokens + elapsed * rate);
    let allowed = new_tokens >= 1.0;
    let final_tokens = if allowed { new_tokens - 1.0 } else { new_tokens };
    (allowed, final_tokens, now)
}

#[pymodule]
fn officeagent_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(fnv64a, m)?)?;
    m.add_function(wrap_pyfunction!(simhash, m)?)?;
    m.add_function(wrap_pyfunction!(hamming_distance, m)?)?;
    m.add_function(wrap_pyfunction!(token_bucket_check, m)?)?;
    m.add("__version__", "0.1.0")?;
    Ok(())
}
'''

RUST_README_TEMPLATE = """# officeagent-rust

OfficeAgent Rust PyO3 扩展(可选高性能加速模块)。

## 构建

```bash
pip install maturin
maturin develop --release      # 本地开发安装
maturin build --release        # 构建 wheel
```

## 预期接口

- `fnv64a(data: str) -> int` — FNV-64a 哈希
- `simhash(text: str) -> int` — Simhash 文本指纹
- `hamming_distance(a: int, b: int) -> int` — 汉明距离
- `token_bucket_check(tokens, capacity, rate, last_refill, now) -> (bool, float, float)`
- `__version__: str`

## 加载机制

Python 端通过 `officeagent.core.rust_ext.probe` 自动探测:

- 默认: 探测到则用 Rust,否则回退到 Python 实现
- `OFFICEAGENT_FORCE_RUST=1`: 强制启用(加载失败抛错)
- `OFFICEAGENT_FORCE_RUST=0`: 强制禁用(回退 Python)
"""


def write_rust_project_template(output_dir: str) -> None:
    """将 Rust 扩展项目模板写入指定目录。

    创建:
      output_dir/Cargo.toml
      output_dir/pyproject.toml (maturin 配置)
      output_dir/src/lib.rs
      output_dir/README.md (构建说明)

    Args:
        output_dir: 目标目录(不存在则创建)。

    Raises:
        OSError: 目录创建或文件写入失败。
    """
    import os

    src_dir = os.path.join(output_dir, "src")
    os.makedirs(src_dir, exist_ok=True)

    files = {
        "Cargo.toml": CARGO_TOML_TEMPLATE,
        "pyproject.toml": PYPROJECT_RUST_TEMPLATE,
        "src/lib.rs": RUST_LIB_TEMPLATE,
        "README.md": RUST_README_TEMPLATE,
    }
    for rel_path, content in files.items():
        full_path = os.path.join(output_dir, rel_path)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content.lstrip("\n"))
    logger.info("Rust 扩展项目模板已写入: %s", output_dir)
