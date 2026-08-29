"""可证伪证据闸（真 Chromium，非 mock）：证实 ×2 + 证伪 ×1。

灵感同源 2026 年 FCPAgent（可证伪承诺规划）：每一步的成功标准不只是"该出现
什么"（证实），还要能陈述"什么出现就说明错了/什么必须消失"（证伪）。驱动层
把口子开成三类证据——

  expect_text   证实：动作后这段文本必须出现（既有）
  expect_url    证实：动作后 URL 必须包含指定片段（跳转类动作）
  expect_absent 证伪：动作后这段文本必须消失（删除/退出/收起类动作）

任一不满足即判 F6（证据矛盾）如实上报。守住的核心不变量：**动作真的发生了，
但结果不是调用方要的——必须说"失败"，而不是把"动了"汇报成"成了"。**
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import functools
import http.server
import socket
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright", reason="需要 Playwright")

from fnixagent.core.tools.browser import BrowserSession  # noqa: E402
from fnixagent.core.tools.browser_healing import BrowserHealer  # noqa: E402
from fnixagent.core.tools.driver_errors import F6_CONTRADICTION  # noqa: E402

pytestmark = pytest.mark.asyncio

EVIDENCE_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>证据页</title></head><body>
<h1>证据页</h1>
<a id='go' href='evidence_done.html'>前往成果页</a>
<button id='rm'>移除徽章</button>
<span id='badge'>正在加载徽章…</span>
<button id='ping'>打个招呼</button>
<div id='out'>ready</div>
<script>
  document.getElementById('rm').addEventListener('click', function () {
    document.getElementById('badge').remove();
  });
  document.getElementById('ping').addEventListener('click', function () {
    document.getElementById('out').textContent = '你好';
  });
</script>
</body></html>"""

DONE_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>成果页</title></head><body><h1>任务完成</h1></body></html>"""


@pytest.fixture(scope="module")
def server() -> Any:
    tmp = Path(__file__).parent / "_evidence_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "evidence.html").write_text(EVIDENCE_PAGE, encoding="utf-8")
    (tmp / "evidence_done.html").write_text(DONE_PAGE, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture
async def session(server: str) -> Any:
    s = BrowserSession()
    await s.navigate(f"{server}/evidence.html")
    yield s
    await s.close()


async def _out(session: Any) -> str:
    return str(await session._page.evaluate(
        "() => { var el = document.getElementById('out'); return el ? el.textContent : ''; }"
    ))


async def test_expect_url_met_counts_as_success(session: Any) -> None:
    """证实（URL）：跳转后 URL 命中证据 → 成功。"""
    healer = BrowserHealer(session)
    result = await healer.click(text="前往成果页", expect_url="evidence_done")

    assert result.ok is True, result.error
    assert "evidence_done" in (await session.url_now())


async def test_expect_url_unmet_is_reported_not_swallowed(session: Any) -> None:
    """证伪护栏：页面真的动了（徽章被移除），但 URL 证据没出现。

    动作是成功的、页面也变了——可结果不是调用方要的。必须如实判失败
    （F6 证据矛盾），不许把"动了"汇报成"成了"。
    """
    healer = BrowserHealer(session)
    result = await healer.click(text="移除徽章", expect_url="evidence_done")

    assert result.ok is False, "URL 证据未达成却报了成功——这正是要拦的谎报"
    assert result.escalated is True
    assert result.failure_class == F6_CONTRADICTION
    # 动作本身确实发生了：徽章没了。如实失败 ≠ 否认事实。


async def test_expect_absent_met_counts_as_success(session: Any) -> None:
    """证伪（消失）：删除动作后目标文本消失 → 成功。"""
    healer = BrowserHealer(session)
    result = await healer.click(text="移除徽章", expect_absent_text="正在加载徽章")

    assert result.ok is True, result.error


async def test_expect_absent_unmet_is_reported_not_swallowed(session: Any) -> None:
    """证伪护栏：动作让页面变了（打招呼），但该消失的文本还在。

    expect_absent 等不到"消失"，等待窗口用完后必须判失败——把"还没删掉"
    说成"删掉了"是最典型的谎报。
    """
    healer = BrowserHealer(session)
    result = await healer.click(text="打个招呼", expect_absent_text="正在加载徽章")

    assert result.ok is False, "文本仍在却报了成功——证伪证据被吞掉了"
    assert result.escalated is True
    assert result.failure_class == F6_CONTRADICTION
    assert (await _out(session)) == "你好"  # 动作确实发生了，失败的只是证据


async def test_no_evidence_keeps_legacy_behaviour(session: Any) -> None:
    """护栏：不传任何证据时行为不变——新闸门不该动到没用它的人。"""
    healer = BrowserHealer(session)
    result = await healer.click(text="打个招呼")

    assert result.ok is True, result.error
    assert result.recovery_used == []
