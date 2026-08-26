"""
AgentKernel - Agent 操作系统内核 (Agent OS Kernel)
====================================================
对齐 2026 AgentOS 前沿研究 / Agent OS / Agentic OS /
Meta Dreamer / Microsoft Project Solara), 将传统 OS 概念完整映射到 Agent 系统。

设计哲学 (2026 共识):
  Prompt Engineering → Context Engineering → Harness Engineering
  决定 Agent 落地的不再是模型能力, 而是 Harness 设计质量。

ETCLOVG 七层框架:
  E - Execution      AgentScheduler   优先级调度 + 抢占 + Durable 检查点
  T - Tool           ToolBackend      MCP 工具驱动 (设备驱动类比)
  C - Context        ContextFS        上下文文件系统 + just-in-time 加载
  L - Lifecycle      DurableExec      崩溃恢复, 长任务不重算
  O - Observability  ObservabilityMgr OTel 钩子 + 审计日志
  V - Verification   GuardrailMgr     三层护栏 (输入/执行/输出)
  G - Governance     PolicyEngine     默认拒绝 + 最小权限 + 能力模型

OS 概念映射:
  Kernel → AgentKernel     Process → AgentProcess    Thread → Agent Step
  Syscall → AgentSyscall   FS → ContextFS            Memory → MemoryManager
  Driver → ToolBackend     Scheduler → AgentScheduler IPC → A2ABus
  Permission → PolicyEngine Shell → AgentShell       Sandbox → SandboxManager

零外部依赖: 仅 asyncio / enum / uuid / dataclasses / datetime / collections / time
可插拔后端: LLM / Memory / Storage / Policy / Audit / Tool 均通过协议接口注入

修复原版 bug:
  - tokens_used 计量: 现在从 LLMBackend.count_tokens 提取实际消耗
  - SCHEDULE syscall 未注册: 已注册
  - shutdown 未保存检查点: 现在调用 suspend
  - 全局单例 import 创建: 改为延迟创建 (get_kernel())
  - 护栏覆盖不全: 现在覆盖全部 syscall (INPUT/EXECUTION/OUTPUT 三层)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fnixagent.core.agent.guardrail import (
    GuardrailContext,
    GuardrailLayer,
    GuardrailManager,
)
from fnixagent.core.agent.memory import MemoryManager
from fnixagent.core.agent.messaging import A2ABus, A2AMessage, AgentCard
from fnixagent.core.agent.observability import ObservabilityManager
from fnixagent.core.agent.policy import PolicyEngine, PolicyRule
from fnixagent.core.agent.process import AgentProcess, AgentState
from fnixagent.core.agent.sandbox import SandboxManager
from fnixagent.core.agent.scheduler import AgentScheduler
from fnixagent.core.agent.syscall import (
    SyscallRequest,
    SyscallResponse,
    SyscallType,
)
from fnixagent.core.agent.types import (
    AUDIT_BOOT,
    AUDIT_CHECKPOINT,
    AUDIT_GUARDRAIL_BLOCK,
    AUDIT_KILL,
    AUDIT_SHUTDOWN,
    AUDIT_SPAWN,
    AUDIT_SYSCALL,
    AUDIT_SYSCALL_DENIED,
    AgentPriority,
    AuditBackend,
    LLMBackend,
    MemoryBackend,
    MemoryLayer,
    PolicyBackend,
    ResourceLimits,
    StorageBackend,
    ToolBackend,
    utcnow_iso,
)
from fnixagent.core.agent.vfs import ContextFS

_logger = logging.getLogger(__name__)


# Syscall 处理器签名
SyscallHandler = Callable[[SyscallRequest], Awaitable[SyscallResponse]]


class AgentKernel:
    """Agent 操作系统内核 (类比 Linux Kernel)。

    AgentKernel 是 AgentOS 的核心, 集成 ETCLOVG 七层框架:
      - E (Execution): AgentScheduler 进程调度
      - T (Tool): ToolBackend MCP 工具驱动
      - C (Context): ContextFS 上下文文件系统
      - L (Lifecycle): RunCheckpointStore 持久化执行（SQLite WAL）
      - O (Observability): ObservabilityManager OTel + 审计
      - V (Verification): GuardrailManager 三层护栏
      - G (Governance): PolicyEngine 权限/能力模型

    所有后端通过 Protocol 接口注入, 实现依赖倒转。
    """

    def __init__(
        self,
        llm_backend: LLMBackend | None = None,
        memory_backend: MemoryBackend | None = None,
        tool_backend: ToolBackend | None = None,
        storage_backend: StorageBackend | None = None,
        policy_backend: PolicyBackend | None = None,
        audit_backend: AuditBackend | None = None,
        policy_mode: str = "development",
        enable_scheduler_loop: bool = True,
    ):
        # --- 可插拔后端 ---
        self._llm_backend = llm_backend
        self._memory_backend = memory_backend
        self._tool_backend = tool_backend
        self._storage_backend = storage_backend
        self._policy_backend = policy_backend
        self._audit_backend = audit_backend

        # --- ETCLOVG 七层组件 ---
        self.scheduler = AgentScheduler(storage=storage_backend)
        self.context_fs = ContextFS(storage=storage_backend)
        self.memory = MemoryManager(episodic_backend=memory_backend)
        self.policy = PolicyEngine(backend=policy_backend, mode=policy_mode)
        self.a2a_bus = A2ABus()
        self.observability = ObservabilityManager()
        self.guardrail = GuardrailManager()
        self.sandbox = SandboxManager()

        # --- 内核状态 ---
        self._processes: dict[str, AgentProcess] = {}
        self._syscall_handlers: dict[SyscallType, SyscallHandler] = {}
        self._booted = False
        self._boot_time: str | None = None
        self._shutdown_event = asyncio.Event()

        # --- 默认配置 ---
        self._enable_scheduler_loop = enable_scheduler_loop

        # 注册 syscall 处理器
        self._register_syscall_handlers()

    # ========================================================================
    # 生命周期
    # ========================================================================

    async def boot(self) -> None:
        """启动内核 (类比 boot loader)。

        流程:
          1. 启动调度器 (后台调度循环 + 资源监控)
          2. 注册默认策略规则
          3. 注册 shell-agent 到 A2A 总线
          4. 记录审计
        """
        if self._booted:
            return
        self._booted = True
        self._boot_time = utcnow_iso()

        # 1. 启动调度器
        if self._enable_scheduler_loop:
            await self.scheduler.start()

        # 2. 注册默认策略规则
        self._register_default_policies()

        # 3. 注册内置护栏
        self._register_default_guardrails()

        # 4. 注册 shell-agent 到 A2A 总线
        shell_card = AgentCard(
            id="kernel",
            name="fnixagent Kernel",
            description="AgentOS 内核 Shell Agent",
            capabilities=["fs", "memory", "llm", "tool", "ipc", "admin"],
            skills=["shell"],
        )
        await self.a2a_bus.register(shell_card)

        # 5. 审计
        await self._audit(AUDIT_BOOT, {"boot_time": self._boot_time})

    async def shutdown(self) -> None:
        """关闭内核 (类比 shutdown)。

        流程:
          1. 挂起所有存活进程 (保存检查点)
          2. 停止调度器
          3. 清理 A2A 总线
          4. 记录审计
        """
        if not self._booted:
            return

        # 1. 挂起所有存活进程 (保存检查点)
        alive_pids = [pid for pid, p in self._processes.items() if p.is_alive]
        for pid in alive_pids:
            await self.scheduler.suspend(pid)
            # 标记为非存活，保留进程记录供审计 (不删除)。
            # 修复: is_alive 是只读 property（由 state 派生），不能直接赋值 —
            # 原 `proc.is_alive = False` 抛 AttributeError 使 shutdown 崩溃。
            # 通过状态机转换到 TERMINATED（SUSPENDED→TERMINATED 合法）达成同样效果。
            proc = self._processes.get(pid)
            if proc is not None:
                try:
                    proc.transition(AgentState.TERMINATED)
                except ValueError:
                    # 已处于终态等边缘情况 — 保底直接置终态字段
                    proc.state = AgentState.TERMINATED
                    proc.finished_at = proc.finished_at or utcnow_iso()

        # 2. 停止调度器
        await self.scheduler.stop()

        # 3. 审计
        await self._audit(
            AUDIT_SHUTDOWN,
            {
                "suspended_count": len(alive_pids),
                "shutdown_time": utcnow_iso(),
            },
        )

        self._booted = False
        self._shutdown_event.set()

    def _register_default_policies(self) -> None:
        """注册默认策略规则。"""
        # 高危操作默认拒绝 (低优先级进程)
        self.policy.add_rule(
            PolicyRule(
                action="shell.exec",
                subject="*",
                effect="deny",
                condition=lambda args: args.get("priority", 99) <= int(AgentPriority.BACKGROUND),
                priority=100,
                description="后台进程禁止 shell.exec",
            )
        )
        self.policy.add_rule(
            PolicyRule(
                action="computer.use",
                subject="*",
                effect="deny",
                condition=lambda args: args.get("priority", 99) <= int(AgentPriority.BACKGROUND),
                priority=100,
                description="后台进程禁止 computer.use",
            )
        )

    def _register_default_guardrails(self) -> None:
        """注册内置护栏。"""
        from fnixagent.core.agent.guardrail import (
            length_limit_guardrail,
            sensitive_data_guardrail,
        )

        # 输入长度限制
        self.guardrail.register(
            "length_limit_input",
            length_limit_guardrail(max_length=100000, layer=GuardrailLayer.INPUT).func,
            layer=GuardrailLayer.INPUT,
            priority=10,
        )
        # 输出敏感数据脱敏
        self.guardrail.register(
            "sensitive_data_output",
            sensitive_data_guardrail().func,
            layer=GuardrailLayer.OUTPUT,
            priority=20,
        )

    # ========================================================================
    # 进程管理
    # ========================================================================

    async def spawn(
        self,
        name: str,
        parent_pid: str | None = None,
        priority: AgentPriority = AgentPriority.NORMAL,
        capabilities: set[str] | None = None,
        limits: ResourceLimits | None = None,
        max_tokens: int = 1_000_000,
        max_steps: int = 1000,
        max_duration_sec: int = 3600,
    ) -> str:
        """创建 Agent 进程 (类比 fork + exec)。

        Args:
            name: Agent 名称
            parent_pid: 父 Agent PID (None = 内核直接创建)
            priority: 优先级
            capabilities: 能力令牌集合 (如 {"fs", "llm", "tool"})
            limits: 资源限制 (None = 默认)
            max_tokens: 最大 token 消耗 (limits=None 时生效)
            max_steps: 最大步数
            max_duration_sec: 最大运行时长 (秒)

        Returns:
            新 Agent 的 PID
        """
        # 能力继承限制: 子进程能力 ⊆ 父进程能力
        if parent_pid and parent_pid in self._processes:
            parent = self._processes[parent_pid]
            if not parent.capabilities.issuperset(capabilities or set()):
                if "admin" not in parent.capabilities:
                    raise PermissionError(
                        f"父进程 {parent_pid} 能力不足, 无法 spawn 具备 "
                        f"{capabilities - parent.capabilities} 的子进程"
                    )

        # 创建进程
        proc = AgentProcess(
            name=name,
            parent_pid=parent_pid,
            priority=priority,
            capabilities=capabilities or {"fs", "llm"},
            limits=limits
            or ResourceLimits(
                max_tokens=max_tokens,
                max_steps=max_steps,
                max_duration_sec=max_duration_sec,
            ),
        )

        # 注册进程
        self._processes[proc.pid] = proc
        await self.scheduler.admit(proc)

        # 记录父子关系
        if parent_pid and parent_pid in self._processes:
            self._processes[parent_pid].child_pids.append(proc.pid)

        # 注册到 A2A 总线
        card = AgentCard(
            id=proc.pid,
            name=name,
            capabilities=list(capabilities or []),
        )
        await self.a2a_bus.register(card)

        await self._audit(
            AUDIT_SPAWN,
            {
                "pid": proc.pid,
                "name": name,
                "parent": parent_pid,
                "priority": int(priority),
                "capabilities": sorted(capabilities or []),
            },
        )
        return proc.pid

    async def kill(self, pid: str, reason: str = "") -> bool:
        """终止 Agent (类比 kill -9)。"""
        proc = self._processes.get(pid)
        if proc is None:
            return False
        await self.scheduler.terminate(pid, reason)
        await self._audit(AUDIT_KILL, {"pid": pid, "reason": reason})
        return True

    def get_process(self, pid: str) -> AgentProcess | None:
        """获取进程信息 (类比 /proc/pid)。"""
        return self._processes.get(pid)

    def list_processes(self) -> list[AgentProcess]:
        """列出所有进程 (类比 ps)。"""
        return list(self._processes.values())

    # ========================================================================
    # 系统调用入口
    # ========================================================================

    async def syscall(self, req: SyscallRequest) -> SyscallResponse:
        """系统调用入口 (类比 syscall handler)。

        所有 Agent 对资源的访问必须经过此处, 受 PolicyEngine 约束。

        流程 (ETCLOVG):
          G - Governance: 授权检查
          V - Verification: 输入护栏
          O - Observability: 开始 span
          Dispatch: 分发到 handler
          V - Verification: 输出护栏
          O - Observability: 结束 span + 审计
          L - Lifecycle: 记录 journal
        """
        start_time = time.monotonic()

        # G - Governance: 授权检查
        process = self._processes.get(req.caller_pid)
        allowed, reason = await self.policy.authorize(req, process)
        if not allowed:
            await self._audit(
                AUDIT_SYSCALL_DENIED,
                {
                    "syscall": req.syscall.value,
                    "pid": req.caller_pid,
                    "reason": reason,
                    "request_id": req.request_id,
                },
            )
            return SyscallResponse.err(
                f"Permission denied: {reason}",
                request_id=req.request_id,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )

        # V - Verification: 输入护栏
        input_ctx = GuardrailContext(
            layer=GuardrailLayer.INPUT,
            syscall=req.syscall.value,
            caller_pid=req.caller_pid,
            content=req.args.get("content") or req.args.get("messages") or req.args,
            args=req.args,
            metadata={"request_id": req.request_id},
        )
        input_result = self.guardrail.evaluate(input_ctx)
        if input_result.blocked:
            await self._audit(
                AUDIT_GUARDRAIL_BLOCK,
                {
                    "syscall": req.syscall.value,
                    "pid": req.caller_pid,
                    "layer": "input",
                    "message": input_result.message,
                },
            )
            return SyscallResponse.err(
                f"Input blocked: {input_result.message}",
                request_id=req.request_id,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )
        # MODIFY: 更新 args (类型安全: 不破坏 messages 列表结构)
        # 先浅拷贝 req.args 避免直接修改传入对象
        req.args = dict(req.args)
        if input_result.modified and input_result.modified_content is not None:
            modified = input_result.modified_content
            if "content" in req.args:
                req.args["content"] = modified
            elif "messages" in req.args and isinstance(req.args["messages"], list):
                # 仅修改最后一条消息的 content, 保持消息列表结构完整
                msgs = list(req.args["messages"])
                if msgs and isinstance(modified, str):
                    last = dict(msgs[-1])
                    last["content"] = modified
                    msgs[-1] = last
                    req.args["messages"] = msgs

        # O - Observability: 开始 span
        span = self.observability.trace_syscall(
            req.syscall.value, req.args, req.caller_pid, req.trace_id
        )

        # Dispatch: 分发到 handler
        handler = self._syscall_handlers.get(req.syscall)
        if handler is None:
            span.end("error", f"Unsupported syscall: {req.syscall.value}")
            return SyscallResponse.err(
                f"Unsupported syscall: {req.syscall.value}",
                request_id=req.request_id,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )

        try:
            # 执行层护栏 (仅 TOOL_INVOKE / SHELL_EXEC / COMPUTER_USE)
            if req.syscall in (
                SyscallType.TOOL_INVOKE,
                SyscallType.SHELL_EXEC,
                SyscallType.COMPUTER_USE,
            ):
                exec_ctx = GuardrailContext(
                    layer=GuardrailLayer.EXECUTION,
                    syscall=req.syscall.value,
                    caller_pid=req.caller_pid,
                    content=req.args.get("command") or req.args.get("arguments") or req.args,
                    args=req.args,
                )
                exec_result = self.guardrail.evaluate(exec_ctx)
                if exec_result.blocked:
                    span.end("error", f"Execution blocked: {exec_result.message}")
                    await self._audit(
                        AUDIT_GUARDRAIL_BLOCK,
                        {
                            "syscall": req.syscall.value,
                            "pid": req.caller_pid,
                            "layer": "execution",
                            "message": exec_result.message,
                        },
                    )
                    return SyscallResponse.err(
                        f"Execution blocked: {exec_result.message}",
                        request_id=req.request_id,
                        duration_ms=(time.monotonic() - start_time) * 1000,
                    )

            response = await handler(req)

            # V - Verification: 输出护栏
            if response.success and response.result is not None:
                output_ctx = GuardrailContext(
                    layer=GuardrailLayer.OUTPUT,
                    syscall=req.syscall.value,
                    caller_pid=req.caller_pid,
                    content=response.result,
                    args=req.args,
                )
                output_result = self.guardrail.evaluate(output_ctx)
                if output_result.blocked:
                    span.end("error", f"Output blocked: {output_result.message}")
                    await self._audit(
                        AUDIT_GUARDRAIL_BLOCK,
                        {
                            "syscall": req.syscall.value,
                            "pid": req.caller_pid,
                            "layer": "output",
                            "message": output_result.message,
                        },
                    )
                    return SyscallResponse.err(
                        f"Output blocked: {output_result.message}",
                        request_id=req.request_id,
                    )
                if output_result.modified:
                    response.result = output_result.modified_content

            # 更新资源计量
            duration_ms = (time.monotonic() - start_time) * 1000
            response.duration_ms = duration_ms
            response.request_id = req.request_id
            if process:
                process.consume_step()
                if response.tokens_used > 0:
                    process.consume_tokens(response.tokens_used)

            # O - Observability: 结束 span
            span.end("ok" if response.success else "error", response.error or "")

            # 审计
            await self._audit(
                AUDIT_SYSCALL,
                {
                    "syscall": req.syscall.value,
                    "pid": req.caller_pid,
                    "success": response.success,
                    "duration_ms": round(duration_ms, 3),
                    "tokens_used": response.tokens_used,
                },
            )

            return response

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            span.end("error", str(e))
            return SyscallResponse.err(
                f"Syscall error: {type(e).__name__}: {e}",
                request_id=req.request_id,
                duration_ms=duration_ms,
            )

    # ========================================================================
    # Syscall 处理器注册
    # ========================================================================

    def _register_syscall_handlers(self) -> None:
        """注册全部 24 个 syscall 处理器。"""
        # FS
        self._syscall_handlers[SyscallType.FS_READ] = self._handle_fs_read
        self._syscall_handlers[SyscallType.FS_WRITE] = self._handle_fs_write
        self._syscall_handlers[SyscallType.FS_LIST] = self._handle_fs_list
        self._syscall_handlers[SyscallType.FS_DELETE] = self._handle_fs_delete
        self._syscall_handlers[SyscallType.FS_MKDIR] = self._handle_fs_mkdir
        # MEM
        self._syscall_handlers[SyscallType.MEM_RECALL] = self._handle_mem_recall
        self._syscall_handlers[SyscallType.MEM_STORE] = self._handle_mem_store
        self._syscall_handlers[SyscallType.MEM_SEARCH] = self._handle_mem_search
        self._syscall_handlers[SyscallType.MEM_FORGET] = self._handle_mem_forget
        # TOOL
        self._syscall_handlers[SyscallType.TOOL_INVOKE] = self._handle_tool_invoke
        self._syscall_handlers[SyscallType.TOOL_LIST] = self._handle_tool_list
        # IPC
        self._syscall_handlers[SyscallType.IPC_SEND] = self._handle_ipc_send
        self._syscall_handlers[SyscallType.IPC_SPAWN] = self._handle_ipc_spawn
        self._syscall_handlers[SyscallType.IPC_WAIT] = self._handle_ipc_wait
        self._syscall_handlers[SyscallType.IPC_BROADCAST] = self._handle_ipc_broadcast
        # LLM
        self._syscall_handlers[SyscallType.LLM_COMPLETE] = self._handle_llm_complete
        self._syscall_handlers[SyscallType.LLM_STREAM] = self._handle_llm_stream
        self._syscall_handlers[SyscallType.EMBED] = self._handle_embed
        # COMPUTER
        self._syscall_handlers[SyscallType.COMPUTER_USE] = self._handle_computer_use
        self._syscall_handlers[SyscallType.SHELL_EXEC] = self._handle_shell_exec
        # WEB
        self._syscall_handlers[SyscallType.WEB_SEARCH] = self._handle_web_search
        self._syscall_handlers[SyscallType.WEB_FETCH] = self._handle_web_fetch
        # SCHEDULE (修复原版 SCHEDULE 未注册 bug)
        self._syscall_handlers[SyscallType.SLEEP] = self._handle_sleep
        self._syscall_handlers[SyscallType.SCHEDULE] = self._handle_schedule
        self._syscall_handlers[SyscallType.CHECKPOINT] = self._handle_checkpoint

    # --- FS 处理器 ---

    async def _handle_fs_read(self, req: SyscallRequest) -> SyscallResponse:
        path = req.args.get("path", "")
        content = await self.context_fs.read(path, req.caller_pid)
        return SyscallResponse.ok(content)

    async def _handle_fs_write(self, req: SyscallRequest) -> SyscallResponse:
        path = req.args.get("path", "")
        content = req.args.get("content", "")
        await self.context_fs.write(path, content, req.caller_pid)
        return SyscallResponse.ok({"written": True, "path": path})

    async def _handle_fs_list(self, req: SyscallRequest) -> SyscallResponse:
        path = req.args.get("path", "/")
        entries = await self.context_fs.list_dir(path, req.caller_pid)
        return SyscallResponse.ok(entries)

    async def _handle_fs_delete(self, req: SyscallRequest) -> SyscallResponse:
        path = req.args.get("path", "")
        deleted = await self.context_fs.delete(path, req.caller_pid)
        if not deleted:
            return SyscallResponse.err(f"删除失败: {path}")
        return SyscallResponse.ok({"deleted": True, "path": path})

    async def _handle_fs_mkdir(self, req: SyscallRequest) -> SyscallResponse:
        path = req.args.get("path", "")
        await self.context_fs.mkdir(path, req.caller_pid)
        return SyscallResponse.ok({"created": True, "path": path})

    # --- MEM 处理器 ---

    async def _handle_mem_recall(self, req: SyscallRequest) -> SyscallResponse:
        query = req.args.get("query", "")
        layers_str = req.args.get("layers", ["working"])
        top_k = req.args.get("top_k", 5)
        layers = [MemoryLayer(l) if isinstance(l, str) else l for l in layers_str]
        results = await self.memory.recall(query, layers, req.caller_pid, top_k)
        return SyscallResponse.ok(results)

    async def _handle_mem_store(self, req: SyscallRequest) -> SyscallResponse:
        content = req.args.get("content", "")
        layer_str = req.args.get("layer", "working")
        layer = MemoryLayer(layer_str) if isinstance(layer_str, str) else layer_str
        metadata = req.args.get("metadata", {})
        memory_id = await self.memory.store(content, layer, metadata, req.caller_pid)
        return SyscallResponse.ok({"memory_id": memory_id})

    async def _handle_mem_search(self, req: SyscallRequest) -> SyscallResponse:
        query = req.args.get("query", "")
        layer_str = req.args.get("layer", "episodic")
        layer = MemoryLayer(layer_str) if isinstance(layer_str, str) else layer_str
        top_k = req.args.get("top_k", 5)
        results = await self.memory.search(query, layer, req.caller_pid, top_k)
        return SyscallResponse.ok(results)

    async def _handle_mem_forget(self, req: SyscallRequest) -> SyscallResponse:
        memory_id = req.args.get("memory_id", "")
        success = await self.memory.forget(memory_id, req.caller_pid)
        if not success:
            return SyscallResponse.err(f"未找到记忆: {memory_id}")
        return SyscallResponse.ok({"forgotten": True})

    # --- TOOL 处理器 ---

    async def _handle_tool_invoke(self, req: SyscallRequest) -> SyscallResponse:
        if self._tool_backend is None:
            return SyscallResponse.err("未配置 ToolBackend")
        tool_name = req.args.get("tool", "")
        arguments = req.args.get("arguments", {})
        try:
            result = await self._tool_backend.invoke(tool_name, arguments)
            return SyscallResponse.ok(result)
        except ValueError as e:
            return SyscallResponse.err(str(e))
        except Exception as e:
            return SyscallResponse.err(f"工具执行异常: {type(e).__name__}: {e}")

    async def _handle_tool_list(self, req: SyscallRequest) -> SyscallResponse:
        if self._tool_backend is None:
            return SyscallResponse.err("未配置 ToolBackend")
        tools = await self._tool_backend.list_tools()
        return SyscallResponse.ok(tools)

    # --- IPC 处理器 ---

    async def _handle_ipc_send(self, req: SyscallRequest) -> SyscallResponse:
        target = req.args.get("target", "")
        content = req.args.get("content")
        msg = A2AMessage(
            source=req.caller_pid,
            target=target,
            message_type="event",
            content=content,
        )
        await self.a2a_bus.send(target, msg)
        return SyscallResponse.ok({"sent": True})

    async def _handle_ipc_spawn(self, req: SyscallRequest) -> SyscallResponse:
        name = req.args.get("name", "child")
        capabilities = set(req.args.get("capabilities", []))
        priority_str = req.args.get("priority", "normal")
        try:
            priority = (
                AgentPriority[priority_str.upper()]
                if isinstance(priority_str, str)
                else AgentPriority(int(priority_str))
            )
        except (KeyError, ValueError):
            return SyscallResponse.err(f"无效的优先级: {priority_str}")
        pid = await self.spawn(
            name=name,
            parent_pid=req.caller_pid,
            capabilities=capabilities,
            priority=priority,
        )
        return SyscallResponse.ok({"pid": pid})

    async def _handle_ipc_wait(self, req: SyscallRequest) -> SyscallResponse:
        timeout = req.args.get("timeout", 30.0)
        try:
            msg = await self.a2a_bus.receive(req.caller_pid, timeout=timeout)
            return SyscallResponse.ok(msg.to_dict())
        except TimeoutError:
            return SyscallResponse.err("等待消息超时")

    async def _handle_ipc_broadcast(self, req: SyscallRequest) -> SyscallResponse:
        content = req.args.get("content")
        msg = A2AMessage(
            source=req.caller_pid,
            target="*",
            message_type="event",
            content=content,
        )
        count = await self.a2a_bus.broadcast(msg, exclude=req.caller_pid)
        return SyscallResponse.ok({"delivered": count})

    # --- LLM 处理器 ---

    async def _handle_llm_complete(self, req: SyscallRequest) -> SyscallResponse:
        if self._llm_backend is None:
            return SyscallResponse.err("未配置 LLMBackend")
        messages = req.args.get("messages", [])
        # 调用 LLM
        result = await self._llm_backend.complete(messages)
        # 计量实际 token (修复原版 max_tokens bug)
        tokens_used = 0
        if hasattr(self._llm_backend, "count_tokens"):
            try:
                tokens_used = await self._llm_backend.count_tokens(messages)
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
        return SyscallResponse.ok(result, tokens_used=tokens_used)

    async def _handle_llm_stream(self, req: SyscallRequest) -> SyscallResponse:
        if self._llm_backend is None:
            return SyscallResponse.err("未配置 LLMBackend")
        messages = req.args.get("messages", [])
        # 收集流式响应 (实际应用应异步迭代)
        chunks: list[str] = []
        async for chunk in self._llm_backend.stream(messages):
            chunks.append(chunk)
        result = "".join(chunks)
        tokens_used = 0
        if hasattr(self._llm_backend, "count_tokens"):
            try:
                tokens_used = await self._llm_backend.count_tokens(messages)
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)
        return SyscallResponse.ok(result, tokens_used=tokens_used)

    async def _handle_embed(self, req: SyscallRequest) -> SyscallResponse:
        if self._llm_backend is None:
            return SyscallResponse.err("未配置 LLMBackend")
        text = req.args.get("text", "")
        vector = await self._llm_backend.embed(text)
        return SyscallResponse.ok(vector)

    # --- COMPUTER 处理器 ---

    async def _handle_computer_use(self, req: SyscallRequest) -> SyscallResponse:
        # 预留: 实际接入 OpenAI Operator / browser-use
        return SyscallResponse.err("computer.use 需接入 browser-use (预留接口)")

    async def _handle_shell_exec(self, req: SyscallRequest) -> SyscallResponse:
        command = req.args.get("command", "")
        sandbox_level = req.args.get("sandbox", "none")
        from fnixagent.core.agent.sandbox import SandboxConfig
        from fnixagent.core.agent.types import SandboxLevel

        config = SandboxConfig(
            level=SandboxLevel(sandbox_level) if isinstance(sandbox_level, str) else sandbox_level,
            timeout_sec=req.args.get("timeout", 30.0),
        )
        result = await self.sandbox.execute(command, config)
        return SyscallResponse(
            success=result.success,
            result=result.to_dict(),
            error=result.error,
        )

    # --- WEB 处理器 ---

    async def _handle_web_search(self, req: SyscallRequest) -> SyscallResponse:
        # 预留: 接入 Brave/Tavily/Jina 搜索 MCP
        return SyscallResponse.err("web.search 需接入 Brave/Tavily 搜索 MCP (预留接口)")

    async def _handle_web_fetch(self, req: SyscallRequest) -> SyscallResponse:
        # 预留: 接入 阅读服务 / 网页抓取服务
        return SyscallResponse.err("web.fetch 需接入 阅读服务 / 网页抓取服务 (预留接口)")

    # --- SCHEDULE 处理器 ---

    async def _handle_sleep(self, req: SyscallRequest) -> SyscallResponse:
        seconds = req.args.get("seconds", 1.0)
        await asyncio.sleep(seconds)
        return SyscallResponse.ok({"slept": seconds})

    async def _handle_schedule(self, req: SyscallRequest) -> SyscallResponse:
        # 预留: 定时任务调度 (类比 cron)
        return SyscallResponse.ok(
            {
                "scheduled": False,
                "message": "schedule syscall 预留接口 (未来支持 cron)",
            }
        )

    async def _handle_checkpoint(self, req: SyscallRequest) -> SyscallResponse:
        pid = req.caller_pid
        proc = self._processes.get(pid)
        if proc is None:
            return SyscallResponse.err(f"进程不存在: {pid}")
        cp = await self.scheduler.checkpoint(pid)
        await self._audit(AUDIT_CHECKPOINT, {"pid": pid})
        return SyscallResponse.ok(cp)

    # ========================================================================
    # 辅助方法
    # ========================================================================

    async def _audit(
        self, action: str, detail: dict[str, Any] | None = None, subject: str | None = None
    ) -> None:
        """记录审计 (内存 + 可选后端)。"""
        self.observability.audit(action, detail, subject)
        if self._audit_backend:
            try:
                await self._audit_backend.log(
                    action=action,
                    subject=subject,
                    detail=detail or {},
                )
            except Exception:
                _logger.debug('Unhandled exception', exc_info=True)

    def get_audit_log(self, limit: int = 100, action: str | None = None) -> list[dict[str, Any]]:
        """查询审计日志。"""
        return self.observability.get_audit_log(limit=limit, action=action)

    def get_kernel_stats(self) -> dict[str, Any]:
        """内核统计 (类比 /proc)。"""
        return {
            "booted": self._booted,
            "boot_time": self._boot_time,
            "process_count": len(self._processes),
            "alive_processes": sum(1 for p in self._processes.values() if p.is_alive),
            "scheduler": self.scheduler.get_stats(),
            "context_fs": self.context_fs.get_stats(),
            "memory": self.memory.get_stats("kernel") if self._processes else {},
            "policy": self.policy.get_stats(),
            "a2a_bus": self.a2a_bus.get_stats(),
            "observability": self.observability.get_stats(),
            "guardrail": self.guardrail.get_stats(),
            "sandbox": self.sandbox.get_stats(),
            "has_llm_backend": self._llm_backend is not None,
            "has_memory_backend": self._memory_backend is not None,
            "has_tool_backend": self._tool_backend is not None,
            "has_storage_backend": self._storage_backend is not None,
            "has_policy_backend": self._policy_backend is not None,
            "has_audit_backend": self._audit_backend is not None,
        }


# ============================================================================
# 全局内核实例 (延迟创建, 修复原版 import 即创建 bug)
# ============================================================================

_kernel_instance: AgentKernel | None = None


def get_kernel() -> AgentKernel:
    """获取全局内核实例 (延迟创建)。

    修复原版 bug: 原版在 import 时创建空壳内核, 污染全局状态。
    现在延迟到首次调用 get_kernel() 时创建。
    """
    global _kernel_instance
    if _kernel_instance is None:
        _kernel_instance = AgentKernel()
    return _kernel_instance


def reset_kernel() -> None:
    """重置全局内核实例 (测试用)。"""
    global _kernel_instance
    _kernel_instance = None


__all__ = [
    "AgentKernel",
    "SyscallHandler",
    "get_kernel",
    "reset_kernel",
]
