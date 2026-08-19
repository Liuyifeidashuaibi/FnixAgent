"""
PolicyEngine - 权限与能力模型 (Policy Engine & Capability Model)
=================================================================
2026 共识: Agent 必须关进"制度"的笼子。

设计要点:
  - 默认拒绝 (default deny): 未明确允许的操作一律拒绝
  - 最小权限 (least privilege): 只授予完成当前任务所需的最小权限
  - 能力令牌 (capability token): Agent 持有的能力令牌决定可执行的 syscall
  - 可插拔后端: OPA (Rego) / Cedar / 自定义规则引擎

规则评估顺序:
  1. 高危 syscall 检查 (需要特殊能力)
  2. 能力令牌检查 (Agent.capabilities)
  3. 规则匹配 (deny 优先, admin 不短路)
  4. 后端策略评估 (OPA / Cedar)
  5. 默认策略 (按模式):
     - 生产模式: 默认拒绝, 高危操作必须有显式 allow 规则 + 能力令牌
     - 开发模式: 能力检查通过即放行 (含高危, 便于调试)

修复原版 bug:
  - glob 匹配: 实现完整 fnmatch (支持 * 和 ?)
  - subject 匹配: 支持角色映射 (role:admin) 而非仅 PID
  - admin 短路: admin 能力不再绕过 deny 规则
  - 默认拒绝矛盾: 开发/生产模式显式切换
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import fnmatch
from collections.abc import Callable
from dataclasses import dataclass

# SyscallRequest 前向引用 (避免循环导入)
from typing import TYPE_CHECKING, Any

from fnixagent.core.agent.syscall import (
    HIGH_RISK_REQUIRED_CAPS,
    HIGH_RISK_SYSCALLS,
    check_capability,
)
from fnixagent.core.agent.types import PolicyBackend

if TYPE_CHECKING:
    from fnixagent.core.agent.process import AgentProcess
    from fnixagent.core.agent.syscall import SyscallRequest


@dataclass
class PolicyRule:
    """策略规则 (类比 iptables 规则)。

    Attributes:
        action: syscall 名称模式 (如 "fs.*", "llm.complete", "*")
        resource: 资源模式 (如 "/tmp/*", "tool:*")
        subject: 主体模式 (如 "pid:abc123", "role:admin", "*")
        effect: allow / deny
        condition: 条件函数 (可选, 接收 args 返回 bool)
        priority: 规则优先级 (高优先级先评估, 默认 0)
        description: 规则描述 (用于审计)
    """

    action: str = "*"
    resource: str = "*"
    subject: str = "*"
    effect: str = "allow"  # "allow" or "deny"
    condition: Callable[[dict[str, Any]], bool] | None = None
    priority: int = 0
    description: str = ""


class PolicyEngine:
    """策略引擎 (类比 OS 权限 / capability model)。

    2026 共识: Agent 必须关进"制度"的笼子。
    - 默认拒绝 (default deny): 未明确允许的操作一律拒绝
    - 最小权限 (least privilege): 只授予完成当前任务所需的最小权限
    - 能力令牌 (capability token): Agent 持有的能力令牌决定可执行的 syscall
    - 可插拔后端: OPA (Rego) / Cedar / 自定义规则引擎

    模式:
      production: 默认拒绝 (未配置规则时拒绝所有)
      development: 默认允许非高危 (未配置规则时允许非高危, 便于开发)
    """

    def __init__(
        self,
        backend: PolicyBackend | None = None,
        mode: str = "development",
    ):
        self._rules: list[PolicyRule] = []
        self._backend = backend
        self._mode = mode  # "production" or "development"
        # PID → 角色映射 (用于 subject 匹配)
        self._pid_roles: dict[str, set[str]] = {}

    # --- 规则管理 ---

    def add_rule(self, rule: PolicyRule) -> None:
        """添加策略规则。"""
        self._rules.append(rule)
        # 按优先级降序排列 (高优先级先评估)
        self._rules.sort(key=lambda r: -r.priority)

    def remove_rule(self, index: int) -> PolicyRule | None:
        """按索引移除规则。"""
        if 0 <= index < len(self._rules):
            return self._rules.pop(index)
        return None

    def list_rules(self) -> list[dict[str, Any]]:
        """列出所有规则。"""
        return [
            {
                "action": r.action,
                "resource": r.resource,
                "subject": r.subject,
                "effect": r.effect,
                "priority": r.priority,
                "description": r.description,
            }
            for r in self._rules
        ]

    # --- 角色管理 ---

    def assign_role(self, pid: str, role: str) -> None:
        """为进程分配角色 (类比 usermod -aG)。"""
        self._pid_roles.setdefault(pid, set()).add(role)

    def revoke_role(self, pid: str, role: str) -> None:
        """移除进程角色。"""
        if pid in self._pid_roles:
            self._pid_roles[pid].discard(role)
            if not self._pid_roles[pid]:
                del self._pid_roles[pid]

    def get_roles(self, pid: str) -> set[str]:
        """获取进程的所有角色。"""
        return self._pid_roles.get(pid, set()).copy()

    # --- 模式切换 ---

    def set_production_mode(self) -> None:
        """切换到生产模式 (默认拒绝)。"""
        self._mode = "production"

    def set_development_mode(self) -> None:
        """切换到开发模式 (默认允许非高危)。"""
        self._mode = "development"

    @property
    def mode(self) -> str:
        return self._mode

    # --- 授权检查 ---

    @staticmethod
    def _match_pattern(pattern: str, value: str) -> bool:
        """通配符匹配 (使用 fnmatch, 支持 * 和 ?)。

        修复原版 bug:
          - 原版仅处理单个 *, 中间段被忽略
          - 原版未处理 ?
          - 现在使用 fnmatch 完整支持 shell-style glob
        """
        if pattern == "*":
            return True
        return fnmatch.fnmatch(value, pattern)

    def _match_subject(self, pattern: str, pid: str) -> bool:
        """主体匹配 (支持 PID 和角色)。

        修复原版 bug:
          - 原版用 caller_pid (UUID) 匹配 "role:admin", 永不匹配
          - 现在支持 "pid:<UUID>" / "role:<role>" / "<UUID>" / "*" 多种模式
        """
        if pattern == "*":
            return True
        # pid: 前缀
        if pattern.startswith("pid:"):
            return pattern[4:] == pid
        # role: 前缀
        if pattern.startswith("role:"):
            role = pattern[5:]
            return role in self._pid_roles.get(pid, set())
        # 直接 PID 匹配
        return pattern == pid

    def _match_resource(self, pattern: str, args: dict[str, Any]) -> bool:
        """资源匹配 (从 args 提取资源标识)。"""
        if pattern == "*":
            return True
        # 从 args 提取资源 (path / tool / target / memory_id)
        resource = str(
            args.get("path")
            or args.get("tool")
            or args.get("target")
            or args.get("memory_id")
            or ""
        )
        if not resource:
            return pattern == "*"
        return self._match_pattern(pattern, resource)

    async def authorize(
        self,
        req: SyscallRequest,
        process: AgentProcess | None = None,
    ) -> tuple[bool, str]:
        """授权检查 (类比 Linux capability check)。

        Returns:
            (是否允许, 拒绝原因)

        评估顺序:
          1. 高危 syscall 需特殊能力
          2. 能力令牌检查 (admin 不短路, 继续规则匹配)
          3. 规则匹配 (deny 优先, 所有规则都评估)
          4. 后端策略评估 (OPA / Cedar)
          5. 默认策略 (生产: 拒绝 / 开发: 允许非高危)
        """
        syscall = req.syscall

        # 1. 高危 syscall 需特殊能力
        if syscall in HIGH_RISK_SYSCALLS:
            if process is None:
                return False, "高危操作缺少进程上下文"
            caps = process.capabilities
            required_caps = HIGH_RISK_REQUIRED_CAPS.get(syscall, [])
            if required_caps and not any(cap in caps for cap in required_caps):
                return False, f"高危操作 {syscall.value} 需要能力: {required_caps}"

        # 2. 能力令牌检查 (admin 不短路, 继续规则匹配以检查 deny)
        if process:
            if not check_capability(syscall, process.capabilities):
                # 无 admin 能力且能力检查失败 → 拒绝
                if "admin" not in process.capabilities:
                    return False, f"进程 {process.pid} 缺少执行 {syscall.value} 的能力"
                # admin 能力通过, 但仍需检查 deny 规则

        # 3. 规则匹配 (deny 优先, 所有匹配规则都评估)
        # 修复原版 bug: admin 不再短路绕过 deny 规则
        matched_allow = False
        for rule in self._rules:
            if not self._match_pattern(rule.action, syscall.value):
                continue
            if not self._match_subject(rule.subject, req.caller_pid):
                continue
            if not self._match_resource(rule.resource, req.args):
                continue
            # 条件检查
            if rule.condition and not rule.condition(req.args):
                continue
            if rule.effect == "deny":
                return False, f"策略拒绝: {rule.description or rule.action}"
            if rule.effect == "allow":
                matched_allow = True

        # 4. 后端策略评估 (OPA / Cedar)
        if self._backend:
            resource = str(
                req.args.get("path") or req.args.get("tool") or req.args.get("target") or ""
            )
            allowed, reason = await self._backend.evaluate(
                action=syscall.value,
                resource=resource,
                subject=req.caller_pid,
                context=req.args,
            )
            if not allowed:
                return False, f"后端策略拒绝: {reason}"

        # 5. 默认策略
        if matched_allow:
            return True, ""
        # 无 allow 规则匹配, 应用默认策略
        if self._mode == "production":
            # 生产模式: 默认拒绝 (default deny)
            return False, f"默认拒绝: 无 allow 规则匹配 {syscall.value}"
        # 开发模式: 能力检查通过即放行 (含高危, 便于调试)
        # 生产模式下高危操作的强制显式授权在此不生效
        return True, ""

    def get_stats(self) -> dict[str, Any]:
        """策略引擎统计。"""
        return {
            "mode": self._mode,
            "rules_count": len(self._rules),
            "deny_rules": sum(1 for r in self._rules if r.effect == "deny"),
            "allow_rules": sum(1 for r in self._rules if r.effect == "allow"),
            "has_backend": self._backend is not None,
            "tracked_pids": len(self._pid_roles),
        }


__all__ = ["PolicyEngine", "PolicyRule"]
