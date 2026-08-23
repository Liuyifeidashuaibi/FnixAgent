# -*- coding: utf-8 -*-
"""UI 全链路快速验证：3 道 Python 简单题，验证 Accept → 落盘链路。"""
import sys, time, json, os, stat, shutil
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS_ROOT = Path("E:/FNIX/_ui_pilot3")

# 3 道简单 Python 题
TASKS = [
    {
        "id": "task-1-calc",
        "prompt": "创建文件 calc.py，内容为 def add(a, b): return a + b，再创建 test_calc.py 测试它",
        "expect_files": ["calc.py", "test_calc.py"],
    },
    {
        "id": "task-2-string",
        "prompt": "创建文件 string_utils.py，内容为 def reverse(s): return s[::-1]，再创建 test_string.py 测试它",
        "expect_files": ["string_utils.py", "test_string.py"],
    },
    {
        "id": "task-3-shapes",
        "prompt": "创建文件 shapes.py，内容为一个 Rectangle 类，有 area 方法返回面积，再创建 test_shapes.py 测试它",
        "expect_files": ["shapes.py", "test_shapes.py"],
    },
]

results = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    for task in TASKS:
        tid = task["id"]
        prompt = task["prompt"]
        expect = task["expect_files"]
        ws = WS_ROOT / tid

        # Clean workspace
        if ws.exists():
            for root, dirs, files in os.walk(str(ws), topdown=False):
                for f in files:
                    p = os.path.join(root, f)
                    try: os.chmod(p, stat.S_IWRITE); os.unlink(p)
                    except: pass
                for d in dirs:
                    try: os.rmdir(os.path.join(root, d))
                    except: pass
            try: os.rmdir(str(ws))
            except: pass
        ws.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*60}", flush=True)
        print(f"[TASK] {tid}", flush=True)
        print(f"[PROMPT] {prompt}", flush=True)

        result = {"id": tid, "status": "unknown", "files": [], "detail": ""}
        t0 = time.time()

        try:
            # Navigate and set workspace
            page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
            page.evaluate("""() => { localStorage.clear(); }""")
            ws_str = str(ws).replace("\\", "/")
            page.evaluate(f"""(ws) => localStorage.setItem('fnix.dev.workspace', ws)""", ws_str)
            page.reload(wait_until="domcontentloaded", timeout=45000)
            page.locator(".glass-composer textarea").wait_for(state="visible", timeout=40000)

            # Submit prompt
            ta = page.locator(".glass-composer textarea")
            ta.click(timeout=10000)
            ta.fill(prompt)
            page.keyboard.press("Escape")
            send = page.locator('button.glass-send[aria-label="发送"]')
            send.wait_for(state="visible", timeout=10000)
            page.wait_for_function(
                """() => { const b = document.querySelector('button.glass-send[aria-label="发送"]'); return !!b && !b.disabled; }""",
                timeout=10000)
            send.click(timeout=10000)
            print(f"[STEP] Sent prompt", flush=True)

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
            print(f"[STEP] Task completed", flush=True)

            # Click "全部确认"
            accept_btn = page.locator('.fnix-review-btn.solid')
            clicked = False
            for _ in range(5):
                btn_count = accept_btn.count()
                if btn_count > 0:
                    for i in range(btn_count):
                        txt = accept_btn.nth(i).inner_text(timeout=1000).strip()
                        if "全部确认" in txt and not accept_btn.nth(i).is_disabled():
                            accept_btn.nth(i).click(timeout=8000)
                            print(f"[STEP] Clicked '全部确认'", flush=True)
                            clicked = True
                            time.sleep(3)
                            break
                if clicked:
                    break
                time.sleep(1)

            if not clicked:
                # Fallback: Ctrl+Enter
                page.keyboard.press("Control+Enter")
                time.sleep(3)
                print(f"[STEP] Fallback: Ctrl+Enter", flush=True)

            # Check disk
            disk_files = []
            for p in ws.rglob("*"):
                if p.is_file() and ".fnix" not in str(p):
                    disk_files.append(str(p.relative_to(ws)).replace("\\", "/"))

            result["files"] = disk_files
            result["duration_s"] = round(time.time() - t0, 1)

            # Verify expected files
            all_present = all(any(f.endswith(ef) for f in disk_files) for ef in expect)
            if all_present and len(disk_files) >= len(expect):
                result["status"] = "success"
                print(f"[OK] All expected files found: {disk_files}", flush=True)
            else:
                result["status"] = "partial"
                result["detail"] = f"Expected {expect}, got {disk_files}"
                print(f"[PARTIAL] Expected {expect}, got {disk_files}", flush=True)

        except Exception as e:
            result["status"] = "error"
            result["detail"] = f"{type(e).__name__}: {str(e)[:200]}"
            result["duration_s"] = round(time.time() - t0, 1)
            print(f"[ERROR] {result['detail']}", flush=True)
            try: page.screenshot(path=f"E:/FNIX/FnixAgent/.temp/pilot3_{tid}_error.png")
            except: pass

        results.append(result)
        print(f"[RESULT] {tid}: {result['status']} ({result['duration_s']}s) files={result['files']}", flush=True)

    ctx.close()
    browser.close()

# Summary
print(f"\n{'='*60}", flush=True)
print(f"=== PILOT 3 SUMMARY ===", flush=True)
for r in results:
    mark = {"success": "OK ", "partial": "PRT", "error": "ERR"}.get(r["status"], "???")
    print(f"  [{mark}] {r['id']} {r['duration_s']}s files={r['files']}", flush=True)
n_ok = sum(1 for r in results if r["status"] == "success")
print(f"\n成功 {n_ok}/{len(results)}", flush=True)
