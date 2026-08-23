# -*- coding: utf-8 -*-
"""UI smoke v5：修复选择器 + 完整 Accept 落盘验证。"""
import sys, time, json, os, stat
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_smoke_v5")

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
console_logs = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    page.on("console", lambda msg: console_logs.append(f"{msg.type}: {msg.text[:400]}"))

    def on_response(response):
        if "/chat/agent" in response.url:
            try:
                body = response.text()
                for line in body.split("\n"):
                    line = line.strip()
                    if line:
                        try: captured_events.append(json.loads(line))
                        except: pass
            except: pass
    page.on("response", on_response)

    try:
        page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
        # Clear ALL localStorage and set workspace
        page.evaluate("""() => { localStorage.clear(); }""")
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
        print(f"\n=== CAPTURED EVENTS ({len(captured_events)}) ===", flush=True)
        for ev in captured_events:
            t = ev.get("type", "")
            if t == "file_change":
                content = ev.get("content", "")
                has_literal_n = "\\n" in content
                print(f"  [file_change] path={ev.get('path','')} action={ev.get('action','')} content_len={len(content)} literal_n={has_literal_n}", flush=True)
            elif t == "done":
                changes = ev.get("changes", [])
                print(f"  [done] status={ev.get('status','')} changes={len(changes)}", flush=True)
            elif t == "step_start":
                print(f"  [step_start] action={ev.get('step',{}).get('action','')} target={ev.get('step',{}).get('target','')}", flush=True)
            elif t == "plan":
                print(f"  [plan] steps={len(ev.get('steps',[]))}", flush=True)
            elif t == "message":
                print(f"  [message] {str(ev.get('content',''))[:200]}", flush=True)
            elif t == "heartbeat":
                pass
            else:
                print(f"  [{t}]", flush=True)

        # DOM state - use querySelectorAll with valid CSS only
        state = page.evaluate("""() => {
            const r = {};
            // Inspector
            const inspector = document.querySelector('.fnix-inspector:not(.fnix-inspector-closed)');
            r.inspector_open = !!inspector;
            // Overlays
            r.overlay_count = document.querySelectorAll('[role="dialog"]').length;
            r.overlay_classes = [...document.querySelectorAll('[role="dialog"]')].map(e => e.className).filter(Boolean);
            // All buttons with tab-like classes
            const allTabs = document.querySelectorAll('[role="tab"]');
            r.all_tab_texts = [...allTabs].map(t => t.textContent?.trim()).filter(Boolean);
            // Studio tabs
            const studioTabs = document.querySelectorAll('.studio-tab, [class*="studio-tab"]');
            r.studio_tab_texts = [...studioTabs].map(t => t.textContent?.trim()).filter(Boolean);
            // Diff blocks
            r.diff_blocks = document.querySelectorAll('.cl-diff-block, [class*="diff-block"]').length;
            // Accept buttons - look for buttons with "全部确认" text
            const allBtns = document.querySelectorAll('button');
            r.review_btns = [...allBtns].filter(b => {
                const t = b.textContent?.trim() || '';
                return t.includes('全部确认') || t.includes('Accept') || t.includes('确认');
            }).map(b => ({
                text: b.textContent?.trim(),
                cls: b.className,
                disabled: b.disabled,
                visible: b.getBoundingClientRect().width > 0
            }));
            // RunCapsule (file change indicators)
            r.run_capsules = document.querySelectorAll('[class*="capsule"]').length;
            // Assistant text
            const asst = document.querySelector('.fnix-turn.fnix-turn-assistant .fnix-asst-text');
            r.asst_text = asst ? asst.innerText.substring(0, 300) : '';
            // Inspector content
            if (inspector) {
                r.inspector_content = inspector.innerText.substring(0, 800);
            }
            return r;
        }""")
        print(f"\n=== DOM STATE ===\n{json.dumps(state, indent=2, ensure_ascii=False)}", flush=True)

        # Close any overlay with Escape
        print("\n=== CLOSING OVERLAYS ===", flush=True)
        page.keyboard.press("Escape")
        time.sleep(1)

        # Check if review tab exists and click it
        review_tab = page.locator('[role="tab"]').filter(has_text="评审")
        print(f"Review tab count: {review_tab.count()}", flush=True)
        if review_tab.count() > 0:
            try:
                review_tab.first.click(timeout=5000)
                time.sleep(2)
                print("Clicked review tab", flush=True)
            except Exception as e:
                print(f"Review tab click failed: {e}", flush=True)

        # Check for accept button
        accept_btn = page.locator('button').filter(has_text="全部确认")
        print(f"Accept button count: {accept_btn.count()}", flush=True)
        if accept_btn.count() > 0:
            btn_info = page.evaluate("""() => {
                const btns = [...document.querySelectorAll('button')].filter(b => b.textContent?.includes('全部确认'));
                return btns.map(b => ({
                    text: b.textContent?.trim(),
                    disabled: b.disabled,
                    visible: b.getBoundingClientRect().width > 0,
                    rect: b.getBoundingClientRect()
                }));
            }""")
            print(f"Accept btn info: {json.dumps(btn_info, ensure_ascii=False)}", flush=True)
            
            if btn_info and btn_info[0].get("visible") and not btn_info[0].get("disabled"):
                print("Clicking Accept All!", flush=True)
                accept_btn.first.click(timeout=8000)
                time.sleep(3)
            else:
                print("Accept not clickable, trying Ctrl+Enter", flush=True)
                page.keyboard.press("Control+Enter")
                time.sleep(3)
        else:
            print("No accept button found, trying Ctrl+Enter", flush=True)
            page.keyboard.press("Control+Enter")
            time.sleep(3)

        # Check disk
        disk = {}
        for fname in ["calc.py", "test_calc.py"]:
            fp = WS / fname
            disk[fname] = fp.read_text("utf-8")[:300] if fp.exists() else None
        disk["all_files"] = [str(p.relative_to(WS)).replace("\\","/") for p in WS.rglob("*") if p.is_file() and ".fnix" not in str(p)]
        print(f"\n=== DISK ===\n{json.dumps(disk, indent=2, ensure_ascii=False)}", flush=True)

        page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v5.png", full_page=False)

        errors = [l for l in console_logs if l.startswith("error")]
        print(f"\n=== CONSOLE ERRORS ({len(errors)}) ===", flush=True)
        for e in errors[:10]: print(f"  {e}", flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        try: page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v5_error.png", full_page=False)
        except: pass
    finally:
        ctx.close()
        browser.close()
