"""
AgentOS 基础类型与协议接口 (Base Types & Protocols)
====================================================
零外部依赖,定义 AgentOS 全部公共类型契约。

设计原则:
  - 所有后端通过 Protocol 接口注入,实现依赖倒转
  - 类型完备: 枚举/数据类/协议/类型别名
  - 可被 mypy/pyright 严格检查
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import enum
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

# ============================================================================
# 基础工具
# ============================================================================


def utcnow() -> datetime:
    """UTC 当前时间 (统一入口, 便于测试 monkey-patch)。"""
    return datetime.now(UTC)


def utcnow_iso() -> str:
    """UTC 当前时间 ISO 字符串。"""
    return utcnow().isoformat()


# ============================================================================
# 优先级与状态枚举
# ============================================================================


class AgentPriority(enum.IntEnum):
    """Agent 优先级 (类比 nice 值, 数值越大优先级越高)。

    对应调度策略:
      BACKGROUND  - 后台批处理 (数据清洗 / 离线生成), 最低
      BATCH       - 批处理 (PDF 解析 / 文档转换)
      NORMAL      - 普通 (异步问答 / 邮件起草)
      INTERACTIVE - 交互 (用户对话 / 实时编辑)
      REALTIME    - 实时 (流式响应 / 紧急告警), 最高, 可独占时间片
    """

    BACKGROUND = 1
    BATCH = 5
    NORMAL = 10
    INTERACTIVE = 15
    REALTIME = 20


class AgentState(enum.Enum):
    """Agent 进程状态机 (类比 Unix 进程状态)。

    状态转换:
        CREATED → READY → RUNNING → TERMINATED
                    ↕        ↕
                 BLOCKED   SUSPENDED
    """

    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


class MemoryLayer(enum.Enum):
    """四层记忆架构 (2026 业界统一共识)。

    参考: Letta (MemGPT 23K star) / A-MEM / Mem-α / Mem0 / Zep Graphiti

    层级:
      SENSORY  - 感知记忆: LLM 当前处理的 token 流 (GPU KV Cache, vLLM PagedAttention)
      WORKING  - 工作记忆: 当前对话上下文 (LLM Context Window)
      EPISODIC - 情节记忆: 历史对话事件 (Letta + Postgres, 自动摘要)
      SEMANTIC - 语义记忆: 知识图谱 / 向量库 (Milvus + cognee + GraphRAG)
    """

    SENSORY = "sensory"
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


class SyscallCategory(enum.Enum):
    """Syscall 分类 (8 类)。"""

    FS = "fs"  # 文件系统 (ContextFS)
    MEM = "mem"  # 记忆管理 (MemoryManager)
    TOOL = "tool"  # 工具调用 (MCP)
    IPC = "ipc"  # Agent 间通信 (A2A)
    LLM = "llm"  # LLM 推理
    COMPUTER = "computer"  # 计算机使用 (高危)
    WEB = "web"  # 网络
    SCHEDULE = "schedule"  # 时间/调度


class GuardrailAction(enum.Enum):
    """护栏动作 (对标 Guardrails AI)。"""

    PASS = "pass"  # 通过
    WARN = "warn"  # 警告但放行
    BLOCK = "block"  # 阻止
    MODIFY = "modify"  # 修改后放行


class GuardrailLayer(enum.Enum):
    """护栏层级。"""

    INPUT = "input"  # 输入层 (LLM 调用前)
    EXECUTION = "execution"  # 执行层 (工具调用前)
    OUTPUT = "output"  # 输出层 (LLM/工具返回后)


class SandboxLevel(enum.Enum):
    """沙箱隔离级别 (三档, 2026 安全共识)。"""

    NONE = "none"  # 无沙箱 (开发模式)
    DOCKER = "docker"  # Docker 容器隔离 (L1)
    GVIsOR = "gvisor"  # gVisor 内核级隔离 (L2)  保留原拼写以向后兼容
    FIRECRACKER = "firecracker"  # Firecracker microVM (L3, 最高)


# ============================================================================
# 可插拔后端协议 (Protocol, 依赖倒转)
# ============================================================================


@runtime_checkable
class LLMBackend(Protocol):
    """LLM 后端协议。

    可由 core/llm/router.py 的 LLMRouter 适配实现。
    所有方法均为 async, 同步实现需用 asyncio.to_thread 包装。
    """

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        """同步补全, 返回完整文本。"""
        ...

    async def stream(self, messages: list[dict[str, Any]], **kwargs: Any) -> AsyncIterator[str]:
        """流式补全, 异步迭代返回 token 片段。"""
        ...

    async def embed(self, text: str) -> list[float]:
        """文本向量化 (用于语义记忆检索)。"""
        ...

    async def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """统计 token 数 (用于资源限制计量)。"""
        ...


@runtime_checkable
class MemoryBackend(Protocol):
    """记忆后端协议 (情节/语义层)。

    可由 core/memory/manager.py 的 MemoryManager 适配实现,
    或直接对接 Letta/Milvus/cognee。
    """

    async def recall(
        self, query: str, top_k: int = 5, layer: MemoryLayer | None = None
    ) -> list[dict[str, Any]]:
        """召回相关记忆。"""
        ...

    async def store(
        self, content: str, metadata: dict[str, Any], layer: MemoryLayer = MemoryLayer.EPISODIC
    ) -> str:
        """存储记忆, 返回 memory_id。"""
        ...

    async def search(
        self, query: str, top_k: int = 5, layer: MemoryLayer | None = None
    ) -> list[dict[str, Any]]:
        """语义搜索。"""
        ...

    async def forget(self, memory_id: str) -> bool:
        """按 ID 删除记忆。"""
        ...


@runtime_checkable
class ToolBackend(Protocol):
    """工具后端协议 (可由 core/mcp/registry.py 的 MCPToolRegistry 适配)。"""

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出所有可用工具。"""
        ...

    async def invoke(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """调用工具, 返回结果。"""
        ...


@runtime_checkable
class StorageBackend(Protocol):
    """持久化后端协议 (可对接 Postgres/Redis/MinIO/本地 FS)。"""

    async def get(self, key: str) -> str | None:
        """读取键值, 不存在返回 None。"""
        ...

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """写入键值, ttl 为过期秒数 (None 永久)。"""
        ...

    async def delete(self, key: str) -> bool:
        """删除键, 返回是否删除成功。"""
        ...

    async def list_prefix(self, prefix: str) -> list[str]:
        """列出所有以 prefix 开头的键。"""
        ...


@runtime_checkable
class PolicyBackend(Protocol):
    """策略后端协议 (可对接 OPA/Cedar/Lambda authorizer)。"""

    async def evaluate(
        self, action: str, resource: str, subject: str, context: dict[str, Any]
    ) -> tuple[bool, str]:
        """评估策略, 返回 (是否允许, 拒绝原因)。"""
        ...


@runtime_checkable
class AuditBackend(Protocol):
    """审计后端协议 (可对接 AuditLogger / SIEM / Langfuse)。"""

    async def log(
        self,
        action: str,
        subject: str | None = None,
        detail: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> None:
        """记录审计事件 (哈希链防篡改推荐)。"""
        ...

    async def query(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        subject: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询审计日志。"""
        ...


# ============================================================================
# 通用数据类
# ============================================================================


@dataclass
class Capability:
    """能力令牌 (类比 Linux capability)。

    Agent 持有的能力决定可执行的 syscall 范围。
    """

    name: str  # 能力名 (fs/memory/tool/llm/...)
    syscalls: frozenset[str]  # 允许的 syscall 名集合
    constraints: dict[str, Any] = field(default_factory=dict)  # 约束 (如资源上限)


@dataclass
class ResourceLimits:
    """资源限制 (类比 ulimit / cgroup)。

    超出限制的 Agent 会被调度器自动终止。
    """

    max_tokens: int = 1_000_000  # 最大 token 消耗
    max_steps: int = 1000  # 最大步数 (syscall 调用次数)
    max_duration_sec: int = 3600  # 最大运行时长 (秒)
    max_memory_mb: int = 512  # 最大内存 (MB, ContextFS 占用)
    max_child_processes: int = 10  # 最大子进程数

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_steps": self.max_steps,
            "max_duration_sec": self.max_duration_sec,
            "max_memory_mb": self.max_memory_mb,
            "max_child_processes": self.max_child_processes,
        }


@dataclass
class TraceContext:
    """OTel trace 上下文 (分布式追踪)。"""

    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    baggage: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "baggage": dict(self.baggage),
        }


# ============================================================================
# 通用结果类型
# ============================================================================


@dataclass
class Result:
    """统一结果类型 (对标 Rust Result)。"""

    success: bool
    value: Any = None
    error: str | None = None

    @classmethod
    def ok(cls, value: Any = None) -> Result:
        return cls(success=True, value=value)

    @classmethod
    def err(cls, error: str) -> Result:
        return cls(success=False, error=error)

    def unwrap(self) -> Any:
        if not self.success:
            raise RuntimeError(f"Result.err: {self.error}")
        return self.value

    def unwrap_or(self, default: Any) -> Any:
        return self.value if self.success else default


# ============================================================================
# 类型别名
# ============================================================================

# Syscall 处理器签名
SyscallHandler = Callable[[Any], Awaitable[Any]]  # (SyscallRequest) -> SyscallResponse

# OTel 钩子签名
OTelHook = Callable[[str, dict[str, Any]], None]

# 护栏检查函数签名: (syscall_name, args, context) -> (action, message, modified_args)
GuardrailFunc = Callable[
    [str, dict[str, Any], dict[str, Any]], tuple[GuardrailAction, str, dict[str, Any]]
]

# 审计动作常量 (与 AuditLogger 对齐)
AUDIT_SPAWN = "agent.spawn"
AUDIT_KILL = "agent.kill"
AUDIT_SYSCALL = "syscall.exec"
AUDIT_SYSCALL_DENIED = "syscall.denied"
AUDIT_CHECKPOINT = "durable.checkpoint"
AUDIT_RESTORE = "durable.restore"
AUDIT_BOOT = "kernel.boot"
AUDIT_SHUTDOWN = "kernel.shutdown"
AUDIT_POLICY_VIOLATION = "policy.violation"
AUDIT_GUARDRAIL_BLOCK = "guardrail.block"


__all__ = [
    # 工具
    "utcnow",
    "utcnow_iso",
    # 枚举
    "AgentPriority",
    "AgentState",
    "MemoryLayer",
    "SyscallCategory",
    "GuardrailAction",
    "GuardrailLayer",
    "SandboxLevel",
    # 协议
    "LLMBackend",
    "MemoryBackend",
    "ToolBackend",
    "StorageBackend",
    "PolicyBackend",
    "AuditBackend",
    # 数据类
    "Capability",
    "ResourceLimits",
    "TraceContext",
    "Result",
    # 类型别名
    "SyscallHandler",
    "OTelHook",
    "GuardrailFunc",
    # 审计常量
    "AUDIT_SPAWN",
    "AUDIT_KILL",
    "AUDIT_SYSCALL",
    "AUDIT_SYSCALL_DENIED",
    "AUDIT_CHECKPOINT",
    "AUDIT_RESTORE",
    "AUDIT_BOOT",
    "AUDIT_SHUTDOWN",
    "AUDIT_POLICY_VIOLATION",
    "AUDIT_GUARDRAIL_BLOCK",
]
