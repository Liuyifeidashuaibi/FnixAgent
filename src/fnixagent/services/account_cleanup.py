"""
账号注销清理调度器(Phase 3.2)。

后台线程每 6 小时检查一次,对所有已过保留期的软删除用户执行硬删除。

启动方式:
    from fnixagent.services.account_cleanup import start_cleanup_scheduler
    start_cleanup_scheduler()  # 在应用启动事件中调用

停止方式:
    stop_cleanup_scheduler()   # 在应用关闭事件中调用
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)
_logger = logger

_cleanup_thread: threading.Thread | None = None
_cleanup_stop_event = threading.Event()
_CHECK_INTERVAL_SECONDS = 6 * 3600  # 每 6 小时检查一次


def _cleanup_loop() -> None:
    """清理循环(后台线程)。"""
    logger.info("账号注销清理调度器已启动")
    while not _cleanup_stop_event.is_set():
        try:
            _run_cleanup()
        except Exception as e:
            logger.error("账号清理调度异常: %s", e)
        _cleanup_stop_event.wait(_CHECK_INTERVAL_SECONDS)
    logger.info("账号注销清理调度器已停止")


def _run_cleanup() -> None:
    """执行一次清理:对所有已过保留期的软删除用户硬删除。"""
    from fnixagent.services.storage import get_user_store

    store = get_user_store()
    candidates = store.get_users_to_hard_delete()
    if not candidates:
        return

    logger.info("发现 %d 个待硬删除用户,开始清理", len(candidates))

    for user in candidates:
        try:
            if store.hard_delete_user(user.id):
                logger.info("用户 %s (id=%d) 已硬删除", user.username, user.id)
                # 写入审计日志
                try:
                    from fnixagent.core.audit import AUDIT_ACCOUNT_HARD_DELETED, AuditLogger

                    AuditLogger().log(
                        action=AUDIT_ACCOUNT_HARD_DELETED,
                        user_id=user.id,
                        detail={
                            "username": user.username,
                            "email": user.email,
                            "deleted_at": user.profile.get("deleted_at"),
                        },
                    )
                except Exception:
                    _logger.debug('Unhandled exception', exc_info=True)
        except Exception as e:
            logger.error("硬删除用户 %d 失败: %s", user.id, e)


def start_cleanup_scheduler() -> None:
    """启动清理调度器(后台守护线程)。"""
    global _cleanup_thread
    if _cleanup_thread is not None and _cleanup_thread.is_alive():
        return  # 已启动
    _cleanup_stop_event.clear()
    _cleanup_thread = threading.Thread(
        target=_cleanup_loop,
        name="account-cleanup",
        daemon=True,
    )
    _cleanup_thread.start()


def stop_cleanup_scheduler() -> None:
    """停止清理调度器。"""
    global _cleanup_thread
    if _cleanup_thread is None:
        return
    _cleanup_stop_event.set()
    _cleanup_thread.join(timeout=5)
    _cleanup_thread = None
