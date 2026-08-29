"""跨 frame 寻址（真 Chromium，非 mock）。

把"看得见但够不着"的盲区变成能力：同源/跨域帧内的可交互元素并入快照，
按 @ref 直接操作（解析侧经 frame_locator 链，对调用方透明）。三条纪律护栏：

  1. 帧内点击/输入必须真实生效，且 `changed` 如实反映（签名覆盖帧内容，
     不许把"点对了"误判成"没反应"）；
  2. 超出寻址深度上限的帧如实报告"未覆盖"，不许假装世界是平的；
  3. 页面重载后帧内 ref 失效必须按 F5（上下文过期）上报，不许静默。
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
from fnixagent.core.tools.driver_errors import F5_STALE_CONTEXT  # noqa: E402

pytestmark = pytest.mark.asyncio

OUTER = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>外层</title></head><body>
<h1>外层页面</h1>
<button id='outer-btn'>外层按钮</button>
<iframe id='fr' src='fx_inner.html' width='680' height='260'
        style='border:1px solid #ddd;margin-top:16px'></iframe>
</body></html>"""

INNER = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>帧内</title></head><body>
<button id='inner-btn' onclick="document.getElementById('st').textContent='已生效'">帧内按钮</button>
<input id='inner-in' placeholder='帧内输入框'>
<div id='st'>未生效</div>
</body></html>"""

# 深度链：host → d1 → d2 → d3 → d4（d4 超出寻址深度上限）
HOST_DEEP = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>深嵌宿主</title></head><body>
<h1>深嵌宿主</h1>
<button id='host-btn'>宿主按钮</button>
<iframe src='fx_d1.html' width='680' height='300' style='border:1px solid #ddd'></iframe>
</body></html>"""

_DEEP_TPL = (
    "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
    "<title>{t}</title></head><body><p>{label}</p>"
    "<iframe src='{src}' width='600' height='{h}' style='border:1px solid #eee'></iframe>"
    "</body></html>"
)

D4 = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>d4</title></head><body>
<button id='deep-btn'>深层按钮</button>
</body></html>"""


def _deep(level: int) -> str:
    return _DEEP_TPL.format(
        t=f"d{level}", label=f"第 {level} 层框架",
        src=f"fx_d{level + 1}.html", h=max(120, 300 - 60 * level),
    )


@pytest.fixture(scope="module")
def server() -> Any:
    tmp = Path(__file__).parent / "_frames_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "fx_outer.html").write_text(OUTER, encoding="utf-8")
    (tmp / "fx_inner.html").write_text(INNER, encoding="utf-8")
    (tmp / "fx_host.html").write_text(HOST_DEEP, encoding="utf-8")
    (tmp / "fx_d1.html").write_text(_deep(1), encoding="utf-8")
    (tmp / "fx_d2.html").write_text(_deep(2), encoding="utf-8")
    (tmp / "fx_d3.html").write_text(_deep(3), encoding="utf-8")
    (tmp / "fx_d4.html").write_text(D4, encoding="utf-8")
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
    await s.navigate(f"{server}/fx_outer.html")
    # 帧内容异步加载——用跨帧文本等待它出现（这本身也顺带验证了 wait_for 跨帧）
    st = await s.wait_for(text="帧内按钮", timeout_ms=5_000)
    assert st.error is None, f"帧内容未就绪: {st.error}"
    yield s
    await s.close()


async def test_snapshot_covers_same_origin_frame(session: Any) -> None:
    """快照必须把帧内元素一并枚举：带帧路径、坐标是整页绝对值。

    坐标断言不依赖版式假设，直接对表真实几何：帧内元素的快照坐标必须等于
    "iframe 绝对偏移 + 帧内局部坐标"，帧外元素必须等于其自身 rect——
    这才验证了绝对偏移的换算，而不是碰巧的上下关系。
    """
    snap = await session.snapshot_ref()
    names = [r.name for r in snap.refs]
    assert "外层按钮" in names
    assert "帧内按钮" in names, "同源帧内元素未被快照枚举"

    inner = next(r for r in snap.refs if r.name == "帧内按钮")
    outer = next(r for r in snap.refs if r.name == "外层按钮")
    assert inner.frame, "帧内元素必须带帧路径"
    assert not outer.frame

    # 帧外：快照坐标 == 元素自身 rect 中心
    orect = await session._page.evaluate(
        """() => { const b = document.getElementById('outer-btn').getBoundingClientRect();
                    return {cx: b.x + b.width / 2, cy: b.y + b.height / 2}; }"""
    )
    assert abs(outer.x - round(orect["cx"])) <= 1
    assert abs(outer.y - round(orect["cy"])) <= 1

    # 帧内：快照坐标 == iframe 绝对偏移 + 帧内局部坐标
    frame1 = session._page.frames[1]
    irect = await frame1.evaluate(
        """() => { const b = document.getElementById('inner-btn').getBoundingClientRect();
                    return {cx: b.x + b.width / 2, cy: b.y + b.height / 2}; }"""
    )
    box = await (await frame1.frame_element()).bounding_box()
    assert abs(inner.x - round(box["x"] + irect["cx"])) <= 1, "帧内元素 x 未换算成绝对坐标"
    assert abs(inner.y - round(box["y"] + irect["cy"])) <= 1, "帧内元素 y 未换算成绝对坐标"


async def test_click_ref_inside_frame_really_happens(session: Any) -> None:
    """点击帧内按钮必须真实生效，且 changed 如实为真。"""
    snap = await session.snapshot_ref()
    inner = next(r for r in snap.refs if r.name == "帧内按钮")

    state = await session.click_ref(inner.ref)
    assert state.error is None, state.error
    assert state.changed, "帧内变化未被 changed 捕获——会把点对误判成没反应"

    status = await session._page.frames[1].evaluate(
        "() => document.getElementById('st').textContent"
    )
    assert status == "已生效"


async def test_type_ref_inside_frame(session: Any) -> None:
    """输入也要能进帧内的控件。"""
    snap = await session.snapshot_ref()
    box = next(r for r in snap.refs if r.name == "帧内输入框")

    state = await session.type_ref(box.ref, "跨帧输入")
    assert state.error is None, state.error

    value = await session._page.frames[1].evaluate(
        "() => document.getElementById('inner-in').value"
    )
    assert value == "跨帧输入"


async def test_healer_expect_gate_reaches_into_frames(session: Any) -> None:
    """expect 证据闸要能看见帧内的结果——否则帧内操作全被误判失败。"""
    snap = await session.snapshot_ref()
    inner = next(r for r in snap.refs if r.name == "帧内按钮")

    healer = BrowserHealer(session)
    result = await healer.click(ref=inner.ref, expect_text="已生效")
    assert result.ok is True, result.error


async def test_deep_frame_reports_blind_spot_honestly(server: str) -> None:
    """反向护栏：超出深度上限的帧必须如实报告未覆盖，不许假装看得见。"""
    s = BrowserSession()
    try:
        await s.navigate(f"{server}/fx_host.html")
        await s.wait_for(text="深层按钮", timeout_ms=5_000)
        snap = await s.snapshot_ref()

        names = [r.name for r in snap.refs]
        assert "宿主按钮" in names
        assert "深层按钮" not in names, "超出深度上限的帧元素不该被枚举"

        assert any(not f.get("covered") for f in snap.frames), (
            "未覆盖的帧必须被如实报告，而不是静默吞掉"
        )
        assert "未覆盖" in snap.to_text()
    finally:
        await s.close()


async def test_stale_frame_ref_recovers_or_reports_f5(
    session: Any, server: str
) -> None:
    """页面重载让帧寻址属性一并消失后，旧 ref 的两种下场都必须如实：

    - 同名元素还在（重载同一页）→ refresh 按名重映射成功，恢复要留痕
      （记录里必须有 F5 + refresh），不许静默；
    - 同名元素不在了（换到没有它的页面）→ 重映射无路，如实升级失败，
      归类必须是 F5 上下文过期，不许混进别的故障类。
    """
    from fnixagent.core.tools.orchestrator import REFRESH

    snap = await session.snapshot_ref()
    inner = next(r for r in snap.refs if r.name == "帧内按钮")

    # 情形一：重载同一页——名字还在，恢复成功但必须留痕
    await session.navigate(f"{server}/fx_outer.html")
    await session.wait_for(text="帧内按钮", timeout_ms=5_000)
    healer = BrowserHealer(session)
    result = await healer.click(ref=inner.ref)
    assert result.ok is True, result.error
    rows = [r.to_dict() for r in result.records]
    assert any(r.get("failure_class") == F5_STALE_CONTEXT for r in rows), (
        "失效应先被归类为 F5 并记录在案"
    )
    assert REFRESH in result.recovery_used, "恢复路径必须记录在案，不许静默"

    # 情形二：去没有该元素的页面——重映射无路，如实升级
    healer2 = BrowserHealer(session)
    await session.navigate(f"{server}/fx_host.html")
    await session.wait_for(text="宿主按钮", timeout_ms=5_000)
    result2 = await healer2.click(ref=inner.ref)
    assert result2.ok is False, "元素已不存在，不许报成功"
    assert result2.escalated is True
    assert result2.failure_class == F5_STALE_CONTEXT, (
        f"帧内 ref 失效应归 F5 上下文过期，实际 {result2.failure_class}"
    )


async def test_snapshot_refresh_leaves_no_stale_attrs(session: Any) -> None:
    """护栏：重新快照后，帧文档里只允许当前快照的属性，不许有残留。"""
    snap1 = await session.snapshot_ref()
    frame_refs = {r.ref for r in snap1.refs if r.frame}
    assert frame_refs, "前置条件：快照里有帧内元素"

    snap2 = await session.snapshot_ref()
    frame = session._page.frames[1]
    leftovers = await frame.evaluate(
        """() => Array.from(document.querySelectorAll('[data-fnix-ref]'))
                  .map(el => el.getAttribute('data-fnix-ref'))"""
    )
    current = {r.ref for r in snap2.refs if r.frame}
    assert set(leftovers) == current, (
        f"帧内存在快照外的残留属性: {set(leftovers) - current}"
    )
