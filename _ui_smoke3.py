"""UI 全链路 smoke v3 — 验证 BUG-5 + Accept 落盘流程
改进：去掉 networkidle，改轮询等待 done 状态出现，然后点击 Accept
"""
import json, time, os
from playwright.sync_api import sync_playwright

WS = r"E:\FNIX\_ui_smoke_03"
os.makedirs(WS, exist_ok=True)

# 先清空 workspace
import shutil
if os.path.exists(WS):
    for root, dirs, files in os.walk(WS):
        for f in files:
            try: os.unlink(os.path.join(root, f))
            except: pass
        for d in dirs:
            try: os.rmdir(os.path.join(root, d))
            except: pass

PROMPT = "写一个 hello.py，内容是 print('hello world from fnix')"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        console_errors = []
        page.on("console", lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"[pageerror] {e}"))

        # 1. 打开工作台
        print("Opening workbench...")
        page.goto("http://127.0.0.1:5175", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(3000)  # 等待前端初始化

        # 2. 找 composer
        composer = page.query_selector(".cl-composer textarea, .cl-composer-input, textarea")
        if not composer:
            print("FAIL: composer not found")
            browser.close()
            return
        print(f"Composer found, submitting task...")
        composer.fill(PROMPT)
        page.keyboard.press("Control+Enter")
        print("Task submitted, monitoring...")

        # 3. 轮询等待：文件出现 或 90s 超时
        hello_path = os.path.join(WS, "hello.py")
        deadline = time.time() + 90
        found = False
        while time.time() < deadline:
            page.wait_for_timeout(3000)
            # 检查 accept 按钮
            accept = page.query_selector(".cl-diff-accept-all, [class*='accept-all']")
            # 检查 capsules
            capsules = page.query_selector_all("[class*='run-capsule'], [class*='file-capsule']")
            # 检查 diff panel
            diff_count = page.evaluate("""
                document.querySelectorAll('[class*=\"diff\"]').length +
                document.querySelectorAll('[class*=\"file-change\"]').length +
                document.querySelectorAll('[class*=\"pending\"]').length
            """)
            # 检查 done 状态
            done_el = page.query_selector("[class*='done'], [class*='completed'], [class*='status']")
            elapsed = int(time.time() - (deadline - 90))
            print(f"  t+{elapsed}s: accept={accept is not None} capsules={len(capsules)} diffs={diff_count}")
            if os.path.exists(hello_path):
                found = True
                print(f"  hello.py FOUND at t+{elapsed}s!")
                break
            if accept is not None:
                print(f"  Accept button visible at t+{elapsed}s, clicking...")
                try:
                    accept.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    if os.path.exists(hello_path):
                        found = True
                        print(f"  hello.py written after Accept!")
                        break
                except Exception as e:
                    print(f"  Accept click failed: {e}")
        page.wait_for_timeout(2000)

        # 4. 验证 disk
        disk_ok = os.path.exists(hello_path)
        disk_content = ""
        if disk_ok:
            try:
                disk_content = open(hello_path, encoding="utf-8", errors="replace").read()
            except Exception as e:
                disk_content = f"read error: {e}"
        print(f"\n=== RESULT ===")
        print(f"hello.py on disk: {disk_ok}")
        print(f"Content: {disk_content.strip()[:120] if disk_content else 'N/A'}")

        # 5. DOM 诊断
        counts = page.evaluate("""
            ({
                capsules: document.querySelectorAll('[class*="capsule"]').length,
                diffItems: document.querySelectorAll('[class*="diff-item"]').length,
                acceptBtns: document.querySelectorAll('.cl-diff-accept-all').length,
                allBtns: document.querySelectorAll('button').length,
                inspectorOpen: !!document.querySelector('[class*="inspector"]'),
                pendingChanges: document.querySelectorAll('[class*="pending"]').length,
                processItems: document.querySelectorAll('[class*="process"]').length,
                activityItems: document.querySelectorAll('[class*="activity"]').length,
            })
        """)
        print(f"DOM: {counts}")

        # 6. 截图
        page.screenshot(path=r"E:\FNIX\FnixAgent\_ui_smoke3_screen.png", full_page=False)
        print("Screenshot: _ui_smoke3_screen.png")

        # 7. Console errors
        crit = [e for e in console_errors if "error" in e.lower() and "favicon" not in e.lower()]
        print(f"Console errors ({len(crit)}): {crit[:3]}")

        browser.close()
        print("SMOKE DONE")
        return disk_ok

ok = run()
exit(0 if ok else 1)
