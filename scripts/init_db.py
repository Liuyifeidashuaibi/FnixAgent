# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

﻿"""
数据库初始化脚本。

使用 SQLAlchemy 创建所有表。
"""
from fnixagent.adapters.db.postgres import DatabaseAdapter
from fnixagent.models.db.models import Base


def init_db(connection_url: str):
    """
    初始化数据库表。

    Args:
        connection_url: PostgreSQL连接字符串
    """
    print("Initializing database...")
    db = DatabaseAdapter(connection_url)
    db.create_tables()
    print("Database tables created successfully!")


if __name__ == "__main__":
    # 从环境变量读取配置
    import os

    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://fnixagent:password@localhost:5432/fnixagent"
    )

    init_db(db_url)