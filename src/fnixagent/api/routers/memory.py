"""API 路由 — Memory 三层记忆查询（短期 / 长期 / 实体）。

暴露 core.memory.manager.MemoryManager 的查询 API，供前端 OaiSettings Memory section 展示。
4 端点：
  GET   /memory/stats              — 统计信息（short/long/entity 计数）
  GET   /memory/long_term          — 长期记忆检索（user_id + query）
  GET   /memory/profile            — 用户画像（user_id）
  POST  /memory/cleanup            — 清理过期长期记忆
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(prefix="/memory", tags=["memory"])


def _get_memory_manager(request: Request):
    """从 app.state 取 MemoryManager（main.py lifespan 中初始化）。"""
    mgr = getattr(request.app.state, "memory_manager", None)
    if mgr is None:
        raise HTTPException(
            status_code=503,
            detail="MemoryManager not initialized (Work pipeline engine boot failed)",
        )
    return mgr


@router.get("/stats")
async def get_stats(request: Request) -> dict[str, Any]:
    """三层记忆统计信息。"""
    mgr = _get_memory_manager(request)
    try:
        return mgr.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stats failed: {e}")


@router.get("/long_term")
async def search_long_term(
    request: Request,
    user_id: str = Query(..., min_length=1, description="用户 ID"),
    query: str = Query(..., min_length=1, description="检索查询"),
    top_k: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """长期记忆语义检索。"""
    mgr = _get_memory_manager(request)
    try:
        items = mgr.search(user_id=user_id, query=query, top_k=top_k)
        return {
            "user_id": user_id,
            "query": query,
            "top_k": top_k,
            "count": len(items),
            "items": [_memory_item_to_dict(it) for it in items],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"search failed: {e}")


@router.get("/profile")
async def get_user_profile(
    request: Request,
    user_id: str = Query(..., min_length=1, description="用户 ID"),
) -> dict[str, Any]:
    """查询用户画像（实体记忆）。"""
    mgr = _get_memory_manager(request)
    try:
        entity = mgr.get_user_profile(user_id=user_id)
        if entity is None:
            return {"user_id": user_id, "entity": None, "found": False}
        return {
            "user_id": user_id,
            "found": True,
            "entity": {
                "entity_type": entity.entity_type,
                "name": entity.name,
                "attributes": dict(entity.attributes) if entity.attributes else {},
                "confidence": getattr(entity, "confidence", 1.0),
                "updated_at": entity.updated_at.isoformat()
                if getattr(entity, "updated_at", None)
                else None,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"profile failed: {e}")


@router.post("/cleanup")
async def cleanup_expired(request: Request) -> dict[str, Any]:
    """清理过期长期记忆，返回清理条数。"""
    mgr = _get_memory_manager(request)
    try:
        removed = mgr.cleanup()
        return {"ok": True, "removed": removed, "stats_after": mgr.get_stats()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"cleanup failed: {e}")


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _memory_item_to_dict(item: Any) -> dict[str, Any]:
    """MemoryItem → JSON-safe dict。"""
    return {
        "id": getattr(item, "id", ""),
        "content": getattr(item, "content", ""),
        "user_id": getattr(item, "user_id", ""),
        "score": getattr(item, "score", 0.0),
        "metadata": dict(getattr(item, "metadata", {}) or {}),
        "created_at": (item.created_at.isoformat() if getattr(item, "created_at", None) else ""),
    }


__all__ = ["router"]
