# -*- coding: utf-8 -*-
"""单题深度诊断：检查流式是否正常完成、file_change 事件是否存在。"""
import sys, time, json, os, stat
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_deep_diag")

if WS.exists():
    import shutil; shutil.rmtree(str(WS), ignore_errors=True)
WS.mkdir(parents=True, exist_ok=True)

PROMPT = "创建文件 calc.py，内容为 def add(a, b): return a + b，再创建 test_calc.py 测试它"

console_logs = []
network_logs = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    def on_console(msg):
        console_logs.append({"type": msg.type, "text": msg.text[:300]})
    page.on("console", on_console)

    def on_request(req):
        if "/api/v1/chat" in req.url:
            network_logs.append({"type": "req", "method": req.method, "url": req.url})
    def on_response(resp):
        if "/api/v1/chat" in resp.url:
            try: body = resp.text()[:800]
            except: body = "<binary>"
            network_logs.append({"type": "resp", "status": resp.status, "url": resp.url, "body": body})
    page.on("request", on_request)
    page.on("response", on_response)

    ws_str = str(WS).replace("\\", "/")

    try:
        page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
        page.evaluate("""() => { localStorage.clear(); }""")
        page.evaluate(f"""() => localStorage.setItem('fnix.dev.workspace', {json.dumps(ws_str)})""")
        page.reload(wait_until="domcontentloaded", timeout=45000)
        page.locator(".glass-composer textarea").wait_for(state="visible", timeout=40000)

        # Check initial state
        mode_info = page.evaluate("""() => {
            const session = JSON.parse(localStorage.getItem('fnix-shell-session') || '{}');
            return { mode: session.state?.mode, inspectorOpen: session.state?.inspectorOpen, workMode: 'unknown' };
        }""")
        print(f"[INIT] session state: {json.dumps(mode_info, ensure_ascii=False)}", flush=True)

        # Submit
        ta = page.locator(".glass-composer textarea")
        ta.click(timeout=10000)
        ta.fill(PROMPT)
        page.keyboard.press("Escape")
        send = page.locator('button.glass-send[aria-label="发送"]')
        send.wait_for(state="visible", timeout=10000)
        page.wait_for_function(
            """() => { const b = document.querySelector('button.glass-send[aria-label="发送"]'); return !!b && !b.disabled; }""",
            timeout=10000)
        send.click(timeout=10000)
        print("[SENT] Prompt sent", flush=True)

        # Wait and monitor
        t0 = time.time()
        stop = page.locator("button.glass-send.stop")
        stop_visible = False
        try:
            stop.wait_for(state="visible", timeout=15000)
            stop_visible = True
            print(f"[STREAM] Stop button appeared at {time.time()-t0:.1f}s", flush=True)
            stop.wait_for(state="detached", timeout=180000)
            print(f"[STREAM] Stop button disappeared at {time.time()-t0:.1f}s", flush=True)
        except Exception as e:
            print(f"[STREAM] Stop button wait failed at {time.time()-t0:.1f}s: {e}", flush=True)
            # Check if assistant message exists
            asst_count = page.evaluate("""() => document.querySelectorAll('.fnix-turn.fnix-turn-assistant').length""")
            print(f"[STREAM] Assistant messages: {asst_count}", flush=True)

        time.sleep(3)

        # Check UI state
        ui_state = page.evaluate("""() => {
            const asstTurns = document.querySelectorAll('.fnix-turn.fnix-turn-assistant');
            const lastAsst = asstTurns[asstTurns.length - 1];
            const lastText = lastAsst ? lastAsst.textContent.slice(0, 500) : null;
            const acceptBtns = document.querySelectorAll('.fnix-review-btn.solid');
            const allBtns = [...acceptBtns].map(b => ({ text: b.textContent.trim(), disabled: b.disabled, visible: b.getBoundingClientRect().width > 0 }));
            const scopes = document.querySelectorAll('.fnix-scope');
            const scopeTexts = [...scopes].map(b => b.textContent.trim());
            const errors = document.querySelectorAll('.fnix-review-note.bad, .fnix-error');
            const errorTexts = [...errors].map(e => e.textContent.trim());
            const feedText = document.querySelector('.fnix-feed')?.textContent?.slice(-500) || null;
            const studioPanel = document.querySelector('.fnx-studio');
            const studioVisible = studioPanel ? studioPanel.getBoundingClientRect().width > 0 : false;
            return { lastText, allBtns, scopeTexts, errorTexts, feedText, studioVisible, asstCount: asstTurns.length };
        }""")
        print(f"\n[UI STATE]", flush=True)
        print(f"  Assistant count: {ui_state['asstCount']}", flush=True)
        print(f"  Last assistant text: {ui_state['lastText']}", flush=True)
        print(f"  Accept buttons: {json.dumps(ui_state['allBtns'], ensure_ascii=False)}", flush=True)
        print(f"  Scope buttons: {json.dumps(ui_state['scopeTexts'], ensure_ascii=False)}", flush=True)
        print(f"  Error texts: {json.dumps(ui_state['errorTexts'], ensure_ascii=False)}", flush=True)
        print(f"  Studio visible: {ui_state['studioVisible']}", flush=True)
        print(f"  Feed text (tail): {ui_state['feedText']}", flush=True)

        # Try clicking accept if available
        if ui_state['allBtns']:
            for i, info in enumerate(ui_state['allBtns']):
                if "全部确认" in info["text"] and info["visible"] and not info["disabled"]:
                    page.locator('.fnix-review-btn.solid').nth(i).click(timeout=8000)
                    print(f"\n[ACCEPT] Clicked '全部确认'", flush=True)
                    time.sleep(3)
                    break

        # Check disk
        disk_files = [str(p.relative_to(WS)).replace("\\", "/") for p in WS.rglob("*") if p.is_file() and ".fnix" not in str(p)]
        print(f"\n[DISK] Files: {disk_files}", flush=True)

        # Network logs
        print(f"\n[NETWORK] ({len(network_logs)} entries)", flush=True)
        for entry in network_logs:
            print(f"  {json.dumps(entry, ensure_ascii=False)[:300]}", flush=True)

        # Console errors
        errors = [l for l in console_logs if l["type"] == "error"]
        print(f"\n[CONSOLE ERRORS] ({len(errors)})", flush=True)
        for e in errors:
            print(f"  [{e['type']}] {e['text']}", flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
    finally:
        ctx.close()
        browser.close()
