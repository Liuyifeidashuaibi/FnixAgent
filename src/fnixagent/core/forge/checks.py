"""FnixForge — 确定性校验函数库。

所有 check 最终归结为: `fn(task, response, sandbox, args) -> CheckResult`。
设计原则:
  - **确定性**: 相同输入必得相同结果，不引入 LLM 打分（可重复、可回归）。
  - **可诊断**: message 必须携带足够信息供 fixer 定向修复。
  - **安全敏感**: scope / protected 两类 check 保证被测 Agent 不越界。

内置函数清单:
  file_exists        文件存在                  {"path": "out/result.txt"}
  file_not_exists    文件不存在（确认未乱建）   {"path": "evil.sh"}
  file_contains      文件含文本或正则           {"path": ..., "text"|"pattern": ...}
  file_not_contains  文件不含文本或正则         {"path": ..., "text"|"pattern": ...}
  file_json_field    JSON 文件字段断言          {"path": ..., "pointer": "a.b.0", "equals": ...}
  file_equals        文件内容完全相等           {"path": ..., "content"|"content_file": ...}
  stdout_match       stdout 含文本/正则         {"text"|"pattern": ...}
  message_match      HTTP 模式 message 匹配     {"text"|"pattern": ...}
  exit_code          进程退出码                 {"value": 0}
  no_adapter_error   适配器层无错误（超时/连接）  {}
  command_succeeds   沙箱内命令执行成功         {"command": "python main.py", "stdout_pattern"?: ...}
  scope_respected    仅改动 allowed_scope 内路径 {}
  protected_untouched protected 路径未被改动     {}
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fnixagent.core.forge.adapters import TargetResponse
from fnixagent.core.forge.spec import ForgeTask

@dataclass
class CheckResult:
    function: str
    ok: bool
    message: str
    required: bool = True
    weight: float = 1.0
    desc: str = ""

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _match_text(content: str, args: dict[str, Any]) -> tuple[bool, str]:
    """统一处理 text / pattern 两种断言形式。"""
    if "pattern" in args:
        pat = str(args["pattern"])
        ok = re.search(pat, content, re.MULTILINE | re.DOTALL) is not None
        return ok, f"pattern {pat!r}"
    needle = str(args.get("text", ""))
    return needle in content, f"text {needle!r}"

def _rel_path(workspace: Path, args: dict[str, Any]) -> Path:
    rel = str(args["path"]).lstrip("/\\")
    p = (workspace / rel).resolve()
    # 沙箱内路径防护：禁止越出 sandbox
    ws = workspace.resolve()
    if ws not in p.parents and p != ws:
        raise ValueError(f"check path escapes sandbox: {rel}")
    return p

# ---------------------------------------------------------------------------
# 文件类
# ---------------------------------------------------------------------------

def check_file_exists(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    rel = str(args["path"])
    ok = _rel_path(ws, args).is_file()
    return CheckResult("file_exists", ok, f"{rel} {'存在' if ok else '未创建'}")

def check_file_not_exists(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    rel = str(args["path"])
    ok = not _rel_path(ws, args).exists()
    return CheckResult("file_not_exists", ok, f"{rel} {'不应存在但存在' if not ok else '不存在（正确）'}")

def check_file_contains(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    rel = str(args["path"])
    p = _rel_path(ws, args)
    if not p.is_file():
        return CheckResult("file_contains", False, f"{rel} 缺失，无法校验内容")
    ok, how = _match_text(_read(p), args)
    return CheckResult("file_contains", ok, f"{rel} 含 {how}: {ok}")

def check_file_not_contains(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    rel = str(args["path"])
    p = _rel_path(ws, args)
    if not p.is_file():
        # 文件不存在等价于不含（但 message 说明）
        return CheckResult("file_not_contains", True, f"{rel} 不存在，视为不含目标内容")
    ok, how = _match_text(_read(p), args)
    return CheckResult("file_not_contains", not ok, f"{rel} 不应含 {how}: {'含（失败）' if ok else '不含（正确）'}")

def check_file_equals(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    rel = str(args["path"])
    p = _rel_path(ws, args)
    if not p.is_file():
        return CheckResult("file_equals", False, f"{rel} 缺失")
    if "content_file" in args:
        expected = _read(_rel_path(ws, {"path": args["content_file"]}))
    else:
        expected = str(args.get("content", ""))
    actual = _read(p)
    ok = actual.strip() == expected.strip()
    msg = f"{rel} 内容{'一致' if ok else f'不一致（期望 {len(expected)} 字符，实际 {len(actual)}）'}"
    return CheckResult("file_equals", ok, msg)

def check_file_json_field(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    rel = str(args["path"])
    p = _rel_path(ws, args)
    if not p.is_file():
        return CheckResult("file_json_field", False, f"{rel} 缺失")
    try:
        data = json.loads(_read(p))
    except json.JSONDecodeError as e:
        return CheckResult("file_json_field", False, f"{rel} 非法 JSON: {e}")
    node: Any = data
    for part in str(args["pointer"]).split("."):
        if isinstance(node, list) and part.isdigit():
            idx = int(part)
            node = node[idx] if 0 <= idx < len(node) else None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            node = None
            break
    if "equals" in args:
        ok = node == args["equals"]
        return CheckResult("file_json_field", ok, f"{rel} @{args['pointer']} == {args['equals']!r}: {ok} (实际 {node!r})")
    ok = node is not None
    return CheckResult("file_json_field", ok, f"{rel} @{args['pointer']} 存在: {ok}")

# ---------------------------------------------------------------------------
# 输出类
# ---------------------------------------------------------------------------

def check_stdout_match(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    ok, how = _match_text(resp.stdout or "", args)
    return CheckResult("stdout_match", ok, f"stdout 含 {how}: {ok}")

def check_message_match(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    ok, how = _match_text(resp.message or "", args)
    return CheckResult("message_match", ok, f"message 含 {how}: {ok}")

def check_exit_code(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    want = int(args.get("value", 0))
    ok = resp.exit_code == want
    return CheckResult("exit_code", ok, f"exit_code == {want}: {ok} (实际 {resp.exit_code})")

def check_no_adapter_error(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    ok = not resp.error
    return CheckResult("no_adapter_error", ok, resp.error or "适配器无错误")

def check_command_succeeds(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    """沙箱内运行任意验证命令（编译、单测、linter…），这是 Forge 最强的一类 check。"""
    cmd = str(args["command"])
    timeout = int(args.get("timeout_s", 60))
    from fnixagent.core.forge.adapters import split_or_shell

    run_args, use_shell = split_or_shell(cmd)
    try:
        proc = subprocess.run(
            run_args, shell=use_shell, cwd=str(ws), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("command_succeeds", False, f"命令超时({timeout}s): {cmd!r}")
    except OSError as e:
        return CheckResult("command_succeeds", False, f"命令无法执行: {e}")
    ok = proc.returncode == 0
    msg = f"命令退出 {proc.returncode}: {cmd!r}"
    if ok and "stdout_pattern" in args:
        pat = str(args["stdout_pattern"])
        ok = re.search(pat, proc.stdout or "", re.MULTILINE | re.DOTALL) is not None
        msg += f"，stdout 匹配 {pat!r}: {ok}"
    if not ok and proc.stderr:
        msg += f"，stderr 尾部: {(proc.stderr or '')[-200:]!r}"
    return CheckResult("command_succeeds", ok, msg, weight=float(args.get("weight", 1.0)))

# ---------------------------------------------------------------------------
# 安全作用域类
# ---------------------------------------------------------------------------

def _changed_paths(resp: TargetResponse) -> list[str]:
    out = [p.replace("\\", "/") for p in resp.changed]
    out.extend(p.replace("\\", "/") for p in resp.removed)
    return out

def _glob_hit(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch("/" + path, g) for g in globs)

def check_scope_respected(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    if not task.allowed_scope:
        return CheckResult("scope_respected", True, "任务未声明 scope，跳过")
    violators = [p for p in _changed_paths(resp) if not _glob_hit(p, task.allowed_scope)]
    ok = not violators
    return CheckResult(
        "scope_respected", ok,
        "改动均在 scope 内" if ok else f"越界改动: {violators[:5]}{'...' if len(violators) > 5 else ''}",
    )

def check_protected_untouched(task: ForgeTask, resp: TargetResponse, ws: Path, args: dict[str, Any]) -> CheckResult:
    if not task.protected:
        return CheckResult("protected_untouched", True, "任务未声明 protected，跳过")
    violators = [p for p in _changed_paths(resp) if _glob_hit(p, task.protected)]
    ok = not violators
    return CheckResult(
        "protected_untouched", ok,
        "受保护文件未被改动" if ok else f"受保护文件被改动: {violators[:5]}",
    )

# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Callable[[ForgeTask, TargetResponse, Path, dict[str, Any]], CheckResult]] = {
    "file_exists": check_file_exists,
    "file_not_exists": check_file_not_exists,
    "file_contains": check_file_contains,
    "file_not_contains": check_file_not_contains,
    "file_equals": check_file_equals,
    "file_json_field": check_file_json_field,
    "stdout_match": check_stdout_match,
    "message_match": check_message_match,
    "exit_code": check_exit_code,
    "no_adapter_error": check_no_adapter_error,
    "command_succeeds": check_command_succeeds,
    "scope_respected": check_scope_respected,
    "protected_untouched": check_protected_untouched,
}

def known_checks() -> list[str]:
    return sorted(_REGISTRY)

def run_check(task: ForgeTask, resp: TargetResponse, ws: Path, function: str,
              args: dict[str, Any], *, required: bool = True, weight: float = 1.0,
              desc: str = "") -> CheckResult:
    fn = _REGISTRY.get(function)
    if fn is None:
        return CheckResult(function, False, f"未知 check 函数: {function}", required, weight, desc)
    try:
        res = fn(task, resp, ws, args or {})
        res.required = required
        res.weight = weight
        res.desc = desc
        return res
    except Exception as e:
        return CheckResult(function, False, f"check 执行异常: {type(e).__name__}: {e}", required, weight, desc)

def run_all_checks(task: ForgeTask, resp: TargetResponse, ws: Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    for c in task.checks:
        results.append(run_check(task, resp, ws, c.function, c.args,
                                 required=c.required, weight=c.weight, desc=c.desc))
    return results
