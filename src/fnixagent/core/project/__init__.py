"""项目空间化模块 —— P2-1。

为多租户场景提供项目级别的资源隔离与权限管理:
  - Project:       项目(租户内独立工作空间)
  - ProjectMember: 项目成员(角色:OWNER/ADMIN/EDITOR/VIEWER)
  - ProjectAsset:  项目资产(文档/任务/工具等资源的引用)

权限模型(4 级):
  - OWNER:  所有者(全部权限 + 删除/转让)
  - ADMIN:  管理员(全部权限 + 成员管理)
  - EDITOR: 编辑者(读写资产,不可管理成员)
  - VIEWER: 只读(仅查看资产)

模块组成:
  - models:  Pydantic 数据模型
  - service: 业务服务层(CRUD + 权限检查)
"""
from fnixagent.core.project.models import (
    Project,
    ProjectAsset,
    ProjectMember,
    ProjectRole,
    ProjectStatus,
)
from fnixagent.core.project.service import ProjectService

__all__ = [
    "Project",
    "ProjectAsset",
    "ProjectMember",
    "ProjectRole",
    "ProjectStatus",
    "ProjectService",
]
