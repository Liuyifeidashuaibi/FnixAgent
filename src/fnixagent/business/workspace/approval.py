"""Approval Connector(P2-10)。

审批能力:submit/list_pending/approve/reject/get_status。
支持厂商:钉钉审批 / 飞书审批 / 企业微信审批 / 泛微。
默认:StubProvider(本地开发占位)。

状态机(BUG 修复「审批状态机非法转移」):
  合法状态:pending / approved / rejected / cancelled / withdrawn
  合法转移:
    pending → approved | rejected | cancelled | withdrawn
    approved / rejected / cancelled / withdrawn → (终态,不可再转移)
  approve/reject 仅在 pending 状态合法;已审批/已撤回/已取消的申请再次审批将被拒绝。

参数校验:
  - request_id/approver/template_code/title/applicant 非空
  - approvers 列表非空(提交审批至少需 1 个审批人)

异常捕获:
  - Provider 调用包裹 try-except,捕获厂商 API(钉钉/飞书/企微/泛微)异常,
    统一转为 ConnectorResult(success=False, error=...)
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass

from fnixagent.business.workspace.base import (
    BaseProvider,
    ConnectorResult,
    StubProvider,
    WorkspaceConnector,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class ApprovalRequest:
    """审批请求。"""

    request_id: str = ""
    template_code: str = ""  # 审批模板编码
    title: str = ""
    applicant: str = ""
    applicant_dept: str = ""
    submitted_at: str = ""  # ISO 8601
    form_data: dict = None  # type: ignore
    approvers: list[dict] = None  # type: ignore  # [{name, status, comment, time}]
    status: str = "pending"  # pending / approved / rejected / cancelled / withdrawn
    current_step: int = 0
    total_steps: int = 1
    cc_list: list[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.form_data is None:
            self.form_data = {}
        if self.approvers is None:
            self.approvers = []
        if self.cc_list is None:
            self.cc_list = []


# ---------------------------------------------------------------------------
# 状态机定义(BUG 修复:审批状态机非法转移)
# ---------------------------------------------------------------------------


# 合法状态集
VALID_STATUSES = frozenset({"pending", "approved", "rejected", "cancelled", "withdrawn"})

# 合法状态转移表:current_status → {允许的目标 action}
# approve/reject 仅在 pending 状态合法;终态(approved/rejected/cancelled/withdrawn)不可再转移
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"approve", "reject", "cancel", "withdraw"}),
    "approved": frozenset(),  # 终态
    "rejected": frozenset(),  # 终态
    "cancelled": frozenset(),  # 终态
    "withdrawn": frozenset(),  # 终态
}


def validate_state_transition(current_status: str, action: str) -> str | None:
    """校验状态转移是否合法。

    Args:
        current_status: 当前状态(pending/approved/rejected/cancelled/withdrawn)
        action: 待执行动作(approve/reject/cancel/withdraw)

    Returns:
        None 表示合法;非 None 为错误描述。
    """
    if current_status not in VALID_STATUSES:
        return f"unknown current status {current_status!r}, must be one of {sorted(VALID_STATUSES)}"
    allowed = VALID_TRANSITIONS.get(current_status, frozenset())
    if action not in allowed:
        return (
            f"illegal transition: cannot {action} a request in "
            f"{current_status!r} state (allowed: {sorted(allowed) or 'none'})"
        )
    return None


# ---------------------------------------------------------------------------
# ApprovalProvider 抽象
# ---------------------------------------------------------------------------


class ApprovalProvider(BaseProvider):
    """审批 Provider 抽象基类。

    具体实现(钉钉/飞书/企微/泛微)应:
      - 持有 HTTP 客户端(支持 keep-alive 连接复用)
      - override close() 释放会话
      - 业务方法内部捕获厂商 API 异常,转为 ConnectorResult(success=False)
      - approve/reject 应在服务端再次校验状态机(防并发竞态)
    """

    @abc.abstractmethod
    def submit(
        self,
        template_code: str,
        title: str,
        applicant: str,
        form_data: dict,
        approvers: list[str],
        cc_list: list[str] | None = None,
        applicant_dept: str = "",
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def list_pending(
        self,
        approver: str | None = None,
        limit: int = 20,
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def approve(
        self,
        request_id: str,
        approver: str,
        comment: str = "",
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def reject(
        self,
        request_id: str,
        approver: str,
        comment: str = "",
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def get_status(self, request_id: str) -> ConnectorResult: ...


# ---------------------------------------------------------------------------
# Stub 实现
# ---------------------------------------------------------------------------


class StubApprovalProvider(StubProvider, ApprovalProvider):
    """审批 stub 实现。

    返回值一致性:list_pending 空结果 data=[];submit 占位 ID 'stub-apr-<generated>'。
    """

    def submit(
        self,
        template_code: str,
        title: str,
        applicant: str,
        form_data: dict,
        approvers: list[str],
        cc_list: list[str] | None = None,
        applicant_dept: str = "",
    ) -> ConnectorResult:
        return self._stub_result(
            data=ApprovalRequest(
                request_id="stub-apr-<generated>",
                template_code=template_code,
                title=title,
                applicant=applicant,
                applicant_dept=applicant_dept,
                form_data=form_data,
                approvers=[
                    {"name": a, "status": "pending", "comment": "", "time": ""} for a in approvers
                ],
                cc_list=cc_list or [],
            ).__dict__,
            action="submit",
        )

    def list_pending(
        self,
        approver: str | None = None,
        limit: int = 20,
    ) -> ConnectorResult:
        # 空结果统一 data=[]
        return self._stub_result(data=[], approver=approver, limit=limit)

    def approve(
        self,
        request_id: str,
        approver: str,
        comment: str = "",
    ) -> ConnectorResult:
        return self._stub_result(
            data={
                "request_id": request_id,
                "approver": approver,
                "action": "approved",
                "comment": comment,
            },
        )

    def reject(
        self,
        request_id: str,
        approver: str,
        comment: str = "",
    ) -> ConnectorResult:
        return self._stub_result(
            data={
                "request_id": request_id,
                "approver": approver,
                "action": "rejected",
                "comment": comment,
            },
        )

    def get_status(self, request_id: str) -> ConnectorResult:
        return self._stub_result(
            data=ApprovalRequest(
                request_id=request_id,
                title="[stub] Sample approval",
                applicant="stub-user",
                status="pending",
            ).__dict__,
        )


# ---------------------------------------------------------------------------
# ApprovalConnector
# ---------------------------------------------------------------------------


class ApprovalConnector(WorkspaceConnector):
    """审批连接器。

    在委托 Provider 前做参数校验与状态机校验(BUG 修复:非法转移),
    并对厂商 API 调用统一捕获异常。
    """

    @property
    def name(self) -> str:
        return "approval"

    def _register_default_stub(self) -> None:
        self._providers["stub"] = StubApprovalProvider()

    # -- 业务方法 ------------------------------------------------------

    def submit(
        self,
        template_code: str,
        title: str,
        applicant: str,
        form_data: dict,
        approvers: list[str],
        cc_list: list[str] | None = None,
        applicant_dept: str = "",
    ) -> ConnectorResult:
        """提交审批申请。

        Args:
            template_code: 审批模板编码(非空)
            title: 申请标题(非空)
            applicant: 申请人(用户 ID/邮箱,非空)
            form_data: 表单数据 {field_code: value}
            approvers: 审批人列表(按顺序,非空)
            cc_list: 抄送人列表
            applicant_dept: 申请人部门

        Returns:
            ConnectorResult(data=ApprovalRequest)
        """
        # 参数非空校验
        if not template_code:
            return ConnectorResult(success=False, error="template_code must not be empty")
        if not title or not title.strip():
            return ConnectorResult(success=False, error="title must not be empty")
        if not applicant:
            return ConnectorResult(success=False, error="applicant must not be empty")
        if not approvers:
            return ConnectorResult(
                success=False,
                error="approvers list must not be empty",
            )

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.submit(
                template_code=template_code,
                title=title,
                applicant=applicant,
                form_data=form_data,
                approvers=approvers,
                cc_list=cc_list,
                applicant_dept=applicant_dept,
            )
        except Exception as e:
            _logger.exception("approval.submit failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"approval submit failed: {type(e).__name__}: {e}",
            )

    def list_pending(
        self,
        approver: str | None = None,
        limit: int = 20,
    ) -> ConnectorResult:
        """列出待审批申请。

        Args:
            approver: 指定审批人(用户 ID);None 列出当前用户全部待审批
            limit: 最多返回条数(自动 clamp 到 [1, 200])

        Returns:
            ConnectorResult(data=[ApprovalRequest, ...]);空结果 data=[]
        """
        safe_limit = max(1, min(limit, 200))
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.list_pending(
                approver=approver,
                limit=safe_limit,
            )
        except Exception as e:
            _logger.exception("approval.list_pending failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"approval list_pending failed: {type(e).__name__}: {e}",
            )

    def approve(
        self,
        request_id: str,
        approver: str,
        comment: str = "",
        current_status: str | None = None,
    ) -> ConnectorResult:
        """审批通过。

        Args:
            request_id: 申请 ID(非空)
            approver: 审批人(非空)
            comment: 审批意见
            current_status: 可选,当前状态;提供时本地校验状态机(非法转移拒绝),
                            不提供则仅服务端校验

        Returns:
            ConnectorResult(data={action: "approved", ...})
        """
        if not request_id:
            return ConnectorResult(success=False, error="request_id must not be empty")
        if not approver:
            return ConnectorResult(success=False, error="approver must not be empty")

        # 状态机校验(BUG 修复:审批状态机非法转移)
        if current_status is not None:
            trans_err = validate_state_transition(current_status, "approve")
            if trans_err is not None:
                _logger.warning(
                    "approval.approve rejected: request=%s approver=%s %s",
                    request_id,
                    approver,
                    trans_err,
                )
                return ConnectorResult(success=False, error=trans_err)

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.approve(
                request_id=request_id,
                approver=approver,
                comment=comment,
            )
        except Exception as e:
            _logger.exception("approval.approve failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"approval approve failed: {type(e).__name__}: {e}",
            )

    def reject(
        self,
        request_id: str,
        approver: str,
        comment: str = "",
        current_status: str | None = None,
    ) -> ConnectorResult:
        """审批驳回。

        Args:
            request_id: 申请 ID(非空)
            approver: 审批人(非空)
            comment: 驳回原因
            current_status: 可选,当前状态;提供时本地校验状态机(非法转移拒绝),
                            不提供则仅服务端校验

        Returns:
            ConnectorResult(data={action: "rejected", ...})
        """
        if not request_id:
            return ConnectorResult(success=False, error="request_id must not be empty")
        if not approver:
            return ConnectorResult(success=False, error="approver must not be empty")

        # 状态机校验(BUG 修复:审批状态机非法转移)
        if current_status is not None:
            trans_err = validate_state_transition(current_status, "reject")
            if trans_err is not None:
                _logger.warning(
                    "approval.reject rejected: request=%s approver=%s %s",
                    request_id,
                    approver,
                    trans_err,
                )
                return ConnectorResult(success=False, error=trans_err)

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.reject(
                request_id=request_id,
                approver=approver,
                comment=comment,
            )
        except Exception as e:
            _logger.exception("approval.reject failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"approval reject failed: {type(e).__name__}: {e}",
            )

    def get_status(self, request_id: str) -> ConnectorResult:
        """查询审批状态。

        Args:
            request_id: 申请 ID(非空)

        Returns:
            ConnectorResult(data=ApprovalRequest)
        """
        if not request_id:
            return ConnectorResult(success=False, error="request_id must not be empty")
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.get_status(request_id=request_id)
        except Exception as e:
            _logger.exception("approval.get_status failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"approval get_status failed: {type(e).__name__}: {e}",
            )
