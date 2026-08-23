"""FnixForge — 被测项目的调用方式自动探测。

用户的半成品 Agent 形态未知：可能是 Python 包、Node CLI、HTTP 服务、
或者只有一份 README 写着 "python main.py"。probe 通过读取项目骨架
（清单文件 / 入口脚本 / README）推断最可能的调用方式，产出:

  ProbeResult.config  — 可直接使用的 AdapterConfig（可能为 None 表示无法推断）
  ProbeResult.notes   — 人类可读的推断依据与建议

探测策略按确定性排序：
  1. 已有 forge.config.json（人工接入过）
  2. Python: pyproject.toml / setup.py / main.py / app.py / cli.py
  3. Node:   package.json bin / scripts
  4. HTTP:   README / 配置中出现明显的服务端口与路由模式
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fnixagent.core.forge.adapters import CONFIG_FILENAME, AdapterConfig

# 常见的 agent 主力入口脚本候选名
_PY_ENTRY_CANDIDATES = (
    "main.py", "app.py", "cli.py", "run.py", "agent.py", "src/main.py",
)
_NODE_EMBEDDED_HINTS = ("openai", "anthropic", "langchain", "llamaindex", "@langchain")
_PY_EMBEDDED_HINTS = ("openai", "anthropic", "langchain", "llama_index", "agno", "crewai")
_README_MAX = 200_000

@dataclass
class ProbeResult:
    config: AdapterConfig | None = None
    confidence: str = "none"          # high | medium | low | none
    kind: str = ""                    # py-cli | node-cli | http | unknown
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "kind": self.kind,
            "config": self.config.to_dict() if self.config else None,
            "notes": list(self.notes),
        }

def _read_text(p: Path, limit: int = _README_MAX) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""

def _find_readme(root: Path) -> Path | None:
    for name in ("README.md", "README.MD", "readme.md", "README.txt", "README"):
        p = root / name
        if p.is_file():
            return p
    return None

def _grep_patterns(text: str, patterns: list[str]) -> list[str]:
    hits = []
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            hits.append(m.group(0)[:200])
    return hits

def _probe_python(root: Path, result: ProbeResult) -> None:
    pyproject = root / "pyproject.toml"
    entry = next((root / c for c in _PY_ENTRY_CANDIDATES if (root / c).is_file()), None)
    setup_py = root / "setup.py"
    requirements = root / "requirements.txt"

    likely_agent = False
    if pyproject.is_file():
        toml_text = _read_text(pyproject)
        if any(h in toml_text.lower() for h in _PY_EMBEDDED_HINTS):
            likely_agent = True
            result.notes.append("pyproject.toml 依赖中含 LLM/agent 框架特征")
    if requirements.is_file():
        req_text = _read_text(requirements)
        if any(h in req_text.lower() for h in _PY_EMBEDDED_HINTS):
            likely_agent = True
            result.notes.append("requirements.txt 依赖中含 LLM/agent 框架特征")

    if entry is not None:
        # 使用 {workspace} 作为 cwd，prompt 通过 base64 环境变量传入；
        # 但大多数半成品 CLI 只接受位置参数，故默认用 --prompt-file 风格不适用。
        # 这里生成最通用模板：把 b64 prompt 注入环境变量，命令本身只接收 workspace。
        result.config = AdapterConfig(
            type="cli",
            command=f'python "{entry.name}" "$FNIX_FORGE_WORKSPACE"',
            env={},
        )
        result.kind = "py-cli"
        result.confidence = "medium" if likely_agent else "low"
        result.notes.append(f"发现入口脚本 {entry.name}，按 python 直接执行推断")
        if not likely_agent:
            result.notes.append("未发现 agent/LLM 依赖特征，人工确认命令参数约定")
    elif setup_py.is_file() or pyproject.is_file():
        result.kind = "py-cli"
        result.confidence = "low"
        result.notes.append("发现 Python 包清单但未找到入口脚本，建议人工配置 forge.config.json")

def _probe_node(root: Path, result: ProbeResult) -> None:
    pkg = root / "package.json"
    if not pkg.is_file():
        return
    try:
        data = json.loads(_read_text(pkg))
    except json.JSONDecodeError:
        result.notes.append("package.json 解析失败")
        return

    bin_field = data.get("bin")
    if isinstance(bin_field, str):
        result.config = AdapterConfig(type="cli", command=f'node "{bin_field}" "$FNIX_FORGE_WORKSPACE"')
        result.confidence = "medium"
        result.kind = "node-cli"
        result.notes.append(f"package.json bin 指向 {bin_field}")
        return
    if isinstance(bin_field, dict) and bin_field:
        first = next(iter(bin_field.values()))
        result.config = AdapterConfig(type="cli", command=f'node "{first}" "$FNIX_FORGE_WORKSPACE"')
        result.confidence = "medium"
        result.kind = "node-cli"
        result.notes.append(f"package.json bin 指向 {first}")
        return

    scripts = data.get("scripts") or {}
    deps = json.dumps(data, ensure_ascii=False).lower()
    agentish = any(h in deps for h in _NODE_EMBEDDED_HINTS)
    for candidate in ("start", "agent", "dev"):
        if candidate in scripts:
            result.config = AdapterConfig(
                type="cli", command=f"npm run --silent {candidate} -- \"$FNIX_FORGE_WORKSPACE\""
            )
            result.confidence = "medium" if agentish else "low"
            result.kind = "node-cli"
            result.notes.append(f"按 npm run {candidate} 推断入口")
            if not agentish:
                result.notes.append("未发现 LLM/agent 依赖特征，人工确认")
            return

def _probe_http(root: Path, result: ProbeResult) -> None:
    readme = _find_readme(root)
    text = _read_text(readme) if readme else ""
    hits = _grep_patterns(
        text,
        [
            r"http://(?:localhost|127\.0\.0\.1):\d{2,5}/[\w/{}-]*",
            r"POST\s+/[\w/{}-]+",
            r"uvicorn\s+[\w.]+:\w+|fastapi|flask|express",
        ],
    )
    if not hits:
        return
    url = next((h for h in hits if h.startswith("http")), None)
    result.kind = "http"
    result.confidence = "low"
    result.notes.append(f"README 中出现服务化特征: {hits[:3]}")
    if url:
        result.config = AdapterConfig(
            type="http",
            endpoint=url,
            body_template={"prompt": "{prompt}", "workspace": "{workspace}"},
        )
        result.notes.append(f"按 README 推断 HTTP endpoint: {url}")

def probe_target(target_root: Path | str) -> ProbeResult:
    root = Path(target_root).resolve()
    result = ProbeResult()

    if not root.is_dir():
        result.notes.append(f"目标目录不存在: {root}")
        return result

    existing = AdapterConfig.load(root)
    if existing is not None:
        result.config = existing
        result.confidence = "high"
        result.kind = existing.type
        result.notes.append(f"已存在 {CONFIG_FILENAME}，直接采用")
        return result

    _probe_python(root, result)
    if result.config is not None:
        return result
    _probe_node(root, result)
    if result.config is not None:
        return result
    _probe_http(root, result)
    if result.config is not None:
        return result

    if not result.confidence or result.confidence == "none":
        result.kind = "unknown"
        n_files = sum(1 for _ in root.iterdir())
        result.notes.append(f"无法自动推断（根目录 {n_files} 项），请人工编写 {CONFIG_FILENAME}")
    return result

def propose_adapter_config(target_root: Path | str) -> dict[str, Any]:
    """CLI/API 友好包装。"""
    return probe_target(target_root).to_dict()
