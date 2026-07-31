"""审计日志路由(Phase 2.5)。

提供:
    1. GET  /audit/logs       — 查询审计日志(分页+多维筛选)
    2. GET  /audit/export      — 导出审计日志(JSON/CSV)
    3. GET  /audit/verify      — 校验哈希链完整性
    4. GET  /audit/actions     — 列出所有审计动作类型
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from fnixagent.api.schemas.models import BaseResponse
from fnixagent.core.security.rbac import require_permission

router = APIRouter(tags=["audit"])

# 审计日志查看权限码(Phase 2.1 RBAC 已内置)
_AUDIT_PERM = "system:audit_log"


def _get_logger():
    from fnixagent.core.audit import AuditLogger

    return AuditLogger()


def _get_ip_ua(http_request: Request) -> tuple[str, str]:
    """从 Request 提取 User-Agent 与客户端 IP。"""
    ua = http_request.headers.get("user-agent", "")
    forwarded = http_request.headers.get("x-forwarded-for", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = http_request.client.host if http_request.client else ""
    return ua, ip


@router.get("/audit/logs", response_model=BaseResponse)
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: int | None = Query(None, description="按用户 ID 筛选"),
    action: str | None = Query(None, description="按操作类型筛选"),
    start: str | None = Query(None, description="起始时间 ISO 8601"),
    end: str | None = Query(None, description="结束时间 ISO 8601"),
    ip_address: str | None = Query(None, description="按 IP 筛选"),
    _perm: dict = Depends(require_permission(_AUDIT_PERM)),
):
    """查询审计日志(按时间/用户/操作类型/IP 筛选)。"""
    logger = _get_logger()
    logs, total = logger.list(
        limit=limit,
        offset=offset,
        user_id=user_id,
        action=action,
        start=start,
        end=end,
        ip_address=ip_address,
    )
    return BaseResponse(
        success=True,
        data={
            "items": [log.to_dict() for log in logs],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    )


@router.get("/audit/export")
async def export_audit_logs(
    http_request: Request,
    format: str = Query("json", pattern="^(json|csv)$"),
    user_id: int | None = Query(None),
    action: str | None = Query(None),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
    _perm: dict = Depends(require_permission(_AUDIT_PERM)),
):
    """导出审计日志(JSON 或 CSV 格式)。

    支持最近 90 天日志导出(limit 最大 50000 条)。
    导出操作本身会被记录到审计日志。
    """
    logger = _get_logger()
    ua, ip = _get_ip_ua(http_request)

    # 记录导出操作本身
    from fnixagent.core.audit import AUDIT_DATA_EXPORT

    logger.log(
        action=AUDIT_DATA_EXPORT,
        user_id=_perm.get("user_id"),
        detail={
            "format": format,
            "filters": {
                "user_id": user_id,
                "action": action,
                "start": start,
                "end": end,
                "limit": limit,
            },
        },
        ip_address=ip,
        user_agent=ua,
    )

    content = logger.export(
        format=format,
        user_id=user_id,
        action=action,
        start=start,
        end=end,
        limit=limit,
    )

    if format == "csv":
        return PlainTextResponse(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
        )
    else:
        return PlainTextResponse(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit_logs.json"},
        )


@router.get("/audit/verify", response_model=BaseResponse)
async def verify_audit_chain(
    _perm: dict = Depends(require_permission(_AUDIT_PERM)),
):
    """校验审计日志哈希链完整性(检测是否被篡改)。"""
    logger = _get_logger()
    is_valid, broken_id = logger.verify_chain()
    return BaseResponse(
        success=True,
        data={
            "is_valid": is_valid,
            "broken_at_id": broken_id,
            "message": "哈希链完整,无篡改"
            if is_valid
            else f"哈希链在 ID={broken_id} 处断裂,可能被篡改",
        },
    )


@router.get("/audit/actions", response_model=BaseResponse)
async def list_audit_actions(
    _perm: dict = Depends(require_permission(_AUDIT_PERM)),
):
    """列出所有审计动作类型(用于前端筛选下拉框)。"""
    from fnixagent.core.audit import ALL_AUDIT_ACTIONS

    return BaseResponse(
        success=True,
        data={"items": list(ALL_AUDIT_ACTIONS)},
    )
