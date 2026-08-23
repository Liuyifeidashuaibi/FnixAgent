"""ASGI 三道闸门网关模块(P0-01):鉴权 → 配额 → 审计。

在 ASGI 层(最外层)对所有请求(HTTP + WebSocket + 挂载子应用)统一执行:
    1. 鉴权(Auth):  Bearer Token / ?token= 校验 → 写入 Principal
    2. 配额(Quota): 全局并发 + 每 Principal 并发 + 每 Principal QPS
    3. 审计(Audit): 包装 send() 捕获状态码,finally 记录访问日志

导出:
    - GatewayMiddleware: ASGI 三道闸门中间件(包裹整个应用)
    - Principal:         鉴权主体数据类
    - QuotaManager:      配额管理器(并发 + QPS)
    - AuditEntry:        审计记录数据类
    - AuditLogger:       网关审计日志器
    - PUBLIC_PATHS:      公共路径白名单(跳过鉴权,仍审计)
    - get_quota_manager / get_audit_logger: 模块级单例获取

用法:
    from fnixagent.core.gateway import GatewayMiddleware
    app = GatewayMiddleware(app, auth_required=not settings.debug)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.gateway.middleware import (
    PUBLIC_PATHS,
    AuditEntry,
    AuditLogger,
    GatewayMiddleware,
    Principal,
    QuotaManager,
    get_audit_logger,
    get_quota_manager,
)

__all__ = [
    "PUBLIC_PATHS",
    "AuditEntry",
    "AuditLogger",
    "GatewayMiddleware",
    "Principal",
    "QuotaManager",
    "get_audit_logger",
    "get_quota_manager",
]
