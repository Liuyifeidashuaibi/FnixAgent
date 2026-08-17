"""已 Accept 变更集落盘 — 支持跨请求一键撤销。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fnixagent.harness.paths import project_fnix_dir


def _dir(workspace: str | os.PathLike[str]) -> Path:
    d = project_fnix_dir(workspace) / "changesets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_changeset(
    workspace: str,
    changeset_id: str,
    changes: list[dict[str, Any]],
) -> Path:
    """持久化变更（含 old/new，供 rollback）。"""
    path = _dir(workspace) / f"{changeset_id}.json"
    payload = {
        "id": changeset_id,
        "workspace": str(Path(workspace).resolve()),
        "changes": changes,
    }
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    latest = _dir(workspace) / "latest.json"
    latest.write_text(
        json.dumps({"changeset_id": changeset_id}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_changeset(workspace: str, changeset_id: str) -> dict[str, Any] | None:
    path = _dir(workspace) / f"{changeset_id}.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def latest_changeset_id(workspace: str) -> str | None:
    path = _dir(workspace) / "latest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cid = data.get("changeset_id")
        return str(cid) if cid else None
    except (OSError, json.JSONDecodeError):
        return None


async def rollback_persisted_async(
    workspace: str,
    changeset_id: str | None = None,
) -> dict[str, Any]:
    """按落盘记录回滚；未指定 id 则回滚 latest。"""
    from fnixagent.core.code.diff import ChangeSetBuilder, DiffEngine

    cid = changeset_id or latest_changeset_id(workspace)
    if not cid:
        return {"ok": False, "error": "没有可撤销的变更集"}
    data = load_changeset(workspace, cid)
    if not data:
        return {"ok": False, "error": f"变更集不存在: {cid}"}

    engine = DiffEngine(project_root=workspace)
    builder = ChangeSetBuilder(f"rollback {cid}")
    for ch in data.get("changes") or []:
        if not isinstance(ch, dict):
            continue
        action = str(ch.get("action") or ch.get("change_type") or "modify").lower()
        path = str(ch.get("path") or "")
        if not path:
            continue
        new_content = ch.get("content") if ch.get("content") is not None else ch.get("new_content")
        old_content = ch.get("old_content")
        if action == "create":
            builder.delete_file(path, new_content or "")
        elif action == "delete":
            builder.create_file(path, old_content or "")
        else:
            # 磁盘上是 new，回到 old
            builder.modify_file(path, new_content or "", old_content or "")

    cs = builder.build()
    result = await engine.apply(cs, dry_run=False)
    if result.success:
        latest = _dir(workspace) / "latest.json"
        try:
            if latest.is_file():
                latest.unlink()
        except OSError:
            pass
    return {
        "ok": result.success,
        "changeset_id": cid,
        "error": result.error or "",
        "applied": len(result.applied_files or []),
    }
