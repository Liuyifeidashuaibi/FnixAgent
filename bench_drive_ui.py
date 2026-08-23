# -*- coding: utf-8 -*-
"""FnixAgent 全链路 UI 驱动：用 Playwright 驱动「真实前端界面」逐题生产。

与 bench_drive_http.py（直接打 HTTP 接口）不同，本脚本操作真实浏览器 UI：
  打开工作台(:5175) -> 在 Composer 输入题目 -> 点发送 -> 观测流式输出 ->
  -> 产物落盘(工作区文件增量) -> 界面附件/预览回显
即 WorkBuddy/Trae 式「前端 UI 点 → 后端 → LLM 工具调用 → 落盘 → 预览回显」纯前端全链路。

工作区隔离（复刻 B6 语义）：
  - web-bench 按项目(subset)共享工作区、项目内串行（顺序依赖）
  - 其余数据集按题独立工作区
  通过 DEV 钩子 localStorage["fnix.dev.workspace"] + reload 切换（见 DesktopApp.tsx boot）。

用法（用带 playwright 的解释器运行，例如 E:/Environments/python.exe）：
  python bench_drive_ui.py --pilot 5                # 冒烟
  python bench_drive_ui.py --project calculator     # 只跑 web-bench 某项目
  python bench_drive_ui.py --dataset vibe-code-bench
  python bench_drive_ui.py                          # 全量（断点续跑，可反复执行）
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.bench.datasets import DatasetManager  # noqa: E402

# Windows 控制台默认 GBK，print 含 emoji/⚠ 等会 UnicodeEncodeError 崩溃。
# 统一重配为 utf-8（errors=replace 兜底），避免长跑中途因打印崩溃。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _safe(s: str) -> str:
    """打印前把非 ASCII 字符替换为 '?'，彻底规避 GBK/UTF-8 编码崩溃。"""
    if not isinstance(s, str):
        return str(s)
    return s.encode("ascii", "replace").decode("ascii")


FRONTEND = "http://127.0.0.1:5175"
RESULTS = ROOT / "bench_ui_results.jsonl"
DATASET_ROOT = ROOT / "benchmarks" / "benchforge" / "datasets"
WS_ROOT = Path.home() / ".fnix" / "workspaces"
SHOTS = ROOT / "outputs" / "bench_ui_shots"
RUN_TAG = time.strftime("%Y%m%d-%H%M%S")

INFRA_KEYWORDS = (
    "quota", "429", "rate limit", "限流", "配额", "余额", "access denied",
    "insufficient", "throttl", "free quota", "model not exist", "403",
)


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s)[:80]


def _workspace_for(task) -> str:
    """返回「绝对路径」工作区名（产品中即项目文件夹路径）：
    后端对绝对路径直接使用；相对路径会按后端 cwd 解析，必须避免。
    """
    if task.dataset == "web-bench" and task.subset:
        return str(WS_ROOT / "bench" / "web-bench" / _slug(task.subset))
    return str(WS_ROOT / "bench" / task.dataset / _slug(task.task_id))


def _workspace_dir(ws: str) -> Path:
    return Path(ws)


def _files_written(ws_dir: Path, since: float) -> list[str]:
    """落盘证据：工作区内 mtime >= since 的文件（相对路径，排序）。"""
    out = []
    if ws_dir.exists():
        for p in ws_dir.rglob("*"):
            if p.is_file():
                try:
                    if p.stat().st_mtime >= since - 3:
                        out.append(str(p.relative_to(ws_dir)).replace("\\", "/"))
                except OSError:
                    continue
    return sorted(set(out))


# ---------------------------------------------------------------------------
# UI 驱动（Playwright sync API；单浏览器上下文 = 单工作区）
# ---------------------------------------------------------------------------
class UiDriver:
    def __init__(self, playwright, headless: bool = False, viewport: dict | None = None):
        self.browser = playwright.chromium.launch(
            channel="chrome", headless=headless,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        )
        self.context = self.browser.new_context(
            viewport=viewport or {"width": 1440, "height": 900},
            locale="zh-CN",
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)

    def close(self):
        try:
            self.context.close()
            self.browser.close()
        except Exception:
            pass

    def open_workspace(self, ws: str):
        """切到指定工作区：设 localStorage 钩子 + reload，等 Composer 就绪。"""
        self.page.goto(FRONTEND, wait_until="domcontentloaded", timeout=45000)
        self.page.evaluate(
            """(ws) => localStorage.setItem('fnix.dev.workspace', ws)""", ws)
        self.page.reload(wait_until="domcontentloaded", timeout=45000)
        self.wait_composer(40000)

    def wait_composer(self, timeout_ms: int = 30000):
        self.page.locator(".glass-composer textarea").wait_for(
            state="visible", timeout=timeout_ms)

    def new_chat(self):
        """左侧「新任务」→ 空会话 + home Composer（同一工作区，后端新 session）。"""
        self.page.locator("button.fnix-nav-primary").click(timeout=10000)
        self.wait_composer()

    def submit(self, prompt: str, timeout_s: int):
        """输入题目并发送；等待流式开始→结束。返回 (ok, detail)。

        流式开始超时给 120s：主模型配额耗尽自动切换兜底模型时，
        首个 chunk 可能延迟较久（日志：qwen-turbo→qwen-plus 切换）。
        """
        try:
            ta = self.page.locator(".glass-composer textarea")
            # 先确保 textarea 可交互（focus + 清空 + 填写 + 校验）
            ta.click(timeout=10000)
            ta.fill("")
            # fill 偶发对 React 受控组件不生效：逐字输入兜底
            ta.fill(prompt)
            actual = (ta.input_value() or "").strip()
            if actual != prompt.strip():
                # 兜底：用 type 逐字触发 React onChange
                ta.click(timeout=10000)
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Delete")
                self.page.keyboard.type(prompt, delay=2)
                actual = (ta.input_value() or "").strip()
            if actual != prompt.strip():
                return False, f"fill failed: textarea has {len(actual)} chars, expected {len(prompt)}"
            self.page.keyboard.press("Escape")  # 关闭 @file 补全 popover
            send = self.page.locator('button.glass-send[aria-label="发送"]')
            # React 受控值提交后按钮必须已启用；若尚未完成状态刷新，短暂等待。
            send.wait_for(state="visible", timeout=10000)
            self.page.wait_for_function(
                """() => {
                  const b = document.querySelector('button.glass-send[aria-label="发送"]');
                  return !!b && !b.disabled;
                }""",
                timeout=10000,
            )
            send.click(timeout=10000)
            stop = self.page.locator("button.glass-send.stop")
            try:
                # 正常路径：流式开始后发送按钮切换为停止按钮。
                stop.wait_for(state="visible", timeout=15000)
            except Exception:
                # 极快任务可能在轮询前已经完成；只有输入框仍保留原提示词时才判定未发送。
                current = (ta.input_value() or "").strip()
                if current != "":
                    return False, f"send not acknowledged; textarea still has {len(current)} chars"
                # 已清空表示 sendDraft 已消费输入，继续等待结果或错误回显。
                try:
                    self.page.wait_for_function(
                        """() => document.querySelectorAll('.fnix-turn.fnix-turn-assistant').length > 0""",
                        timeout=105000,
                    )
                except Exception:
                    return False, self.feed_tail(800) or "sent but no assistant response"
                self._accept_all_changes()
                return True, ""
            stop.wait_for(state="detached", timeout=timeout_s * 1000)  # 流式结束
            # 流式结束后：Code 模式是「先审后写」(preview=True)，文件变更以
            # DiffBlock 呈现，需点「Accept all remaining」才真正落盘。评测要
            # 验证「落盘」链路，故自动 Accept（WorkBuddy/Trae 式的验收动作）。
            self._accept_all_changes()
            return True, ""
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:200]}"

    def _accept_all_changes(self):
        """若存在「全部确认」按钮则点击，使 preview 变更真正落盘。

        优先点 .fnix-review-btn.solid（review 面板自动展开后可见）；
        兜底用 Ctrl+Enter 快捷键（useShellHotkeys 注册，review open 时 Accept all）。
        """
        try:
            btn = self.page.locator(".fnix-review-btn.solid")
            for _ in range(5):
                if btn.count() > 0:
                    # Find the "全部确认" button specifically
                    for i in range(btn.count()):
                        txt = btn.nth(i).inner_text(timeout=1000).strip()
                        if "全部确认" in txt and not btn.nth(i).is_disabled():
                            btn.nth(i).click(timeout=8000)
                            self.page.wait_for_timeout(2500)  # 等 apply 完成 + 重渲染
                            return
                self.page.wait_for_timeout(800)
            # 兜底：快捷键 Accept all
            self.page.keyboard.press("Control+Enter")
            self.page.wait_for_timeout(2500)
        except Exception:
            pass

    def feed_tail(self, n: int = 1500) -> str:
        """最近一条 assistant 回复文本（优先 .fnix-asst-text），兜底整个 feed 尾部。"""
        try:
            asst = self.page.locator(
                ".fnix-turn.fnix-turn-assistant .fnix-asst-text").last
            if asst.count() > 0:
                txt = asst.inner_text()
                if txt.strip():
                    return txt[-n:]
            el = self.page.locator(".fnix-feed")
            if el.count() == 0:
                return ""
            txt = el.inner_text()
            return txt[-n:]
        except Exception:
            return ""

    def attachment_names(self) -> list[str]:
        """界面消息中展示的产物附件名。"""
        try:
            loc = self.page.locator(".fnix-msg-att-name")
            if loc.count() == 0:
                return []
            return [x.strip() for x in loc.all_inner_texts() if x.strip()]
        except Exception:
            return []

    def preview_shot(self, path: Path):
        """打开右侧工作台面（Canvas 预览）截图后关闭，作为「预览回显」证据。"""
        try:
            toggle = self.page.locator('button.fnix-ibtn.sm[title^="工作台面"]')
            if toggle.count() > 0 and toggle.is_visible():
                toggle.click(timeout=8000)
                self.page.wait_for_timeout(2500)
                self.page.screenshot(path=str(path), full_page=False)
                toggle.click(timeout=8000)  # 关闭，回到正常态
        except Exception:
            pass

    def screenshot(self, path: Path):
        try:
            self.page.screenshot(path=str(path), full_page=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 结果记录 / 断点续跑
# ---------------------------------------------------------------------------
def _load_done() -> dict[str, dict]:
    done = {}
    if RESULTS.exists():
        for line in RESULTS.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            done[f"{r['dataset']}/{r['task_id']}"] = r
    return done


def _record(res: dict):
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")


def _classify(text: str, files: list[str], arts: list[str]) -> str:
    low = text.lower()
    # 真实产物 = 排除 .fnix/ 下的框架自动文件(memories.json/skills.json 等)。
    # 这些文件每次会话都会写入，即使模型限流/失败也会产生，不能作为"题目成功"的证据。
    real_files = [f for f in files if not f.startswith(".fnix/")]
    if real_files or arts:
        return "success"
    if any(k in low for k in INFRA_KEYWORDS):
        return "infra_skip"
    return "error"


def main() -> int:
    ap = argparse.ArgumentParser(description="FnixAgent 全链路 UI 驱动（真实前端）")
    ap.add_argument("--dataset", default="", help="逗号分隔数据集名（默认全部）")
    ap.add_argument("--project", default="", help="只跑 web-bench 某项目（subset）")
    ap.add_argument("--pilot", type=int, default=0, help="只跑前 N 个执行单元（冒烟）")
    ap.add_argument("--timeout", type=int, default=600, help="单题 UI 完成超时(秒)")
    ap.add_argument("--headless", action="store_true", help="无头模式（默认可见窗口）")
    ap.add_argument("--retry-skip", action="store_true", help="把之前的 infra_skip 也当作待跑")
    ap.add_argument("--shot-every", type=int, default=0, help="每 N 题截图一张留档(0=关闭)")
    ap.add_argument("--shots-on-error", action="store_true", default=True, help="出错时截图")
    ap.add_argument("--preview-sample", type=int, default=0,
                    help="每 N 题成功且落盘后，打开右侧工作台面截图作「预览回显」证据")
    args = ap.parse_args()

    mgr = DatasetManager(DATASET_ROOT)
    ds_list = [d for d in args.dataset.split(",") if d] or None
    tasks = list(mgr.load_all(ds_list, refresh=False))
    if args.project:
        tasks = [t for t in tasks if t.dataset == "web-bench" and (t.subset or "") == args.project]
    if not tasks:
        print("[fatal] 没有任务可跑", file=sys.stderr)
        return 1

    done = _load_done()

    # 执行单元：web-bench 按项目串行；其余每题独立
    web_units: dict[str, list] = {}
    other_units: list = []
    for t in tasks:
        if t.dataset == "web-bench":
            web_units.setdefault(t.subset or "_", []).append(t)
        else:
            other_units.append(t)

    def _pending(t) -> bool:
        r = done.get(f"{t.dataset}/{t.task_id}")
        if r and r["status"] == "success":
            return False
        if r and r["status"] == "infra_skip" and not args.retry_skip:
            return False
        return True

    units = []
    for sub, tl in sorted(web_units.items()):
        pend = [t for t in tl if _pending(t)]
        if pend:
            units.append(("project", sub, pend))
    for t in other_units:
        if _pending(t):
            units.append(("single", None, t))

    if args.pilot:
        units = units[: args.pilot]

    total = len(tasks)
    n_pending = sum(len(u[2]) if u[0] == "project" else 1 for u in units)
    print(f"[info] 总题数 {total} | 待跑单元 {len(units)} (含 {n_pending} 题) | "
          f"已完成 {sum(1 for r in done.values() if r['status']=='success')} "
          f"| 超时 {args.timeout}s | headless={args.headless}", file=sys.stderr)

    SHOTS.mkdir(parents=True, exist_ok=True)
    counters = {"success": 0, "error": 0, "infra_skip": 0}
    for r in done.values():
        counters[r["status"]] = counters.get(r["status"], 0) + 1
    n_success_total = counters["success"]

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        driver = UiDriver(pw, headless=args.headless)
        try:
            shot_ix = 0
            for ui, (kind, sub, tl) in enumerate(units, 1):
                if kind == "project":
                    ws = str(WS_ROOT / "bench" / "web-bench" / _slug(sub))
                    print(f"[unit {ui}/{len(units)}] project={sub} 题数={len(tl)} ws={ws}",
                          flush=True)
                    driver.open_workspace(ws)
                    for j, t in enumerate(tl, 1):
                        n_success_total, shot_ix = _run_one(
                            driver, t, ws, args, counters, n_success_total, total,
                            shot_ix, new_chat=(j > 1))
                else:
                    t = tl
                    ws = _workspace_for(t)
                    print(f"[unit {ui}/{len(units)}] single {t.dataset}/{t.task_id} ws={ws}",
                          flush=True)
                    driver.open_workspace(ws)
                    n_success_total, shot_ix = _run_one(
                        driver, t, ws, args, counters, n_success_total, total,
                        shot_ix, new_chat=False)
        finally:
            driver.close()

    print(f"\n[done] 成功 {counters.get('success',0)} 能力失败 {counters.get('error',0)} "
          f"限流跳过 {counters.get('infra_skip',0)} | 结果: {RESULTS}", file=sys.stderr)
    return 0


def _run_one(driver: UiDriver, task, ws: str, args, counters: dict,
             n_success: int, total: int, shot_ix: int, new_chat: bool):
    """跑单题；返回 (n_success, shot_ix)。"""
    t0 = time.time()
    ws_dir = _workspace_dir(ws)
    res = {
        "dataset": task.dataset, "task_id": task.task_id, "subset": task.subset,
        "workspace": ws, "status": "unknown", "detail": "",
        "duration_s": 0.0, "files_written": [], "artifacts": [],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        if new_chat:
            driver.new_chat()
        ok, err = driver.submit(task.prompt, args.timeout)
        res["duration_s"] = round(time.time() - t0, 1)
        if not ok:
            res["status"] = "error"
            res["detail"] = err
        else:
            time.sleep(1)  # 等 React 渲染落定
            files = _files_written(ws_dir, t0)
            arts = driver.attachment_names()
            text = driver.feed_tail(1500)
            res["status"] = _classify(text, files, arts)
            res["files_written"] = files[:40]
            res["artifacts"] = arts[:40]
            res["detail"] = text[:300]
    except Exception as e:
        res["duration_s"] = round(time.time() - t0, 1)
        res["status"] = "error"
        res["detail"] = f"{type(e).__name__}: {str(e)[:200]}"
        # 页面级故障：尝试重开工作区自愈
        try:
            driver.open_workspace(ws)
        except Exception:
            pass

    _record(res)
    counters[res["status"]] = counters.get(res["status"], 0) + 1
    n_success += 1 if res["status"] == "success" else 0
    mark = {"success": "OK ", "error": "ERR", "infra_skip": "SKP"}.get(res["status"], "???")
    print(_safe(f"[{n_success}/{total}] {mark} {res['dataset']}/{res['task_id']} "
                f"{res['duration_s']:.0f}s files={len(res['files_written'])} "
                f"{res['detail'][:60]}"), flush=True)

    shot_ix += 1
    do_shot = res["status"] in ("error", "infra_skip") or (
        args.shot_every > 0 and shot_ix % args.shot_every == 0)
    if do_shot:
        safe = f"{_slug(task.dataset)}__{_slug(task.task_id)}"
        driver.screenshot(SHOTS / f"{safe}.png")
    if (args.preview_sample > 0 and res["status"] == "success"
            and res["files_written"] and shot_ix % args.preview_sample == 0):
        safe = f"{_slug(task.dataset)}__{_slug(task.task_id)}__preview"
        driver.preview_shot(SHOTS / f"{safe}.png")
    return n_success, shot_ix


if __name__ == "__main__":
    raise SystemExit(main())
