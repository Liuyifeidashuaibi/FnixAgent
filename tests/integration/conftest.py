"""集成测试共享 fixture。

提供 tmp_dir fixture (对齐 unit/conftest.py), 让集成测试可复用临时目录。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir() -> Path:
    """提供临时目录 Path (对齐 pytest 内置 tmp_path, 但命名为 tmp_dir 兼容历史测试)。"""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
