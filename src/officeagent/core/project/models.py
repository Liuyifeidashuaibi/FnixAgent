"""项目数据模型 —— P2-1。

基于 Pydantic BaseModel,与 DB 表结构对齐。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class ProjectRole(str, Enum):
    """项目成员角色(4 级权限)。"""

    OWNER = "owner"    # 所有者:全部权限 + 删除/转让
    ADMIN = "admin"    # 管理员:全部权限 + 成员管理
    EDITOR = "editor"  # 编辑者:读写资产
    VIEWER = "viewer"  # 只读

    @property
    def can_manage_members(self) -> bool:
        """是否可管理成员(OWNER/ADMIN)。"""
        return self in (ProjectRole.OWNER, ProjectRole.ADMIN)

    @property
    def can_write(self) -> bool:
        """是否可写(OWNER/ADMIN/EDITOR)。"""
        return self != ProjectRole.VIEWER

    @property
    def can_delete(self) -> bool:
        """是否可删除项目(仅 OWNER)。"""
        return self == ProjectRole.OWNER


class ProjectStatus(str, Enum):
    """项目状态。"""

    ACTIVE = "active"      # 活跃
    ARCHIVED = "archived"  # 归档(只读)
    DELETED = "deleted"    # 已删除(软删除)


class AssetType(str, Enum):
    """资产类型。"""

    DOCUMENT = "document"  # 文档(Word/Excel/PPT/PDF)
    TASK = "task"          # 任务
    TOOL = "tool"          # 工具配置
    TEMPLATE = "template"  # 模板
    DATASET = "dataset"    # 数据集
    OTHER = "other"        # 其他


class AssetPermission(str, Enum):
    """资产权限。"""

    READ = "read"      # 只读
    WRITE = "write"    # 读写
    ADMIN = "admin"    # 管理(可删除/分享)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class Project(BaseModel):
    """项目。

    对应 DB 表:projects
    """

    id: str = Field(..., description="项目唯一 ID")
    tenant_id: str = Field(..., description="租户 ID")
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    description: str = Field(default="", max_length=2000, description="项目描述")
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE, description="项目状态")
    owner_id: str = Field(..., description="所有者用户 ID")
    settings: dict[str, Any] = Field(default_factory=dict, description="项目设置")
    tags: list[str] = Field(default_factory=list, description="项目标签")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    archived_at: Optional[datetime] = Field(default=None, description="归档时间")

    class Config:
        use_enum_values = True


class ProjectMember(BaseModel):
    """项目成员。

    对应 DB 表:project_members
    """

    id: str = Field(..., description="成员记录 ID")
    project_id: str = Field(..., description="项目 ID")
    user_id: str = Field(..., description="用户 ID")
    role: ProjectRole = Field(..., description="成员角色")
    joined_at: datetime = Field(default_factory=datetime.now, description="加入时间")
    invited_by: Optional[str] = Field(default=None, description="邀请人")

    class Config:
        use_enum_values = True


class ProjectAsset(BaseModel):
    """项目资产(资源引用)。

    对应 DB 表:project_assets
    资产本身存储在外部(如文档库/任务系统),此处仅存引用与权限。
    """

    id: str = Field(..., description="资产记录 ID")
    project_id: str = Field(..., description="所属项目 ID")
    asset_type: AssetType = Field(..., description="资产类型")
    ref_id: str = Field(..., description="外部资源 ID(如 document_id)")
    name: str = Field(..., description="资产名称(便于展示)")
    permission: AssetPermission = Field(
        default=AssetPermission.READ, description="资产权限级别"
    )
    added_by: str = Field(..., description="添加者用户 ID")
    added_at: datetime = Field(default_factory=datetime.now, description="添加时间")
    metadata: dict[str, Any] = Field(default_factory=dict, description="资产元信息")

    class Config:
        use_enum_values = True
