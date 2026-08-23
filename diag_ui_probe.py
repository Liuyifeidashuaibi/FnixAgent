# -*- coding: utf-8 -*-
"""诊断前端当前状态：Composer 是否渲染、textarea 是否存在。"""
from playwright.sync_api import sync_playwright
import json

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True,
                           args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(15000)
    page.goto("http://127.0.0.1:5175/", wait_until="domcontentloaded", timeout=45000)
    ws = r"C:\Users\liuyi\.fnix\workspaces\bench\vibe-code-bench\case_01_pomodoro"
    page.evaluate("(ws) => localStorage.setItem('fnix.dev.workspace', ws)", ws)
    page.reload(wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(12000)
    diag = page.evaluate("""() => {
        return {
            title: document.title,
            url: location.href,
            bodyText: document.body.innerText.slice(0, 1000),
            hasComposer: !!document.querySelector('.glass-composer'),
            hasTextarea: !!document.querySelector('.glass-composer textarea'),
            textareaCount: document.querySelectorAll('textarea').length,
            anyTextarea: Array.from(document.querySelectorAll('textarea')).map(t=>({aria:t.getAttribute('aria-label'), placeholder:t.getAttribute('placeholder'), cls:t.className})),
            buttons: Array.from(document.querySelectorAll('button')).map(b=>(b.getAttribute('aria-label')||b.innerText||'').slice(0,25)).filter(Boolean).slice(0,40),
        };
    }""")
    print(json.dumps(diag, ensure_ascii=True, indent=1))
    page.screenshot(path=r"E:\FNIX\FnixAgent\outputs\bench_ui_shots\_diag_probe.png", full_page=False)
    b.close()
