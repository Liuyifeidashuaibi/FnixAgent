"""感知层盲区 · 端到端（真实 Chromium）。

这组用例守的是"看得见"这件事本身。快照看不见的元素，模型就永远不会去点，
而且它不知道自己不知道——这是感知层最危险的失败形态：不报错、不失败，
只是那个按钮从来没出现在上下文里。

三件事：

1. **Shadow DOM**：Web Components 的按钮不在 document 树里，不做递归就永远
   扫不到。表现为"页面上明明有个按钮，AI 说没有"，用户会认为 AI 在胡说。
2. **被遮挡的元素**：固定顶栏/弹窗下面的按钮，点下去事件被上面那层接走。
   不标记的话，驱动层可能一句错都不报，模型以为自己点成功了。
3. **iframe 盲区**：不枚举 frame 内元素，但必须把"那里有 N 个元素"说出来。
   静默的盲区比显式的能力缺口危险。

每条都配了一条反向护栏——尤其是 obscured：一个把所有元素都标成遮挡的实现
照样能通过"能标出来"的测试，却让标记失去意义。
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

# Shadow DOM 页：按钮藏在 open shadow root 里，light DOM 的 querySelectorAll 扫不到
SHADOW_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>shadow</title></head><body>
<h1>组件页</h1>
<my-widget></my-widget>
<script>
class Widget extends HTMLElement {
  connectedCallback() {
    const root = this.attachShadow({mode: 'open'});
    root.innerHTML = `
      <button id='inner'>加入购物车</button>
      <input id='q' placeholder='组件内搜索'>`;
    root.getElementById('inner').addEventListener('click', () => {
      window.__clicked = true;
    });
  }
}
customElements.define('my-widget', Widget);
</script>
</body></html>"""

# 遮挡页：固定顶栏压在一个按钮上；另一个按钮完全没被压
OVERLAY_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>overlay</title>
<style>
  body { margin: 0; }
  #bar { position: fixed; top: 0; left: 0; width: 100%; height: 60px;
         background: #333; color: #fff; z-index: 999; }
  #covered { position: absolute; top: 0px; left: 20px; width: 200px; height: 60px; }
  #free { position: absolute; top: 300px; left: 20px; width: 200px; height: 60px; }
</style></head><body>
<div id='bar'>固定顶栏</div>
<button id='covered'>被顶栏压住的按钮</button>
<button id='free'>没被压住的按钮</button>
</body></html>"""

# iframe 页：同源 iframe 里放两个可交互元素
FRAME_INNER = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>inner</title></head><body>
<button>框架内按钮</button>
<input placeholder='框架内输入'>
</body></html>"""

FRAME_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>frame</title></head><body>
<h1>外层</h1>
<button id='outer'>外层按钮</button>
<iframe src='frame_inner.html' width='600' height='300'></iframe>
</body></html>"""

# 画布页：主体内容画在 canvas 上，DOM 里一个可交互元素都没有。
# 这是 Playwright MCP 一类方案的公开弱点，也是编造答案的高发场景。
CANVAS_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>canvas</title>
<style>body{margin:0}canvas{display:block}</style></head><body>
<canvas id='stage' width='1200' height='700'></canvas>
<script>
  const c = document.getElementById('stage');
  const g = c.getContext('2d');
  g.fillStyle = '#123'; g.fillRect(0, 0, 1200, 700);
  g.fillStyle = '#fff'; g.font = '28px sans-serif';
  g.fillText('这里是画布内容，DOM 里什么都没有', 60, 120);
</script>
</body></html>"""

# 同样是画布页，但配了几个真按钮：验证"快照非空"时盲区提示不会漏掉
CANVAS_CHROME_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>canvas chrome</title>
<style>body{margin:0}canvas{display:block}</style></head><body>
<button id='zoom'>放大</button>
<canvas id='stage' width='1000' height='600'></canvas>
<script>
  const g = document.getElementById('stage').getContext('2d');
  g.fillStyle = '#234'; g.fillRect(0, 0, 1000, 600);
</script>
</body></html>"""

# 小画布（图标尺寸）不该被当成盲区
CANVAS_SMALL_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>icon</title></head><body>
<canvas width='32' height='32'></canvas>
<button id='go'>开始</button>
</body></html>"""

# 折叠面板：内容藏在 summary 后面，不展开就看不见
DISCLOSURE_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>disclosure</title></head><body>
<details id='spec'><summary>规格参数</summary>
  <button id='inner'>加入购物车</button>
</details>
</body></html>"""


@pytest.fixture(scope="module")
def server() -> Any:
    d = Path(__file__).parent / "_perception_tmp"
    d.mkdir(exist_ok=True)
    (d / "shadow.html").write_text(SHADOW_PAGE, encoding="utf-8")
    (d / "overlay.html").write_text(OVERLAY_PAGE, encoding="utf-8")
    (d / "frame.html").write_text(FRAME_PAGE, encoding="utf-8")
    (d / "frame_inner.html").write_text(FRAME_INNER, encoding="utf-8")
    (d / "canvas.html").write_text(CANVAS_PAGE, encoding="utf-8")
    (d / "canvas_chrome.html").write_text(CANVAS_CHROME_PAGE, encoding="utf-8")
    (d / "canvas_small.html").write_text(CANVAS_SMALL_PAGE, encoding="utf-8")
    (d / "disclosure.html").write_text(DISCLOSURE_PAGE, encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture
async def session(server: str) -> Any:
    s = BrowserSession()
    yield s
    await s.close()


# ── Shadow DOM ─────────────────────────────────────────────────────────


async def test_shadow_dom_button_is_visible(session: Any, server: str) -> None:
    """Web Components 里的按钮必须在快照里出现——否则模型永远不会去点它。"""
    await session.navigate(f"{server}/shadow.html")
    snap = await session.snapshot_ref()

    names = [r.name for r in snap.refs]
    assert "加入购物车" in names, f"shadow root 内的按钮没被快照看到: {names}"


async def test_shadow_dom_element_is_flagged(session: Any, server: str) -> None:
    await session.navigate(f"{server}/shadow.html")
    snap = await session.snapshot_ref()

    inner = [r for r in snap.refs if r.name == "加入购物车"]
    assert inner and inner[0].in_shadow is True


async def test_shadow_dom_button_is_clickable_by_ref(session: Any, server: str) -> None:
    """看见只是第一步，按 ref 真能点中才算数（Playwright 穿透 open shadow root）。"""
    await session.navigate(f"{server}/shadow.html")
    snap = await session.snapshot_ref()

    target = next(r for r in snap.refs if r.name == "加入购物车")
    state = await session.click_ref(target.ref)

    assert not state.error, state.error
    clicked = await session._page.evaluate("() => window.__clicked === true")
    assert clicked is True, "点了但事件没触发——ref 解析没穿透 shadow root"


async def test_shadow_dom_counts_toward_total(session: Any, server: str) -> None:
    """shadow 内的元素要计入页面总数，否则"视口外还有 N 个"的提示会算错。"""
    await session.navigate(f"{server}/shadow.html")
    snap = await session.snapshot_ref()

    assert snap.total_on_page >= 2, snap.total_on_page


# ── 遮挡 ───────────────────────────────────────────────────────────────


async def test_obscured_element_is_flagged(session: Any, server: str) -> None:
    """顶栏压住的按钮必须标记出来：点下去事件会被顶栏接走。"""
    await session.navigate(f"{server}/overlay.html")
    snap = await session.snapshot_ref()

    covered = next((r for r in snap.refs if r.name == "被顶栏压住的按钮"), None)
    assert covered is not None, [r.name for r in snap.refs]
    assert covered.obscured is True


async def test_unobscured_element_is_not_flagged(session: Any, server: str) -> None:
    """护栏：把所有元素都标成遮挡的实现照样能过上一条测试，但标记就废了。"""
    await session.navigate(f"{server}/overlay.html")
    snap = await session.snapshot_ref()

    free = next((r for r in snap.refs if r.name == "没被压住的按钮"), None)
    assert free is not None, [r.name for r in snap.refs]
    assert free.obscured is False


# ── iframe 盲区 ────────────────────────────────────────────────────────


async def test_same_origin_frame_is_reported(session: Any, server: str) -> None:
    """不枚举 frame 内元素，但必须让调用方知道那里有东西。"""
    await session.navigate(f"{server}/frame.html")
    snap = await session.snapshot_ref()

    assert snap.frames, "iframe 盲区没被报告"
    reachable = [f for f in snap.frames if f.get("reachable")]
    assert reachable, snap.frames
    assert snap.hidden_frame_count >= 2, snap.hidden_frame_count


async def test_frame_blind_spot_is_in_snapshot_text(session: Any, server: str) -> None:
    """提示必须真的出现在模型读到的文本里——写在字段里但没人读等于没有。"""
    await session.navigate(f"{server}/frame.html")
    snap = await session.snapshot_ref()

    text = snap.to_text()
    assert "iframe" in text, text
    assert "未覆盖" in text, text


async def test_outer_elements_still_enumerated(session: Any, server: str) -> None:
    """报告盲区的同时，外层元素照常要能拿到。"""
    await session.navigate(f"{server}/frame.html")
    snap = await session.snapshot_ref()

    assert "外层按钮" in [r.name for r in snap.refs]


# ── Canvas / WebGL 盲区 ────────────────────────────────────────────────


async def test_canvas_page_reports_blind_spot(session: Any, server: str) -> None:
    """画布承载主体内容时，快照必须自己承认看不见。

    画布里画的东西没有无障碍树，扫出来的元素数为 0。不说出来的话，模型
    拿到一个空快照只会读作"这个页面是空的"，然后据此编造结论——这比报错
    糟糕得多。
    """
    await session.navigate(f"{server}/canvas.html")
    snap = await session.snapshot_ref()

    assert not snap.refs, "画布页不该扫出可交互元素"
    assert snap.has_canvas_blind_spot is True, snap.canvas


async def test_canvas_blind_spot_is_explained_to_model(session: Any, server: str) -> None:
    """空快照必须区分"页面是空的"和"我们看不见"——两种结论的后续动作完全不同。"""
    await session.navigate(f"{server}/canvas.html")
    snap = await session.snapshot_ref()

    text = snap.to_text()
    assert "画布" in text or "Canvas" in text, text
    assert "没有无障碍树" in text, text
    assert "截图" in text, "必须告诉模型该换视觉通道，光说看不见没用"


async def test_canvas_blind_spot_surfaces_even_with_refs(session: Any, server: str) -> None:
    """画布页常配着几个真按钮。此时快照不为空，盲区提示也不能因此消失。"""
    await session.navigate(f"{server}/canvas_chrome.html")
    snap = await session.snapshot_ref()

    assert snap.refs, "这一页故意留了按钮，用来验证非空快照也会带盲区提示"
    text = snap.to_text()
    assert "画布" in text, text


async def test_small_canvas_is_not_a_blind_spot(session: Any, server: str) -> None:
    """护栏：图标之类的小画布不该触发盲区提示，否则提示就成了噪音。"""
    await session.navigate(f"{server}/canvas_small.html")
    snap = await session.snapshot_ref()

    assert snap.has_canvas_blind_spot is False, snap.canvas
    assert "没有无障碍树" not in snap.to_text()


# ── 折叠控件 ────────────────────────────────────────────────────────────


async def test_summary_reports_disclosure_role(session: Any, server: str) -> None:
    """`<summary>` 必须报出它是可展开控件，不能退化成 generic。

    标成 generic 等于把"点了会展开"这件事从上下文里删掉：内容藏在折叠面板
    里时，模型看到的是一坨没有特征的元素，不知道该先点哪一个才能把内容
    放出来。
    """
    await session.navigate(f"{server}/disclosure.html")
    snap = await session.snapshot_ref()

    target = next((r for r in snap.refs if r.name == "规格参数"), None)
    assert target is not None, [r.name for r in snap.refs]
    assert target.role == "summary", target.role


async def test_collapsed_content_stays_out_of_snapshot(session: Any, server: str) -> None:
    """折叠起来的内容不该出现在快照里——看不见就是看不见，别假装能点。"""
    await session.navigate(f"{server}/disclosure.html")
    snap = await session.snapshot_ref()

    assert "加入购物车" not in [r.name for r in snap.refs]


async def test_expanded_content_appears_after_clicking_summary(session: Any, server: str) -> None:
    """展开之后要能看见——否则前面的"不出现"就不是折叠导致的，而是扫不到。"""
    await session.navigate(f"{server}/disclosure.html")
    snap = await session.snapshot_ref()

    summary = next(r for r in snap.refs if r.name == "规格参数")
    await session.click_ref(summary.ref)

    snap = await session.snapshot_ref()
    assert "加入购物车" in [r.name for r in snap.refs]
