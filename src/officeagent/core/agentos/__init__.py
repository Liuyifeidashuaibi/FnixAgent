"""
OfficeAgent OS — Agent 操作系统内核包
=====================================
对标 2026 AgentOS 前沿研究 (OpenClaw / DingTalk Agent OS / Honor Agentic OS /
Meta Dreamer / Microsoft Project Solara), 将传统 OS 概念完整映射到 Agent 系统。

设计哲学 (2026 共识):
  Prompt Engineering → Context Engineering → Harness Engineering
  决定 Agent 落地的不再是模型能力, 而是 Harness 设计质量。

ETCLOVG 七层框架:
  E - Execution      AgentScheduler        优先级调度 + 抢占 + Durable 检查点
  T - Tool           ToolBackend           MCP 工具驱动 (设备驱动类比)
  C - Context        ContextFS             上下文文件系统 + just-in-time 加载
  L - Lifecycle      DurableExecutionMgr   崩溃恢复, 长任务不重算
  O - Observability  ObservabilityManager  OTel 钩子 + 审计日志
  V - Verification   GuardrailManager      三层护栏 (输入/执行/输出)
  G - Governance     PolicyEngine          默认拒绝 + 最小权限 + 能力模型

OS 概念映射:
  Kernel    → AgentKernel         Process   → AgentProcess    Thread → Agent Step
  Syscall   → SyscallType         FS        → ContextFS       Memory → MemoryManager
  Driver    → ToolBackend         Scheduler → AgentScheduler IPC    → A2ABus
  Permission→ PolicyEngine        Shell     → AgentShell      Sandbox→ SandboxManager

模块清单 (15 个模块):
  types         - 基础类型 + 6 个 Protocol 协议接口 (LLM/Memory/Tool/Storage/Policy/Audit)
  process       - AgentProcess 进程抽象 + 状态机 + Durable 检查点
  syscall       - 24 类 syscall + 能力映射 + 高危标记
  context_fs    - 上下文文件系统 (VFS + LRU + just-in-time 加载)
  memory        - 四层记忆 (Sensory/Working/Episodic/Semantic)
  policy        - 权限引擎 + 能力模型 + glob 匹配 + 角色映射
  scheduler     - CFS 调度器 + 后台循环 + 资源监控
  a2a           - A2A v1.0 JSON-RPC 协议 + AgentCard + 总线
  durable       - Durable Execution + Journal + 崩溃恢复
  observability - OTel 风格 Span + Metrics + 审计日志
  guardrail     - 三层护栏 (INPUT/EXECUTION/OUTPUT) + PASS/WARN/BLOCK/MODIFY
  sandbox       - 三档沙箱 (Inline/Docker/gVisor/Firecracker)
  kernel        - AgentKernel 主内核 (集成 ETCLOVG 七层)
  shell         - AgentShell CLI + 自然语言 + Skill 加载
  backends      - 内置后端实现 (in_memory + llm_router + mcp_registry)

零外部依赖: 仅 asyncio / enum / uuid / dataclasses / datetime / collections / time
可插拔后端: LLM / Memory / Storage / Policy / Audit / Tool 均通过 Protocol 接口注入
"""
from __future__ import annotations

# --- 基础类型与协议 ---
from officeagent.core.agentos.types import (
    # 工具函数
    utcnow, utcnow_iso,
    # 枚举
    AgentPriority, AgentState, MemoryLayer, SyscallCategory,
    GuardrailAction, GuardrailLayer, SandboxLevel,
    # 协议接口
    LLMBackend, MemoryBackend, ToolBackend, StorageBackend,
    PolicyBackend, AuditBackend,
    # 数据类
    Capability, ResourceLimits, TraceContext, Result,
    # 类型别名
    SyscallHandler, OTelHook, GuardrailFunc,
    # 审计常量
    AUDIT_SPAWN, AUDIT_KILL, AUDIT_SYSCALL, AUDIT_SYSCALL_DENIED,
    AUDIT_CHECKPOINT, AUDIT_RESTORE, AUDIT_BOOT, AUDIT_SHUTDOWN,
    AUDIT_POLICY_VIOLATION, AUDIT_GUARDRAIL_BLOCK,
)

# --- 进程抽象 ---
from officeagent.core.agentos.process import AgentProcess

# --- Syscall 层 ---
from officeagent.core.agentos.syscall import (
    SyscallType, HIGH_RISK_SYSCALLS, SYSCALL_CATEGORY,
    CAPABILITY_SYSCALLS, HIGH_RISK_REQUIRED_CAPS,
    SyscallRequest, SyscallResponse,
    is_high_risk, get_required_caps, check_capability,
    get_syscalls_for_capability,
)

# --- ETCLOVG 七层组件 ---
from officeagent.core.agentos.context_fs import ContextFS
from officeagent.core.agentos.memory import MemoryManager
from officeagent.core.agentos.policy import PolicyEngine, PolicyRule
from officeagent.core.agentos.scheduler import AgentScheduler
from officeagent.core.agentos.a2a import A2ABus, A2AMessage, AgentCard
from officeagent.core.agentos.durable import DurableExecutionManager, JournalEntry
from officeagent.core.agentos.observability import ObservabilityManager, Span
from officeagent.core.agentos.guardrail import (
    GuardrailContext, GuardrailResult, GuardrailManager,
    length_limit_guardrail, sensitive_data_guardrail,
)
from officeagent.core.agentos.sandbox import (
    SandboxConfig, SandboxResult, SandboxManager,
    InlineExecutor, DockerExecutor, GVisorExecutor, FirecrackerExecutor,
)

# --- 内核主体 ---
from officeagent.core.agentos.kernel import (
    AgentKernel, get_kernel, reset_kernel,
)

# --- Shell ---
from officeagent.core.agentos.shell import (
    AgentShell, ShellResult, Skill, SkillRegistry, create_shell,
)

# --- 内置后端 ---
from officeagent.core.agentos.backends import (
    InMemoryLLMBackend, InMemoryMemoryBackend, InMemoryToolBackend,
    InMemoryStorageBackend, InMemoryPolicyBackend, InMemoryAuditBackend,
)

__all__ = [
    # 工具
    "utcnow", "utcnow_iso",
    # 枚举
    "AgentPriority", "AgentState", "MemoryLayer", "SyscallCategory",
    "GuardrailAction", "GuardrailLayer", "SandboxLevel",
    # 协议接口
    "LLMBackend", "MemoryBackend", "ToolBackend", "StorageBackend",
    "PolicyBackend", "AuditBackend",
    # 数据类
    "Capability", "ResourceLimits", "TraceContext", "Result",
    # 类型别名
    "SyscallHandler", "OTelHook", "GuardrailFunc",
    # 审计常量
    "AUDIT_SPAWN", "AUDIT_KILL", "AUDIT_SYSCALL", "AUDIT_SYSCALL_DENIED",
    "AUDIT_CHECKPOINT", "AUDIT_RESTORE", "AUDIT_BOOT", "AUDIT_SHUTDOWN",
    "AUDIT_POLICY_VIOLATION", "AUDIT_GUARDRAIL_BLOCK",
    # 进程
    "AgentProcess",
    # Syscall
    "SyscallType", "HIGH_RISK_SYSCALLS", "SYSCALL_CATEGORY",
    "CAPABILITY_SYSCALLS", "HIGH_RISK_REQUIRED_CAPS",
    "SyscallRequest", "SyscallResponse",
    "is_high_risk", "get_required_caps", "check_capability",
    "get_syscalls_for_capability",
    # ETCLOVG 七层组件
    "ContextFS",
    "MemoryManager",
    "PolicyEngine", "PolicyRule",
    "AgentScheduler",
    "A2ABus", "A2AMessage", "AgentCard",
    "DurableExecutionManager", "JournalEntry",
    "ObservabilityManager", "Span",
    "GuardrailContext", "GuardrailResult", "GuardrailManager",
    "length_limit_guardrail", "sensitive_data_guardrail",
    "SandboxConfig", "SandboxResult", "SandboxManager",
    "InlineExecutor", "DockerExecutor", "GVisorExecutor", "FirecrackerExecutor",
    # 内核
    "AgentKernel", "get_kernel", "reset_kernel",
    # Shell
    "AgentShell", "ShellResult", "Skill", "SkillRegistry", "create_shell",
    # 内置后端
    "InMemoryLLMBackend", "InMemoryMemoryBackend", "InMemoryToolBackend",
    "InMemoryStorageBackend", "InMemoryPolicyBackend", "InMemoryAuditBackend",
]

# ============================================================================
# 包元数据
# ============================================================================

__version__ = "1.0.0"
__author__ = "OfficeAgent Team"
__license__ = "Apache-2.0"
