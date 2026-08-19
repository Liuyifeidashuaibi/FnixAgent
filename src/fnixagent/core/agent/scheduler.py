"""
AgentScheduler - 进程调度器 (Process Scheduler)
================================================
类比 OS Scheduler, 负责 Agent 进程的调度与资源管理。

设计要点:
  - 优先级调度: REALTIME > INTERACTIVE > NORMAL > BATCH > BACKGROUND
  - 公平调度 (CFS): 同优先级内按 cpu_time_ms 最小者优先 (防饿死)
  - 抢占式: 高优先级 Agent 可抢占低优先级 Agent
  - Durable Execution: 检查点保存到后端, 崩溃后可恢复
  - 资源限制: 超出 max_tokens / max_steps / max_duration 自动终止
  - 后台调度循环: 自动轮转调度 (修复原版无后台循环 bug)
  - 资源监控: 后台监控超限进程 (修复原版无自动检查 bug)

修复原版 bug:
  - block(pid) 误删无关进程: 修复 pop(-1, None) 问题
  - terminate 未处理 ready_queue: 已补充
  - 无后台调度循环: 已实现 _scheduler_loop
  - 无资源监控: 已实现 _resource_monitor_loop
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fnixagent.core.agent.process import AgentProcess
from fnixagent.core.agent.types import (
    AgentPriority,
    AgentState,
    StorageBackend,
)


class AgentScheduler:
    """Agent 调度器 (类比 OS Scheduler)。

    调度策略:
      1. 优先级调度: REALTIME > INTERACTIVE > NORMAL > BATCH > BACKGROUND
      2. 公平调度 (CFS): 同优先级内按 cpu_time_ms 最小者优先 (防饿死)
      3. 抢占式: 高优先级 Agent 可抢占低优先级 Agent
      4. Durable Execution: 检查点保存到后端, 崩溃后可恢复
      5. 资源限制: 超出 max_tokens / max_steps / max_duration 自动终止

    时间片: 默认 100ms, REALTIME 可独占
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        time_slice_ms: float = 100.0,
        preempt_enabled: bool = True,
        monitor_interval_sec: float = 1.0,
    ):
        self._ready_queue: list[AgentProcess] = []
        self._running: dict[str, AgentProcess] = {}
        self._blocked: dict[str, AgentProcess] = {}
        self._suspended: dict[str, AgentProcess] = {}
        self._terminated: dict[str, AgentProcess] = {}
        self._storage = storage
        self._time_slice_ms = time_slice_ms
        self._preempt_enabled = preempt_enabled
        self._monitor_interval = monitor_interval_sec
        self._scheduler_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._wakeup_event = asyncio.Event()
        # 统计
        self._total_scheduled = 0
        self._total_preemptions = 0
        self._total_terminations = 0

    # --- 生命周期 ---

    async def start(self) -> None:
        """启动调度器 (后台调度循环 + 资源监控)。"""
        if self._scheduler_task is None:
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._resource_monitor_loop())

    async def stop(self) -> None:
        """停止调度器。"""
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

    async def _scheduler_loop(self) -> None:
        """后台调度循环 (修复原版无后台循环 bug)。

        每 time_slice_ms 检查一次:
          1. 若无 running 进程, 从 ready_queue 选一个执行
          2. 若 running 进程超时, yield_ 让出
        """
        while True:
            try:
                await asyncio.sleep(self._time_slice_ms / 1000.0)
                async with self._lock:
                    # 无 running 进程时调度新进程
                    if not self._running and self._ready_queue:
                        await self.schedule()
                    # running 进程超时, 让出 CPU
                    running = list(self._running.values())
                    for proc in running:
                        if (time.monotonic() - proc.last_scheduled) * 1000 > self._time_slice_ms:
                            if proc.priority != AgentPriority.REALTIME:
                                await self.yield_(proc.pid)
            except asyncio.CancelledError:
                break
            except Exception:
                # 避免循环因异常退出
                continue

    async def _resource_monitor_loop(self) -> None:
        """资源监控循环 (修复原版无自动检查 bug)。

        每 monitor_interval_sec 检查所有 running/blocked 进程的资源使用,
        超限进程自动终止。
        """
        while True:
            try:
                await asyncio.sleep(self._monitor_interval)
                async with self._lock:
                    # 检查 running 进程
                    pids_to_terminate: list[tuple[str, str]] = []
                    for pid, proc in self._running.items():
                        reason = proc.check_limits()
                        if reason:
                            pids_to_terminate.append((pid, reason))
                    # 检查 blocked 进程
                    for pid, proc in self._blocked.items():
                        reason = proc.check_limits()
                        if reason:
                            pids_to_terminate.append((pid, reason))
                # 在锁外执行 terminate (避免死锁)
                for pid, reason in pids_to_terminate:
                    await self.terminate(pid, f"资源超限: {reason}")
            except asyncio.CancelledError:
                break
            except Exception:
                continue

    # --- 进程管理 ---

    async def admit(self, proc: AgentProcess) -> None:
        """接纳进程进入就绪队列 (类比 admit to ready queue)。"""
        proc.transition(AgentState.READY)
        proc.last_scheduled = time.monotonic()
        async with self._lock:
            self._ready_queue.append(proc)
        # 尝试抢占
        if self._preempt_enabled:
            await self._try_preempt(proc)

    async def schedule(self) -> AgentProcess | None:
        """选择下一个执行的 Agent (类比 schedule() 函数)。

        调度算法:
          1. 按优先级降序
          2. 同优先级内按 cpu_time_ms 升序 (CFS 公平调度)
        """
        async with self._lock:
            if not self._ready_queue:
                return None
            # 排序: 优先级降序, cpu_time 升序 (公平)
            self._ready_queue.sort(key=lambda p: (-p.priority, p.cpu_time_ms))
            proc = self._ready_queue.pop(0)
            proc.transition(AgentState.RUNNING)
            proc.last_scheduled = time.monotonic()
            self._running[proc.pid] = proc
            self._total_scheduled += 1
            return proc

    async def yield_(self, pid: str) -> None:
        """Agent 主动让出 CPU (类比 sched_yield)。"""
        async with self._lock:
            proc = self._running.pop(pid, None)
        if proc:
            proc.cpu_time_ms += self._time_slice_ms
            proc.transition(AgentState.READY)
            await self.admit(proc)

    async def block(self, pid: str, reason: str = "") -> None:
        """阻塞 Agent (类比 wait / block)。

        修复原版 bug: pop(-1, None) 会误删队尾无关进程。
        """
        async with self._lock:
            # 先从 running 取
            proc = self._running.pop(pid, None)
            if proc is None:
                # 从 ready_queue 取 (修复 pop(-1, None) bug)
                for i, p in enumerate(self._ready_queue):
                    if p.pid == pid:
                        proc = self._ready_queue.pop(i)
                        break
        if proc:
            proc.transition(AgentState.BLOCKED)
            proc.runtime_meta["block_reason"] = reason
            async with self._lock:
                self._blocked[pid] = proc

    async def unblock(self, pid: str) -> None:
        """解除阻塞 (类比 wakeup)。"""
        async with self._lock:
            proc = self._blocked.pop(pid, None)
        if proc:
            proc.runtime_meta.pop("block_reason", None)
            await self.admit(proc)

    async def terminate(self, pid: str, reason: str = "") -> None:
        """终止 Agent (类比 kill / exit)。

        递归终止子进程, 但使用迭代式收集避免重复锁获取。
        """
        # 收集需要终止的所有 pid (父 + 子孙), 避免递归重复加锁
        to_terminate: list[tuple[str, str]] = [(pid, reason)]
        terminated_pids: set[str] = set()
        results: list[tuple[AgentProcess, str]] = []

        while to_terminate:
            current_pid, current_reason = to_terminate.pop(0)
            if current_pid in terminated_pids:
                continue
            terminated_pids.add(current_pid)

            async with self._lock:
                proc = (
                    self._running.pop(current_pid, None)
                    or self._blocked.pop(current_pid, None)
                    or self._suspended.pop(current_pid, None)
                )
                if proc is None:
                    for i, p in enumerate(self._ready_queue):
                        if p.pid == current_pid:
                            proc = self._ready_queue.pop(i)
                            break
            if proc is None:
                continue

            proc.transition(AgentState.TERMINATED)
            proc.exit_reason = current_reason
            self._total_terminations += 1
            async with self._lock:
                self._terminated[current_pid] = proc
            results.append((proc, current_reason))

            # 将子进程加入待终止队列
            for child_pid in list(proc.child_pids):
                if child_pid not in terminated_pids:
                    to_terminate.append((child_pid, f"父进程 {current_pid} 终止"))

    async def suspend(self, pid: str) -> dict[str, Any] | None:
        """挂起 Agent 并保存检查点 (Durable Execution)。

        修复原版 bug: str(dict) 非 JSON, resume 从未反序列化。
        """
        async with self._lock:
            proc = self._running.pop(pid, None) or self._blocked.pop(pid, None)
            if proc is None:
                for i, p in enumerate(self._ready_queue):
                    if p.pid == pid:
                        proc = self._ready_queue.pop(i)
                        break
        if proc is None:
            return None
        proc.transition(AgentState.SUSPENDED)
        cp = proc.save_checkpoint()
        # 持久化检查点 (JSON 序列化, 修复原版 str(dict) bug)
        if self._storage:
            await self._storage.set(
                f"checkpoint:{pid}",
                json.dumps(cp, ensure_ascii=False),
            )
        async with self._lock:
            self._suspended[pid] = proc
        return cp

    async def resume(self, pid: str) -> AgentProcess | None:
        """恢复挂起的 Agent (崩溃恢复)。"""
        # 优先从内存 _suspended 恢复
        async with self._lock:
            proc = self._suspended.pop(pid, None)
        if proc is None and self._storage:
            # 从后端恢复 (崩溃后冷启动)
            cp_str = await self._storage.get(f"checkpoint:{pid}")
            if cp_str:
                try:
                    # from_checkpoint_json 内部会 json.loads, 此处仅需验证
                    json.loads(cp_str)  # 验证 JSON 合法性
                    proc = AgentProcess.from_checkpoint_json(cp_str)
                except (json.JSONDecodeError, KeyError):
                    proc = None
        if proc is None:
            return None
        proc.transition(AgentState.READY)
        await self.admit(proc)
        return proc

    async def checkpoint(self, pid: str) -> dict[str, Any] | None:
        """保存检查点但不挂起 (类比 fsync)。"""
        async with self._lock:
            proc = self._running.get(pid) or self._blocked.get(pid) or self._suspended.get(pid)
        if proc is None:
            for p in self._ready_queue:
                if p.pid == pid:
                    proc = p
                    break
        if proc is None:
            return None
        cp = proc.save_checkpoint()
        if self._storage:
            await self._storage.set(
                f"checkpoint:{pid}",
                json.dumps(cp, ensure_ascii=False),
            )
        return cp

    async def _try_preempt(self, new_proc: AgentProcess) -> None:
        """尝试抢占当前 running 中优先级更低的进程。"""
        async with self._lock:
            to_preempt: list[AgentProcess] = []
            for running_pid, running_proc in list(self._running.items()):
                if (
                    new_proc.priority > running_proc.priority
                    and running_proc.priority != AgentPriority.REALTIME
                ):
                    to_preempt.append(running_proc)
            for proc in to_preempt:
                self._running.pop(proc.pid, None)
        for proc in to_preempt:
            proc.cpu_time_ms += (time.monotonic() - proc.last_scheduled) * 1000
            proc.transition(AgentState.READY)
            self._total_preemptions += 1
            await self.admit(proc)

    # --- 查询 ---

    def get_process_state(self, pid: str) -> AgentState | None:
        """查询进程状态。"""
        for collection in (self._running, self._blocked, self._suspended, self._terminated):
            if pid in collection:
                return collection[pid].state
        for p in self._ready_queue:
            if p.pid == pid:
                return p.state
        return None

    def list_ready(self) -> list[AgentProcess]:
        """列出就绪队列。"""
        return list(self._ready_queue)

    def list_running(self) -> list[AgentProcess]:
        """列出运行中进程。"""
        return list(self._running.values())

    def list_blocked(self) -> list[AgentProcess]:
        """列出阻塞进程。"""
        return list(self._blocked.values())

    def list_suspended(self) -> list[AgentProcess]:
        """列出挂起进程。"""
        return list(self._suspended.values())

    def list_terminated(self) -> list[AgentProcess]:
        """列出已终止进程。"""
        return list(self._terminated.values())

    def get_stats(self) -> dict[str, Any]:
        """调度器统计 (类比 /proc/schedstat)。"""
        return {
            "ready_count": len(self._ready_queue),
            "running_count": len(self._running),
            "blocked_count": len(self._blocked),
            "suspended_count": len(self._suspended),
            "terminated_count": len(self._terminated),
            "total_scheduled": self._total_scheduled,
            "total_preemptions": self._total_preemptions,
            "total_terminations": self._total_terminations,
            "time_slice_ms": self._time_slice_ms,
            "preempt_enabled": self._preempt_enabled,
            "scheduler_running": self._scheduler_task is not None,
            "monitor_running": self._monitor_task is not None,
        }


__all__ = ["AgentScheduler"]
