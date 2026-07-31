"""
领域模型 - 与 ORM 解耦的业务对象。

用于业务逻辑层,不直接依赖 SQLAlchemy。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Tenant:
    """租户领域对象。"""

    id: int
    name: str
    plan: str = "free"  # free/pro/enterprise
    quota_tokens: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class User:
    """用户领域对象。"""

    id: int
    tenant_id: int
    username: str
    email: str | None = None
    role: str = "user"  # user/admin
    profile: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Session:
    """会话领域对象。"""

    id: int
    tenant_id: int
    user_id: int
    title: str | None = None
    context: dict = field(default_factory=dict)
    status: str = "active"  # active/closed/archived
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Message:
    """消息领域对象。"""

    id: int
    session_id: int
    role: str  # user/assistant/system/tool
    content: str
    content_type: str = "text"  # text/json/tool_call/thought
    parent_id: int | None = None
    token_input: int | None = None
    token_output: int | None = None
    model: str | None = None
    trace_id: str | None = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Task:
    """任务领域对象。"""

    id: int
    session_id: int
    user_id: int
    intent: str | None = None
    reasoning_mode: str = "react"  # react/plan_execute/self_reflect
    status: str = "pending"  # pending/running/succeeded/failed
    plan: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TaskStep:
    """任务步骤领域对象。"""

    id: int
    task_id: int
    step_no: int
    description: str
    tool_name: str | None = None
    status: str = "pending"
    depends_on: list[int] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class ToolExecution:
    """工具执行记录领域对象。"""

    id: int
    task_id: int | None = None
    step_id: int | None = None
    tool_name: str
    tool_version: str | None = None
    arguments: dict = field(default_factory=dict)
    result: dict | None = None
    status: str = "success"  # success/failed/timeout
    error: str | None = None
    duration_ms: int | None = None
    sandbox_id: str | None = None
    permission_level: str = "low"
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Document:
    """文档领域对象。"""

    id: int
    tenant_id: int
    user_id: int
    name: str
    doc_type: str  # paper/docx/pdf/markdown/chart
    source: str  # upload/generated/search
    object_key: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Entity:
    """实体记忆领域对象。"""

    id: int
    tenant_id: int
    user_id: int | None = None
    entity_type: str  # user_profile/paper/project/note
    name: str
    attributes: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BillingRecord:
    """计费记录领域对象。"""

    id: int
    tenant_id: int
    user_id: int
    model: str
    token_input: int
    token_output: int
    cost: float
    trace_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# 转换函数: ORM -> 领域对象
# ---------------------------------------------------------------------------


def orm_to_domain(orm_obj: Any) -> Any:
    """
    将 ORM 对象转换为领域对象。

    Args:
        orm_obj: SQLAlchemy ORM 实体

    Returns:
        对应的领域对象
    """
    # 根据类型映射转换
    orm_type = type(orm_obj).__name__

    if orm_type == "Tenant":
        return Tenant(
            id=orm_obj.id,
            name=orm_obj.name,
            plan=orm_obj.plan,
            quota_tokens=orm_obj.quota_tokens,
            created_at=orm_obj.created_at,
        )

    elif orm_type == "User":
        return User(
            id=orm_obj.id,
            tenant_id=orm_obj.tenant_id,
            username=orm_obj.username,
            email=orm_obj.email,
            role=orm_obj.role,
            profile=orm_obj.profile,
            created_at=orm_obj.created_at,
        )

    elif orm_type == "Session":
        return Session(
            id=orm_obj.id,
            tenant_id=orm_obj.tenant_id,
            user_id=orm_obj.user_id,
            title=orm_obj.title,
            context=orm_obj.context,
            status=orm_obj.status,
            created_at=orm_obj.created_at,
            updated_at=orm_obj.updated_at,
        )

    # 其他类型同理...

    return orm_obj  # 默认返回原对象
