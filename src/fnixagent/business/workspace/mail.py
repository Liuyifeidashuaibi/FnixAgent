"""Mail Connector(P2-10)。

邮件能力:send/list/get/reply/search。
支持厂商:Exchange / Gmail / 阿里邮箱 / 腾讯企业邮箱(通过 IMAP+SMTP 通用实现)。
默认:StubProvider(本地开发占位)。

安全防护:
  - 收件人邮箱格式校验(_validate_email);非法地址直接返回失败,避免无效投递
  - HTML 正文/主题消毒(html.escape),防止 XSS 注入到邮件客户端
  - 附件大小限制(MAX_ATTACHMENT_BYTES);超过限制拒绝,避免内存爆炸/被网关拒收
  - 收件人列表日志脱敏(_mask_addrs),不打印完整邮箱到日志
  - API token/SMTP 密码不出现在异常信息中

异常捕获:
  - Provider 调用包裹 try-except,捕获 smtplib/imaplib/网络 IO 异常,
    统一转为 ConnectorResult(success=False, error=...)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
import html
import logging
import re
from dataclasses import dataclass

from fnixagent.business.workspace.base import (
    BaseProvider,
    ConnectorResult,
    StubProvider,
    WorkspaceConnector,
)

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量与工具
# ---------------------------------------------------------------------------

# 简易邮箱格式校验(本地开发级;生产可用 email.utils.parseaddr 配合更严格规则)
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# 单附件大小上限(25 MB,与主流邮箱网关一致)
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024

# 列表分页上限(避免一次性加载全量邮件导致内存飙升)
MAX_LIST_LIMIT = 200

def _validate_email(addr: str) -> bool:
    """校验单个邮箱地址格式。"""
    if not isinstance(addr, str) or not addr:
        return False
    return _EMAIL_RE.match(addr) is not None

def _validate_addrs(addrs: list[str]) -> str | None:
    """校验收件人列表,返回首个非法地址(全合法返回 None)。"""
    for a in addrs:
        if not _validate_email(a):
            return a
    return None

def _mask_addrs(addrs: list[str] | None) -> list[str]:
    """收件人列表脱敏(仅保留首字符 + 域名),用于日志。"""
    if not addrs:
        return []
    masked: list[str] = []
    for a in addrs:
        if "@" in a:
            local, domain = a.split("@", 1)
            masked.append(f"{local[0]}***@{domain}" if local else f"***@{domain}")
        else:
            masked.append("***")
    return masked

def _check_attachments(attachments: list[dict] | None) -> str | None:
    """校验附件大小限制。

    支持两种附件表示:
      - {path, name}:从文件读取,校验文件大小
      - {content_base64, name, mime_type}:内联内容,校验解码后字节数
    返回首个超限附件名(全合法返回 None)。
    """
    if not attachments:
        return None
    import os

    for att in attachments:
        path = att.get("path")
        if path and os.path.exists(path):
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > MAX_ATTACHMENT_BYTES:
                return att.get("name", path)
        else:
            content_b64 = att.get("content_base64")
            if content_b64:
                # base64 编码后长度 ≈ 原始大小 * 4/3
                size = len(content_b64) * 3 // 4
                if size > MAX_ATTACHMENT_BYTES:
                    return att.get("name", "<inline>")
    return None

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Email:
    """邮件数据结构。"""

    message_id: str = ""
    subject: str = ""
    from_addr: str = ""
    to_addrs: list[str] = None  # type: ignore
    cc_addrs: list[str] = None  # type: ignore
    bcc_addrs: list[str] = None  # type: ignore
    body_text: str = ""
    body_html: str = ""
    attachments: list[dict] = None  # type: ignore
    date: str = ""
    is_read: bool = False
    labels: list[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.to_addrs is None:
            self.to_addrs = []
        if self.cc_addrs is None:
            self.cc_addrs = []
        if self.bcc_addrs is None:
            self.bcc_addrs = []
        if self.attachments is None:
            self.attachments = []
        if self.labels is None:
            self.labels = []

# ---------------------------------------------------------------------------
# MailProvider 抽象
# ---------------------------------------------------------------------------

class MailProvider(BaseProvider):
    """邮件 Provider 抽象基类。

    具体实现(如 ImapSmtpMailProvider / FeishuMailProvider)应:
      - 持有 SMTP/IMAP 会话或 HTTP 客户端(支持 keep-alive 连接复用)
      - override close() 释放会话
      - 业务方法内部捕获 smtplib.SMTPException / imaplib.IMAP4.error / OSError,
        转为 ConnectorResult(success=False)
    """

    @abc.abstractmethod
    def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[dict] | None = None,
        html: bool = False,
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def list(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        unread_only: bool = False,
        since: str | None = None,
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def get(self, message_id: str) -> ConnectorResult: ...

    @abc.abstractmethod
    def reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        attachments: list[dict] | None = None,
    ) -> ConnectorResult: ...

    @abc.abstractmethod
    def search(
        self,
        query: str,
        folder: str = "INBOX",
        limit: int = 20,
    ) -> ConnectorResult: ...

# ---------------------------------------------------------------------------
# Stub 实现
# ---------------------------------------------------------------------------

class StubMailProvider(StubProvider, MailProvider):
    """邮件 stub 实现(本地开发占位)。

    返回值一致性:列表方法空结果 data=[],非 None。
    """

    def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[dict] | None = None,
        html: bool = False,
    ) -> ConnectorResult:
        return self._stub_result(
            data={"message_id": "stub-<generated>", "to": to, "subject": subject},
            action="send",
        )

    def list(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        unread_only: bool = False,
        since: str | None = None,
    ) -> ConnectorResult:
        # 空结果统一 data=[]
        return self._stub_result(data=[], folder=folder, limit=limit)

    def get(self, message_id: str) -> ConnectorResult:
        return self._stub_result(
            data=Email(
                message_id=message_id,
                subject="[stub] Sample email",
                from_addr="stub@example.com",
                to_addrs=["you@example.com"],
                body_text="This is a stub email body.",
            ).__dict__,
        )

    def reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        attachments: list[dict] | None = None,
    ) -> ConnectorResult:
        return self._stub_result(
            data={"in_reply_to": message_id, "sent": True},
            action="reply",
        )

    def search(
        self,
        query: str,
        folder: str = "INBOX",
        limit: int = 20,
    ) -> ConnectorResult:
        # 搜索空结果统一 data=[],非 None(BUG 修复:避免下游 NoneType 迭代错误)
        return self._stub_result(data=[], query=query, folder=folder)

# ---------------------------------------------------------------------------
# MailConnector
# ---------------------------------------------------------------------------

class MailConnector(WorkspaceConnector):
    """邮件连接器。

    在委托 Provider 前做参数校验(收件人格式/附件大小/分页上限),
    并对 HTML 正文/主题做消毒,异常统一捕获。
    """

    @property
    def name(self) -> str:
        return "mail"

    def _register_default_stub(self) -> None:
        self._providers["stub"] = StubMailProvider()

    # -- 业务方法(委托 active provider) --------------------------------

    def send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        attachments: list[dict] | None = None,
        html: bool = False,
    ) -> ConnectorResult:
        """发送邮件。

        Args:
            to: 收件人列表(至少 1 个,格式校验)
            subject: 主题(消毒)
            body: 正文(html=True 时消毒)
            cc: 抄送列表(格式校验)
            bcc: 密送列表(格式校验)
            attachments: 附件 [{path, name} 或 {content_base64, name, mime_type}]
                         单文件不超过 25MB
            html: 是否 HTML 正文

        Returns:
            ConnectorResult(data={message_id, ...})
        """
        # 参数非空校验
        if not to:
            return ConnectorResult(success=False, error="recipients (to) must not be empty")
        if not subject or not subject.strip():
            return ConnectorResult(success=False, error="subject must not be empty")
        if not body:
            return ConnectorResult(success=False, error="body must not be empty")

        # 收件人格式校验
        for label, addrs in (("to", to), ("cc", cc or []), ("bcc", bcc or [])):
            bad = _validate_addrs(addrs)
            if bad is not None:
                return ConnectorResult(
                    success=False,
                    error=f"invalid email address in {label}: {bad!r}",
                )

        # 附件大小校验
        oversized = _check_attachments(attachments)
        if oversized is not None:
            return ConnectorResult(
                success=False,
                error=f"attachment {oversized!r} exceeds limit "
                f"({MAX_ATTACHMENT_BYTES // 1024 // 1024}MB)",
            )

        err = self._ensure_connected()
        if err:
            return err

        # HTML 正文消毒(防 XSS);HTML 主题同样转义
        safe_subject = html.escape(subject)
        safe_body = body if not html else html.escape(body)

        # 日志脱敏:不打印完整收件人列表
        _logger.info(
            "mail.send to=%s cc=%s subject_len=%d attachments=%d",
            _mask_addrs(to),
            _mask_addrs(cc),
            len(safe_subject),
            len(attachments or []),
        )

        assert self._active_provider is not None
        try:
            # 捕获 SMTP/IMAP/网络 IO 异常
            return self._active_provider.send(
                to=to,
                subject=safe_subject,
                body=safe_body,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                html=html,
            )
        except Exception as e:
            # 不打印 token/密码;仅异常类型与消息
            _logger.exception("mail.send failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"mail send failed: {type(e).__name__}: {e}",
            )

    def list(
        self,
        folder: str = "INBOX",
        limit: int = 20,
        unread_only: bool = False,
        since: str | None = None,
    ) -> ConnectorResult:
        """列出邮件(分页加载,避免全量加载)。

        Args:
            folder: 邮箱文件夹(INBOX/SENT/DRAFTS/TRASH/...)
            limit: 最多返回条数(自动 clamp 到 MAX_LIST_LIMIT)
            unread_only: 仅未读
            since: 起始日期(ISO 格式)

        Returns:
            ConnectorResult(data=[Email, ...]);空结果 data=[]
        """
        if not folder:
            return ConnectorResult(success=False, error="folder must not be empty")
        # 分页上限 clamp
        safe_limit = max(1, min(limit, MAX_LIST_LIMIT))

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            # 捕获 IMAP 异常
            return self._active_provider.list(
                folder=folder,
                limit=safe_limit,
                unread_only=unread_only,
                since=since,
            )
        except Exception as e:
            _logger.exception("mail.list failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"mail list failed: {type(e).__name__}: {e}",
            )

    def get(self, message_id: str) -> ConnectorResult:
        """获取单封邮件详情。

        Args:
            message_id: 邮件 ID(非空)

        Returns:
            ConnectorResult(data=Email)
        """
        if not message_id:
            return ConnectorResult(success=False, error="message_id must not be empty")
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.get(message_id)
        except Exception as e:
            _logger.exception("mail.get failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"mail get failed: {type(e).__name__}: {e}",
            )

    def reply(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        attachments: list[dict] | None = None,
    ) -> ConnectorResult:
        """回复邮件。

        Args:
            message_id: 原邮件 ID(非空)
            body: 回复正文(HTML 转义)
            reply_all: 是否回复全部(包含 cc)
            attachments: 附件(校验大小)

        Returns:
            ConnectorResult(data={sent: True, ...})
        """
        if not message_id:
            return ConnectorResult(success=False, error="message_id must not be empty")
        if not body:
            return ConnectorResult(success=False, error="body must not be empty")

        oversized = _check_attachments(attachments)
        if oversized is not None:
            return ConnectorResult(
                success=False,
                error=f"attachment {oversized!r} exceeds limit "
                f"({MAX_ATTACHMENT_BYTES // 1024 // 1024}MB)",
            )

        err = self._ensure_connected()
        if err:
            return err
        # 正文消毒
        safe_body = html.escape(body)
        assert self._active_provider is not None
        try:
            return self._active_provider.reply(
                message_id=message_id,
                body=safe_body,
                reply_all=reply_all,
                attachments=attachments,
            )
        except Exception as e:
            _logger.exception("mail.reply failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"mail reply failed: {type(e).__name__}: {e}",
            )

    def search(
        self,
        query: str,
        folder: str = "INBOX",
        limit: int = 20,
    ) -> ConnectorResult:
        """搜索邮件。

        Args:
            query: 搜索关键词(支持 from:/to:/subject:/has:attachment 等修饰符)
            folder: 限定文件夹
            limit: 最多返回条数(自动 clamp)

        Returns:
            ConnectorResult(data=[Email, ...]);空结果 data=[]
        """
        if not query or not query.strip():
            # 空查询直接返回空结果(BUG 修复:不抛错给下游)
            return ConnectorResult(success=True, data=[], metadata={"empty_query": True})
        safe_limit = max(1, min(limit, MAX_LIST_LIMIT))
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.search(
                query=query,
                folder=folder,
                limit=safe_limit,
            )
        except Exception as e:
            _logger.exception("mail.search failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"mail search failed: {type(e).__name__}: {e}",
            )
