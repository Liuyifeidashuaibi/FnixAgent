"""项目服务层 —— P2-1。

ProjectService 提供项目 CRUD + 成员管理 + 资产管理 + 权限检查。
默认使用内存存储(测试/开发用);生产环境可通过 set_storage 替换为 DB 后端。

DB 表结构(生产环境):
    CREATE TABLE projects (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        owner_id TEXT NOT NULL,
        settings JSONB,
        tags JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        archived_at TIMESTAMPTZ
    );
    CREATE TABLE project_members (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id),
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        invited_by TEXT,
        UNIQUE(project_id, user_id)
    );
    CREATE TABLE project_assets (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id),
        asset_type TEXT NOT NULL,
        ref_id TEXT NOT NULL,
        name TEXT NOT NULL,
        permission TEXT NOT NULL DEFAULT 'read',
        added_by TEXT NOT NULL,
        added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        metadata JSONB
    );
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import threading
import uuid
from datetime import datetime

from fnixagent.core.project.models import (
    AssetPermission,
    AssetType,
    Project,
    ProjectAsset,
    ProjectMember,
    ProjectRole,
    ProjectStatus,
)

class ProjectPermissionError(Exception):
    """项目权限不足。"""

class ProjectNotFoundError(Exception):
    """项目不存在。"""

class ProjectService:
    """项目服务层。

    用法:
        svc = ProjectService()
        project = svc.create_project(tenant_id="t1", name="周报项目", owner_id="u1")
        svc.add_member(project.id, user_id="u2", role=ProjectRole.EDITOR, added_by="u1")
        if svc.check_permission(project.id, user_id="u2", need_write=True):
            ...
    """

    def __init__(self) -> None:
        # 内存存储(生产环境替换为 DB)
        self._projects: dict[str, Project] = {}
        self._members: dict[str, list[ProjectMember]] = {}  # project_id → members
        self._assets: dict[str, list[ProjectAsset]] = {}  # project_id → assets
        self._lock = threading.RLock()

    # -- 项目 CRUD ----------------------------------------------------------
    def create_project(
        self,
        tenant_id: str,
        name: str,
        owner_id: str,
        description: str = "",
        settings: dict | None = None,
        tags: list[str] | None = None,
    ) -> Project:
        """创建项目(自动将 owner 加为 OWNER 成员)。

        Raises:
            ValueError: tenant_id/name/owner_id 为空
        """
        # 参数校验:核心字段非空
        if not tenant_id:
            raise ValueError("tenant_id must be non-empty")
        if not name or not name.strip():
            raise ValueError("project name must be non-empty")
        if not owner_id:
            raise ValueError("owner_id must be non-empty")
        project_id = uuid.uuid4().hex[:16]
        now = datetime.now()
        project = Project(
            id=project_id,
            tenant_id=tenant_id,
            name=name,
            description=description,
            status=ProjectStatus.ACTIVE,
            owner_id=owner_id,
            settings=settings or {},
            tags=tags or [],
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._projects[project_id] = project
            self._members[project_id] = [
                ProjectMember(
                    id=uuid.uuid4().hex[:16],
                    project_id=project_id,
                    user_id=owner_id,
                    role=ProjectRole.OWNER,
                    joined_at=now,
                )
            ]
            self._assets[project_id] = []
        return project

    def get_project(self, project_id: str) -> Project | None:
        """获取项目(不存在返回 None)。"""
        with self._lock:
            return self._projects.get(project_id)

    def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        settings: dict | None = None,
        tags: list[str] | None = None,
        updated_by: str = "",
    ) -> Project:
        """更新项目(需 ADMIN+ 权限)。"""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                raise ProjectNotFoundError(f"项目 {project_id} 不存在")
            # 权限检查
            self._check_permission(project_id, updated_by, need_admin=True)
            if name is not None:
                project.name = name
            if description is not None:
                project.description = description
            if settings is not None:
                project.settings = settings
            if tags is not None:
                project.tags = tags
            project.updated_at = datetime.now()
            return project

    def archive_project(self, project_id: str, archived_by: str) -> Project:
        """归档项目(需 ADMIN+ 权限,归档后只读)。"""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                raise ProjectNotFoundError(f"项目 {project_id} 不存在")
            self._check_permission(project_id, archived_by, need_admin=True)
            project.status = ProjectStatus.ARCHIVED
            project.archived_at = datetime.now()
            project.updated_at = datetime.now()
            return project

    def delete_project(self, project_id: str, deleted_by: str) -> bool:
        """删除项目(仅 OWNER,软删除)。"""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                raise ProjectNotFoundError(f"项目 {project_id} 不存在")
            self._check_permission(project_id, deleted_by, need_owner=True)
            project.status = ProjectStatus.DELETED
            project.updated_at = datetime.now()
            return True

    def list_projects(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
        include_archived: bool = False,
    ) -> list[Project]:
        """列出项目(可按租户/用户过滤)。

        注意:全部过滤逻辑在 _lock 内完成,避免遍历 _members 时并发修改。
        """
        with self._lock:
            projects = list(self._projects.values())
            # 状态过滤
            if not include_archived:
                projects = [p for p in projects if p.status == ProjectStatus.ACTIVE]
            else:
                projects = [p for p in projects if p.status != ProjectStatus.DELETED]
            # 租户过滤
            if tenant_id:
                projects = [p for p in projects if p.tenant_id == tenant_id]
            # 用户过滤(该用户是成员的项目)
            if user_id:
                # BUG 修复:此处访问 _members 必须在锁内,防止并发修改导致迭代错误
                member_project_ids = {
                    m.project_id
                    for members in self._members.values()
                    for m in members
                    if m.user_id == user_id
                }
                projects = [p for p in projects if p.id in member_project_ids]
        return projects

    # -- 成员管理 -----------------------------------------------------------
    def add_member(
        self,
        project_id: str,
        user_id: str,
        role: ProjectRole,
        added_by: str,
    ) -> ProjectMember:
        """添加成员(需 ADMIN+ 权限)。"""
        with self._lock:
            if project_id not in self._projects:
                raise ProjectNotFoundError(f"项目 {project_id} 不存在")
            self._check_permission(project_id, added_by, need_admin=True)
            members = self._members.setdefault(project_id, [])
            # 检查是否已存在
            for m in members:
                if m.user_id == user_id:
                    raise ValueError(f"用户 {user_id} 已是项目成员")
            member = ProjectMember(
                id=uuid.uuid4().hex[:16],
                project_id=project_id,
                user_id=user_id,
                role=role,
                joined_at=datetime.now(),
                invited_by=added_by,
            )
            members.append(member)
            return member

    def remove_member(
        self,
        project_id: str,
        user_id: str,
        removed_by: str,
    ) -> bool:
        """移除成员(需 ADMIN+ 权限;OWNER 不可被移除)。"""
        with self._lock:
            self._check_permission(project_id, removed_by, need_admin=True)
            members = self._members.get(project_id, [])
            for i, m in enumerate(members):
                if m.user_id == user_id:
                    if m.role == ProjectRole.OWNER:
                        raise ProjectPermissionError("不可移除项目所有者")
                    members.pop(i)
                    return True
            return False

    def update_member_role(
        self,
        project_id: str,
        user_id: str,
        new_role: ProjectRole,
        updated_by: str,
    ) -> ProjectMember:
        """更新成员角色(需 ADMIN+ 权限;OWNER 转让需 OWNER 权限)。"""
        with self._lock:
            self._check_permission(project_id, updated_by, need_admin=True)
            # 若设为 OWNER,需当前操作者是 OWNER(转让)
            if new_role == ProjectRole.OWNER:
                self._check_permission(project_id, updated_by, need_owner=True)
            members = self._members.get(project_id, [])
            for m in members:
                if m.user_id == user_id:
                    m.role = new_role
                    return m
            raise ValueError(f"用户 {user_id} 不是项目成员")

    def list_members(self, project_id: str) -> list[ProjectMember]:
        """列出项目全部成员。"""
        with self._lock:
            return list(self._members.get(project_id, []))

    def get_member_role(
        self,
        project_id: str,
        user_id: str,
    ) -> ProjectRole | None:
        """获取用户在项目中的角色(非成员返回 None)。"""
        with self._lock:
            for m in self._members.get(project_id, []):
                if m.user_id == user_id:
                    return ProjectRole(m.role) if isinstance(m.role, str) else m.role
            return None

    # -- 资产管理 -----------------------------------------------------------
    def add_asset(
        self,
        project_id: str,
        asset_type: AssetType,
        ref_id: str,
        name: str,
        added_by: str,
        permission: AssetPermission = AssetPermission.READ,
        metadata: dict | None = None,
    ) -> ProjectAsset:
        """添加资产(需 EDITOR+ 权限)。"""
        with self._lock:
            if project_id not in self._projects:
                raise ProjectNotFoundError(f"项目 {project_id} 不存在")
            self._check_permission(project_id, added_by, need_write=True)
            asset = ProjectAsset(
                id=uuid.uuid4().hex[:16],
                project_id=project_id,
                asset_type=asset_type,
                ref_id=ref_id,
                name=name,
                permission=permission,
                added_by=added_by,
                added_at=datetime.now(),
                metadata=metadata or {},
            )
            self._assets.setdefault(project_id, []).append(asset)
            return asset

    def remove_asset(
        self,
        project_id: str,
        asset_id: str,
        removed_by: str,
    ) -> bool:
        """移除资产(需 ADMIN 权限或资产添加者)。"""
        with self._lock:
            self._check_permission(project_id, removed_by, need_write=True)
            assets = self._assets.get(project_id, [])
            for i, a in enumerate(assets):
                if a.id == asset_id:
                    # ADMIN 或添加者可删除
                    role = self.get_member_role(project_id, removed_by)
                    if (role and role.can_manage_members) or a.added_by == removed_by:
                        assets.pop(i)
                        return True
                    raise ProjectPermissionError("仅管理员或资产添加者可移除资产")
            return False

    def list_assets(
        self,
        project_id: str,
        asset_type: AssetType | None = None,
    ) -> list[ProjectAsset]:
        """列出项目资产(可按类型过滤)。"""
        with self._lock:
            assets = list(self._assets.get(project_id, []))
        if asset_type:
            assets = [a for a in assets if a.asset_type == asset_type]
        return assets

    # -- 权限检查 -----------------------------------------------------------
    def check_permission(
        self,
        project_id: str,
        user_id: str,
        *,
        need_write: bool = False,
        need_admin: bool = False,
        need_owner: bool = False,
    ) -> bool:
        """检查用户权限。"""
        role = self.get_member_role(project_id, user_id)
        if role is None:
            return False
        if need_owner:
            return role == ProjectRole.OWNER
        if need_admin:
            return role.can_manage_members
        if need_write:
            return role.can_write
        return True

    def _check_permission(
        self,
        project_id: str,
        user_id: str,
        *,
        need_write: bool = False,
        need_admin: bool = False,
        need_owner: bool = False,
    ) -> None:
        """内部权限检查(不通过抛异常)。"""
        if not self.check_permission(
            project_id,
            user_id,
            need_write=need_write,
            need_admin=need_admin,
            need_owner=need_owner,
        ):
            raise ProjectPermissionError(f"用户 {user_id} 在项目 {project_id} 中权限不足")
