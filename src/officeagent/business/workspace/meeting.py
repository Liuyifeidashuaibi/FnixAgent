"""Meeting Connector(P2-10)。

会议能力:create/list/get_link/get_transcript。
支持厂商:Zoom / Teams / 飞书会议 / 钉钉会议 / 腾讯会议。
默认:StubProvider(本地开发占位)。

参数校验:
  - 参与人列表非空:提供 participants 时必须非空列表(避免创建无参会人的"会议")
  - duration_minutes > 0
  - meeting_id/topic 非空
  - format ∈ {text, json, srt}

异常捕获:
  - Provider 调用包裹 try-except,捕获厂商 API(Zoom/Teams/飞书/钉钉/腾讯)异常,
    统一转为 ConnectorResult(success=False, error=...)
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import Optional

from officeagent.business.workspace.base import (
    BaseProvider,
    ConnectorConfig,
    ConnectorResult,
    StubProvider,
    WorkspaceConnector,
)


_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class Meeting:
    """会议对象。"""
    meeting_id: str = ""
    topic: str = ""
    start_time: str = ""          # ISO 8601
    duration_minutes: int = 60
    host: str = ""
    participants: list[str] = None  # type: ignore
    join_url: str = ""
    host_url: str = ""
    password: str = ""
    settings: dict = None  # type: ignore
    status: str = "scheduled"      # scheduled / started / ended / cancelled

    def __post_init__(self) -> None:
        if self.participants is None:
            self.participants = []
        if self.settings is None:
            self.settings = {}


# ---------------------------------------------------------------------------
# MeetingProvider 抽象
# ---------------------------------------------------------------------------


class MeetingProvider(BaseProvider):
    """会议 Provider 抽象基类。

    具体实现(ZoomMeetingProvider / FeishuMeetingProvider 等)应:
      - 持有 HTTP 客户端(支持 keep-alive 连接复用)
      - override close() 释放会话
      - 业务方法内部捕获厂商 API 异常(如 requests.RequestException、
        zoomus exception、lark-oapi 异常),转为 ConnectorResult(success=False)
    """

    @abc.abstractmethod
    def create(
        self,
        topic: str,
        start_time: str,
        duration_minutes: int = 60,
        participants: Optional[list[str]] = None,
        password: str = "",
        settings: Optional[dict] = None,
    ) -> ConnectorResult:
        ...

    @abc.abstractmethod
    def list(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 20,
    ) -> ConnectorResult:
        ...

    @abc.abstractmethod
    def get_link(self, meeting_id: str) -> ConnectorResult:
        ...

    @abc.abstractmethod
    def get_transcript(
        self,
        meeting_id: str,
        format: str = "text",
    ) -> ConnectorResult:
        ...


# ---------------------------------------------------------------------------
# Stub 实现
# ---------------------------------------------------------------------------


class StubMeetingProvider(StubProvider, MeetingProvider):
    """会议 stub 实现。

    返回值一致性:list 空结果 data=[];create 占位 ID 'stub-mtg-<generated>'。
    """

    def create(
        self,
        topic: str,
        start_time: str,
        duration_minutes: int = 60,
        participants: Optional[list[str]] = None,
        password: str = "",
        settings: Optional[dict] = None,
    ) -> ConnectorResult:
        return self._stub_result(
            data=Meeting(
                meeting_id="stub-mtg-<generated>",
                topic=topic,
                start_time=start_time,
                duration_minutes=duration_minutes,
                participants=participants or [],
                join_url="https://stub.example.com/join/stub-mtg",
                host_url="https://stub.example.com/host/stub-mtg",
            ).__dict__,
            action="create",
        )

    def list(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 20,
    ) -> ConnectorResult:
        # 空结果统一 data=[]
        return self._stub_result(data=[], start=start, end=end)

    def get_link(self, meeting_id: str) -> ConnectorResult:
        return self._stub_result(
            data={"join_url": f"https://stub.example.com/join/{meeting_id}",
                  "host_url": f"https://stub.example.com/host/{meeting_id}"},
        )

    def get_transcript(
        self,
        meeting_id: str,
        format: str = "text",
    ) -> ConnectorResult:
        if format == "text":
            content = "[stub] Meeting transcript placeholder.\nSpeaker 1: Hello.\nSpeaker 2: Hi."
        elif format == "json":
            content = [
                {"speaker": "Speaker 1", "text": "Hello.", "start": 0.0, "end": 1.5},
                {"speaker": "Speaker 2", "text": "Hi.", "start": 1.5, "end": 2.5},
            ]
        else:
            content = "[stub transcript]"
        return self._stub_result(data=content, format=format)


# ---------------------------------------------------------------------------
# MeetingConnector
# ---------------------------------------------------------------------------


# 支持的转写稿格式
_TRANSCRIPT_FORMATS = {"text", "json", "srt"}


class MeetingConnector(WorkspaceConnector):
    """会议连接器。

    在委托 Provider 前校验参数(参与人列表非空/时长合法/格式枚举),
    并对厂商 API 调用统一捕获异常。
    """

    @property
    def name(self) -> str:
        return "meeting"

    def _register_default_stub(self) -> None:
        self._providers["stub"] = StubMeetingProvider()

    # -- 业务方法 ------------------------------------------------------

    def create(
        self,
        topic: str,
        start_time: str,
        duration_minutes: int = 60,
        participants: Optional[list[str]] = None,
        password: str = "",
        settings: Optional[dict] = None,
    ) -> ConnectorResult:
        """创建会议。

        Args:
            topic: 主题(非空)
            start_time: 开始时间(ISO 8601,非空)
            duration_minutes: 持续分钟(>0)
            participants: 参会者邮箱列表;提供时必须非空列表
            password: 入会密码(空串无密码)
            settings: 会议设置(自动录像/等候室/...)

        Returns:
            ConnectorResult(data=Meeting)
        """
        # 参数非空校验
        if not topic or not topic.strip():
            return ConnectorResult(success=False, error="topic must not be empty")
        if not start_time:
            return ConnectorResult(success=False, error="start_time must not be empty")
        # 时长合法
        if not isinstance(duration_minutes, int) or duration_minutes <= 0:
            return ConnectorResult(
                success=False,
                error=f"duration_minutes must be a positive integer, got {duration_minutes!r}",
            )
        # 参与人列表非空校验:提供 participants 时必须非空(避免创建无参会人的"会议")
        if participants is not None and len(participants) == 0:
            return ConnectorResult(
                success=False,
                error="participants list must not be empty (pass None to omit)",
            )

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.create(
                topic=topic, start_time=start_time, duration_minutes=duration_minutes,
                participants=participants, password=password, settings=settings,
            )
        except Exception as e:
            # 捕获 Zoom/Teams/飞书/钉钉/腾讯会议 API 异常
            _logger.exception("meeting.create failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"meeting create failed: {type(e).__name__}: {e}",
            )

    def list(
        self,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 20,
    ) -> ConnectorResult:
        """列出会议。

        Args:
            start/end: 时间区间(ISO 8601);若同时提供则 start < end
            limit: 最多返回条数(自动 clamp 到 [1, 200])

        Returns:
            ConnectorResult(data=[Meeting, ...]);空结果 data=[]
        """
        # 若提供时间区间,校验 start < end(此处复用 mail 的简单空校验,
        # 严格 ISO 解析由 schedule 模块负责,meeting 列表对时间格式宽容)
        if start and end and start >= end:
            return ConnectorResult(
                success=False,
                error=f"start ({start}) must be earlier than end ({end})",
            )
        safe_limit = max(1, min(limit, 200))

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.list(start=start, end=end, limit=safe_limit)
        except Exception as e:
            _logger.exception("meeting.list failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"meeting list failed: {type(e).__name__}: {e}",
            )

    def get_link(self, meeting_id: str) -> ConnectorResult:
        """获取会议入会链接。

        Args:
            meeting_id: 会议 ID(非空)

        Returns:
            ConnectorResult(data={join_url, host_url, password})
        """
        if not meeting_id:
            return ConnectorResult(success=False, error="meeting_id must not be empty")
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.get_link(meeting_id=meeting_id)
        except Exception as e:
            _logger.exception("meeting.get_link failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"meeting get_link failed: {type(e).__name__}: {e}",
            )

    def get_transcript(
        self,
        meeting_id: str,
        format: str = "text",
    ) -> ConnectorResult:
        """获取会议转写稿。

        Args:
            meeting_id: 会议 ID(非空)
            format: text / json / srt

        Returns:
            ConnectorResult(data=transcript_content)
        """
        if not meeting_id:
            return ConnectorResult(success=False, error="meeting_id must not be empty")
        if format not in _TRANSCRIPT_FORMATS:
            return ConnectorResult(
                success=False,
                error=f"unsupported transcript format {format!r}, "
                      f"must be one of {sorted(_TRANSCRIPT_FORMATS)}",
            )
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.get_transcript(
                meeting_id=meeting_id, format=format,
            )
        except Exception as e:
            _logger.exception("meeting.get_transcript failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"meeting get_transcript failed: {type(e).__name__}: {e}",
            )
