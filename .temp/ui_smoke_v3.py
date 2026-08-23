# -*- coding: utf-8 -*-
"""UI smoke v3：网络拦截 + 完整事件捕获 + Accept 落盘验证。"""
import sys, time, json, os, stat, re
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_smoke_v3")

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

captured_events = []
ndjson_lines = []
console_logs = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    # Capture console
    page.on("console", lambda msg: console_logs.append(f"{msg.type}: {msg.text[:400]}"))

    # Intercept network requests to chat/agent
    def on_response(response):
        url = response.url
        if "/chat/agent" in url:
            try:
                body = response.text()
                for line in body.split("\n"):
                    line = line.strip()
                    if line:
                        ndjson_lines.append(line)
                        try:
                            ev = json.loads(line)
                            captured_events.append(ev)
                        except: pass
            except: pass

    page.on("response", on_response)

    try:
        page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
        page.evaluate(f"""() => localStorage.setItem('fnix.dev.workspace', '{WS}')""")
        page.reload(wait_until="domcontentloaded", timeout=45000)
        page.locator(".glass-composer textarea").wait_for(state="visible", timeout=40000)

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
        print("Sent", flush=True)

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

        # Print captured events
        print(f"\n=== CAPTURED NDJSON EVENTS ({len(captured_events)}) ===", flush=True)
        for ev in captured_events:
            t = ev.get("type", "")
            if t == "file_change":
                print(f"  [file_change] path={ev.get('path','')} action={ev.get('action','')} content_len={len(ev.get('content',''))}", flush=True)
            elif t == "done":
                print(f"  [done] status={ev.get('status','')} changes={len(ev.get('changes',[]))}", flush=True)
            elif t == "step_start":
                print(f"  [step_start] action={ev.get('step',{}).get('action','')} target={ev.get('step',{}).get('target','')}", flush=True)
            elif t == "step_end":
                print(f"  [step_end] status={ev.get('step',{}).get('status','')}", flush=True)
            elif t == "plan":
                print(f"  [plan] steps={len(ev.get('steps',[]))}", flush=True)
            elif t == "thinking":
                print(f"  [thinking] {str(ev.get('content',''))[:80]}", flush=True)
            elif t == "message":
                print(f"  [message] {str(ev.get('content',''))[:200]}", flush=True)
            elif t == "heartbeat":
                pass
            else:
                print(f"  [{t}]", flush=True)

        # DOM state
        state = page.evaluate("""() => {
            const r = {};
            r.inspector_open = !!document.querySelector('.fnix-inspector:not(.fnix-inspector-closed)');
            r.inspector_exists = document.querySelectorAll('.fnix-inspector').length;
            // Check for review tab
            const tabs = document.querySelectorAll('[role="tab"], .studio-tab, button[class*="tab"]');
            r.tab_texts = [...tabs].map(t => t.textContent?.trim()).filter(Boolean);
            // Check for diff blocks
            r.diff_blocks = document.querySelectorAll('.cl-diff-block, [class*="diff-block"]').length;
            // Check for accept buttons
            r.accept_all = document.querySelectorAll('.cl-diff-accept-all, [class*="accept-all"]').length;
            r.accept_btns = document.querySelectorAll('button[class*="accept"]').length;
            // Pending changes badge
            r.badge_texts = [...document.querySelectorAll('[class*="badge"]')].map(b => b.textContent?.trim()).filter(Boolean);
            // Assistant content
            const asst = document.querySelector('.fnix-turn.fnix-turn-assistant .fnix-asst-text');
            r.asst_text = asst ? asst.innerText.substring(0, 500) : '';
            // Blocks in message
            r.structured_blocks = document.querySelectorAll('.fnix-struct-block, [class*="struct-block"]').length;
            // Check inspector tabs specifically
            const inspector = document.querySelector('.fnix-inspector:not(.fnix-inspector-closed)');
            if (inspector) {
                r.inspector_tabs = [...inspector.querySelectorAll('[role="tab"], .studio-tab, button[class*="tab"]')].map(t => t.textContent?.trim()).filter(Boolean);
                r.inspector_content = inspector.innerText.substring(0, 600);
            }
            return r;
        }""")
        print(f"\n=== DOM STATE ===\n{json.dumps(state, indent=2, ensure_ascii=False)}", flush=True)

        # Check if review tab exists and click it
        review_tab = page.locator('button:has-text("评审"), [role="tab"]:has-text("评审")')
        print(f"\nReview tab count: {review_tab.count()}", flush=True)
        if review_tab.count() > 0:
            review_tab.first.click(timeout=5000)
            time.sleep(2)
            state2 = page.evaluate("""() => {
                const inspector = document.querySelector('.fnix-inspector:not(.fnix-inspector-closed)');
                const r = {};
                r.inspector_content = inspector ? inspector.innerText.substring(0, 800) : 'no inspector';
                r.accept_all = document.querySelectorAll('.cl-diff-accept-all, [class*="accept-all"]').length;
                r.diff_blocks = document.querySelectorAll('.cl-diff-block, [class*="diff-block"]').length;
                r.accept_visible = false;
                const btn = document.querySelector('.cl-diff-accept-all, [class*="accept-all"]');
                if (btn) { const rect = btn.getBoundingClientRect(); r.accept_visible = rect.width > 0 && rect.height > 0; }
                return r;
            }""")
            print(f"\n=== AFTER REVIEW TAB CLICK ===\n{json.dumps(state2, indent=2, ensure_ascii=False)}", flush=True)

            if state2.get("accept_visible"):
                print("Clicking Accept All!", flush=True)
                page.locator(".cl-diff-accept-all").click(timeout=8000)
                time.sleep(3)
            else:
                # Try Ctrl+Enter
                page.keyboard.press("Control+Enter")
                time.sleep(3)
                print("Tried Ctrl+Enter", flush=True)

        # Check disk
        disk = {}
        for fname in ["calc.py", "test_calc.py", "hello.py"]:
            fp = WS / fname
            disk[fname] = fp.read_text("utf-8")[:300] if fp.exists() else None
        disk["all_files"] = [str(p.relative_to(WS)).replace("\\","/") for p in WS.rglob("*") if p.is_file() and ".fnix" not in str(p)]
        print(f"\n=== DISK ===\n{json.dumps(disk, indent=2, ensure_ascii=False)}", flush=True)

        page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v3.png", full_page=False)

        errors = [l for l in console_logs if l.startswith("error")]
        print(f"\n=== CONSOLE ERRORS ({len(errors)}) ===\n" + "\n".join(errors[:10]), flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        try: page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v3_error.png", full_page=False)
        except: pass
    finally:
        ctx.close()
        browser.close()
