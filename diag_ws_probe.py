# -*- coding: utf-8 -*-
"""诊断 dev 钩子链路：localStorage 是否写入 + projectPath 是否反映到 UI。"""
from playwright.sync_api import sync_playwright
import json

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(15000)
    page.goto("http://127.0.0.1:5175/", wait_until="domcontentloaded", timeout=45000)
    ws = r"C:\Users\liuyi\.fnix\workspaces\bench\vibe-code-bench\case_01_pomodoro"

    written = page.evaluate("(ws) => { localStorage.setItem('fnix.dev.workspace', ws); return localStorage.getItem('fnix.dev.workspace'); }", ws)
    print("WRITTEN:", json.dumps(written, ensure_ascii=True))

    page.reload(wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(9000)

    ls = page.evaluate("() => localStorage.getItem('fnix.dev.workspace')")
    print("LS_AFTER_RELOAD:", json.dumps(ls, ensure_ascii=True))

    body = page.evaluate("() => document.body.innerText")
    print("BODY_HAS_WS_PATH:", ws.replace("\\", "\\\\") in body)
    # 状态栏 / footer 文本
    status = page.evaluate("""() => {
        const els = document.querySelectorAll('footer, [class*="status"], [class*="Status"], [class*="statusbar"], [class*="StatusBar"]');
        return Array.from(els).map(e=>e.innerText).filter(t=>t && t.trim().length>0 && t.length<300).slice(0,10);
    }""")
    print("STATUS:", json.dumps(status, ensure_ascii=True))
    b.close()
