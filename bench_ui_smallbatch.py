# -*- coding: utf-8 -*-
"""UI 全链路小批量验证：每数据集 2-3 题。

复用 bench_drive_ui.UiDriver，但按题目粒度精确控制，只跑少量题，
并产出截图 + 落盘证据 + 预览回显证据。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _safe(s: str) -> str:
    if not isinstance(s, str):
        return str(s)
    return s.encode("ascii", "replace").decode("ascii")


from bench_drive_ui import UiDriver, _workspace_for, _workspace_dir, _files_written, _slug, SHOTS  # noqa: E402
from fnixagent.bench.datasets import DatasetManager  # noqa: E402

DATASET_ROOT = ROOT / "benchmarks" / "benchforge" / "datasets"
WS_ROOT = Path.home() / ".fnix" / "workspaces"

# 每数据集要跑的题目数
PLAN = {
    "web-bench": ["angular--task-1", "angular--task-2", "angular--task-3"],
    "vibe-code-bench": ["case_01_pomodoro"],
    "prototypebench": [],  # 后续按需
    "workbuddy-bench": [],
    "swe-bench-lite": [],
}


def main() -> int:
    mgr = DatasetManager(DATASET_ROOT)
    tasks = list(mgr.load_all(["web-bench"], refresh=False))
    by_id = {t.task_id: t for t in tasks}

    selected = []
    for tid in PLAN.get("web-bench", []):
        if tid in by_id:
            selected.append(by_id[tid])
    if not selected:
        print("[fatal] 无选中题目", file=sys.stderr)
        return 1

    SHOTS.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as pw:
        driver = UiDriver(pw, headless=True)
        try:
            # web-bench 项目共享工作区，串行
            ws = str(WS_ROOT / "bench" / "web-bench" / "angular")
            driver.open_workspace(ws)
            for i, t in enumerate(selected, 1):
                print(f"\n[题 {i}/{len(selected)}] {t.task_id}", flush=True)
                t0 = time.time()
                ws_dir = _workspace_dir(ws)
                ok, err = driver.submit(t.prompt, timeout_s=600)
                dt = time.time() - t0
                time.sleep(1)
                files = _files_written(ws_dir, t0)
                arts = driver.attachment_names()
                text = driver.feed_tail(1200)
                status = "success" if (files and any(not f.startswith(".fnix/") for f in files)) else "error"
                res = {
                    "dataset": t.dataset, "task_id": t.task_id,
                    "status": status, "detail": text[:200],
                    "duration_s": round(dt, 1), "files_written": files[:40],
                    "artifacts": arts[:20], "ok": ok, "err": err,
                }
                results.append(res)
                print(_safe(f"  [{i}] status={status} {dt:.0f}s files={len(files)} "
                            f"real={sum(1 for f in files if not f.startswith('.fnix/'))} "
                            f"arts={len(arts)} ok={ok}"), flush=True)
                if err:
                    print(_safe(f"       err: {err[:160]}"), flush=True)
                # 截图留档
                safe = f"{_slug(t.dataset)}__{_slug(t.task_id)}"
                driver.screenshot(SHOTS / f"{safe}.png")
                # 成功且落盘 → 预览回显截图
                if status == "success":
                    driver.preview_shot(SHOTS / f"{safe}__preview.png")
                if i < len(selected):
                    driver.new_chat()
        finally:
            driver.close()

    # 写结果
    out = ROOT / "bench_ui_smallbatch_results.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n[done] 结果写入 {out.name}，共 {len(results)} 题", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
