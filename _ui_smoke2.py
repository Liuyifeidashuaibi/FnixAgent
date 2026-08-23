"""UI 全链路 smoke — 验证 BUG-5 修复后的 Accept 落盘流程"""
import json, time, os
from playwright.sync_api import sync_playwright

WS = r"E:\FNIX\_ui_smoke_02"
os.makedirs(WS, exist_ok=True)

PROMPT = "写一个 hello.py，内容是 print('hello world')"

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        errors = []
        page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)

        # 1. 打开工作台
        page.goto("http://127.0.0.1:5175", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)

        # 2. 找 composer 输入框并提交任务
        composer = page.query_selector(".cl-composer textarea, .cl-composer-input, textarea")
        if not composer:
            print("FAIL: composer not found")
            browser.close()
            return
        composer.fill(PROMPT)
        page.keyboard.press("Control+Enter")
        print("Task submitted, waiting for streaming...")

        # 3. 等待流式完成（network idle 或超时 90s）
        try:
            page.wait_for_load_state("networkidle", timeout=90000)
        except Exception:
            print("Note: network-idle timeout (may still be streaming)")
        page.wait_for_timeout(5000)

        # 4. 检查 review panel / Accept button
        #    Accept button lives inside review panel, which auto-opens with pending changes
        panel = page.query_selector("[class*='inspector'], [class*='review-panel'], .cl-inspector")
        accept_btn = page.query_selector(".cl-diff-accept-all, [class*='accept-all']")
        capsules = page.query_selector_all("[class*='run-capsule'], [class*='file-capsule']")
        print(f"Panel found: {panel is not None}")
        print(f"Accept button: {accept_btn is not None}")
        print(f"Capsules: {len(capsules)}")
        if accept_btn:
            # 截图按钮状态
            try:
                accept_btn.click(timeout=3000)
                print("Accept clicked")
            except Exception as e:
                print(f"Accept click failed: {e}")
            page.wait_for_timeout(2000)
        else:
            # 尝试 Ctrl+Enter 触发 apply
            page.keyboard.press("Control+Enter")
            print("Fallback: Ctrl+Enter sent")
            page.wait_for_timeout(2000)

        # 5. 验证 disk
        hello = os.path.join(WS, "hello.py")
        disk_ok = os.path.exists(hello)
        disk_content = open(hello, encoding="utf-8", errors="replace").read() if disk_ok else "NOT FOUND"
        print(f"hello.py on disk: {disk_ok}")
        print(f"Content: {disk_content.strip()[:100]}")

        # 6. 截图存证
        page.screenshot(path=r"E:\FNIX\FnixAgent\_ui_smoke2_screen.png", full_page=False)
        print("Screenshot saved: _ui_smoke2_screen.png")

        # 7. 收集 console errors
        critical_errors = [e for e in errors if "error" in e.lower() and "favicon" not in e.lower()]
        print(f"Console errors: {len(critical_errors)}")
        for e in critical_errors[:5]:
            print(f"  {e}")

        browser.close()
        print("SMOKE DONE")

run()
