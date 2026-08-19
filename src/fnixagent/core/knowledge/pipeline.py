"""Knowledge Pipeline(P2-5)。

文档处理管道:把原始文档(Word/Excel/PDF/图片/Markdown)处理为可检索的知识块。
6 步流水线:OCR → Parse → Chunk → Extract → Permission → Embed。

设计:
  - PipelineContext:流水线上下文,在步骤间传递
  - PipelineStep:步骤抽象基类,子类实现具体逻辑
  - KnowledgePipeline:流水线编排,支持 add/remove/replace 步骤
  - 每步可声明 should_run(),按文档类型跳过(如 OCR 仅图片/扫描件)
  - 每步可声明 required=False,失败不阻断整条流水线

安全:
  - file_path 路径穿越防护(禁止 .. 与绝对路径越界)
  - 上传文件大小限制(可通过 options.max_file_bytes 配置)
  - 并行执行通过 _lock 保护步骤列表的读写
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import abc
import asyncio
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# 默认上传文件大小上限(50MB),防止大文件耗尽内存
DEFAULT_MAX_FILE_BYTES: int = 50 * 1024 * 1024


def _validate_file_path(file_path: str, base_dir: str | None = None) -> str:
    """校验文件路径安全性:非空 + 禁止路径穿越 + 可选基目录限制。

    Args:
        file_path: 待校验的文件路径
        base_dir: 可选的基目录,若提供则要求 file_path 必须位于其下

    Returns:
        规范化后的绝对路径

    Raises:
        ValueError: 路径为空、含路径穿越、或越出基目录
    """
    if not file_path or not file_path.strip():
        raise ValueError("file_path 不能为空")
    # 规范化路径,解析 .. / 符号链接等
    norm = os.path.normpath(file_path)
    # 禁止 .. 路径穿越(规范化后仍含 .. 说明试图越界)
    if ".." in norm.split(os.sep):
        raise ValueError(f"路径穿越被拒绝: {file_path}")
    abs_path = os.path.abspath(norm)
    if base_dir is not None:
        base_abs = os.path.abspath(base_dir)
        if not abs_path.startswith(base_abs + os.sep) and abs_path != base_abs:
            raise ValueError(f"路径越出基目录 {base_dir}: {file_path}")
    return abs_path


# ---------------------------------------------------------------------------
# PipelineContext
# ---------------------------------------------------------------------------


@dataclass
class PipelineContext:
    """流水线上下文(在步骤间传递的累积状态)。"""

    # 输入
    document_id: str = ""
    tenant_id: str = ""
    file_path: str = ""
    mime_type: str = ""
    file_ext: str = ""  # 扩展名(小写无点)

    # 各步输出(累积)
    ocr_text: str = ""
    parsed_blocks: list[dict] = field(default_factory=list)  # [{type, text, metadata}]
    chunks: list[dict] = field(default_factory=list)  # [{text, index, tokens, metadata}]
    extracted_metadata: dict[str, Any] = field(default_factory=dict)
    permission_tags: dict[str, Any] = field(default_factory=dict)
    embeddings: list[list[float]] = field(default_factory=list)

    # 执行追踪
    errors: list[dict] = field(default_factory=list)  # [{step, error, fatal}]
    step_results: dict[str, dict] = field(
        default_factory=dict
    )  # {step_name: {duration_ms, skipped, ...}}

    # 透传配置(步骤可读取)
    options: dict[str, Any] = field(default_factory=dict)

    def validate_file_path(self, base_dir: str | None = None) -> str:
        """校验 self.file_path 的安全性(非空 + 禁路径穿越)。

        Args:
            base_dir: 可选的基目录限制

        Returns:
            规范化后的绝对路径

        Raises:
            ValueError: 路径不合法
        """
        return _validate_file_path(self.file_path, base_dir=base_dir)

    def check_file_size(self, max_bytes: int | None = None) -> int:
        """检查 file_path 指向文件的大小是否超限。

        Args:
            max_bytes: 最大允许字节数,None 时取 options.max_file_bytes 或默认值

        Returns:
            文件实际大小(字节)

        Raises:
            ValueError: 文件超过大小限制
            FileNotFoundError: 文件不存在
        """
        if max_bytes is None:
            max_bytes = int(self.options.get("max_file_bytes", DEFAULT_MAX_FILE_BYTES))
        if not self.file_path or not os.path.exists(self.file_path):
            raise FileNotFoundError(f"文件不存在: {self.file_path}")
        size = os.path.getsize(self.file_path)
        if size > max_bytes:
            raise ValueError(f"文件大小 {size} 字节超过上限 {max_bytes} 字节: {self.file_path}")
        return size


# ---------------------------------------------------------------------------
# PipelineStep
# ---------------------------------------------------------------------------


class PipelineStep(abc.ABC):
    """流水线步骤抽象基类。"""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """步骤名(唯一标识)。"""
        ...

    @property
    def required(self) -> bool:
        """是否必需步骤(失败是否阻断整条流水线)。"""
        return True

    @abc.abstractmethod
    def execute(self, ctx: PipelineContext) -> PipelineContext:
        """执行步骤,返回更新后的 ctx。"""
        ...

    def should_run(self, ctx: PipelineContext) -> bool:
        """是否应执行此步骤(默认 True,子类可按文档类型跳过)。"""
        return True


# ---------------------------------------------------------------------------
# KnowledgePipeline
# ---------------------------------------------------------------------------


class KnowledgePipeline:
    """知识处理流水线。

    默认 6 步:OCR → Parse → Chunk → Extract → Permission → Embed。
    支持 add/remove/replace 步骤,支持同步/异步执行。
    """

    def __init__(self, steps: list[PipelineStep] | None = None) -> None:
        if steps is None:
            # 延迟导入,避免循环依赖
            from fnixagent.core.knowledge.steps import (
                ChunkStep,
                EmbedStep,
                ExtractStep,
                OCRStep,
                ParseStep,
                PermissionStep,
            )

            steps = [
                OCRStep(),
                ParseStep(),
                ChunkStep(),
                ExtractStep(required=False),
                PermissionStep(),
                EmbedStep(),
            ]
        self._steps: list[PipelineStep] = list(steps)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 步骤管理
    # ------------------------------------------------------------------

    def add_step(self, step: PipelineStep, after: str | None = None) -> None:
        """添加步骤。after=None 追加到末尾;after=step_name 插入到指定步骤后。"""
        with self._lock:
            if after is None:
                self._steps.append(step)
            else:
                idx = self._find_step_index(after)
                if idx is None:
                    raise ValueError(f"step '{after}' not found")
                self._steps.insert(idx + 1, step)

    def remove_step(self, name: str) -> PipelineStep | None:
        """移除步骤。"""
        with self._lock:
            for i, s in enumerate(self._steps):
                if s.name == name:
                    return self._steps.pop(i)
            return None

    def replace_step(self, name: str, new_step: PipelineStep) -> PipelineStep | None:
        """替换步骤。"""
        with self._lock:
            idx = self._find_step_index(name)
            if idx is None:
                return None
            old = self._steps[idx]
            self._steps[idx] = new_step
            return old

    def list_steps(self) -> list[str]:
        """列出所有步骤名。"""
        with self._lock:
            return [s.name for s in self._steps]

    def get_progress(self, ctx: PipelineContext) -> dict:
        """获取当前执行进度。"""
        total = len(self._steps)
        completed = len(ctx.step_results)
        return {
            "total_steps": total,
            "completed_steps": completed,
            "percentage": (completed / total * 100) if total else 0.0,
            "steps": [
                {
                    "name": s.name,
                    "required": s.required,
                    "executed": s.name in ctx.step_results,
                    "skipped": ctx.step_results.get(s.name, {}).get("skipped", False),
                }
                for s in self._steps
            ],
        }

    def _find_step_index(self, name: str) -> int | None:
        for i, s in enumerate(self._steps):
            if s.name == name:
                return i
        return None

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """同步执行流水线。

        编排逻辑:
          1. 入口校验:若 ctx.file_path 非空,做路径穿越与文件大小校验,
             校验失败记录为 fatal 错误并直接返回(不进入步骤循环)
          2. 在 _lock 下快照当前步骤列表,避免并行 add/remove 导致迭代异常
          3. 顺序执行每个步骤:
             - should_run=False → 记录 skipped,继续下一步
             - execute 抛异常 → 记录到 ctx.errors,required=True 则中断
          4. 异常不向上抛出,确保单步失败不污染整体流程
        """
        # 入口安全校验:路径穿越 + 文件大小
        if ctx.file_path:
            try:
                ctx.validate_file_path()
                ctx.check_file_size()
            except (ValueError, FileNotFoundError) as e:
                ctx.errors.append(
                    {
                        "step": "_validate",
                        "error": str(e),
                        "fatal": True,
                    }
                )
                ctx.step_results["_validate"] = {
                    "skipped": False,
                    "duration_ms": 0.0,
                    "error": str(e),
                }
                return ctx

        # 在锁内快照步骤列表,保证并行 add/remove 不影响本次执行
        with self._lock:
            steps_snapshot = list(self._steps)

        for step in steps_snapshot:
            step_name = step.name
            # 跳过判断(如 OCR 仅对图片触发)
            if not step.should_run(ctx):
                ctx.step_results[step_name] = {"skipped": True, "duration_ms": 0.0}
                continue
            # 执行单步,异常隔离
            start = time.perf_counter()
            try:
                ctx = step.execute(ctx)
                duration_ms = (time.perf_counter() - start) * 1000
                ctx.step_results[step_name] = {
                    "skipped": False,
                    "duration_ms": duration_ms,
                }
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                ctx.step_results[step_name] = {
                    "skipped": False,
                    "duration_ms": duration_ms,
                    "error": str(e),
                }
                # 记录错误:required=True 标记为 fatal
                ctx.errors.append(
                    {
                        "step": step_name,
                        "error": str(e),
                        "fatal": step.required,
                    }
                )
                if step.required:
                    # 必需步骤失败:阻断整条流水线
                    break
        return ctx

    async def run_async(self, ctx: PipelineContext) -> PipelineContext:
        """异步执行流水线。

        各步骤按顺序执行(步骤间有数据依赖);步骤内部可并发。
        编排逻辑与 run() 一致,但支持 execute 返回协程时自动 await。
        """
        # 入口安全校验
        if ctx.file_path:
            try:
                ctx.validate_file_path()
                ctx.check_file_size()
            except (ValueError, FileNotFoundError) as e:
                ctx.errors.append(
                    {
                        "step": "_validate",
                        "error": str(e),
                        "fatal": True,
                    }
                )
                ctx.step_results["_validate"] = {
                    "skipped": False,
                    "duration_ms": 0.0,
                    "error": str(e),
                }
                return ctx

        # 快照步骤列表,避免并行修改造成迭代异常
        with self._lock:
            steps_snapshot = list(self._steps)

        for step in steps_snapshot:
            step_name = step.name
            if not step.should_run(ctx):
                ctx.step_results[step_name] = {"skipped": True, "duration_ms": 0.0}
                continue
            start = time.perf_counter()
            try:
                # 若 execute 是协程,await;否则同步调用
                result = step.execute(ctx)
                if asyncio.iscoroutine(result):
                    ctx = await result
                else:
                    ctx = result
                duration_ms = (time.perf_counter() - start) * 1000
                ctx.step_results[step_name] = {
                    "skipped": False,
                    "duration_ms": duration_ms,
                }
            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                ctx.step_results[step_name] = {
                    "skipped": False,
                    "duration_ms": duration_ms,
                    "error": str(e),
                }
                ctx.errors.append(
                    {
                        "step": step_name,
                        "error": str(e),
                        "fatal": step.required,
                    }
                )
                if step.required:
                    break
        return ctx
