"""
CodingAgent - 编码智能体核心
============================
对标 Codex Plan → Apply 范式和 Trae Agent Mode, 基于 AgentOS 构建编码 Agent。

架构:
    Planner → Executor → Reviewer

底座:
    - AgentOS Process (任务状态机)
    - DiffEngine (原子多文件编辑)
    - CodeTools (read/write/edit/search/git/test)
    - ContextBuilder (上下文工程)

执行流程:
    1. PLAN:     LLM 分析任务 → 分解为 TaskStep 列表
    2. EXECUTE:  按计划调用 CodeTools (read/edit/write/test), 写操作经 DiffEngine 原子应用
    3. REVIEW:   运行 pytest + LLM 审查 diff
    4. 任一步失败 → 返回 FAILED

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
from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4

from fnixagent.core.agent.types import utcnow_iso


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
    action: str = ""          # 具体操作 (read/write/edit/test 等)
    target: str = ""          # 目标文件
    status: str = "pending"   # pending/done/failed/skipped
    result: str = ""
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
    review_passed: bool | None = None
    review_notes: str | None = None
    result: TaskResult | None = None


# ============================================================================
# 编码智能体
# ============================================================================

class CodingAgent:
    """编码智能体 (对标 Codex/Trae Agent Mode)。

    架构: Planner → Executor → Reviewer
    底座: AgentOS Process + DiffEngine + CodeTools

    支持两种执行模式:
      - execute_task(): 同步执行, 返回 TaskResult
      - streaming_execute(): 流式执行, 逐步产出 CodingAgentEvent 事件

    Usage:
        agent = CodingAgent(code_tools, context_builder, llm_backend)
        result = await agent.execute_task("为 AgentKernel 添加 health_check 方法")
    """

    def __init__(self, code_tools, context_builder, llm_backend):
        """初始化编码智能体。

        Args:
            code_tools: CodeTools 实例 (提供 read/write/edit/search/git/test)。
            context_builder: ContextBuilder 实例 (提供 build_context)。
            llm_backend: LLMBackend 实例 (提供 complete 方法)。
        """
        self._tools = code_tools
        self._ctx_builder = context_builder
        self._llm = llm_backend
        # 活跃任务表 (task_id -> CodingTask)
        self._active_tasks: dict[str, CodingTask] = {}
        # 每个任务执行期间产生的变更集 ID 列表 (task_id -> [changeset_id])
        # 用于 Review 阶段收集 diff (CodeTools 的写操作不返回 changeset_id, 只能从 DiffEngine 历史提取)
        self._task_changesets: dict[str, list[str]] = {}
        # 事件回调 (流式执行时由 streaming_execute / execute_task 设置)
        self._event_cb: Callable[[CodingAgentEvent], Any] | None = None

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
        self._event_cb = on_event
        start_time = time.perf_counter()

        plan: list[TaskStep] = []
        changeset_id: str | None = None
        review_passed = False
        review_notes = ""
        error: str | None = None
        status = TaskStatus.PENDING

        try:
            # 1. PLAN: 生成执行计划
            status = TaskStatus.PLANNING
            await self._emit(CodingAgentEvent(type="status", status="planning"))
            plan = await self._plan(task)
            await self._emit(CodingAgentEvent(
                type="plan",
                steps=[{
                    "id": s.id, "description": s.description,
                    "action": s.action, "target": s.target,
                } for s in plan],
            ))

            # 2. EXECUTE: 按计划执行
            status = TaskStatus.EXECUTING
            await self._emit(CodingAgentEvent(type="status", status="executing"))
            changeset_id = await self._execute(task, plan)

            # 3. REVIEW: 测试 + diff 审查
            status = TaskStatus.REVIEWING
            await self._emit(CodingAgentEvent(type="status", status="reviewing"))
            review_passed, review_notes = await self._review(task, plan)
            await self._emit(CodingAgentEvent(
                type="review", review_passed=review_passed, review_notes=review_notes,
            ))

            # 审查未通过视为失败
            if not review_passed:
                status = TaskStatus.FAILED
                error = review_notes or "审查未通过"
            else:
                status = TaskStatus.COMPLETED

        except RuntimeError as exc:
            status = TaskStatus.FAILED
            error = str(exc)
        except Exception as exc:  # noqa: BLE001
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

        await self._emit(CodingAgentEvent(
            type="status", status=status.value,
        ))
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
                # 1. PLAN
                status = TaskStatus.PLANNING
                await self._emit(CodingAgentEvent(type="status", status="planning"))
                plan = await self._plan(task)
                await self._emit(CodingAgentEvent(
                    type="plan",
                    steps=[{
                        "id": s.id, "description": s.description,
                        "action": s.action, "target": s.target,
                    } for s in plan],
                ))

                # 2. EXECUTE
                status = TaskStatus.EXECUTING
                await self._emit(CodingAgentEvent(type="status", status="executing"))
                changeset_id = await self._execute(task, plan)

                # 3. REVIEW
                status = TaskStatus.REVIEWING
                await self._emit(CodingAgentEvent(type="status", status="reviewing"))
                review_passed, review_notes = await self._review(task, plan)
                await self._emit(CodingAgentEvent(
                    type="review", review_passed=review_passed,
                    review_notes=review_notes,
                ))

                if not review_passed:
                    status = TaskStatus.FAILED
                    error = review_notes or "审查未通过"
                else:
                    status = TaskStatus.COMPLETED

            except RuntimeError as exc:
                status = TaskStatus.FAILED
                error = str(exc)
            except Exception as exc:  # noqa: BLE001
                status = TaskStatus.FAILED
                error = f"未预期错误: {type(exc).__name__}: {exc}"
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

            await self._emit(CodingAgentEvent(
                type="status", status=status.value,
            ))
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
    # Plan 阶段
    # ========================================================================

    async def _plan(self, task: CodingTask) -> list[TaskStep]:
        """Plan 阶段: LLM 生成执行计划。

        构造上下文 (ContextBuilder.build_context) → LLM 推理 → 解析为 TaskStep 列表。
        LLM 应返回 JSON 格式:
        {"steps": [{"description": "...", "action": "read|edit|write|test", "target": "path"}]}

        解析失败时返回单步 "手动执行任务"。

        Args:
            task: 编码任务。

        Returns:
            TaskStep 列表 (至少 1 个步骤)。
        """
        # 构造上下文 (系统提示指定为计划生成器角色)
        ctx = await self._ctx_builder.build_context(
            task.description,
            system_prompt="你是编码计划生成器, 将任务分解为具体步骤, 返回 JSON",
        )
        messages = list(ctx.messages)

        # 追加输出格式指令 + 任务补充信息
        instruction_lines: list[str] = [
            "请将上述任务分解为具体执行步骤, 返回 JSON 格式:",
            '{"steps": [{"description": "步骤描述", "action": "read|edit|write|test", "target": "文件路径"}]}',
            "只返回 JSON, 不要其他内容。",
        ]
        if task.files:
            instruction_lines.append(f"涉及文件: {', '.join(task.files)}")
        if task.constraints:
            instruction_lines.append(f"约束条件: {'; '.join(task.constraints)}")
        messages.append({
            "role": "user",
            "content": "\n".join(instruction_lines),
        })

        # LLM 推理并解析
        response = await self._call_llm(messages)
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
                await self._emit(CodingAgentEvent(
                    type="step",
                    step={
                        "id": step.id, "description": step.description,
                        "action": step.action, "target": step.target,
                        "status": "running",
                    },
                ))

                # 记录步骤执行前的历史长度, 用于检测文件变更
                step_hist_before = len(self._tools._diff.get_history())

                try:
                    await self._execute_step(step)
                    # _execute_step 未标记 skipped 时视为成功
                    if step.status != "skipped":
                        step.status = "done"
                except Exception as exc:  # noqa: BLE001
                    step.status = "failed"
                    step.error = str(exc)
                    # 发送步骤失败事件
                    await self._emit(CodingAgentEvent(
                        type="step",
                        step={"id": step.id, "status": "failed", "error": str(exc)},
                    ))
                    raise RuntimeError(
                        f"步骤 {step.id} ({step.description[:60]}) 执行失败: {exc}"
                    ) from exc

                # 发送步骤完成事件
                await self._emit(CodingAgentEvent(
                    type="step",
                    step={
                        "id": step.id, "status": step.status,
                        "result": step.result,
                    },
                ))

                # 检测写操作产生的文件变更并发送 file_change 事件
                if step.action in ("write", "edit"):
                    new_history = self._tools._diff.get_history()
                    new_changesets = [
                        (cs, _) for cs, _ in new_history[step_hist_before:]
                    ]
                    for cs, _ in new_changesets:
                        await self._emit(CodingAgentEvent(
                            type="file_change",
                            file_path=step.target,
                            file_action="modify",
                            diff=cs.to_diff(),
                        ))
        finally:
            # 收集本次执行产生的所有变更集 ID (无论成功失败, 便于 Review 阶段取 diff)
            history = self._tools._diff.get_history()
            new_ids = [cs.id for cs, _ in history[hist_before:]]
            self._task_changesets[task.id] = new_ids

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

        if action == "read":
            result = await self._tools.read(step.target)

        elif action == "write":
            # description 作为写入内容
            result = await self._tools.write(step.target, step.description)

        elif action == "edit":
            # description 解析为 (old_text, new_text)
            old_text, new_text = self._parse_edit_payload(step.description)
            result = await self._tools.edit(step.target, old_text, new_text)

        elif action == "test":
            result = await self._tools.test()

        else:
            # 未知 action, 跳过 (不视为失败)
            step.status = "skipped"
            step.result = f"未知 action: {action or '(空)'}"
            return

        # 统一处理工具结果
        if not result.success:
            raise RuntimeError(result.error or f"工具 {action} 执行失败")

        # 记录结果摘要 (截断防止过长)
        step.result = self._truncate(str(result.output), 2000)

    def _parse_edit_payload(self, description: str) -> tuple[str, str]:
        """解析 edit 步骤的 description 为 (old_text, new_text)。

        支持两种格式:
          1. JSON: {"old_text": "...", "new_text": "..."}
          2. 分隔符: "原文|||新文本"

        Args:
            description: edit 步骤的描述字段。

        Returns:
            (old_text, new_text) 元组。

        Raises:
            RuntimeError: 无法解析出 old_text/new_text。
        """
        # 尝试 JSON 解析
        try:
            data = json.loads(description)
            if isinstance(data, dict):
                old_text = str(data.get("old_text", ""))
                new_text = str(data.get("new_text", ""))
                if old_text:
                    return old_text, new_text
        except Exception:  # noqa: BLE001
            pass

        # 尝试 "|||" 分隔符格式
        if "|||" in description:
            old_text, new_text = description.split("|||", 1)
            return old_text, new_text

        raise RuntimeError(
            "edit 步骤的 description 无法解析为 {old_text, new_text} "
            "(需 JSON 格式或 'old|||new' 分隔符格式)"
        )

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

        # 1. 运行测试
        test_result = await self._tools.test()
        test_passed = test_result.success
        if not test_passed:
            notes_parts.append(f"测试失败: {test_result.error or ''}")

        # 2. 收集本次执行的 diff, 供 LLM 审查
        diff_text = self._collect_diff(task.id)
        llm_passed = True
        if diff_text:
            llm_passed, llm_notes = await self._llm_review(task, diff_text)
            if llm_notes:
                notes_parts.append(llm_notes)

        # 3. 综合判定: 测试通过且 LLM 审查通过
        passed = test_passed and llm_passed
        return passed, "\n".join(notes_parts)

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
                    "你是代码审查员, 审查代码变更是否正确实现了任务, "
                    "是否引入了语法错误、逻辑问题或破坏性变更。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"任务: {task.description}\n\n"
                    f"变更 diff:\n{diff_text}\n\n"
                    "请审查并返回 JSON: "
                    '{"passed": true/false, "notes": "审查意见"}'
                ),
            },
        ]
        response = await self._call_llm(messages)
        return self._parse_review(response)

    def _collect_diff(self, task_id: str) -> str:
        """收集指定任务执行期间产生的所有变更集 diff。

        从 DiffEngine 历史中提取与本次任务变更集 ID 匹配的条目,
        拼接各变更集的 unified diff。

        Args:
            task_id: 任务 ID。

        Returns:
            拼接后的 diff 文本; 无变更时返回空字符串。
        """
        changeset_ids = self._task_changesets.get(task_id, [])
        if not changeset_ids:
            return ""

        id_set = set(changeset_ids)
        parts: list[str] = []
        for cs, _ in self._tools._diff.get_history():
            if cs.id in id_set:
                diff = cs.to_diff()
                if diff:
                    parts.append(diff)
        return "\n".join(parts)

    def _parse_review(self, response: str) -> tuple[bool, str]:
        """解析 LLM 审查响应为 (passed, notes)。

        解析策略 (层层降级):
          1. 直接 json.loads
          2. 正则提取 {...} 块再 json.loads
          3. 关键字判定 (含 "不通过"/"reject"/"failed" → 不通过)

        Args:
            response: LLM 响应文本。

        Returns:
            (passed, notes) 元组; 空响应默认通过 (避免 LLM 不可用时阻塞)。
        """
        # LLM 不可用 (空响应) 时默认通过, 避免阻塞流程
        if not response:
            return True, ""

        # 1. 直接 json.loads
        try:
            data = json.loads(response)
            if isinstance(data, dict):
                return bool(data.get("passed", True)), str(data.get("notes", ""))
        except Exception:  # noqa: BLE001
            pass

        # 2. 正则提取 {...} 块再尝试
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return bool(data.get("passed", True)), str(data.get("notes", ""))
            except Exception:  # noqa: BLE001
                pass

        # 3. 关键字降级: 含否定关键字判为不通过
        lower = response.lower()
        if "不通过" in response or "reject" in lower or "failed" in lower:
            return False, self._truncate(response, 500)
        return True, self._truncate(response, 500)

    # ========================================================================
    # LLM 调用封装
    # ========================================================================

    async def _call_llm(self, messages: list[dict[str, str]]) -> str:
        """调用 LLM (封装异常)。

        Args:
            messages: LLM 消息列表 (role/content)。

        Returns:
            LLM 响应文本; 调用失败时返回空字符串。
        """
        try:
            return await self._llm.complete({"messages": messages})
        except Exception:  # noqa: BLE001
            return ""

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
        except Exception:  # noqa: BLE001
            data = None

        # 2. 正则提取第一个 {...} 块再尝试 (贪婪匹配, 可捕获含嵌套的完整 JSON)
        if data is None:
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except Exception:  # noqa: BLE001
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
                    steps.append(TaskStep(
                        id=uuid4().hex[:8],
                        description=desc,
                        action=action,
                        target=str(item.get("target", "")).strip(),
                    ))
                if steps:
                    return steps

        # 4. 降级: 单步
        return self._fallback_plan()

    def _fallback_plan(self) -> list[TaskStep]:
        """降级计划: 返回单步 "手动执行任务"。

        Returns:
            包含单个手动执行步骤的列表。
        """
        return [TaskStep(
            id=uuid4().hex[:8],
            description="手动执行任务",
            action="",
            target="",
        )]

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
            if result is not None and hasattr(result, '__await__'):
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
    "TaskStatus",
    "TaskStep",
    "CodingTask",
    "TaskResult",
    "CodingAgentEvent",
    "CodingAgent",
]
