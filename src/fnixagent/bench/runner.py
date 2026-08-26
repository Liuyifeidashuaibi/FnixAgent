"""BenchForge — 全量评测运行器。

执行模型（严格遵守任务规格书）：
  - 逐条遍历全部任务，原始 prompt 原样传入（不改写）
  - 每条任务使用**全新 AgenticLoop 实例 + 全新隔离工作区**，
    不继承上一条任务的输出上下文
  - 单任务异常 / 超时 / 崩溃：记录后继续下一条，绝不中断
  - 完整轨迹（规划、工具调用、中间输出、最终产物）写入本地 jsonl
  - 支持 checkpoint 断点续跑（崩溃后恢复，不重跑已完成任务）
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
import traceback
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from fnixagent.bench.judge import Judge
from fnixagent.bench.schema import BenchTask, RunSummary, TaskRun, TaskStatus

_logger = logging.getLogger(__name__)


class BenchRunner:
    """全量基准评测运行器。

    用法:
        runner = BenchRunner(output_dir="benchmarks/benchforge/runs/20260821")
        summary = runner.run_all(tasks, judge=Judge(llm_call=...))
    """

    def __init__(
        self,
        output_dir: Path | str,
        model: str = "",
        max_steps: int = 25,
        task_timeout: int = 600,
        max_concurrency: int = 4,
        agent_builder: Callable[[Path], Any] | None = None,
        keep_workspaces: bool = False,
        run_id: str = "",
        quota_abort_threshold: int = 15,
    ) -> None:
        """
        Args:
            output_dir:      本此运行产物目录（轨迹/回归集/报告都写这里）
            model:           被测模型名（记录到报告）
            max_steps:       单任务 Agent 最大步数
            task_timeout:    单任务超时（秒）
            max_concurrency: 并发任务数（受 API 限流约束）
            agent_builder:   自定义 Agent 构建函数 (workspace) -> AgenticLoop；
                             为 None 时用默认 GLM 配置构建
            keep_workspaces: 任务结束后保留隔离工作区（调试用）
            run_id:          运行 ID（默认时间戳）
            quota_abort_threshold: 连续出现多少次"配额/鉴权"基础设施错误后提前熔断，
                             避免配额耗尽时 1406 条任务全部空转刷 403
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "trajectories").mkdir(exist_ok=True)
        (self.output_dir / "workspaces").mkdir(exist_ok=True)
        self.model = model
        self.max_steps = max_steps
        self.task_timeout = task_timeout
        self.max_concurrency = max(1, max_concurrency)
        self.agent_builder = agent_builder
        self.keep_workspaces = keep_workspaces
        self.quota_abort_threshold = max(1, quota_abort_threshold)
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        self._summary = RunSummary(run_id=self.run_id, model=model, started_at=time.time())
        self._completed: set[str] = set()   # "dataset/task_id" 已完成集合
        self._infra_streak = 0              # 连续基础设施错误计数（配额熔断器）
        self._quota_aborted = False         # 熔断标志：剩余任务保持 pending 待重跑
        self._results_file = self.output_dir / "results.jsonl"
        self._load_checkpoint()

    # ------------------------------------------------------------------
    # checkpoint 断点续跑
    # ------------------------------------------------------------------

    def _load_checkpoint(self) -> None:
        if not self._results_file.exists():
            return
        for line in self._results_file.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                status = rec.get("status", "")
                # 配额/鉴权等基础设施错误不锁为"已完成"：
                # 保持 pending，配额恢复后续跑会自动重试这些任务
                if status == TaskStatus.INFRA_SKIP.value:
                    continue
                key = f"{rec['dataset']}/{rec['task_id']}"
                if key in self._completed:
                    continue
                self._completed.add(key)
                self._summary.add_run(TaskRun.from_dict(rec))
            except Exception:
                _logger.debug("checkpoint 行解析失败，忽略", exc_info=True)

    def _append_result(self, run: TaskRun) -> None:
        with self._results_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(run.to_dict(), ensure_ascii=False) + "\n")
        traj_dir = self.output_dir / "trajectories" / run.dataset
        traj_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(c if c.isalnum() or c in "._-" else "_" for c in run.task_id)
        (traj_dir / f"{safe_id}.json").write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2), "utf-8",
        )

    # ------------------------------------------------------------------
    # 单任务执行
    # ------------------------------------------------------------------

    # B6: web-bench 等项目按"项目级"共享工作区（文件级继承）。
    # 官方语义：每项目 20 个任务有顺序依赖（init 创建文件 → 后续任务在其上修改）。
    # 这里每个项目复用同一工作区目录，但每个任务仍是全新 Agent 实例
    # （对话上下文不继承，仅文件系统产物继承），符合用户"任务独立运行"的约束。
    _PROJECT_SHARED_DATASETS = {"web-bench"}

    def _make_workspace(self, task: BenchTask) -> Path:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in task.task_id)
        if task.dataset in self._PROJECT_SHARED_DATASETS and task.subset:
            # 项目级共享：同一 subset（项目）的所有任务使用同一目录，
            # init 任务产物被后续任务继承
            proj = "".join(c if c.isalnum() or c in "._-" else "_" for c in task.subset)
            ws = self.output_dir / "workspaces" / f"{task.dataset}__{proj}__shared"
        else:
            ws = self.output_dir / "workspaces" / f"{task.dataset}__{safe}__{uuid.uuid4().hex[:6]}"
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    async def _run_one(self, task: BenchTask, judge: Judge) -> TaskRun:
        """执行单条任务：全新 Agent 实例、全新工作区、原样 prompt。"""
        run = TaskRun(dataset=task.dataset, task_id=task.task_id, prompt=task.prompt)
        ws = self._make_workspace(task)
        run.workspace = str(ws)
        started = time.monotonic()
        try:
            builder = self.agent_builder or self._default_agent_builder
            agent = builder(ws)
            agent.reset()  # 显式确保无遗留上下文
            result = await asyncio.wait_for(
                agent.run(task.prompt), timeout=self.task_timeout,
            )
            run.final_response = getattr(result, "response", "") or ""
            run.total_tokens = int(getattr(result, "total_tokens", 0) or 0)
            run.steps = [s.to_summary() for s in getattr(agent, "traces", [])]
            run.tool_calls = [
                {
                    "step": i + 1,
                    "tool": t.tool_name,
                    "args": getattr(t, "tool_args", {}),
                    "success": t.tool_success,
                    "output_preview": (t.tool_output or "")[:500],
                }
                for i, t in enumerate(getattr(agent, "traces", []))
                if getattr(t, "tool_name", None)
            ]
            run.files_written = sorted(
                str(p.relative_to(ws)) for p in ws.rglob("*") if p.is_file()
            )[:200]
            if not getattr(result, "success", False):
                run.error = getattr(result, "error", "") or "agent returned failure"
        except TimeoutError:
            run.status = TaskStatus.FAILURE
            run.error = f"任务超时（>{self.task_timeout}s）"
        except Exception as exc:
            run.status = TaskStatus.FAILURE
            run.error = f"{exc}\n{traceback.format_exc(limit=5)}"
        run.duration_ms = (time.monotonic() - started) * 1000

        # 判定（成功/失败 + 失败分类）
        if run.status != TaskStatus.FAILURE or not run.error or not run.failure_type:
            try:
                verdict = await judge.judge(task, run)
                run.status = verdict.status
                run.failure_type = verdict.failure_type
                run.failure_evidence = verdict.evidence
                run.judge_method = verdict.method
            except Exception as exc:
                _logger.error("判定异常，按启发式兜底: %s", exc)
                if run.status != TaskStatus.FAILURE:
                    run.status = TaskStatus.FAILURE
                    run.failure_type = "other"
                    run.failure_evidence = f"判定器异常: {exc}"

        if not self.keep_workspaces:
            shutil.rmtree(ws, ignore_errors=True)
        return run

    def _default_agent_builder(self, workspace: Path) -> Any:
        """默认：按 fnixagent 主入口同款方式构建 AgenticLoop。"""
        import os

        from fnixagent.core.agent.loop import AgenticLoop
        from fnixagent.core.llm.adapter import LLMAdapter
        from fnixagent.core.tools.registry import ToolRegistry
        from fnixagent.core.tools.workspace import register_workspace_tools

        registry = ToolRegistry()
        register_workspace_tools(registry, str(workspace))
        adapter = LLMAdapter(
            api_key=os.getenv("BENCH_API_KEY", ""),
            base_url=os.getenv("BENCH_BASE_URL", ""),
            model_name=os.getenv("BENCH_MODEL", ""),
            # 评测隔离: 禁用 fallback 链（.env 的 LLM_MODEL_FALLBACKS 指向的
            # 备用模型可能已下线/无权限，会让评测任务以 infra_skip 告终）
            fallback_models=[m.strip() for m in os.getenv("BENCH_MODEL_FALLBACKS", "").split(",") if m.strip()],
        )
        if not adapter.is_configured:
            raise RuntimeError(
                "LLM 未配置：请设置 BENCH_API_KEY / BENCH_BASE_URL / BENCH_MODEL "
                "或 ~/.fnix 配置"
            )
        return AgenticLoop(
            llm_call=adapter.chat,
            tool_executor=registry,
            workspace_root=str(workspace),
            max_steps=self.max_steps,
        )

    # ------------------------------------------------------------------
    # 全量执行
    # ------------------------------------------------------------------

    def run_all(
        self,
        tasks: list[BenchTask],
        judge: Judge,
        progress: Callable[[int, int, TaskRun], None] | None = None,
    ) -> RunSummary:
        """全量执行（不抽样、不过滤）；支持断点续跑。"""
        pending = [
            t for t in tasks if f"{t.dataset}/{t.task_id}" not in self._completed
        ]
        # B6: web-bench 项目级共享工作区 → 同项目任务按 id 排序执行，
        # 保证 --init 先建基础文件，后续 task-N 在其上修改（顺序依赖语义）。
        pending.sort(
            key=lambda t: (
                t.dataset,
                t.subset if t.dataset in self._PROJECT_SHARED_DATASETS else "",
                # 数字后缀任务按数值排序（task-2 < task-10），init 排最前
                0 if t.task_id.endswith("--init") else int(
                    "".join(ch for ch in t.task_id.rsplit("--", 1)[-1] if ch.isdigit()) or 0
                ),
            )
        )
        _logger.info(
            "评测启动 run=%s 任务总数=%d 已完成=%d 待执行=%d",
            self.run_id, len(tasks), len(tasks) - len(pending), len(pending),
        )
        asyncio.run(self._run_pending(pending, judge, progress))
        self._summary.finished_at = time.time()
        (self.output_dir / "summary.json").write_text(
            json.dumps(self._summary.to_dict(), ensure_ascii=False, indent=2), "utf-8",
        )
        return self._summary

    async def _run_pending(
        self,
        pending: list[BenchTask],
        judge: Judge,
        progress: Callable[[int, int, TaskRun], None] | None,
    ) -> None:
        sem = asyncio.Semaphore(self.max_concurrency)
        done_count = 0
        total = len(pending)
        lock = asyncio.Lock()
        # B6: 项目级共享工作区 → 同项目任务必须串行（避免并发写同一目录竞态）。
        # 不同项目之间仍可并发。
        project_locks: dict[tuple[str, str], asyncio.Lock] = {}

        def _proj_lock(task: BenchTask) -> asyncio.Lock | None:
            if task.dataset not in self._PROJECT_SHARED_DATASETS or not task.subset:
                return None
            key = (task.dataset, task.subset)
            if key not in project_locks:
                project_locks[key] = asyncio.Lock()
            return project_locks[key]

        async def worker(task: BenchTask) -> None:
            nonlocal done_count
            async with sem:
                # 配额熔断：连续基础设施错误超阈值时，剩余任务保持 pending 待重跑
                if self._quota_aborted:
                    return
                plock = _proj_lock(task)
                try:
                    if plock is not None:
                        async with plock:  # 同项目串行（文件级继承）
                            run = await self._run_one(task, judge)
                    else:
                        run = await self._run_one(task, judge)
                except Exception as exc:  # 双保险：任何异常都不允许中断整体流程
                    run = TaskRun(
                        dataset=task.dataset, task_id=task.task_id, prompt=task.prompt,
                        status=TaskStatus.FAILURE, failure_type="crash",
                        failure_evidence=f"runner 层异常: {exc}",
                        error=traceback.format_exc(limit=5),
                    )
                async with lock:
                    self._summary.add_run(run)
                    self._append_result(run)
                    if run.status == TaskStatus.INFRA_SKIP:
                        # 配额/鉴权错误不锁 completed，保持可重跑；累计连续错误触发熔断
                        self._infra_streak += 1
                        if self._infra_streak >= self.quota_abort_threshold:
                            self._quota_aborted = True
                            _logger.warning(
                                "连续 %d 条基础设施错误（疑似配额耗尽），本次运行提前熔断；"
                                "剩余任务保持 pending，配额恢复后重跑即可续上",
                                self._infra_streak,
                            )
                    else:
                        self._infra_streak = 0
                        self._completed.add(f"{run.dataset}/{run.task_id}")
                    done_count += 1
                    if progress:
                        progress(done_count, total, run)

        await asyncio.gather(*(worker(t) for t in pending), return_exceptions=False)
        if self._quota_aborted:
            self._summary.note = (
                f"配额熔断：连续 {self._infra_streak} 条基础设施错误后提前停止，"
                "剩余任务未执行，待模型配额恢复后重跑续上。"
            )
