# -*- coding: utf-8 -*-
"""UI smoke v6：直接点击 .fnix-review-btn.solid 验证 Accept 落盘。"""
import sys, time, json, os, stat
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_smoke_v6")

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

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    try:
        page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
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
        print("Task completed", flush=True)

        # Check if "全部确认" button exists and click it directly
        accept_btn = page.locator('.fnix-review-btn.solid')
        btn_count = accept_btn.count()
        print(f"Accept button count (.fnix-review-btn.solid): {btn_count}", flush=True)

        if btn_count > 0:
            # Get button info
            btn_info = page.evaluate("""() => {
                const btns = document.querySelectorAll('.fnix-review-btn.solid');
                return [...btns].map(b => ({
                    text: b.textContent.trim(),
                    disabled: b.disabled,
                    visible: b.getBoundingClientRect().width > 0,
                    rect: {
                        x: b.getBoundingClientRect().x,
                        y: b.getBoundingClientRect().y,
                        w: b.getBoundingClientRect().width,
                        h: b.getBoundingClientRect().height
                    }
                }));
            }""")
            print(f"Button info: {json.dumps(btn_info, ensure_ascii=False)}", flush=True)

            # Find the "全部确认" button specifically
            for i, info in enumerate(btn_info):
                if "全部确认" in info["text"] and info["visible"] and not info["disabled"]:
                    print(f"\nClicking '全部确认' button (index {i})...", flush=True)
                    accept_btn.nth(i).click(timeout=8000)
                    time.sleep(3)
                    print("Clicked!", flush=True)
                    break
            else:
                print("'全部确认' not found or not clickable, trying first visible solid button", flush=True)
                for i, info in enumerate(btn_info):
                    if info["visible"] and not info["disabled"]:
                        accept_btn.nth(i).click(timeout=8000)
                        time.sleep(3)
                        break
        else:
            print("No accept button found, trying Ctrl+Enter", flush=True)
            page.keyboard.press("Control+Enter")
            time.sleep(3)

        # Take screenshot BEFORE checking disk (to see the state after click)
        page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v6.png", full_page=False)

        # Check disk
        disk = {}
        for fname in ["calc.py", "test_calc.py"]:
            fp = WS / fname
            if fp.exists():
                content = fp.read_text("utf-8")
                disk[fname] = content[:300]
            else:
                disk[fname] = None
        disk["all_files"] = [str(p.relative_to(WS)).replace("\\","/") for p in WS.rglob("*") if p.is_file() and ".fnix" not in str(p)]
        print(f"\n=== DISK ===\n{json.dumps(disk, indent=2, ensure_ascii=False)}", flush=True)

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        try: page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_v6_error.png", full_page=False)
        except: pass
    finally:
        ctx.close()
        browser.close()
