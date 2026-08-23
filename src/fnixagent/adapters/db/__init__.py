"""数据库适配器。

延迟导入 postgres 适配器：standalone 默认不安装 psycopg2（见 requirements-optional.txt），
缺包时 DatabaseAdapter 置为 None，仅在显式访问时抛出可读错误，不影响 Desktop / CLI 启动。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

try:
    from fnixagent.adapters.db.postgres import DatabaseAdapter
except ImportError:  # psycopg2 未安装（standalone 默认）
    DatabaseAdapter = None  # type: ignore[assignment]

__all__ = ["DatabaseAdapter"]
