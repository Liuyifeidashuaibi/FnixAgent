"""Compatibility submodule: ``fnixagent.core.agentos.sandbox``."""

from fnixagent.core.agent.sandbox import (
    FirecrackerExecutor,
    GVisorExecutor,
    InlineExecutor,
    SandboxConfig,
    SandboxManager,
)

__all__ = [
    "FirecrackerExecutor",
    "GVisorExecutor",
    "InlineExecutor",
    "SandboxConfig",
    "SandboxManager",
]
