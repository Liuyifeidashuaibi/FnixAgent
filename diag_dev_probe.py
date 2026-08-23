# -*- coding: utf-8 -*-
"""在页面模块上下文里检查 import.meta.env.DEV（通过动态 import）。"""
from playwright.sync_api import sync_playwright
import json

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(15000)
    page.goto("http://127.0.0.1:5175/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(6000)
    # 通过动态 import 一个模块来读取 import.meta.env（模块上下文）
    env = page.evaluate("""async () => {
        try {
            const m = await import('/src/main.tsx');
            return 'imported ok';
        } catch (e) {
            return 'import err: ' + String(e).slice(0,200);
        }
    }""")
    print("MAIN_IMPORT:", env)
    # 检查 vite client 是否有 DEV 相关全局
    probe = page.evaluate("""() => {
        return {
            hasViteClient: !!window.__vite_plugin_react_preamble_installed__,
            envKeys: Object.keys(import.meta.env || {}).filter(k=>k.includes('DEV')||k.includes('MODE')||k.includes('PROD')),
        };
    }""")
    print("PROBE:", json.dumps(probe, ensure_ascii=True))
    b.close()
