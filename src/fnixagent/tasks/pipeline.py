"""批量处理管道(Phase 5.4)。

fnixagent 任务引擎的批量执行层:支持多文件并行处理、任务模板复用、
失败重试与进度回调。

数据流:
  file_paths ──> process_files ──> [per-file TaskRequest -> classify -> route]
                                       │
                                       └─> execute_steps (拓扑排序 + 上下文传递)
                                              │
                                              └─> _execute_step (派发到具体 Expert)
                                                       │
                                                       └─> ExpertResult 聚合为 TaskResult

设计要点:
  - 继承 BaseExpert,复用 name 抽象属性与 _success/_failure 工具方法
  - ThreadPoolExecutor 并行处理多文件,线程池大小 = min(max_workers, 文件数)
  - 单文件失败按 retry_count 重试,sleep(retry_delay) 后重试
  - 进度回调:completed/total * 100,回调异常不外泄
  - 步骤间上下文传递:context dict 累积每步产出,后续步骤可读取
  - 处理器实例化延迟到 _execute_step 内部,避免 __init__ 触发依赖加载
  - 线程安全:模板字典与进度计数均加锁,线程池在 finally 中 shutdown

能力边界:
  - 处理器依赖缺失时降级返回 _failure,不崩溃
  - 仅派发已注册的 handler,未知 handler 返回 _failure
  - 拓扑排序检测环依赖,有环则整体失败
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from fnixagent.office.base import BaseExpert, ExpertResult
from fnixagent.tasks.dsl import TaskRequest, TaskResult, TaskStep
from fnixagent.tasks.router import TaskRouter

_logger = logging.getLogger(__name__)


__all__ = [
    "BatchConfig",
    "BatchResult",
    "Pipeline",
]

# ---------------------------------------------------------------------------
# 批量配置
# ---------------------------------------------------------------------------


@dataclass
class BatchConfig:
    """批量处理配置。

    Attributes:
        max_workers: 最大并行数
        retry_count: 失败重试次数(0 表示不重试,仅尝试一次)
        retry_delay: 重试间隔秒
        continue_on_error: 单文件失败是否继续处理其他文件;
            False 时单文件失败即中断整批
        output_dir: 输出目录;None 表示原目录
        keep_filename: 是否保持原文件名;True 时忽略 suffix
        suffix: 输出文件后缀(keep_filename=False 时生效,
            如 "_processed" → "report_processed.docx")
        progress_callback: 进度回调(file_path, percent);
            percent 取值 0-100
    """

    max_workers: int = 4
    retry_count: int = 1
    retry_delay: float = 1.0
    continue_on_error: bool = True
    output_dir: str | None = None
    keep_filename: bool = True
    suffix: str = "_processed"
    progress_callback: Callable[[str, float], None] | None = None


# ---------------------------------------------------------------------------
# 批量结果
# ---------------------------------------------------------------------------


@dataclass
class BatchResult:
    """批量处理结果汇总。

    Attributes:
        total: 文件总数
        succeeded: 成功数
        failed: 失败数
        results: 每个文件的 TaskResult 列表
        failed_files: 失败文件列表,(file_path, error) 二元组
        total_duration_ms: 整体耗时(毫秒)
    """

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[TaskResult] = field(default_factory=list)
    failed_files: list[tuple[str, str]] = field(default_factory=list)
    total_duration_ms: float = 0.0

    def summary(self) -> dict[str, Any]:
        """汇总统计(供日志/Agent 工具结果展示)。"""
        rate = (self.succeeded / self.total) if self.total else 0.0
        return {
            "total": self.total,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "success_rate": round(rate, 4),
            "failed_files_count": len(self.failed_files),
            "total_duration_ms": round(self.total_duration_ms, 2),
        }


# ---------------------------------------------------------------------------
# 批量处理管道
# ---------------------------------------------------------------------------


class Pipeline(BaseExpert):
    """批量处理管道:多文件并行 + 任务模板 + 失败重试 + 进度回调。

    用法::

        pipe = Pipeline(BatchConfig(max_workers=4, retry_count=2))
        result = pipe.process_files(
            file_paths=["a.docx", "b.docx"],
            task_desc="填答案并统一格式",
        )
        print(result.summary())
        pipe.close()

    也可先保存任务模板,再用模板批量处理::

        steps = router.route(request)
        pipe.save_template("fill_answer", steps)
        result = pipe.process_with_template(
            file_paths=["a.docx", "b.docx"],
            template_name="fill_answer",
            params={},
        )
    """

    @property
    def name(self) -> str:
        return "pipeline"

    def __init__(self, config: BatchConfig | None = None) -> None:
        """初始化批量处理管道。

        Args:
            config: 批量配置;None 使用默认 BatchConfig()
        """
        self._config: BatchConfig = config or BatchConfig()
        self._router: TaskRouter = TaskRouter()
        # 线程池:默认按 config.max_workers 创建;process_files 内部按
        # min(max_workers, 文件数) 创建局部线程池并在 finally 中 shutdown,
        # 此处 _executor 作为默认池供单文件/简单场景复用
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=max(1, self._config.max_workers)
        )
        # 任务模板(内存态):name -> steps
        self._templates: dict[str, list[TaskStep]] = {}
        # 模板读写锁(模板可被 process_with_template 并发读取)
        self._template_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 批量处理入口
    # ------------------------------------------------------------------

    def process_files(
        self,
        file_paths: list[str],
        task_desc: str,
        config: BatchConfig | None = None,
    ) -> BatchResult:
        """批量处理多文件。

        对每个文件:创建 TaskRequest → classify → route → execute_steps。
        用 ThreadPoolExecutor 并行,单文件失败按 retry_count 重试。

        Args:
            file_paths: 输入文件路径列表
            task_desc: 自然语言任务描述(用于 classify/route)
            config: 批量配置;None 使用 self._config

        Returns:
            BatchResult: 批量结果汇总
        """
        cfg = config or self._config
        total = len(file_paths)

        # 空列表快速返回
        if total == 0:
            return BatchResult(
                total=0,
                succeeded=0,
                failed=0,
                results=[],
                failed_files=[],
                total_duration_ms=0.0,
            )

        # 线程池大小 = min(max_workers, 文件数)
        workers = max(1, min(cfg.max_workers, total))

        start_ts = time.time()
        results: list[TaskResult] = []
        failed_files: list[tuple[str, str]] = []
        completed_count = 0
        counter_lock = threading.Lock()
        aborted = threading.Event()  # continue_on_error=False 时标记中断

        # 局部线程池,确保在 finally 中 shutdown(内存安全)
        executor = ThreadPoolExecutor(max_workers=workers)
        try:
            future_to_file: dict[Any, str] = {}
            for fp in file_paths:
                # continue_on_error=False 且已中断:不再提交新任务
                if aborted.is_set():
                    break
                fut = executor.submit(self._process_one, fp, task_desc, cfg)
                future_to_file[fut] = fp

            for future in as_completed(future_to_file):
                fp = future_to_file[future]
                try:
                    result = future.result()
                except Exception as e:
                    # 线程内未捕获异常兜底:构造失败结果,不外泄
                    result = TaskResult(
                        task_id="",
                        success=False,
                        error=f"unexpected error: {e}",
                    )

                results.append(result)
                if not result.success:
                    failed_files.append((fp, result.error or "unknown error"))
                    # continue_on_error=False:标记中断,后续未启动的任务跳过
                    if not cfg.continue_on_error:
                        aborted.set()

                # 进度回调
                with counter_lock:
                    completed_count += 1
                    pct = (completed_count / total) * 100.0
                if cfg.progress_callback:
                    try:
                        cfg.progress_callback(fp, pct)
                    except Exception:
                        _logger.debug('Unhandled exception', exc_info=True)  # 回调异常不外泄
        finally:
            executor.shutdown(wait=True)

        duration_ms = (time.time() - start_ts) * 1000.0
        succeeded = sum(1 for r in results if r.success)
        return BatchResult(
            total=total,
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=results,
            failed_files=failed_files,
            total_duration_ms=duration_ms,
        )

    def process_with_template(
        self,
        file_paths: list[str],
        template_name: str,
        params: dict[str, Any],
    ) -> BatchResult:
        """用任务模板批量处理(模板预定义步骤,跳过 classify/route)。

        Args:
            file_paths: 输入文件路径列表
            template_name: 已保存的模板名
            params: 额外参数(合并进每个步骤的 params)

        Returns:
            BatchResult: 批量结果汇总
        """
        total = len(file_paths)

        if total == 0:
            return BatchResult(
                total=0,
                succeeded=0,
                failed=0,
                results=[],
                failed_files=[],
                total_duration_ms=0.0,
            )

        # 取模板(线程安全读取)
        with self._template_lock:
            template_steps = self._templates.get(template_name)
        if not template_steps:
            err = f"template not found: {template_name}"
            failed = [(fp, err) for fp in file_paths]
            fail_results = [TaskResult(task_id="", success=False, error=err) for _ in file_paths]
            return BatchResult(
                total=total,
                succeeded=0,
                failed=total,
                results=fail_results,
                failed_files=failed,
                total_duration_ms=0.0,
            )

        # 深拷贝模板步骤,合并 params(避免污染原模板)
        steps = [
            TaskStep(
                step_id=s.step_id,
                name=s.name,
                handler=s.handler,
                params={**s.params, **params},
                depends_on=list(s.depends_on),
            )
            for s in template_steps
        ]

        cfg = self._config
        workers = max(1, min(cfg.max_workers, total))

        start_ts = time.time()
        results: list[TaskResult] = []
        failed_files: list[tuple[str, str]] = []
        completed_count = 0
        counter_lock = threading.Lock()

        executor = ThreadPoolExecutor(max_workers=workers)
        try:
            future_to_file: dict[Any, str] = {}
            for fp in file_paths:
                fut = executor.submit(self._process_one_with_steps, fp, steps, cfg)
                future_to_file[fut] = fp

            for future in as_completed(future_to_file):
                fp = future_to_file[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = TaskResult(
                        task_id="",
                        success=False,
                        error=f"unexpected error: {e}",
                    )
                results.append(result)
                if not result.success:
                    failed_files.append((fp, result.error or "unknown error"))

                with counter_lock:
                    completed_count += 1
                    pct = (completed_count / total) * 100.0
                if cfg.progress_callback:
                    try:
                        cfg.progress_callback(fp, pct)
                    except Exception:
                        _logger.debug('Unhandled exception', exc_info=True)
        finally:
            executor.shutdown(wait=True)

        duration_ms = (time.time() - start_ts) * 1000.0
        succeeded = sum(1 for r in results if r.success)
        return BatchResult(
            total=total,
            succeeded=succeeded,
            failed=len(results) - succeeded,
            results=results,
            failed_files=failed_files,
            total_duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # 单文件处理(含重试)
    # ------------------------------------------------------------------

    def _process_one(
        self,
        file_path: str,
        task_desc: str,
        cfg: BatchConfig,
    ) -> TaskResult:
        """处理单个文件:创建请求 → classify → route → execute_steps。

        失败时按 cfg.retry_count 重试,sleep(retry_delay) 后重试。
        """
        last_error: str | None = None
        attempts = cfg.retry_count + 1  # 首次 + 重试次数

        for attempt in range(attempts):
            try:
                request = TaskRequest(
                    description=task_desc,
                    file_paths=[file_path],
                )
                request = self._router.classify(request)
                steps = self._router.route(request)
                output_path = self._compute_output_path(file_path, cfg)
                result = self.execute_steps(file_path, steps, output_path)
                if result.success:
                    return result
                last_error = result.error
            except Exception as e:
                last_error = f"processing failed: {e}"

            # 非最后一次重试前 sleep
            if attempt < attempts - 1:
                time.sleep(cfg.retry_delay)

        return TaskResult(
            task_id="",
            success=False,
            error=last_error or "unknown error",
        )

    def _process_one_with_steps(
        self,
        file_path: str,
        steps: list[TaskStep],
        cfg: BatchConfig,
    ) -> TaskResult:
        """用预定义步骤处理单个文件(模板模式,含重试)。"""
        last_error: str | None = None
        attempts = cfg.retry_count + 1

        for attempt in range(attempts):
            try:
                output_path = self._compute_output_path(file_path, cfg)
                result = self.execute_steps(file_path, steps, output_path)
                if result.success:
                    return result
                last_error = result.error
            except Exception as e:
                last_error = f"processing failed: {e}"

            if attempt < attempts - 1:
                time.sleep(cfg.retry_delay)

        return TaskResult(
            task_id="",
            success=False,
            error=last_error or "unknown error",
        )

    def _compute_output_path(self, file_path: str, cfg: BatchConfig) -> str | None:
        """根据配置计算单个文件的输出路径。

        - output_dir 为 None:返回 None(原地或由处理器决定)
        - keep_filename=True:保持原文件名,输出到 output_dir
        - keep_filename=False:加 suffix 后缀
        """
        if cfg.output_dir is None:
            return None

        base = os.path.basename(file_path)
        name, ext = os.path.splitext(base)
        if cfg.keep_filename:
            out_name = base
        else:
            out_name = f"{name}{cfg.suffix}{ext}"
        return os.path.join(cfg.output_dir, out_name)

    # ------------------------------------------------------------------
    # 步骤链执行
    # ------------------------------------------------------------------

    def execute_steps(
        self,
        file_path: str,
        steps: list[TaskStep],
        output_path: str,
    ) -> TaskResult:
        """执行单个文件的任务步骤链。

        - 按 depends_on 拓扑排序
        - 逐步执行,每步产出累积进 context dict,供后续步骤读取
        - continue_on_error=False 时任一步骤失败即中断

        Args:
            file_path: 输入文件路径
            steps: 任务步骤列表
            output_path: 输出路径

        Returns:
            TaskResult: 聚合结果
        """
        start_ts = time.time()

        if not steps:
            return TaskResult(
                task_id="",
                success=False,
                error="no steps to execute",
                duration_ms=0.0,
            )

        # 拓扑排序
        ordered = self._topo_sort(steps)
        if ordered is None:
            return TaskResult(
                task_id="",
                success=False,
                error="circular dependency detected in steps",
                duration_ms=(time.time() - start_ts) * 1000.0,
            )

        # 上下文:初始包含文件路径与输出路径,逐步累积每步产出
        context: dict[str, Any] = {
            "file_path": file_path,
            "output_path": output_path,
        }
        output_files: list[str] = []
        pending_items: list[dict[str, Any]] = []
        step_stats: dict[str, Any] = {}
        cfg = self._config

        for step in ordered:
            step_start = time.time()
            result = self._execute_step(step, context)
            step_ms = (time.time() - step_start) * 1000.0
            step_stats[step.step_id] = {
                "name": step.name,
                "handler": step.handler,
                "success": result.success,
                "duration_ms": round(step_ms, 2),
            }

            # 累积上下文(以 step_id 与 key 双索引)
            context[step.step_id] = result
            step_key = step.params.get("key")
            if step_key:
                context[step_key] = result

            if result.success:
                # 收集产物文件
                if isinstance(result.output, str) and os.path.exists(result.output):
                    output_files.append(result.output)
                elif isinstance(result.output, dict):
                    out = result.output.get("output") or result.output.get("save_path")
                    if isinstance(out, str) and os.path.exists(out):
                        output_files.append(out)
                # 收集待确认项(metadata 中的 pending)
                pending = result.metadata.get("pending_items")
                if isinstance(pending, list):
                    pending_items.extend(pending)
            else:
                # 步骤失败:continue_on_error=False 则中断
                if not cfg.continue_on_error:
                    return TaskResult(
                        task_id="",
                        success=False,
                        output_files=output_files,
                        pending_items=pending_items,
                        stats=step_stats,
                        error=f"step '{step.name}' failed: {result.error}",
                        duration_ms=(time.time() - start_ts) * 1000.0,
                    )

        # 整体成功:所有步骤成功(或失败但 continue_on_error=True 且无致命错误)
        has_failure = any(not s["success"] for s in step_stats.values())
        success = not has_failure
        error_msg: str | None = None
        if has_failure:
            failed_steps = [f"{s['name']}" for s in step_stats.values() if not s["success"]]
            error_msg = (
                f"completed with failures: {', '.join(failed_steps)}"
                if cfg.continue_on_error
                else None
            )

        return TaskResult(
            task_id="",
            success=success,
            output_files=output_files,
            pending_items=pending_items,
            stats=step_stats,
            error=error_msg,
            duration_ms=(time.time() - start_ts) * 1000.0,
        )

    # ------------------------------------------------------------------
    # 拓扑排序
    # ------------------------------------------------------------------

    @staticmethod
    def _topo_sort(steps: list[TaskStep]) -> list[TaskStep] | None:
        """按 depends_on 拓扑排序。

        Returns:
            排序后的步骤列表;检测到环依赖返回 None
        """
        step_map = {s.step_id: s for s in steps}
        # 入度表
        in_degree: dict[str, int] = {s.step_id: 0 for s in steps}
        # 邻接表:step_id -> 依赖它的 step_id 列表
        adj: dict[str, list[str]] = {s.step_id: [] for s in steps}

        for s in steps:
            for dep in s.depends_on:
                if dep in step_map:
                    adj[dep].append(s.step_id)
                    in_degree[s.step_id] += 1

        # Kahn 算法
        queue = [sid for sid, d in in_degree.items() if d == 0]
        ordered: list[TaskStep] = []
        while queue:
            sid = queue.pop(0)
            ordered.append(step_map[sid])
            for nxt in adj[sid]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if len(ordered) != len(steps):
            return None  # 存在环依赖
        return ordered

    # ------------------------------------------------------------------
    # 单步骤执行(handler 派发)
    # ------------------------------------------------------------------

    def _execute_step(self, step: TaskStep, context: dict[str, Any]) -> ExpertResult:
        """执行单个步骤,根据 step.handler 派发到对应处理器。

        处理器实例化延迟到此处,避免 __init__ 时触发依赖加载。
        依赖缺失或未知 handler 时降级返回 _failure,不崩溃。

        Args:
            step: 任务步骤
            context: 上下文 dict(含 file_path/output_path 及前序步骤产出)

        Returns:
            ExpertResult: 统一返回结构
        """
        handler = step.handler
        params = step.params

        # 当前处理的文件路径(优先取 context,回退到 params.file_paths[0])
        file_path = context.get("file_path") or ""
        if not file_path:
            fps = params.get("file_paths") or []
            if fps:
                file_path = fps[0]

        output_path = context.get("output_path") or params.get("output_path")

        try:
            # ----------------------------------------------------------
            # parser: 文档解析(Element 列表)
            # ----------------------------------------------------------
            if handler == "parser":
                from fnixagent.office.parser import ParserExpert

                expert = ParserExpert()
                return expert.parse_elements(path=file_path)

            # ----------------------------------------------------------
            # format_normalizer: 格式统一
            # ----------------------------------------------------------
            if handler == "format_normalizer":
                from fnixagent.office.format_spec import FormatNormalizer

                expert = FormatNormalizer()
                return expert.normalize(path=file_path, output_path=output_path)

            # ----------------------------------------------------------
            # run_editor: Run 级编辑
            # ----------------------------------------------------------
            if handler == "run_editor":
                from fnixagent.office.run_editor import EditOp, RunEditor

                expert = RunEditor()
                ops = params.get("ops") or params.get("params", {}).get("ops", [])
                # dict 形式转换为 EditOp
                if ops and isinstance(ops[0], dict):
                    ops = [EditOp(**o) for o in ops]
                if not ops:
                    return self._failure(f"step '{step.name}': ops must be a non-empty list")
                return expert.edit(path=file_path, ops=ops, output_path=output_path)

            # ----------------------------------------------------------
            # validator: 题库验证(返回 ValidationReport,包装为 ExpertResult)
            # ----------------------------------------------------------
            if handler == "validator":
                from fnixagent.tasks.validator import TaskValidator

                expert = TaskValidator()
                processed = output_path or file_path
                report = expert.validate_question_bank(
                    original_path=file_path, processed_path=processed
                )
                return ExpertResult(
                    success=report.passed,
                    output=report,
                    error=None if report.passed else "; ".join(report.errors),
                    metadata={
                        "total_checks": report.total_checks,
                        "passed_checks": report.passed_checks,
                        "failed_checks": report.failed_checks,
                        "warnings": list(report.warnings),
                        "errors": list(report.errors),
                        "details": list(report.details),
                    },
                )

            # ----------------------------------------------------------
            # garbage_detector: 乱码检测(返回 GarbageReport,包装为 ExpertResult)
            # ----------------------------------------------------------
            if handler == "garbage_detector":
                from fnixagent.tasks.resolver import GarbageDetector

                expert = GarbageDetector()
                text = params.get("answer_text") or context.get("answer_text") or ""
                report = expert.detect(answer_text=text)
                return ExpertResult(
                    success=True,
                    output=report,
                    metadata={
                        "is_garbled": report.is_garbled,
                        "garble_type": report.garble_type,
                        "recoverable": report.recoverable,
                        "parsed_options": list(report.parsed_options),
                    },
                )

            # ----------------------------------------------------------
            # answer_resolver: 答案恢复(返回 ResolveResult,包装为 ExpertResult)
            # ----------------------------------------------------------
            if handler == "answer_resolver":
                from fnixagent.tasks.resolver import AnswerResolver

                expert = AnswerResolver()
                result = expert.resolve(
                    question_num=params.get("question_num", ""),
                    stem=params.get("stem", ""),
                    options=params.get("options", []),
                    garbled_answer=params.get("garbled_answer", ""),
                )
                return ExpertResult(
                    success=result.answer is not None,
                    output=result,
                    error=(
                        None
                        if result.answer is not None
                        else f"answer not resolved (source={result.source})"
                    ),
                    metadata={
                        "question_num": result.question_num,
                        "answer": result.answer,
                        "confidence": result.confidence,
                        "source": result.source,
                        "needs_manual": result.needs_manual,
                        "pending_items": (
                            [{"question": result.question_num}] if result.needs_manual else []
                        ),
                    },
                )

            # ----------------------------------------------------------
            # 未知 handler
            # ----------------------------------------------------------
            return self._failure(f"unknown handler: {handler}")

        except Exception as e:
            # 依赖缺失/处理器异常:降级返回 _failure,不外泄
            return self._failure(f"step '{step.name}' failed: {e}")

    # ------------------------------------------------------------------
    # 任务模板管理(内存态)
    # ------------------------------------------------------------------

    def save_template(self, name: str, steps: list[TaskStep]) -> ExpertResult:
        """保存任务模板(内存态)。

        Args:
            name: 模板名(唯一标识)
            steps: 步骤列表

        Returns:
            ExpertResult: output 为模板名;已存在则覆盖
        """
        if not name or not isinstance(name, str):
            return self._failure("template name must be a non-empty string")
        if not isinstance(steps, list) or not steps:
            return self._failure("steps must be a non-empty list")

        with self._template_lock:
            self._templates[name] = [
                TaskStep(
                    step_id=s.step_id,
                    name=s.name,
                    handler=s.handler,
                    params=dict(s.params),
                    depends_on=list(s.depends_on),
                )
                for s in steps
            ]
        return self._success(
            output=name,
            step_count=len(steps),
            template_names=list(self._templates.keys()),
        )

    def list_templates(self) -> list[str]:
        """列出所有已保存的模板名。"""
        with self._template_lock:
            return list(self._templates.keys())

    # ------------------------------------------------------------------
    # 资源清理
    # ------------------------------------------------------------------

    def close(self) -> None:
        """关闭线程池,释放资源。

        应在 Pipeline 不再使用时调用(通常放在 finally 块中)。
        """
        try:
            self._executor.shutdown(wait=True)
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)
