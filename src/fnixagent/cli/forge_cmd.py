"""FnixForge CLI — 他人 Agent 的测评与自动修复。

  fnixagent forge suites                    列出内置 benchmark 套件
  fnixagent forge probe <dir> [--write]     探测目标 Agent 的调用方式
  fnixagent forge test  <dir> [--suite S]   只测评（不修改目标项目）
  fnixagent forge fix   <dir> [--suite S] [--rounds N] [--threshold P]
                                            测评 + 自动修复 + 复测闭环
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import sys
from pathlib import Path

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_DIM = "\033[90m"
_RESET = "\033[0m"

def _c(text: str, color: str) -> str:
    if sys.stdout.isatty():
        return f"{color}{text}{_RESET}"
    return text

def _print_event(ev: dict) -> None:
    kind = ev.get("event")
    if kind == "task_start":
        print(f"  {_c('▶', _DIM)} [{ev['i']}/{ev['n']}] {ev['task_id']} ...", end="\r", flush=True)
    elif kind == "task_end":
        icon = _c("✓", _GREEN) if ev["passed"] else _c("✗", _RED)
        print(f"  {icon} [{ev['i']}/{ev['n']}] {ev['task_id']}  {ev['score']:.0f}分        ")
    elif kind == "round_start":
        print(f"\n== Round {ev['round']}  共 {ev['tasks']} 题 ==")
    elif kind == "round_end":
        print(f"-- Round {ev['round']} 结束: 通过 {ev['passed']}/{ev['total']}，"
              f"加权分 {ev['overall']:.1f}%")
    elif kind == "diagnosed":
        print(_c(f"  诊断: {ev['clusters']} 个失败簇，相关文件: "
                 f"{', '.join(ev.get('relevant_files', [])[:4]) or '(无)'}", _YELLOW))
    elif kind == "fix_proposed":
        print(_c(f"  修复提案落盘: {', '.join(ev['paths'])}", _YELLOW))
    elif kind == "fix_decision":
        color = _GREEN if ev["decision"] == "kept" else _RED
        print(_c(f"  修复裁决: {ev['decision']} — {ev['note']}", color))
    elif kind == "done":
        ready = ev.get("production_ready")
        verdict = _c("PRODUCTION READY", _GREEN) if ready else _c("尚未达到生产级", _RED)
        print(f"\n{verdict}  最终: 通过 {ev['passed']}/{ev['tasks']}，"
              f"总分 {ev['overall_score']:.1f}%，共 {ev['rounds']} 轮")

def run_forge(args) -> int:
    from fnixagent.core.forge import (
        AdapterConfig,
        ForgeLoop,
        list_suites,
        probe_target,
        write_html_report,
        write_json_report,
    )

    sub = getattr(args, "forge_cmd", None)

    if sub == "suites":
        suites = list_suites()
        if not suites:
            print("未找到内置套件（benchmarks/forge/suites 缺失）")
            return 1
        print(f"{'ID':<10} {'任务数':<6} 说明")
        for s in suites:
            print(f"{s['id']:<10} {s.get('tasks', 0):<6}  {s.get('description', '')}")
        return 0

    target = Path(args.target).resolve()
    if not target.is_dir():
        print(_c(f"目标目录不存在: {target}", _RED))
        return 2

    if sub == "probe":
        res = probe_target(target)
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
        if args.write and res.config is not None:
            path = res.config.save(target)
            print(_c(f"已写入 {path}", _GREEN))
        elif res.config is not None:
            print(_c("（加 --write 可将该配置写入目标目录 forge.config.json）", _DIM))
        return 0 if res.config is not None else 1

    if sub not in ("test", "fix"):
        print("未知 forge 子命令")
        return 2

    config = None
    if getattr(args, "config", None):
        cfg_path = Path(args.config)
        if not cfg_path.is_file():
            print(_c(f"配置文件不存在: {cfg_path}", _RED))
            return 2
        config = AdapterConfig.from_dict(json.loads(cfg_path.read_text(encoding="utf-8")))

    print(_c(f"FnixForge  目标: {target}", _DIM))
    print(_c(f"套件: {args.suite}   模式: {sub}   上限轮次: {getattr(args, 'rounds', 1)}", _DIM))

    try:
        loop = ForgeLoop(
            target,
            suite=args.suite,
            mode=sub,
            max_rounds=getattr(args, "rounds", 1) if sub == "fix" else 1,
            adapter_config=config,
            keep_sandboxes=getattr(args, "keep", False),
            fix_threshold=getattr(args, "threshold", 90.0),
            on_event=_print_event,
        )
        result = loop.run()
    except (RuntimeError, FileNotFoundError) as e:
        print(_c(f"执行失败: {e}", _RED))
        return 3

    if getattr(args, "report", None):
        out = Path(args.report)
        json_path = out if out.suffix == ".json" else out.with_suffix(".json")
        html_path = out.with_suffix(".html")
        write_json_report(result.to_dict(), json_path)
        write_html_report(result.to_dict(), html_path)
        print(f"\n报告: {json_path}")
        print(f"      {html_path}")

    return 0 if result.readiness.get("ready") or result.final.get("passed") else 0
