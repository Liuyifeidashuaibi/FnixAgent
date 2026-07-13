"""
LDAP 定时同步任务(Phase 2.2)。

后台线程每 1 小时检查一次,若距上次同步超过 sync_interval_hours(默认 24h),
则自动触发 LDAP 用户同步。

启动方式:
    from officeagent.core.security.auth.ldap_sync import start_ldap_sync_scheduler
    start_ldap_sync_scheduler()  # 在应用启动事件中调用

停止方式:
    stop_ldap_sync_scheduler()  # 在应用关闭事件中调用
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

_sync_thread: threading.Thread | None = None
_sync_stop_event = threading.Event()
_CHECK_INTERVAL_SECONDS = 3600  # 每小时检查一次


def _sync_loop() -> None:
    """同步循环(后台线程)。"""
    logger.info("LDAP 同步调度器已启动")
    while not _sync_stop_event.is_set():
        try:
            _run_due_syncs()
        except Exception as e:
            logger.error("LDAP 同步调度异常: %s", e)
        # 等待下次检查(或停止信号)
        _sync_stop_event.wait(_CHECK_INTERVAL_SECONDS)
    logger.info("LDAP 同步调度器已停止")


def _run_due_syncs() -> None:
    """检查所有 LDAP 配置,对到期的执行同步。"""
    from officeagent.core.security.auth.ldap import LDAPClient, LDAPError, LDAPNotInstalledError
    from officeagent.services.storage_ldap import get_ldap_config_store

    store = get_ldap_config_store()
    configs = store.list_configs(include_inactive=False)
    now = datetime.utcnow()

    for cfg in configs:
        # 判断是否到期
        if cfg.last_sync_at:
            next_sync = cfg.last_sync_at + timedelta(hours=cfg.sync_interval_hours)
            if now < next_sync:
                continue  # 未到期,跳过

        logger.info("开始同步 LDAP 配置: %s (id=%s)", cfg.name, cfg.id)
        try:
            client = LDAPClient(cfg.to_ldap_config())
            stats = client.sync_users_to_local()
            store.mark_synced(cfg.id)
            logger.info(
                "LDAP 同步完成: %s - 创建 %d, 更新 %d, 跳过 %d",
                cfg.name, stats["created"], stats["updated"], stats["skipped"],
            )
        except LDAPNotInstalledError:
            logger.warning("ldap3 未安装,跳过 LDAP 同步")
            break  # 没装 ldap3,所有配置都会失败,直接退出
        except LDAPError as e:
            logger.error("LDAP 同步失败 (%s): %s", cfg.name, e)
        except Exception as e:
            logger.error("LDAP 同步异常 (%s): %s", cfg.name, e)


def start_ldap_sync_scheduler() -> None:
    """启动 LDAP 同步调度器(非阻塞)。"""
    global _sync_thread
    if _sync_thread is not None and _sync_thread.is_alive():
        return  # 已在运行
    _sync_stop_event.clear()
    _sync_thread = threading.Thread(target=_sync_loop, daemon=True, name="ldap-sync")
    _sync_thread.start()


def stop_ldap_sync_scheduler() -> None:
    """停止 LDAP 同步调度器。"""
    global _sync_thread
    if _sync_thread is None:
        return
    _sync_stop_event.set()
    _sync_thread.join(timeout=5)
    _sync_thread = None
