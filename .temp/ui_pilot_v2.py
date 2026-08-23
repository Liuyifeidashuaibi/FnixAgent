# -*- coding: utf-8 -*-
"""UI 全链路 3 题 pilot v2：用简单 Python 题目快速验证 Accept 落盘链路。

验证链路：打开工作区 → Composer 输入 → 发送 → 流式观测 → Accept 落盘 → 产物校验
"""
import sys, time, json, os, stat, shutil
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS_ROOT = Path("E:/FNIX/_ui_pilot_v2")

# 3 个简单 Python 题目
TASKS = [
    {
        "id": "py-add-fn",
        "prompt": "创建文件 calc.py，内容为 def add(a, b): return a + b",
        "expect": ["calc.py"],
    },
    {
        "id": "py-string-utils",
        "prompt": "创建文件 string_utils.py，内容为一个 reverse(s) 函数返回反转字符串，和 is_palindrome(s) 函数判断回文",
        "expect": ["string_utils.py"],
    },
    {
        "id": "py-class-person",
        "prompt": "创建 person.py，定义一个 Person 类，有 name 和 age 属性，以及 greet() 方法返回 'Hello, I am {name}'",
        "expect": ["person.py"],
    },
]

if WS_ROOT.exists():
    shutil.rmtree(str(WS_ROOT), ignore_errors=True)
WS_ROOT.mkdir(parents=True, exist_ok=True)

results = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    for idx, task in enumerate(TASKS, 1):
        ws = WS_ROOT / task["id"]
        ws.mkdir(parents=True, exist_ok=True)
        ws_str = str(ws).replace("\\", "/")

        print(f"\n{'='*60}", flush=True)
        print(f"[TASK {idx}/{len(TASKS)}] {task['id']}", flush=True)
        print(f"  prompt: {task['prompt'][:80]}", flush=True)
        print(f"  ws: {ws_str}", flush=True)

        t0 = time.time()
        result = {"id": task["id"], "status": "unknown", "duration_s": 0, "files": [], "detail": ""}

        try:
            # Navigate + set workspace
            page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
            page.evaluate("""() => { localStorage.clear(); }""")
            page.evaluate(f"""() => localStorage.setItem('fnix.dev.workspace', {json.dumps(ws_str)})""")
            page.reload(wait_until="domcontentloaded", timeout=45000)
            page.locator(".glass-composer textarea").wait_for(state="visible", timeout=40000)

            # Submit
            ta = page.locator(".glass-composer textarea")
            ta.click(timeout=10000)
            ta.fill(task["prompt"])
            page.keyboard.press("Escape")
            send = page.locator('button.glass-send[aria-label="发送"]')
            send.wait_for(state="visible", timeout=10000)
            page.wait_for_function(
                """() => { const b = document.querySelector('button.glass-send[aria-label="发送"]'); return !!b && !b.disabled; }""",
                timeout=10000)
            send.click(timeout=10000)
            print("  [sent]", flush=True)

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
            print("  [stream done]", flush=True)

            # Click "全部确认" button
            accept_btn = page.locator('.fnix-review-btn.solid')
            btn_count = accept_btn.count()
            if btn_count > 0:
                btn_info = page.evaluate("""() => {
                    const btns = document.querySelectorAll('.fnix-review-btn.solid');
                    return [...btns].map(b => ({
                        text: b.textContent.trim(),
                        disabled: b.disabled,
                        visible: b.getBoundingClientRect().width > 0,
                    }));
                }""")
                clicked = False
                for i, info in enumerate(btn_info):
                    if "全部确认" in info["text"] and info["visible"] and not info["disabled"]:
                        accept_btn.nth(i).click(timeout=8000)
                        print(f"  [accept] Clicked '全部确认'", flush=True)
                        time.sleep(3)
                        clicked = True
                        break
                if not clicked:
                    for i, info in enumerate(btn_info):
                        if info["visible"] and not info["disabled"]:
                            accept_btn.nth(i).click(timeout=8000)
                            print(f"  [accept] Clicked fallback button '{info['text']}'", flush=True)
                            time.sleep(3)
                            break
            else:
                print("  [accept] No accept button found", flush=True)

            # Check disk
            files_on_disk = []
            for fname in task["expect"]:
                fp = ws / fname
                if fp.exists():
                    content = fp.read_text("utf-8")[:200]
                    files_on_disk.append(fname)
                    print(f"  [disk] {fname}: {content[:60]}...", flush=True)
                else:
                    print(f"  [disk] {fname}: NOT FOUND", flush=True)

            all_files = [str(p.relative_to(ws)).replace("\\", "/") for p in ws.rglob("*") if p.is_file() and ".fnix" not in str(p)]
            print(f"  [disk] all files: {all_files}", flush=True)

            result["files"] = files_on_disk
            result["duration_s"] = round(time.time() - t0, 1)
            if files_on_disk:
                result["status"] = "success"
                result["detail"] = f"Files written: {files_on_disk}"
            else:
                result["status"] = "error"
                result["detail"] = f"Expected {task['expect']} but none found. All: {all_files}"

        except Exception as e:
            result["duration_s"] = round(time.time() - t0, 1)
            result["status"] = "error"
            result["detail"] = f"{type(e).__name__}: {str(e)[:200]}"
            import traceback; traceback.print_exc()

        results.append(result)
        mark = "OK " if result["status"] == "success" else "ERR"
        print(f"  [{mark}] {result['id']} {result['duration_s']:.0f}s files={result['files']} {result['detail'][:60]}", flush=True)

    ctx.close()
    browser.close()

print(f"\n{'='*60}", flush=True)
print(f"PILOT RESULTS", flush=True)
print(f"{'='*60}", flush=True)
success = sum(1 for r in results if r["status"] == "success")
error = sum(1 for r in results if r["status"] == "error")
for r in results:
    mark = "OK " if r["status"] == "success" else "ERR"
    print(f"  {mark} {r['id']} {r['duration_s']:.0f}s files={r['files']} {r['detail'][:60]}", flush=True)
print(f"\nTotal: {success} success, {error} error out of {len(results)}", flush=True)
