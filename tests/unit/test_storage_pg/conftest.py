"""
Phase 0.8 PostgreSQL 持久化 Store 单元测试 fixture。

使用 SQLite 内存数据库测试 Pg*Store(得益于 StringArray/SmallIntArray 跨数据库类型)。
验证接口与内存 Store 一致 + 数据真正持久化(重启不丢)。
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from fnixagent.adapters.db.postgres import DatabaseAdapter
from fnixagent.models.db.models import Base
from fnixagent.services.storage import reset_stores


@pytest.fixture
def db_adapter():
    """创建 SQLite 内存数据库适配器(每个测试独立,隔离)。

    使用 SQLite 验证 Pg*Store 的逻辑正确性:
      - CRUD 操作
      - 数据持久化(同一 adapter 重启数据不丢)
      - 接口签名与内存 Store 一致

    注意:SQLite 不支持 PostgreSQL 的 ARRAY 类型,
    但 StringArray/SmallIntArray TypeDecorator 会自动降级为 JSON,
    因此测试逻辑与生产 PG 环境等价。
    """
    # 使用文件级 SQLite,验证数据真正持久化(关闭连接再开,数据仍在)
    db_path = tempfile.mktemp(suffix=".db")
    url = f"sqlite:///{db_path}"
    adapter = DatabaseAdapter(url)
    # 创建全部表
    Base.metadata.create_all(adapter.engine)
    yield adapter
    # 清理
    adapter.engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def storage_dir():
    """临时文件存储目录(用于 PgDocumentStore 文件落盘)。"""
    d = tempfile.mkdtemp(prefix="fnixagent_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_stores_fixture():
    """每个测试前后重置全局 Store 单例(防止测试间污染)。"""
    reset_stores()
    yield
    reset_stores()
