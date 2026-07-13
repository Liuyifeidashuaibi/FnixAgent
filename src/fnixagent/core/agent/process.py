"""
AgentProcess - 进程抽象 (Process Abstraction)
=============================================
类比 OS Process, 每个 Agent 是独立进程, 有状态/优先级/资源/检查点。

设计要点:
  - 完整状态机: CREATED → READY → RUNNING → TERMINATED
                              ↕        ↕
                           BLOCKED   SUSPENDED
  - Durable Execution: 检查点 JSON 序列化 (修复原版 str(dict) bug)
  - 资源限制: token/step/duration/child 四项 cgroup 风格限制
  - 父子关系: 进程树, 父进程可限制子进程能力
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from fnixagent.core.agent.types import (
    AgentPriority, AgentState, ResourceLimits, TraceContext, utcnow, utcnow_iso,
)


@dataclass
class AgentProcess:
    """Agent 进程 (类比 OS Process)。

    每个 Agent 有独立上下文、状态、优先级, 由 Kernel 调度。
    支持 Durable Execution: 检查点可在崩溃后恢复。

    Attributes:
        pid: 进程 ID (UUID)
        name: 进程名 (人类可读)
        state: 进程状态
        priority: 优先级 (nice 值)
        context_root: 上下文 FS 挂载点
        parent_pid: 父进程 PID (None = 内核直接创建)
        child_pids: 子进程 PID 列表
        capabilities: 能力令牌集合 (如 {"fs", "llm", "tool"})
        limits: 资源限制 (类比 ulimit)
        tokens_used: 已消耗 token 数
        steps_executed: 已执行步数
        checkpoint: Durable Execution 检查点
        created_at: 创建时间
        started_at: 开始运行时间
        finished_at: 结束时间
        trace_context: OTel trace 上下文
        cpu_time_ms: 累计 CPU 时间 (毫秒, 用于公平调度)
        last_scheduled: 上次调度时间戳 (monotonic)
        exit_code: 退出码 (None = 未退出)
        exit_reason: 退出原因
    """
    pid: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    state: AgentState = AgentState.CREATED
    priority: AgentPriority = AgentPriority.NORMAL
    context_root: str = "/"
    parent_pid: str | None = None
    child_pids: list[str] = field(default_factory=list)
    capabilities: set[str] = field(default_factory=set)
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    tokens_used: int = 0
    steps_executed: int = 0
    checkpoint: dict[str, Any] = field(default_factory=dict)
    runtime_meta: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow_iso)
    started_at: str | None = None
    finished_at: str | None = None
    trace_context: TraceContext = field(default_factory=TraceContext)
    cpu_time_ms: float = 0.0
    last_scheduled: float = 0.0
    exit_code: int | None = None
    exit_reason: str = ""

    # --- 状态查询 ---

    @property
    def is_alive(self) -> bool:
        """进程是否存活 (类比 kill -0)。"""
        return self.state in (AgentState.READY, AgentState.RUNNING,
                              AgentState.BLOCKED, AgentState.SUSPENDED)

    @property
    def is_running(self) -> bool:
        """是否正在运行。"""
        return self.state == AgentState.RUNNING

    @property
    def is_terminated(self) -> bool:
        """是否已终止。"""
        return self.state == AgentState.TERMINATED

    @property
    def elapsed_sec(self) -> float:
        """已运行秒数 (从 started_at 到 finished_at 或 now)。"""
        if self.started_at is None:
            return 0.0
        from datetime import datetime
        start = datetime.fromisoformat(self.started_at)
        if self.finished_at:
            end = datetime.fromisoformat(self.finished_at)
        else:
            end = utcnow()
        return (end - start).total_seconds()

    # --- 状态转换 (受调度器调用, 这里只做状态变更) ---

    def transition(self, new_state: AgentState) -> None:
        """状态转换 (带合法性检查, 非法转换抛 ValueError)。"""
        legal = {
            AgentState.CREATED: {AgentState.READY, AgentState.TERMINATED},
            AgentState.READY: {AgentState.RUNNING, AgentState.TERMINATED, AgentState.SUSPENDED},
            AgentState.RUNNING: {AgentState.READY, AgentState.BLOCKED,
                                 AgentState.SUSPENDED, AgentState.TERMINATED},
            AgentState.BLOCKED: {AgentState.READY, AgentState.TERMINATED},
            AgentState.SUSPENDED: {AgentState.READY, AgentState.TERMINATED},
            AgentState.TERMINATED: set(),  # 终态
        }
        if new_state not in legal.get(self.state, set()):
            raise ValueError(
                f"非法状态转换: {self.state.value} → {new_state.value} "
                f"(pid={self.pid})"
            )
        self.state = new_state
        if new_state == AgentState.RUNNING and self.started_at is None:
            self.started_at = utcnow_iso()
        elif new_state == AgentState.TERMINATED and self.finished_at is None:
            self.finished_at = utcnow_iso()

    # --- 资源限制检查 ---

    def check_limits(self) -> str | None:
        """检查是否超出资源限制, 返回超出原因 (None = 未超出)。"""
        if self.tokens_used > self.limits.max_tokens:
            return f"token 超限: {self.tokens_used} > {self.limits.max_tokens}"
        if self.steps_executed > self.limits.max_steps:
            return f"步数超限: {self.steps_executed} > {self.limits.max_steps}"
        if self.elapsed_sec > self.limits.max_duration_sec:
            return (f"时长超限: {self.elapsed_sec:.1f}s > "
                    f"{self.limits.max_duration_sec}s")
        if len(self.child_pids) > self.limits.max_child_processes:
            return (f"子进程超限: {len(self.child_pids)} > "
                    f"{self.limits.max_child_processes}")
        return None

    def consume_tokens(self, count: int) -> None:
        """记录 token 消耗。"""
        if count > 0:
            self.tokens_used += count

    def consume_step(self) -> None:
        """记录一次 syscall 步数。"""
        self.steps_executed += 1

    # --- Durable Execution 检查点 ---

    def save_checkpoint(self) -> dict[str, Any]:
        """保存检查点 (JSON 可序列化, 修复原版 str(dict) bug)。

        检查点包含恢复进程所需的最小信息:
          - 基本属性: pid/name/state/priority/context_root
          - 资源使用: tokens_used/steps_executed
          - 能力集: capabilities
          - 父子关系: parent_pid/child_pids
          - trace 上下文
        """
        self.checkpoint = {
            "pid": self.pid,
            "name": self.name,
            "state": self.state.value,
            "priority": int(self.priority),
            "context_root": self.context_root,
            "tokens_used": self.tokens_used,
            "steps_executed": self.steps_executed,
            "capabilities": sorted(self.capabilities),
            "parent_pid": self.parent_pid,
            "child_pids": list(self.child_pids),
            "limits": self.limits.to_dict(),
            "trace_context": self.trace_context.to_dict(),
            "saved_at": utcnow_iso(),
            "cpu_time_ms": self.cpu_time_ms,
        }
        return self.checkpoint

    def restore_from_checkpoint(self, cp: dict[str, Any]) -> None:
        """从检查点恢复 (支持崩溃后冷启动)。"""
        self.state = AgentState(cp.get("state", AgentState.READY.value))
        self.priority = AgentPriority(cp.get("priority", int(AgentPriority.NORMAL)))
        self.context_root = cp.get("context_root", "/")
        self.tokens_used = cp.get("tokens_used", 0)
        self.steps_executed = cp.get("steps_executed", 0)
        self.capabilities = set(cp.get("capabilities", []))
        self.parent_pid = cp.get("parent_pid")
        self.child_pids = list(cp.get("child_pids", []))
        self.cpu_time_ms = cp.get("cpu_time_ms", 0.0)
        # 恢复资源限制
        limits_dict = cp.get("limits", {})
        if limits_dict:
            self.limits = ResourceLimits(**{
                k: v for k, v in limits_dict.items()
                if k in ResourceLimits.__dataclass_fields__
            })
        # 恢复 trace 上下文
        trace_dict = cp.get("trace_context", {})
        if trace_dict:
            self.trace_context = TraceContext(**{
                k: v for k, v in trace_dict.items()
                if k in TraceContext.__dataclass_fields__
            })
        # 恢复后进入 READY 状态, 等待重新调度
        if self.state == AgentState.RUNNING:
            self.state = AgentState.READY

    def to_checkpoint_json(self) -> str:
        """检查点 JSON 字符串 (用于持久化到 StorageBackend)。"""
        return json.dumps(self.save_checkpoint(), ensure_ascii=False)

    @classmethod
    def from_checkpoint_json(cls, json_str: str) -> AgentProcess:
        """从 JSON 字符串重建进程 (崩溃恢复)。"""
        cp = json.loads(json_str)
        proc = cls(
            pid=cp.get("pid", str(uuid.uuid4())),
            name=cp.get("name", ""),
            context_root=cp.get("context_root", "/"),
            capabilities=set(cp.get("capabilities", [])),
        )
        proc.restore_from_checkpoint(cp)
        return proc

    # --- 序列化 ---

    def to_dict(self) -> dict[str, Any]:
        """完整序列化 (用于 ps 命令/API 响应)。"""
        return {
            "pid": self.pid,
            "name": self.name,
            "state": self.state.value,
            "priority": int(self.priority),
            "parent_pid": self.parent_pid,
            "child_count": len(self.child_pids),
            "capabilities": sorted(self.capabilities),
            "tokens_used": self.tokens_used,
            "steps_executed": self.steps_executed,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "cpu_time_ms": round(self.cpu_time_ms, 2),
            "created_at": self.created_at,
            "is_alive": self.is_alive,
        }

    def __repr__(self) -> str:
        return (f"AgentProcess(pid={self.pid[:8]}, name={self.name!r}, "
                f"state={self.state.value}, priority={int(self.priority)})")


__all__ = ["AgentProcess"]
