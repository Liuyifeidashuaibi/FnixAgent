"""
AgentOS 后端适配器 (Backend Adapters)
=======================================
为 Protocol 接口提供开箱即用的实现:
  - in_memory: 纯内存实现 (零依赖, 测试/开发用)

设计原则:
  - 零外部依赖: in_memory 模块仅用 stdlib
  - 统一接口: 所有适配器实现对应 Protocol
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

# 内存后端 (零依赖, 始终可用)
from fnixagent.core.agent.backends.in_memory import (
    InMemoryAuditBackend,
    InMemoryLLMBackend,
    InMemoryMemoryBackend,
    InMemoryPolicyBackend,
    InMemoryStorageBackend,
    InMemoryToolBackend,
)

__all__ = [
    # 内存后端
    "InMemoryLLMBackend",
    "InMemoryMemoryBackend",
    "InMemoryToolBackend",
    "InMemoryStorageBackend",
    "InMemoryPolicyBackend",
    "InMemoryAuditBackend",
]
