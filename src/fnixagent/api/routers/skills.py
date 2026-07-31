"""API 路由 — Skills 技能市场（DRAFT → PENDING_REVIEW → PUBLISHED → DEPRECATED）。

暴露 core.skills.market.SkillMarket 的生命周期管理 API，供前端 OaiSettings Skills section 展示。
6 端点：
  GET    /skills                 — list entries (filter: status / category)
  GET    /skills/drafts          — list drafts (status=DRAFT)
  POST   /skills/drafts          — create draft
  POST   /skills/{id}/submit     — submit for review
  POST   /skills/{id}/approve    — approve (PENDING_REVIEW → PUBLISHED)
  POST   /skills/{id}/deprecate  — deprecate (PUBLISHED → DEPRECATED)
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from fnixagent.core.skills.market import (
    SkillAlreadyExistsError,
    SkillMarket,
    SkillMarketError,
    SkillNotFoundError,
    SkillStatusError,
    SkillVersion,
)

router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# 全局单例（与 mcp.py 风格一致，进程内内存版）
# ---------------------------------------------------------------------------


_market: SkillMarket | None = None
_market_lock = threading.Lock()


def get_skill_market() -> SkillMarket:
    """全局 SkillMarket 单例。"""
    global _market
    if _market is None:
        with _market_lock:
            if _market is None:
                _market = SkillMarket()
    return _market


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class CreateDraftRequest(BaseModel):
    """创建技能草稿请求。"""

    name: str = Field(..., min_length=1, max_length=64)
    display_name: str = ""
    description: str = ""
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    owner_id: str = "desktop"
    tenant_id: str = ""
    icon_url: str | None = None
    # 可选初始版本
    initial_version: str | None = None  # "1.0.0"
    initial_changelog: str = ""


class ReviewActionRequest(BaseModel):
    """审核操作请求（submit / approve / deprecate 共用）。"""

    reviewer_id: str = "desktop"
    comment: str = ""


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("")
async def list_entries(
    status: str | None = Query(
        None, description="draft|pending_review|published|rejected|deprecated"
    ),
    category: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """列出技能条目（支持 status / category 过滤）。"""
    market = get_skill_market()
    status_enum = None
    if status:
        try:
            from fnixagent.core.skills.market import SkillStatus

            status_enum = SkillStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"invalid status '{status}'; expected draft|pending_review|published|rejected|deprecated",
            )
    entries = market.list_entries(
        status=status_enum,
        category=category,
        limit=limit,
        offset=offset,
    )
    return {
        "entries": [_entry_to_dict(e) for e in entries],
        "count": len(entries),
        "stats": market.stats(),
    }


@router.get("/drafts")
async def list_drafts(
    owner_id: str | None = None,
) -> dict[str, Any]:
    """列出 DRAFT 态技能（可选 owner_id 过滤）。"""
    market = get_skill_market()
    entries = market.list_entries()
    drafts = [e for e in entries if e.status.value == "draft"]
    if owner_id:
        drafts = [e for e in drafts if e.owner_id == owner_id]
    return {
        "drafts": [_entry_to_dict(e) for e in drafts],
        "count": len(drafts),
    }


@router.post("/drafts")
async def create_draft(body: CreateDraftRequest) -> dict[str, Any]:
    """创建技能草稿（含可选初始版本）。"""
    market = get_skill_market()
    initial_version: SkillVersion | None = None
    if body.initial_version:
        initial_version = SkillVersion(
            version=body.initial_version,
            changelog=body.initial_changelog,
            created_by=body.owner_id,
        )
    try:
        entry = market.create_draft(
            tenant_id=body.tenant_id,
            name=body.name,
            display_name=body.display_name,
            description=body.description,
            category=body.category,
            tags=body.tags,
            owner_id=body.owner_id,
            icon_url=body.icon_url,
            initial_version=initial_version,
        )
    except SkillAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SkillMarketError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"entry": _entry_to_dict(entry), "ok": True}


@router.post("/{entry_id}/submit")
async def submit_for_review(
    entry_id: str,
    body: ReviewActionRequest,
) -> dict[str, Any]:
    """提交审核（DRAFT → PENDING_REVIEW）。"""
    market = get_skill_market()
    try:
        entry = market.submit_for_review(entry_id, reviewer_id=body.reviewer_id)
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SkillStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"entry": _entry_to_dict(entry), "ok": True}


@router.post("/{entry_id}/approve")
async def approve_entry(
    entry_id: str,
    body: ReviewActionRequest,
) -> dict[str, Any]:
    """审批通过（PENDING_REVIEW → PUBLISHED）。"""
    market = get_skill_market()
    try:
        entry = market.approve(
            entry_id,
            reviewer_id=body.reviewer_id or "desktop",
            comment=body.comment,
        )
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SkillMarketError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"entry": _entry_to_dict(entry), "ok": True}


@router.post("/{entry_id}/deprecate")
async def deprecate_entry(
    entry_id: str,
    body: ReviewActionRequest,
) -> dict[str, Any]:
    """弃用（PUBLISHED → DEPRECATED）。"""
    market = get_skill_market()
    try:
        entry = market.deprecate(entry_id, reason=body.comment)
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SkillStatusError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"entry": _entry_to_dict(entry), "ok": True}


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _entry_to_dict(entry: Any) -> dict[str, Any]:
    """SkillMarketEntry → JSON-safe dict（datetime ISO 化）。"""
    return {
        "id": entry.id,
        "name": entry.name,
        "display_name": entry.display_name,
        "description": entry.description,
        "category": entry.category,
        "tags": list(entry.tags),
        "icon_url": entry.icon_url,
        "owner_id": entry.owner_id,
        "status": entry.status.value,
        "latest_version": entry.latest_version,
        "versions": [
            {
                "version": v.version,
                "changelog": v.changelog,
                "skill_level": v.skill_level,
                "tool_names": list(v.tool_names),
                "created_at": v.created_at.isoformat() if v.created_at else "",
                "created_by": v.created_by,
            }
            for v in entry.versions
        ],
        "install_count": entry.install_count,
        "rating": entry.rating,
        "rating_count": entry.rating_count,
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else "",
        "published_at": entry.published_at.isoformat() if entry.published_at else None,
        "deprecated_at": entry.deprecated_at.isoformat() if entry.deprecated_at else None,
        "reviewer_id": entry.reviewer_id,
        "review_comment": entry.review_comment,
        "reviewed_at": entry.reviewed_at.isoformat() if entry.reviewed_at else None,
    }


__all__ = ["get_skill_market", "router"]
