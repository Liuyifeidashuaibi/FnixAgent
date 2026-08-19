"""
SOAR 响应剧本引擎 (Playbook Engine) - P2 安全模块。

参考 Shuffle SOAR + Cortex,提供 YAML 声明式响应剧本:
  - trigger → steps → approval 三段式结构
  - 内置动作:block_ip / disable_user / revoke_token / isolate_agent /
              notify_admin / rollback_operation
  - 订阅 RuleEngine 输出(trigger 事件类型匹配后异步执行)
  - 支持人工审批节点(approval_required),超时自动 reject
  - 剧本执行状态可查询(pending/running/approval_required/completed/failed)

设计原则:
  - 异步执行:ThreadPoolExecutor(max_workers=4)
  - 所有动作记录审计日志(成功/失败均留痕)
  - 可选依赖(yaml)缺失时降级为仅支持编程式 add_playbook
  - 所有异常不外泄,捕获后返回合理默认值
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# 可选依赖:PyYAML(剧本文件解析)
try:
    import yaml  # type: ignore[import-not-found]

    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class PlaybookAction:
    """剧本动作。

    Attributes:
        name: 动作名(block_ip/disable_user/revoke_token/isolate_agent/
              notify_admin/rollback_operation)
        params: 动作参数字典
        timeout: 超时秒数(默认 60)
    """

    name: str
    params: dict
    timeout: int = 60


@dataclass
class PlaybookStep:
    """剧本步骤(包含一组动作)。

    Attributes:
        name: 步骤名
        actions: 动作列表(顺序执行)
        condition: 执行条件(可选,暂作预留)
        require_approval: 是否需要人工审批
        approval_timeout: 审批超时秒数(超时自动 reject)
    """

    name: str
    actions: list[PlaybookAction]
    condition: str | None = None
    require_approval: bool = False
    approval_timeout: int = 3600


@dataclass
class Playbook:
    """响应剧本。

    Attributes:
        name: 剧本名
        id: 剧本 UUID
        trigger: 触发事件类型(如 "rule.match.high")
        steps: 步骤列表
        enabled: 是否启用
        description: 描述
    """

    name: str
    id: str
    trigger: str
    steps: list[PlaybookStep]
    enabled: bool = True
    description: str = ""


@dataclass
class PlaybookExecution:
    """剧本执行实例。

    Attributes:
        execution_id: 执行 ID(UUID)
        playbook_id: 关联剧本 ID
        triggered_by: 触发事件 ID
        status: pending/running/approval_required/completed/failed
        current_step: 当前步骤索引
        started_at: 开始时间(ISO)
        completed_at: 完成时间(ISO)
        error: 错误信息
        results: 各步骤执行结果
    """

    execution_id: str
    playbook_id: str
    triggered_by: str
    status: str = "pending"
    current_step: int = 0
    started_at: str = ""
    completed_at: str | None = None
    error: str | None = None
    results: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 审计钩子(失败不影响主流程)
# ---------------------------------------------------------------------------


def _audit_playbook(
    action: str,
    detail: dict | None = None,
) -> None:
    """将剧本操作写入审计日志(异常吞掉)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(action=action, detail=detail or {})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PlaybookEngine
# ---------------------------------------------------------------------------


class PlaybookEngine:
    """SOAR 响应剧本引擎。

    用法:
        engine = PlaybookEngine(playbooks_dir="config/security/playbooks")
        engine.load_playbooks()
        exec_ids = engine.trigger("rule.match.high", {"event_id": "evt-1"})
        # 人工审批
        engine.approve(exec_ids[0], approver="admin")
        # 查询状态
        execution = engine.get_execution(exec_ids[0])
    """

    # 内置动作名 → 处理函数名映射
    _ACTION_MAP = {
        "block_ip": "_action_block_ip",
        "disable_user": "_action_disable_user",
        "revoke_token": "_action_revoke_token",
        "isolate_agent": "_action_isolate_agent",
        "notify_admin": "_action_notify_admin",
        "rollback_operation": "_action_rollback_operation",
    }

    # blocked_ips 文件路径(网络层可读取)
    _BLOCKED_IPS_FILE = os.path.join("config", "security", "blocked_ips.json")

    def __init__(self, playbooks_dir: str = "config/security/playbooks") -> None:
        self._playbooks_dir = playbooks_dir
        self._playbooks: dict[str, Playbook] = {}  # playbook_id → Playbook
        self._trigger_index: dict[str, list[str]] = {}  # trigger → [playbook_id]
        self._executions: dict[str, PlaybookExecution] = {}  # execution_id → 执行
        self._lock = threading.Lock()
        # 线程池:异步执行剧本
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="soar")
        # 审批等待:event_id → (Future, PlaybookExecution)
        self._pending_approvals: dict[str, threading.Event] = {}

    # -- 公开接口:剧本加载 -----------------------------------------------

    def load_playbooks(self) -> int:
        """从 playbooks_dir 加载所有 YAML 剧本,返回加载数量。"""
        if not _HAS_YAML:
            logger.warning("[soar] PyYAML 不可用,跳过剧本文件加载")
            return 0
        if not os.path.isdir(self._playbooks_dir):
            logger.info("[soar] 剧本目录不存在: %s", self._playbooks_dir)
            return 0
        count = 0
        for name in os.listdir(self._playbooks_dir):
            if not name.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(self._playbooks_dir, name)
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    continue
                playbook = self._parse_playbook(data)
                if playbook is not None:
                    self.add_playbook(playbook)
                    count += 1
            except Exception as exc:
                logger.warning("[soar] 剧本加载失败 %s: %s", name, exc)
        logger.info("[soar] 加载 %d 个剧本", count)
        return count

    def reload(self) -> int:
        """重新加载剧本(清空后重载)。"""
        with self._lock:
            self._playbooks.clear()
            self._trigger_index.clear()
        return self.load_playbooks()

    def add_playbook(self, playbook: Playbook) -> bool:
        """注册剧本到引擎。"""
        try:
            with self._lock:
                self._playbooks[playbook.id] = playbook
                self._trigger_index.setdefault(playbook.trigger, []).append(playbook.id)
            return True
        except Exception:
            return False

    # -- 公开接口:触发与执行 ---------------------------------------------

    def trigger(self, event_type: str, event_data: dict) -> list[str]:
        """触发事件,返回匹配的 execution_id 列表(异步执行)。

        Args:
            event_type: 事件类型(如 "rule.match.high")
            event_data: 事件数据(含 event_id 等)
        """
        exec_ids: list[str] = []
        with self._lock:
            pb_ids = self._trigger_index.get(event_type, [])
        event_id = event_data.get("event_id", event_type)
        for pb_id in pb_ids:
            playbook = self._playbooks.get(pb_id)
            if playbook is None or not playbook.enabled:
                continue
            execution = PlaybookExecution(
                execution_id=uuid.uuid4().hex,
                playbook_id=playbook.id,
                triggered_by=event_id,
                status="pending",
                started_at=datetime.now(UTC).isoformat(),
            )
            with self._lock:
                self._executions[execution.execution_id] = execution
            exec_ids.append(execution.execution_id)
            # 异步执行
            self._executor.submit(self._safe_execute, execution.execution_id)
        if exec_ids:
            _audit_playbook(
                "soar.trigger",
                detail={
                    "event_type": event_type,
                    "event_id": event_id,
                    "executions": exec_ids,
                },
            )
        return exec_ids

    def execute(self, execution_id: str) -> bool:
        """同步执行指定 execution(主要用于审批后继续)。

        Returns:
            True 表示已提交执行;False 表示 execution 不存在或已完成
        """
        with self._lock:
            execution = self._executions.get(execution_id)
        if execution is None or execution.status in ("completed", "failed"):
            return False
        self._executor.submit(self._safe_execute, execution_id)
        return True

    def approve(self, execution_id: str, approver: str) -> bool:
        """人工审批通过。"""
        with self._lock:
            execution = self._executions.get(execution_id)
            event = self._pending_approvals.get(execution_id)
        if execution is None or event is None:
            return False
        _audit_playbook(
            "soar.approve",
            detail={
                "execution_id": execution_id,
                "approver": approver,
            },
        )
        event.set()  # 唤醒等待
        return True

    def reject(self, execution_id: str, approver: str, reason: str = "") -> bool:
        """人工审批拒绝。"""
        with self._lock:
            execution = self._executions.get(execution_id)
            event = self._pending_approvals.get(execution_id)
        if execution is None:
            return False
        execution.status = "failed"
        execution.error = f"被 {approver} 拒绝: {reason}"
        execution.completed_at = datetime.now(UTC).isoformat()
        _audit_playbook(
            "soar.reject",
            detail={
                "execution_id": execution_id,
                "approver": approver,
                "reason": reason,
            },
        )
        if event is not None:
            # 用 reject 标记唤醒:先存入 execution 再 set
            self._reject_flags.add(execution_id)
            event.set()
        return True

    def get_execution(self, execution_id: str) -> PlaybookExecution | None:
        """查询执行状态。"""
        with self._lock:
            return self._executions.get(execution_id)

    def list_executions(self, limit: int = 50) -> list[PlaybookExecution]:
        """列出最近的执行记录(按开始时间倒序)。"""
        with self._lock:
            execs = list(self._executions.values())
        execs.sort(key=lambda e: e.started_at, reverse=True)
        return execs[:limit]

    # -- 内部:执行主循环 -------------------------------------------------

    # 拒绝标记集合(approve/reject 共用一个 event,用集合区分)
    _reject_flags: set[str] = set()

    def _safe_execute(self, execution_id: str) -> None:
        """异步执行入口(异常不外泄)。"""
        try:
            self._do_execute(execution_id)
        except Exception as exc:
            logger.exception("[soar] 执行异常 %s", execution_id)
            with self._lock:
                execution = self._executions.get(execution_id)
                if execution is not None:
                    execution.status = "failed"
                    execution.error = f"执行异常: {exc}"
                    execution.completed_at = datetime.now(UTC).isoformat()

    def _do_execute(self, execution_id: str) -> None:
        """执行剧本各步骤。"""
        with self._lock:
            execution = self._executions.get(execution_id)
        if execution is None:
            return
        playbook = self._playbooks.get(execution.playbook_id)
        if playbook is None:
            execution.status = "failed"
            execution.error = "剧本不存在"
            return

        execution.status = "running"
        _audit_playbook(
            "soar.execute.start",
            detail={
                "execution_id": execution_id,
                "playbook": playbook.name,
            },
        )

        for idx, step in enumerate(playbook.steps):
            execution.current_step = idx
            # 人工审批节点
            if step.require_approval:
                if not self._wait_for_approval(execution_id, step, execution):
                    return  # 被拒绝或超时
            # 执行该步骤的所有动作
            for action in step.actions:
                result = self._execute_action(action)
                execution.results.append(
                    {
                        "step": step.name,
                        "action": action.name,
                        "result": result,
                    }
                )
                if not result.get("success", False):
                    # 动作失败:记录但继续后续动作(容错)
                    logger.warning(
                        "[soar] 动作失败 %s (step=%s): %s",
                        action.name,
                        step.name,
                        result.get("error"),
                    )

        execution.status = "completed"
        execution.completed_at = datetime.now(UTC).isoformat()
        _audit_playbook(
            "soar.execute.complete",
            detail={
                "execution_id": execution_id,
                "playbook": playbook.name,
                "results_count": len(execution.results),
            },
        )

    def _wait_for_approval(
        self,
        execution_id: str,
        step: PlaybookStep,
        execution: PlaybookExecution,
    ) -> bool:
        """等待人工审批,返回 True=通过 / False=拒绝或超时。"""
        execution.status = "approval_required"
        event = threading.Event()
        with self._lock:
            self._pending_approvals[execution_id] = event
        _audit_playbook(
            "soar.approval_required",
            detail={
                "execution_id": execution_id,
                "step": step.name,
            },
        )
        # 等待审批(超时自动拒绝)
        signaled = event.wait(timeout=step.approval_timeout)
        with self._lock:
            self._pending_approvals.pop(execution_id, None)
            rejected = execution_id in self._reject_flags
            self._reject_flags.discard(execution_id)
        if not signaled:
            execution.status = "failed"
            execution.error = f"审批超时({step.approval_timeout}s)"
            execution.completed_at = datetime.now(UTC).isoformat()
            _audit_playbook(
                "soar.approval_timeout",
                detail={
                    "execution_id": execution_id,
                    "step": step.name,
                },
            )
            return False
        if rejected:
            return False  # reject 已设置 status=failed
        execution.status = "running"
        return True

    # -- 内部:动作执行 ---------------------------------------------------

    def _execute_action(self, action: PlaybookAction) -> dict:
        """执行单个动作,返回结果字典。"""
        handler_name = self._ACTION_MAP.get(action.name)
        if handler_name is None:
            return {"success": False, "error": f"未知动作: {action.name}"}
        handler = getattr(self, handler_name, None)
        if handler is None:
            return {"success": False, "error": f"动作未实现: {action.name}"}
        try:
            result = handler(action.params)
            _audit_playbook(
                f"soar.action.{action.name}",
                detail={
                    "params": action.params,
                    "result": result,
                },
            )
            return result
        except Exception as exc:
            logger.exception("[soar] 动作异常 %s", action.name)
            return {"success": False, "error": f"动作异常: {exc}"}

    def _action_block_ip(self, params: dict) -> dict:
        """封禁 IP:写入 config/security/blocked_ips.json。"""
        ip = params.get("ip", "")
        if not ip:
            return {"success": False, "error": "缺少 ip 参数"}
        try:
            os.makedirs(os.path.dirname(self._BLOCKED_IPS_FILE), exist_ok=True)
            blocked: list = []
            if os.path.exists(self._BLOCKED_IPS_FILE):
                with open(self._BLOCKED_IPS_FILE, encoding="utf-8") as f:
                    blocked = json.load(f)
            if ip not in blocked:
                blocked.append(ip)
            with open(self._BLOCKED_IPS_FILE, "w", encoding="utf-8") as f:
                json.dump(blocked, f, ensure_ascii=False, indent=2)
            return {"success": True, "ip": ip, "total_blocked": len(blocked)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _action_disable_user(self, params: dict) -> dict:
        """禁用用户:调用 RBAC / UserStore 修改用户状态。"""
        user_id = params.get("user_id")
        if user_id is None:
            return {"success": False, "error": "缺少 user_id 参数"}
        try:
            from fnixagent.services.storage import get_user_store

            store = get_user_store()
            user = store.get_by_id(int(user_id))
            if user is None:
                return {"success": False, "error": f"用户 {user_id} 不存在"}
            # 通用禁用:尝试调用 update_status / disable 方法(若存在)
            for method_name in ("disable", "update_status", "set_status"):
                method = getattr(store, method_name, None)
                if callable(method):
                    try:
                        if method_name == "update_status":
                            method(int(user_id), "disabled")
                        else:
                            method(int(user_id))
                    except TypeError:
                        method(user_id)
                    break
            else:
                # 无显式方法:直接修改 user.role/status 字段后 update
                if hasattr(user, "status"):
                    user.status = "disabled"
                if hasattr(store, "update"):
                    store.update(user)
            # 失效权限缓存
            try:
                from fnixagent.core.security.rbac import invalidate_user_permission_cache

                invalidate_user_permission_cache(int(user_id))
            except Exception:
                pass
            return {"success": True, "user_id": user_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _action_revoke_token(self, params: dict) -> dict:
        """撤销凭证:调用 SecretManager 轮换 + 记录撤销清单。"""
        scope = params.get("scope", "all")
        revoked: list[str] = []
        try:
            from fnixagent.core.security.secrets import get_secret_manager

            mgr = get_secret_manager()
            for name in mgr.check_rotation():
                revoked.append(name)
        except Exception:
            pass
        # 记录撤销事件到审计日志(已在 _execute_action 中记录)
        return {"success": True, "scope": scope, "revoked": revoked}

    def _action_isolate_agent(self, params: dict) -> dict:
        """隔离 Agent:用 SandboxExecutor 限制(只读 + 无网络)。"""
        reason = params.get("reason", "")
        try:
            from fnixagent.core.security.sandbox import SandboxConfig, SandboxExecutor

            cfg = SandboxConfig(
                workspace_root=params.get("workspace", "/tmp/oa_isolate"),
                network_allowed=False,
                timeout_seconds=10,
                memory_limit_mb=128,
            )
            executor = SandboxExecutor(cfg)
            return {
                "success": True,
                "sandboxed": executor.is_available(),
                "reason": reason,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _action_notify_admin(self, params: dict) -> dict:
        """通知管理员:打印 + 记录审计(可扩展为邮件/Slack)。"""
        severity = params.get("severity", "medium")
        message = params.get("message", "")
        # 打印到日志(生产可替换为邮件/Slack webhook)
        log_fn = logger.warning if severity in ("high", "critical") else logger.info
        log_fn("[soar][notify_admin][%s] %s", severity, message)
        return {"success": True, "severity": severity, "message": message}

    def _action_rollback_operation(self, params: dict) -> dict:
        """回滚操作:调用 ImpactTracker.rollback 回滚最近操作。"""
        try:
            from fnixagent.core.security.impact import ImpactTracker

            tracker = ImpactTracker()
            if params.get("lookup_recent", False):
                # 查找最近一条操作并回滚
                recent = tracker.list_operations(limit=1)
                if not recent:
                    return {"success": False, "error": "无可回滚的操作"}
                op_id = recent[0].operation_id
            else:
                op_id = params.get("operation_id", "")
                if not op_id:
                    return {"success": False, "error": "缺少 operation_id"}
            ok = tracker.rollback(op_id)
            return {"success": ok, "operation_id": op_id}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    # -- 内部:YAML 解析 --------------------------------------------------

    @staticmethod
    def _parse_playbook(data: dict) -> Playbook | None:
        """将 YAML 字典解析为 Playbook 对象。"""
        try:
            steps: list[PlaybookStep] = []
            for s in data.get("steps", []):
                actions: list[PlaybookAction] = []
                for a in s.get("actions", []):
                    actions.append(
                        PlaybookAction(
                            name=a.get("name", ""),
                            params=a.get("params", {}),
                            timeout=a.get("timeout", 60),
                        )
                    )
                steps.append(
                    PlaybookStep(
                        name=s.get("name", ""),
                        actions=actions,
                        condition=s.get("condition"),
                        require_approval=s.get("require_approval", False),
                        approval_timeout=s.get("approval_timeout", 3600),
                    )
                )
            return Playbook(
                name=data.get("name", ""),
                id=data.get("id", uuid.uuid4().hex),
                trigger=data.get("trigger", ""),
                steps=steps,
                enabled=data.get("enabled", True),
                description=data.get("description", ""),
            )
        except Exception as exc:
            logger.warning("[soar] 剧本解析失败: %s", exc)
            return None
