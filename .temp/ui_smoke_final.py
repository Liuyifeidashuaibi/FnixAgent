# -*- coding: utf-8 -*-
"""UI 全链路 smoke：浏览器→输入任务→流式→Accept 落盘→校验产物。

验证 BUG-5 修复后 file_change 事件是否正确驱动前端 fileChanges 状态，
以及 Accept all 按钮是否出现并可点击落盘。
"""
import sys, time, json, shutil
from pathlib import Path

# UTF-8 控制台
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except: pass

from playwright.sync_api import sync_playwright

FRONTEND = "http://127.0.0.1:5175"
WS = Path("E:/FNIX/_ui_smoke_final")

# 清空工作区
if WS.exists():
    import os, stat
    def _del(p):
        os.chmod(p, stat.S_IWRITE)
    for root, dirs, files in os.walk(str(WS), topdown=False):
        for f in files: _del(os.path.join(root, f)); os.unlink(os.path.join(root, f))
        for d in dirs: os.rmdir(os.path.join(root, d))
    os.rmdir(str(WS))
WS.mkdir(parents=True, exist_ok=True)

PROMPT = "创建一个 Python 文件 calc.py，实现一个简单的加法函数 add(a, b) 返回 a+b，并在文件末尾加一行 print(add(3, 5))"

results = {}

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=False,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    page.set_default_timeout(30000)

    console_errors = []
    page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text[:200]}") if msg.type == "error" else None)

    try:
        # 1. 打开前端 + 设工作区
        print("[1] Opening frontend...", flush=True)
        page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
        page.evaluate(f"""() => localStorage.setItem('fnix.dev.workspace', '{WS}')""")
        page.reload(wait_until="domcontentloaded", timeout=45000)

        # 2. 等 Composer 就绪
        print("[2] Waiting for composer...", flush=True)
        page.locator(".glass-composer textarea").wait_for(state="visible", timeout=40000)
        print("    Composer ready", flush=True)

        # 3. 输入并发送
        print("[3] Submitting task...", flush=True)
        ta = page.locator(".glass-composer textarea")
        ta.click(timeout=10000)
        ta.fill(PROMPT)
        actual = (ta.input_value() or "").strip()
        if actual != PROMPT.strip():
            ta.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.keyboard.type(PROMPT, delay=2)
        page.keyboard.press("Escape")
        send = page.locator('button.glass-send[aria-label="发送"]')
        send.wait_for(state="visible", timeout=10000)
        page.wait_for_function(
            """() => { const b = document.querySelector('button.glass-send[aria-label="发送"]'); return !!b && !b.disabled; }""",
            timeout=10000)
        send.click(timeout=10000)
        print("    Sent, waiting for streaming...", flush=True)

        # 4. 等流式开始
        stop = page.locator("button.glass-send.stop")
        try:
            stop.wait_for(state="visible", timeout=15000)
            print("    Streaming started, waiting for completion...", flush=True)
            # 等流式结束（最长 180s）
            stop.wait_for(state="detached", timeout=180000)
            print("    Streaming completed", flush=True)
        except Exception:
            # 可能极快完成
            current = (ta.input_value() or "").strip()
            if current:
                print(f"    Warning: textarea not cleared, content: {current[:50]}", flush=True)
            # 等待 assistant 回复
            page.wait_for_function(
                """() => document.querySelectorAll('.fnix-turn.fnix-turn-assistant').length > 0""",
                timeout=120000)
            print("    Assistant response appeared", flush=True)

        time.sleep(2)  # 等 React 渲染落定

        # 5. 检查 DOM 状态：fileChanges 是否填充、review 面板是否打开
        print("[5] Checking DOM state...", flush=True)
        dom_state = page.evaluate("""() => {
            const results = {};
            // 检查 fileChanges 相关 DOM
            results.cl_diff_count = document.querySelectorAll('.cl-diff-block, .cl-diff-item').length;
            results.cl_diff_file_count = document.querySelectorAll('[data-diff-file]').length;
            results.review_panel = document.querySelectorAll('.fnix-review-panel, .fnix-inspector-review').length;
            results.accept_btn = document.querySelectorAll('.cl-diff-accept-all').length;
            results.accept_btn_visible = false;
            const btn = document.querySelector('.cl-diff-accept-all');
            if (btn) {
                const rect = btn.getBoundingClientRect();
                results.accept_btn_visible = rect.width > 0 && rect.height > 0;
                results.accept_btn_text = btn.textContent?.trim()?.substring(0, 50);
            }
            // 检查 RunCapsule（MessageBubble 中的文件变更摘要）
            results.run_capsules = document.querySelectorAll('.fnix-run-capsule, .fnix-msg-att-name').length;
            // 检查 inspector panel 状态
            results.inspector_open = !!document.querySelector('.fnix-inspector:not(.fnix-inspector-closed)');
            // assistant 文本
            const asst = document.querySelector('.fnix-turn.fnix-turn-assistant .fnix-asst-text');
            results.asst_text = asst ? asst.innerText.substring(0, 500) : '';
            return results;
        }""")
        print(f"    DOM state: {json.dumps(dom_state, indent=2, ensure_ascii=False)}", flush=True)

        # 6. 尝试 Accept all
        print("[6] Attempting Accept all...", flush=True)
        accept_clicked = False
        # 先尝试直接点 .cl-diff-accept-all
        btn = page.locator(".cl-diff-accept-all")
        for attempt in range(5):
            if btn.count() > 0:
                try:
                    if btn.is_visible():
                        btn.click(timeout=8000)
                        accept_clicked = True
                        print(f"    Accept clicked (attempt {attempt+1})", flush=True)
                        time.sleep(2)
                        break
                except: pass
            # 尝试打开 review panel
            # 点击 RunCapsule 或 file change 相关元素
            capsule = page.locator(".fnix-run-capsule, [data-diff-file], .fnix-msg-att-name")
            if capsule.count() > 0:
                try:
                    capsule.first.click(timeout=5000)
                    time.sleep(1)
                except: pass
            time.sleep(1)

        if not accept_clicked:
            # 兜底：Ctrl+Enter
            page.keyboard.press("Control+Enter")
            time.sleep(2)
            print("    Tried Ctrl+Enter fallback", flush=True)

        # 7. 检查磁盘文件
        print("[7] Checking disk for calc.py...", flush=True)
        time.sleep(1)
        calc_path = WS / "calc.py"
        disk_result = {
            "calc_exists": calc_path.exists(),
            "calc_content": "",
            "all_files": [],
        }
        if calc_path.exists():
            disk_result["calc_content"] = calc_path.read_text("utf-8")[:500]
        if WS.exists():
            disk_result["all_files"] = [str(p.relative_to(WS)).replace("\\","/")
                                        for p in WS.rglob("*") if p.is_file()
                                        and not str(p).startswith(str(WS / ".fnix"))]
        print(f"    Disk: {json.dumps(disk_result, indent=2, ensure_ascii=False)}", flush=True)

        # 8. 截图
        shot_path = Path("E:/FNIX/FnixAgent/.temp/ui_smoke_final.png")
        shot_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(shot_path), full_page=False)
        print(f"[8] Screenshot: {shot_path}", flush=True)

        results = {
            "dom_state": dom_state,
            "accept_clicked": accept_clicked,
            "disk": disk_result,
            "console_errors": console_errors[:10],
        }

    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
        results = {"error": f"{type(e).__name__}: {str(e)[:300]}", "console_errors": console_errors[:10]}
        try: page.screenshot(path="E:/FNIX/FnixAgent/.temp/ui_smoke_error.png", full_page=False)
        except: pass
    finally:
        ctx.close()
        browser.close()

print(f"\n=== RESULTS ===\n{json.dumps(results, indent=2, ensure_ascii=False)}", flush=True)
