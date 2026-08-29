"""
驱动路由器 — 统一驱动入口：能力探测、路由、降级、事件流（GUI_DRIVER_DESIGN.md P1）

职责（设计文档 §3.1 / §3.2）：
  - 能力探测：CDP endpoint 探测（9222/9223），供 L1 接管用户浏览器
  - 统一执行：computer.use syscall 路由到浏览器（L1/L2）或桌面（L3）
  - 降级事件：降级必须是显式事件（两条铁律之一），全量落盘审计
  - 审计：driver_events.jsonl 一行一事件，安全合规 + agent 行为数据一鱼两吃

事件格式（与前端时间线、审计文件共用）：
  {id, ts, session, driver_mode, action, target, ok, degraded, error, confirmations}
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_logger = logging.getLogger(__name__)

# 事件缓冲上限（环形，给前端时间线增量拉取）
_MAX_EVENTS = 200
# 连续失败多少次触发整体降级（设计文档 §2.2 铁律 2：失败不逐动作回退）
_FAILURE_THRESHOLD = 2
# 审计落盘路径（~/.local/share/fnixagent/driver_events.jsonl）
_AUDIT_FILE = Path.home() / ".local" / "share" / "fnixagent" / "driver_events.jsonl"
# CDP 探测超时（秒）——设计文档 §3.1：2 秒
_CDP_PROBE_TIMEOUT = 2.0

# 浏览器类 op → BrowserSession 方法（computer.use 的 L1/L2 路由表）
_BROWSER_OPS = {
    "navigate",
    "click",
    "type",
    "scroll",
    "snapshot",
    "screenshot",
    "read",
    "history",
}


@dataclass
class DriverEvent:
    """驱动事件（前端时间线 + 审计落盘共用格式）。"""

    id: int
    ts: float
    session: str = ""
    driver_mode: str = "none"  # none | cdp-attach | managed | desktop
    action: str = ""
    target: str = ""
    ok: bool = True
    degraded: bool = False
    error: str | None = None
    confirmations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "session": self.session,
            "driver_mode": self.driver_mode,
            "action": self.action,
            "target": self.target,
            "ok": self.ok,
            "degraded": self.degraded,
            "error": self.error,
            "confirmations": self.confirmations,
        }


@dataclass
class ExecuteResult:
    """统一执行结果（三个驱动都收敛到这一套）。"""

    ok: bool
    summary: str = ""
    degraded: bool = False
    driver_mode: str = "none"
    error: str | None = None
    screenshot_b64: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "degraded": self.degraded,
            "driver_mode": self.driver_mode,
            "error": self.error,
            "meta": self.meta,
        }


def _probe_endpoint(url: str) -> bool:
    """同步探测单个 CDP /json/version 端点（在 to_thread 中执行）。"""
    try:
        with urllib.request.urlopen(url, timeout=_CDP_PROBE_TIMEOUT) as resp:
            json.loads(resp.read().decode("utf-8", "replace"))
            return True
    except Exception:  # noqa: BLE001
        return False


# CDP 端点归属：
#   builtin = 我们自己的真实渲染窗口（Tauri WebView），attach 的语义是
#             **接管用户正在看的那个页面**——真实渲染的全部意义就在这里；
#             新开 tab 会让 AI 在一个用户看不见的页面里自说自话。
#   user    = 接管用户日常浏览器（9222/9223 那类）。那里装着用户全部登录态，
#             隔离纪律要求只在自己 new_page() 出来的 tab 里活动，绝不碰已有标签页。
ATTACH_BUILTIN = "builtin"
ATTACH_USER = "user"


@dataclass(frozen=True)
class CdpTarget:
    """一个可用的 CDP 端点及其归属。

    `kind` 决定 BrowserSession 用哪种 attach 语义，两者不可混用：
    在用户浏览器里"接管可见页面"等于抢用户的标签页；在自建真实渲染窗口里
    "新开 tab"等于让 AI 和用户各看各的。
    """

    endpoint: str
    kind: str = ATTACH_USER

    @property
    def is_builtin(self) -> bool:
        return self.kind == ATTACH_BUILTIN


class DriverRouter:
    """统一驱动入口：能力探测、路由、降级、事件流。

    线程/协程安全：事件缓冲与审计写入用 asyncio.Lock 串行化。
    降级铁律（设计文档 §2.2）：
      1. 降级是显式事件——切换驱动必须 emit 一条 driver_mode 变更事件
      2. 失败不逐动作回退——连续 _FAILURE_THRESHOLD 次失败整体切换，不在单个动作上横跳
    """

    def __init__(self) -> None:
        self._events: list[DriverEvent] = []
        self._next_id = 0
        self._lock = asyncio.Lock()
        self._failures: dict[str, int] = {}
        self._waiters: list[asyncio.Future] = []
        # 桌面驱动调用处理器（由 desktop.py 注册，避免循环 import）
        self._desktop_handler: Callable[..., Any] | None = None
        # 内置真实渲染窗口的 CDP 端口（Phase 4，动态分配，由前端告知）
        self._builtin_cdp_port: int | None = None

    # -- 事件流 ---------------------------------------------------------

    async def emit(self, event: DriverEvent) -> None:
        """追加事件到环形缓冲 + 落盘审计 + 唤醒等待者。"""
        if event.id <= 0:
            self._next_id += 1
            event.id = self._next_id
        if event.ts <= 0:
            event.ts = time.time()
        async with self._lock:
            self._events.append(event)
            if len(self._events) > _MAX_EVENTS:
                self._events = self._events[-_MAX_EVENTS:]
            # 唤醒 wait_event 的等待者
            waiters = self._waiters
            self._waiters = []
            for w in waiters:
                if not w.done():
                    w.set_result(True)
        self._audit_write(event)

    def _audit_write(self, event: DriverEvent) -> None:
        """审计落盘（同步小写，失败只记日志不抛异常）。"""
        try:
            _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _AUDIT_FILE.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            _logger.debug("driver event audit write failed: %s", e)

    async def recent_events(self, since_id: int = 0) -> tuple[list[dict[str, Any]], int]:
        """增量拉取事件（since_id 之后的新事件，用于前端时间线）。"""
        async with self._lock:
            out = [e.to_dict() for e in self._events if e.id > since_id]
            last_id = self._events[-1].id if self._events else since_id
            return out, last_id

    # -- 能力探测 -------------------------------------------------------

    def set_builtin_cdp_port(self, port: int | None) -> None:
        """登记内置浏览器窗口的 CDP 端口（Phase 4 真实渲染）。

        由前端在打开真实渲染窗口后调用。端口是动态分配的，所以不能靠猜，
        必须由桌面端告知。
        """
        self._builtin_cdp_port = int(port) if port else None

    @property
    def builtin_cdp_port(self) -> int | None:
        return self._builtin_cdp_port

    async def probe_cdp_target(
        self, ports: tuple[int, ...] = (9222, 9223)
    ) -> CdpTarget | None:
        """探测 CDP 端点，连归属一起返回。

        优先级：**内置真实渲染窗口 > 用户浏览器**。

        内置窗口优先的理由有两层。安全和性能之外还有一层更硬的——只有内置
        窗口才能兑现"AI 与用户看到同一个页面"这个承诺：那是我们的窗口，接管
        它的可见页面不会打扰任何人。而接管用户浏览器意味着必须在一个装着用户
        全部登录态的浏览器里活动，只能老实待在自己 new_page() 出来的 tab 里。

        实测依据：评估报告 §2.1，Chrome 151 Protocol 1.3 全通。
        """
        builtin = getattr(self, "_builtin_cdp_port", None)
        if builtin:
            url = f"http://127.0.0.1:{builtin}/json/version"
            if await asyncio.to_thread(_probe_endpoint, url):
                return CdpTarget(f"http://127.0.0.1:{builtin}", ATTACH_BUILTIN)
        for port in ports:
            url = f"http://127.0.0.1:{port}/json/version"
            if await asyncio.to_thread(_probe_endpoint, url):
                return CdpTarget(f"http://127.0.0.1:{port}", ATTACH_USER)
        return None

    async def probe_cdp(self, ports: tuple[int, ...] = (9222, 9223)) -> str | None:
        """探测 CDP 端点，只返回地址（不关心归属时用这个）。"""
        target = await self.probe_cdp_target(ports)
        return target.endpoint if target else None

    # -- 失败计数 / 降级 ------------------------------------------------

    async def record_failure(self, mode: str) -> bool:
        """记录一次驱动失败；返回是否达到降级阈值（触发整体切换）。"""
        async with self._lock:
            self._failures[mode] = self._failures.get(mode, 0) + 1
            return self._failures[mode] >= _FAILURE_THRESHOLD

    async def reset_failures(self, mode: str | None = None) -> None:
        """清零失败计数（成功执行或显式切换驱动后调用）。"""
        async with self._lock:
            if mode is None:
                self._failures.clear()
            else:
                self._failures.pop(mode, None)

    # -- 桌面驱动注册 ---------------------------------------------------

    def register_desktop_handler(self, handler: Callable[..., Any]) -> None:
        """注册桌面驱动调用处理器（desktop.py 在注册工具时调用）。"""
        self._desktop_handler = handler

    # -- 统一执行 -------------------------------------------------------

    async def execute(self, action: dict[str, Any]) -> ExecuteResult:
        """computer.use 统一入口：按 op 路由到浏览器或桌面驱动。"""
        op = str(action.get("op", "") or "").strip()
        if not op:
            return ExecuteResult(ok=False, error="computer.use 需要 op 参数")

        if op in _BROWSER_OPS:
            return await self._execute_browser(op, action)
        if op.startswith("desktop_"):
            return await self._execute_desktop(op, action)
        return ExecuteResult(ok=False, error=f"未知驱动操作: {op}")

    async def _execute_browser(self, op: str, action: dict[str, Any]) -> ExecuteResult:
        """浏览器 op → BrowserSession 方法（L1/L2）。延迟 import 防循环。"""
        try:
            from fnixagent.core.tools.browser import BrowserSession
        except Exception as e:  # noqa: BLE001
            return ExecuteResult(ok=False, error=f"浏览器驱动不可用: {e}")
        session = BrowserSession.instance()
        try:
            if op == "navigate":
                st = await session.navigate(str(action.get("url") or action.get("target") or ""))
            elif op == "click":
                text = action.get("text")
                if text:
                    st = await session.click_text(str(text))
                else:
                    st = await session.click(int(action.get("x", 0)), int(action.get("y", 0)))
            elif op == "type":
                text = str(action.get("text", ""))
                into = action.get("into") or action.get("target")
                submit = bool(action.get("submit", False))
                st = await session.type_into(text, str(into), submit) if into else await session.type_text(text, submit)
            elif op == "scroll":
                st = await session.scroll(str(action.get("direction", "down")), int(action.get("amount", 480)))
            elif op == "history":
                st = await session.history(str(action.get("op", "back")))
            elif op == "screenshot":
                st = await session.screenshot()
            elif op == "snapshot":
                text = await session.snapshot()
                return ExecuteResult(ok=True, summary=text, driver_mode=session.mode)
            elif op == "read":
                text = await session.page_text(int(action.get("max_chars", 4000)))
                return ExecuteResult(ok=True, summary=text, driver_mode=session.mode)
            else:
                return ExecuteResult(ok=False, error=f"未知浏览器操作: {op}")
            # BrowserState → ExecuteResult
            summary = f"当前页面: {st.title or '(无标题)'}\nURL: {st.url or '(空)'}"
            if st.error:
                summary = f"失败: {st.error}"
            return ExecuteResult(
                ok=not st.error,
                summary=summary,
                degraded=False,
                driver_mode=session.mode,
                error=st.error,
                screenshot_b64=st.screenshot_b64 or None,
            )
        except Exception as e:  # noqa: BLE001
            return ExecuteResult(ok=False, error=f"{op} 执行失败: {e}")

    async def _execute_desktop(self, op: str, action: dict[str, Any]) -> ExecuteResult:
        """桌面 op → DesktopDriver（L3）。handler 由 desktop.py 注册。"""
        if self._desktop_handler is None:
            return ExecuteResult(ok=False, error="桌面驱动未注册（cua-driver 未安装？）")
        try:
            return await self._desktop_handler(op, action)
        except Exception as e:  # noqa: BLE001
            return ExecuteResult(ok=False, error=f"{op} 执行失败: {e}")


_router: DriverRouter | None = None


def get_driver_router() -> DriverRouter:
    """获取进程级单例。"""
    global _router
    if _router is None:
        _router = DriverRouter()
    return _router


def reset_driver_router_for_tests() -> DriverRouter:
    """测试用：重建单例。"""
    global _router
    _router = DriverRouter()
    return _router
