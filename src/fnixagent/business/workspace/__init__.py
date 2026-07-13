"""L2 办公生态连接器(P2-10)。

6 个 Connector,每个继承 WorkspaceConnector,内置 StubProvider 默认实现,
具体厂商实现(飞书/企业微信/钉钉/Exchange 等)通过 register_provider() 注册。

设计原则(对应"可插拔第三方服务接口"):
  - Connector 是抽象接口,不绑定具体厂商
  - 默认 StubProvider 用于本地开发/测试/降级
  - 具体厂商实现按需注册,运行时按 config.provider 切换
  - 全部方法返回 ConnectorResult(success/data/error)
  - 数据结构(Email/CalendarEvent/Meeting/ApprovalRequest/IMMessage/KnowledgeDoc)
    作为厂商无关的中间表示,具体 Provider 负责厂商格式↔中间格式转换

6 个 Connector:
  - MailConnector:      send/list/get/reply/search
  - ScheduleConnector:  create_event/list/update/delete/check_freebusy
  - MeetingConnector:   create/list/get_link/get_transcript
  - ApprovalConnector:  submit/list_pending/approve/reject/get_status
  - IMConnector:        send_message/send_card/create_group/list_groups
  - KnowledgeConnector: search/list_bases/get_doc/upload
"""
from fnixagent.business.workspace.base import (
    BaseProvider,
    ConnectorConfig,
    ConnectorResult,
    StubProvider,
    WorkspaceConnector,
)
from fnixagent.business.workspace.mail import (
    Email,
    MailConnector,
    MailProvider,
    StubMailProvider,
)
from fnixagent.business.workspace.schedule import (
    CalendarEvent,
    FreeBusySlot,
    ScheduleConnector,
    ScheduleProvider,
    StubScheduleProvider,
)
from fnixagent.business.workspace.meeting import (
    Meeting,
    MeetingConnector,
    MeetingProvider,
    StubMeetingProvider,
)
from fnixagent.business.workspace.approval import (
    ApprovalConnector,
    ApprovalProvider,
    ApprovalRequest,
    StubApprovalProvider,
)
from fnixagent.business.workspace.im import (
    IMConnector,
    IMGroup,
    IMMessage,
    IMProvider,
    StubIMProvider,
)
from fnixagent.business.workspace.knowledge import (
    KnowledgeBase,
    KnowledgeConnector,
    KnowledgeDoc,
    KnowledgeProvider,
    SearchResult,
    StubKnowledgeProvider,
)

__all__ = [
    # 基类
    "WorkspaceConnector",
    "BaseProvider",
    "ConnectorConfig",
    "ConnectorResult",
    "StubProvider",
    # 邮件
    "MailConnector",
    "MailProvider",
    "StubMailProvider",
    "Email",
    # 日程
    "ScheduleConnector",
    "ScheduleProvider",
    "StubScheduleProvider",
    "CalendarEvent",
    "FreeBusySlot",
    # 会议
    "MeetingConnector",
    "MeetingProvider",
    "StubMeetingProvider",
    "Meeting",
    # 审批
    "ApprovalConnector",
    "ApprovalProvider",
    "StubApprovalProvider",
    "ApprovalRequest",
    # IM
    "IMConnector",
    "IMProvider",
    "StubIMProvider",
    "IMMessage",
    "IMGroup",
    # 知识库
    "KnowledgeConnector",
    "KnowledgeProvider",
    "StubKnowledgeProvider",
    "KnowledgeBase",
    "KnowledgeDoc",
    "SearchResult",
]
