"""Schedule Connector(P2-10)。

日程能力:create_event/list/update/delete/check_freebusy。
支持厂商:Exchange / Google Calendar / 飞书日历 / 钉钉日历。
默认:StubProvider(本地开发占位)。

参数校验:
  - 时间范围校验:start < end(避免创建负时长/零时长事件)
  - 时间区间重叠检测:check_freebusy 返回 busy slot 后可本地判断新事件是否冲突

异常捕获:
  - Provider 调用包裹 try-except,捕获厂商 API/网络 IO 异常,
    统一转为 ConnectorResult(success=False, error=...)
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

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
class CalendarEvent:
    """日历事件。"""
    event_id: str = ""
    title: str = ""
    description: str = ""
    start_time: str = ""          # ISO 8601
    end_time: str = ""            # ISO 8601
    timezone: str = "Asia/Shanghai"
    location: str = ""
    attendees: list[str] = None  # type: ignore
    organizer: str = ""
    reminders_minutes: list[int] = None  # type: ignore
    recurrence: str = ""          # RRULE 字符串
    conference_link: str = ""
    status: str = "confirmed"     # confirmed / tentative / cancelled

    def __post_init__(self) -> None:
        if self.attendees is None:
            self.attendees = []
        if self.reminders_minutes is None:
            self.reminders_minutes = []


@dataclass
class FreeBusySlot:
    """忙闲时段。"""
    start_time: str
    end_time: str
    busy: bool = True
    summary: str = ""


# ---------------------------------------------------------------------------
# 时间校验工具
# ---------------------------------------------------------------------------


def _parse_iso(ts: str) -> Optional[datetime]:
    """解析 ISO 8601 时间字符串(失败返回 None)。

    容忍带/不带时区、带/不带毫秒。仅做基本格式校验,不做时区转换。
    """
    if not isinstance(ts, str) or not ts:
        return None
    # 兼容 'Z' 结尾的 UTC 时间
    text = ts.rstrip("Z")
    try:
        # fromisoformat 不接受微秒末尾的非零省略,先尝试原样
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    # 尝试截取到秒
    try:
        return datetime.fromisoformat(text[:19])
    except ValueError:
        return None


def _validate_time_range(start: str, end: str) -> Optional[str]:
    """校验时间范围(start < end),返回错误描述(合法返回 None)。"""
    if not start or not end:
        return "start and end must not be empty"
    s = _parse_iso(start)
    e = _parse_iso(end)
    if s is None:
        return f"invalid start time format: {start!r} (expected ISO 8601)"
    if e is None:
        return f"invalid end time format: {end!r} (expected ISO 8601)"
    if s >= e:
        return f"start ({start}) must be earlier than end ({end})"
    return None


def detect_overlap(
    start_a: str,
    end_a: str,
    start_b: str,
    end_b: str,
) -> bool:
    """检测两个时间区间是否重叠(闭区间视为不含右端点,避免边界误判)。

    Args:
        start_a/end_a: 区间 A(ISO 8601)
        start_b/end_b: 区间 B(ISO 8601)

    Returns:
        True 表示重叠;False 表示不重叠或某区间格式非法(无法判定时保守返回 False)
    """
    sa, ea = _parse_iso(start_a), _parse_iso(end_a)
    sb, eb = _parse_iso(start_b), _parse_iso(end_b)
    if sa is None or ea is None or sb is None or eb is None:
        return False
    # 经典区间重叠判定:not (A.end <= B.start or A.start >= B.end)
    return sa < eb and sb < ea


# ---------------------------------------------------------------------------
# ScheduleProvider 抽象
# ---------------------------------------------------------------------------


class ScheduleProvider(BaseProvider):
    """日程 Provider 抽象基类。

    具体实现应捕获厂商 API 异常(如 googleapiclient.errors.HttpError、
    requests.RequestException),转为 ConnectorResult(success=False)。
    """

    @abc.abstractmethod
    def create_event(self, event: CalendarEvent) -> ConnectorResult:
        ...

    @abc.abstractmethod
    def list(
        self,
        start: str,
        end: str,
        calendar_id: Optional[str] = None,
        limit: int = 50,
    ) -> ConnectorResult:
        ...

    @abc.abstractmethod
    def update(self, event_id: str, updates: dict) -> ConnectorResult:
        ...

    @abc.abstractmethod
    def delete(self, event_id: str) -> ConnectorResult:
        ...

    @abc.abstractmethod
    def check_freebusy(
        self,
        emails: list[str],
        start: str,
        end: str,
    ) -> ConnectorResult:
        ...


# ---------------------------------------------------------------------------
# Stub 实现
# ---------------------------------------------------------------------------


class StubScheduleProvider(StubProvider, ScheduleProvider):
    """日程 stub 实现。

    返回值一致性:列表方法空结果 data=[];create_event 占位 ID 'stub-evt-<generated>'。
    """

    def create_event(self, event: CalendarEvent) -> ConnectorResult:
        return self._stub_result(
            data={"event_id": "stub-evt-<generated>", "title": event.title},
            action="create_event",
        )

    def list(
        self,
        start: str,
        end: str,
        calendar_id: Optional[str] = None,
        limit: int = 50,
    ) -> ConnectorResult:
        # 空结果统一 data=[]
        return self._stub_result(data=[], start=start, end=end)

    def update(self, event_id: str, updates: dict) -> ConnectorResult:
        return self._stub_result(
            data={"event_id": event_id, "updated_fields": list(updates.keys())},
            action="update",
        )

    def delete(self, event_id: str) -> ConnectorResult:
        return self._stub_result(data={"event_id": event_id, "deleted": True})

    def check_freebusy(
        self,
        emails: list[str],
        start: str,
        end: str,
    ) -> ConnectorResult:
        return self._stub_result(
            data=[FreeBusySlot(
                start_time=start, end_time=end, busy=False, summary="free",
            ).__dict__],
            emails=emails,
        )


# ---------------------------------------------------------------------------
# ScheduleConnector
# ---------------------------------------------------------------------------


class ScheduleConnector(WorkspaceConnector):
    """日程连接器。

    在委托 Provider 前校验时间范围(start < end),并对 create_event 提供
    overlap_check(可选)用于本地时间冲突预判。
    """

    @property
    def name(self) -> str:
        return "schedule"

    def _register_default_stub(self) -> None:
        self._providers["stub"] = StubScheduleProvider()

    # -- 业务方法 ------------------------------------------------------

    def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        location: str = "",
        attendees: Optional[list[str]] = None,
        timezone: str = "Asia/Shanghai",
        reminders_minutes: Optional[list[int]] = None,
        conference_link: str = "",
        recurrence: str = "",
        existing_events: Optional[list[dict]] = None,
    ) -> ConnectorResult:
        """创建日历事件。

        Args:
            title: 标题(非空)
            start_time/end_time: ISO 8601 时间(start < end)
            description: 描述
            location: 地点
            attendees: 参会者邮箱列表
            timezone: 时区
            reminders_minutes: 提醒分钟列表(如 [30, 10])
            conference_link: 视频会议链接
            recurrence: 重复规则(RRULE)
            existing_events: 可选,已有事件列表 [{start_time, end_time, ...}],
                             提供时本地做时间区间重叠检测,冲突则返回失败

        Returns:
            ConnectorResult(data={event_id, ...})
        """
        # 参数非空校验
        if not title or not title.strip():
            return ConnectorResult(success=False, error="title must not be empty")

        # 时间范围校验(start < end)
        range_err = _validate_time_range(start_time, end_time)
        if range_err is not None:
            return ConnectorResult(success=False, error=range_err)

        # 时间区间重叠检测(可选,需调用方提供 existing_events)
        if existing_events:
            for ev in existing_events:
                es = ev.get("start_time", "")
                ee = ev.get("end_time", "")
                if es and ee and detect_overlap(start_time, end_time, es, ee):
                    return ConnectorResult(
                        success=False,
                        error=f"time range overlaps with existing event "
                              f"{ev.get('event_id', ev.get('title', ''))!r} "
                              f"({es} ~ {ee})",
                    )

        err = self._ensure_connected()
        if err:
            return err
        event = CalendarEvent(
            title=title, start_time=start_time, end_time=end_time,
            description=description, location=location,
            attendees=attendees or [], timezone=timezone,
            reminders_minutes=reminders_minutes or [],
            conference_link=conference_link, recurrence=recurrence,
        )
        assert self._active_provider is not None
        try:
            return self._active_provider.create_event(event)
        except Exception as e:
            _logger.exception("schedule.create_event failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"create_event failed: {type(e).__name__}: {e}",
            )

    def list(
        self,
        start: str,
        end: str,
        calendar_id: Optional[str] = None,
        limit: int = 50,
    ) -> ConnectorResult:
        """列出时间区间内的事件。

        Args:
            start/end: ISO 8601 时间(start < end)
            calendar_id: 指定日历;None 主日历
            limit: 最多返回条数(自动 clamp 到 [1, 500])

        Returns:
            ConnectorResult(data=[CalendarEvent, ...]);空结果 data=[]
        """
        range_err = _validate_time_range(start, end)
        if range_err is not None:
            return ConnectorResult(success=False, error=range_err)
        safe_limit = max(1, min(limit, 500))

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.list(
                start=start, end=end, calendar_id=calendar_id, limit=safe_limit,
            )
        except Exception as e:
            _logger.exception("schedule.list failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"schedule list failed: {type(e).__name__}: {e}",
            )

    def update(self, event_id: str, **updates: Any) -> ConnectorResult:
        """更新事件字段。

        Args:
            event_id: 事件 ID(非空)
            updates: 待更新字段(title/start_time/end_time/...)
                     若同时提供 start_time/end_time,会校验时间范围

        Returns:
            ConnectorResult(data={event_id, updated_fields})
        """
        if not event_id:
            return ConnectorResult(success=False, error="event_id must not be empty")
        # 若更新涉及时间,校验范围
        if "start_time" in updates and "end_time" in updates:
            range_err = _validate_time_range(updates["start_time"], updates["end_time"])
            if range_err is not None:
                return ConnectorResult(success=False, error=range_err)
        elif "start_time" in updates or "end_time" in updates:
            return ConnectorResult(
                success=False,
                error="updating start_time and end_time together is required",
            )

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.update(event_id=event_id, updates=updates)
        except Exception as e:
            _logger.exception("schedule.update failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"schedule update failed: {type(e).__name__}: {e}",
            )

    def delete(self, event_id: str) -> ConnectorResult:
        """删除事件。

        Args:
            event_id: 事件 ID(非空)

        Returns:
            ConnectorResult(data={deleted: True})
        """
        if not event_id:
            return ConnectorResult(success=False, error="event_id must not be empty")
        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.delete(event_id=event_id)
        except Exception as e:
            _logger.exception("schedule.delete failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"schedule delete failed: {type(e).__name__}: {e}",
            )

    def check_freebusy(
        self,
        emails: list[str],
        start: str,
        end: str,
    ) -> ConnectorResult:
        """查询多个邮箱的忙闲时段。

        Args:
            emails: 参会者邮箱列表(非空)
            start/end: ISO 8601 时间区间(start < end)

        Returns:
            ConnectorResult(data=[FreeBusySlot, ...])
        """
        if not emails:
            return ConnectorResult(
                success=False, error="emails (attendees) must not be empty",
            )
        range_err = _validate_time_range(start, end)
        if range_err is not None:
            return ConnectorResult(success=False, error=range_err)

        err = self._ensure_connected()
        if err:
            return err
        assert self._active_provider is not None
        try:
            return self._active_provider.check_freebusy(
                emails=emails, start=start, end=end,
            )
        except Exception as e:
            _logger.exception("schedule.check_freebusy failed: %s: %s", type(e).__name__, e)
            return ConnectorResult(
                success=False,
                error=f"check_freebusy failed: {type(e).__name__}: {e}",
            )
