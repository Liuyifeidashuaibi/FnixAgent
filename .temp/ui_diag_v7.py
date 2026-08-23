# -*- coding: utf-8 -*-
"""UI 诊断 v7：拦截网络请求 + console，精确诊断 Accept 落盘失败根因。"""
import sys, time, json, os, stat
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_diag_v7")

# Clean workspace
if WS.exists():
    for root, dirs, files in os.walk(str(WS), topdown=False):
        for f in files:
            p = os.path.join(root, f)
            try: os.chmod(p, stat.S_IWRITE); os.unlink(p)
            except: pass
        for d in dirs:
            try: os.rmdir(os.path.join(root, d))
            except: pass
    try: os.rmdir(str(WS))
    except: pass
WS.mkdir(parents=True, exist_ok=True)

PROMPT = "创建文件 calc.py，内容为 def add(a, b): return a + b，再创建 test_calc.py 测试它"

network_logs = []
console_logs = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    # Capture network requests
    def on_request(req):
        if "/api/v1/chat" in req.url:
            network_logs.append({
                "type": "request",
                "method": req.method,
                "url": req.url,
                "post_data": req.post_data[:500] if req.post_data else None,
            })
    def on_response(resp):
        if "/api/v1/chat" in resp.url:
            try:
                body = resp.text()[:500]
            except:
                body = "<binary>"
            network_logs.append({
                "type": "response",
                "status": resp.status,
                "url": resp.url,
                "body": body,
            })
    page.on("request", on_request)
    page.on("response", on_response)

    # Capture console
    def on_console(msg):
        console_logs.append({
            "type": msg.type,
            "text": msg.text[:300],
        })
    page.on("console", on_console)

    try:
        page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
        page.evaluate("""() => { localStorage.clear(); }""")
        page.evaluate(f"""() => localStorage.setItem('fnix.dev.workspace', {json.dumps(str(WS).replace(chr(92), '/'))})""")
        page.reload(wait_until="domcontentloaded", timeout=45000)
        page.locator(".glass-composer textarea").wait_for(state="visible", timeout=40000)

        # Verify workspace is set
        ws_val = page.evaluate("""() => {
            const stores = window.__zustandStores || {};
            return localStorage.getItem('fnix.dev.workspace');
        }""")
        print(f"[SETUP] dev.workspace = {ws_val}", flush=True)

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
            stop.wait_for(state="detached", timeout=180000)
        except:
            page.wait_for_function(
                """() => document.querySelectorAll('.fnix-turn.fnix-turn-assistant').length > 0""",
                timeout=120000)

        time.sleep(3)
        print("[STEP] Task completed", flush=True)

        # Check React state via DOM inspection
        state_info = page.evaluate("""() => {
            const btns = document.querySelectorAll('.fnix-review-btn.solid');
            const btnInfo = [...btns].map(b => ({
                text: b.textContent.trim(),
                disabled: b.disabled,
                visible: b.getBoundingClientRect().width > 0,
                rect: {
                    x: b.getBoundingClientRect().x,
                    y: b.getBoundingClientRect().y,
                    w: b.getBoundingClientRect().width,
                    h: b.getBoundingClientRect().height,
                },
            }));

            // Check if review panel is visible
            const studioPanel = document.querySelector('.fnx-studio');
            const studioVisible = studioPanel ? studioPanel.getBoundingClientRect().width > 0 : false;

            // Check apply message
            const applyNote = document.querySelector('.fnix-review-note');
            const applyText = applyNote ? applyNote.textContent.trim() : null;

            // Check file change items in review
            const scopeBtns = document.querySelectorAll('.fnix-scope');
            const scopeTexts = [...scopeBtns].map(b => b.textContent.trim());

            return { btnInfo, studioVisible, applyText, scopeTexts };
        }""")
        print(f"[STATE] Button info: {json.dumps(state_info['btnInfo'], ensure_ascii=False)}", flush=True)
        print(f"[STATE] Studio panel visible: {state_info['studioVisible']}", flush=True)
        print(f"[STATE] Apply message: {state_info['applyText']}", flush=True)
        print(f"[STATE] Scope buttons: {json.dumps(state_info['scopeTexts'], ensure_ascii=False)}", flush=True)

        # Clear network logs before click to isolate apply request
        pre_click_net = len(network_logs)
        pre_click_console = len(console_logs)
        print(f"[PRE-CLICK] Network logs so far: {pre_click_net}", flush=True)

        # Click "全部确认"
        accept_btn = page.locator('.fnix-review-btn.solid')
        btn_count = accept_btn.count()
        if btn_count > 0:
            for i in range(btn_count):
                info = state_info['btnInfo'][i] if i < len(state_info['btnInfo']) else {}
                if "全部确认" in info.get("text", "") and info.get("visible") and not info.get("disabled"):
                    print(f"\n[CLICK] Clicking '全部确认' button (index {i})...", flush=True)
                    accept_btn.nth(i).click(timeout=8000)
                    print("[CLICK] Clicked!", flush=True)
                    time.sleep(5)
                    break
            else:
                print("[CLICK] '全部确认' not found or not clickable, trying first solid button", flush=True)
                for i in range(btn_count):
                    if state_info['btnInfo'][i].get("visible") and not state_info['btnInfo'][i].get("disabled"):
                        accept_btn.nth(i).click(timeout=8000)
                        print(f"[CLICK] Clicked first visible button (index {i})", flush=True)
                        time.sleep(5)
                        break
        else:
            print("[CLICK] No accept button found!", flush=True)
            # Try Ctrl+Enter as fallback
            page.keyboard.press("Control+Enter")
            time.sleep(5)

        # Check network logs after click
        post_click_net = network_logs[pre_click_net:]
        print(f"\n=== NETWORK AFTER CLICK ({len(post_click_net)} entries) ===", flush=True)
        for entry in post_click_net:
            print(f"  {json.dumps(entry, ensure_ascii=False)}", flush=True)

        # Check console logs after click
        post_click_console = console_logs[pre_click_console:]
        print(f"\n=== CONSOLE AFTER CLICK ({len(post_click_console)} entries) ===", flush=True)
        for entry in post_click_console:
            print(f"  [{entry['type']}] {entry['text']}", flush=True)

        # Check apply message after click
        post_apply = page.evaluate("""() => {
            const applyNote = document.querySelector('.fnix-review-note');
            return applyNote ? applyNote.textContent.trim() : null;
        }""")
        print(f"\n[POST-CLICK] Apply message: {post_apply}", flush=True)

        # Take screenshot
        page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_diag_v7.png", full_page=False)

        # Check disk
        disk = {}
        for fname in ["calc.py", "test_calc.py"]:
            fp = WS / fname
            if fp.exists():
                content = fp.read_text("utf-8")
                disk[fname] = content[:300]
            else:
                disk[fname] = None
        all_files = [str(p.relative_to(WS)).replace("\\","/") for p in WS.rglob("*") if p.is_file() and ".fnix" not in str(p)]
        disk["all_files"] = all_files
        print(f"\n=== DISK ===\n{json.dumps(disk, indent=2, ensure_ascii=False)}", flush=True)

        # Also print all network logs for the entire session
        print(f"\n=== ALL NETWORK LOGS ({len(network_logs)} total) ===", flush=True)
        for entry in network_logs:
            print(f"  {json.dumps(entry, ensure_ascii=False)}", flush=True)

        # Print all console logs
        print(f"\n=== ALL CONSOLE LOGS ({len(console_logs)} total) ===", flush=True)
        for entry in console_logs:
            print(f"  [{entry['type']}] {entry['text']}", flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        try: page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_diag_v7_error.png", full_page=False)
        except: pass
    finally:
        ctx.close()
        browser.close()
