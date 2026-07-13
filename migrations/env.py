"""
Alembic 迁移环境(Phase 0.3)。

职责:
    1. 从环境变量 DATABASE_URL 读取连接串(覆盖 alembic.ini 默认值)
    2. 导入 officeagent.models.db.models.Base,把 metadata 注册到 alembic
    3. 支持 online(直接连 DB)与 offline(生成 SQL 文件)两种模式

用法:
    # 应用所有迁移
    alembic upgrade head

    # 创建新迁移(自动检测模型变化)
    alembic revision --autogenerate -m "add xxx table"

    # 回滚一个版本
    alembic downgrade -1
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# 把 src/ 加入 sys.path,使 alembic 能 import officeagent 包
# ---------------------------------------------------------------------------
# alembic.ini 位于项目根,env.py 位于 migrations/
# 项目结构:
#   officeagent/
#   ├── alembic.ini
#   ├── migrations/
#   │   └── env.py  ← 本文件
#   └── src/
#       └── officeagent/
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# 导入所有 ORM 模型,确保 Base.metadata 包含全部表定义
from officeagent.models.db.models import Base  # noqa: E402

# alembic 配置对象
config = context.config

# 日志配置(若 alembic.ini 中定义了 [loggers] 段)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 把 Base.metadata 设为 autogenerate 的比对基准
target_metadata = Base.metadata

# 环境变量 DATABASE_URL 优先于 alembic.ini 中的 sqlalchemy.url
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)


# ---------------------------------------------------------------------------
# Offline 模式:仅生成 SQL,不连 DB(用于 CI / 审计)
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """以 offline 模式运行迁移(生成 SQL 脚本,不连数据库)。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,        # 比较列类型(检测 String 长度变化)
        compare_server_default=True,  # 比较 server_default
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online 模式:连接 DB 执行迁移
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """以 online 模式运行迁移(连接数据库执行)。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # 迁移不需要连接池
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
