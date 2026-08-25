"""Agent 角色注册表 — 团队工人的能力规格。

每个角色 = 系统提示词 + 工具白名单 + 步数预算 + 风险等级。
对齐 CrewAI 的角色隐喻与 Claude Code 的 agents/*.md 自定义机制,
但白名单在代码层强制执行(非仅提示词约定)。

红线:
  - 任何角色的白名单都无法包含团队协作工具(workers 是叶子节点)
  - 写类工具(write_file/edit_file)的执行仍需过 ToolPolicy/HITL 门
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from dataclasses import dataclass, field

# 只读工具集(与 subagent._READONLY_TOOLS 对齐; 此处独立声明避免循环导入)
READONLY_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "read_lines",
        "list_dir",
        "list_directory",
        "ls",
        "glob",
        "grep",
        "search",
        "search_code",
        "search_project",
        "web_search",
        "web_fetch",
        "calculate",
        "get_context",
    }
)

# 写工具(仍受 ToolPolicy/HITL 治理; 不含 run_command —— 终端权留给主循环)
WRITE_TOOLS: frozenset[str] = frozenset({"write_file", "edit_file"})


@dataclass
class AgentProfile:
    """一个团队角色的完整规格。"""

    name: str
    description: str  # 给主 Agent 选角色时看的一句话说明
    system_prompt: str  # 角色系统提示词({workspace_root} 占位可用)
    tools: frozenset[str] = READONLY_TOOLS  # 工具白名单(代码层强制)
    max_steps: int = 15  # 单次子任务步数预算
    risk_level: str = "low"  # low / medium / high(预留 HITL 分级)
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 内置角色
# ---------------------------------------------------------------------------

_RESEARCHER_PROMPT = (
    "你是团队中的研究员(researcher),只做信息收集与分析。\n"
    "规则:\n"
    "1. 使用只读工具(read/grep/glob/web)收集证据\n"
    "2. 结论必须附带来源(文件路径/URL)\n"
    "3. 输出结构化要点,控制在 800 字内\n"
    "4. 信息不足时明确说明缺什么,不编造\n"
    "工作区: {workspace_root}"
)

_CODER_PROMPT = (
    "你是团队中的工程师(coder),负责具体实施。\n"
    "规则:\n"
    "1. 先读后写: 修改前必须 read_file 目标文件\n"
    "2. 改动最小化: 只做委派任务范围内的事,不顺手重构\n"
    "3. 完成后汇报改了哪些文件、每处改动的原因\n"
    "4. 遇到超出范围的问题,记录下来而不是自行扩大改动\n"
    "工作区: {workspace_root}"
)

_CRITIC_PROMPT = (
    "你是团队中的评审员(critic),专职质量把关,不使用工具。\n"
    "根据委派给你的材料进行审查:\n"
    "1. 列出发现的问题(按严重度排序)\n"
    "2. 给出总分(0-100)与一句话结论\n"
    "3. 通过标准: 无高危问题且总分 ≥ 70\n"
    "输出格式:\nISSUES: ...(或 '无')\nSCORE: <数字>\nVERDICT: PASS|FAIL"
)

BUILTIN_PROFILES: dict[str, AgentProfile] = {
    p.name: p
    for p in (
        AgentProfile(
            name="researcher",
            description="只读探索与调研: 代码检索/资料搜集/结构梳理",
            system_prompt=_RESEARCHER_PROMPT,
            tools=READONLY_TOOLS,
            max_steps=15,
            tags=["research", "readonly"],
        ),
        AgentProfile(
            name="coder",
            description="读写实施: 按委派范围修改文件(写操作过治理门)",
            system_prompt=_CODER_PROMPT,
            tools=READONLY_TOOLS | WRITE_TOOLS,
            max_steps=25,
            risk_level="medium",
            tags=["coding", "write"],
        ),
        AgentProfile(
            name="critic",
            description="无工具纯审阅: 对给定材料输出问题清单+评分+结论",
            system_prompt=_CRITIC_PROMPT,
            tools=frozenset(),
            max_steps=6,
            tags=["review"],
        ),
    )
}

# 运行时自定义注册(进程级)
_CUSTOM_PROFILES: dict[str, AgentProfile] = {}


def register_profile(profile: AgentProfile, *, override_builtin: bool = False) -> None:
    """注册自定义角色。默认禁止覆盖内置名(防误伤)。"""
    if profile.name in BUILTIN_PROFILES and not override_builtin:
        raise ValueError(f"不能覆盖内置角色: {profile.name}")
    _CUSTOM_PROFILES[profile.name] = profile


def get_profile(name: str) -> AgentProfile | None:
    """按名取角色(自定义优先于内置)。未知返回 None。"""
    return _CUSTOM_PROFILES.get(name) or BUILTIN_PROFILES.get(name)


def list_profiles() -> list[AgentProfile]:
    """全部可用角色(内置+自定义)。"""
    merged = dict(BUILTIN_PROFILES)
    merged.update(_CUSTOM_PROFILES)
    return sorted(merged.values(), key=lambda p: p.name)
