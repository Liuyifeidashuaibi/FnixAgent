"""fnix-local — 本地算力 sidecar（索引 / 上下文 / 命令执行）。

Phase 2: Python MVP（CodeIndexer + WorkspaceTools）。
Phase 3+: 可替换为 FnixAi Rust 二进制，HTTP 契约保持不变。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.local.sidecar_app import create_app

__all__ = ["create_app"]
