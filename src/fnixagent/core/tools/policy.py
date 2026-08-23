"""Tool execution policy — risk, approval, idempotency, audit summary.

All tool calls (ToolExecutor + ToolRegistry.execute) should pass through
``ToolPolicy.evaluate`` before side effects.
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolRisk(str, Enum):
    READ = "read"  # list/search/read — no side effects
    WRITE = "write"  # create/edit files, office write
    NETWORK = "network"  # outbound HTTP / LLM / MCP
    SHELL = "shell"  # process / terminal
    DESTRUCTIVE = "destructive"  # delete, rm, format, force-push


# Name → risk (longest-match / exact). Unknown tools default to WRITE.
_RISK_BY_NAME: dict[str, ToolRisk] = {
    "read_file": ToolRisk.READ,
    "read_lines": ToolRisk.READ,
    "list_dir": ToolRisk.READ,
    "list_directory": ToolRisk.READ,
    "ls": ToolRisk.READ,
    "ll": ToolRisk.READ,
    "search": ToolRisk.READ,
    "search_code": ToolRisk.READ,
    "search_project": ToolRisk.READ,
    "grep": ToolRisk.READ,
    "glob": ToolRisk.READ,
    "get_context": ToolRisk.READ,
    "write_file": ToolRisk.WRITE,
    "edit_file": ToolRisk.WRITE,
    "create_file": ToolRisk.WRITE,
    "apply_patch": ToolRisk.WRITE,
    "apply_multi_patch": ToolRisk.WRITE,
    "run_terminal": ToolRisk.SHELL,
    "run_command": ToolRisk.SHELL,
    "shell": ToolRisk.SHELL,
    "bash": ToolRisk.SHELL,
    "execute": ToolRisk.SHELL,
    "delete_path": ToolRisk.DESTRUCTIVE,
    "delete_file": ToolRisk.DESTRUCTIVE,
    "rm": ToolRisk.DESTRUCTIVE,
    "remove": ToolRisk.DESTRUCTIVE,
}

_NAME_PREFIX_RISK: list[tuple[str, ToolRisk]] = [
    ("read_", ToolRisk.READ),
    ("list_", ToolRisk.READ),
    ("search_", ToolRisk.READ),
    ("get_", ToolRisk.READ),
    ("write_", ToolRisk.WRITE),
    ("edit_", ToolRisk.WRITE),
    ("create_", ToolRisk.WRITE),
    ("apply_", ToolRisk.WRITE),
    ("run_", ToolRisk.SHELL),
    ("exec_", ToolRisk.SHELL),
    ("delete_", ToolRisk.DESTRUCTIVE),
    ("remove_", ToolRisk.DESTRUCTIVE),
]


@dataclass
class PolicyDecision:
    allowed: bool
    risk: ToolRisk
    reason: str = ""
    requires_approval: bool = False
    idempotency_key: str = ""
    cached_result: Any = None
    summary: str = ""


@dataclass
class PolicyAuditEntry:
    tool: str
    risk: ToolRisk
    allowed: bool
    reason: str
    idempotency_key: str
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


def classify_risk(tool_name: str) -> ToolRisk:
    name = (tool_name or "").strip().lower()
    if name in _RISK_BY_NAME:
        return _RISK_BY_NAME[name]
    for prefix, risk in _NAME_PREFIX_RISK:
        if name.startswith(prefix):
            return risk
    # MCP / unknown connectors often hit network
    if name.startswith("mcp_") or "http" in name or "fetch" in name:
        return ToolRisk.NETWORK
    return ToolRisk.WRITE


def make_idempotency_key(tool_name: str, arguments: dict[str, Any] | None) -> str:
    payload = {"name": tool_name, "args": arguments or {}}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class ToolPolicy:
    """Gate + idempotency cache for tool side effects."""

    def __init__(
        self,
        *,
        auto_approve_high: bool | None = None,
        idempotency_ttl_sec: float = 120.0,
        max_cache: int = 256,
    ) -> None:
        if auto_approve_high is None:
            env = (os.getenv("FNIX_TOOL_AUTO_APPROVE") or "").strip().lower()
            if env in {"1", "true", "yes", "on"}:
                auto_approve_high = True
            elif env in {"0", "false", "no", "off"}:
                auto_approve_high = False
            else:
                # standalone 模式下无人工审批通道, SHELL/DESTRUCTIVE 默认放行
                # 云端/生产模式仍保持 fail-closed
                try:
                    from fnixagent.core.profile import is_standalone

                    auto_approve_high = is_standalone()
                except Exception:
                    auto_approve_high = False
        self.auto_approve_high = auto_approve_high
        self.idempotency_ttl_sec = idempotency_ttl_sec
        self._max_cache = max_cache
        self._cache: dict[str, tuple[float, Any]] = {}
        self._audit: list[PolicyAuditEntry] = []
        self._lock = threading.Lock()
        # Explicit one-shot approvals: idempotency_key → True
        self._approvals: set[str] = set()

    def approve(self, idempotency_key: str) -> None:
        with self._lock:
            self._approvals.add(idempotency_key)

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        approved: bool = False,
    ) -> PolicyDecision:
        args = dict(arguments or {})
        # Strip control flags from risk hashing payload later
        approved = approved or bool(args.pop("_approved", False))
        risk = classify_risk(tool_name)
        key = make_idempotency_key(tool_name, args)
        # B5：只读工具不做幂等缓存（结果上下文相关，缓存会跨任务串号）
        cacheable = self.should_cache_result(tool_name)

        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                ts, value = cached
                if time.time() - ts <= self.idempotency_ttl_sec:
                    if cacheable:
                        return PolicyDecision(
                            allowed=True,
                            risk=risk,
                            reason="idempotent_cache_hit",
                            idempotency_key=key,
                            cached_result=value,
                            summary=f"{tool_name}:{risk.value}:cache_hit",
                        )
                    # 只读工具即使有残留缓存也不命中，删除脏缓存
                    del self._cache[key]
                else:
                    del self._cache[key]

        requires = risk in {ToolRisk.SHELL, ToolRisk.DESTRUCTIVE}
        if requires and not (approved or self.auto_approve_high or key in self._approvals):
            decision = PolicyDecision(
                allowed=False,
                risk=risk,
                reason="approval_required",
                requires_approval=True,
                idempotency_key=key,
                summary=f"{tool_name}:{risk.value}:blocked",
            )
            self._record(tool_name, decision)
            return decision

        decision = PolicyDecision(
            allowed=True,
            risk=risk,
            reason="ok",
            requires_approval=False,
            idempotency_key=key,
            summary=f"{tool_name}:{risk.value}:allow",
        )
        self._record(tool_name, decision)
        return decision

    def remember_success(
        self,
        idempotency_key: str,
        result: Any,
        tool_name: str = "",
    ) -> None:
        if not idempotency_key:
            return
        # B5：只读工具结果禁止进入幂等缓存（结果上下文相关，缓存会跨任务串号）。
        # 双保险：即便调用方漏判，这里也拦截。
        if tool_name and not self.should_cache_result(tool_name):
            return
        with self._lock:
            if len(self._cache) >= self._max_cache:
                # Drop oldest ~25%
                items = sorted(self._cache.items(), key=lambda kv: kv[1][0])
                for k, _ in items[: max(1, self._max_cache // 4)]:
                    self._cache.pop(k, None)
            self._cache[idempotency_key] = (time.time(), result)
            self._approvals.discard(idempotency_key)

    def should_cache_result(self, tool_name: str) -> bool:
        """判断工具结果是否应进入幂等缓存。

        B5 修复：仅缓存**有副作用**的工具结果（WRITE/SHELL/DESTRUCTIVE/NETWORK），
        用于防止同一参数在短时间内的重复副作用执行。

        只读工具（READ，如 ls/read_file/grep/glob）**禁止缓存**：
        - 它们的结果依赖当前工作区/文件系统状态，是上下文相关的
        - 全局缓存会让并发/后续任务命中其他任务的路径结果，导致工作区串号
          （实测：task-7 的 ls 结果被 task-8 命中，agent 看到错误的目录内容）
        """
        try:
            from fnixagent.core.tools.policy import classify_risk

            return classify_risk(tool_name) != ToolRisk.READ
        except Exception:
            # 兜底：无法判定风险时保守不缓存（宁可多执行一次，不串号）
            return False

    def recent_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._audit[-limit:]
        return [
            {
                "tool": e.tool,
                "risk": e.risk.value,
                "allowed": e.allowed,
                "reason": e.reason,
                "idempotency_key": e.idempotency_key,
                "timestamp": e.timestamp,
            }
            for e in rows
        ]

    def _record(self, tool_name: str, decision: PolicyDecision) -> None:
        with self._lock:
            self._audit.append(
                PolicyAuditEntry(
                    tool=tool_name,
                    risk=decision.risk,
                    allowed=decision.allowed,
                    reason=decision.reason,
                    idempotency_key=decision.idempotency_key,
                )
            )
            if len(self._audit) > 500:
                self._audit = self._audit[-250:]


_DEFAULT_POLICY: ToolPolicy | None = None
_POLICY_LOCK = threading.Lock()


def get_tool_policy() -> ToolPolicy:
    global _DEFAULT_POLICY
    with _POLICY_LOCK:
        if _DEFAULT_POLICY is None:
            _DEFAULT_POLICY = ToolPolicy()
        return _DEFAULT_POLICY


def reset_tool_policy_for_tests() -> ToolPolicy:
    global _DEFAULT_POLICY
    with _POLICY_LOCK:
        _DEFAULT_POLICY = ToolPolicy(auto_approve_high=True)
        return _DEFAULT_POLICY
