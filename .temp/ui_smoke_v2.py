# -*- coding: utf-8 -*-
"""UI smoke v2：调试 fileChanges 状态 + inspector 打开 + Accept 落盘。"""
import sys, time, json, os, stat
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_smoke_v2")

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

PROMPT = "创建文件 hello.py，内容为 print('hello world')"

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"{msg.type}: {msg.text[:300]}"))

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

        # Check React state via DOM interrogation
        state = page.evaluate("""() => {
            const r = {};
            // Check all diff-related elements
            r.cl_diff_blocks = document.querySelectorAll('.cl-diff-block').length;
            r.cl_diff_items = document.querySelectorAll('.cl-diff-item').length;
            r.cl_diff_accept_all = document.querySelectorAll('.cl-diff-accept-all').length;
            r.cl_diff_accept_btn = document.querySelectorAll('.cl-diff-btn--accept').length;
            r.cl_diff_readonly = document.querySelectorAll('.cl-diff-readonly-hint').length;
            r.fnix_inspector = document.querySelectorAll('.fnix-inspector').length;
            r.fnix_inspector_open = document.querySelectorAll('.fnix-inspector:not(.fnix-inspector-closed)').length;
            r.review_panel = document.querySelectorAll('[class*="review"]').length;
            // Check for pending changes indicators
            r.msg_att = document.querySelectorAll('.fnix-msg-att-name').length;
            r.run_capsule = document.querySelectorAll('[class*="capsule"]').length;
            // Check for any accept-like buttons
            r.all_accept_btns = document.querySelectorAll('[class*="accept"], button[onclick*="accept"]').length;
            // Get the text of the assistant message
            const asst = document.querySelector('.fnix-turn.fnix-turn-assistant .fnix-asst-text');
            r.asst_text = asst ? asst.innerText.substring(0, 800) : '';
            // Check if there are any diff entries visible
            const diffEntries = document.querySelectorAll('.cl-diff-entry, .cl-diff-file-entry');
            r.diff_entries = diffEntries.length;
            // Get inspector state from React (zustand persist)
            const stored = localStorage.getItem('fnix-session-store');
            r.session_store = stored ? stored.substring(0, 500) : 'not found';
            return r;
        }""")
        print(f"\n=== DOM STATE ===\n{json.dumps(state, indent=2, ensure_ascii=False)}", flush=True)

        # Try to manually open inspector panel
        print("\n=== Trying to open inspector ===", flush=True)
        # Method 1: Click the inspector toggle button
        toggle = page.locator('button.fnix-ibtn[title*="面板"], button.fnix-ibtn[title*="工作台面"], button[aria-label*="面板"]')
        if toggle.count() > 0:
            try:
                toggle.first.click(timeout=5000)
                time.sleep(1)
                print("Clicked inspector toggle", flush=True)
            except Exception as e:
                print(f"Toggle click failed: {e}", flush=True)

        # Method 2: Look for review tab
        review_tab = page.locator('[role="tab"]:has-text("评审"), [role="tab"]:has-text("Review"), button:has-text("评审")')
        if review_tab.count() > 0:
            try:
                review_tab.first.click(timeout=5000)
                time.sleep(1)
                print("Clicked review tab", flush=True)
            except Exception as e:
                print(f"Review tab click failed: {e}", flush=True)

        time.sleep(2)

        # Re-check after attempting to open
        state2 = page.evaluate("""() => {
            const r = {};
            r.inspector_open = !!document.querySelector('.fnix-inspector:not(.fnix-inspector-closed)');
            r.cl_diff_accept_all = document.querySelectorAll('.cl-diff-accept-all').length;
            r.accept_btn_visible = false;
            const btn = document.querySelector('.cl-diff-accept-all');
            if (btn) { const rect = btn.getBoundingClientRect(); r.accept_btn_visible = rect.width > 0 && rect.height > 0; }
            r.cl_diff_btn_accept = document.querySelectorAll('.cl-diff-btn--accept').length;
            r.review_content = '';
            const rp = document.querySelector('.fnix-inspector:not(.fnix-inspector-closed)');
            if (rp) r.review_content = rp.innerText.substring(0, 500);
            return r;
        }""")
        print(f"\n=== AFTER OPEN ATTEMPT ===\n{json.dumps(state2, indent=2, ensure_ascii=False)}", flush=True)

        # Try clicking accept-all if visible
        if state2.get("accept_btn_visible"):
            print("Accept button visible! Clicking...", flush=True)
            page.locator(".cl-diff-accept-all").click(timeout=8000)
            time.sleep(2)
        else:
            # Try Ctrl+Enter as fallback
            page.keyboard.press("Control+Enter")
            time.sleep(2)
            print("Tried Ctrl+Enter", flush=True)

        # Check disk
        hello_path = WS / "hello.py"
        disk = {
            "hello_exists": hello_path.exists(),
            "hello_content": hello_path.read_text("utf-8")[:300] if hello_path.exists() else "",
            "all_files": [str(p.relative_to(WS)).replace("\\","/") for p in WS.rglob("*") if p.is_file() and not str(p).startswith(str(WS / ".fnix"))] if WS.exists() else [],
        }
        print(f"\n=== DISK ===\n{json.dumps(disk, indent=2, ensure_ascii=False)}", flush=True)

        # Screenshot
        page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v2.png", full_page=False)

        # Console errors
        errors = [l for l in console_logs if l.startswith("error")]
        print(f"\n=== CONSOLE ERRORS ({len(errors)}) ===\n" + "\n".join(errors[:5]), flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        try: page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v2_error.png", full_page=False)
        except: pass
    finally:
        ctx.close()
        browser.close()
