"""Run benchmark tasks in isolated workspaces."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from fnixagent.core.code.benchmark.agent_client import apply_changes, ensure_workspace, stream_agent
from fnixagent.core.code.benchmark.checks import run_check
from fnixagent.core.code.benchmark.schema import TaskSpec, load_task, validate_task
from fnixagent.core.code.benchmark.scorer import TaskRunMeta, TaskScore, score_task


@dataclass
class RunOptions:
    dry_checks_only: bool = False
    agent_base_url: str = ""
    skip_agent: bool = False
    retrieval_context: str = ""  # Context to inject into the prompt
    reasoning_mode: str = ""  # "react" or "plan_execute"
    max_steps_hint: int = 0  # Step budget hint
    extra_instructions: str = ""  # Additional system-level instructions


def materialize_workspace(task: TaskSpec, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    files = (task.setup or {}).get("files") or {}
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def run_checks(task: TaskSpec, workspace: Path, meta: TaskRunMeta) -> list:
    results = []
    meta_dict = {
        "heal_rounds": meta.heal_rounds,
        "steps": meta.steps,
        "elapsed_s": meta.elapsed_s,
    }
    for spec in task.checks:
        r = run_check(
            workspace,
            spec.function,
            spec.args,
            required=spec.required,
            weight=spec.weight,
            meta=meta_dict,
        )
        results.append(r)
    return results


def invoke_agent(
    task: TaskSpec, workspace: Path, base_url: str, opts: RunOptions | None = None
) -> TaskRunMeta:
    ensure_workspace(base_url, workspace)
    run = stream_agent(
        base_url,
        task.prompt,
        str(workspace),
        preview=True,
        timeout=task.timeout_s,
        retrieval_context=opts.retrieval_context if opts else "",
        reasoning_mode=opts.reasoning_mode if opts else "",
        max_steps_hint=opts.max_steps_hint if opts else 0,
        extra_instructions=opts.extra_instructions if opts else "",
    )
    meta = TaskRunMeta(
        elapsed_s=run.elapsed_s,
        steps=run.steps,
        heal_rounds=run.heal_rounds,
        tool_calls=run.tool_calls,
        agent_error=run.error,
    )
    if run.error and not run.changes:
        return meta
    if run.changes:
        applied = apply_changes(base_url, str(workspace), run.changes)
        if applied.get("ok"):
            # Non-fatal stream warnings should not fail hard_pass when apply succeeded.
            meta.agent_error = ""
        else:
            meta.agent_error = meta.agent_error or str(applied.get("error") or "apply failed")
    return meta


def run_task(task_path: Path, options: RunOptions | None = None) -> TaskScore:
    options = options or RunOptions()
    task = load_task(task_path)
    errors = validate_task(task)
    if errors:
        meta = TaskRunMeta(agent_error="; ".join(errors))
        return score_task(task, [], meta)

    with tempfile.TemporaryDirectory(prefix="fcs-") as tmp:
        workspace = materialize_workspace(task, Path(tmp))
        t0 = time.perf_counter()
        if options.dry_checks_only or options.skip_agent or not options.agent_base_url:
            meta = TaskRunMeta(elapsed_s=0.0, steps=0, heal_rounds=0, tool_calls=0)
        else:
            meta = invoke_agent(task, workspace, options.agent_base_url, options)
        if meta.elapsed_s <= 0:
            meta.elapsed_s = time.perf_counter() - t0
        results = run_checks(task, workspace, meta)
        return score_task(task, results, meta)


def load_manifest(manifest_path: Path) -> list[str]:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(data.get("tasks") or [])


def resolve_task_paths(benchmark_root: Path, task_ids: list[str]) -> list[Path]:
    paths: list[Path] = []
    for tid in task_ids:
        for sub in ("seed", "generated"):
            p = benchmark_root / sub / f"{tid}.json"
            if p.is_file():
                paths.append(p)
                break
    return paths
