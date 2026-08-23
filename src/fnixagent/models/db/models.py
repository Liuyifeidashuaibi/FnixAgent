"""
数据库模型层 - SQLAlchemy ORM 实体定义。

对应架构文档第四章的表结构。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import json
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    JSON,
    TEXT,
    TIMESTAMP,
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Table,
    TypeDecorator,
    UniqueConstraint,
)

# PostgreSQL 上用 64 位 BigInteger,SQLite 上用 Integer 以支持 autoincrement。
# 这样生产环境享受 PG 大整数 ID,测试环境可用 SQLite 零依赖运行。
BigIntPK = BigInteger().with_variant(Integer, "sqlite")

from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类。"""

    pass


class StringArray(TypeDecorator):
    """跨数据库字符串数组类型。

    PostgreSQL 上使用原生 ARRAY(TEXT),其他数据库(SQLite/MySQL)用 JSON。
    这样生产环境享受 PG 原生数组性能,测试环境可用 SQLite 零依赖运行。
    """

    impl = TEXT
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(TEXT))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value if value is not None else []
        # SQLite/MySQL:JSON 序列化
        if value is None:
            return []
        return value  # JSON 类型自动序列化

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value if value is not None else []
        if value is None:
            return []
        # JSON 类型自动反序列化
        if isinstance(value, str):
            return json.loads(value)
        return value


class SmallIntArray(TypeDecorator):
    """跨数据库小整数数组类型。

    PostgreSQL 上使用原生 ARRAY(SmallInteger),其他数据库用 JSON。
    """

    impl = SmallInteger
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(SmallInteger))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value if value is not None else []
        if value is None:
            return []
        return value

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value if value is not None else []
        if value is None:
            return []
        if isinstance(value, str):
            return json.loads(value)
        return value


# ---------------------------------------------------------------------------
# 账号与租户
# ---------------------------------------------------------------------------


class Tenant(Base):
    """租户(多租户隔离)。"""

    __tablename__ = "tenants"

    id = Column(BigIntPK, primary_key=True)
    name = Column(String(128), nullable=False)
    plan = Column(String(32), nullable=False, default="free")  # free/pro/enterprise
    quota_tokens = Column(BigInteger, nullable=False, default=0)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # 关系
    users = relationship("User", back_populates="tenant")


class User(Base):
    """用户。"""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),)

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    username = Column(String(64), nullable=False)
    email = Column(String(128), unique=True)
    password_hash = Column(String(255))
    role = Column(
        String(32), nullable=False, default="user"
    )  # user/admin(向后兼容,RBAC 细粒度权限走 user_roles)
    profile = Column(JSON, nullable=False, default=dict)  # 偏好/学科领域
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # Phase 2.1 RBAC:主部门 + 主职位(单值,一个用户一个主部门/职位;多角色走 user_roles 关联表)
    department_id = Column(BigInteger, ForeignKey("departments.id"), nullable=True)
    position_id = Column(BigInteger, ForeignKey("positions.id"), nullable=True)

    # 关系
    tenant = relationship("Tenant", back_populates="users")
    sessions = relationship("Session", back_populates="user")
    api_credentials = relationship("APICredential", back_populates="user")
    department = relationship("Department", back_populates="users", foreign_keys=[department_id])
    position = relationship("Position", back_populates="users", foreign_keys=[position_id])
    roles = relationship("Role", secondary="user_roles", back_populates="users")


class APICredential(Base):
    """API凭证。"""

    __tablename__ = "api_credentials"

    id = Column(BigIntPK, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    api_key_hash = Column(String(255), nullable=False)
    scopes = Column(StringArray, nullable=False, default=list)
    expires_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    revoked_at = Column(TIMESTAMP)

    # 关系
    user = relationship("User", back_populates="api_credentials")


# ---------------------------------------------------------------------------
# 会话与消息
# ---------------------------------------------------------------------------


class Session(Base):
    """会话(按会话隔离记忆)。"""

    __tablename__ = "sessions"
    __table_args__ = (Index("idx_sessions_user", "user_id", "status"),)

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, ForeignKey("tenants.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    title = Column(String(255))
    context = Column(JSON, nullable=False, default=dict)  # 当前任务上下文
    status = Column(String(32), nullable=False, default="active")  # active/closed/archived
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session")
    tasks = relationship("Task", back_populates="session")


class Message(Base):
    """消息(对话/思考/工具记录)。"""

    __tablename__ = "messages"
    __table_args__ = (Index("idx_messages_session", "session_id", "created_at"),)

    id = Column(BigIntPK, primary_key=True)
    session_id = Column(BigInteger, ForeignKey("sessions.id"), nullable=False)
    role = Column(String(16), nullable=False)  # user/assistant/system/tool
    content = Column(TEXT, nullable=False)
    content_type = Column(String(32), nullable=False, default="text")  # text/json/tool_call/thought
    parent_id = Column(BigInteger, ForeignKey("messages.id"))
    token_input = Column(SmallInteger)
    token_output = Column(SmallInteger)
    model = Column(String(64))
    trace_id = Column(String(64))
    # 注意:"metadata" 是 SQLAlchemy Declarative API 保留属性名,
    # 此处 Python 属性命名为 meta,DB 列名仍为 "metadata"(通过首参指定)。
    meta = Column("metadata", JSON, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # 关系
    session = relationship("Session", back_populates="messages")
    parent = relationship("Message", remote_side=[id])


# ---------------------------------------------------------------------------
# 任务与规划
# ---------------------------------------------------------------------------


class Task(Base):
    """任务(用户的一个高层目标)。"""

    __tablename__ = "tasks"
    __table_args__ = (Index("idx_tasks_user_status", "user_id", "status"),)

    id = Column(BigIntPK, primary_key=True)
    session_id = Column(BigInteger, ForeignKey("sessions.id"), nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    intent = Column(String(128))  # 意图: search_paper/edit_word/...
    reasoning_mode = Column(String(32), nullable=False)  # react/plan_execute/self_reflect
    status = Column(
        String(32), nullable=False, default="pending"
    )  # pending/running/succeeded/failed
    plan = Column(JSON, nullable=False, default=dict)  # 规划引擎产出
    result = Column(JSON)  # 最终结果
    error = Column(TEXT)
    started_at = Column(TIMESTAMP)
    finished_at = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # 关系
    session = relationship("Session", back_populates="tasks")
    steps = relationship("TaskStep", back_populates="task")
    tool_executions = relationship("ToolExecution", back_populates="task")


class TaskStep(Base):
    """子任务步骤。"""

    __tablename__ = "task_steps"

    id = Column(BigIntPK, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    step_no = Column(SmallInteger, nullable=False)
    description = Column(TEXT, nullable=False)
    tool_name = Column(String(128))  # 调用的工具
    status = Column(String(32), nullable=False, default="pending")
    depends_on = Column(SmallIntArray, nullable=False, default=list)  # 依赖步骤
    started_at = Column(TIMESTAMP)
    finished_at = Column(TIMESTAMP)

    # 关系
    task = relationship("Task", back_populates="steps")


# ---------------------------------------------------------------------------
# 工具执行记录
# ---------------------------------------------------------------------------


class ToolExecution(Base):
    """工具调用记录。"""

    __tablename__ = "tool_executions"
    __table_args__ = (
        Index("idx_tool_exec_task", "task_id"),
        Index("idx_tool_exec_name_time", "tool_name", "created_at"),
    )

    id = Column(BigIntPK, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id"))
    step_id = Column(BigInteger, ForeignKey("task_steps.id"))
    tool_name = Column(String(128), nullable=False)
    tool_version = Column(String(32))
    arguments = Column(JSON, nullable=False)  # 入参
    result = Column(JSON)  # 返回
    status = Column(String(32), nullable=False)  # success/failed/timeout
    error = Column(TEXT)
    duration_ms = Column(SmallInteger)
    sandbox_id = Column(String(64))  # 油箱实例
    permission_level = Column(String(32), default="low")  # low/middle/high
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # 关系
    task = relationship("Task", back_populates="tool_executions")


# ---------------------------------------------------------------------------
# 工具元数据
# ---------------------------------------------------------------------------


class Tool(Base):
    """工具元数据(标准化工具平台)。"""

    __tablename__ = "tools"

    id = Column(BigIntPK, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(TEXT, nullable=False)  # 给LLM看的功能描述
    category = Column(String(64), nullable=False)  # search/word/pdf/chart/...
    input_schema = Column(JSON, nullable=False)  # JSON Schema入参
    output_schema = Column(JSON)
    permission_level = Column(String(32), nullable=False, default="low")
    timeout_ms = Column(SmallInteger, nullable=False, default=30000)
    rate_limit = Column(SmallInteger)  # 每分钟调用上限
    enabled = Column(Boolean, nullable=False, default=True)
    version = Column(String(32), nullable=False, default="1.0.0")
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# 文档与知识库
# ---------------------------------------------------------------------------


class Document(Base):
    """文档(用户上传/Agent生成)。"""

    __tablename__ = "documents"
    __table_args__ = (Index("idx_docs_user_type", "user_id", "doc_type"),)

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    name = Column(String(255), nullable=False)
    doc_type = Column(String(32), nullable=False)  # paper/docx/pdf/markdown/chart
    source = Column(String(32), nullable=False)  # upload/generated/search
    object_key = Column(String(512))  # MinIO对象键
    mime_type = Column(String(128))
    size_bytes = Column(BigInteger)
    checksum = Column(String(64))
    # DB 列名 "metadata",Python 属性 meta(避免与 Declarative API 保留名冲突)
    meta = Column("metadata", JSON, nullable=False, default=dict)  # 标题/作者/DOI/摘要
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    deleted_at = Column(TIMESTAMP)  # 软删除

    # 关系
    chunks = relationship("KnowledgeChunk", back_populates="document")


class KnowledgeChunk(Base):
    """知识分块(向量入库的元数据)。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (Index("idx_chunks_doc", "document_id"),)

    id = Column(BigIntPK, primary_key=True)
    document_id = Column(BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(SmallInteger, nullable=False)
    content = Column(TEXT, nullable=False)  # 原文分块
    vector_id = Column(String(128))  # Milvus中的向量主键
    token_count = Column(SmallInteger)
    # DB 列名 "metadata",Python 属性 meta(避免与 Declarative API 保留名冲突)
    meta = Column("metadata", JSON, nullable=False, default=dict)  # 章节/页码/标题层级
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # 关系
    document = relationship("Document", back_populates="chunks")


# ---------------------------------------------------------------------------
# 实体记忆
# ---------------------------------------------------------------------------


class Entity(Base):
    """实体记忆(用户/论文/项目等)。"""

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "entity_type", "name", name="uq_tenant_entity"),
        Index("idx_entities_user_type", "user_id", "entity_type"),
    )

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger)  # 可空: 全局实体
    entity_type = Column(String(64), nullable=False)  # user_profile/paper/project/note
    name = Column(String(255), nullable=False)
    attributes = Column(JSON, nullable=False, default=dict)  # 结构化属性
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    source_relations = relationship(
        "EntityRelation",
        foreign_keys="EntityRelation.source_id",
        back_populates="source",
    )
    target_relations = relationship(
        "EntityRelation",
        foreign_keys="EntityRelation.target_id",
        back_populates="target",
    )


class EntityRelation(Base):
    """实体关系(知识图谱式)。"""

    __tablename__ = "entity_relations"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relation", name="uq_entity_relation"),
    )

    id = Column(BigIntPK, primary_key=True)
    source_id = Column(BigInteger, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    target_id = Column(BigInteger, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False)
    relation = Column(String(64), nullable=False)  # authored_by/cites/related_to
    weight = Column(Numeric(12, 6), nullable=False, default=1.0)

    # 关系
    source = relationship("Entity", foreign_keys=[source_id], back_populates="source_relations")
    target = relationship("Entity", foreign_keys=[target_id], back_populates="target_relations")


# ---------------------------------------------------------------------------
# 反思与安全审计
# ---------------------------------------------------------------------------


class ReflectionLog(Base):
    """反思记录。"""

    __tablename__ = "reflection_logs"

    id = Column(BigIntPK, primary_key=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id"))
    step_id = Column(BigInteger, ForeignKey("task_steps.id"))
    check_type = Column(String(64), nullable=False)  # completeness/logic/safety
    passed = Column(Boolean, nullable=False)
    reason = Column(TEXT)
    suggestion = Column(TEXT)  # 重规划建议
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


class AuditLog(Base):
    """安全审计。"""

    __tablename__ = "audit_logs"

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger)
    action = Column(String(64), nullable=False)  # login.success / mfa.enable / permission.denied 等
    detail = Column(JSON, nullable=False)
    trace_id = Column(String(64))
    ip_address = Column(String(64))  # Phase 2.5: 客户端 IP
    user_agent = Column(String(256))  # Phase 2.5: 客户端 User-Agent
    prev_hash = Column(String(64))  # Phase 2.5: 哈希链 — 上一条的 hash
    entry_hash = Column(String(64))  # Phase 2.5: 哈希链 — 本条 hash
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


class PromptTemplate(Base):
    """Prompt模板版本。"""

    __tablename__ = "prompt_templates"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_prompt_template"),)

    id = Column(BigIntPK, primary_key=True)
    name = Column(String(128), nullable=False)
    version = Column(String(32), nullable=False)
    layer = Column(String(32), nullable=False)  # role/constraint/tools/memory/format
    content = Column(TEXT, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# 计费与反馈
# ---------------------------------------------------------------------------


class BillingRecord(Base):
    """Token计费。"""

    __tablename__ = "billing_records"

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    model = Column(String(64), nullable=False)
    token_input = Column(SmallInteger, nullable=False)
    token_output = Column(SmallInteger, nullable=False)
    cost = Column(Numeric(12, 6), nullable=False)
    trace_id = Column(String(64))
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


class Feedback(Base):
    """用户反馈。"""

    __tablename__ = "feedbacks"

    id = Column(BigIntPK, primary_key=True)
    message_id = Column(BigInteger, ForeignKey("messages.id"))
    user_id = Column(BigInteger, nullable=False)
    rating = Column(SmallInteger, nullable=False)  # 1-5
    comment = Column(TEXT)
    tags = Column(StringArray)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Phase 2.1:RBAC 细粒度权限 + 组织架构
# ---------------------------------------------------------------------------


# 关联表:角色 ↔ 权限(多对多)
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        BigInteger,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Index("ix_role_permissions_role_id", "role_id"),
    Index("ix_role_permissions_permission_id", "permission_id"),
)


# 关联表:用户 ↔ 角色(多对多,一个用户可多角色)
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", BigInteger, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("granted_at", TIMESTAMP, nullable=False, default=datetime.utcnow),
    Column("granted_by", BigInteger),  # 授权人 user_id(审计用)
    Index("ix_user_roles_user_id", "user_id"),
    Index("ix_user_roles_role_id", "role_id"),
)


class Role(Base):
    """角色。

    内置角色(super_admin/admin/user/visitor)is_builtin=True 不可删除;
    自定义角色由管理员创建。
    """

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_tenant_role_code"),)

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, nullable=False, default=1)
    code = Column(String(64), nullable=False)  # admin/user/manager/...
    name = Column(String(128), nullable=False)  # 显示名
    description = Column(String(512), default="")
    is_builtin = Column(Boolean, nullable=False, default=False)  # 内置角色不可删
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    users = relationship("User", secondary=user_roles, back_populates="roles")


class Permission(Base):
    """权限。

    权限码格式:`<resource>:<action>`(如 `document:read`、`user:manage`、`role:assign`)。
    前端按 resource 分组展示,后端按 code 精确匹配。
    """

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="uq_permission_code"),)

    id = Column(BigIntPK, primary_key=True)
    code = Column(String(128), nullable=False)  # document:read / user:manage
    name = Column(String(128), nullable=False)  # 显示名
    resource = Column(String(64), nullable=False)  # document/user/role/department/...
    action = Column(String(32), nullable=False)  # read/create/update/delete/manage/assign/...
    description = Column(String(512), default="")
    is_builtin = Column(Boolean, nullable=False, default=True)  # 内置权限不可删
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)

    # 关系
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")


class Department(Base):
    """部门(组织架构,自引用树)。

    通过 parent_id 形成树形结构,顶层部门 parent_id=NULL。
    code 在租户内唯一,用于与 LDAP/AD 同步。
    """

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_tenant_dept_code"),)

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, nullable=False, default=1)
    code = Column(String(64), nullable=False)  # 部门编码
    name = Column(String(128), nullable=False)
    parent_id = Column(BigInteger, ForeignKey("departments.id"), nullable=True)  # 自引用
    manager_id = Column(BigInteger)  # 部门负责人 user_id
    sort_order = Column(SmallInteger, nullable=False, default=0)
    description = Column(String(512), default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    parent = relationship("Department", remote_side=[id], back_populates="children")
    children = relationship("Department", back_populates="parent", cascade="all, delete-orphan")
    users = relationship("User", back_populates="department", foreign_keys="User.department_id")


class Position(Base):
    """职位(职务)。

    level 越大级别越高(用于排序与权限继承参考)。
    """

    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_tenant_position_code"),)

    id = Column(BigIntPK, primary_key=True)
    tenant_id = Column(BigInteger, nullable=False, default=1)
    code = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    level = Column(SmallInteger, nullable=False, default=0)  # 0-100,越大级别越高
    description = Column(String(512), default="")
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        TIMESTAMP, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    users = relationship("User", back_populates="position", foreign_keys="User.position_id")
