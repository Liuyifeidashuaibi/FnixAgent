# -*- coding: utf-8 -*-
"""全链路 UI 冒烟（增强）：验证 发送→流式→Accept→落盘 全链路，并定位 Accept 是否真正持久化。"""
import sys, time, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from playwright.sync_api import sync_playwright
from bench_drive_ui import WS_ROOT

WS = str(WS_ROOT / "bench" / "ui_smoke_02")
PROMPT = "在当前工作区创建一个 hello.py 文件，内容为一行代码：print('hello fnix')"

console_errs, page_errs = [], []
def on_console(m):
    if m.type in ("error", "warning"):
        console_errs.append(f"[{m.type}] {m.text}")
def on_pageerror(e):
    page_errs.append(str(e))

with sync_playwright() as pw:
    from bench_drive_ui import UiDriver
    driver = UiDriver(pw, headless=True, viewport={"width": 1440, "height": 900})
    driver.page.on("console", on_console)
    driver.page.on("pageerror", on_pageerror)
    try:
        t0 = time.time()
        driver.open_workspace(WS)
        ok, err = driver.submit(PROMPT, timeout_s=240)
        dur = round(time.time() - t0, 1)
        # 等待 diff 面板渲染（最多 15s）
        acc_visible = False
        for _ in range(30):
            btn = driver.page.locator(".cl-diff-accept-all")
            if btn.count() > 0 and btn.is_visible():
                acc_visible = True
                break
            driver.page.wait_for_timeout(500)
        # 点击 Accept all
        accept_clicked = False
        if acc_visible:
            try:
                driver.page.locator(".cl-diff-accept-all").click(timeout=8000)
                accept_clicked = True
                driver.page.wait_for_timeout(2000)
            except Exception as e:
                err2 = str(e)[:120]
        else:
            # 兜底：Ctrl+Enter
            try:
                driver.page.keyboard.press("Control+Enter")
                accept_clicked = True
                driver.page.wait_for_timeout(2000)
            except Exception:
                pass
        time.sleep(1)
        import os
        ws_dir = Path(WS)
        files = []
        for p in ws_dir.rglob("*"):
            if p.is_file() and ".fnix" not in p.parts:
                files.append(str(p.relative_to(ws_dir)).replace("\\", "/"))
        # DOM 探针：diff 块是否渲染、accept 按钮是否存在、review 面板状态
        dom = {}
        try:
            dom["cl_diff_count"] = driver.page.locator(".cl-diff").count()
            dom["cl_diff_file_count"] = driver.page.locator(".cl-diff-file").count()
            dom["cl_diff_accept_all"] = driver.page.locator(".cl-diff-accept-all").count()
            dom["review_panel"] = driver.page.locator(".fnix-review-panel, .review-panel").count()
            dom["apply_msg"] = (driver.page.locator(".fnix-apply-msg, .cl-apply-msg").last.inner_text()[:120]
                                 if driver.page.locator(".fnix-apply-msg, .cl-apply-msg").count() else "")
            # 是否出现「没有待应用的变更」类提示
            dom["no_pending_hint"] = driver.page.locator("text=没有待应用").count()
        except Exception as e:
            dom["probe_err"] = str(e)[:120]
        text = driver.feed_tail(800)
        # 是否已写入（找 apply 成功提示）
        applied_msg = ""
        try:
            applied_msg = driver.page.locator(".fnix-apply-msg, .cl-apply-msg").last.inner_text()[:120]
        except Exception:
            pass
        driver.screenshot(ROOT / "outputs" / "bench_ui_shots" / "ui_smoke2.png")
        print(json.dumps({
            "submit_ok": ok, "submit_err": err[:160], "duration_s": dur,
            "accept_button_visible": acc_visible, "accept_clicked": accept_clicked,
            "disk_files": files,
            "apply_message": applied_msg,
            "dom": dom,
            "assistant_tail": text[:200],
            "console_errors": console_errs[:10], "page_errors": page_errs[:6],
        }, ensure_ascii=False, indent=2))
    finally:
        driver.close()
