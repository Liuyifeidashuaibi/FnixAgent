"""组织内技能市场(P2-2)。,允许组织内部成员:
  - 创建技能草稿(create_draft)
  - 提交审核(submit_for_review)
  - 审批发布(approve / reject)
  - 多版本管理(add_version / list_versions)
  - 弃用下线(deprecate)
  - 全文检索(search)

与现有 STP(技能-拓扑突触协议)的关系:
  - STP 管"运行时调度"(拓扑权重 → 优先级)
  - 本模块管"生命周期管理"(草稿 → 审核 → 发布 → 弃用)
  - SkillMarketEntry.name 与 ToolMetadata.name 对齐,作为安装唯一键
  - SkillInstaller 调用 ToolRegistry.register/unregister 完成实际注册

数据模型层级:
    SkillStatus(枚举) → SkillVersion(版本) → SkillMarketEntry(市场条目)
    一个 Entry 可有多个 Version,但仅 latest_version 处于 PUBLISHED 态

线程安全:SkillMarket 内部用 RLock 保护,可被多线程 API 调用。
持久化:本实现为内存版;生产环境可由子类重写 _load/_persist 接入 DB。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# 技能名合法字符:字母/数字/下划线/连字符,1~64 字符
_SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
# 版本号语义化版本(semver)宽松匹配
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")

# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class SkillStatus(str, Enum):
    """技能生命周期状态。

    状态机:
        DRAFT ──submit──→ PENDING_REVIEW ──approve──→ PUBLISHED
                                       └──reject──→ REJECTED(可改回 DRAFT)
        PUBLISHED ──deprecate──→ DEPRECATED
    """

    DRAFT = "draft"  # 草稿(创建者可编辑)
    PENDING_REVIEW = "pending_review"  # 待审核
    PUBLISHED = "published"  # 已发布(可被安装)
    REJECTED = "rejected"  # 审核拒绝(可改回 DRAFT 修改)
    DEPRECATED = "deprecated"  # 已弃用(不可安装,已安装可继续用)


# 允许的状态转换(用于校验)。
# 状态机设计原则:严格线性流转,禁止跳过 PENDING_REVIEW 直接进入 PUBLISHED。
#   DRAFT ──submit──→ PENDING_REVIEW ──approve──→ PUBLISHED ──deprecate──→ DEPRECATED
#                        └──reject──→ REJECTED ──reactivate──→ DRAFT
#   DEPRECATED ──reactivate──→ DRAFT(重新上架需重新走审核流程)
# 注意:
#   - PUBLISHED 不能直接回 DRAFT(必须先 DEPRECATED 再 DRAFT,避免绕过审核)
#   - REJECTED 不能直接 DEPRECATED(rejected 本身未发布,无需弃用,应回 DRAFT 修改)
#   - DRAFT 不能直接 DEPRECATED(草稿应直接删除,而非弃用)
_VALID_TRANSITIONS: dict[SkillStatus, set[SkillStatus]] = {
    SkillStatus.DRAFT: {SkillStatus.PENDING_REVIEW},
    SkillStatus.PENDING_REVIEW: {
        SkillStatus.PUBLISHED,
        SkillStatus.REJECTED,
        SkillStatus.DRAFT,  # 撤回审核
    },
    SkillStatus.PUBLISHED: {SkillStatus.DEPRECATED},
    SkillStatus.REJECTED: {SkillStatus.DRAFT},
    SkillStatus.DEPRECATED: {SkillStatus.DRAFT},  # 重新上架需走草稿流程
}

# ---------------------------------------------------------------------------
# Pydantic 模型
# ---------------------------------------------------------------------------


class SkillVersion(BaseModel):
    """技能版本。

    一个技能可发布多个版本,每个版本独立记录变更日志和工具列表。
    version 字段遵循语义化版本(semver):"1.0.0" / "1.1.0" 等。
    """

    version: str = Field(..., description="语义化版本号,如 1.0.0")
    changelog: str = Field("", description="本版本变更说明")
    skill_level: str = Field(
        "basic",
        description="技能权限级别:basic(自动)/reasoning(确认)/meta(禁用)",
    )
    tool_names: list[str] = Field(
        default_factory=list,
        description="本版本包含的工具名列表(对应 ToolMetadata.name)",
    )
    config_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="配置项 JSON Schema(安装时校验用户提供的 config)",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field("", description="创建者用户 ID")


class SkillMarketEntry(BaseModel):
    """技能市场条目。

    一个 Entry 对应一个可被组织成员安装的技能包,内含多个版本。
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    tenant_id: str = Field("", description="租户 ID(空表示全局公共市场)")
    name: str = Field(..., description="技能唯一标识(与 ToolMetadata.name 对齐)")
    display_name: str = Field("", description="展示名(可中文)")
    description: str = Field("", description="技能描述")
    category: str = Field("general", description="分类标签")
    tags: list[str] = Field(default_factory=list)
    icon_url: str | None = None
    owner_id: str = Field("", description="所有者用户 ID")
    status: SkillStatus = SkillStatus.DRAFT
    versions: list[SkillVersion] = Field(default_factory=list)
    latest_version: str | None = None
    install_count: int = 0
    rating: float = 0.0  # 0.0-5.0
    rating_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: datetime | None = None
    deprecated_at: datetime | None = None
    # 审核相关
    reviewer_id: str = ""
    review_comment: str = ""
    reviewed_at: datetime | None = None


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class SkillMarketError(Exception):
    """技能市场基础异常。"""


class SkillNotFoundError(SkillMarketError):
    """技能不存在。"""


class SkillVersionNotFoundError(SkillMarketError):
    """技能版本不存在。"""


class SkillStatusError(SkillMarketError):
    """状态转换非法(如 DRAFT 直接 PUBLISHED)。"""


class SkillAlreadyExistsError(SkillMarketError):
    """技能名已存在(同租户内唯一)。"""


class SkillReviewError(SkillMarketError):
    """审核操作非法(如非 PENDING_REVIEW 状态调 approve)。"""


# ---------------------------------------------------------------------------
# SkillMarket
# ---------------------------------------------------------------------------


class SkillMarket:
    """组织内技能市场。

    职责:
        - 技能生命周期管理(DRAFT → PENDING_REVIEW → PUBLISHED → DEPRECATED)
        - 多版本管理(add_version / list_versions / get_version)
        - 全文检索(search:名称/描述/标签/分类)
        - 安装计数(install_count 由 SkillInstaller 调用 increment_install_count 维护)

    线程安全:所有写操作加 RLock。
    多租户:tenant_id 隔离;空 tenant_id 表示全局公共市场。
    """

    def __init__(self) -> None:
        self._entries: dict[str, SkillMarketEntry] = {}  # id → entry
        self._name_index: dict[str, set[str]] = {}  # (tenant_id, name) → {entry_ids}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 草稿与发布
    # ------------------------------------------------------------------

    def create_draft(
        self,
        tenant_id: str,
        name: str,
        display_name: str = "",
        description: str = "",
        category: str = "general",
        tags: list[str] | None = None,
        owner_id: str = "",
        icon_url: str | None = None,
        initial_version: SkillVersion | None = None,
    ) -> SkillMarketEntry:
        """创建技能草稿。

        Args:
            tenant_id: 租户 ID(空表示全局公共市场)
            name: 技能唯一标识(同租户内不可重复)
            display_name: 展示名(可中文,默认等于 name)
            initial_version: 初始版本(可选,不传则不创建版本)

        Returns:
            创建的 SkillMarketEntry

        Raises:
            SkillAlreadyExistsError: 同租户内 name 已存在
            SkillMarketError: name 格式非法
        """
        self._validate_skill_name(name)
        with self._lock:
            key = self._name_key(tenant_id, name)
            if self._name_index.get(key):
                raise SkillAlreadyExistsError(
                    f"Skill '{name}' already exists in tenant '{tenant_id}'"
                )
            entry = SkillMarketEntry(
                tenant_id=tenant_id,
                name=name,
                display_name=display_name or name,
                description=description,
                category=category,
                tags=list(tags or []),
                owner_id=owner_id,
                icon_url=icon_url,
                status=SkillStatus.DRAFT,
            )
            if initial_version is not None:
                entry.versions.append(initial_version)
                entry.latest_version = initial_version.version
            self._entries[entry.id] = entry
            self._name_index.setdefault(key, set()).add(entry.id)
            return entry

    def submit_for_review(self, entry_id: str, reviewer_id: str = "") -> SkillMarketEntry:
        """提交审核(DRAFT → PENDING_REVIEW)。

        Args:
            entry_id: 技能 ID
            reviewer_id: 指定审核人(可选)

        Raises:
            SkillNotFoundError: entry_id 不存在
            SkillStatusError: 当前状态非 DRAFT
        """
        with self._lock:
            entry = self._get_or_raise(entry_id)
            self._check_transition(entry, SkillStatus.PENDING_REVIEW)
            if not entry.versions:
                raise SkillStatusError(f"Cannot submit skill '{entry.name}': no version added")
            entry.status = SkillStatus.PENDING_REVIEW
            entry.reviewer_id = reviewer_id
            entry.updated_at = datetime.utcnow()
            return entry

    def approve(
        self,
        entry_id: str,
        reviewer_id: str,
        comment: str = "",
    ) -> SkillMarketEntry:
        """审批通过(PENDING_REVIEW → PUBLISHED)。

        Args:
            reviewer_id: 审核人 ID(必须非空)
            comment: 审核意见(可选)

        Raises:
            SkillReviewError: 当前状态非 PENDING_REVIEW
        """
        if not reviewer_id:
            raise SkillReviewError("reviewer_id is required for approval")
        with self._lock:
            entry = self._get_or_raise(entry_id)
            if entry.status != SkillStatus.PENDING_REVIEW:
                raise SkillReviewError(f"Cannot approve skill in status {entry.status.value}")
            entry.status = SkillStatus.PUBLISHED
            entry.reviewer_id = reviewer_id
            entry.review_comment = comment
            entry.reviewed_at = datetime.utcnow()
            entry.published_at = datetime.utcnow()
            entry.updated_at = datetime.utcnow()
            return entry

    def reject(
        self,
        entry_id: str,
        reviewer_id: str,
        comment: str = "",
    ) -> SkillMarketEntry:
        """审核拒绝(PENDING_REVIEW → REJECTED)。

        Args:
            comment: 拒绝原因(建议必填)
        """
        if not reviewer_id:
            raise SkillReviewError("reviewer_id is required for rejection")
        with self._lock:
            entry = self._get_or_raise(entry_id)
            if entry.status != SkillStatus.PENDING_REVIEW:
                raise SkillReviewError(f"Cannot reject skill in status {entry.status.value}")
            entry.status = SkillStatus.REJECTED
            entry.reviewer_id = reviewer_id
            entry.review_comment = comment
            entry.reviewed_at = datetime.utcnow()
            entry.updated_at = datetime.utcnow()
            return entry

    def deprecate(self, entry_id: str, reason: str = "") -> SkillMarketEntry:
        """弃用技能(PUBLISHED → DEPRECATED)。

        已安装的技能可继续使用,但市场不再允许新安装。
        """
        with self._lock:
            entry = self._get_or_raise(entry_id)
            self._check_transition(entry, SkillStatus.DEPRECATED)
            entry.status = SkillStatus.DEPRECATED
            entry.deprecated_at = datetime.utcnow()
            entry.review_comment = reason
            entry.updated_at = datetime.utcnow()
            return entry

    def reactivate(self, entry_id: str) -> SkillMarketEntry:
        """重新激活(DEPRECATED/REJECTED → DRAFT)。

        需重新走 submit_for_review → approve 流程才能再次 PUBLISHED。
        """
        with self._lock:
            entry = self._get_or_raise(entry_id)
            self._check_transition(entry, SkillStatus.DRAFT)
            entry.status = SkillStatus.DRAFT
            entry.reviewer_id = ""
            entry.review_comment = ""
            entry.reviewed_at = None
            entry.updated_at = datetime.utcnow()
            return entry

    # ------------------------------------------------------------------
    # 版本管理
    # ------------------------------------------------------------------

    def add_version(
        self,
        entry_id: str,
        version: SkillVersion,
    ) -> SkillMarketEntry:
        """为技能追加版本。

        仅 DRAFT/REJECTED 态可追加版本(PUBLISHED 态需先 reactivate 或新发版走流程)。
        新版本追加后自动更新 latest_version。

        Raises:
            SkillStatusError: 当前状态非 DRAFT/REJECTED
            SkillMarketError: 版本号已存在或格式非法
        """
        self._validate_version(version.version)
        with self._lock:
            entry = self._get_or_raise(entry_id)
            if entry.status not in (SkillStatus.DRAFT, SkillStatus.REJECTED):
                raise SkillStatusError(
                    f"Cannot add version in status {entry.status.value}; reactivate to DRAFT first"
                )
            existing_versions = {v.version for v in entry.versions}
            if version.version in existing_versions:
                raise SkillMarketError(
                    f"Version {version.version} already exists for skill '{entry.name}'"
                )
            entry.versions.append(version)
            entry.latest_version = version.version
            entry.updated_at = datetime.utcnow()
            return entry

    def list_versions(self, entry_id: str) -> list[SkillVersion]:
        """列出技能的全部版本(按创建时间倒序)。"""
        with self._lock:
            entry = self._get_or_raise(entry_id)
            return sorted(
                entry.versions,
                key=lambda v: v.created_at,
                reverse=True,
            )

    def get_version(
        self,
        entry_id: str,
        version: str | None = None,
    ) -> SkillVersion:
        """获取指定版本;version=None 返回 latest_version。

        Raises:
            SkillVersionNotFoundError: 版本不存在或无任何版本
        """
        with self._lock:
            entry = self._get_or_raise(entry_id)
            if not entry.versions:
                raise SkillVersionNotFoundError(f"Skill '{entry.name}' has no versions")
            if version is None:
                target = entry.latest_version
                if target is None:
                    target = entry.versions[-1].version
            else:
                target = version
            for v in entry.versions:
                if v.version == target:
                    return v
            raise SkillVersionNotFoundError(
                f"Version '{version}' not found in skill '{entry.name}'"
            )

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def get_entry(self, entry_id: str) -> SkillMarketEntry | None:
        """按 ID 获取技能条目(不存在返回 None)。"""
        with self._lock:
            return self._entries.get(entry_id)

    def get_entry_by_name(
        self,
        name: str,
        tenant_id: str = "",
    ) -> SkillMarketEntry | None:
        """按 name + tenant_id 获取技能条目。"""
        with self._lock:
            key = self._name_key(tenant_id, name)
            entry_ids = self._name_index.get(key, set())
            if not entry_ids:
                # 回退到全局公共市场
                if tenant_id:
                    global_key = self._name_key("", name)
                    entry_ids = self._name_index.get(global_key, set())
            if not entry_ids:
                return None
            # 取第一个(同租户内 name 唯一)
            return self._entries[next(iter(entry_ids))]

    def list_entries(
        self,
        tenant_id: str | None = None,
        status: SkillStatus | None = None,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkillMarketEntry]:
        """列出技能条目(支持过滤)。

        Args:
            tenant_id: 限制租户(None 表示全部)
            status: 限制状态
            category: 限制分类
            limit/offset: 分页
        """
        with self._lock:
            entries = list(self._entries.values())
            if tenant_id is not None:
                entries = [e for e in entries if e.tenant_id == tenant_id]
            if status is not None:
                entries = [e for e in entries if e.status == status]
            if category is not None:
                entries = [e for e in entries if e.category == category]
            entries.sort(key=lambda e: e.updated_at, reverse=True)
            return entries[offset : offset + limit]

    def search(
        self,
        query: str,
        tenant_id: str | None = None,
        top_k: int = 20,
    ) -> list[SkillMarketEntry]:
        """全文检索(名称/描述/标签/分类)。

        简易实现:子串匹配 + 加权排序(名称命中 > 标签 > 描述 > 分类)。
        生产环境可替换为向量检索。
        """
        if not query:
            return []
        q = query.lower()
        with self._lock:
            scored: list[tuple[float, SkillMarketEntry]] = []
            for entry in self._entries.values():
                if tenant_id is not None and entry.tenant_id != tenant_id:
                    continue
                if entry.status == SkillStatus.DEPRECATED:
                    continue  # 弃用技能不参与搜索
                score = 0.0
                name_l = entry.name.lower()
                display_l = entry.display_name.lower()
                desc_l = entry.description.lower()
                category_l = entry.category.lower()
                tags_l = [t.lower() for t in entry.tags]
                if q == name_l or q == display_l:
                    score += 5.0
                elif q in name_l or q in display_l:
                    score += 3.0
                if any(q == t for t in tags_l):
                    score += 4.0
                elif any(q in t for t in tags_l):
                    score += 2.0
                if q in desc_l:
                    score += 1.5
                if q in category_l:
                    score += 1.0
                if score > 0:
                    # 已发布技能加权
                    if entry.status == SkillStatus.PUBLISHED:
                        score += 0.5
                    scored.append((score, entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [e for _, e in scored[:top_k]]

    # ------------------------------------------------------------------
    # 安装计数(供 SkillInstaller 调用)
    # ------------------------------------------------------------------

    def increment_install_count(self, entry_id: str, delta: int = 1) -> int:
        """增减安装计数(安装 +1,卸载 -1,不低于 0)。

        Returns:
            更新后的 install_count
        """
        with self._lock:
            entry = self._get_or_raise(entry_id)
            entry.install_count = max(0, entry.install_count + delta)
            entry.updated_at = datetime.utcnow()
            return entry.install_count

    def update_rating(self, entry_id: str, new_rating: float) -> SkillMarketEntry:
        """更新评分(0.0-5.0,追加平均)。

        Args:
            new_rating: 单次评分(0.0-5.0)
        """
        if not 0.0 <= new_rating <= 5.0:
            raise SkillMarketError(f"rating must be in [0.0, 5.0], got {new_rating}")
        with self._lock:
            entry = self._get_or_raise(entry_id)
            total = entry.rating * entry.rating_count + new_rating
            entry.rating_count += 1
            entry.rating = round(total / entry.rating_count, 2)
            entry.updated_at = datetime.utcnow()
            return entry

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _name_key(self, tenant_id: str, name: str) -> str:
        return f"{tenant_id}::{name}"

    def _get_or_raise(self, entry_id: str) -> SkillMarketEntry:
        entry = self._entries.get(entry_id)
        if entry is None:
            raise SkillNotFoundError(f"Skill entry '{entry_id}' not found")
        return entry

    def _check_transition(
        self,
        entry: SkillMarketEntry,
        target: SkillStatus,
    ) -> None:
        # 状态机校验:从 _VALID_TRANSITIONS 表查询允许的目标状态集合
        allowed = _VALID_TRANSITIONS.get(entry.status, set())
        if target not in allowed:
            raise SkillStatusError(
                f"Cannot transition skill '{entry.name}' from "
                f"{entry.status.value} to {target.value}"
            )

    @staticmethod
    def _validate_skill_name(name: str) -> None:
        """校验技能名格式(非空 + 合法字符)。

        Args:
            name: 技能名

        Raises:
            SkillMarketError: name 为空或含非法字符
        """
        if not name or not isinstance(name, str):
            raise SkillMarketError("skill name must be a non-empty string")
        if not _SKILL_NAME_PATTERN.match(name):
            raise SkillMarketError(
                f"Invalid skill name '{name}': only letters, digits, "
                "'_' and '-' are allowed (1-64 chars)"
            )

    @staticmethod
    def _validate_version(version: str) -> None:
        """校验版本号格式(语义化版本)。

        Args:
            version: 版本号字符串(如 "1.0.0")

        Raises:
            SkillMarketError: version 格式非法
        """
        if not version or not isinstance(version, str):
            raise SkillMarketError("version must be a non-empty string")
        if not _VERSION_PATTERN.match(version):
            raise SkillMarketError(
                f"Invalid version '{version}': expected semver format (e.g. '1.0.0')"
            )

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """市场统计(总数/各状态数/已发布数/总安装数)。"""
        with self._lock:
            entries = list(self._entries.values())
            by_status: dict[str, int] = {}
            for e in entries:
                by_status[e.status.value] = by_status.get(e.status.value, 0) + 1
            return {
                "total": len(entries),
                "by_status": by_status,
                "published": sum(1 for e in entries if e.status == SkillStatus.PUBLISHED),
                "total_installs": sum(e.install_count for e in entries),
            }
