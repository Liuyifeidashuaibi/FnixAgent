"""
Syscall 层 - 系统调用 (System Calls)
=====================================
类比 Unix syscall, 所有 Agent 对资源的访问必须通过 syscall, 受 PolicyEngine 约束。

设计要点:
  - 24 类 syscall, 覆盖 8 个分类 (FS/MEM/TOOL/IPC/LLM/COMPUTER/WEB/SCHEDULE)
  - 高危 syscall 标记 (COMPUTER_USE/SHELL_EXEC/FS_DELETE/MEM_FORGET/IPC_BROADCAST)
  - 请求/响应数据类, 含 trace_id 用于 OTel
  - 能力映射表: capability → 允许的 syscall 集合
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Any

from officeagent.core.agentos.types import SyscallCategory, utcnow_iso


class SyscallType(enum.Enum):
    """Agent 系统调用类型 (类比 Unix syscall)。

    所有工具/资源访问必须通过 syscall, 受 PolicyEngine 约束。
    高危操作 (COMPUTER_USE / SHELL_EXEC / FS_DELETE / MEM_FORGET / IPC_BROADCAST)
    需特殊能力令牌。

    分类:
      FS  - fs.read/write/list/delete/mkdir
      MEM - mem.recall/store/search/forget
      TOOL - tool.invoke/list
      IPC - ipc.send/spawn/wait/broadcast
      LLM - llm.complete/stream + embed
      COMPUTER - computer.use (高危) + shell.exec (高危)
      WEB - web.search/fetch
      SCHEDULE - sleep/schedule/checkpoint
    """
    # 文件系统 (ContextFS)
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    FS_LIST = "fs.list"
    FS_DELETE = "fs.delete"
    FS_MKDIR = "fs.mkdir"
    # 记忆管理 (MemoryManager)
    MEM_RECALL = "mem.recall"
    MEM_STORE = "mem.store"
    MEM_SEARCH = "mem.search"
    MEM_FORGET = "mem.forget"
    # 工具调用 (MCP)
    TOOL_INVOKE = "tool.invoke"
    TOOL_LIST = "tool.list"
    # Agent 间通信 (A2A)
    IPC_SEND = "ipc.send"
    IPC_SPAWN = "ipc.spawn"
    IPC_WAIT = "ipc.wait"
    IPC_BROADCAST = "ipc.broadcast"
    # LLM 推理
    LLM_COMPLETE = "llm.complete"
    LLM_STREAM = "llm.stream"
    EMBED = "embed"
    # 计算机使用 (高危)
    COMPUTER_USE = "computer.use"
    SHELL_EXEC = "shell.exec"
    # 网络
    WEB_SEARCH = "web.search"
    WEB_FETCH = "web.fetch"
    # 时间/调度
    SLEEP = "sleep"
    SCHEDULE = "schedule"
    CHECKPOINT = "checkpoint"


# 高危 syscall 集合 (需要特殊能力)
HIGH_RISK_SYSCALLS: frozenset[SyscallType] = frozenset({
    SyscallType.COMPUTER_USE,
    SyscallType.SHELL_EXEC,
    SyscallType.FS_DELETE,
    SyscallType.MEM_FORGET,
    SyscallType.IPC_BROADCAST,
})


# Syscall 分类映射
SYSCALL_CATEGORY: dict[SyscallType, SyscallCategory] = {
    SyscallType.FS_READ: SyscallCategory.FS,
    SyscallType.FS_WRITE: SyscallCategory.FS,
    SyscallType.FS_LIST: SyscallCategory.FS,
    SyscallType.FS_DELETE: SyscallCategory.FS,
    SyscallType.FS_MKDIR: SyscallCategory.FS,
    SyscallType.MEM_RECALL: SyscallCategory.MEM,
    SyscallType.MEM_STORE: SyscallCategory.MEM,
    SyscallType.MEM_SEARCH: SyscallCategory.MEM,
    SyscallType.MEM_FORGET: SyscallCategory.MEM,
    SyscallType.TOOL_INVOKE: SyscallCategory.TOOL,
    SyscallType.TOOL_LIST: SyscallCategory.TOOL,
    SyscallType.IPC_SEND: SyscallCategory.IPC,
    SyscallType.IPC_SPAWN: SyscallCategory.IPC,
    SyscallType.IPC_WAIT: SyscallCategory.IPC,
    SyscallType.IPC_BROADCAST: SyscallCategory.IPC,
    SyscallType.LLM_COMPLETE: SyscallCategory.LLM,
    SyscallType.LLM_STREAM: SyscallCategory.LLM,
    SyscallType.EMBED: SyscallCategory.LLM,
    SyscallType.COMPUTER_USE: SyscallCategory.COMPUTER,
    SyscallType.SHELL_EXEC: SyscallCategory.COMPUTER,
    SyscallType.WEB_SEARCH: SyscallCategory.WEB,
    SyscallType.WEB_FETCH: SyscallCategory.WEB,
    SyscallType.SLEEP: SyscallCategory.SCHEDULE,
    SyscallType.SCHEDULE: SyscallCategory.SCHEDULE,
    SyscallType.CHECKPOINT: SyscallCategory.SCHEDULE,
}


# 能力 → syscall 映射 (高危 syscall 纳入对应能力, 由 HIGH_RISK 额外把关)
CAPABILITY_SYSCALLS: dict[str, frozenset[SyscallType]] = {
    "fs": frozenset({
        SyscallType.FS_READ, SyscallType.FS_WRITE,
        SyscallType.FS_LIST, SyscallType.FS_MKDIR, SyscallType.FS_DELETE,
    }),
    "memory": frozenset({
        SyscallType.MEM_RECALL, SyscallType.MEM_STORE,
        SyscallType.MEM_SEARCH, SyscallType.MEM_FORGET,
    }),
    "tool": frozenset({SyscallType.TOOL_INVOKE, SyscallType.TOOL_LIST}),
    "ipc": frozenset({
        SyscallType.IPC_SEND, SyscallType.IPC_SPAWN,
        SyscallType.IPC_WAIT, SyscallType.IPC_BROADCAST,
    }),
    "llm": frozenset({
        SyscallType.LLM_COMPLETE, SyscallType.LLM_STREAM, SyscallType.EMBED,
    }),
    "web": frozenset({SyscallType.WEB_SEARCH, SyscallType.WEB_FETCH}),
    "computer": frozenset({SyscallType.COMPUTER_USE}),
    "shell": frozenset({SyscallType.SHELL_EXEC}),
    "schedule": frozenset({
        SyscallType.SLEEP, SyscallType.SCHEDULE, SyscallType.CHECKPOINT,
    }),
    # admin 拥有全部权限 (但 deny 规则仍生效)
    "admin": frozenset(SyscallType),
}


# 高危 syscall 所需能力
HIGH_RISK_REQUIRED_CAPS: dict[SyscallType, list[str]] = {
    SyscallType.COMPUTER_USE: ["computer", "admin"],
    SyscallType.SHELL_EXEC: ["shell", "admin"],
    SyscallType.FS_DELETE: ["fs", "admin"],
    SyscallType.MEM_FORGET: ["memory", "admin"],
    SyscallType.IPC_BROADCAST: ["ipc", "admin"],
}


@dataclass
class SyscallRequest:
    """系统调用请求。

    Attributes:
        syscall: syscall 类型
        args: 参数字典 (如 {"path": "/ctx/a.md", "content": "..."})
        caller_pid: 调用方进程 ID
        timestamp: 请求时间 (ISO)
        request_id: 请求 ID (UUID, 用于追踪)
        trace_id: OTel trace ID (可选, 用于分布式追踪)
    """
    syscall: SyscallType
    args: dict[str, Any] = field(default_factory=dict)
    caller_pid: str = ""
    timestamp: str = field(default_factory=utcnow_iso)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "syscall": self.syscall.value,
            "args": dict(self.args),
            "caller_pid": self.caller_pid,
            "timestamp": self.timestamp,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
        }


@dataclass
class SyscallResponse:
    """系统调用响应。

    Attributes:
        success: 是否成功
        result: 结果数据 (成功时)
        error: 错误信息 (失败时)
        request_id: 对应请求 ID
        duration_ms: 执行耗时 (毫秒)
        tokens_used: 本次调用消耗的 token 数 (用于资源计量)
        audit_trace_id: 审计追踪 ID
    """
    success: bool
    result: Any = None
    error: str | None = None
    request_id: str = ""
    duration_ms: float = 0.0
    tokens_used: int = 0
    audit_trace_id: str = ""

    @classmethod
    def ok(cls, result: Any = None, *, request_id: str = "",
           duration_ms: float = 0.0, tokens_used: int = 0) -> SyscallResponse:
        """成功响应。"""
        return cls(
            success=True, result=result, request_id=request_id,
            duration_ms=duration_ms, tokens_used=tokens_used,
        )

    @classmethod
    def err(cls, error: str, *, request_id: str = "",
            duration_ms: float = 0.0) -> SyscallResponse:
        """失败响应。"""
        return cls(
            success=False, error=error, request_id=request_id,
            duration_ms=duration_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "request_id": self.request_id,
            "duration_ms": round(self.duration_ms, 3),
            "tokens_used": self.tokens_used,
        }


def is_high_risk(syscall: SyscallType) -> bool:
    """判断是否为高危 syscall。"""
    return syscall in HIGH_RISK_SYSCALLS


def get_required_caps(syscall: SyscallType) -> list[str]:
    """获取高危 syscall 所需能力 (非高危返回空列表)。"""
    return HIGH_RISK_REQUIRED_CAPS.get(syscall, [])


def check_capability(syscall: SyscallType, capabilities: set[str]) -> bool:
    """检查能力集是否包含执行该 syscall 的能力。"""
    for cap in capabilities:
        allowed = CAPABILITY_SYSCALLS.get(cap, frozenset())
        if syscall in allowed:
            return True
    return False


def get_syscalls_for_capability(capability: str) -> frozenset[SyscallType]:
    """获取能力对应的 syscall 集合。"""
    return CAPABILITY_SYSCALLS.get(capability, frozenset())


__all__ = [
    "SyscallType", "HIGH_RISK_SYSCALLS", "SYSCALL_CATEGORY",
    "CAPABILITY_SYSCALLS", "HIGH_RISK_REQUIRED_CAPS",
    "SyscallRequest", "SyscallResponse",
    "is_high_risk", "get_required_caps", "check_capability",
    "get_syscalls_for_capability",
]
