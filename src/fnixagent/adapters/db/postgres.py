"""
数据库适配器 - PostgreSQL 连接与操作封装。

使用 SQLAlchemy 进行数据库操作,提供统一接口。

安全特性:
    - 连接字符串脱敏(__repr__ 不暴露密码)
    - 连接参数校验(pool_size/max_overflow 边界)
    - 事务自动提交/回滚(session 上下文管理器)
    - SQL 注入防护:全部使用 ORM filter_by(**dict) 参数化查询
    - 线程安全:session 创建加锁(SQLAlchemy session 非线程安全)
"""

import logging
import re
import threading
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as SQLAlchemySession
from sqlalchemy.orm import sessionmaker

from fnixagent.models.db.models import Base

logger = logging.getLogger(__name__)

# 连接字符串中 password 位的正则, 用于脱敏
# 形如: postgresql://user:password@host:port/db → postgresql://user:***@host:port/db
_PASSWORD_RE = re.compile(r"(://[^:/@]+):[^@/]+@")


def _mask_connection_url(url: str) -> str:
    """脱敏连接字符串中的密码部分。

    Args:
        url: 原始连接字符串(含密码)

    Returns:
        脱敏后的字符串(密码替换为 ***); 无密码则原样返回
    """
    if not url:
        return ""
    return _PASSWORD_RE.sub(r"\1:***@", url)


def _validate_connection_url(url: str) -> None:
    """校验连接字符串格式。

    支持 PostgreSQL 与 SQLite(测试场景) URL。
    形如:
        - postgresql://user:pass@host:port/db
        - sqlite:///path/to/file.db

    Args:
        url: 数据库连接字符串

    Raises:
        ValueError: url 为空或缺少 scheme
    """
    if not url or not isinstance(url, str):
        raise ValueError(f"connection_url 必须为非空字符串, 收到 {url!r}")
    parsed = urlparse(url)
    if not parsed.scheme:
        raise ValueError(f"connection_url 缺少 scheme, 收到 {url!r}")
    # 网络型 DB(postgresql/mysql 等)必须有 host; sqlite 走文件路径, 无 host
    network_schemes = {"postgresql", "postgres", "mysql", "mariadb"}
    if parsed.scheme in network_schemes and not parsed.hostname:
        raise ValueError(f"{parsed.scheme} 连接必须包含 host, 收到 {url!r}")


class DatabaseAdapter:
    """PostgreSQL 数据库适配器。

    线程安全: SQLAlchemy Session 非线程安全, 本类通过 _lock 保护 session 创建。
    事务管理: session() 上下文管理器自动 commit/rollback/close。
    SQL 注入防护: 全部使用 ORM filter_by(**dict) 参数化查询, 不拼接 SQL。

    用法:
        db = DatabaseAdapter("postgresql://user:pass@localhost/db")
        with db.session() as session:
            user = session.query(User).filter_by(id=1).first()
    """

    def __init__(
        self,
        connection_url: str,
        pool_size: int = 20,
        max_overflow: int = 10,
    ):
        """初始化数据库适配器。

        Args:
            connection_url: PostgreSQL 连接字符串(含密码, 不打印)
            pool_size:      连接池大小(正整数)
            max_overflow:   最大溢出连接数(非负整数)

        Raises:
            ValueError: connection_url 为空/格式错, 或 pool_size/max_overflow 越界
        """
        # 参数校验
        _validate_connection_url(connection_url)
        if not isinstance(pool_size, int) or pool_size <= 0:
            raise ValueError(f"pool_size 必须为正 int, 收到 {pool_size!r}")
        if not isinstance(max_overflow, int) or max_overflow < 0:
            raise ValueError(f"max_overflow 必须为非负 int, 收到 {max_overflow!r}")

        # 保存脱敏后的 url(用于 __repr__/日志, 不暴露密码)
        self._masked_url = _mask_connection_url(connection_url)
        # Session 非线程安全, 用锁保护 SessionLocal 的创建/销毁
        self._lock = threading.Lock()
        self.engine = create_engine(
            connection_url,
            pool_size=pool_size,
            max_overflow=max_overflow,
            echo=False,  # 不打印 SQL 语句(避免泄露敏感数据)
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    def __repr__(self) -> str:
        """脱敏 repr: 不暴露连接字符串中的密码。"""
        return f"DatabaseAdapter(url={self._masked_url!r})"

    def create_tables(self) -> None:
        """创建所有表(仅用于初始化)。

        Raises:
            SQLAlchemyError: 表创建失败
        """
        try:
            Base.metadata.create_all(self.engine)
        except SQLAlchemyError as e:
            logger.error("创建表失败: %s", e)
            raise

    def drop_tables(self) -> None:
        """删除所有表(仅用于测试)。

        Raises:
            SQLAlchemyError: 表删除失败
        """
        try:
            Base.metadata.drop_all(self.engine)
        except SQLAlchemyError as e:
            logger.error("删除表失败: %s", e)
            raise

    @contextmanager
    def session(self) -> SQLAlchemySession:
        """提供数据库会话上下文管理器。

        事务管理:
            - 正常退出 → commit()
            - 异常退出 → rollback() + raise
            - 总是 → close()

        线程安全: 通过 _lock 保护 session 创建。

        用法:
            with db.session() as session:
                user = User(username="test")
                session.add(user)
                session.commit()  # 也可不调用, 退出时自动 commit
        """
        # 加锁保护 SessionLocal() 创建(Session 非线程安全)
        with self._lock:
            session = self.SessionLocal()
        try:
            yield session
            # 正常退出 → 提交事务(避免事务未提交的 BUG)
            session.commit()
        except Exception:
            # 异常退出 → 回滚事务
            session.rollback()
            raise
        finally:
            session.close()

    def add(self, obj: Any) -> Any:
        """添加对象到数据库。

        Args:
            obj: ORM 对象

        Returns:
            添加后的对象(包含 ID)

        Raises:
            SQLAlchemyError: 数据库操作失败
        """
        with self.session() as session:
            session.add(obj)
            session.flush()  # 获取 ID 但不提交(由 session() 退出时 commit)
            session.refresh(obj)
            return obj

    def query(self, model: Any, filters: dict | None = None) -> list[Any]:
        """查询对象。

        SQL 注入防护: 使用 filter_by(**filters) 参数化查询, 不拼接 SQL。

        Args:
            model:  ORM 模型类
            filters: 过滤条件字典(参数化, 防 SQL 注入)

        Returns:
            查询结果列表
        """
        with self.session() as session:
            query = session.query(model)
            if filters:
                # 参数化查询: filter_by 内部使用绑定参数, 防 SQL 注入
                query = query.filter_by(**filters)
            return query.all()

    def get_by_id(self, model: Any, id: int) -> Any | None:
        """根据 ID 获取对象。

        Args:
            model: ORM 模型类
            id:    对象 ID

        Returns:
            对象或 None
        """
        with self.session() as session:
            return session.query(model).filter_by(id=id).first()

    def update(self, model: Any, id: int, updates: dict) -> Any | None:
        """更新对象。

        Args:
            model:   ORM 模型类
            id:      对象 ID
            updates: 更新字段字典

        Returns:
            更新后的对象或 None(对象不存在)
        """
        with self.session() as session:
            obj = session.query(model).filter_by(id=id).first()
            if obj:
                for key, value in updates.items():
                    setattr(obj, key, value)
                session.flush()
                session.refresh(obj)
                return obj
            return None

    def delete(self, model: Any, id: int) -> bool:
        """删除对象。

        Args:
            model: ORM 模型类
            id:    对象 ID

        Returns:
            是否删除成功
        """
        with self.session() as session:
            obj = session.query(model).filter_by(id=id).first()
            if obj:
                session.delete(obj)
                return True
            return False

    def close(self) -> None:
        """释放引擎资源(显式关闭, 避免连接泄漏)。"""
        try:
            self.engine.dispose()
        except SQLAlchemyError as e:
            logger.warning("数据库引擎释放失败: %s", e)

    # 上下文管理器支持
    def __enter__(self) -> "DatabaseAdapter":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# 向后兼容别名: 部分代码使用 PostgresAdapter 名称
PostgresAdapter = DatabaseAdapter
