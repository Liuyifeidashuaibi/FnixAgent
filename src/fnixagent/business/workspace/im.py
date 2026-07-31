"""IM Connector(P2-10)。

即时通讯能力:send_message/send_card/create_group/list_groups。
支持厂商:飞书 / 企业微信 / 钉钉(用户偏好:仅这三家,L2 适度覆盖)。
默认:StubProvider(本地开发占位)。

参数校验:
  - send_message/send_card:chat_id 与 user_id 至少一个;content/card 非空
  - create_group:name/owner/members 非空(至少 1 个成员)

异常捕获:
  - Provider 调用包裹 try-except,捕获厂商 API(飞书 lark-oapi / 企微 / 钉钉)异常,
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
class IMMessage:
    """IM 消息。"""

    msg_id: str = ""
    msg_type: str = "text"  # text / card / image / file / share_chat
    chat_id: str = ""  # 群聊 ID(群消息)
    user_id: str = ""  # 接收人 ID(单聊消息)
    sender: str = ""
    content: str = ""  # text 类型的内容
    card: dict | None = None  # card 类型的内容
    timestamp: str = ""
    mention_list: list[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.mention_list is None:
            self.mention_list = []


@dataclass
class IMGroup:
    """IM 群组。"""

    chat_id: str = ""
    name: str = ""
    description: str = ""
    owner: str = ""
    members: list[dict] = None  # type: ignore  # [{user_id, name, role}]
    chat_mode: str = "group"  # group / p2p
    chat_type: str = "private"  # private / public

    def __post_init__(self) -> None:
        if self.members is None:
            self.members = []


# ---------------------------------------------------------------------------
# IMProvider 抽象
# ---------------------------------------------------------------------------


class IMProvider(BaseProvider):
    """IM Provider 抽象基类。

    具体实现(飞书 FeishuIMProvider / 企微 WechatWorkIMProvider / 钉钉 DingTalkIMProvider)应:
      - 持有 HTTP 客户端(支持 keep-alive 连接复用)
      - override close() 释放会话
      - 业务方法内部捕获厂商 SDK 异常(如 lark_oapi 异常、requests.RequestException),
        转为 ConnectorResult(success=False)
    """

    @abc.abstractmethod
    def send_message(
        self,
        content: str,
        chat_id: str | None = None,
        user_id: str | None = None,
        msg_type: str = "text",
        mention_list: list[str] | None = None,
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def send_card(
        self,
        card: dict,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def create_group(
        self,
        name: str,
        owner: str,
        members: list[str],
        description: str = "",
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def list_groups(self, limit: int = 50) -> ConnectorResult: ...


# ---------------------------------------------------------------------------
# Stub 实现
# ---------------------------------------------------------------------------


class StubIMProvider(StubProvider, IMProvider):
    """IM stub 实现。

    返回值一致性:list_groups 空结果 data=[];send_message/send_card 占位 ID 'stub-msg-<generated>'。
    """

    def send_message(
        self,
        content: str,
        chat_id: str | None = None,
        user_id: str | None = None,
        msg_type: str = "text",
        mention_list: list[str] | None = None,
    ) -> ConnectorResult:
        return self._stub_result(
            data=IMMessage(
                msg_id="stub-msg-<generated>",
                msg_type=msg_type,
                chat_id=chat_id or "",
                user_id=user_id or "",
                content=content,
                mention_list=mention_list or [],
            ).__dict__,
            action="send_message",
        )

    def send_card(
        self,
        card: dict,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> ConnectorResult:
        return self._stub_result(
            data=IMMessage(
                msg_id="stub-msg-<generated>",
                msg_type="card",
                chat_id=chat_id or "",
                user_id=user_id or "",
                card=card,
            ).__dict__,
            action="send_card",
        )

    def create_group(
        self,
        name: str,
        owner: str,
        members: list[str],
        description: str = "",
    ) -> ConnectorResult:
        return self._stub_result(
            data=IMGroup(
                chat_id="stub-chat-<generated>",
                name=name,
                owner=owner,
                description=description,
                members=[{"user_id": m, "name": m, "role": "member"} for m in members],
            ).__dict__,
            action="create_group",
        )

    def list_groups(self, limit: int = 50) -> ConnectorResult:
        # 空结果统一 data=[]
        return self._stub_result(data=[], limit=limit)


# ---------------------------------------------------------------------------
# IMConnector
# ---------------------------------------------------------------------------


class IMConnector(WorkspaceConnector):
    """IM 即时通讯连接器(飞书/企业微信/钉钉)。

    在委托 Provider 前做参数校验(chat_id/user_id 至少一个、群名/群主/成员非空),
    并对厂商 API 调用统一捕获异常。
    """

    @property
    def name(self) -> str:
        return "im"

    def _register_default_stub(self) -> None:
        self._providers["stub"] = StubIMProvider()

    # -- 业务方法 ------------------------------------------------------

    def send_message(
        self,
        content: str,
        chat_id: str | None = None,
        user_id: str | None = None,
        msg_type: str = "text",
        mention_list: list[str] | None = None,
    ) -> ConnectorResult:
        """发送文本消息。

        Args:
            content: 消息内容(非空)
            chat_id: 群聊 ID(群消息)
            user_id: 接收人 ID(单聊消息)
            msg_type: text / image / file / share_chat(默认 text)
            mention_list: @ 用户 ID 列表

        Note:
            chat_id 与 user_id 至少一个;同时存在优先 chat_id。

        Returns:
            ConnectorResult(data=IMMessage)
        """
        # 参数非空校验
        if not content:
            return ConnectorResult(success=False, error="content must not be empty")
        if not chat_id and not user_id:
            return ConnectorResult(
                success=False,
                error="either chat_id or user_id must be provided",
            )
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            # 捕获飞书/企微/钉钉 API 异常
            return self._active_provider.send_message(
                content=content,
                chat_id=chat_id,
                user_id=user_id,
                msg_type=msg_type,
                mention_list=mention_list,
            )
        except Exception as e:
            _logger.exception("im.send_message failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"im send_message failed: {type(e).__name__}: {e}",
            )

    def send_card(
        self,
        card: dict,
        chat_id: str | None = None,
        user_id: str | None = None,
    ) -> ConnectorResult:
        """发送卡片消息(交互式卡片)。

        Args:
            card: 卡片内容(厂商特定结构,通常含 header/elements,非空)
            chat_id: 群聊 ID
            user_id: 接收人 ID

        Returns:
            ConnectorResult(data=IMMessage)
        """
        # 参数非空校验
        if not card or not isinstance(card, dict):
            return ConnectorResult(success=False, error="card must be a non-empty dict")
        if not chat_id and not user_id:
            return ConnectorResult(
                success=False,
                error="either chat_id or user_id must be provided",
            )
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.send_card(
                card=card,
                chat_id=chat_id,
                user_id=user_id,
            )
        except Exception as e:
            _logger.exception("im.send_card failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"im send_card failed: {type(e).__name__}: {e}",
            )

    def create_group(
        self,
        name: str,
        owner: str,
        members: list[str],
        description: str = "",
    ) -> ConnectorResult:
        """创建群组。

        Args:
            name: 群名(非空)
            owner: 群主用户 ID(非空)
            members: 成员用户 ID 列表(非空)
            description: 群描述

        Returns:
            ConnectorResult(data=IMGroup)
        """
        # 参数非空校验
        if not name or not name.strip():
            return ConnectorResult(success=False, error="group name must not be empty")
        if not owner:
            return ConnectorResult(success=False, error="owner must not be empty")
        if not members:
            return ConnectorResult(
                success=False,
                error="members list must not be empty",
            )

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.create_group(
                name=name,
                owner=owner,
                members=members,
                description=description,
            )
        except Exception as e:
            _logger.exception("im.create_group failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"im create_group failed: {type(e).__name__}: {e}",
            )

    def list_groups(self, limit: int = 50) -> ConnectorResult:
        """列出当前用户参与的群组。

        Args:
            limit: 最多返回条数(自动 clamp 到 [1, 200])

        Returns:
            ConnectorResult(data=[IMGroup, ...]);空结果 data=[]
        """
        safe_limit = max(1, min(limit, 200))
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.list_groups(limit=safe_limit)
        except Exception as e:
            _logger.exception("im.list_groups failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"im list_groups failed: {type(e).__name__}: {e}",
            )
