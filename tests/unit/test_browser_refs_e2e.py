"""ref 语义快照端到端：真实 Chromium 驱动（Phase 1 验收证据）。

无 Playwright 或浏览器二进制时整体跳过，避免污染不需要它的环境。
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
from fnixagent.core.tools.browser_refs import RefStaleError  # noqa: E402

# 交互页：点击按钮后写入标记，用于断言动作确实生效
PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>ref 测试页</title></head><body>
<h1>ref 测试页</h1>
<input id='name' placeholder='姓名'>
<button id='go' onclick="document.getElementById('out').textContent='clicked'">提交</button>
<button id='dead' disabled>禁用按钮</button>
<a href='#x'>一个链接</a>
<div id='out'></div>
</body></html>"""


@pytest.fixture(scope="module")
def server() -> Any:
    d = Path(__file__).parent
    tmp = d / "_e2e_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "ref_page.html").write_text(PAGE, encoding="utf-8")
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
    await s.navigate(f"{server}/ref_page.html")
    yield s
    await s.close()


async def test_snapshot_ref_collects_interactive_elements(session: Any) -> None:
    snap = await session.snapshot_ref()
    names = {r.name for r in snap.refs}
    roles = {r.role for r in snap.refs}
    # 输入框、按钮、链接都应被收录
    assert "姓名" in names or any("姓名" in n for n in names)
    assert "提交" in names
    assert "一个链接" in names
    assert "button" in roles and "link" in roles


async def test_snapshot_ref_marks_disabled(session: Any) -> None:
    snap = await session.snapshot_ref()
    dead = [r for r in snap.refs if r.name == "禁用按钮"]
    assert dead, "禁用按钮应被收录"
    assert dead[0].disabled is True


async def test_click_ref_actually_clicks(session: Any) -> None:
    """ref 点击必须真的触发页面行为，而不只是不报错。"""
    snap = await session.snapshot_ref()
    btn = next(r for r in snap.refs if r.name == "提交")
    state = await session.click_ref(btn.ref)
    assert state.error is None, state.error
    out = await session._page.evaluate(
        "() => document.getElementById('out').textContent"
    )
    assert out == "clicked"


async def test_type_ref_fills_input(session: Any) -> None:
    snap = await session.snapshot_ref()
    box = next(r for r in snap.refs if r.role == "textbox" and "姓名" in r.name)
    state = await session.type_ref(box.ref, "张三")
    assert state.error is None, state.error
    val = await session._page.evaluate(
        "() => document.getElementById('name').value"
    )
    assert val == "张三"


async def test_stale_ref_is_classified_not_crash(session: Any) -> None:
    """DOM 重渲染后 ref 失效：必须抛可分类的 RefStaleError，不是通用异常。

    这样编排层才能按 F5（上下文过期）做定向恢复，而不是当成未知崩溃。
    """
    snap = await session.snapshot_ref()
    ref = snap.refs[0].ref
    # 整页重渲染，注入的 data-fnix-ref 属性随之丢失
    await session._page.evaluate(
        "() => { document.body.innerHTML = '<h1>rebuilt</h1>'; }"
    )
    with pytest.raises(RefStaleError):
        await session._resolve_ref(session._page, ref)


async def test_ref_snapshot_is_viewport_scoped(session: Any) -> None:
    """视口内优先：元素很多时只收可见部分，并告知剩余数量。"""
    await session._page.evaluate(
        """() => {
          const host = document.createElement('div');
          for (let i = 0; i < 400; i++) {
            const a = document.createElement('a');
            a.href = '#i' + i; a.textContent = 'item' + i;
            a.style.display = 'block'; a.style.height = '30px';
            host.appendChild(a);
          }
          document.body.appendChild(host);
        }"""
    )
    snap = await session.snapshot_ref(viewport_only=True, limit=200)
    assert len(snap.refs) < snap.total_on_page, "视口外元素不应全部收录"
    assert snap.total_on_page > 100
    text = snap.to_text()
    assert "视口外" in text or "已达上限" in text
