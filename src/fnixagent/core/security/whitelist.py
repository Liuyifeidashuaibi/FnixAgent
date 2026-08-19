"""
任务粒度工具白名单 (Tool Whitelist) - P1 安全模块。

基于 TaskRouter.classify 返回的 task_type 限制 LLM 可调用的工具集:
  - question_bank  仅允许 Parser/Resolver/RunEditor/FormatNormalizer,禁 Shell
  - document_create 允许 word/excel/ppt/pdf/template 全套
  - document_parse 仅允许 parser/inspector
  - document_convert 仅允许 converter
  - document_format 仅允许 format_normalizer/run_editor
  - shell           默认禁止(空列表)

特性:
  1. deny list 优先于 allow list(全局禁止覆盖一切)
  2. 通配符匹配(用 fnmatch:"word.*" 允许所有 word 子工具)
  3. 临时授权 grant 机制(带过期时间,支持人工授权高危工具)
  4. 线程安全(threading.Lock 保护 grants / deny_list)

设计原则:
  - 默认拒绝:未注册的 task_type 一律 deny
  - 最小权限:每个 task_type 仅暴露必要工具
  - 可审计:WhitelistDecision 含 matched_rule / grant 来源
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import fnmatch
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------------------
# 默认任务-工具映射
# ---------------------------------------------------------------------------

DEFAULT_TASK_TOOLS: dict[str, list[str]] = {
    # 题库任务:仅允许读取/解析/规范化,禁止 Shell
    "question_bank": [
        "parser.*",
        "resolver.*",
        "run_editor.*",
        "format_normalizer.*",
        "word.read",
        "word.edit",
    ],
    # 文档创建:全套 office 工具
    "document_create": ["word.*", "excel.*", "ppt.*", "pdf.*", "template.*"],
    # 文档解析:仅允许解析器与检查器
    "document_parse": ["parser.*", "inspector.*"],
    # 文档转换:仅允许转换器
    "document_convert": ["converter.*"],
    # 文档格式化:仅允许格式化与运行编辑器
    "document_format": ["format_normalizer.*", "run_editor.*"],
    # shell:默认禁止(空列表)
    "shell": [],
}

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ToolGrant:
    """临时工具授权(带过期时间)。

    Attributes:
        tool_pattern: 工具名通配符(如 "word.*" / "shell.exec")
        granted_at:   授权时间(ISO 8601)
        expires_at:   过期时间(ISO 8601)
        reason:       授权原因(审计用)
        granted_by:   授权者(user_id / "system")
    """

    tool_pattern: str
    granted_at: str
    expires_at: str
    reason: str
    granted_by: str


@dataclass
class WhitelistDecision:
    """白名单判定结果。

    Attributes:
        allowed:      是否允许调用
        reason:       判定原因(用于审计/日志)
        matched_rule: 匹配的规则(allow/deny/grant)
        grant:        命中的临时授权(仅 grant 通过时非空)
    """

    allowed: bool
    reason: str
    matched_rule: str | None = None
    grant: ToolGrant | None = None


# ---------------------------------------------------------------------------
# ToolWhitelist
# ---------------------------------------------------------------------------


class ToolWhitelist:
    """任务粒度工具白名单。

    用法:
        wl = ToolWhitelist()
        decision = wl.check("word.edit", "question_bank")
        if decision.allowed:
            ...

        # 临时授权(60 分钟)
        grant = wl.grant("shell.exec", duration_minutes=60, reason="用户确认")
    """

    def __init__(self, task_tools: dict[str, list[str]] | None = None):
        # 深拷贝默认映射,避免修改模块级常量
        self._task_tools: dict[str, list[str]] = {
            k: list(v) for k, v in (task_tools or DEFAULT_TASK_TOOLS).items()
        }
        self._deny_list: list[str] = []
        self._grants: list[ToolGrant] = []
        self._lock = threading.Lock()

    # -- 核心检查 ---------------------------------------------------------

    def check(self, tool_name: str, task_type: str) -> WhitelistDecision:
        """检查单个工具调用是否被允许。

        判定顺序:
          1. deny list 命中 → 直接 deny(优先级最高)
          2. task_type 未注册 → deny(默认拒绝)
          3. allow list 通配匹配 → allow
          4. grant 命中(未过期)→ allow
          5. 都未命中 → deny

        Args:
            tool_name: 工具名(如 "word.edit" / "shell.exec")
            task_type: 任务类型(如 "question_bank")

        Returns:
            WhitelistDecision
        """
        try:
            with self._lock:
                # 1. deny list 优先
                for pat in self._deny_list:
                    if fnmatch.fnmatch(tool_name, pat):
                        return WhitelistDecision(
                            allowed=False,
                            reason=f"工具 {tool_name} 在全局禁止列表(匹配 {pat})",
                            matched_rule="deny",
                        )

                # 2. task_type 未注册 → 默认拒绝
                if task_type not in self._task_tools:
                    return WhitelistDecision(
                        allowed=False,
                        reason=f"task_type {task_type} 未注册,默认拒绝",
                        matched_rule=None,
                    )

                allowed_tools = self._task_tools[task_type]

                # 3. allow list 通配匹配
                for pat in allowed_tools:
                    if fnmatch.fnmatch(tool_name, pat):
                        return WhitelistDecision(
                            allowed=True,
                            reason=f"工具 {tool_name} 匹配 allow 规则 {pat}",
                            matched_rule="allow",
                        )

                # 4. grant 命中(过滤已过期)
                now = datetime.now(UTC)
                for grant in list(self._grants):
                    if self._is_expired(grant, now):
                        # 惰性清理过期 grant
                        self._grants.remove(grant)
                        continue
                    if fnmatch.fnmatch(tool_name, grant.tool_pattern):
                        return WhitelistDecision(
                            allowed=True,
                            reason=(
                                f"工具 {tool_name} 由临时授权通过"
                                f"(granted_by={grant.granted_by}, "
                                f"reason={grant.reason})"
                            ),
                            matched_rule="grant",
                            grant=grant,
                        )

                # 5. 都未命中 → deny
                return WhitelistDecision(
                    allowed=False,
                    reason=(
                        f"工具 {tool_name} 不在 task_type={task_type} 的允许列表 {allowed_tools}"
                    ),
                    matched_rule=None,
                )
        except Exception as e:
            # 异常时降级到拒绝(安全默认)
            return WhitelistDecision(
                allowed=False,
                reason=f"白名单检查异常: {type(e).__name__}: {e}",
                matched_rule=None,
            )

    def check_batch(self, calls: list[dict], task_type: str) -> dict[str, WhitelistDecision]:
        """批量检查工具调用(键为 tool_name,值为判定结果)。

        Args:
            calls: 调用列表,每项含 "tool" 字段(及可选 params)
            task_type: 任务类型

        Returns:
            dict[tool_name, WhitelistDecision]
        """
        result: dict[str, WhitelistDecision] = {}
        for call in calls:
            tool = call.get("tool", "") if isinstance(call, dict) else str(call)
            if tool and tool not in result:
                result[tool] = self.check(tool, task_type)
        return result

    # -- 临时授权管理 -----------------------------------------------------

    def grant(
        self,
        tool_pattern: str,
        duration_minutes: int = 60,
        reason: str = "",
        granted_by: str = "system",
    ) -> ToolGrant:
        """授予临时工具授权(用于人工确认高危工具)。

        Args:
            tool_pattern: 工具名通配符(如 "shell.*")
            duration_minutes: 有效期(分钟),默认 60
            reason: 授权原因(审计)
            granted_by: 授权者

        Returns:
            ToolGrant 实例
        """
        now = datetime.now(UTC)
        expires = now + timedelta(minutes=max(1, duration_minutes))
        grant = ToolGrant(
            tool_pattern=tool_pattern,
            granted_at=now.isoformat(),
            expires_at=expires.isoformat(),
            reason=reason or "临时授权",
            granted_by=granted_by,
        )
        with self._lock:
            self._grants.append(grant)
        return grant

    def revoke(self, tool_pattern: str) -> bool:
        """撤销指定模式的临时授权。

        Args:
            tool_pattern: 要撤销的通配符(精确匹配 grant.tool_pattern)

        Returns:
            是否成功撤销(若不存在返回 False)
        """
        with self._lock:
            before = len(self._grants)
            self._grants = [g for g in self._grants if g.tool_pattern != tool_pattern]
            return len(self._grants) < before

    def list_grants(self) -> list[ToolGrant]:
        """列出当前所有有效授权(已过滤过期)。"""
        with self._lock:
            now = datetime.now(UTC)
            # 惰性清理
            self._grants = [g for g in self._grants if not self._is_expired(g, now)]
            return list(self._grants)

    # -- 任务/规则管理 ----------------------------------------------------

    def register_task(self, task_type: str, allowed_tools: list[str]) -> None:
        """注册新任务类型或覆盖已有任务的工具列表。

        Args:
            task_type: 任务类型名
            allowed_tools: 允许的工具列表(支持通配符)
        """
        with self._lock:
            self._task_tools[task_type] = list(allowed_tools)

    def add_deny(self, tool_pattern: str) -> None:
        """添加全局禁止规则(优先级高于 allow / grant)。

        Args:
            tool_pattern: 工具名通配符(如 "shell.*")
        """
        with self._lock:
            if tool_pattern not in self._deny_list:
                self._deny_list.append(tool_pattern)

    # -- 内部辅助 ---------------------------------------------------------

    @staticmethod
    def _is_expired(grant: ToolGrant, now: datetime) -> bool:
        """检查 grant 是否已过期(异常时视为已过期,安全默认)。"""
        try:
            expires = datetime.fromisoformat(grant.expires_at)
            # 处理 naive datetime(无时区信息时按 UTC 处理)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=UTC)
            return now > expires
        except Exception:
            return True
