"""人工确认节点(Phase 6.2)。

OfficeAgent 任务引擎的安全护栏:高风险操作(批量删除/覆盖原文件/加密)
执行前必须经过人工确认;低风险操作可自动批准;确认请求有超时机制。

设计借鉴:电商客服翻车教训——"能做≠应做,人工审核节点不能省"。

风险等级:
  SAFE   — 只读/新建文件
  LOW    — 修改副本,不影响原文件
  MEDIUM — 修改原文件但可撤销(如格式统一)
  HIGH   — 不可逆操作(删除段落/批量删除/覆盖/加密)

状态机:
  合法状态:pending / approved / rejected / expired
  合法转移:
    pending → approved | rejected | expired
    approved / rejected / expired → (终态,不可再转移)
  approve/reject 仅在 pending 状态合法;已审批/已过期/已拒绝的请求再次操作将被拒绝。

审计:
  所有确认操作(创建/批准/拒绝/过期)均通过 print 输出审计日志,
  实际可替换为 officeagent.core.audit.logger。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from officeagent.office.base import BaseExpert, ExpertResult


# ---------------------------------------------------------------------------
# 风险等级
# ---------------------------------------------------------------------------


class RiskLevel(Enum):
    """操作风险等级。

    数值越大风险越高(用于比较与阈值判断)。
    """

    SAFE = "safe"        # 只读/新建文件
    LOW = "low"          # 修改副本,不影响原文件
    MEDIUM = "medium"    # 修改原文件但可撤销(如格式统一)
    HIGH = "high"        # 不可逆操作(删除段落/批量删除/覆盖/加密)


# 风险等级→数值映射,数值越大风险越高
_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.SAFE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
}


# 高风险关键词(小写匹配,命中即判 HIGH)
_HIGH_RISK_KEYWORDS: frozenset[str] = frozenset({
    "删除", "delete", "del", "remove", "rm",
    "覆盖", "overwrite", "overwirte", "replace_file",
    "加密", "encrypt", "encryption",
    "清空", "clear", "truncate",
    "格式化", "format",
})

# 批量关键词(命中提升一级风险,封顶 HIGH)
_BATCH_KEYWORDS: frozenset[str] = frozenset({
    "批量", "batch", "bulk", "all", "全部", "所有",
})


def _bump_up(level: RiskLevel) -> RiskLevel:
    """风险等级提升一级(封顶 HIGH)。"""
    order = _RISK_ORDER[level]
    if order >= _RISK_ORDER[RiskLevel.HIGH]:
        return RiskLevel.HIGH
    for lvl, ord_ in _RISK_ORDER.items():
        if ord_ == order + 1:
            return lvl
    return RiskLevel.HIGH


# ---------------------------------------------------------------------------
# 确认请求
# ---------------------------------------------------------------------------


@dataclass
class ConfirmationRequest:
    """人工确认请求。

    Attributes:
        request_id: 请求唯一 ID(uuid)
        task_id: 所属任务 ID
        risk_level: 风险等级
        action_desc: 操作描述(中文)
        affected_files: 受影响文件列表
        irreversible: 是否不可逆
        estimated_impact: 预估影响(如"删除145个段落")
        created_at: 创建时间
        status: 状态 pending / approved / rejected / expired
        decided_at: 决策时间(批准/拒绝/过期时写入)
        decided_by: 决策者(user/auto/system)
        reason: 批准/拒绝理由
    """

    request_id: str
    task_id: str
    risk_level: RiskLevel
    action_desc: str
    affected_files: list[str]
    irreversible: bool
    estimated_impact: str
    created_at: datetime
    status: str = "pending"            # pending / approved / rejected / expired
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# HumanConfirmer
# ---------------------------------------------------------------------------


class HumanConfirmer(BaseExpert):
    """人工确认节点。

    高风险操作必须显式 approve 才能执行;
    低风险(<=auto_approve_threshold)可自动批准;
    确认请求有超时机制(默认 60 分钟过期)。

    所有确认操作记录审计日志(用 print 模拟,实际可接 audit logger)。

    用法:
        c = HumanConfirmer()
        risk = c.assess_risk("删除所有答案行", [{"op": "delete"}], ["a.docx"])
        if c.should_confirm(risk):
            req = c.request_confirmation("t1", "删除答案行", ["a.docx"], risk, "删除145个段落")
            # ... 等待人工 approve / reject ...
    """

    @property
    def name(self) -> str:
        return "human_confirmer"

    def __init__(self) -> None:
        # 待确认请求池(含所有状态,便于审计查询)
        self._pending: dict[str, ConfirmationRequest] = {}
        # 自动批准阈值:风险 <= 此值则自动批准
        self._auto_approve_threshold: RiskLevel = RiskLevel.LOW

    # ------------------------------------------------------------------
    # 风险评估
    # ------------------------------------------------------------------

    def assess_risk(
        self,
        task_desc: str,
        ops: list[dict],
        affected_files: list[str],
    ) -> RiskLevel:
        """评估操作风险等级。

        评估规则(逐级提升,封顶 HIGH):
          1. 命中高风险关键词(删除/覆盖/加密/清空/格式化)→ HIGH
          2. 命中批量关键词(批量/全部/所有)→ 提升一级
          3. 受影响文件数 > 10 → 提升一级
          4. ops 中显式标记 irreversible=True → HIGH

        Args:
            task_desc: 任务描述(中文/英文)
            ops: 操作列表,每项为 dict(可含 op/action/desc/description/type/irreversible 字段)
            affected_files: 受影响文件列表

        Returns:
            RiskLevel
        """
        # 拼接所有文本用于关键词扫描(小写)
        desc_text = task_desc or ""
        for op in ops or []:
            if not isinstance(op, dict):
                continue
            for k in ("op", "action", "desc", "description", "type"):
                v = op.get(k)
                if isinstance(v, str):
                    desc_text += " " + v
        text = desc_text.lower()

        risk = RiskLevel.SAFE

        # 1) 高风险关键词 → HIGH
        if any(kw in text for kw in _HIGH_RISK_KEYWORDS):
            risk = RiskLevel.HIGH

        # 2) 批量关键词 → 提升一级
        if any(kw in text for kw in _BATCH_KEYWORDS):
            risk = _bump_up(risk)

        # 3) 文件数 > 10 → 提升一级
        if len(affected_files or []) > 10:
            risk = _bump_up(risk)

        # 4) ops 中显式标记 irreversible → HIGH
        for op in ops or []:
            if isinstance(op, dict) and op.get("irreversible"):
                risk = RiskLevel.HIGH
                break

        return risk

    # ------------------------------------------------------------------
    # 确认请求管理
    # ------------------------------------------------------------------

    def should_confirm(self, risk_level: RiskLevel) -> bool:
        """是否需要人工确认。

        规则:风险等级 > auto_approve_threshold 时需要确认。

        Args:
            risk_level: 风险等级

        Returns:
            True 表示需要人工确认
        """
        return _RISK_ORDER[risk_level] > _RISK_ORDER[self._auto_approve_threshold]

    def auto_approve(self, request: ConfirmationRequest) -> bool:
        """低风险自动批准。

        规则:风险等级 <= auto_approve_threshold 时可自动批准。

        Args:
            request: 确认请求

        Returns:
            True 表示可自动批准
        """
        return not self.should_confirm(request.risk_level)

    def request_confirmation(
        self,
        task_id: str,
        action_desc: str,
        affected_files: list[str],
        risk_level: RiskLevel,
        estimated_impact: str = "",
    ) -> ConfirmationRequest:
        """创建确认请求。

        若风险等级 <= auto_approve_threshold,自动批准并返回 approved 状态的请求;
        否则返回 pending 状态,等待人工 approve/reject。

        Args:
            task_id: 任务 ID
            action_desc: 操作描述(中文)
            affected_files: 受影响文件列表
            risk_level: 风险等级
            estimated_impact: 预估影响(如"删除145个段落")

        Returns:
            ConfirmationRequest(status=approved 或 pending)
        """
        req = ConfirmationRequest(
            request_id=f"cf-{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            risk_level=risk_level,
            action_desc=action_desc,
            affected_files=list(affected_files or []),
            irreversible=(risk_level == RiskLevel.HIGH),
            estimated_impact=estimated_impact,
            created_at=datetime.now(),
        )
        self._pending[req.request_id] = req

        # 尝试自动批准(低风险)
        if self.auto_approve(req):
            req.status = "approved"
            req.decided_at = datetime.now()
            req.decided_by = "auto"
            req.reason = "auto-approved: risk <= threshold"
            print(
                f"[audit] confirmation auto-approved: id={req.request_id} "
                f"task={task_id} risk={risk_level.value}"
            )
        else:
            print(
                f"[audit] confirmation pending: id={req.request_id} "
                f"task={task_id} risk={risk_level.value} desc={action_desc} "
                f"impact={estimated_impact}"
            )
        return req

    def approve(
        self,
        request_id: str,
        decided_by: str = "user",
        reason: str = "",
    ) -> ExpertResult:
        """批准确认请求。

        仅 pending 状态可批准;其他状态返回失败。

        Args:
            request_id: 请求 ID
            decided_by: 决策者(默认 "user")
            reason: 批准理由

        Returns:
            ExpertResult(output=request_id, metadata={status, risk_level, task_id})
        """
        req = self._pending.get(request_id)
        if req is None:
            return self._failure(f"confirmation request not found: {request_id}")
        if req.status != "pending":
            return self._failure(
                f"cannot approve: request {request_id} is in '{req.status}' state "
                f"(终态,不可再转移)"
            )
        req.status = "approved"
        req.decided_at = datetime.now()
        req.decided_by = decided_by
        req.reason = reason
        print(
            f"[audit] confirmation approved: id={request_id} "
            f"by={decided_by} reason={reason}"
        )
        return self._success(
            request_id,
            status="approved",
            risk_level=req.risk_level.value,
            task_id=req.task_id,
        )

    def reject(
        self,
        request_id: str,
        decided_by: str = "user",
        reason: str = "",
    ) -> ExpertResult:
        """拒绝确认请求。

        仅 pending 状态可拒绝;其他状态返回失败。

        Args:
            request_id: 请求 ID
            decided_by: 决策者(默认 "user")
            reason: 拒绝理由

        Returns:
            ExpertResult(output=request_id, metadata={status, risk_level, task_id})
        """
        req = self._pending.get(request_id)
        if req is None:
            return self._failure(f"confirmation request not found: {request_id}")
        if req.status != "pending":
            return self._failure(
                f"cannot reject: request {request_id} is in '{req.status}' state "
                f"(终态,不可再转移)"
            )
        req.status = "rejected"
        req.decided_at = datetime.now()
        req.decided_by = decided_by
        req.reason = reason
        print(
            f"[audit] confirmation rejected: id={request_id} "
            f"by={decided_by} reason={reason}"
        )
        return self._success(
            request_id,
            status="rejected",
            risk_level=req.risk_level.value,
            task_id=req.task_id,
        )

    def list_pending(self) -> list[ConfirmationRequest]:
        """列出所有待确认(status=pending)请求。"""
        return [r for r in self._pending.values() if r.status == "pending"]

    def get_status(self, request_id: str) -> Optional[ConfirmationRequest]:
        """查询确认请求状态。

        Args:
            request_id: 请求 ID

        Returns:
            ConfirmationRequest;不存在返回 None
        """
        return self._pending.get(request_id)

    def expire_old(self, timeout_minutes: int = 60) -> int:
        """清理过期的待确认请求。

        将创建时间超过 timeout_minutes 的 pending 请求标记为 expired。

        Args:
            timeout_minutes: 超时分钟数(默认 60)

        Returns:
            清理的请求数
        """
        if timeout_minutes <= 0:
            return 0
        now = datetime.now()
        threshold = now - timedelta(minutes=timeout_minutes)
        expired_ids = [
            rid for rid, r in self._pending.items()
            if r.status == "pending" and r.created_at < threshold
        ]
        for rid in expired_ids:
            r = self._pending[rid]
            r.status = "expired"
            r.decided_at = now
            r.decided_by = "system"
            r.reason = f"timeout after {timeout_minutes} minutes"
            print(
                f"[audit] confirmation expired: id={rid} "
                f"task={r.task_id} timeout={timeout_minutes}min"
            )
        return len(expired_ids)
