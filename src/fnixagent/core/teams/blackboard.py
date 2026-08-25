"""结构化交接黑板 — 工人产出落盘为带 frontmatter 的 Markdown 文档。

MetaGPT 的核心洞察: Agent 间用结构化文档而非自由对话交接,
可显著降低级联幻觉。每个工人的结论以统一契约落盘:

    ---
    task_id: T3
    agent: researcher-1
    role: researcher
    status: success
    duration_ms: 8210
    ---
    # 结论正文(Markdown)

主 Agent 与后续工人通过路径引用读取, 保证交接信息完整、可审计、可 git diff。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
from typing import Any


def write_handover(
    team_dir: str,
    *,
    task_id: str,
    agent: str,
    role: str,
    status: str,
    content: str,
    duration_ms: float = 0.0,
    extra_meta: dict[str, Any] | None = None,
) -> str:
    """写一份交接文档到 {team_dir}/outputs/, 返回文件路径。"""
    out_dir = os.path.join(str(team_dir), "outputs")
    os.makedirs(out_dir, exist_ok=True)
    meta = {
        "task_id": str(task_id),
        "agent": str(agent)[:100],
        "role": str(role)[:40],
        "status": str(status)[:20],
        "duration_ms": round(float(duration_ms), 1),
    }
    if extra_meta:
        meta.update({k: v for k, v in extra_meta.items() if isinstance(v, (str, int, float, bool))})
    frontmatter = json.dumps(meta, ensure_ascii=False, indent=1)
    body = str(content or "").strip() or "(无输出)"
    path = os.path.join(out_dir, f"{os.path.basename(str(task_id)) or 'task'}.md")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(f"---\n{frontmatter}\n---\n\n{body}\n")
    os.replace(tmp, path)
    return path


def read_handover(path: str) -> tuple[dict[str, Any], str]:
    """读交接文档, 返回 (meta_dict, body)。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.startswith("---"):
        return {}, text
    try:
        end = text.index("\n---", 3)
        meta = json.loads(text[3:end].strip())
        body = text[end + 4 :].strip("\n")
        return meta, body
    except (ValueError, json.JSONDecodeError):
        return {}, text


__all__ = ["read_handover", "write_handover"]
