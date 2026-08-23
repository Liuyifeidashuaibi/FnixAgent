# -*- coding: utf-8 -*-
"""UI 诊断 v8：单题深度诊断——捕获网络请求/响应全文 + DOM 状态 + console。"""
import sys, time, json, os, stat
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_diag_v8")

if WS.exists():
    for root, dirs, files in os.walk(str(WS), topdown=False):
        for f in files:
            try: os.chmod(os.path.join(root, f), stat.S_IWRITE); os.unlink(os.path.join(root, f))
            except: pass
        for d in dirs:
            try: os.rmdir(os.path.join(root, d))
            except: pass
    try: os.rmdir(str(WS))
    except: pass
WS.mkdir(parents=True, exist_ok=True)

PROMPT = "创建文件 calc.py，内容为 def add(a, b): return a + b"

network_logs = []
console_logs = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    def on_request(req):
        if "/api/v1/chat" in req.url:
            network_logs.append({"type": "req", "method": req.method, "url": req.url,
                                "post_data": req.post_data[:800] if req.post_data else None})
    def on_response(resp):
        if "/api/v1/chat" in resp.url:
            try: body = resp.text()[:2000]
            except: body = "<binary>"
            network_logs.append({"type": "resp", "status": resp.status, "url": resp.url, "body": body})
    page.on("request", on_request)
    page.on("response", on_response)

    def on_console(msg):
        console_logs.append({"type": msg.type, "text": msg.text[:300]})
    page.on("console", on_console)

    try:
        page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
        page.evaluate("""() => { localStorage.clear(); }""")
        ws_str = str(WS).replace("\\", "/")
        page.evaluate(f"""() => localStorage.setItem('fnix.dev.workspace', {json.dumps(ws_str)})""")
        page.reload(wait_until="domcontentloaded", timeout=45000)
        page.locator(".glass-composer textarea").wait_for(state="visible", timeout=40000)

        # Check initial state
        mode_info = page.evaluate("""() => {
            const persisted = JSON.parse(localStorage.getItem('fnix-shell-session') || '{}');
            return {
                persistedMode: persisted.state?.mode,
                persistedInspectorOpen: persisted.state?.inspectorOpen,
                devWs: localStorage.getItem('fnix.dev.workspace'),
            };
        }""")
        print(f"[INIT] {json.dumps(mode_info, ensure_ascii=False)}", flush=True)

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
        print("[STEP] Sent prompt", flush=True)

        # Wait for completion
        stop = page.locator("button.glass-send.stop")
        try:
            stop.wait_for(state="visible", timeout=15000)
            print("[STEP] Stop button appeared (streaming started)", flush=True)
            stop.wait_for(state="detached", timeout=180000)
            print("[STEP] Stop button detached (streaming ended)", flush=True)
        except:
            print("[STEP] No stop button or timeout", flush=True)
            page.wait_for_function(
                """() => document.querySelectorAll('.fnix-turn.fnix-turn-assistant').length > 0""",
                timeout=120000)

        time.sleep(3)
        print("[STEP] Post-stream wait done", flush=True)

        # Check DOM state
        dom_state = page.evaluate("""() => {
            const assistantTurns = document.querySelectorAll('.fnix-turn.fnix-turn-assistant');
            const lastAssistant = assistantTurns[assistantTurns.length - 1];
            const lastText = lastAssistant ? lastAssistant.textContent.trim().slice(0, 500) : null;

            const acceptBtns = document.querySelectorAll('.fnix-review-btn.solid');
            const acceptInfo = [...acceptBtns].map(b => ({
                text: b.textContent.trim(),
                disabled: b.disabled,
                visible: b.getBoundingClientRect().width > 0,
            }));

            const scopeBtns = document.querySelectorAll('.fnix-scope');
            const scopeTexts = [...scopeBtns].map(b => b.textContent.trim());

            const studioPanel = document.querySelector('.fnx-studio');
            const studioVisible = studioPanel ? studioPanel.getBoundingClientRect().width > 0 : false;

            const processItems = document.querySelectorAll('.fnix-process-item, .fnix-activity-item');
            const processTexts = [...processItems].map(e => e.textContent.trim().slice(0, 100));

            // Check for error messages
            const errorEls = document.querySelectorAll('.fnix-review-note.bad, .fnix-error, [class*="error"]');
            const errorTexts = [...errorEls].map(e => e.textContent.trim().slice(0, 200));

            return {
                assistantTurnCount: assistantTurns.length,
                lastAssistantText: lastText,
                acceptBtns: acceptInfo,
                scopeBtns: scopeTexts,
                studioVisible,
                processItems: processTexts,
                errorTexts,
            };
        }""")
        print(f"\n[DOM] Assistant turns: {dom_state['assistantTurnCount']}", flush=True)
        print(f"[DOM] Last assistant text: {dom_state['lastAssistantText']}", flush=True)
        print(f"[DOM] Accept buttons: {json.dumps(dom_state['acceptBtns'], ensure_ascii=False)}", flush=True)
        print(f"[DOM] Scope buttons: {json.dumps(dom_state['scopeBtns'], ensure_ascii=False)}", flush=True)
        print(f"[DOM] Studio visible: {dom_state['studioVisible']}", flush=True)
        print(f"[DOM] Process items: {json.dumps(dom_state['processItems'], ensure_ascii=False)}", flush=True)
        print(f"[DOM] Error texts: {json.dumps(dom_state['errorTexts'], ensure_ascii=False)}", flush=True)

        # Screenshot
        page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_diag_v8.png", full_page=False)

        # Check disk
        all_files = [str(p.relative_to(WS)).replace("\\","/") for p in WS.rglob("*") if p.is_file() and ".fnix" not in str(p)]
        print(f"\n[DISK] Files: {json.dumps(all_files, ensure_ascii=False)}", flush=True)

        # Print network logs
        print(f"\n=== NETWORK LOGS ({len(network_logs)} total) ===", flush=True)
        for entry in network_logs:
            print(f"  {json.dumps(entry, ensure_ascii=False)}", flush=True)

        # Print console logs
        print(f"\n=== CONSOLE LOGS ({len(console_logs)} total) ===", flush=True)
        for entry in console_logs:
            print(f"  [{entry['type']}] {entry['text']}", flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        try: page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_diag_v8_error.png")
        except: pass
    finally:
        ctx.close()
        browser.close()
