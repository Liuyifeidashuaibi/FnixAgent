"""
API 路由 - 后台控制面板 Dashboard(Phase 4.4)。

提供运维一屏总览所需的统计指标:
  1. GET /dashboard/overview       — 总览(用户/在线/文档/任务/告警)
  2. GET /dashboard/users          — 用户统计(总数/今日新增/禁用/待注销)
  3. GET /dashboard/audit          — 审计统计(近 24h 动作分布)
  4. GET /dashboard/moderation     — 审核统计(拦截/脱敏/类别分布)
  5. GET /dashboard/system         — 系统信息(版本/运行时长/存储模式)
  6. GET /dashboard/trends         — 趋势(近 7 天用户增长 + 审计量)

所有接口要求 admin 角色。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from fnixagent.api.routers.admin import require_admin
from fnixagent.api.schemas.models import BaseResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# 应用启动时间(用于计算运行时长)
_APP_START_TIME = time.time()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _get_user_store():
    from fnixagent.services.storage import get_user_store

    return get_user_store()


def _get_audit_store():
    from fnixagent.services.storage_audit import get_audit_store

    return get_audit_store()


def _get_moderation_service():
    try:
        from fnixagent.services.moderation import get_moderation_service

        return get_moderation_service()
    except Exception:
        return None


def _to_aware(dt: datetime) -> datetime:
    """将 naive datetime 视为 UTC 并附加 tzinfo，确保与 aware datetime 可比较。

    数据库 / 测试 fixture 中存储的 datetime 可能是 naive 的（无 tzinfo），
    而 ``datetime.now(UTC)`` 返回 aware datetime，直接比较会抛 TypeError。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.get("/overview")
async def get_overview(_admin: dict = Depends(require_admin)):
    """总览:核心指标一屏展示。

    返回:
      - users: {total, active, disabled, pending_deletion, today_new}
      - audit: {last_24h_count, top_action}
      - moderation: {today_blocked, total_blocked}
      - system: {version, uptime_seconds, storage_mode}
    """
    user_store = _get_user_store()
    audit_store = _get_audit_store()

    # 用户统计
    all_users, _ = user_store.list_users(limit=10000)
    total_users = len(all_users)
    disabled_users = sum(1 for u in all_users if u.profile.get("disabled"))
    pending_deletion = sum(1 for u in all_users if u.profile.get("deleted_at"))
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_new = sum(1 for u in all_users if u.created_at and _to_aware(u.created_at) >= today_start)

    # 审计统计(近 24h)
    since = now - timedelta(hours=24)
    audit_logs, audit_total = audit_store.query(
        start=since.isoformat(),
        limit=10000,
    )
    last_24h_count = audit_total or len(audit_logs)

    # 动作分布
    action_counts: dict[str, int] = {}
    for log in audit_logs:
        action_counts[log.action] = action_counts.get(log.action, 0) + 1
    top_action = max(action_counts.items(), key=lambda x: x[1])[0] if action_counts else None

    # 审核统计
    mod_stats = {}
    mod_svc = _get_moderation_service()
    if mod_svc:
        mod_stats = mod_svc.get_stats()

    # 系统信息
    version = os.getenv("fnixagent_VERSION", "1.0.0")
    storage_mode = "postgres" if os.getenv("DATABASE_URL") else "memory"
    uptime_seconds = int(time.time() - _APP_START_TIME)

    return BaseResponse(
        success=True,
        data={
            "users": {
                "total": total_users,
                "active": total_users - disabled_users,
                "disabled": disabled_users,
                "pending_deletion": pending_deletion,
                "today_new": today_new,
            },
            "audit": {
                "last_24h_count": last_24h_count,
                "top_action": top_action,
                "action_distribution": action_counts,
            },
            "moderation": mod_stats,
            "system": {
                "version": version,
                "uptime_seconds": uptime_seconds,
                "storage_mode": storage_mode,
                "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
            },
        },
    )


@router.get("/users")
async def get_user_stats(_admin: dict = Depends(require_admin)):
    """用户统计明细。"""
    user_store = _get_user_store()
    all_users, _ = user_store.list_users(limit=10000)

    # 按角色分布
    role_counts: dict[str, int] = {}
    for u in all_users:
        role_counts[u.role] = role_counts.get(u.role, 0) + 1

    # 按注册日期分布(近 7 天)
    now = datetime.now(UTC)
    daily_new: list[dict] = []
    for i in range(6, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = sum(
            1 for u in all_users if u.created_at and day_start <= _to_aware(u.created_at) < day_end
        )
        daily_new.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "new_users": count,
            }
        )

    return BaseResponse(
        success=True,
        data={
            "total": len(all_users),
            "by_role": role_counts,
            "daily_new_7d": daily_new,
            "pending_deletion": sum(1 for u in all_users if u.profile.get("deleted_at")),
            "disabled": sum(1 for u in all_users if u.profile.get("disabled")),
        },
    )


@router.get("/audit")
async def get_audit_stats(
    _admin: dict = Depends(require_admin),
    hours: int = Query(24, ge=1, le=720, description="统计时间窗口(小时)"),
):
    """审计统计(指定时间窗口内的动作分布)。"""
    audit_store = _get_audit_store()
    now = datetime.now(UTC)
    since = now - timedelta(hours=hours)

    logs, total = audit_store.query(start=since.isoformat(), limit=10000)

    action_counts: dict[str, int] = {}
    user_counts: dict[int, int] = {}
    for log in logs:
        action_counts[log.action] = action_counts.get(log.action, 0) + 1
        if log.user_id:
            user_counts[log.user_id] = user_counts.get(log.user_id, 0) + 1

    # 最活跃用户(Top 10)
    top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return BaseResponse(
        success=True,
        data={
            "window_hours": hours,
            "total_events": total or len(logs),
            "action_distribution": action_counts,
            "top_active_users": [{"user_id": uid, "count": cnt} for uid, cnt in top_users],
        },
    )


@router.get("/moderation")
async def get_moderation_stats(_admin: dict = Depends(require_admin)):
    """审核服务统计。"""
    mod_svc = _get_moderation_service()
    if not mod_svc:
        return BaseResponse(success=True, data={"enabled": False})

    return BaseResponse(
        success=True,
        data={
            "enabled": mod_svc.config.enabled,
            "input_enabled": mod_svc.config.input_enabled,
            "output_enabled": mod_svc.config.output_enabled,
            "auto_sanitize": mod_svc.config.auto_sanitize,
            "block_high_risk_only": mod_svc.config.block_high_risk_only,
            **mod_svc.get_stats(),
        },
    )


@router.patch("/moderation/config")
async def update_moderation_config(
    body: dict,
    _admin: dict = Depends(require_admin),
):
    """更新审核服务配置(运行时热更新)。

    Body 例:
        {"enabled": true, "input_enabled": true, "block_high_risk_only": false}
    """
    mod_svc = _get_moderation_service()
    if not mod_svc:
        return BaseResponse(success=False, error="审核服务未安装")

    allowed_keys = {
        "enabled",
        "input_enabled",
        "output_enabled",
        "auto_sanitize",
        "block_high_risk_only",
        "high_risk_threshold",
    }
    updates = {k: v for k, v in body.items() if k in allowed_keys}
    mod_svc.update_config(**updates)

    return BaseResponse(
        success=True,
        data={
            "updated": list(updates.keys()),
            "current_config": {
                "enabled": mod_svc.config.enabled,
                "input_enabled": mod_svc.config.input_enabled,
                "output_enabled": mod_svc.config.output_enabled,
                "auto_sanitize": mod_svc.config.auto_sanitize,
                "block_high_risk_only": mod_svc.config.block_high_risk_only,
                "high_risk_threshold": mod_svc.config.high_risk_threshold,
            },
        },
    )


@router.get("/system")
async def get_system_info(_admin: dict = Depends(require_admin)):
    """系统信息。"""
    version = os.getenv("fnixagent_VERSION", "1.0.0")
    storage_mode = "postgres" if os.getenv("DATABASE_URL") else "memory"
    uptime_seconds = int(time.time() - _APP_START_TIME)

    # 转换为可读格式
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60

    return BaseResponse(
        success=True,
        data={
            "version": version,
            "uptime_seconds": uptime_seconds,
            "uptime_human": f"{days}d {hours}h {minutes}m",
            "storage_mode": storage_mode,
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "environment": os.getenv("fnixagent_ENV", "development"),
            "mode": os.getenv("FNIXAGENT_MODE", "legacy"),
        },
    )


@router.get("/trends")
async def get_trends(
    _admin: dict = Depends(require_admin),
    days: int = Query(7, ge=1, le=90, description="趋势时间范围(天)"),
):
    """趋势统计(用户增长 + 审计量)。"""
    user_store = _get_user_store()
    audit_store = _get_audit_store()

    now = datetime.now(UTC)
    daily_data: list[dict] = []

    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        # 当日新增用户
        all_users, _ = user_store.list_users(limit=10000)
        new_users = sum(
            1 for u in all_users if u.created_at and day_start <= _to_aware(u.created_at) < day_end
        )

        # 当日审计量
        audit_logs, audit_count = audit_store.query(
            start=day_start.isoformat(),
            end=day_end.isoformat(),
            limit=10000,
        )

        daily_data.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "new_users": new_users,
                "audit_events": audit_count or len(audit_logs),
            }
        )

    return BaseResponse(
        success=True,
        data={
            "days": days,
            "trends": daily_data,
        },
    )


# ---------------------------------------------------------------------------
# P2-02: 监控指标暴露(统一 stats 聚合)
# ---------------------------------------------------------------------------

stats_router = APIRouter(prefix="/stats", tags=["stats"])


@stats_router.get("/detailed")
async def get_detailed_stats(_admin: dict = Depends(require_admin)):
    """返回各核心子系统聚合后的运行时指标快照。

    通过 fnixagent.core.observability.stats.StatsAggregator 采集:
      - rate_limiter / guardrail / autoscale_pool / endpoint_pool
      - deduplicator / priority_queue / checkpoint / reflection / workflow

    单模块采集异常不阻塞其他模块,错误信息记录在 errors 字段。
    """
    from fnixagent.core.observability.stats import get_stats_aggregator

    agg = get_stats_aggregator()
    snapshot = agg.collect()
    return BaseResponse(
        success=True,
        data={
            "timestamp": snapshot["timestamp"],
            "uptime_seconds": snapshot["uptime_seconds"],
            "modules": snapshot["modules"],
            "errors": snapshot["errors"],
            "registered_providers": agg.list_providers(),
            "health": agg.get_health(),
        },
    )


@stats_router.get("/health")
async def get_stats_health(_admin: dict = Depends(require_admin)):
    """返回各模块健康状态(healthy / error / disabled)。"""
    from fnixagent.core.observability.stats import get_stats_aggregator

    agg = get_stats_aggregator()
    return BaseResponse(success=True, data=agg.get_health())
