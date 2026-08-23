"""
工具语义审计层 (Tool Auditor)。

参考 OWASP ASI Top 10 与  三层防御体系的第二层(语义校验),
在 LLM 生成工具调用后、实际执行前插入静态审计:
  - 参数类型不匹配(JSON Schema 校验)
  - 路径越界(.. 跨目录、绝对路径越出 workspace)
  - 敏感操作关键词(delete/remove/drop/truncate/overwrite 等)
  - 风险分级:low(只读)/medium(写入)/high(删除/覆盖)/critical(批量删除)
  - 破坏性操作(destructive=True)强制 need_confirm=True,要求人工确认

设计原则:
  - 独立模块,不修改 office/base.py
  - 所有审计记录写入审计日志(操作者/时间/参数/风险等级/决策)
  - 审计失败不阻断主流程,但降级为 deny(保守策略)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)
_logger = logger


# ---------------------------------------------------------------------------
# 审计钩子
# ---------------------------------------------------------------------------


def _audit_tool_call(
    action: str,
    detail: dict | None = None,
) -> None:
    """将工具审计决策写入审计日志(异常吞掉)。"""
    try:
        from fnixagent.core.audit import AuditLogger

        AuditLogger().log(action=action, detail=detail or {})
    except Exception:
        _logger.debug('Unhandled exception', exc_info=True)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class AuditRecord:
    """单条工具审计记录。

    Attributes:
        timestamp: ISO 时间戳
        tool_name: 工具名
        params: 调用参数(脱敏后)
        risk_level: 风险等级 low/medium/high/critical
        decision: 决策 allow/deny/confirm
        reason: 决策原因
        operator: 操作者(默认 system)
    """

    timestamp: str
    tool_name: str
    params: dict
    risk_level: str  # "low"/"medium"/"high"/"critical"
    decision: str  # "allow"/"deny"/"confirm"
    reason: str
    operator: str = "system"


@dataclass
class AuditReport:
    """工具调用审计报告。

    Attributes:
        allowed: 是否允许执行(need_confirm=True 时为 False)
        risk_level: 整体风险等级(取最高)
        records: 各项审计记录列表
        need_confirm: 是否需要人工确认
        confirm_reason: 需确认原因
    """

    allowed: bool
    risk_level: str
    records: list[AuditRecord] = field(default_factory=list)
    need_confirm: bool = False
    confirm_reason: str | None = None


# ---------------------------------------------------------------------------
# ToolAuditor
# ---------------------------------------------------------------------------


# JSON Schema 类型映射(Python 类型)
_SCHEMA_PY_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list, tuple),
    "object": (dict,),
    "null": (type(None),),
}


class ToolAuditor:
    """工具语义审计器。

    用法:
        auditor = ToolAuditor(workspace_root="/data/workspace")
        report = auditor.audit("delete_file", {"path": "/etc/passwd"})
        if not report.allowed:
            raise PermissionError(report.records[0].reason)
        if report.need_confirm:
            # 触发人工确认流程
            ...
    """

    # 破坏性操作关键词(扫描 params 字符串值)
    DESTRUCTIVE_KEYWORDS: tuple[str, ...] = (
        "delete",
        "remove",
        "drop",
        "truncate",
        "overwrite",
        "rm",
        "rmdir",
        "format",
        "wipe",
        "purge",
    )

    # 批量操作关键词(触发 critical)
    BATCH_KEYWORDS: tuple[str, ...] = (
        "all",
        "batch",
        "bulk",
        "recursive",
        "*",
    )

    # 风险等级排序(便于取最高)
    _RISK_ORDER: tuple[str, ...] = ("low", "medium", "high", "critical")

    def __init__(
        self,
        workspace_root: str | None = None,
    ) -> None:
        self._workspace_root = os.path.realpath(workspace_root) if workspace_root else None
        self._sensitive_tools: dict[str, str] = {}  # tool_name → risk_level
        self._log: list[AuditReport] = []
        self._lock = threading.Lock()

    # -- 公开接口 ----------------------------------------------------------

    def audit(
        self,
        tool_name: str,
        params: dict,
        schema: dict | None = None,
    ) -> AuditReport:
        """审计单次工具调用。

        Args:
            tool_name: 工具名
            params: 调用参数
            schema: 工具参数 JSON Schema(可选,用于类型校验)

        Returns:
            AuditReport:含 allowed/risk_level/records/need_confirm
        """
        records: list[AuditRecord] = []
        now = datetime.now(UTC).isoformat()
        risk = "low"
        need_confirm = False
        confirm_reason: str | None = None

        # 1. 工具级敏感标记
        if tool_name in self._sensitive_tools:
            risk = self._max_risk(risk, self._sensitive_tools[tool_name])
            records.append(
                AuditRecord(
                    timestamp=now,
                    tool_name=tool_name,
                    params=self._safe_params(params),
                    risk_level=risk,
                    decision="confirm",
                    reason=f"工具 {tool_name} 标记为敏感({risk})",
                )
            )
            if risk in ("high", "critical"):
                need_confirm = True
                confirm_reason = f"敏感工具:{tool_name}"

        # 2. 路径越界检测
        path_findings = self._check_path_traversal(tool_name, params)
        for finding in path_findings:
            records.append(finding)
            if finding.decision == "deny":
                risk = self._max_risk(risk, finding.risk_level)
                # 路径越界直接拒绝,不允许确认放行
                report = AuditReport(
                    allowed=False,
                    risk_level=risk,
                    records=records,
                    need_confirm=False,
                    confirm_reason=finding.reason,
                )
                self._append_log(report)
                _audit_tool_call(
                    "tool.audit.deny",
                    detail={
                        "tool": tool_name,
                        "reason": finding.reason,
                    },
                )
                return report

        # 3. 破坏性关键词检测
        destructive_findings = self._check_destructive(tool_name, params)
        for finding in destructive_findings:
            records.append(finding)
            risk = self._max_risk(risk, finding.risk_level)
            if finding.risk_level in ("high", "critical"):
                need_confirm = True
                if confirm_reason is None:
                    confirm_reason = finding.reason

        # 4. 参数类型校验(若提供 schema)
        if schema:
            type_findings = self._check_types(tool_name, params, schema)
            for finding in type_findings:
                records.append(finding)
                if finding.decision == "deny":
                    risk = self._max_risk(risk, finding.risk_level)
                    report = AuditReport(
                        allowed=False,
                        risk_level=risk,
                        records=records,
                        need_confirm=False,
                        confirm_reason=finding.reason,
                    )
                    self._append_log(report)
                    _audit_tool_call(
                        "tool.audit.deny",
                        detail={
                            "tool": tool_name,
                            "reason": finding.reason,
                        },
                    )
                    return report

        # 5. 综合决策
        allowed = not need_confirm
        decision = "allow" if allowed else "confirm"
        if not records:
            records.append(
                AuditRecord(
                    timestamp=now,
                    tool_name=tool_name,
                    params=self._safe_params(params),
                    risk_level=risk,
                    decision=decision,
                    reason="无风险命中,默认放行",
                )
            )
        report = AuditReport(
            allowed=allowed,
            risk_level=risk,
            records=records,
            need_confirm=need_confirm,
            confirm_reason=confirm_reason,
        )
        self._append_log(report)
        _audit_tool_call(
            "tool.audit",
            detail={
                "tool": tool_name,
                "risk": risk,
                "decision": decision,
            },
        )
        return report

    def audit_batch(self, calls: list[dict]) -> AuditReport:
        """批量审计多个工具调用,任一拒绝则整体拒绝。

        Args:
            calls: [{"tool_name", "params", "schema?"}, ...]

        Returns:
            AuditReport:聚合结果(records 包含所有调用的记录)
        """
        all_records: list[AuditRecord] = []
        overall_risk = "low"
        need_confirm = False
        confirm_reason: str | None = None
        blocked = False

        for call in calls:
            tool_name = call.get("tool_name", "")
            params = call.get("params", {}) or {}
            schema = call.get("schema")
            sub = self.audit(tool_name, params, schema=schema)
            all_records.extend(sub.records)
            overall_risk = self._max_risk(overall_risk, sub.risk_level)
            if not sub.allowed:
                # 区分 deny(硬拒绝)与 confirm(可放行)
                if not sub.need_confirm:
                    blocked = True
                    if confirm_reason is None:
                        confirm_reason = sub.confirm_reason or "存在硬拒绝项"
                else:
                    need_confirm = True
                    if confirm_reason is None:
                        confirm_reason = sub.confirm_reason

        allowed = not blocked and not need_confirm
        return AuditReport(
            allowed=allowed,
            risk_level=overall_risk,
            records=all_records,
            need_confirm=need_confirm,
            confirm_reason=confirm_reason,
        )

    def register_sensitive_tool(
        self,
        tool_name: str,
        risk_level: str = "high",
    ) -> None:
        """注册敏感工具(后续 audit 命中时按 risk_level 标记)。"""
        with self._lock:
            self._sensitive_tools[tool_name] = risk_level

    def get_audit_log(self, limit: int = 100) -> list[AuditReport]:
        """返回最近 N 条审计报告。"""
        with self._lock:
            return list(self._log[-limit:])

    # -- 内部:路径越界检测 ------------------------------------------------

    def _check_path_traversal(
        self,
        tool_name: str,
        params: dict,
    ) -> list[AuditRecord]:
        """检测 .. 跨目录与绝对路径越出 workspace。"""
        findings: list[AuditRecord] = []
        now = datetime.now(UTC).isoformat()
        for key, val in params.items():
            if not isinstance(val, str):
                continue
            # 启发式:看起来像路径的字符串(含分隔符或扩展名)
            if not (os.sep in val or "/" in val or "\\" in val or "." in val[-5:]):
                continue
            try:
                rp = os.path.realpath(val)
            except (OSError, ValueError):
                continue
            # 检测 .. 越界
            if ".." in val.replace("\\", "/").split("/"):
                findings.append(
                    AuditRecord(
                        timestamp=now,
                        tool_name=tool_name,
                        params={key: val},
                        risk_level="high",
                        decision="deny",
                        reason=f"参数 {key} 含 '..' 路径越界: {val}",
                    )
                )
                continue
            # 检测绝对路径越出 workspace
            if self._workspace_root and os.path.isabs(val):
                try:
                    rel = os.path.relpath(rp, self._workspace_root)
                    if rel.startswith(".."):
                        findings.append(
                            AuditRecord(
                                timestamp=now,
                                tool_name=tool_name,
                                params={key: val},
                                risk_level="high",
                                decision="deny",
                                reason=f"参数 {key} 越出 workspace: {val}",
                            )
                        )
                except ValueError:
                    # Windows 跨盘符 relpath 抛 ValueError
                    findings.append(
                        AuditRecord(
                            timestamp=now,
                            tool_name=tool_name,
                            params={key: val},
                            risk_level="high",
                            decision="deny",
                            reason=f"参数 {key} 跨盘符访问: {val}",
                        )
                    )
        return findings

    # -- 内部:破坏性关键词检测 -------------------------------------------

    def _check_destructive(
        self,
        tool_name: str,
        params: dict,
    ) -> list[AuditRecord]:
        """扫描参数字符串值中的破坏性关键词,做风险分级。"""
        findings: list[AuditRecord] = []
        now = datetime.now(UTC).isoformat()
        for key, val in params.items():
            if not isinstance(val, str):
                continue
            low = val.lower()
            for kw in self.DESTRUCTIVE_KEYWORDS:
                if not self._match_keyword(low, kw):
                    continue
                # 判断是否批量
                is_batch = any(b in low for b in self.BATCH_KEYWORDS)
                risk = "critical" if is_batch else "high"
                decision = "confirm"
                reason = f"参数 {key} 含破坏性关键词 '{kw}'" + ("(批量)" if is_batch else "")
                findings.append(
                    AuditRecord(
                        timestamp=now,
                        tool_name=tool_name,
                        params={key: val},
                        risk_level=risk,
                        decision=decision,
                        reason=reason,
                    )
                )
                break  # 单参数只记录一次最高风险
        return findings

    @staticmethod
    def _match_keyword(text: str, keyword: str) -> bool:
        """单词边界匹配关键词(避免 delete 误匹配 undeleted)。"""
        pattern = r"\b" + re.escape(keyword) + r"\b"
        return re.search(pattern, text) is not None

    # -- 内部:参数类型校验 -----------------------------------------------

    def _check_types(
        self,
        tool_name: str,
        params: dict,
        schema: dict,
    ) -> list[AuditRecord]:
        """基于 JSON Schema 做基本类型校验。"""
        findings: list[AuditRecord] = []
        now = datetime.now(UTC).isoformat()
        props = schema.get("properties", {}) if isinstance(schema, dict) else {}
        for name, val in params.items():
            spec = props.get(name)
            if not isinstance(spec, dict):
                continue
            json_type = spec.get("type")
            if not json_type:
                continue
            expected_types = _SCHEMA_PY_TYPES.get(json_type)
            if expected_types is None:
                continue
            # bool 是 int 的子类,需特殊处理
            if json_type == "integer" and isinstance(val, bool):
                findings.append(
                    AuditRecord(
                        timestamp=now,
                        tool_name=tool_name,
                        params={name: val},
                        risk_level="medium",
                        decision="deny",
                        reason=f"参数 {name} 期望 integer,实际 boolean",
                    )
                )
                continue
            if not isinstance(val, expected_types):
                findings.append(
                    AuditRecord(
                        timestamp=now,
                        tool_name=tool_name,
                        params={name: val},
                        risk_level="medium",
                        decision="deny",
                        reason=(
                            f"参数 {name} 类型不匹配: 期望 {json_type},实际 {type(val).__name__}"
                        ),
                    )
                )
        return findings

    # -- 辅助 -------------------------------------------------------------

    def _max_risk(self, a: str, b: str) -> str:
        """返回两个风险等级中较高的。"""
        ai = self._RISK_ORDER.index(a) if a in self._RISK_ORDER else 0
        bi = self._RISK_ORDER.index(b) if b in self._RISK_ORDER else 0
        return self._RISK_ORDER[max(ai, bi)]

    def _safe_params(self, params: dict) -> dict:
        """对参数做脱敏(避免敏感值进入审计日志)。"""
        try:
            from fnixagent.core.security.desensitize import Desensitizer

            desensitizer = Desensitizer()
            return {
                k: desensitizer.mask_all(v) if isinstance(v, str) else v for k, v in params.items()
            }
        except Exception:
            # 脱敏失败返回 key 列表(不暴露值)
            return {k: "***" if isinstance(v, str) else v for k, v in params.items()}

    def _append_log(self, report: AuditReport) -> None:
        """追加审计报告到内存日志(线程安全)。"""
        with self._lock:
            self._log.append(report)
            # 防止内存无限增长,保留最近 1000 条
            if len(self._log) > 1000:
                self._log = self._log[-1000:]
