"""本地 Harness 门面 — workspace / session / skills / gateway。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.harness.gateway import get_harness_status, init_harness
from fnixagent.harness.session import SessionStore, WorkSession
from fnixagent.harness.skills_loader import format_skills_block, load_workspace_skills
from fnixagent.harness.workspace import ensure_home_layout, ensure_project_layout

__all__ = [
    "SessionStore",
    "WorkSession",
    "ensure_home_layout",
    "ensure_project_layout",
    "format_skills_block",
    "get_harness_status",
    "init_harness",
    "load_workspace_skills",
]
