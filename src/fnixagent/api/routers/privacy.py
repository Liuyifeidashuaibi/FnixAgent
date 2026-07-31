"""
API 路由 - 用户隐私中心(Phase 3.2 / 2.12)。

提供:
  1. GET  /privacy/profile         — 查看本人个人数据
  2. GET  /privacy/export          — 导出全部个人数据(JSON)
  3. POST /privacy/delete-account  — 注销账号(软删除,30 天保留期)
  4. POST /privacy/cancel-deletion — 撤销注销(30 天内可恢复)
  5. GET  /privacy/deletion-status — 查询注销状态

设计:
  - 所有接口要求 Access Token(本人操作)
  - 导出/注销自动写入审计日志
  - 注销后立即禁用登录(disabled=True),但保留数据 30 天
  - 30 天后由后台清理任务硬删除
  - 所有响应中的 PII 已脱敏(手机号/邮箱/身份证)
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from fnixagent.api.routers.auth import _get_user_or_404, verify_jwt_token
from fnixagent.api.schemas.models import BaseResponse
from fnixagent.services.storage import (
    get_apikey_store,
    get_document_store,
    get_task_store,
    get_user_store,
)

router = APIRouter(prefix="/privacy", tags=["privacy"])

# 默认账号注销保留期(天)
_DEFAULT_RETENTION_DAYS = 30


# ---------------------------------------------------------------------------
# 审计辅助
# ---------------------------------------------------------------------------


def _audit_privacy(
    action: str,
    user_id: int | None,
    detail: dict,
    http_request: Request,
) -> None:
    """写入隐私操作的审计日志(失败不影响主流程)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        ua = http_request.headers.get("user-agent", "")
        forwarded = http_request.headers.get("x-forwarded-for", "")
        ip = (
            forwarded.split(",")[0].strip()
            if forwarded
            else (http_request.client.host if http_request.client else "")
        )
        AuditLogger().log(
            action=action,
            user_id=user_id,
            detail=detail,
            ip_address=ip,
            user_agent=ua,
        )
    except Exception:
        pass


def _get_request_ip(request: Request) -> str:
    """从 Request 提取客户端 IP。"""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.get("/profile")
async def get_own_profile(payload: dict = Depends(verify_jwt_token)):
    """查看本人个人数据(已脱敏)。

    返回内容:
      - 用户基本信息(用户名、邮箱、角色、创建时间)
      - 配额信息
      - 手机号(脱敏:138****5678)
    """
    user = _get_user_or_404(payload)
    profile = dict(user.profile or {})

    # 脱敏手机号
    phone = profile.get("phone", "")
    masked_phone = ""
    if phone and len(phone) == 11:
        masked_phone = f"{phone[:3]}****{phone[7:]}"

    return BaseResponse(
        success=True,
        data={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "phone": masked_phone,
            "quota": {
                "total": user.quota_total,
                "used": user.quota_used,
                "remaining": max(0, user.quota_total - user.quota_used),
            },
            "disabled": profile.get("disabled", False),
            "deleted_at": profile.get("deleted_at"),
            "hard_delete_at": profile.get("hard_delete_at"),
        },
    )


@router.get("/export")
async def export_personal_data(
    http_request: Request,
    payload: dict = Depends(verify_jwt_token),
):
    """导出当前用户的全部个人数据(JSON 文件下载)。

    包含:
      - 用户基本信息
      - API Keys(仅元数据,不含密钥明文)
      - 文档列表
      - 任务列表
      - 审计日志(本用户的最近 100 条)

    响应 Content-Type: application/json
    响应 Content-Disposition: attachment; filename="fnixagent_export_<uid>_<ts>.json"
    """
    user = _get_user_or_404(payload)
    user_id = user.id

    # 写入审计日志
    _audit_privacy(
        "privacy.export",
        user_id=user_id,
        detail={"username": user.username},
        http_request=http_request,
    )

    # 收集数据
    get_user_store()
    apikey_store = get_apikey_store()
    document_store = get_document_store()
    task_store = get_task_store()

    # API Keys(仅元数据)
    try:
        apikeys = apikey_store.list_by_user(user_id)
        apikeys_data = [
            {
                "id": k.id,
                "scopes": k.scopes,
                "created_at": k.created_at.isoformat() if k.created_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "revoked": k.revoked,
            }
            for k in apikeys
        ]
    except Exception:
        apikeys_data = []

    # 文档
    try:
        docs = document_store.list(user_id=user_id, limit=200)
        docs_data = [d.to_dict() for d in docs]
    except Exception:
        docs_data = []

    # 任务
    try:
        tasks = task_store.list(user_id=user_id, limit=200)
        tasks_data = [t.to_dict() for t in tasks]
    except Exception:
        tasks_data = []

    # 审计日志(本用户最近 100 条)
    audit_data: list[dict] = []
    try:
        from fnixagent.services.storage_audit import get_audit_store

        store = get_audit_store()
        all_logs = store.list_all(limit=10000)
        user_logs = [log.to_dict() for log in all_logs if log.user_id == user_id][:100]
        audit_data = user_logs
    except Exception:
        pass

    # 用户基本信息(包含脱敏手机号)
    profile = dict(user.profile or {})
    phone = profile.get("phone", "")
    masked_phone = ""
    if phone and len(phone) == 11:
        masked_phone = f"{phone[:3]}****{phone[7:]}"

    export_data = {
        "exported_at": datetime.utcnow().isoformat(),
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "phone": masked_phone,
            "quota_total": user.quota_total,
            "quota_used": user.quota_used,
        },
        "api_keys": apikeys_data,
        "documents": docs_data,
        "tasks": tasks_data,
        "audit_logs": audit_data,
    }

    filename = f"fnixagent_export_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    content = json.dumps(export_data, ensure_ascii=False, indent=2, default=str)

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.post("/delete-account")
async def request_account_deletion(
    http_request: Request,
    payload: dict = Depends(verify_jwt_token),
    retention_days: int = _DEFAULT_RETENTION_DAYS,
):
    """注销账号(软删除)。

    行为:
      - 标记 profile.deleted_at = now
      - 标记 profile.hard_delete_at = now + 30 天
      - 立即禁用登录(disabled=True)
      - 30 天保留期内可调用 /privacy/cancel-deletion 撤销
      - 30 天后由后台任务硬删除

    Args:
      retention_days: 保留天数(默认 30,最大 90,最小 1)
    """
    user = _get_user_or_404(payload)
    user_id = user.id

    # 参数校验
    retention_days = max(1, min(90, retention_days))

    # 已注销的不能重复注销
    if user.profile.get("deleted_at"):
        raise HTTPException(status_code=400, detail="账号已处于注销流程中")

    store = get_user_store()
    if not store.soft_delete_user(user_id, retention_days=retention_days):
        raise HTTPException(status_code=500, detail="注销失败")

    _audit_privacy(
        "account.delete_request",
        user_id=user_id,
        detail={
            "username": user.username,
            "retention_days": retention_days,
            "hard_delete_at": (
                datetime.utcnow().replace(microsecond=0).isoformat()
                if retention_days == 0
                else None
            ),
        },
        http_request=http_request,
    )

    return BaseResponse(
        success=True,
        message=f"账号注销请求已提交,将在 {retention_days} 天后永久删除。在此期间可登录撤销注销。",
        data={
            "deleted_at": datetime.utcnow().isoformat(),
            "retention_days": retention_days,
        },
    )


@router.post("/cancel-deletion")
async def cancel_account_deletion(
    http_request: Request,
    payload: dict = Depends(verify_jwt_token),
):
    """撤销账号注销(在 30 天保留期内可恢复)。

    行为:
      - 清除 profile.deleted_at / profile.hard_delete_at
      - 恢复 disabled=False
    """
    user = _get_user_or_404(payload)
    user_id = user.id

    if not user.profile.get("deleted_at"):
        raise HTTPException(status_code=400, detail="账号未在注销流程中")

    store = get_user_store()
    if not store.cancel_soft_delete(user_id):
        raise HTTPException(status_code=500, detail="撤销注销失败")

    _audit_privacy(
        "account.delete_cancel",
        user_id=user_id,
        detail={"username": user.username},
        http_request=http_request,
    )

    return BaseResponse(
        success=True,
        message="账号注销已撤销,您可以正常登录使用了。",
    )


@router.get("/deletion-status")
async def get_deletion_status(payload: dict = Depends(verify_jwt_token)):
    """查询账号注销状态。"""
    user = _get_user_or_404(payload)
    profile = dict(user.profile or {})

    deleted_at = profile.get("deleted_at")
    hard_delete_at = profile.get("hard_delete_at")

    if not deleted_at:
        return BaseResponse(
            success=True,
            data={
                "status": "active",
                "deleted_at": None,
                "hard_delete_at": None,
                "remaining_days": None,
            },
        )

    # 计算剩余天数
    remaining_days = None
    if hard_delete_at:
        try:
            hard_delete_time = datetime.fromisoformat(hard_delete_at)
            now = datetime.utcnow()
            remaining_days = max(0, (hard_delete_time - now).days)
        except (ValueError, TypeError):
            remaining_days = None

    return BaseResponse(
        success=True,
        data={
            "status": "pending_deletion",
            "deleted_at": deleted_at,
            "hard_delete_at": hard_delete_at,
            "remaining_days": remaining_days,
        },
    )
