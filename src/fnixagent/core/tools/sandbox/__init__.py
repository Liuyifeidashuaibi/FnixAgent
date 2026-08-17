"""
安全沙箱模块。

提供:
  - SandboxPolicy: 安全策略(高危命令黑名单/网络白名单/文件写白名单)
  - CodeSandbox: 受限代码执行(受限 globals + 内置函数过滤 + 超时 + 内存监控)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.tools.sandbox.executor import CodeSandbox, SandboxResult
from fnixagent.core.tools.sandbox.policy import SandboxPolicy

__all__ = ["CodeSandbox", "SandboxPolicy", "SandboxResult"]
