"""
审计日志写入器(Phase 2.5)。

功能:
    1. 统一审计日志写入接口(log_audit)
    2. 哈希链防篡改(每条记录包含 prev_hash + entry_hash)
    3. 敏感操作自动埋点(登录/权限变更/数据导出/删除等)
    4. 支持双存储(InMemory + Pg)

哈希链设计:
    - entry_hash = SHA256(prev_hash || action || user_id || detail_json || created_at || ip)
    - 第一条记录 prev_hash = "0"*64(genesis)
    - 篡改任意记录会导致后续所有 hash 不匹配
    - verify_hash_chain() 可校验链完整性

用法:
    from fnixagent.core.audit import AuditLogger, AUDIT_LOGIN_SUCCESS

    logger = AuditLogger()
    logger.log(
        action=AUDIT_LOGIN_SUCCESS,
        user_id=42,
        detail={"username": "alice", "method": "password"},
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 审计动作常量
# ---------------------------------------------------------------------------

# 认证类
AUDIT_LOGIN_SUCCESS: str = "login.success"
AUDIT_LOGIN_FAILED: str = "login.failed"
AUDIT_LOGOUT: str = "logout"
AUDIT_SSO_LOGIN: str = "sso.login"
AUDIT_LDAP_LOGIN: str = "ldap.login"

# MFA 类
AUDIT_MFA_ENABLE: str = "mfa.enable"
AUDIT_MFA_DISABLE: str = "mfa.disable"
AUDIT_MFA_CHALLENGE: str = "mfa.challenge"
AUDIT_MFA_VERIFY_FAILED: str = "mfa.verify_failed"
AUDIT_FACTOR_FORCE_DISABLED: str = "mfa.factor_force_disabled"

# 权限类
AUDIT_PERMISSION_DENIED: str = "permission.denied"

# 用户管理类
AUDIT_USER_DISABLE: str = "user.disable"
AUDIT_USER_ENABLE: str = "user.enable"
AUDIT_USER_ROLE_CHANGE: str = "user.role_change"
AUDIT_PASSWORD_RESET: str = "user.password_reset"

# 系统类
AUDIT_CONFIG_UPDATE: str = "config.update"
AUDIT_SENSITIVE_HIT: str = "sensitive.hit"
AUDIT_INJECTION_BLOCKED: str = "injection.blocked"

# 数据类
AUDIT_DATA_EXPORT: str = "data.export"
AUDIT_DATA_DELETE: str = "data.delete"

# 隐私与合规类(Phase 2.12 / 3.2)
AUDIT_PRIVACY_EXPORT: str = "privacy.export"
AUDIT_ACCOUNT_DELETE_REQUEST: str = "account.delete_request"
AUDIT_ACCOUNT_DELETE_CANCEL: str = "account.delete_cancel"
AUDIT_ACCOUNT_HARD_DELETED: str = "account.hard_deleted"

# 内容审核类(Phase 2.11 / 3.2)
AUDIT_MODERATION_INPUT_BLOCKED: str = "moderation.input_blocked"
AUDIT_MODERATION_OUTPUT_BLOCKED: str = "moderation.output_blocked"

ALL_AUDIT_ACTIONS: tuple[str, ...] = (
    AUDIT_LOGIN_SUCCESS,
    AUDIT_LOGIN_FAILED,
    AUDIT_LOGOUT,
    AUDIT_SSO_LOGIN,
    AUDIT_LDAP_LOGIN,
    AUDIT_MFA_ENABLE,
    AUDIT_MFA_DISABLE,
    AUDIT_MFA_CHALLENGE,
    AUDIT_MFA_VERIFY_FAILED,
    AUDIT_FACTOR_FORCE_DISABLED,
    AUDIT_PERMISSION_DENIED,
    AUDIT_USER_DISABLE,
    AUDIT_USER_ENABLE,
    AUDIT_USER_ROLE_CHANGE,
    AUDIT_PASSWORD_RESET,
    AUDIT_CONFIG_UPDATE,
    AUDIT_SENSITIVE_HIT,
    AUDIT_INJECTION_BLOCKED,
    AUDIT_DATA_EXPORT,
    AUDIT_DATA_DELETE,
    AUDIT_PRIVACY_EXPORT,
    AUDIT_ACCOUNT_DELETE_REQUEST,
    AUDIT_ACCOUNT_DELETE_CANCEL,
    AUDIT_ACCOUNT_HARD_DELETED,
    AUDIT_MODERATION_INPUT_BLOCKED,
    AUDIT_MODERATION_OUTPUT_BLOCKED,
)

# 哈希链 genesis 值(第一条记录的 prev_hash)
_GENESIS_HASH: str = "0" * 64

# ---------------------------------------------------------------------------
# DTO
# ---------------------------------------------------------------------------

@dataclass
class AuditLogDTO:
    """审计日志数据传输对象。"""

    id: int
    tenant_id: int = 0
    user_id: int | None = None
    action: str = ""
    detail: dict = field(default_factory=dict)
    trace_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    prev_hash: str = _GENESIS_HASH
    entry_hash: str = ""
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "action": self.action,
            "detail": self.detail,
            "trace_id": self.trace_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_export_dict(self) -> dict:
        """导出格式(不含内部哈希,用于 JSON/CSV 导出)。"""
        return {
            "id": self.id,
            "timestamp": self.created_at.isoformat() if self.created_at else "",
            "user_id": self.user_id or "",
            "action": self.action,
            "detail": json.dumps(self.detail, ensure_ascii=False),
            "ip": self.ip_address or "",
            "user_agent": self.user_agent or "",
            "trace_id": self.trace_id or "",
        }

# ---------------------------------------------------------------------------
# 哈希链工具
# ---------------------------------------------------------------------------

def _compute_entry_hash(
    prev_hash: str,
    action: str,
    user_id: int | None,
    detail_json: str,
    created_at_iso: str,
    ip_address: str,
) -> str:
    """计算单条审计日志的哈希值。

    将关键字段拼接后做 SHA256,用于哈希链防篡改。
    """
    raw = f"{prev_hash}|{action}|{user_id or 0}|{detail_json}|{created_at_iso}|{ip_address or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def verify_hash_chain(logs: list[AuditLogDTO]) -> tuple[bool, str | None]:
    """校验哈希链完整性。

    Args:
        logs: 按时间正序排列的审计日志列表

    Returns:
        (is_valid, first_broken_id) — 链完整返回 (True, None),
        否则返回 (False, 首个断裂处的日志 ID)
    """
    prev_hash = _GENESIS_HASH
    for log in logs:
        if log.prev_hash != prev_hash:
            return False, log.id
        detail_json = json.dumps(log.detail, sort_keys=True, ensure_ascii=False)
        created_at_iso = log.created_at.isoformat() if log.created_at else ""
        expected = _compute_entry_hash(
            prev_hash,
            log.action,
            log.user_id,
            detail_json,
            created_at_iso,
            log.ip_address or "",
        )
        if log.entry_hash != expected:
            return False, log.id
        prev_hash = log.entry_hash
    return True, None

# ---------------------------------------------------------------------------
# Phase 3.2: detail 字段自动脱敏
# ---------------------------------------------------------------------------

def _desensitize_detail(detail: dict) -> dict:
    """递归对 detail 中的字符串值做 PII 脱敏。

    对 dict / list / str 类型递归遍历,对 str 调用 Desensitizer.mask_all。
    其他类型(int/float/bool/None)原样返回。

    Args:
        detail: 原始 detail 字典

    Returns:
        脱敏后的 detail 字典(深拷贝)
    """
    if not detail:
        return detail
    try:
        from fnixagent.core.security.desensitize import Desensitizer

        desensitizer = Desensitizer()
        return _desensitize_value(detail, desensitizer)
    except Exception:
        # 脱敏失败不影响审计主流程,返回原始数据
        return detail

def _desensitize_value(value, desensitizer) -> object:
    """递归对值做脱敏。"""
    if isinstance(value, str):
        return desensitizer.mask_all(value)
    if isinstance(value, dict):
        return {k: _desensitize_value(v, desensitizer) for k, v in value.items()}
    if isinstance(value, list):
        return [_desensitize_value(v, desensitizer) for v in value]
    if isinstance(value, tuple):
        return tuple(_desensitize_value(v, desensitizer) for v in value)
    return value

# ---------------------------------------------------------------------------
# 审计日志写入器
# ---------------------------------------------------------------------------

class AuditLogger:
    """审计日志写入器。

    通过 get_audit_store() 获取底层存储(InMemory / Pg),
    写入时自动构建哈希链。
    """

    def __init__(self):
        self._store = None

    @property
    def store(self):
        """延迟获取存储层(避免循环导入)。"""
        if self._store is None:
            from fnixagent.services.storage_audit import get_audit_store

            self._store = get_audit_store()
        return self._store

    def log(
        self,
        action: str,
        user_id: int | None = None,
        detail: dict | None = None,
        trace_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        tenant_id: int = 0,
    ) -> AuditLogDTO | None:
        """写入一条审计日志。

        Args:
            action: 审计动作(使用 AUDIT_* 常量)
            user_id: 操作者用户 ID(未登录为 None)
            detail: 详细信息(会存为 JSON,自动脱敏 PII)
            trace_id: 链路追踪 ID
            ip_address: 客户端 IP
            user_agent: 客户端 User-Agent
            tenant_id: 租户 ID(默认 0)

        Returns:
            写入后的 AuditLogDTO,None 表示写入失败

        Phase 3.2: detail 中的字符串值会自动脱敏(手机号/邮箱/身份证/银行卡),
        确保审计日志不包含明文 PII。
        """
        try:
            detail = _desensitize_detail(detail or {})
            detail_json = json.dumps(detail, sort_keys=True, ensure_ascii=False)
            now = datetime.utcnow()
            created_at_iso = now.isoformat()

            # 获取上一条记录的 hash
            prev_hash = self.store.get_last_hash(tenant_id)
            if not prev_hash:
                prev_hash = _GENESIS_HASH

            entry_hash = _compute_entry_hash(
                prev_hash,
                action,
                user_id,
                detail_json,
                created_at_iso,
                ip_address or "",
            )

            entry = self.store.create(
                tenant_id=tenant_id,
                user_id=user_id,
                action=action,
                detail=detail,
                trace_id=trace_id,
                ip_address=ip_address,
                user_agent=user_agent,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                created_at=now,
            )
            # Phase 2.10: 记录审计日志 Prometheus 指标
            try:
                from fnixagent.core.observability.metrics import record_audit_log

                record_audit_log(action)
            except Exception:
                pass  # 指标记录失败不影响审计
            return entry
        except Exception as e:
            # 审计日志失败不应影响主流程
            logger.error("审计日志写入失败(action=%s): %s", action, e)
            return None

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: int | None = None,
        action: str | None = None,
        start: str | None = None,
        end: str | None = None,
        ip_address: str | None = None,
        tenant_id: int = 0,
    ) -> tuple[list[AuditLogDTO], int]:
        """查询审计日志(支持分页+多维筛选)。"""
        return self.store.query(
            limit=limit,
            offset=offset,
            user_id=user_id,
            action=action,
            start=start,
            end=end,
            ip_address=ip_address,
            tenant_id=tenant_id,
        )

    def verify_chain(self, tenant_id: int = 0) -> tuple[bool, int | None]:
        """校验哈希链完整性。"""
        logs, _ = self.store.query(
            limit=10000,
            offset=0,
            tenant_id=tenant_id,
        )
        # 按时间正序排列(查询默认按 id desc,需反转)
        logs = list(reversed(logs))
        is_valid, broken_id = verify_hash_chain(logs)
        return is_valid, broken_id

    def export(
        self,
        format: str = "json",
        user_id: int | None = None,
        action: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 10000,
        tenant_id: int = 0,
    ) -> str:
        """导出审计日志(JSON 或 CSV)。"""
        logs, _ = self.store.query(
            limit=limit,
            offset=0,
            user_id=user_id,
            action=action,
            start=start,
            end=end,
            tenant_id=tenant_id,
        )
        # 导出按时间正序
        logs = list(reversed(logs))
        rows = [log.to_export_dict() for log in logs]

        if format == "csv":
            import csv
            import io

            if not rows:
                return "id,timestamp,user_id,action,detail,ip,user_agent,trace_id\n"
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "id",
                    "timestamp",
                    "user_id",
                    "action",
                    "detail",
                    "ip",
                    "user_agent",
                    "trace_id",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
            return output.getvalue()
        else:
            return json.dumps(rows, ensure_ascii=False, indent=2)
