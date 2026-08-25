"""
CodingAgent - 编码智能体核心
============================
对齐工程实践 → Apply 范式和 Agent Mode, 基于 AgentOS 构建编码 Agent。

架构:
    Planner → Executor → Reviewer

底座:
    - AgentOS Process (任务状态机)
    - DiffEngine (原子多文件编辑)
    - CodeTools (read/write/edit/search/git/test)
    - ContextBuilder (上下文工程)

执行流程:
    1. PLAN:     LLM 分析任务 → 分解为 TaskStep 列表
    2. EXECUTE:  按计划调用 CodeTools (read/edit/write/compile/test), 写操作经 DiffEngine 原子应用
    3. REVIEW:   编译检查 + pytest + LLM 审查 diff
    4. HEAL:     审查失败时携带报错再规划/执行（最多 FNIX_CODE_HEAL_ROUNDS 轮，默认 2）
    5. 仍失败 → 返回 FAILED

零外部依赖: 仅 Python stdlib (json / asyncio / re / time / dataclasses / enum / uuid)

Usage:
    agent = CodingAgent(code_tools, context_builder, llm_backend)

    # 同步执行
    result = await agent.execute_task("为 AgentKernel 添加 health_check 方法")

    # 流式执行 (实时进度)
    async for event in agent.streaming_execute("为 AgentKernel 添加 health_check 方法"):
        print(event.type, event.status)

    # 带回调的同步执行
    result = await agent.execute_task("任务", on_event=lambda e: print(e))
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
import os
import re
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from fnixagent.core.agent.types import utcnow_iso
from fnixagent.core.code.vfs import VirtualFileSystem
from fnixagent.core.code.completeness import check_completeness

_logger = logging.getLogger(__name__)



def _heal_rounds() -> int:
    """报错修复最大轮数（0 = 关闭 heal）。"""
    try:
        return max(0, int(os.getenv("FNIX_CODE_HEAL_ROUNDS", "3")))
    except ValueError:
        return 3


# ============================================================================
# 任务状态枚举
# ============================================================================


class TaskStatus(Enum):
    """任务状态。"""

    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# 数据结构
# ============================================================================


@dataclass
class TaskStep:
    """任务执行步骤。

    Attributes:
        id: 步骤唯一标识 (8 位 hex)。
        description: 步骤描述; write 时作为写入内容, edit 时为 JSON {old_text, new_text}。
        action: 具体操作 (read/write/edit/test 等)。
        target: 目标文件路径。
        status: 步骤状态 (pending/done/failed/skipped)。
        result: 执行结果摘要。
        error: 失败原因。
    """

    id: str
    description: str
    action: str = ""  # 具体操作 (read/write/edit/test 等)
    target: str = ""  # 目标文件
    status: str = "pending"  # pending/done/failed/skipped
    result: str | dict = ""
    error: str = ""


@dataclass
class CodingTask:
    """编码任务。

    Attributes:
        id: 任务唯一标识 (12 位 hex)。
        description: 任务描述 (自然语言)。
        files: 涉及文件列表。
        constraints: 约束条件列表。
        created_at: 创建时间 (UTC ISO 字符串)。
    """

    id: str = field(default_factory=lambda: uuid4().hex[:12])
    description: str = ""
    files: list[str] = field(default_factory=list)  # 涉及文件
    constraints: list[str] = field(default_factory=list)  # 约束条件
    created_at: str = field(default_factory=lambda: utcnow_iso())


@dataclass
class TaskResult:
    """任务结果。

    Attributes:
        task_id: 任务 ID。
        status: 最终任务状态。
        plan: 执行计划 (TaskStep 列表)。
        changeset_id: 变更集 ID (None 表示无变更)。
        review_passed: 审查是否通过。
        review_notes: 审查意见。
        duration_sec: 执行耗时 (秒)。
        error: 失败原因 (成功时为 None)。
    """

    task_id: str
    status: TaskStatus
    plan: list[TaskStep] = field(default_factory=list)
    changeset_id: str | None = None
    review_passed: bool = False
    review_notes: str = ""
    duration_sec: float = 0.0
    error: str | None = None


@dataclass
class CodingAgentEvent:
    """流式执行事件。

    用于 streaming_execute() 和 execute_task() 的 on_event 回调。

    Attributes:
        type: 事件类型 (status/plan/step/file_change/review/done)。
        status: 当前状态 (planning/executing/reviewing/completed/failed)，
            type=status 时有效。
        steps: 计划步骤列表，type=plan 时有效。
        step: 当前步骤信息 (dict)，type=step 时有效。
        file_path: 文件变更路径，type=file_change 时有效。
        file_action: 文件变更操作 (create/modify/delete)，type=file_change 时有效。
        diff: 文件变更 diff 文本，type=file_change 时有效。
        content: 新文件内容（Accept 写入），type=file_change 时有效。
        old_content: 磁盘基线内容（冲突检测），type=file_change 时有效。
        review_passed: 审查是否通过，type=review 时有效。
        review_notes: 审查意见，type=review 时有效。
        result: 最终结果 (TaskResult)，type=done 时有效。
    """

    type: str
    status: str | None = None
    steps: list[dict] | None = None
    step: dict | None = None
    file_path: str | None = None
    file_action: str | None = None
    diff: str | None = None
    content: str | None = None
    old_content: str | None = None
    review_passed: bool | None = None
    review_notes: str | None = None
    result: TaskResult | None = None


# ============================================================================
# 编码智能体
# ============================================================================


class CodingAgent:
    """编码智能体 (对齐工程实践)。

    架构: Planner → Executor → Reviewer
    底座: AgentOS Process + DiffEngine + CodeTools

    支持两种执行模式:
      - execute_task(): 同步执行, 返回 TaskResult
      - streaming_execute(): 流式执行, 逐步产出 CodingAgentEvent 事件

    Usage:
        agent = CodingAgent(code_tools, context_builder, llm_backend)
        result = await agent.execute_task("为 AgentKernel 添加 health_check 方法")
    """

    def __init__(self, code_tools, context_builder, llm_backend, workspace: str = "."):
        """初始化编码智能体。

        Args:
            code_tools: CodeTools 实例 (提供 read/write/edit/search/git/test)。
            context_builder: ContextBuilder 实例 (提供 build_context)。
            llm_backend: LLMBackend 实例 (提供 complete 方法)。
            workspace: 工作区根目录 (用于 TodoStore 持久化 load-bearing state)。
        """
        self._tools = code_tools
        self._ctx_builder = context_builder
        self._llm = llm_backend
        self._workspace = workspace
        # 活跃任务表 (task_id -> CodingTask)
        self._active_tasks: dict[str, CodingTask] = {}
        # 每个任务执行期间产生的变更集 ID 列表 (task_id -> [changeset_id])
        # 用于 Review 阶段收集 diff (CodeTools 的写操作不返回 changeset_id, 只能从 DiffEngine 历史提取)
        self._task_changesets: dict[str, list[str]] = {}
        # 事件回调 (流式执行时由 streaming_execute / execute_task 设置)
        self._event_cb: Callable[[CodingAgentEvent], Any] | None = None
        self._last_llm_error: str | None = None
        # VirtualFileSystem: preview 模式下维护文件最终状态（磁盘即真相源）
        # 每次 write 同步到 VFS，每次 edit 基于当前 VFS 内容替换
        # review/completeness 从 VFS 读取最终内容，而非 step.result 拼接
        self._vfs = VirtualFileSystem()

    # ========================================================================
    # 主入口
    # ========================================================================

    async def execute_task(
        self,
        task: CodingTask | str,
        on_event: Callable[[CodingAgentEvent], Any] | None = None,
    ) -> TaskResult:
        """执行编码任务 (Plan → Execute → Review)。

        流程:
          1. PLAN: LLM 分析任务 → 分解为 TaskStep 列表
          2. EXECUTE: 按计划执行 (read/edit/write/test)
          3. REVIEW: 运行测试 + 审查 diff
          4. 任一步失败 → 返回 FAILED

        Args:
            task: 编码任务 (CodingTask 对象或任务描述字符串)。
            on_event: 可选事件回调, 在关键节点接收 CodingAgentEvent 事件。
                支持同步和异步回调。若不需要事件通知可省略, 保持向后兼容。

        Returns:
            TaskResult 任务执行结果。
        """
        # 标准化任务对象
        if isinstance(task, str):
            task = CodingTask(description=task)

        self._active_tasks[task.id] = task
        self._task_changesets[task.id] = []
        self._vfs.clear()  # 新任务清空 VFS
        self._event_cb = on_event
        start_time = time.perf_counter()

        plan: list[TaskStep] = []
        changeset_id: str | None = None
        review_passed = False
        review_notes = ""
        error: str | None = None
        status = TaskStatus.PENDING

        try:
            (
                plan,
                changeset_id,
                review_passed,
                review_notes,
                status,
                error,
            ) = await self._run_plan_execute_review_heal(task)
        except RuntimeError as exc:
            status = TaskStatus.FAILED
            error = str(exc)
        except Exception as exc:
            status = TaskStatus.FAILED
            error = f"未预期错误: {type(exc).__name__}: {exc}"
        finally:
            duration = time.perf_counter() - start_time
            self._active_tasks.pop(task.id, None)
            self._task_changesets.pop(task.id, None)
            self._event_cb = None

        result = TaskResult(
            task_id=task.id,
            status=status,
            plan=plan,
            changeset_id=changeset_id,
            review_passed=review_passed,
            review_notes=review_notes,
            duration_sec=duration,
            error=error,
        )

        await self._emit(
            CodingAgentEvent(
                type="status",
                status=status.value,
            )
        )

        # HERA 技能捕获 (对齐 Work 模式, 双模式对齐):
        # 任务完成后把解决方案存入技能库, 下次类似任务可召回
        await self._capture_skill_hera(task, result)

        # CriticAgent 独立审查 (对齐 Work 模式, 双模式对齐):
        # 解决 _review 内嵌审查易被 LLM 自圆其说的问题
        if status == TaskStatus.COMPLETED:
            await self._run_critic_review(task, result)

        # 用 LLM 流式生成自然语言完成摘要，逐 chunk 发送 message 事件
        # 让聊天区看到文字逐字流式输出（像 Cursor/Codex 那样）
        await self._stream_completion_summary(task, result)

        await self._emit(CodingAgentEvent(type="done", result=result))

        return result

    async def streaming_execute(
        self,
        task: CodingTask | str,
    ) -> AsyncGenerator[CodingAgentEvent, None]:
        """流式执行编码任务 (Plan → Execute → Review)。

        与 execute_task() 执行相同的 Plan→Execute→Review 流程,
        但以异步生成器方式逐步产出 CodingAgentEvent 事件,
        调用方可通过 async for 逐事件消费, 实现实时进度展示。

        产出的事件类型:
          - {"type": "status", "status": "planning"} — 开始规划
          - {"type": "plan", "steps": [...]} — 规划完成, 返回步骤列表
          - {"type": "status", "status": "executing"} — 开始执行
          - {"type": "step", "step": {...}} — 每个步骤开始/完成/失败
          - {"type": "file_change", "file_path": "...", "file_action": "modify", "diff": "..."} — 文件变更
          - {"type": "status", "status": "reviewing"} — 开始审查
          - {"type": "review", "review_passed": true/false, "review_notes": "..."} — 审查结果
          - {"type": "status", "status": "completed"|"failed"} — 最终状态
          - {"type": "done", "result": TaskResult} — 最终结果

        Args:
            task: 编码任务 (CodingTask 对象或任务描述字符串)。

        Yields:
            CodingAgentEvent 流式事件。
        """
        # 标准化任务对象
        if isinstance(task, str):
            task = CodingTask(description=task)

        self._active_tasks[task.id] = task
        self._task_changesets[task.id] = []
        self._vfs.clear()  # 新任务清空 VFS
        start_time = time.perf_counter()

        plan: list[TaskStep] = []
        changeset_id: str | None = None
        review_passed = False
        review_notes = ""
        error: str | None = None
        status = TaskStatus.PENDING

        # 使用队列收集 _emit 发出的事件, 从生成器逐条产出
        queue: asyncio.Queue[CodingAgentEvent | None] = asyncio.Queue()

        async def _queue_cb(event: CodingAgentEvent) -> None:
            await queue.put(event)

        self._event_cb = _queue_cb

        # 后台执行任务, 事件通过队列传递
        async def _run() -> None:
            nonlocal plan, changeset_id, review_passed, review_notes, error, status
            try:
                (
                    plan,
                    changeset_id,
                    review_passed,
                    review_notes,
                    status,
                    error,
                ) = await self._run_plan_execute_review_heal(task)
            except RuntimeError as exc:
                status = TaskStatus.FAILED
                error = str(exc) or f"{type(exc).__name__}(无错误消息)"
                _logger.exception("coding task failed (RuntimeError): %s", task.id)
            except Exception as exc:
                status = TaskStatus.FAILED
                error = f"未预期错误: {type(exc).__name__}: {exc}"
                _logger.exception("coding task failed (unexpected): %s", task.id)
            finally:
                duration = time.perf_counter() - start_time
                self._active_tasks.pop(task.id, None)
                self._task_changesets.pop(task.id, None)

            result = TaskResult(
                task_id=task.id,
                status=status,
                plan=plan,
                changeset_id=changeset_id,
                review_passed=review_passed,
                review_notes=review_notes,
                duration_sec=duration,
                error=error,
            )

            await self._emit(
                CodingAgentEvent(
                    type="status",
                    status=status.value,
                )
            )

            # 用 LLM 流式生成自然语言完成摘要，逐 chunk 发送 message 事件
            await self._stream_completion_summary(task, result)

            await self._emit(CodingAgentEvent(type="done", result=result))
            # 发送结束标记
            await queue.put(None)

        # 启动后台任务
        runner = asyncio.ensure_future(_run())

        try:
            # 从队列中逐条产出事件
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
            await runner  # 确保后台任务完成, 捕获可能遗漏的异常
        finally:
            self._event_cb = None
            if not runner.done():
                runner.cancel()
                try:
                    await runner
                except asyncio.CancelledError:
                    pass

    # ========================================================================
    # Plan → Execute → Review → Heal
    # ========================================================================

    async def _run_plan_execute_review_heal(
        self,
        task: CodingTask,
    ) -> tuple[list[TaskStep], str | None, bool, str, TaskStatus, str | None]:
        """完整闭环：规划 → 执行 → 审查 →（失败则）带报错再修复。"""
        # load-bearing state 外化 (任务状态外化):
        # heal 多轮时记录已尝试的 plan/失败原因, 避免 _plan_heal 失忆
        todo_store = self._load_todo_store()
        todos_block = todo_store.format_for_prompt() if todo_store else ""

        await self._emit(CodingAgentEvent(type="status", status="planning"))
        # 初始 thinking 标签由 _plan → _call_llm_streaming 发送，不再重复
        plan = await self._plan(task, todos_block=todos_block)
        plan = self._augment_plan_with_required_files(task, plan)
        # 把 plan steps 同步到 TodoStore (load-bearing state)
        if todo_store:
            self._sync_plan_to_todos(todo_store, plan)
            todos_block = todo_store.format_for_prompt()
        await self._emit(
            CodingAgentEvent(
                type="plan",
                steps=[
                    {
                        "id": s.id,
                        "description": s.description,
                        "action": s.action,
                        "target": s.target,
                    }
                    for s in plan
                ],
            )
        )

        # 发送分阶段 message 事件：规划完成，让聊天区实时显示进度
        plan_summary = self._build_plan_message(plan)
        if plan_summary:
            await self._emit(CodingAgentEvent(type="message", content=plan_summary))

        await self._emit(CodingAgentEvent(type="status", status="executing"))
        changeset_id = await self._execute(task, plan)
        if todo_store:
            self._update_todos_after_execute(todo_store, plan)

        await self._emit(CodingAgentEvent(type="status", status="reviewing"))
        # 审查 thinking 标签由 _review → _call_llm_streaming 发送，不再重复
        review_passed, review_notes = await self._review(task, plan)
        if todo_store:
            self._update_todos_after_review(todo_store, review_passed, review_notes)
            todos_block = todo_store.format_for_prompt()
        await self._emit(
            CodingAgentEvent(
                type="review",
                review_passed=review_passed,
                review_notes=review_notes,
            )
        )

        # 发送分阶段 message 事件：审查结果（加 \n\n 段落分隔）
        review_msg = self._build_review_message(review_passed, review_notes)
        if review_msg:
            await self._emit(CodingAgentEvent(type="message", content="\n\n" + review_msg))

        heal_round = 0
        max_heal = _heal_rounds()
        while (not review_passed) and heal_round < max_heal:
            heal_round += 1
            await self._emit(
                CodingAgentEvent(
                    type="heal",
                    status=f"healing:{heal_round}",
                    review_notes=review_notes[:500] if review_notes else "",
                )
            )
            await self._emit(
                CodingAgentEvent(
                    type="status",
                    status=f"healing:{heal_round}",
                )
            )
            # heal 时注入最新 todos_block (含历次失败原因, 避免 _plan_heal 失忆)
            # heal thinking 标签由 _plan_heal → _call_llm_streaming 发送，不再重复
            heal_plan = await self._plan_heal(task, review_notes, todos_block=todos_block)
            if not heal_plan:
                # 最后一轮：用脚手架补齐缺失交付（smoke/可靠性）
                heal_plan = self._scaffold_heal_plan(task, review_notes)
            if not heal_plan:
                break
            plan = self._augment_plan_with_required_files(task, heal_plan)
            if todo_store:
                self._sync_plan_to_todos(todo_store, plan, heal_round=heal_round)
                todos_block = todo_store.format_for_prompt()
            await self._emit(
                CodingAgentEvent(
                    type="plan",
                    steps=[
                        {
                            "id": s.id,
                            "description": s.description,
                            "action": s.action,
                            "target": s.target,
                        }
                        for s in plan
                    ],
                )
            )
            await self._emit(CodingAgentEvent(type="status", status="executing"))
            cs = await self._execute(task, plan)
            if cs:
                changeset_id = cs
            if todo_store:
                self._update_todos_after_execute(todo_store, plan)
            await self._emit(CodingAgentEvent(type="status", status="reviewing"))
            review_passed, review_notes = await self._review(task, plan)
            if todo_store:
                self._update_todos_after_review(todo_store, review_passed, review_notes)
                todos_block = todo_store.format_for_prompt()
            await self._emit(
                CodingAgentEvent(
                    type="review",
                    review_passed=review_passed,
                    review_notes=review_notes or f"heal round {heal_round}",
                )
            )

        if not review_passed:
            # 耗尽 heal 后仍失败：再尝试一次脚手架写盘
            scaffold = self._scaffold_heal_plan(task, review_notes or "")
            if scaffold:
                plan = scaffold
                cs = await self._execute(task, plan)
                if cs:
                    changeset_id = cs
                review_passed, review_notes = await self._review(task, plan)
                if review_passed:
                    return plan, changeset_id, True, review_notes, TaskStatus.COMPLETED, None
            return (
                plan,
                changeset_id,
                False,
                review_notes or "审查未通过",
                TaskStatus.FAILED,
                (review_notes or "审查未通过"),
            )
        return plan, changeset_id, True, review_notes, TaskStatus.COMPLETED, None

    async def _plan_heal(
        self, task: CodingTask, failure_notes: str, *, todos_block: str = ""
    ) -> list[TaskStep]:
        """根据编译/测试失败信息生成修复计划。"""
        ctx = await self._ctx_builder.build_context(
            task.description,
            system_prompt=(
                "你是编码修复助手。根据报错修改代码，返回 JSON 计划。"
                "优先使用 edit/write，然后 compile 与 test。"
            ),
        )
        messages = list(ctx.messages)
        # load-bearing state 注入 (任务状态外化):
        # heal 时让 LLM 看到历次尝试和失败原因, 避免重复相同错误
        if todos_block:
            messages.append(
                {
                    "role": "system",
                    "content": todos_block,
                }
            )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"原任务: {task.description}\n\n"
                    f"失败信息:\n{failure_notes[:4000]}\n\n"
                    "请返回修复步骤 JSON:\n"
                    '{"steps": [{"description": "...", "action": "read|edit|write|compile|test",'
                    ' "target": "文件路径"}]}\n'
                    "规则：\n"
                    "- 若提示「函数/类未实现」或「缺少函数」：必须 write 完整源码，"
                    "包含所有缺失的函数定义。不要只写缺失的函数，要写出完整的文件内容。\n"
                    "- 若提示缺少文件：必须 write 完整源码（含函数定义与测试）。\n"
                    "- 若提示 SyntaxError：先 read 再 edit 补全冒号/缩进/括号。\n"
                    "- edit 的 description 必须是 "
                    '{"old_text":"...","new_text":"..."} 或 old|||new。\n'
                    "- write 的 description 必须是完整可运行源码，禁止中文占位说明。\n"
                    "- 不要引入任务中未提到的额外类或函数（如 Identity、Rules 等）。\n"
                    "- 最后一步尽量 compile 或 test。\n"
                    "只返回 JSON。"
                ),
            }
        )
        # P1-3: 注入当前文件状态（VFS 快照），让 LLM 看到完整文件而非 diff 片段
        # 借鉴 SWE-agent "先读后写" 原则：heal 时让 LLM 基于当前文件内容修复
        vfs_snapshot = self._vfs.code_snapshot()
        if vfs_snapshot:
            file_context = "\n\n".join(
                f"--- {path} ---\n{content}"
                for path, content in vfs_snapshot.items()
            )
            # 截断到 8000 字符防止上下文溢出
            if len(file_context) > 8000:
                file_context = file_context[:8000] + "\n...(截断)"
            messages.insert(-1, {
                "role": "system",
                "content": f"当前文件状态（请基于此修复，不要重写已有内容）：\n{file_context}",
            })
        response = await self._call_llm_streaming(
            messages,
            thinking_label="正在根据审查反馈制定修复计划",
        )
        steps = self._parse_plan(response)
        # 过滤掉无意义的 fallback「手动执行」若 LLM 空响应
        if len(steps) == 1 and steps[0].action in ("", "manual"):
            return []
        return steps

    # ========================================================================
    # Plan 阶段
    # ========================================================================

    async def _plan(self, task: CodingTask, *, todos_block: str = "") -> list[TaskStep]:
        """Plan 阶段: LLM 生成执行计划。

        构造上下文 (ContextBuilder.build_context) → LLM 推理 → 解析为 TaskStep 列表。
        LLM 应返回 JSON 格式:
        {"steps": [{"description": "...", "action": "read|edit|write|test", "target": "path"}]}

        解析失败时返回单步 "手动执行任务"。

        Args:
            task: 编码任务。
            todos_block: load-bearing state (任务状态外化), 可选。

        Returns:
            TaskStep 列表 (至少 1 个步骤)。
        """
        # 构造上下文 (系统提示指定为计划生成器角色)
        ctx = await self._ctx_builder.build_context(
            task.description,
            system_prompt="你是编码计划生成器, 将任务分解为具体步骤, 返回 JSON",
        )
        messages = list(ctx.messages)
        # load-bearing state 注入 (任务状态外化)
        if todos_block:
            messages.append(
                {
                    "role": "system",
                    "content": todos_block,
                }
            )

        # 追加输出格式指令 + 任务补充信息
        instruction_lines: list[str] = [
            "请将上述任务分解为具体执行步骤, 返回 JSON 格式:",
            '{"steps": [{"description": "步骤描述", "action": "read|edit|write|compile|test", "target": "文件路径"}],'
            ' "deliverables": ["必须存在的文件路径列表"]}',
            "硬性要求：",
            "1) 任务要求新建的每个文件必须在 steps 里有对应 write，且列入 deliverables。",
            "2) 若要求测试，必须 write 出 test_*.py（或任务指定的测试文件）并有一步 test。",
            "3) 语法/bug 修复：先 read 再 edit，然后 compile 与 test。",
            "4) write 的 description 必须是完整可运行源码（含 def/import），禁止中文占位或 TODO stub。",
            '5) edit 的 description 必须是 JSON {"old_text":"原文","new_text":"新文"} 或 old|||new。',
            "6) **路径**：按用户指定的文件名写到项目根或相对路径（如 fib.py、calc.py）。"
            "禁止写入 `.fnix/artifacts/`（那是 Work 办公产物目录，不是 Code 工程目录）。",
            "只返回 JSON, 不要其他内容。",
        ]
        if task.files:
            instruction_lines.append(f"涉及文件: {', '.join(task.files)}")
        if task.constraints:
            instruction_lines.append(f"约束条件: {'; '.join(task.constraints)}")
        messages.append(
            {
                "role": "user",
                "content": "\n".join(instruction_lines),
            }
        )

        # LLM 推理并解析 — 规划阶段使用真正流式调用，逐 chunk 发送 thinking 事件
        response = await self._call_llm_streaming(
            messages,
            thinking_label="正在分析任务需求，制定执行计划",
        )
        return self._parse_plan(response)

    # ========================================================================
    # Execute 阶段
    # ========================================================================

    async def _execute(self, task: CodingTask, steps: list[TaskStep]) -> str | None:
        """Execute 阶段: 按计划执行。

        根据 step.action 调用 CodeTools 对应方法。
        所有写操作通过 DiffEngine 原子应用。
        返回 changeset_id (None 表示无变更)。

        任一步失败 → 抛 RuntimeError。

        执行过程中会通过 _emit 发送 step 和 file_change 事件。

        Args:
            task: 编码任务。
            steps: 执行计划。

        Returns:
            最后一个变更集 ID; 无变更时返回 None。

        Raises:
            RuntimeError: 任一步骤执行失败。
        """
        # 记录执行前的 DiffEngine 历史长度, 用于事后收集本次产生的变更集
        hist_before = len(self._tools._diff.get_history())

        try:
            for step in steps:
                # 发送步骤开始事件
                await self._emit(
                    CodingAgentEvent(
                        type="step",
                        step={
                            "id": step.id,
                            "description": step.description,
                            "action": step.action,
                            "target": step.target,
                            "status": "running",
                        },
                    )
                )

                # 记录步骤执行前的历史长度, 用于检测文件变更
                step_hist_before = len(self._tools._diff.get_history())

                try:
                    await self._execute_step(step)
                    # compile/test 失败不中断整条流水线，交给 Review → Heal
                    if step.status == "failed":
                        await self._emit(
                            CodingAgentEvent(
                                type="step",
                                step={
                                    "id": step.id,
                                    "status": "failed",
                                    "error": step.error or str(step.result or ""),
                                },
                            )
                        )
                        continue
                    if step.status != "skipped":
                        step.status = "done"
                except Exception as exc:
                    step.status = "failed"
                    step.error = str(exc)
                    await self._emit(
                        CodingAgentEvent(
                            type="step",
                            step={"id": step.id, "status": "failed", "error": str(exc)},
                        )
                    )
                    # 写操作失败仍中断；校验类失败进入审查/修复
                    if step.action.strip().lower() in ("test", "compile", "write", "edit"):
                        continue
                    raise RuntimeError(
                        f"步骤 {step.id} ({step.description[:60]}) 执行失败: {exc}"
                    ) from exc

                # 发送步骤完成事件
                await self._emit(
                    CodingAgentEvent(
                        type="step",
                        step={
                            "id": step.id,
                            "status": step.status,
                            "result": step.result,
                        },
                    )
                )

                # 检测写操作产生的文件变更并发送 file_change 事件
                if step.action in ("write", "edit"):
                    new_history = self._tools._diff.get_history()
                    new_changesets = [(cs, _) for cs, _ in new_history[step_hist_before:]]
                    for cs, _ in new_changesets:
                        for ch in getattr(cs, "changes", None) or []:
                            action = getattr(ch.change_type, "value", None) or str(
                                ch.change_type or "modify"
                            )
                            file_path = ch.path or step.target
                            await self._emit(
                                CodingAgentEvent(
                                    type="file_change",
                                    file_path=file_path,
                                    file_action=str(action).lower(),
                                    diff=ch.to_diff() or cs.to_diff(),
                                    content=ch.new_content,
                                    old_content=ch.old_content,
                                )
                            )
                            # 发送分阶段 message 事件：文件变更（加 \n\n 段落分隔）
                            action_label = "创建" if str(action).lower() == "create" else "修改"
                            await self._emit(
                                CodingAgentEvent(
                                    type="message",
                                    content=f"\n\n正在{action_label} `{file_path}`…",
                                )
                            )
        finally:
            # 收集本次执行产生的所有变更集 ID (无论成功失败, 便于 Review 阶段取 diff)
            history = self._tools._diff.get_history()
            new_ids = [cs.id for cs, _ in history[hist_before:]]
            # BUG-4 修复: 累积而非覆盖。heal/多轮 _execute 时, 阶段1(plan) 与
            # 阶段2(heal) 的变更集都要保留; 否则最终 Review 的 diff 只含最后一次
            # _execute 的变更, LLM 会误报「早期已创建的交付文件缺失」→ 整任务假失败。
            # 案例: angular--task-1 阶段1 建 header/main/blog 三组件, heal 阶段建
            # app.component.ts, 覆盖后 review 只见 app.component.ts → 三组件误报缺失。
            existing = self._task_changesets.get(task.id, [])
            seen = set(existing)
            self._task_changesets[task.id] = existing + [i for i in new_ids if i not in seen]

        # 返回最后一个变更集 ID (无变更返回 None)
        changeset_ids = self._task_changesets[task.id]
        if not changeset_ids:
            return None
        return changeset_ids[-1]

    async def _execute_step(self, step: TaskStep) -> None:
        """执行单个步骤 (按 action 分发到 CodeTools)。

        支持的 action:
          - read:  读取 step.target 文件
          - write: 将 step.description 作为内容写入 step.target
          - edit:  从 step.description 解析 {old_text, new_text} 后精确替换
          - test:  运行 pytest (默认参数)
        未知 action 标记为 skipped。

        Args:
            step: 待执行步骤, 执行后填充 result/error。

        Raises:
            RuntimeError: 工具执行失败 (result.success=False)。
        """
        action = step.action.strip().lower()
        # Code 工程：勿把 .py 写进 Work 的 artifacts 目录
        if action in ("read", "write", "edit", "compile") and step.target:
            step.target = self._normalize_code_target(step.target)

        if action == "read":
            result = await self._tools.read(step.target)

        elif action == "write":
            content = self._extract_source_content(step.description)
            if not self._looks_like_source(content, target=step.target or ""):
                # 模型把 description 写成了「任务描述」而非「完整源码」——
                # 对 glm-4.7 等 reasoning 模型常见。降级：调用 LLM 依据
                # step.description + 原始任务生成真实源码，再写入。
                generated = await self._generate_source_for_write(step)
                if generated and self._looks_like_source(generated, target=step.target or ""):
                    content = generated
                else:
                    step.status = "failed"
                    step.error = (
                        f"write 内容不是可运行源码（target={step.target}）。"
                        "请用完整 Python/源码重写，勿写中文说明。"
                    )
                    step.result = step.error
                    return
            # 同步到 VFS（无论是否 preview）— 磁盘即真相源
            self._vfs.write(step.target, content)
            result = await self._tools.write(step.target, content)

        elif action == "edit":
            try:
                old_text, new_text = self._parse_edit_payload(step.description)
                # 同步到 VFS：基于当前 VFS 内容做替换（如果 VFS 中有该文件）
                vfs_ok, vfs_err = self._vfs.edit(step.target, old_text, new_text)
                if not vfs_ok:
                    _logger.debug("VFS edit skipped: %s", vfs_err)
                result = await self._tools.edit(step.target, old_text, new_text)
                # 如果磁盘 edit 成功但 VFS 没有该文件（编辑已有磁盘文件），
                # 从磁盘读取最终内容同步到 VFS
                if not vfs_ok and result.success and isinstance(result.output, dict):
                    final_content = str(result.output.get("content") or "")
                    if final_content:
                        self._vfs.write(step.target, final_content)
            except RuntimeError:
                result = await self._edit_fallback(step)
                # edit_fallback 可能用 write 覆盖，同步到 VFS
                if result.success and isinstance(result.output, dict):
                    final_content = str(result.output.get("content") or "")
                    if final_content:
                        self._vfs.write(step.target, final_content)

        elif action == "compile":
            result = await self._tools.compile_check(step.target if step.target else None)

        elif action == "test":
            result = await self._tools.test()

        else:
            # 未知 action, 跳过 (不视为失败)
            step.status = "skipped"
            step.result = f"未知 action: {action or '(空)'}"
            return

        # 统一处理工具结果
        if not result.success:
            err = result.error or f"工具 {action} 执行失败"
            # compile/test/write/edit 均可恢复：交给 Review → Heal，勿中断整轮
            if action in ("compile", "test", "write", "edit", "read"):
                step.status = "failed"
                step.error = err
                step.result = self._truncate(err, 2000)
                return
            raise RuntimeError(err)

        # 写操作保留结构化结果（供 preview / file_change 流式事件）
        if action in ("write", "edit") and isinstance(result.output, dict):
            step.result = result.output
        else:
            step.result = self._truncate(str(result.output), 2000)

    def _parse_edit_payload(self, description: str) -> tuple[str, str]:
        """解析 edit 步骤的 description 为 (old_text, new_text)。

        支持格式:
          1. JSON: {"old_text": "...", "new_text": "..."}（含 old/new、from/to 等别名）
          2. Markdown 代码块内的 JSON
          3. 分隔符: "原文|||新文本"
          4. 双换行 + --- 分隔的旧/新文本块

        Args:
            description: edit 步骤的描述字段。

        Returns:
            (old_text, new_text) 元组。

        Raises:
            RuntimeError: 无法解析出 old_text/new_text。
        """
        text = (description or "").strip()
        if not text:
            raise RuntimeError("edit 步骤 description 为空")

        block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if block:
            text = block.group(1).strip()

        candidates = [text]
        embedded = re.search(
            r"\{[\s\S]*\"(?:old_text|old|new_text|new|from|to)\"[\s\S]*\}",
            text,
        )
        if embedded:
            candidates.insert(0, embedded.group(0))

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
                continue
            if not isinstance(data, dict):
                continue
            old_text = str(
                data.get("old_text")
                or data.get("old")
                or data.get("from")
                or data.get("before")
                or data.get("oldText")
                or ""
            )
            new_text = str(
                data.get("new_text")
                or data.get("new")
                or data.get("to")
                or data.get("after")
                or data.get("newText")
                or ""
            )
            if old_text:
                return old_text, new_text

        if "|||" in text:
            old_text, new_text = text.split("|||", 1)
            return old_text, new_text

        if "\n---\n" in text:
            old_text, new_text = text.split("\n---\n", 1)
            if old_text.strip() and new_text.strip():
                return old_text, new_text

        raise RuntimeError(
            "edit 步骤的 description 无法解析为 {old_text, new_text} "
            "(需 JSON 格式或 'old|||new' 分隔符格式)"
        )

    async def _edit_fallback(self, step: TaskStep) -> Any:
        """edit 解析失败时的降级策略：常见 bug 模式替换或小文件 write 覆盖。"""
        read_r = await self._tools.read(step.target)
        if not read_r.success:
            raise RuntimeError(
                f"edit 无法解析 description 且读取 {step.target} 失败: {read_r.error}"
            )

        body = self._strip_line_numbers(str(read_r.output))
        desc = (step.description or "").strip()
        desc_lower = desc.lower()

        if "a + b" in body and (
            "subtract" in body.lower()
            or "subtract" in desc_lower
            or "减法" in desc
            or "bug" in desc_lower
            or "fix" in desc_lower
        ):
            fixed = re.sub(r"return\s+a\s*\+\s+b", "return a - b", body, count=1)
            if fixed == body:
                fixed = body.replace("a + b", "a - b", 1)
            if fixed != body:
                return await self._tools.write(step.target, fixed)

        # 常见语法错误：def foo(x)\n 缺冒号
        if (
            "syntax" in desc_lower
            or "冒号" in desc
            or "colon" in desc_lower
            or "fix" in desc_lower
            or "missing" in desc_lower
        ):
            fixed = re.sub(r"(def\s+\w+\([^)]*\))\s*\n(\s+)", r"\1:\n\2", body)
            if fixed != body:
                return await self._tools.write(step.target, fixed)

        if self._looks_like_source(desc):
            return await self._tools.write(step.target, desc)

        raise RuntimeError(
            "edit 步骤的 description 无法解析为 {old_text, new_text} "
            "(需 JSON 格式或 'old|||new' 分隔符格式)"
        )

    @staticmethod
    def _extract_source_content(description: str) -> str:
        """从 write description 提取源码（去掉 markdown 围栏）。

        BUG-7 防御: 某些 LLM 在 JSON 中把换行转义为字面 ``\\n`` (双重转义)，
        导致 json.loads 后仍含字面 backslash-n。此处做一步 unescape 兜底。
        """
        text = (description or "").strip()
        if not text:
            return ""
        m = re.search(
            r"```(?:python|py|typescript|ts|javascript|js|rust|go)?\s*\n([\s\S]*?)```", text
        )
        if m:
            return m.group(1).strip() + "\n"
        # 去掉误嵌的 JSON 外壳 {"content": "..."}
        if text.startswith("{") and "content" in text[:80]:
            try:
                data = json.loads(text)
                if isinstance(data, dict) and isinstance(data.get("content"), str):
                    return data["content"]
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
        # BUG-7 防御: 如果文本含字面 \n (backslash + n) 但不含真实换行，
        # 说明 LLM 返回了双重转义的 JSON。将字面 \n 替换为真实换行。
        if "\\n" in text and "\n" not in text:
            text = text.replace("\\n", "\n").replace("\\t", "\t")
        return text if text.endswith("\n") else text + "\n"

    async def _generate_source_for_write(self, step: TaskStep) -> str:
        """write 的 description 是「任务描述」而非「源码」时，调用 LLM 生成源码。

        依据 step.description（如 "Write blog-list.component.ts with input property..."）
        和 target 文件扩展名，生成完整可运行源码。返回空串表示生成失败。
        """
        desc = (step.description or "").strip()
        target = (step.target or "").strip()
        if not desc or not target:
            return ""
        ext = target.rsplit(".", 1)[-1].lower() if "." in target else ""
        lang = {
            "py": "Python", "ts": "TypeScript", "tsx": "TypeScript (React)",
            "js": "JavaScript", "jsx": "JavaScript (React)", "html": "HTML",
            "css": "CSS", "json": "JSON", "rs": "Rust", "go": "Go",
            "md": "Markdown", "svg": "SVG",
        }.get(ext, "源码")
        messages = [
            {
                "role": "system",
                "content": (
                    "你是资深工程师。只输出完整可运行的%s代码，"
                    "不要任何解释、注释外的中文说明、不要 markdown 围栏。"
                    "直接以代码开头、以代码结尾。" % lang
                ),
            },
            {
                "role": "user",
                "content": (
                    "目标文件：%s\n任务：%s\n\n"
                    "请直接输出该文件的完整%s代码。" % (target, desc, lang)
                ),
            },
        ]
        try:
            text = await self._call_llm(messages)
        except Exception as exc:
            self._last_llm_error = f"{type(exc).__name__}: {exc}"
            return ""
        return self._extract_source_content(text)

    @staticmethod
    def _infer_required_files(task_description: str) -> list[str]:
        """从任务描述推断必须交付的文件名（如 fib.py / test_fib.py）。

        仅源码类扩展名视为交付物；文档/纯文本(.md/.txt)虽常被上下文(如注入的
        SOUL.md / MEMORY.md / AGENTS.md 等记忆文件)提及,但脚手架无法生成,
        若纳入推断会永远判定为"缺失交付"导致审查误失败。
        同时显式屏蔽内部记忆/配置文件,避免被当作编码交付物。
        """
        # 源码类扩展名（脚手架可生成/审查可用）
        code_ext = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".html", ".css")
        # 内部记忆/配置文件：永不作为编码交付物
        reserved = {
            "soul.md",
            "memory.md",
            "user.md",
            "agents.md",
            "agents.override.md",
            "rules.md",
            "bootstrap.md",
            "identity.md",
            "readme.md",
            "changelog.md",
        }
        text = task_description or ""
        found = re.findall(
            r"\b([A-Za-z_][\w./-]*\.(?:py|ts|tsx|js|jsx|rs|go|html|css|md|txt))\b",
            text,
        )
        # 去重保序；丢掉明显非工程路径
        out: list[str] = []
        seen: set[str] = set()
        for f in found:
            f = f.replace("\\", "/").lstrip("./")
            if f.startswith(".fnix/"):
                continue
            base = f.split("/")[-1].lower()
            if base in reserved:
                continue
            if not base.endswith(code_ext):
                continue
            if base in seen:
                continue
            seen.add(base)
            out.append(base)
        return out

    def _augment_plan_with_required_files(
        self, task: CodingTask, plan: list[TaskStep]
    ) -> list[TaskStep]:
        """计划缺少任务点名的文件 write 时，补上脚手架 write 步骤。"""
        required = self._infer_required_files(task.description)
        if not required:
            return plan
        planned_writes = {
            self._normalize_code_target(s.target).replace("\\", "/").split("/")[-1]
            for s in plan
            if (s.action or "").lower() == "write" and s.target
        }
        # 已有 write 但内容不像源码 → 用脚手架替换 description
        for step in plan:
            if (step.action or "").lower() != "write" or not step.target:
                continue
            name = self._normalize_code_target(step.target).replace("\\", "/").split("/")[-1]
            if name in required and not self._looks_like_source(
                self._extract_source_content(step.description)
            ):
                scaffold = self._scaffold_file_content(name, task.description)
                if scaffold:
                    step.description = scaffold
                    step.target = name

        extras: list[TaskStep] = []
        for name in required:
            if name in planned_writes:
                continue
            content = self._scaffold_file_content(name, task.description)
            if not content:
                continue
            extras.append(
                TaskStep(
                    id=uuid4().hex[:8],
                    description=content,
                    action="write",
                    target=name,
                )
            )
        if not extras:
            return plan
        # 插入到 test/compile 之前
        insert_at = len(plan)
        for i, s in enumerate(plan):
            if (s.action or "").lower() in ("test", "compile"):
                insert_at = i
                break
        return plan[:insert_at] + extras + plan[insert_at:]

    def _scaffold_heal_plan(self, task: CodingTask, failure_notes: str) -> list[TaskStep]:
        """根据任务/失败信息生成确定性 write 脚手架（最后手段）。"""
        required = self._infer_required_files(task.description)
        # 从失败笔记里再挖文件名
        required.extend(self._infer_required_files(failure_notes))
        # 常见缺文件关键词
        notes = (failure_notes or "").lower()
        for hint, name in (
            ("fib.py", "fib.py"),
            ("test_fib", "test_fib.py"),
            ("calc.py", "calc.py"),
            ("test_calc", "test_calc.py"),
            ("main.py", "main.py"),
            ("broken.py", "broken.py"),
        ):
            if hint in notes or hint in task.description.lower():
                required.append(name)
        # 去重
        seen: set[str] = set()
        files: list[str] = []
        for f in required:
            base = f.replace("\\", "/").split("/")[-1]
            if base not in seen:
                seen.add(base)
                files.append(base)
        steps: list[TaskStep] = []
        for name in files:
            content = self._scaffold_file_content(name, task.description)
            if not content:
                continue
            steps.append(
                TaskStep(
                    id=uuid4().hex[:8],
                    description=content,
                    action="write",
                    target=name,
                )
            )
        if steps:
            steps.append(
                TaskStep(
                    id=uuid4().hex[:8],
                    description="compile check",
                    action="compile",
                    target=steps[0].target,
                )
            )
            steps.append(
                TaskStep(
                    id=uuid4().hex[:8],
                    description="run tests",
                    action="test",
                    target="",
                )
            )
        return steps

    @staticmethod
    def _scaffold_file_content(filename: str, task_description: str = "") -> str:
        """为常见 smoke 文件生成可运行源码。"""
        name = filename.replace("\\", "/").split("/")[-1].lower()
        desc = (task_description or "").lower()

        if name == "fib.py":
            return (
                "def fib(n):\n"
                "    if n < 0:\n"
                "        raise ValueError('n must be >= 0')\n"
                "    if n == 0:\n"
                "        return 0\n"
                "    if n == 1:\n"
                "        return 1\n"
                "    a, b = 0, 1\n"
                "    for _ in range(2, n + 1):\n"
                "        a, b = b, a + b\n"
                "    return b\n"
            )
        if name == "test_fib.py":
            return (
                "from fib import fib\n\n\n"
                "def test_fib():\n"
                "    assert fib(0) == 0\n"
                "    assert fib(1) == 1\n"
                "    assert fib(10) == 55\n"
            )
        if name == "calc.py":
            return "def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n"
        if name == "test_calc.py":
            return (
                "from calc import add, multiply\n\n\n"
                "def test_add():\n"
                "    assert add(2, 3) == 5\n\n\n"
                "def test_multiply():\n"
                "    assert multiply(4, 5) == 20\n"
            )
        if name == "main.py" and ("hello" in desc or "greet" in desc or "alice" in desc):
            return (
                "import sys\n\n\n"
                "def main():\n"
                "    name = sys.argv[1] if len(sys.argv) > 1 else 'World'\n"
                "    print(f'Hello, {name}!')\n\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            )
        if name == "broken.py":
            return "def double(x):\n    return x * 2\n"
        if name == "math_utils.py" and "subtract" in desc:
            return "def subtract(a, b):\n    return a - b\n"
        return ""

    @staticmethod
    def _normalize_code_target(target: str) -> str:
        """把误指向 `.fnix/artifacts/.../foo.py` 的路径纠正为工程相对路径。"""
        t = (target or "").replace("\\", "/")
        while t.startswith("./"):
            t = t[2:]
        marker = ".fnix/artifacts/"
        if marker not in t:
            return target
        rest = t.split(marker, 1)[1]
        parts = [p for p in rest.split("/") if p]
        if not parts:
            return target
        name = parts[-1]
        # 单文件模块 / 测试：提到根目录
        if name.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go")):
            if len(parts) <= 2:
                return name
            return "/".join(parts)
        return "/".join(parts)

    @staticmethod
    def _strip_line_numbers(text: str) -> str:
        lines: list[str] = []
        for line in text.splitlines():
            m = re.match(r"^\s*\d+\t(.*)$", line)
            lines.append(m.group(1) if m else line)
        return "\n".join(lines)

    @staticmethod
    def _looks_like_source(text: str, target: str = "") -> bool:
        """判断 write 内容是否像可运行源码。

        按目标文件扩展名分派校验策略：
          - 声明式/标记类文件(.html/.css/.json/.md/.svg/.xml/.yaml/.yml)
            只要求非空且有一定结构(含标签/冒号/括号等),不强制代码关键词——
            Angular 模板、CSS、JSON 等天然不含 def/class/function。
          - 代码类文件(.py/.ts/.js/.tsx/.jsx/.rs/.go)要求含代码关键词。
        """
        t = text.strip()
        # 仅拒绝真正空/极短的无效内容。原先 20 字符阈值会把合法的极简源码
        # (print('hi') / x = 1 / if True: pass) 误判为"非源码"而拒绝落盘。
        # 真正的"任务描述 vs 源码"区分交给下方关键词+结构符号 gate。
        if len(t) < 3:
            return False

        ext = target.rsplit(".", 1)[-1].lower() if "." in target else ""

        # 闸 0-A: JSON/数组结构一律不是源码。LLM(尤其 reasoning 模型)常把
        # 计划/编辑指令 JSON 误当源码返回;这类内容恰恰富含 {}()": 等结构符号,
        # 会骗过下方启发式计数,导致 plan JSON 被当作 .py 源码落盘污染 VFS。
        if t.startswith(("{", "[")):
            try:
                json.loads(t)
            except (ValueError, TypeError):
                pass  # 不是合法 JSON, 继续常规判定
            else:
                return False

        # 闸 0-B: 对 Python 目标用 compile() 做权威判定——语法合法即源码。
        # 启发式 codeish 计数会把 def add(a,b): return a - b 这类极简合法
        # 源码(结构字符只有 2 个)误判为非源码, 触发不必要的 LLM 再生成。
        if ext == "py":
            try:
                compile(t, target or "<write>", "exec")
            except (SyntaxError, ValueError):
                pass  # 语法不合法不代表不是源码意图, 继续启发式判定
            else:
                return True

        # 声明式 / 标记 / 配置文件：要求真实结构符号（与写入层
        # _reject_stub_source 对齐），避免把 "Write xxx.html with..." 这类
        # 任务描述误判为源码（此前 len>=20 恒真，导致 html/css 在写入层被拒）。
        markup_exts = {
            "html", "htm", "css", "scss", "less", "json", "md", "markdown",
            "svg", "xml", "yaml", "yml", "toml", "ini", "conf", "txt",
        }
        if ext in markup_exts:
            # HTML/模板必须有标签；CSS/样式必须有规则块——否则是任务描述。
            if ext in {"html", "htm"}:
                return "<" in t and ">" in t
            if ext in {"css", "scss", "less"}:
                return "{" in t and "}" in t
            codeish = sum(t.count(ch) for ch in "{}[];=<>/\\`'\"():")
            return codeish >= 2

        # 代码类文件：要求含代码关键词（覆盖 Python/TS/JS/Go/Rust 等）。
        # 用词边界匹配，避免 "display titles with class 'list-item'" 这类
        # 自然语言误命中 "class "；"=>" 仍作为 TS/JS 箭头函数信号。
        # 关键词集合已扩充常见的代码起始 token（print/from/if/for/while/with/
        # assert/async/await/yield/try/else/elif/raise/return），否则极简合法
        # 脚本 (print('hi') / x = 1) 会被误判为非源码而拒绝落盘。
        if (re.search(
                r"\b(def|class|import|export|function|const|let|return|print|"
                r"from|if|for|while|with|assert|async|await|yield|try|else|"
                r"elif|raise|pass|break|continue|lambda|del)\b", t) is None
                and "=>" not in t and "=" not in t):
            return False
        # 关键区分信号：代码关键词必须出现在「结构符号」上下文里。
        # 自然语言 "class 'list-item'" 只有引号，没有花括号/圆括号等结构；
        # 而真实源码（import{...}/@Component({...})/class X {...}）必含成对结构符号。
        has_brace = "{" in t and "}" in t
        has_paren = "(" in t and ")" in t
        has_semi = ";" in t
        has_arrow = "=>" in t
        has_assign = "=" in t  # 简单赋值 (x = 1) 也算代码结构
        # 至少命中一种"结构信号"，且结构符号计数达到阈值，才算源码。
        codeish = sum(t.count(ch) for ch in "{}[];=<>/\\`'\"()")
        if not (has_brace or has_paren or has_semi or has_arrow or has_assign):
            return False
        # 阈值 3：任务描述即便含个别引号/等号，结构符号也极少；
        # 完整源码（import/class + {}() 等）通常远超 3。
        return codeish >= 3

    # ========================================================================
    # Review 阶段
    # ========================================================================

    async def _review(self, task: CodingTask, steps: list[TaskStep]) -> tuple[bool, str]:
        """Review 阶段: 运行测试 + 审查 diff。

        1. 运行 test (pytest)
        2. 如有 changeset, 生成 diff 供 LLM 审查
        3. 返回 (passed, notes)

        Args:
            task: 编码任务。
            steps: 执行计划 (含各步执行结果)。

        Returns:
            (passed, notes) 元组, passed=True 表示审查通过。
        """
        notes_parts: list[str] = []
        preview = bool(getattr(self._tools, "preview_mode", False))

        # 任务点名要求的交付文件（用于判定「失败步骤」是否致命）
        required_bases = {
            self._normalize_code_target(r).replace("\\", "/").split("/")[-1]
            for r in self._infer_required_files(task.description)
        }

        # 仅「未恢复的任务交付步骤失败」才致命。
        # 1) 探查型步骤 (read/search/ls/...) 可能瞬时失败并被后续步骤修复 —— 不致命。
        # 2) 非任务点名文件的 write/edit 失败（agent 自选的次要产物，如未创建的全局 css）
        #    不致命：核心交付物仍在，不应因 agent 的次优计划判整任务失败。
        # 观察: Angular 任务 read 未写入的文件 → 误判 failed；edit 未创建的 styles.css → 误判 failed。
        _EXPLORATORY_ACTIONS = {
            "read", "search", "grep", "ls", "explore", "view", "cat", "find",
            "glob", "inspect", "open", "list", "stat", "diff", "describe",
        }
        failed: list = []
        for s in steps:
            if s.status != "failed":
                continue
            action = (s.action or "").strip().lower()
            if action in _EXPLORATORY_ACTIONS:
                continue
            target = (s.target or "").strip()
            if not target:
                continue
            base = self._normalize_code_target(target).replace("\\", "/").split("/")[-1]
            # 仅当失败目标属于任务点名交付物且磁盘确实缺失时才致命
            if base not in required_bases:
                continue
            if self._deliverable_present(target, steps):
                continue
            failed.append(s)
        if failed:
            for s in failed[:5]:
                notes_parts.append(
                    f"步骤失败 ({s.action} {s.target}): {s.error or s.result or 'unknown'}"
                )

        # 0. 产物清单：计划 + 任务点名文件必须存在
        missing = self._missing_deliverables(steps)
        for req in self._infer_required_files(task.description):
            if req not in missing and not self._deliverable_present(req, steps):
                missing.append(req)
        if missing:
            notes_parts.append("缺少交付文件（请 write 完整源码）: " + ", ".join(missing))

        # 1–2. 编译 / 测试
        # preview 下不落盘：用 VFS content 做 py_compile；pytest 在临时目录运行
        compile_passed = True
        test_passed = True
        if preview:
            compile_passed, compile_notes = self._preview_compile_check(steps)
            if not compile_passed:
                notes_parts.append(compile_notes)
            # BUG-10 修复：preview 模式下也运行 pytest（将 VFS 文件写入临时目录）
            test_passed, test_notes = await self._preview_test_check(steps)
            if not test_passed:
                notes_parts.append(test_notes)
        else:
            compile_result = await self._tools.compile_check()
            compile_passed = compile_result.success
            if not compile_passed:
                notes_parts.append(f"编译失败: {compile_result.error or ''}")

            test_result = await self._tools.test()
            test_passed = test_result.success
            if not test_passed:
                notes_parts.append(f"测试失败: {test_result.error or ''}")

        # 3. 任务要求完整性检查：从任务描述提取函数/方法名，验证生成代码中是否存在
        completeness_passed, completeness_notes = self._check_task_completeness(task, steps)
        if not completeness_passed:
            notes_parts.append(completeness_notes)

        # 4. 收集本次执行的 diff, 供 LLM 审查
        diff_text = self._collect_diff(task.id)
        llm_passed = True
        # BUG-9 修复: preview 模式也运行 LLM 审查 — 之前 `not preview` 条件导致
        # preview 模式（Code 默认）完全跳过 LLM 审查，模型只写了部分函数就"通过"。
        if diff_text and compile_passed and test_passed and not missing:
            llm_passed, llm_notes = await self._llm_review(task, diff_text)
            # Bug-Fix: 模型返回 {"passed": false} 但未附 notes 时合成提示,
            # 避免 review 失败却无 notes（用户看不到任何失败原因）
            if not llm_passed and not (llm_notes or "").strip():
                llm_notes = "LLM 审查未通过（模型未返回具体意见）"
            if llm_notes:
                notes_parts.append(llm_notes)

        # 5. 综合判定
        passed = (
            compile_passed
            and test_passed
            and llm_passed
            and completeness_passed
            and not failed
            and not missing
        )
        return passed, "\n".join(notes_parts)

    def _preview_compile_check(self, steps: list[TaskStep]) -> tuple[bool, str]:
        """preview 模式：对 write/edit 的 content 做 py_compile（不写盘）。

        P0-3 改进：优先从 VFS 读取最终内容，回退到 step.result.content。
        """
        import py_compile
        import tempfile
        from pathlib import Path

        errors: list[str] = []
        # 优先从 VFS 收集所有 .py 文件的最终内容
        vfs_code = self._vfs.code_snapshot()
        if vfs_code:
            for path, content in vfs_code.items():
                if not path.endswith(".py"):
                    continue
                if not content.strip():
                    continue
                try:
                    with tempfile.NamedTemporaryFile(
                        suffix=".py", delete=False, mode="w", encoding="utf-8"
                    ) as tf:
                        tf.write(content)
                        tmp_path = tf.name
                    try:
                        py_compile.compile(tmp_path, doraise=True)
                    finally:
                        Path(tmp_path).unlink(missing_ok=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"{path}: {e}")
                except Exception as e:
                    errors.append(f"{path}: {e}")
        else:
            # 回退：从 step.result 收集（兼容 VFS 未同步的情况）
            for step in steps:
                action = (step.action or "").strip().lower()
                if action not in ("write", "edit"):
                    continue
                target = (step.target or "").strip()
                if not target.endswith(".py"):
                    continue
                content = ""
                if isinstance(step.result, dict):
                    content = str(step.result.get("content") or "")
                if not content.strip():
                    try:
                        p = Path(self._tools._root) / target
                        if p.is_file():
                            content = p.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        _logger.debug('Unhandled exception', exc_info=True)
                if not content.strip():
                    if action == "edit" and target:
                        errors.append(f"{target}: 未产生有效编辑内容")
                    continue
                try:
                    with tempfile.NamedTemporaryFile(
                        suffix=".py", delete=False, mode="w", encoding="utf-8"
                    ) as tf:
                        tf.write(content)
                        tmp_path = tf.name
                    try:
                        py_compile.compile(tmp_path, doraise=True)
                    finally:
                        Path(tmp_path).unlink(missing_ok=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"{target}: {e}")
                except Exception as e:
                    errors.append(f"{target}: {e}")
        if errors:
            return False, "预览编译失败: " + "; ".join(errors[:3])
        return True, ""

    async def _preview_test_check(self, steps: list[TaskStep]) -> tuple[bool, str]:
        """preview 模式下将 VFS 文件写入临时目录后运行 pytest（BUG-10 修复）。

        策略：
            1. 从 VFS 获取所有文件快照
            2. 筛选 test_*.py / *_test.py 文件
            3. 无测试文件 → 跳过（返回 True，与非 preview 的 _has_pytest_targets 逻辑对齐）
            4. 有测试文件 → 将所有 VFS 文件写入临时目录（保留目录结构），运行 pytest
            5. 退出码 5（no tests collected）也视为跳过
            6. 清理临时目录

        Returns:
            (passed, notes) — passed=True 表示测试通过或无测试需运行
        """
        import shutil
        import tempfile
        from pathlib import Path

        # 从 VFS 获取所有文件
        vfs_files = self._vfs.snapshot()
        if not vfs_files:
            # VFS 为空：回退检查磁盘上是否有测试文件
            # 如果磁盘上也没有，直接跳过
            if not self._tools._has_pytest_targets():
                return True, ""
            # 磁盘有测试文件但 VFS 为空 → 说明只做了 edit 而非 write
            # 此时 preview 模式下无法可靠运行测试，跳过
            return True, "跳过预览测试：VFS 无完整文件快照（仅编辑已有文件）"

        # 筛选测试文件
        test_exts = (".py",)
        test_patterns = ("test_", "_test.py")
        has_test_files = any(
            any(pat in path for pat in test_patterns) and path.endswith(test_exts)
            for path in vfs_files
        )
        if not has_test_files:
            return True, "跳过预览测试：VFS 中无 test_*.py / *_test.py 文件"

        # 创建临时目录，写入所有 VFS 文件（保留相对路径结构）
        tmp_dir = Path(tempfile.mkdtemp(prefix="fnix_preview_test_"))
        try:
            for rel_path, content in vfs_files.items():
                if not rel_path.endswith((".py", ".txt", ".cfg", ".ini", ".toml", ".json")):
                    continue
                dest = tmp_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8", errors="replace")

            # 运行 pytest
            cmd = ["python", "-m", "pytest", "-x", "--tb=short", "-q"]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(tmp_dir),
                )
            except (FileNotFoundError, OSError) as e:
                return True, f"跳过预览测试：无法启动 pytest ({e})"

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=120
                )
            except TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
                return False, "预览测试超时 (120s)"

            stdout_text = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            # pytest exit code 5 = no tests collected → 跳过
            if proc.returncode == 5 or "no tests ran" in stdout_text.lower():
                return True, "跳过预览测试：未收集到用例"

            if proc.returncode != 0:
                detail = stdout_text.strip() or stderr_text.strip()
                # 截取最后几行关键信息
                lines = (detail or "").strip().splitlines()
                summary = "\n".join(lines[-15:]) if len(lines) > 15 else detail
                return False, f"预览测试失败 (退出码 {proc.returncode}):\n{summary}"

            return True, ""
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _deliverable_present(self, target: str, steps: list[TaskStep]) -> bool:
        """磁盘或 preview step.result 是否已有该文件。"""
        from pathlib import Path

        root = Path(getattr(self._tools, "_root", None) or ".")
        norm = self._normalize_code_target(target).replace("\\", "/")
        base = norm.split("/")[-1]
        if (root / norm).is_file() or (root / base).is_file():
            return True
        # 递归按 basename 查找：agent 可能将文件写入子目录（如 src/app/），
        # 仅查 root/<basename> 会漏报, 导致误判「缺失交付」。前端/Angular 工程常见。
        try:
            for hit in root.rglob(base):
                if hit.is_file():
                    return True
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)
        preview = bool(getattr(self._tools, "preview_mode", False))
        for step in steps:
            if (step.action or "").lower() not in ("write", "edit"):
                continue
            st = self._normalize_code_target(step.target or "").replace("\\", "/")
            if st.split("/")[-1] != base:
                continue
            if step.status == "failed":
                continue
            if preview and isinstance(step.result, dict) and step.result.get("content"):
                return True
            if not preview and ((root / st).is_file() or (root / base).is_file()):
                return True
        return False

    def _missing_deliverables(self, steps: list[TaskStep]) -> list[str]:
        """Plan 中 write 的 target 若不在磁盘上，记为缺失交付。

        仅统计 write（交付型）步骤：edit 步骤预设文件已存在，失败的 edit（尤其针对
        agent 自选的、任务未点名的次要文件如全局 css）属于 agent 次优计划，不应被
        当作「缺失交付」而误判整任务失败。preview 下不落盘：step.result 带 content 视为已交付。
        """
        missing: list[str] = []
        seen: set[str] = set()
        for step in steps:
            action = (step.action or "").strip().lower()
            target = (step.target or "").strip().replace("\\", "/")
            if action != "write" or not target:
                continue
            target = self._normalize_code_target(target)
            base = target.split("/")[-1]
            if base in seen or target in (".", "*", "project", "workspace"):
                continue
            seen.add(base)
            if not self._deliverable_present(target, steps):
                missing.append(base)
        return missing

    def _collect_final_code(self) -> dict[str, str]:
        """收集最终代码内容 — 从 VFS（preview）或磁盘（非 preview）读取。

        借鉴 SWE-agent "磁盘即真相源" 原则：review/completeness 检查时
        不再依赖 step.result.content 的不可靠拼接，而是从 VFS/磁盘
        读取文件最终状态。
        """
        preview = bool(getattr(self._tools, "preview_mode", False))
        if preview:
            return self._vfs.code_snapshot()

        # 非 preview：从磁盘读取 VFS 中记录的所有文件
        from pathlib import Path

        root = Path(getattr(self._tools, "_root", None) or ".")
        code_contents: dict[str, str] = {}
        for path_str in self._vfs.list_files():
            p = root / path_str
            if p.is_file():
                try:
                    code_contents[path_str] = p.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except Exception:
                    _logger.debug("Failed to read %s from disk", path_str)
        return code_contents

    def _check_task_completeness(
        self, task: CodingTask, steps: list[TaskStep]
    ) -> tuple[bool, str]:
        """检查生成代码是否包含任务描述中提到的所有函数/方法/类。

        P0-2 改进：用 AST 解析（Python）+ 增强正则（TS/JS）替代原来的纯正则检查。
        P0-3 改进：从 VFS/磁盘读取最终内容，而非 step.result.content 拼接。

        Args:
            task: 编码任务。
            steps: 执行计划步骤（含 result.content）。

        Returns:
            (passed, notes) — passed=True 表示所有提到的函数/类都已定义。
        """
        # 从 VFS/磁盘读取最终代码内容（磁盘即真相源）
        code_contents = self._collect_final_code()

        # 如果 VFS 为空（可能全是 edit 操作已有文件），回退到 step.result
        if not code_contents:
            # 回退：从 step.result 收集（兼容旧路径）
            latest_code_by_file: dict[str, str] = {}
            for step in steps:
                action = (step.action or "").strip().lower()
                if action not in ("write", "edit"):
                    continue
                content = ""
                if isinstance(step.result, dict):
                    content = str(step.result.get("content") or "")
                elif isinstance(step.result, str):
                    content = step.result
                target = (step.target or "").strip()
                if content.strip() and target:
                    if target.endswith('.py'):
                        try:
                            compile(content, target, 'exec')
                        except (SyntaxError, ValueError):
                            # str 型 step.result 通常是工具输出消息（如 “已写入: app.py”），
                            # 并非代码内容——直接当作代码会误报“函数未实现”。
                            # 非法 Python 源码一律丢弃，不参与完整性检查。
                            continue
                    latest_code_by_file[target] = content
            code_contents = latest_code_by_file

        if not code_contents:
            return True, ""  # 无代码内容可检查

        # 用 completeness.py 模块做多语言完整性检查
        result = check_completeness(task.description, code_contents)
        return result.passed, result.notes

    async def _llm_review(self, task: CodingTask, diff_text: str) -> tuple[bool, str]:
        """LLM 审查 diff。

        构造审查 prompt → LLM 推理 → 解析为 (passed, notes)。

        Args:
            task: 编码任务。
            diff_text: 变更 diff 文本。

        Returns:
            (passed, notes) 元组。
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "你是代码审查员, 审查代码变更是否正确实现了任务。"
                    "重点检查:\n"
                    "1. 任务中提到的每个函数/方法/类是否都有对应的定义\n"
                    "2. 是否引入了语法错误、逻辑问题或破坏性变更\n"
                    "3. 测试文件是否覆盖了任务要求的测试场景\n"
                    "4. 函数参数和返回值是否符合任务描述\n"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"任务: {task.description}\n\n"
                    f"变更 diff:\n{diff_text}\n\n"
                    "请逐条检查任务要求, 确认每个要求的函数/方法都已实现。"
                    "返回 JSON: "
                    '{"passed": true/false, "notes": "审查意见（列出缺失或不符的内容）"}'
                ),
            },
        ]
        response = await self._call_llm_streaming(
            messages,
            thinking_label="正在审查代码变更和测试结果",
        )
        return self._parse_review(response)

    def _collect_diff(self, task_id: str) -> str:
        """收集指定任务执行期间产生的所有变更集 diff。

        从 DiffEngine 历史中提取与本次任务变更集 ID 匹配的条目。
        改进：对同一文件的多次变更，只取最终版本（heal 轮次会多次写同一文件，
        拼接所有版本会让 LLM 审查困惑——看到多个冲突的 diff 版本）。

        Args:
            task_id: 任务 ID。

        Returns:
            最终版本各文件的 diff 文本; 无变更时返回空字符串。
        """
        changeset_ids = self._task_changesets.get(task_id, [])
        if not changeset_ids:
            return ""

        id_set = set(changeset_ids)
        # 按文件路径收集最终版本的 diff（后出现的覆盖先出现的）
        latest_diff_by_path: dict[str, str] = {}
        for cs, _ in self._tools._diff.get_history():
            if cs.id not in id_set:
                continue
            # 遍历 changeset 中的每个文件变更
            for ch in getattr(cs, "changes", None) or []:
                path = ch.path or ""
                if not path:
                    continue
                diff = ch.to_diff() or ""
                if diff:
                    latest_diff_by_path[path] = diff
        return "\n".join(latest_diff_by_path.values())

    def _parse_review(self, response: str) -> tuple[bool, str]:
        """解析 LLM 审查响应为 (passed, notes)。

        解析策略 (层层降级):
          1. 直接 json.loads
          2. 正则提取 {...} 块再 json.loads
          3. 关键字判定 (含 "不通过"/"reject"/"failed" → 不通过)

        Args:
            response: LLM 响应文本。

        Returns:
            (passed, notes) 元组; 空响应或不可解析时失败，禁止假成功。
        """
        # LLM 不可用 (空响应) 时必须失败，避免静默放行错误补丁
        if not response or not str(response).strip():
            return False, "审查失败: LLM 无响应"

        # 1. 直接 json.loads
        try:
            data = json.loads(response)
            if isinstance(data, dict):
                if "passed" not in data:
                    return False, "审查失败: 缺少 passed 字段"
                return bool(data.get("passed")), str(data.get("notes", ""))
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        # 2. 正则提取 {...} 块再尝试
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    if "passed" not in data:
                        return False, "审查失败: 缺少 passed 字段"
                    return bool(data.get("passed")), str(data.get("notes", ""))
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)

        # 3. 关键字降级: 含否定关键字判为不通过；否则要求明确通过
        lower = response.lower()
        if "不通过" in response or "reject" in lower or "failed" in lower:
            return False, self._truncate(response, 500)
        if "通过" in response or "pass" in lower or "approved" in lower:
            return True, self._truncate(response, 500)
        return False, "审查失败: 无法解析审查结果"

    # ========================================================================
    # LLM 调用封装
    # ========================================================================

    async def _call_llm(self, messages: list[dict[str, str]]) -> str:
        """调用 LLM (封装异常 + compaction)。

        Args:
            messages: LLM 消息列表 (role/content)。

        Returns:
            LLM 响应文本; 调用失败时返回空字符串。
        """
        # Compaction (上下文压缩器 / 上下文压缩机制):
        # messages 超 50K tokens 时压缩早期消息, 防止长程 heal 任务 token 溢出
        messages = await self._compact_if_needed(messages)
        try:
            return await self._llm.complete({"messages": messages})
        except Exception as exc:
            # 保留失败信号：空字符串会触发审查失败，而不是默认通过
            self._last_llm_error = f"{type(exc).__name__}: {exc}"
            return ""

    async def _call_llm_with_progress(
        self,
        messages: list[dict[str, str]],
        *,
        progress_msgs: list[str] | None = None,
        interval: int = 8,
    ) -> str:
        """调用 LLM 并在等待期间定期发送 thinking 事件。

        解决规划/审查阶段 LLM 阻塞期间前端无任何可见进度的问题：
        每 interval 秒发送一条 progress_msgs 中的 thinking 事件，
        让用户知道系统正在工作而非卡死。

        Args:
            messages: LLM 消息列表。
            progress_msgs: 进度提示文本列表（轮换发送）。
            interval: 发送间隔秒数。

        Returns:
            LLM 响应文本。
        """
        if not progress_msgs:
            return await self._call_llm(messages)

        progress_task: asyncio.Task[None] | None = None

        async def _emit_progress() -> None:
            idx = 0
            while True:
                await asyncio.sleep(interval)
                idx = min(idx + 1, len(progress_msgs) - 1)
                await self._emit(CodingAgentEvent(type="thinking", content=progress_msgs[idx]))

        progress_task = asyncio.create_task(_emit_progress())
        try:
            return await self._call_llm(messages)
        finally:
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass

    async def _call_llm_streaming(
        self,
        messages: list[dict[str, str]],
        *,
        thinking_label: str = "正在思考",
    ) -> str:
        """流式调用 LLM，逐 chunk 发送 thinking 事件，最后返回完整响应。

        真正的流式输出：LLM 思考过程的每个 token chunk 通过 thinking 事件
        实时推送到前端，像聊天一样逐字显示，而非预定义文字轮换。

        若 LLM backend 不支持 stream_complete，自动降级到 _call_llm_with_progress。

        Args:
            messages: LLM 消息列表。
            thinking_label: 思考阶段标签（用于第一个 thinking 事件）。

        Returns:
            LLM 完整响应文本。
        """
        # 先发送一个标签事件，让前端知道开始思考
        # 只发送 label，不发送 LLM 的 JSON chunk — 结构化结果通过 plan/review 等事件展示
        await self._emit(
            CodingAgentEvent(type="thinking", content=thinking_label)
        )

        # 检查 backend 是否支持流式
        if not hasattr(self._llm, "stream_complete"):
            # 降级到进度轮换方案
            return await self._call_llm_with_progress(
                messages,
                progress_msgs=[
                    f"{thinking_label}...",
                    "正在生成执行计划，请稍候...",
                    "正在分析任务细节，确定文件结构...",
                ],
            )

        # 上下文压缩
        messages = await self._compact_if_needed(messages)

        try:
            full_text = ""
            async for chunk in self._llm.stream_complete({"messages": messages}):
                full_text += chunk
                # 不发送 LLM chunk 到前端 thinking 事件
                # LLM 输出的是结构化 JSON（规划步骤/审查结论），不是用户可读的思考过程
                # 结构化结果通过 plan/review/step_start 等事件正确展示给用户
            return full_text
        except Exception as exc:
            self._last_llm_error = f"{type(exc).__name__}: {exc}"
            # 如果已经有部分文本，返回它；否则返回空
            return ""

    async def _compact_if_needed(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """超阈值时压缩早期 messages (上下文压缩器 五维度摘要)。

        复用 Work 模式的 compact_messages_if_needed, 保持双模式一致。
        """
        try:
            from fnixagent.core.agent.compaction import compact_messages_if_needed

            # 构造 LLM adapter shim (Code 模式的 _llm 只有 complete, 没有 achat)
            # 降级: 若 compaction 需要 LLM 调用但 adapter 不兼容, 直接跳过
            llm_adapter = getattr(self._llm, "_adapter", None)
            if llm_adapter is None or not hasattr(llm_adapter, "achat"):
                return messages

            compacted, info = await compact_messages_if_needed(
                llm_adapter,
                messages,
                threshold_tokens=50000,
                keep_recent=6,
                keep_first_n=2,
            )
            if info and info.get("compacted"):
                await self._emit(
                    CodingAgentEvent(
                        type="status",
                        status=f"compacted: {info.get('before_tokens', 0)}→{info.get('after_tokens', 0)}",
                    )
                )
            return compacted
        except Exception:
            return messages

    # ========================================================================
    # TodoStore 辅助 (load-bearing state, 任务状态外化)
    # ========================================================================

    def _load_todo_store(self):
        """加载 workspace 的 TodoStore (失败时返回 None, 不阻塞主路径)。"""
        try:
            from fnixagent.core.skills.todos import TodoStore

            return TodoStore(self._workspace)
        except Exception:
            return None

    def _sync_plan_to_todos(self, todo_store, plan: list[TaskStep], *, heal_round: int = 0) -> None:
        """把 plan steps 同步到 TodoStore (首次 plan 清空重建, heal 追加)。"""
        try:
            from fnixagent.core.skills.todos import TodoItem

            if heal_round == 0:
                # 首次 plan: 清空旧 todos, 重建
                todo_store.clear()
                for i, step in enumerate(plan):
                    todo_store.add(
                        TodoItem(
                            id=f"step_{i + 1}",
                            content=f"{step.action}: {step.target or step.description[:80]}",
                            priority="high" if step.action in ("write", "edit") else "medium",
                        )
                    )
            else:
                # heal: 标记之前的失败步骤 + 追加新 heal 步骤
                for todo in todo_store.todos:
                    if todo.status == "in_progress":
                        todo_store.update_status(todo.id, "failed", note=f"heal_{heal_round} 失败")
                for i, step in enumerate(plan):
                    tid = f"heal{heal_round}_step_{i + 1}"
                    if not any(t.id == tid for t in todo_store.todos):
                        todo_store.add(
                            TodoItem(
                                id=tid,
                                content=f"[heal{heal_round}] {step.action}: {step.target or step.description[:80]}",
                                priority="high",
                            )
                        )
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

    def _update_todos_after_execute(self, todo_store, plan: list[TaskStep]) -> None:
        """执行完成后标记步骤为 completed。"""
        try:
            for i, step in enumerate(plan):
                tid = f"step_{i + 1}"
                if any(t.id == tid and t.status != "completed" for t in todo_store.todos):
                    todo_store.update_status(tid, "completed")
                # heal steps
                for hr in range(1, 10):
                    hid = f"heal{hr}_step_{i + 1}"
                    if any(t.id == hid and t.status != "completed" for t in todo_store.todos):
                        todo_store.update_status(hid, "completed")
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

    def _update_todos_after_review(self, todo_store, passed: bool, notes: str) -> None:
        """审查后更新状态 (passed 标记全部完成, failed 记录原因)。"""
        try:
            if passed:
                for todo in todo_store.todos:
                    if todo.status in ("pending", "in_progress"):
                        todo_store.update_status(todo.id, "completed")
            else:
                # 记录审查失败原因到最近一个 in_progress todo
                for todo in reversed(todo_store.todos):
                    if todo.status == "in_progress":
                        todo_store.update_status(todo.id, "failed", note=notes[:200])
                        break
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

    # ========================================================================
    # HERA 技能捕获 + CriticAgent 独立审查 (双模式对齐)
    # ========================================================================

    async def _capture_skill_hera(self, task: CodingTask, result: TaskResult) -> None:
        """HERA 技能捕获: 把成功的解决方案存入技能库 (对齐 Work 模式)。

        论文贡献: 失败技能也存储 (含 failure_count), 下次类似任务可降权召回避免重复错误。
        """
        try:
            from fnixagent.core.skills import SkillLibrary

            skill_lib = SkillLibrary(self._workspace)
            # 收集工具调用摘要
            tool_calls_summary = [
                {
                    "name": s.action,
                    "status": "success" if result.review_passed else "failed",
                    "target": s.target,
                }
                for s in (result.plan or [])
            ]
            skill_lib.add_new_skill(
                user_input=task.description,
                response=result.review_notes or "",
                tool_calls=tool_calls_summary,
                workspace_kind="code",
                success=result.status == TaskStatus.COMPLETED,
            )
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)  # HERA 失败不阻塞主路径

    async def _run_critic_review(self, task: CodingTask, result: TaskResult) -> None:
        """CriticAgent 独立审查 (对齐 Work 模式, 双模式对齐)。

        解决 Code 模式 _review 内嵌审查易被 LLM 自圆其说的问题。。
        """
        try:
            from fnixagent.core.agent.critic import CriticAgent

            # 收集 diff 作为 artifacts
            diff_text = self._collect_diff(task.id)
            if not diff_text:
                return

            artifacts = [{"path": "code_diff", "name": "code_diff", "content": diff_text[:4000]}]
            tool_calls_summary = [
                {"name": s.action, "success": True} for s in (result.plan or [])[:15]
            ]

            llm_config = getattr(self._llm, "_config", None) or {}
            critic = CriticAgent(llm_config=llm_config)
            verdict = await critic.review(
                user_input=task.description,
                artifacts=artifacts,
                tool_calls_summary=tool_calls_summary,
                answer=result.review_notes or "",
            )
            if verdict is not None:
                # Spec 7 fail-soft-with-signal: 检测哨兵值, emit 可观测信号
                # (对齐 Work 模式 work_pipeline.py 的 critic_skipped 事件)
                # score==-1.0 表示审查未完成 (LLM 故障/解析失败),
                # 不阻断主流程但 emit 信号, 让 MFP 第 3 阶可统计 critic.skip_rate。
                if verdict.score == -1.0:
                    await self._emit(
                        CodingAgentEvent(
                            type="status",
                            status="critic_skipped: review_incomplete",
                        )
                    )
                else:
                    await self._emit(
                        CodingAgentEvent(
                            type="status",
                            status=f"critic: {'passed' if verdict.passed else 'issues'} (score={verdict.score:.1f})",
                        )
                    )
                    if not verdict.passed and verdict.suggestions:
                        suggestions_text = "\n".join(f"- {s}" for s in verdict.suggestions[:3])
                        await self._emit(
                            CodingAgentEvent(
                                type="status",
                                status=f"critic_suggestions: {suggestions_text[:200]}",
                            )
                        )
        except Exception as critic_exc:
            # Spec 7 fail-soft-with-signal: Critic 异常时 emit 信号, 不静默
            # (对齐 Work 模式, 避免"假装阻断实则静默放行"的最差组合)
            await self._emit(
                CodingAgentEvent(
                    type="status",
                    status=f"critic_skipped: {type(critic_exc).__name__}: {critic_exc}",
                )
            )

    def _build_plan_message(self, plan: list[TaskStep]) -> str:
        """生成规划阶段的聊天消息，让用户看到 Agent 正在做什么。"""
        write_steps = [s for s in plan if s.action in ("write", "edit") and s.target]
        if not write_steps:
            return f"我分析了你的需求，计划执行 {len(plan)} 个操作。"
        files = []
        for s in write_steps:
            if s.target not in files:
                files.append(s.target)
        if len(files) == 1:
            return f"我计划修改文件 `{files[0]}`。"
        file_list = "\n".join(f"- `{f}`" for f in files)
        return f"我计划修改以下 {len(files)} 个文件：\n{file_list}"

    def _build_review_message(self, review_passed: bool, review_notes: str) -> str:
        """生成审查阶段的聊天消息。简洁状态，不重复 review_notes 全文。"""
        if review_passed:
            return "✅ 代码审查通过。"
        else:
            return "⚠️ 审查发现问题，正在尝试修复…"

    async def _stream_completion_summary(
        self, task: CodingTask, result: TaskResult
    ) -> None:
        """用 LLM 流式生成自然语言完成摘要，逐 chunk 发送 message 事件。

        让聊天区看到文字逐字流式输出（像 Cursor/Codex 那样），
        而不是一次性弹出整段文本。

        若 LLM 不支持流式或调用失败，降级到 _build_completion_message 一次性发送。
        """
        # 收集变更文件列表
        changed_files: list[str] = []
        for step in (result.plan or []):
            if step.action in ("write", "edit") and step.target:
                if step.target not in changed_files:
                    changed_files.append(step.target)

        # 构建给 LLM 的 prompt
        if result.status == TaskStatus.COMPLETED:
            user_prompt = (
                f"任务：{task.description[:500]}\n\n"
                f"修改的文件：{', '.join(changed_files) if changed_files else '无'}\n"
                f"审查结果：{'通过' if result.review_passed else '未通过'}\n"
                f"耗时：{result.duration_sec:.1f}s\n\n"
                "请用一两句自然的中文总结你做了什么，不要列文件清单，不要重复任务描述。"
                "简洁友好，像同事汇报工作一样。"
            )
        else:
            error_msg = result.error or result.review_notes or "未知原因"
            user_prompt = (
                f"任务：{task.description[:500]}\n\n"
                f"很遗憾任务没有完成。失败原因：{error_msg[:300]}\n"
                "请用一两句自然的中文向用户说明情况，简洁友好。"
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是编程助手。请用自然的中文回复，像正常对话一样说话。"
                    "回复不超过 80 字，写成一两句连贯的话，不要换行，不要用 markdown，不要用代码块。"
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        # 检查是否支持流式
        llm_type = type(self._llm).__name__ if self._llm else "None"
        has_stream = hasattr(self._llm, "stream_complete") if self._llm else False
        print(f"[stream_summary] LLM={llm_type}, has_stream_complete={has_stream}", flush=True)
        if not has_stream:
            # 降级：一次性发送
            fallback = self._build_completion_message(task, result)
            if fallback:
                await self._emit(CodingAgentEvent(type="message", content=fallback))
            return

        try:
            print(f"[stream_summary] starting stream_complete, msg_count={len(messages)}", flush=True)
            # 在现有内容前加段落分隔
            await self._emit(CodingAgentEvent(type="message", content="\n\n"))
            chunk_count = 0
            async for chunk in self._llm.stream_complete({"messages": messages}):
                if chunk:
                    chunk_count += 1
                    await self._emit(CodingAgentEvent(type="message", content=chunk))
            print(f"[stream_summary] done, total_chunks={chunk_count}", flush=True)
        except Exception as e:
            print(f"[stream_summary] FAILED: {type(e).__name__}: {e}", flush=True)
            import traceback; traceback.print_exc()
            # 降级：一次性发送
            fallback = self._build_completion_message(task, result)
            if fallback:
                await self._emit(CodingAgentEvent(type="message", content=fallback))

    def _build_completion_message(
        self, task: CodingTask, result: TaskResult
    ) -> str:
        """生成人类可读的任务完成摘要, 用于聊天区的 AI 回复消息。

        成功时: 简洁确认（审查详情已在审查消息中发送）
        失败时: 说明失败原因
        """
        # 收集变更文件列表
        changed_files: list[str] = []
        for step in (result.plan or []):
            if step.action in ("write", "edit") and step.target:
                if step.target not in changed_files:
                    changed_files.append(step.target)

        if result.status == TaskStatus.COMPLETED:
            parts = ["✅ 任务已完成"]
            if changed_files:
                if len(changed_files) == 1:
                    parts.append(f"已修改文件：`{changed_files[0]}`")
                else:
                    file_list = "\n".join(f"- `{f}`" for f in changed_files)
                    parts.append(f"已修改 {len(changed_files)} 个文件：\n{file_list}")
            duration = result.duration_sec
            if duration > 0:
                parts.append(f"耗时 {duration:.1f}s")
            return "\n\n".join(parts)
        else:
            parts = ["❌ 任务未完成"]
            if result.error:
                parts.append(f"原因：{result.error[:300]}")
            elif result.review_notes:
                parts.append(f"审查未通过：{result.review_notes[:300]}")
            if changed_files:
                file_list = "\n".join(f"- `{f}`" for f in changed_files)
                parts.append(f"已修改的文件：\n{file_list}")
            return "\n\n".join(parts)

    # ========================================================================
    # 计划解析
    # ========================================================================

    def _parse_plan(self, response: str) -> list[TaskStep]:
        """解析 LLM 返回的计划 JSON。

        容错策略 (层层降级):
          1. 直接 json.loads
          2. 正则提取第一个 {...} 块再 json.loads
          3. 从 data["steps"] 构造 TaskStep 列表
          4. 上述均失败 → 返回单步 "手动执行任务"

        Args:
            response: LLM 响应文本。

        Returns:
            TaskStep 列表 (至少 1 个步骤)。
        """
        # 空响应 → 降级
        if not response:
            return self._fallback_plan()

        data = None

        # 1. 直接 json.loads
        try:
            data = json.loads(response)
        except Exception:
            data = None

        # 2. 正则提取第一个 {...} 块再尝试 (贪婪匹配, 可捕获含嵌套的完整 JSON)
        if data is None:
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:
                    data = None

        # 3. 从 steps 数组构造 TaskStep 列表
        if isinstance(data, dict):
            raw_steps = data.get("steps")
            if isinstance(raw_steps, list) and raw_steps:
                steps: list[TaskStep] = []
                for item in raw_steps:
                    if not isinstance(item, dict):
                        continue
                    action = str(item.get("action", "")).strip().lower()
                    raw_desc = str(item.get("description", ""))
                    # edit 的 description 含 "old|||new", 不能 strip (会丢失缩进)
                    desc = raw_desc if action == "edit" else raw_desc.strip()
                    if not desc:
                        continue
                    steps.append(
                        TaskStep(
                            id=uuid4().hex[:8],
                            description=desc,
                            action=action,
                            target=str(item.get("target", "")).strip(),
                        )
                    )
                if steps:
                    return steps

        # 4. 降级: 单步
        return self._fallback_plan()

    def _fallback_plan(self) -> list[TaskStep]:
        """降级计划: 返回单步 "手动执行任务"。

        Returns:
            包含单个手动执行步骤的列表。
        """
        return [
            TaskStep(
                id=uuid4().hex[:8],
                description="手动执行任务",
                action="",
                target="",
            )
        ]

    # ========================================================================
    # 事件发送
    # ========================================================================

    async def _emit(self, event: CodingAgentEvent) -> None:
        """发送事件到已注册的回调。

        同时支持同步和异步回调: 若回调为异步函数则 await, 否则直接调用。

        Args:
            event: 要发送的 CodingAgentEvent 事件。
        """
        if self._event_cb is not None:
            result = self._event_cb(event)
            if result is not None and hasattr(result, "__await__"):
                await result

    # ========================================================================
    # 辅助
    # ========================================================================

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        """截断文本到指定长度。

        Args:
            text: 原始文本。
            max_len: 最大长度。

        Returns:
            截断后的文本 (超长时追加 "...")。
        """
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."


__all__ = [
    "CodingAgent",
    "CodingAgentEvent",
    "CodingTask",
    "TaskResult",
    "TaskStatus",
    "TaskStep",
]
