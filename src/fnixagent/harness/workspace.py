"""Harness workspace 管理 — 初始化 ~/.fnix 与项目 .fnix 布局。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fnixagent.harness.paths import (
    config_path,
    fnix_home,
    logs_dir,
    mcp_path,
    memories_dir,
    project_artifacts_dir,
    project_fnix_dir,
    project_index_dir,
    project_skills_dir,
    project_topology_dir,
    sessions_dir,
    skills_dir,
    soul_path,
)

_DEFAULT_CONFIG = """# Fnix Harness 本地配置（非密钥）
# provider: qwen | openai | deepseek | glm | custom
provider = ""
model = ""
# base_url = ""

[mcp]
# servers configured via mcp.json
"""

_DEFAULT_SOUL = """# Fnix Agent

你是 Fnix Harness — 本地优先的 AI 工作台助手。

## 原则
- 数据与 API Key 留在用户本机；不要求云账号
- Work：办公任务交付清晰、可验收
- Code：改动可 Diff、用户 Accept 后写盘
- 简洁直接；说明产物路径与下一步

## 能力
- 阅读与编辑工作区文件
- 运行本地命令（在沙箱策略内）
- 加载 `~/.fnix/skills` 与 `{workspace}/.fnix/skills`
"""

_DEFAULT_MEMORY = """# MEMORY

（Agent 与用户可共同维护的长期记忆。保持简短。）
"""

_DEFAULT_USER = """# USER

（关于用户的偏好：语言、风格、常用工具。可选。）
"""

_DEFAULT_RULES = """# Fnix 项目规则

- 优先将可交付产物写入 `.fnix/artifacts/`
- 修改代码前先阅读相关文件
- 回复简洁，说明产物路径与验收方式

也可在仓库根或子目录放置 `AGENTS.md` / `AGENTS.override.md`（Codex 兼容），
Fnix 会按目录层级注入到 Work / Code 上下文。
"""

_DEFAULT_MCP = {
    "version": 1,
    "servers": [],
}


def ensure_home_layout() -> Path:
    """确保用户级 ~/.fnix 完整布局（对标 Hermes ensure_hermes_home）。"""
    home = fnix_home()
    for sub in (
        home,
        sessions_dir(),
        logs_dir(),
        memories_dir(),
        skills_dir(),
    ):
        sub.mkdir(parents=True, exist_ok=True)

    cfg = config_path()
    if not cfg.is_file():
        cfg.write_text(_DEFAULT_CONFIG, encoding="utf-8")

    soul = soul_path()
    if not soul.is_file():
        soul.write_text(_DEFAULT_SOUL, encoding="utf-8")

    mem = memories_dir() / "MEMORY.md"
    if not mem.is_file():
        mem.write_text(_DEFAULT_MEMORY, encoding="utf-8")

    user = memories_dir() / "USER.md"
    if not user.is_file():
        user.write_text(_DEFAULT_USER, encoding="utf-8")

    mcp = mcp_path()
    if not mcp.is_file():
        import json

        mcp.write_text(
            json.dumps(_DEFAULT_MCP, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    skills_readme = skills_dir() / "README.md"
    if not skills_readme.is_file():
        skills_readme.write_text(
            "# 全局技能\n\n放置 `*.md` 技能文件；Work/Code 会加载并注入上下文。\n",
            encoding="utf-8",
        )

    return home


def ensure_project_layout(workspace: str | os.PathLike[str]) -> dict[str, Any]:
    """打开/绑定 workspace 时创建项目级 .fnix 结构。"""
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"workspace 不是有效目录: {workspace}")

    ensure_home_layout()

    fnix_dir = project_fnix_dir(root)
    skills = project_skills_dir(root)
    artifacts = project_artifacts_dir(root)
    topology = project_topology_dir(root)
    index = project_index_dir(root)

    for path in (fnix_dir, skills, artifacts, topology, index):
        path.mkdir(parents=True, exist_ok=True)

    rules = fnix_dir / "rules.md"
    if not rules.is_file():
        rules.write_text(_DEFAULT_RULES, encoding="utf-8")

    sample = skills / "README.md"
    if not sample.is_file():
        sample.write_text(
            "# 项目技能\n\n在此目录放置 `*.md` 技能文件，Fnix 会在 Work/Code 任务中加载。\n",
            encoding="utf-8",
        )

    return {
        "workspace": str(root),
        "fnix": str(fnix_dir),
        "skills": str(skills),
        "artifacts": str(artifacts),
        "topology": str(topology),
        "index": str(index),
    }


def read_home_config() -> dict[str, Any]:
    """读取 ~/.fnix/config.toml（兼容旧调用）。"""
    from fnixagent.harness.config import read_config_toml

    return read_config_toml()
