# -*- coding: utf-8 -*-
"""UI 全链路小批量 pilot：真实前端(5175) + Playwright/Chrome 模拟用户跑 3 题。

复用 bench_drive_ui.UiDriver 的全链路语义（打开工作区 → Composer 输入 →
发送 → 流式观测 → Accept 落盘 → 产物校验 → 截图），用固定小题目集，
在修复循环中快速验证「前端 UI → 后端 → LLM → 工具调用 → 落盘 → 回显」链路。

运行（用带 playwright 的解释器）：
  E:/Environments/python.exe bench_ui_pilot.py            # 可见窗口
  E:/Environments/python.exe bench_ui_pilot.py --headless # 无头
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import bench_drive_ui as bdu  # noqa: E402  (UiDriver / _files_written / _classify / _record / _safe)

DATASET_DIR = ROOT / "benchmarks" / "benchforge" / "datasets"
RESULTS = ROOT / "bench_ui_pilot_results.jsonl"
WS_ROOT = Path.home() / ".fnix" / "workspaces" / "bench" / "ui-pilot"

# 固定小题目集（多样框架 + 关键回归）
SELECT = [
    ("vibe-code-bench", "case_02_quiz"),        # 答题测试应用（新题）
    ("vibe-code-bench", "case_03_calculator"),  # 计算器（新题）
    ("vibe-code-bench", "case_04_notes"),       # 笔记应用（新题）
    ("vibe-code-bench", "case_06_kanban"),      # 看板（拖拽+localStorage，新题）
    ("web-bench", "angular--task-1"),           # 回归：多文件组件 + heal
]


def _load(dataset: str, task_id: str) -> dict:
    p = DATASET_DIR / dataset / "tasks.jsonl"
    for line in p.read_text("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("task_id") == task_id:
            r.setdefault("dataset", dataset)
            r.setdefault("subset", "")
            return r
    raise KeyError(f"{dataset}/{task_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description="FnixAgent UI 全链路小批量 pilot")
    ap.add_argument("--headless", action="store_true", help="无头模式")
    ap.add_argument("--timeout", type=int, default=900, help="单题 UI 完成超时(秒)")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    # 覆盖已有结果（pilot 是回归验证，重跑覆盖）
    if RESULTS.exists():
        RESULTS.unlink()

    with sync_playwright() as pw:
        driver = bdu.UiDriver(pw, headless=args.headless)
        counters = {"success": 0, "error": 0, "infra_skip": 0}
        try:
            for i, (ds, tid) in enumerate(SELECT, 1):
                rec = _load(ds, tid)
                ws = str(WS_ROOT / tid.replace("/", "_"))
                if os.path.exists(ws):
                    shutil.rmtree(ws)
                os.makedirs(ws, exist_ok=True)
                t0 = time.time()
                res = {
                    "dataset": ds, "task_id": tid, "subset": rec.get("subset", ""),
                    "workspace": ws, "status": "unknown", "detail": "",
                    "duration_s": 0.0, "files_written": [], "artifacts": [],
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                print(f"[pilot {i}/{len(SELECT)}] {ds}/{tid} -> {ws}", flush=True)
                try:
                    driver.open_workspace(ws)
                    ok, err = driver.submit(rec["prompt"], args.timeout)
                    res["duration_s"] = round(time.time() - t0, 1)
                    if not ok:
                        res["status"] = "error"
                        res["detail"] = err
                    else:
                        time.sleep(1)
                        files = bdu._files_written(Path(ws), t0)
                        arts = driver.attachment_names()
                        text = driver.feed_tail(1500)
                        res["status"] = bdu._classify(text, files, arts)
                        res["files_written"] = files[:40]
                        res["artifacts"] = arts[:40]
                        res["detail"] = text[:300]
                except Exception as e:
                    res["duration_s"] = round(time.time() - t0, 1)
                    res["status"] = "error"
                    res["detail"] = f"{type(e).__name__}: {str(e)[:200]}"
                    try:
                        driver.open_workspace(ws)
                    except Exception:
                        pass
                bdu._record(res)
                counters[res["status"]] = counters.get(res["status"], 0) + 1
                mark = {"success": "OK ", "error": "ERR", "infra_skip": "SKP"}.get(res["status"], "???")
                print(bdu._safe(f"[{i}/{len(SELECT)}] {mark} {ds}/{tid} {res['duration_s']:.0f}s "
                                f"files={len(res['files_written'])} {res['detail'][:80]}"), flush=True)
                if res["status"] in ("error", "infra_skip"):
                    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in tid)[:80]
                    bdu.SHOTS.mkdir(parents=True, exist_ok=True)
                    driver.screenshot(bdu.SHOTS / f"pilot__{safe}.png")
        finally:
            driver.close()

    print(f"\n[pilot done] 成功 {counters.get('success',0)} 失败 {counters.get('error',0)} "
          f"跳过 {counters.get('infra_skip',0)} | {RESULTS}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
