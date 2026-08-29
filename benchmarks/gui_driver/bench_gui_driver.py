"""GUI Driver 度量基线（Phase 0）。

路线文档 GUI_DRIVER_ROADMAP.md 的执行纪律第一条：没有基线就无法证明改进。
本脚本产出可复现的基线数字，每期开工前与结项时各跑一次。

当前测量：
  - 快照体积（字符 / token 估算）：驱动 Phase 1 的 ref 重构
  - 快照与导航耗时：驱动 Phase 2 的 auto-wait 改造
  - 页面可交互元素数：感知层 O(n) 问题的量化

做法：把 fixture 页面用本地 HTTP 服务托管（不用 file://，因为内置浏览器
按安全策略禁了本地协议），这也顺带覆盖 localhost 导航路径。

用法：
  PYTHONPATH=src .venv/Scripts/python.exe benchmarks/gui_driver/bench_gui_driver.py
"""

# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import functools
import http.server
import json
import socket
import threading
import time
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

# ── fixture 定义：覆盖不同规模与语言，逼近真实分布 ────────────────
# (文件名, 标题, 卡片块数, 每块链接数, 表单字段数, 是否中文)
PAGE_SPECS = [
    ("simple_form.html", "简单表单", 0, 0, 8, False),
    ("mid_list.html", "中等列表", 12, 4, 3, False),
    ("complex_portal.html", "复杂门户", 50, 5, 10, False),
    ("heavy_spa.html", "重型页面", 160, 5, 12, False),
    ("zh_site.html", "中文站点", 40, 5, 8, True),
]

ZH_WORDS = ["首页", "新闻", "财经", "体育", "娱乐", "科技", "教育", "健康"]

# Phase 2 用：与 fixture 页面同目录托管，覆盖三种动作后果形态。
#  - 立即改变：动作同步生效
#  - 延迟改变：回调里 setTimeout 700ms 后才改 DOM（固定 sleep 必漏判）
#  - 点了没反应：动作合法但页面不变（必须报 changed=False）
ACTION_PAGE = """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>动作延迟页</title></head><body>
<h1>动作延迟页</h1>
<button id='fast' onclick="document.getElementById('out').textContent='fast-done'">立即改变</button>
<button id='slow' onclick="setTimeout(function(){
  document.getElementById('out').textContent='slow-done';}, 700)">延迟改变</button>
<button id='inert'>点了没反应</button>
<div id='out'>initial</div>
</body></html>"""

# 旧实现的等待方式，A/B 对照用
_OLD_FIXED_SLEEP_MS = 600


def _build_html(title: str, cards: int, links_per_card: int, fields: int, zh: bool) -> str:
    nav_items = ZH_WORDS if zh else ["Home", "News", "Finance", "Sports", "Tech", "About"]
    word = (lambda i: f"{ZH_WORDS[i % len(ZH_WORDS)]}频道") if zh else (lambda i: f"Section {i}")

    parts = [
        "<!doctype html><html lang='zh-CN'>" if zh else "<!doctype html><html lang='en'>",
        "<head><meta charset='utf-8'>",
        f"<title>{title}</title>",
        "<style>body{font-family:system-ui;margin:0}"
        ".nav{display:flex;gap:12px;padding:12px;background:#f5f5f5}"
        ".card{border:1px solid #e5e5e5;padding:12px;margin:8px;border-radius:8px}"
        ".field{margin:6px 0}</style></head><body>",
        "<nav class='nav'>",
    ]
    for i, item in enumerate(nav_items):
        parts.append(f"<a href='#s{i}'>{item}</a>")
    parts.append("</nav><main>")
    parts.append(f"<h1>{title}</h1>")

    # 表单区
    parts.append("<form id='main-form'>")
    labels = ["姓名", "邮箱", "电话", "地址"] if zh else ["Name", "Email", "Phone", "Address"]
    for f in range(fields):
        lab = labels[f % len(labels)]
        parts.append(
            f"<div class='field'><label for='f{f}'>{lab} {f}</label>"
            f"<input id='f{f}' name='f{f}' placeholder='{lab}'></div>"
        )
    parts.append("<button type='submit'>提交</button>" if zh else "<button type='submit'>Submit</button>")
    parts.append("</form>")

    # 卡片列表区（元素规模的主要来源）
    for c in range(cards):
        parts.append(f"<section class='card' id='c{c}'><h2>{word(c)} {c}</h2><ul>")
        for l in range(links_per_card):
            parts.append(f"<li><a href='#c{c}l{l}'>{word(c)} 条目 {l}</a></li>")
        parts.append("</ul><button>操作</button></section>")

    parts.append("</main></body></html>")
    return "".join(parts)


def ensure_fixtures() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    changed = []
    for name, title, cards, links, fields, zh in PAGE_SPECS:
        path = FIXTURES / name
        html = _build_html(title, cards, links, fields, zh)
        if not path.exists() or path.read_text(encoding="utf-8") != html:
            path.write_text(html, encoding="utf-8")
            changed.append(name)
    action_page = FIXTURES / "actions.html"
    if not action_page.exists() or action_page.read_text(encoding="utf-8") != ACTION_PAGE:
        action_page.write_text(ACTION_PAGE, encoding="utf-8")
        changed.append("actions.html")
    if changed:
        print(f"[fixtures] 生成/更新 {len(changed)} 个页面: {', '.join(changed)}")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def serve_fixtures() -> tuple[http.server.ThreadingHTTPServer, int, threading.Thread]:
    port = _free_port()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port, t


# ── token 估算 ──────────────────────────────────────────────────
def estimate_tokens(text: str) -> tuple[int, str]:
    """返回 (token 数, 估算方式)。优先 tiktoken，缺失时用字符启发式。"""
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text)), "tiktoken/cl100k_base"
    except Exception:
        # 启发式：CJK 约 1.2 token/字，其余约 4 字符/token
        cjk = sum(1 for ch in text if "一" <= ch <= "鿿")
        other = len(text) - cjk
        return int(cjk * 1.2 + other / 4), "heuristic(cjk*1.2+ascii/4)"


async def measure_page(session, base: str, name: str, title: str) -> dict:
    url = f"{base}/{name}"
    t0 = time.perf_counter()
    state = await session.navigate(url)
    nav_ms = (time.perf_counter() - t0) * 1000
    if state.error:
        return {"page": name, "title": title, "error": state.error}

    t1 = time.perf_counter()
    snapshot = await session.snapshot()
    snap_ms = (time.perf_counter() - t1) * 1000

    # Phase 1 对照：ref 语义快照
    t2 = time.perf_counter()
    ref_snap = await session.snapshot_ref()
    ref_ms = (time.perf_counter() - t2) * 1000
    ref_text = ref_snap.to_text()
    ref_tokens, _ = estimate_tokens(ref_text)

    # 页面真实可交互元素数（对照用，非快照返回数）
    try:
        dom_count = await session._page.evaluate(
            "() => document.querySelectorAll("
            "'a,button,input,select,textarea,[role=button],[onclick]').length"
        )
    except Exception:
        dom_count = -1

    tokens, method = estimate_tokens(snapshot)
    return {
        "page": name,
        "title": title,
        "dom_interactive_elements": dom_count,
        "snapshot_chars": len(snapshot),
        "snapshot_tokens": tokens,
        "token_method": method,
        # Phase 1 ref 快照对照
        "ref_snapshot_tokens": ref_tokens,
        "ref_snapshot_chars": len(ref_text),
        "ref_count": len(ref_snap.refs),
        "ref_truncated": ref_snap.truncated,
        "token_reduction_pct": round((1 - ref_tokens / tokens) * 100, 1) if tokens else 0,
        "nav_ms": round(nav_ms, 1),
        "snapshot_ms": round(snap_ms, 1),
        "ref_snapshot_ms": round(ref_ms, 1),
        "screenshot_b64_kb": round(len(state.screenshot_b64) / 1024, 1),
    }


async def measure_actions(session: Any, base: str) -> dict:
    """Phase 2 对照：状态等待 vs 旧实现的固定 sleep(600ms)。

    只比平均耗时会得出错误结论——固定 sleep 在快页面确实"看起来"也不慢，
    真正致命的是它在延迟渲染场景会**漏判动作效果**（changed=False 被当成
    失败，或更糟：判定成功但页面其实没变）。所以这里同时测三件事：

      1. 瞬时动作的等待耗时（快页面有没有白等）
      2. 延迟 700ms 生效的动作能否被捕获（慢页面有没有漏判）
      3. 点了没反应能否被识别（静默失败拦截）
    """
    results: dict[str, Any] = {}
    url = f"{base}/actions.html"

    async def _timed_click(label: str, settle_ms: int | None) -> dict:
        """settle_ms=None 走状态等待；否则把等待替换成固定 sleep 以复现旧行为。"""
        await session.navigate(url)
        original = type(session)._wait_settled

        if settle_ms is not None:

            async def _fixed(self: Any, page: Any, **_kw: Any) -> None:
                await page.wait_for_timeout(settle_ms)

            type(session)._wait_settled = _fixed  # type: ignore[method-assign]
        try:
            t0 = time.perf_counter()
            state = await session.click_text(label)
            elapsed = (time.perf_counter() - t0) * 1000
            return {
                "elapsed_ms": round(elapsed, 1),
                "changed": bool(state.changed),
                "error": state.error,
            }
        finally:
            type(session)._wait_settled = original  # type: ignore[method-assign]

    # 1. 瞬时动作：新方式应显著快于固定 sleep
    results["instant_state_wait"] = await _timed_click("立即改变", None)
    results["instant_fixed_sleep"] = await _timed_click("立即改变", _OLD_FIXED_SLEEP_MS)

    # 2. 延迟生效：固定 sleep 等不到，会误判成"点了没反应"
    results["delayed_state_wait"] = await _timed_click("延迟改变", None)
    results["delayed_fixed_sleep"] = await _timed_click("延迟改变", _OLD_FIXED_SLEEP_MS)

    # 3. 静默失败：两种都该识别，用于确认新方式没有把"真没变"也刷成 changed
    results["inert_state_wait"] = await _timed_click("点了没反应", None)

    sw = results["instant_state_wait"]["elapsed_ms"]
    fs = results["instant_fixed_sleep"]["elapsed_ms"]
    results["summary"] = {
        "instant_speedup_pct": round((1 - sw / fs) * 100, 1) if fs else 0.0,
        "delayed_caught_state_wait": results["delayed_state_wait"]["changed"],
        "delayed_caught_fixed_sleep": results["delayed_fixed_sleep"]["changed"],
        "inert_correctly_reported": results["inert_state_wait"]["changed"] is False,
    }
    return results


async def main() -> None:
    ensure_fixtures()
    httpd, port, _thread = serve_fixtures()
    base = f"http://127.0.0.1:{port}"
    print(f"[server] fixture 服务 {base}\n")

    from fnixagent.core.tools.browser import BrowserSession

    session = BrowserSession.instance()
    results = []
    try:
        for name, title, *_ in PAGE_SPECS:
            r = await measure_page(session, base, name, title)
            results.append(r)
            if "error" in r:
                print(f"  ✗ {name}: {r['error']}")
            else:
                print(
                    f"  {title:<8} 元素{r['dom_interactive_elements']:>5}  "
                    f"旧{r['snapshot_tokens']:>6} tok → ref {r['ref_snapshot_tokens']:>5} tok "
                    f"(省 {r['token_reduction_pct']:>5.1f}%, 收录 {r['ref_count']:>3} 个)"
                )
        # Phase 2：动作等待 A/B（状态等待 vs 旧固定 sleep）
        actions = await measure_actions(session, base)
        await session.close()
    finally:
        httpd.shutdown()

    ok = [r for r in results if "error" not in r]
    if not ok:
        print("\n全部失败，无基线数据")
        return

    heavy = max(ok, key=lambda r: r["dom_interactive_elements"])
    avg_red = sum(r["token_reduction_pct"] for r in ok) / len(ok)
    out = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "token_method": ok[0]["token_method"],
        "pages": results,
        "summary": {
            "max_snapshot_tokens": max(r["snapshot_tokens"] for r in ok),
            "heavy_page_tokens": heavy["snapshot_tokens"],
            "heavy_page_elements": heavy["dom_interactive_elements"],
            "avg_nav_ms": round(sum(r["nav_ms"] for r in ok) / len(ok), 1),
            "avg_snapshot_ms": round(sum(r["snapshot_ms"] for r in ok) / len(ok), 1),
            # Phase 1 成效
            "avg_token_reduction_pct": round(avg_red, 1),
            "max_ref_snapshot_tokens": max(r["ref_snapshot_tokens"] for r in ok),
            "heavy_page_ref_tokens": heavy["ref_snapshot_tokens"],
        },
        # Phase 2 成效
        "actions": actions,
    }
    out_path = Path(__file__).parent / "baseline.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n── 基线摘要 ──")
    print(f"  最重页面快照: {out['summary']['heavy_page_tokens']} tokens "
          f"（{out['summary']['heavy_page_elements']} 个可交互元素）")
    print(f"  平均导航:     {out['summary']['avg_nav_ms']} ms")
    print(f"  token 估算:   {out['token_method']}")
    if "avg_token_reduction_pct" in out["summary"]:
        print("\n── Phase 1 成效（旧 ARIA+坐标 → ref 语义快照）──")
        print(f"  平均 token 降幅:   {out['summary']['avg_token_reduction_pct']}%")
        print(f"  ref 快照峰值:      {out['summary']['max_ref_snapshot_tokens']} tokens "
              f"（目标 ≤400）")
        print(f"  最重页面:          {out['summary']['heavy_page_ref_tokens']} tokens")

    a = out["actions"]["summary"]
    print("\n── Phase 2 成效（固定 sleep(600ms) → 状态等待）──")
    print(f"  瞬时动作:          {out['actions']['instant_fixed_sleep']['elapsed_ms']}ms → "
          f"{out['actions']['instant_state_wait']['elapsed_ms']}ms "
          f"(快 {a['instant_speedup_pct']}%)")
    print(f"  延迟 700ms 生效:   固定 sleep 捕获={a['delayed_caught_fixed_sleep']} → "
          f"状态等待捕获={a['delayed_caught_state_wait']}")
    print(f"  点了没反应:        正确报 changed=False = {a['inert_correctly_reported']}")
    print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
