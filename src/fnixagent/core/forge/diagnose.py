"""FnixForge — 失败诊断。

把一轮测评的 TaskRunRecord 聚类为可供修复的"问题簇"：

  聚类维度（按优先级）：
    1. error 签名（adapter 超时 / 连接失败 / 进程崩溃 → 接入层问题）
    2. 失败 check 函数（file_contains 失败 = 没写对内容；stdout 失败 = 没输出…）
    3. capability（同类能力反复失败 = 系统性缺陷）

  同时构建 **根因定位上下文**：在目标项目源码中按关键字做启发式搜索，
  为 fixer 准备 "最可能相关的文件清单"，避免让 LLM 无头苍蝇式读全仓。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from fnixagent.core.forge.runner import TaskRunRecord

_SOURCE_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h"}
_SKIP_DIR = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
_MAX_FILES = 200
_MAX_FILE_BYTES = 64_000
_MAX_TOTAL_BYTES = 400_000

@dataclass
class FailureCluster:
    key: str                       # 聚类键（人类可读）
    category: str                  # adapter | output | file | scope | behavior
    task_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)   # 失败 check message
    capability: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key, "category": self.category,
            "capability": self.capability, "task_ids": self.task_ids,
            "evidence": self.evidence[:10],
            "count": len(self.task_ids),
        }

def _error_signature(rec: TaskRunRecord) -> str | None:
    err = (rec.response.error or "").lower()
    if not err:
        return None
    if "timeout" in err:
        return "adapter-timeout"
    if any(k in err for k in ("connection", "refused", "unreachable", "urlopen")):
        return "adapter-connection"
    return "adapter-crash"

def _primary_failed_check(rec: TaskRunRecord) -> tuple[str, str] | None:
    for c in rec.score.checks:
        if not c["ok"] and c["required"]:
            return c["function"], c["message"]
    return None

_CATEGORY_MAP = {
    "file_exists": "file", "file_not_exists": "file", "file_contains": "file",
    "file_not_contains": "file", "file_equals": "file", "file_json_field": "file",
    "stdout_match": "output", "message_match": "output", "exit_code": "output",
    "no_adapter_error": "adapter", "command_succeeds": "behavior",
    "scope_respected": "scope", "protected_untouched": "scope",
}

def cluster_failures(records: list[TaskRunRecord]) -> list[FailureCluster]:
    clusters: dict[str, FailureCluster] = {}
    for rec in records:
        if rec.score.passed:
            continue
        sig = _error_signature(rec)
        if sig is not None:
            key, category = sig, "adapter"
        else:
            fc = _primary_failed_check(rec)
            if fc is None:
                continue
            check_fn, _msg = fc
            key = f"check:{check_fn}"
            category = _CATEGORY_MAP.get(check_fn, "behavior")
        cl = clusters.get(key)
        if cl is None:
            cl = clusters[key] = FailureCluster(
                key=key, category=category, capability=rec.score.capability
            )
        cl.task_ids.append(rec.task_id)
        for c in rec.score.checks:
            if not c["ok"]:
                cl.evidence.append(f"[{rec.task_id}] {c['function']}: {c['message'][:160]}")
    return sorted(clusters.values(), key=lambda c: -len(c.task_ids))

# ---------------------------------------------------------------------------
# 根因定位上下文
# ---------------------------------------------------------------------------

_KEYWORDS_BY_CATEGORY = {
    "adapter": ["main", "entry", "cli", "argparse", "click", "serve", "app"],
    "output":  ["print", "stdout", "output", "response", "message", "format", "json"],
    "file":    ["open", "write", "path", "file", "save", "read"],
    "scope":   ["write", "delete", "remove", "workspace", "cwd", "path"],
    "behavior": ["run", "exec", "test", "command", "tool"],
}

def _iter_source_files(root: Path):
    count = 0
    for p in sorted(root.rglob("*")):
        if count >= _MAX_FILES:
            break
        if not p.is_file() or p.suffix.lower() not in _SOURCE_EXT:
            continue
        rel = p.relative_to(root).parts
        if any(part in _SKIP_DIR for part in rel):
            continue
        try:
            if p.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        count += 1
        yield p

def guess_relevant_files(target_root: Path, clusters: list[FailureCluster], limit: int = 8) -> list[dict]:
    """按聚类关键词在目标项目源码中打分，返回最可能相关的文件。

    评分为纯启发式：文件名命中 ×3 + 内容行命中 ×1，每个文件截断展示前若干命中行。
    """
    keywords: set[str] = set()
    for cl in clusters[:3]:
        keywords.update(_KEYWORDS_BY_CATEGORY.get(cl.category, ()))
    keywords = {k.lower() for k in keywords}
    if not keywords:
        return []

    scored: list[tuple[int, Path, list[str]]] = []
    total_bytes = 0
    for p in _iter_source_files(target_root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total_bytes += len(text)
        if total_bytes > _MAX_TOTAL_BYTES:
            break
        score = 0
        hits: list[str] = []
        name_l = p.name.lower()
        for kw in keywords:
            if kw in name_l:
                score += 3
        for line in text.splitlines():
            low = line.lower()
            if any(kw in low for kw in keywords):
                score += 1
                if len(hits) < 4:
                    hits.append(line.strip()[:140])
        if score > 0:
            scored.append((score, p, hits))
    scored.sort(key=lambda t: -t[0])
    return [
        {
            "path": str(p.relative_to(target_root)).replace("\\", "/"),
            "score": s,
            "sample_lines": hits,
        }
        for s, p, hits in scored[:limit]
    ]

def build_diagnosis(records: list[TaskRunRecord], target_root: Path) -> dict:
    """完整诊断报告（dict，可直接序列化 / 喂给 fixer）。"""
    clusters = cluster_failures(records)
    relevant = guess_relevant_files(target_root, clusters) if clusters else []
    failed_rec = [r for r in records if not r.score.passed]
    return {
        "failed_tasks": len(failed_rec),
        "clusters": [c.to_dict() for c in clusters],
        "relevant_files": relevant,
        "failure_traces": [r.to_dict() for r in failed_rec[:6]],
    }
