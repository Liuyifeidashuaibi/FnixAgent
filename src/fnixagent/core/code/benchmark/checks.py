"""Declarative check functions for code benchmark tasks."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import py_compile
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STUB_PATTERNS = (
    r"功能开发中",
    r"TODO:\s*implement",
    r"not implemented",
    r"pass\s*#\s*stub",
)


@dataclass
class CheckResult:
    function: str
    ok: bool
    message: str
    required: bool = True
    weight: float = 1.0


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def check_file_exists(workspace: Path, args: dict[str, Any]) -> CheckResult:
    rel = args["path"]
    p = workspace / rel
    ok = p.is_file()
    return CheckResult("file_exists", ok, f"{rel} {'exists' if ok else 'missing'}")


def check_file_contains(workspace: Path, args: dict[str, Any]) -> CheckResult:
    rel = args["path"]
    p = workspace / rel
    if not p.is_file():
        return CheckResult("file_contains", False, f"{rel} missing")
    text = _read(p)
    if "pattern" in args:
        ok = re.search(args["pattern"], text, re.MULTILINE | re.DOTALL) is not None
        needle = args["pattern"]
    else:
        needle = args.get("text", "")
        ok = needle in text
    return CheckResult("file_contains", ok, f"{rel} contains {needle!r}: {ok}")


def check_file_not_contains(workspace: Path, args: dict[str, Any]) -> CheckResult:
    rel = args["path"]
    p = workspace / rel
    if not p.is_file():
        return CheckResult("file_not_contains", True, f"{rel} missing (vacuous)")
    text = _read(p)
    needle = args.get("text", "")
    ok = needle not in text
    return CheckResult("file_not_contains", ok, f"{rel} excludes {needle!r}: {ok}")


def check_compile_ok(workspace: Path, args: dict[str, Any]) -> CheckResult:
    rel = args["path"]
    p = workspace / rel
    if not p.is_file():
        return CheckResult("compile_ok", False, f"{rel} missing")
    try:
        py_compile.compile(str(p), doraise=True)
        return CheckResult("compile_ok", True, f"{rel} compiles")
    except py_compile.PyCompileError as e:
        return CheckResult("compile_ok", False, str(e))


def check_pytest_passes(workspace: Path, args: dict[str, Any]) -> CheckResult:
    target = args.get("path", ".")
    cmd = [sys.executable, "-m", "pytest", "-q", str(workspace / target)]
    if args.get("extra_args"):
        cmd.extend(args["extra_args"])
    try:
        proc = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=int(args.get("timeout_s", 120)),
        )
        ok = proc.returncode == 0
        tail = (proc.stdout + proc.stderr)[-400:]
        return CheckResult("pytest_passes", ok, tail.strip() or f"exit {proc.returncode}")
    except subprocess.TimeoutExpired:
        return CheckResult("pytest_passes", False, "pytest timeout")


def check_stdout_equals(workspace: Path, args: dict[str, Any]) -> CheckResult:
    cmd = args["command"]
    if isinstance(cmd, str):
        cmd = cmd.split()
    try:
        proc = subprocess.run(
            cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=int(args.get("timeout_s", 30)),
        )
        expected = args.get("expected", "").strip()
        actual = proc.stdout.strip()
        ok = proc.returncode == 0 and actual == expected
        return CheckResult(
            "stdout_equals",
            ok,
            f"expected {expected!r} got {actual!r} (rc={proc.returncode})",
        )
    except subprocess.TimeoutExpired:
        return CheckResult("stdout_equals", False, "command timeout")


def check_no_stub_content(workspace: Path, args: dict[str, Any]) -> CheckResult:
    rel = args.get("path", "")
    paths = [workspace / rel] if rel else list(workspace.rglob("*.py"))
    hits: list[str] = []
    for p in paths:
        if not p.is_file():
            continue
        text = _read(p)
        for pat in STUB_PATTERNS:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(f"{p.relative_to(workspace)}:{pat}")
    ok = len(hits) == 0
    return CheckResult("no_stub_content", ok, "; ".join(hits) or "clean")


def check_heal_rounds_lte(
    _workspace: Path, args: dict[str, Any], meta: dict[str, Any]
) -> CheckResult:
    limit = int(args.get("max", 3))
    rounds = int(meta.get("heal_rounds", 0))
    ok = rounds <= limit
    return CheckResult("heal_rounds_lte", ok, f"heal_rounds={rounds} limit={limit}")


CHECK_REGISTRY: dict[str, Callable[..., CheckResult]] = {
    "file_exists": check_file_exists,
    "file_contains": check_file_contains,
    "file_not_contains": check_file_not_contains,
    "compile_ok": check_compile_ok,
    "pytest_passes": check_pytest_passes,
    "stdout_equals": check_stdout_equals,
    "no_stub_content": check_no_stub_content,
    "heal_rounds_lte": check_heal_rounds_lte,
}


def run_check(
    workspace: Path,
    function: str,
    args: dict[str, Any],
    *,
    required: bool = True,
    weight: float = 1.0,
    meta: dict[str, Any] | None = None,
) -> CheckResult:
    fn = CHECK_REGISTRY.get(function)
    if fn is None:
        return CheckResult(
            function, False, f"unknown check: {function}", required=required, weight=weight
        )
    meta = meta or {}
    if function == "heal_rounds_lte":
        result = fn(workspace, args, meta)
    else:
        result = fn(workspace, args)
    result.required = required
    result.weight = weight
    return result
