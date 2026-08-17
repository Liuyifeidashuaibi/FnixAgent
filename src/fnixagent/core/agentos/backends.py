"""Compatibility submodule: ``fnixagent.core.agentos.backends``."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.agent.backends.in_memory import (
    InMemoryAuditBackend,
    InMemoryLLMBackend,
    InMemoryMemoryBackend,
    InMemoryPolicyBackend,
    InMemoryStorageBackend,
    InMemoryToolBackend,
)

__all__ = [
    "InMemoryAuditBackend",
    "InMemoryLLMBackend",
    "InMemoryMemoryBackend",
    "InMemoryPolicyBackend",
    "InMemoryStorageBackend",
    "InMemoryToolBackend",
]
