"""反爬指纹掩藏 + 人类化动作（真 Chromium，非 mock）。

真实站点按 `navigator.webdriver` 与"单次大位移滚动"识别自动化——前者直接把
我们拦在门外，后者是让 agent"不像人在用浏览器"的最大特征。这两条护栏：

  1. 托管模式下 `navigator.webdriver` 必须不出现（反爬最基础指纹）；
  2. 滚动必须拆成多个滚轮事件，且总位移分毫不差——拟人化不许以改变语义
     为代价（向上滚就是负位移，总量必须守恒）。
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

pytestmark = pytest.mark.asyncio

PROBE_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>指纹探针</title></head><body>
<div style='height:4000px'>高页面，保证能滚动</div>
<div id='out'></div>
<script>
  window.__wheels = [];
  window.addEventListener('wheel', function (e) {
    window.__wheels.push(e.deltaY);
  });
  document.getElementById('out').textContent = JSON.stringify({
    webdriver: navigator.webdriver,
    languages: navigator.languages,
    plugins: navigator.plugins.length,
    chrome: typeof window.chrome,
  });
</script>
</body></html>"""


@pytest.fixture(scope="module")
def server() -> Any:
    tmp = Path(__file__).parent / "_humanlike_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "probe.html").write_text(PROBE_PAGE, encoding="utf-8")
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
    await s.navigate(f"{server}/probe.html")
    yield s
    await s.close()


async def test_webdriver_flag_is_hidden(session: Any) -> None:
    """托管模式下 navigator.webdriver 不得出现——反爬的第一道指纹。

    注意断言写法：JSON.stringify 会把值为 undefined 的键整个丢掉，所以
    "键缺失"恰恰证明掩藏成功。这里读原始值再归一化判断，避免被序列化
    语义误导。
    """
    raw = await session._page.evaluate(
        "() => ({ wd: navigator.webdriver, langs: navigator.languages,"
        " plugs: navigator.plugins.length, chrome: typeof window.chrome })"
    )
    assert raw["wd"] in (None, False), (
        f"navigator.webdriver 暴露了（{raw['wd']!r}）——会被反爬直接拦截"
    )
    # 伴随指纹也要像普通浏览器：语言非空、插件非空、window.chrome 存在
    assert raw["langs"], "navigator.languages 为空"
    assert raw["plugs"] > 0, "navigator.plugins 为空"
    assert raw["chrome"] == "object", "window.chrome 缺失"


async def test_scroll_is_broken_into_human_like_steps(session: Any) -> None:
    """一次 scroll 必须拆成多个小滚轮事件，且总位移精确守恒。"""
    state = await session.scroll("down", 1000)
    assert state.error is None, state.error

    wheels = await session._page.evaluate("() => window.__wheels")
    assert len(wheels) >= 2, f"滚动被一次性发出（{len(wheels)} 个事件）——非人类形态"
    assert all(w > 0 for w in wheels), "向下滚动不应出现负位移"
    assert sum(wheels) == 1000, f"总位移不守恒: {sum(wheels)} != 1000"
    assert max(wheels) <= 320, f"单步位移过大（{max(wheels)}），不像滚轮"


async def test_scroll_up_sign_is_preserved(session: Any) -> None:
    """反向护栏：向上滚是负位移——拟人化不许改变方向语义。"""
    await session.scroll("down", 800)  # 先滚下去才有空间往上滚
    await session._page.evaluate("() => { window.__wheels = []; }")
    state = await session.scroll("up", 500)
    assert state.error is None, state.error

    wheels = await session._page.evaluate("() => window.__wheels")
    assert len(wheels) >= 1
    assert all(w < 0 for w in wheels), "向上滚动必须是负位移"
    assert sum(wheels) == -500, f"向上总位移不守恒: {sum(wheels)} != -500"
