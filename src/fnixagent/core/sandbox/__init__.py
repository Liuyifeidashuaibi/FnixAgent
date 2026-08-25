"""
Windows Job Object 软沙箱模块。

提供:
  - WinJobObject: kernel32 Job Object 封装(进程树击杀/内存上限/进程数上限)
  - is_windows: 平台探测常量(非 Windows 平台整个模块为 no-op)

设计原则: 纯 ctypes 零依赖; fail-open(沙箱故障不阻塞业务); per-call 局部
实例, 不跨协程共享。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.sandbox.win_job import WinJobObject, is_windows

__all__ = ["WinJobObject", "is_windows"]
