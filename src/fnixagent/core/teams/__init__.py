"""FnixAgent AgentTeams — 多 Agent 协作层。

设计对齐业界已验证的模式(2026):
  - Orchestrator-Worker 阻塞式并行委派(OpenHands/Magentic-One)
  - 共享任务清单 + 信箱(Claude Code Agent Teams)
  - 结构化文档交接(MetaGPT SOP 精髓)
  - 组织记忆回写(KTG, FnixAgent 独有)

模块:
  profiles   — 角色注册表(AgentProfile)
  tasklist   — 共享任务清单(三态/依赖/版本号乐观锁)
  mailbox    — Agent 信箱(JSON 收件箱)
  blackboard — 结构化交接黑板(frontmatter Markdown)
  runner     — AgentTeam 编排器(fan_out/fan_in + 工人运行时)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.core.teams.blackboard import read_handover, write_handover
from fnixagent.core.teams.mailbox import Mailbox
from fnixagent.core.teams.profiles import (
    BUILTIN_PROFILES,
    AgentProfile,
    get_profile,
    list_profiles,
    register_profile,
)
from fnixagent.core.teams.runner import AgentTeam
from fnixagent.core.teams.tasklist import SharedTaskList

__all__ = [
    "AgentProfile",
    "AgentTeam",
    "BUILTIN_PROFILES",
    "Mailbox",
    "SharedTaskList",
    "get_profile",
    "list_profiles",
    "read_handover",
    "register_profile",
    "write_handover",
]
