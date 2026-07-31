"""集成测试共享 fixture。

提供 tmp_dir fixture (对标 unit/conftest.py), 让集成测试可复用临时目录。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir() -> Path:
    """提供临时目录 Path (对标 pytest 内置 tmp_path, 但命名为 tmp_dir 兼容历史测试)。"""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
