"""
Compatibility shim for the renamed ``fnixagent.core.agentos`` package.

The agent runtime was refactored into ``fnixagent.core.agent`` (and its
submodules: ``backends.in_memory``, ``guardrail``, ``kernel``, ``memory``,
``messaging``, ``observability``, ``policy``, ``process``, ``sandbox``,
``scheduler``, ``shell``, ``syscall``, ``types``, ``vfs``).

This shim re-exports the public symbols the test-suite (and any legacy
importer) still expects from ``fnixagent.core.agentos`` so existing code keeps
working without edits. It is a thin bridge: every name resolves to the real
implementation living under ``fnixagent.core.agent``.

Once all callers are migrated to ``fnixagent.core.agent.*`` directly, this
package can be deleted.
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.agent.backends.in_memory import (
    InMemoryAuditBackend,
    InMemoryLLMBackend,
    InMemoryMemoryBackend,
    InMemoryPolicyBackend,
    InMemoryStorageBackend,
    InMemoryToolBackend,
)
from fnixagent.core.agent.guardrail import (
    GuardrailContext,
    GuardrailManager,
    GuardrailResult,
    length_limit_guardrail,
    sensitive_data_guardrail,
)
from fnixagent.core.agent.kernel import (
    AgentKernel,
    get_kernel,
    reset_kernel,
)
from fnixagent.core.agent.memory import (
    MemoryManager,
)
from fnixagent.core.agent.messaging import (
    A2ABus,
    A2AMessage,
    AgentCard,
)
from fnixagent.core.agent.observability import (
    ObservabilityManager,
    Span,
)
from fnixagent.core.agent.policy import (
    PolicyEngine,
    PolicyRule,
)
from fnixagent.core.agent.process import (
    AgentProcess,
)
from fnixagent.core.agent.sandbox import (
    FirecrackerExecutor,
    GVisorExecutor,
    InlineExecutor,
    SandboxManager,
)
from fnixagent.core.agent.scheduler import (
    AgentScheduler,
)
from fnixagent.core.agent.shell import (
    AgentShell,
    ShellResult,
    Skill,
    SkillRegistry,
)
from fnixagent.core.agent.syscall import (
    CAPABILITY_SYSCALLS,
    HIGH_RISK_SYSCALLS,
    SyscallRequest,
    SyscallResponse,
    SyscallType,
)
from fnixagent.core.agent.types import (
    AgentPriority,
    AuditBackend,
    GuardrailAction,
    GuardrailLayer,
    LLMBackend,
    MemoryBackend,
    MemoryLayer,
    PolicyBackend,
    ResourceLimits,
    Result,
    SandboxLevel,
    StorageBackend,
    ToolBackend,
    TraceContext,
    utcnow,
    utcnow_iso,
)
from fnixagent.core.agent.vfs import (
    ContextFS,
)

# Alias expected by some tests (``A2ABus as _A2ABus``).
_A2ABus = A2ABus

# Version (expected by test_agentos_e2e.py)
__version__ = "1.0.0"

__all__ = [
    "CAPABILITY_SYSCALLS",
    "HIGH_RISK_SYSCALLS",
    "A2ABus",
    "A2AMessage",
    "AgentCard",
    "AgentKernel",
    "AgentPriority",
    "AgentProcess",
    "AgentScheduler",
    "AgentShell",
    "AuditBackend",
    "ContextFS",
    "FirecrackerExecutor",
    "GVisorExecutor",
    "GuardrailAction",
    "GuardrailContext",
    "GuardrailLayer",
    "GuardrailManager",
    "GuardrailResult",
    "InMemoryAuditBackend",
    "InMemoryLLMBackend",
    "InMemoryMemoryBackend",
    "InMemoryPolicyBackend",
    "InMemoryStorageBackend",
    "InMemoryToolBackend",
    "InlineExecutor",
    "LLMBackend",
    "MemoryBackend",
    "MemoryLayer",
    "MemoryManager",
    "ObservabilityManager",
    "PolicyBackend",
    "PolicyEngine",
    "PolicyRule",
    "ResourceLimits",
    "Result",
    "SandboxLevel",
    "SandboxManager",
    "ShellResult",
    "Skill",
    "SkillRegistry",
    "Span",
    "StorageBackend",
    "SyscallRequest",
    "SyscallResponse",
    "SyscallType",
    "ToolBackend",
    "TraceContext",
    "_A2ABus",
    "get_kernel",
    "length_limit_guardrail",
    "reset_kernel",
    "sensitive_data_guardrail",
    "utcnow",
    "utcnow_iso",
]
