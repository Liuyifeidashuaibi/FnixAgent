"""Compatibility submodule: ``fnixagent.core.agentos.sandbox``."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

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
