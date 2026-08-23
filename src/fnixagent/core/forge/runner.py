"""FnixForge — 单题沙箱执行与轨迹采集。

每道题获得一个独立临时沙箱:
  1. materialize — 按 task.setup.files 铺初始文件
  2. snapshot    — 调用前记录全部文件的 sha1（before）
  3. invoke      — 通过适配器驱动被测 Agent
  4. snapshot    — 调用后记录 sha1（after），得出 changed/removed
  5. checks      — 确定性判定 + 评分

沙箱与目标项目**完全隔离**——Agent 的能力验证不应污染其源码目录。
修复阶段由 fixer 在目标项目另行操作。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from fnixagent.core.forge.adapters import (
    AdapterConfig,
    TargetAdapter,
    TargetResponse,
    resolve_adapter,
)
from fnixagent.core.forge.checks import run_all_checks
from fnixagent.core.forge.scorer import TaskScore, score_task
from fnixagent.core.forge.spec import ForgeTask

_logger = logging.getLogger(__name__)

_SNAPSHOT_IGNORE = {".git", "node_modules", "__pycache__", ".venv", "venv", ".fnix-forge"}
_SNAPSHOT_MAX_FILE = 4 * 1024 * 1024  # >4MB 文件按大小+路径记指纹，不读内容

@dataclass
class TaskRunRecord:
    """一题一次的完整轨迹。"""
    task_id: str
    score: TaskScore
    response: TargetResponse
    sandbox_dir: str = ""
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "score": self.score.to_dict(),
            "response": {
                "exit_code": self.response.exit_code,
                "stdout_tail": (self.response.stdout or "")[-2000:],
                "stderr_tail": (self.response.stderr or "")[-2000:],
                "message_tail": (self.response.message or "")[-2000:],
                "elapsed_s": round(self.response.elapsed_s, 2),
                "error": self.response.error,
                "changed": sorted(self.response.changed),
                "removed": sorted(self.response.removed),
            },
            "sandbox_dir": self.sandbox_dir,
            "started_at": self.started_at,
        }

def _sha1(p: Path) -> str:
    if p.stat().st_size > _SNAPSHOT_MAX_FILE:
        return f"big:{p.stat().st_size}:{p.stat().st_mtime_ns}"
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def snapshot_tree(root: Path) -> dict[str, str]:
    """root 下所有文件 -> sha1 指纹。"""
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in _SNAPSHOT_IGNORE for part in rel_parts):
            continue
        try:
            out[str(p.relative_to(root)).replace("\\", "/")] = _sha1(p)
        except OSError:
            continue
    return out

def materialize_sandbox(task: ForgeTask, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for rel, content in ((task.setup or {}).get("files") or {}).items():
        rel_clean = str(rel).lstrip("/\\")
        p = (root / rel_clean).resolve()
        if root.resolve() not in p.parents:
            raise ValueError(f"setup file escapes sandbox: {rel}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8")
    return root

class ForgeRunner:
    """整轮执行同一批任务。默认每题独立沙箱，跑完即清理（可保留供排查）。"""

    def __init__(
        self,
        target_root: Path | str,
        config: AdapterConfig | None = None,
        *,
        adapter: TargetAdapter | None = None,
        work_dir: Path | str | None = None,
        keep_sandboxes: bool = False,
    ) -> None:
        self.target_root = Path(target_root).resolve()
        self.adapter: TargetAdapter = (
            adapter if adapter is not None else resolve_adapter(self.target_root, config)
        )
        self.work_dir = Path(work_dir).resolve() if work_dir else None
        self.keep_sandboxes = keep_sandboxes

    def _sandbox_for(self, task: ForgeTask) -> Path:
        if self.work_dir:
            d = self.work_dir
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
            return d
        return Path(tempfile.mkdtemp(prefix="fnix-forge-"))

    def run_task(self, task: ForgeTask) -> TaskRunRecord:
        sandbox = self._sandbox_for(task)
        try:
            materialize_sandbox(task, sandbox)
        except ValueError as e:
            score = score_task(task, [], 0.0, error=str(e))
            return TaskRunRecord(
                task_id=task.id, score=score, response=TargetResponse(error=str(e)),
                sandbox_dir=str(sandbox),
            )

        before = snapshot_tree(sandbox)
        t0 = time.perf_counter()
        resp = self.adapter.invoke(task.prompt, sandbox, timeout_s=task.timeout_s)
        if time.perf_counter() - t0 > task.timeout_s + 5 and not resp.error:
            resp.error = f"exceeded timeout_s={task.timeout_s} (软超时)"
        resp.files_before = before
        resp.files_after = snapshot_tree(sandbox)

        results = run_all_checks(task, resp, sandbox)
        score = score_task(task, results, resp.elapsed_s, error=resp.error)
        record = TaskRunRecord(
            task_id=task.id, score=score, response=resp,
            sandbox_dir=str(sandbox),
        )
        if not self.keep_sandboxes and not self.work_dir:
            shutil.rmtree(sandbox, ignore_errors=True)
            record.sandbox_dir = "(cleaned)"
        return record

    def run_suite(
        self,
        tasks: list[ForgeTask],
        on_event: "callable[[dict], None] | None" = None,
    ) -> list[TaskRunRecord]:
        records: list[TaskRunRecord] = []
        for i, task in enumerate(tasks, 1):
            if on_event:
                on_event({"event": "task_start", "i": i, "n": len(tasks), "task_id": task.id})
            try:
                rec = self.run_task(task)
            except Exception as e:  # 单题崩溃不中断整轮
                _logger.exception("task %s crashed", task.id)
                score = score_task(task, [], 0.0, error=f"runner crash: {e}")
                rec = TaskRunRecord(task_id=task.id, score=score, response=TargetResponse(error=str(e)))
            records.append(rec)
            if on_event:
                on_event({
                    "event": "task_end", "i": i, "n": len(tasks),
                    "task_id": task.id, "passed": rec.score.passed,
                    "score": round(rec.score.score, 2),
                })
        return records

def tasks_dir_default() -> Path:
    """内置 benchmark 套件根目录（随 FnixAgent 分发，独占资源）。

    从本文件向上逐级寻找含 benchmarks/forge 的仓库根，兼容 editable install 与
    源码树两种布局；都找不到时回退到推导路径（后续 locate_suite 会报错）。
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "benchmarks" / "forge"
        if candidate.is_dir():
            return candidate
    return Path.cwd() / "benchmarks" / "forge"

def locate_suite(name: str) -> Path:
    base = tasks_dir_default() / "suites"
    p = base / name
    if p.is_dir():
        return p
    alt = Path(name)
    if alt.is_dir():
        return alt.resolve()
    raise FileNotFoundError(f"未找到套件 {name!r}（{base} 下无此目录）")

def list_suites() -> list[dict]:
    base = tasks_dir_default() / "suites"
    out: list[dict] = []
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        manifest = d / "manifest.json"
        info: dict = {"id": d.name, "tasks": len([p for p in d.glob("*.json") if not p.name.startswith("_") and p.name != "manifest.json"])}
        if manifest.is_file():
            try:
                info.update(json.loads(manifest.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
        out.append(info)
    return out
