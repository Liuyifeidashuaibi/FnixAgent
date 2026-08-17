"""
审计日志核心模块(Phase 2.5)。

导出:
    - AuditLogger: 审计日志写入器(支持哈希链防篡改)
    - 审计动作常量(AUDIT_*)
    - verify_hash_chain: 哈希链完整性校验
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.audit.logger import (
    ALL_AUDIT_ACTIONS,
    AUDIT_ACCOUNT_DELETE_CANCEL,
    AUDIT_ACCOUNT_DELETE_REQUEST,
    AUDIT_ACCOUNT_HARD_DELETED,
    AUDIT_CONFIG_UPDATE,
    AUDIT_DATA_DELETE,
    AUDIT_DATA_EXPORT,
    AUDIT_FACTOR_FORCE_DISABLED,
    AUDIT_INJECTION_BLOCKED,
    AUDIT_LDAP_LOGIN,
    AUDIT_LOGIN_FAILED,
    # 审计动作常量
    AUDIT_LOGIN_SUCCESS,
    AUDIT_LOGOUT,
    AUDIT_MFA_CHALLENGE,
    AUDIT_MFA_DISABLE,
    AUDIT_MFA_ENABLE,
    AUDIT_MFA_VERIFY_FAILED,
    AUDIT_MODERATION_INPUT_BLOCKED,
    AUDIT_MODERATION_OUTPUT_BLOCKED,
    AUDIT_PASSWORD_RESET,
    AUDIT_PERMISSION_DENIED,
    AUDIT_PRIVACY_EXPORT,
    AUDIT_SENSITIVE_HIT,
    AUDIT_SSO_LOGIN,
    AUDIT_USER_DISABLE,
    AUDIT_USER_ENABLE,
    AUDIT_USER_ROLE_CHANGE,
    AuditLogDTO,
    AuditLogger,
    verify_hash_chain,
)

__all__ = [
    "ALL_AUDIT_ACTIONS",
    "AUDIT_ACCOUNT_DELETE_CANCEL",
    "AUDIT_ACCOUNT_DELETE_REQUEST",
    "AUDIT_ACCOUNT_HARD_DELETED",
    "AUDIT_CONFIG_UPDATE",
    "AUDIT_DATA_DELETE",
    "AUDIT_DATA_EXPORT",
    "AUDIT_FACTOR_FORCE_DISABLED",
    "AUDIT_INJECTION_BLOCKED",
    "AUDIT_LDAP_LOGIN",
    "AUDIT_LOGIN_FAILED",
    "AUDIT_LOGIN_SUCCESS",
    "AUDIT_LOGOUT",
    "AUDIT_MFA_CHALLENGE",
    "AUDIT_MFA_DISABLE",
    "AUDIT_MFA_ENABLE",
    "AUDIT_MFA_VERIFY_FAILED",
    "AUDIT_MODERATION_INPUT_BLOCKED",
    "AUDIT_MODERATION_OUTPUT_BLOCKED",
    "AUDIT_PASSWORD_RESET",
    "AUDIT_PERMISSION_DENIED",
    "AUDIT_PRIVACY_EXPORT",
    "AUDIT_SENSITIVE_HIT",
    "AUDIT_SSO_LOGIN",
    "AUDIT_USER_DISABLE",
    "AUDIT_USER_ENABLE",
    "AUDIT_USER_ROLE_CHANGE",
    "AuditLogDTO",
    "AuditLogger",
    "verify_hash_chain",
]
