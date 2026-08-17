"""Programmatic generation of benchmark tasks from templates."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

# Template families: (capability, base difficulty) -> generator params
OPS = ["add", "sub", "mul", "div"]
NAMES = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]


def _calc_task(op: str, a: int, b: int, variant: int) -> dict[str, Any]:
    tid = f"gen.calc.{op}.{a}.{b}.v{variant}"
    if op == "add":
        body = "    return a + b"
        test = f"assert calc({a}, {b}) == {a + b}"
    elif op == "sub":
        body = "    return a - b"
        test = f"assert calc({a}, {b}) == {a - b}"
    elif op == "mul":
        body = "    return a * b"
        test = f"assert calc({a}, {b}) == {a * b}"
    else:
        body = "    if b == 0:\n        raise ValueError('div by zero')\n    return a // b"
        test = f"assert calc({a}, {b}) == {a // b}"

    broken = variant % 3 == 1
    if broken:
        src = """def calc(a, b):\n    return 0  # bug\n"""
    else:
        src = f"def calc(a, b):\n{body}\n"

    prompt = f"Implement `calc(a, b)` in `calc.py` for integer {op}. " + (
        "Fix the bug so tests pass." if broken else "Make tests pass."
    )

    return {
        "id": tid,
        "title": f"calc {op} ({a},{b})",
        "prompt": prompt,
        "capability": ["bugfix" if broken else "write", "edit"],
        "difficulty": 1 + (variant % 3),
        "language": "python",
        "tags": ["generated", "calc", op, "smoke" if variant < 5 else "full"],
        "timeout_s": 120,
        "setup": {
            "files": {
                "calc.py": src,
                "test_calc.py": f"from calc import calc\n\n\ndef test_op():\n    {test}\n",
            }
        },
        "checks": [
            {"function": "compile_ok", "args": {"path": "calc.py"}},
            {"function": "pytest_passes", "args": {"path": "test_calc.py"}},
            {"function": "no_stub_content", "args": {}},
        ],
    }


def _greeter_task(name: str, variant: int) -> dict[str, Any]:
    tid = f"gen.cli.greet.{name}.v{variant}"
    broken = variant % 2 == 0
    if broken:
        main_src = """def main():\n    print("hello")\n\nif __name__ == "__main__":\n    main()\n"""
        prompt = f"Fix `main.py` so running `python main.py {name}` prints exactly `Hello, {name}!`"
        cap = ["bugfix", "cli"]
    else:
        main_src = "pass\n"
        prompt = f"Create `main.py` CLI: `python main.py {name}` prints `Hello, {name}!`"
        cap = ["write", "cli"]

    return {
        "id": tid,
        "title": f"greet {name}",
        "prompt": prompt,
        "capability": cap,
        "difficulty": 2 if broken else 1,
        "language": "python",
        "tags": ["generated", "cli", "smoke" if variant < 3 else "full"],
        "timeout_s": 120,
        "setup": {"files": {"main.py": main_src}},
        "checks": [
            {
                "function": "stdout_equals",
                "args": {
                    "command": ["python", "main.py", name],
                    "expected": f"Hello, {name}!",
                },
            },
            {"function": "no_stub_content", "args": {"path": "main.py"}},
        ],
    }


def _multi_file_task(prefix: str, variant: int) -> dict[str, Any]:
    tid = f"gen.multi.{prefix}.v{variant}"
    return {
        "id": tid,
        "title": f"package {prefix}",
        "prompt": (
            f"Create package `{prefix}` with `__init__.py` exporting `run()` "
            f"and `{prefix}/core.py` implementing `run()` returning '{prefix}-ok'."
        ),
        "capability": ["multi_file", "write"],
        "difficulty": 3,
        "language": "python",
        "tags": ["generated", "multi_file"],
        "timeout_s": 180,
        "setup": {"files": {"README.md": f"# {prefix}\n"}},
        "checks": [
            {"function": "file_exists", "args": {"path": f"{prefix}/__init__.py"}},
            {"function": "file_exists", "args": {"path": f"{prefix}/core.py"}},
            {
                "function": "stdout_equals",
                "args": {
                    "command": [
                        "python",
                        "-c",
                        f"from {prefix} import run; print(run())",
                    ],
                    "expected": f"{prefix}-ok",
                },
            },
        ],
    }


def generate_tasks(count: int, seed: int = 42) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    tasks: list[dict[str, Any]] = []
    i = 0
    while len(tasks) < count:
        kind = i % 3
        variant = i
        if kind == 0:
            op = OPS[i % len(OPS)]
            a, b = rng.randint(1, 20), rng.randint(1, 10)
            if op == "div":
                b = max(1, b)
            tasks.append(_calc_task(op, a, b, variant))
        elif kind == 1:
            name = NAMES[i % len(NAMES)]
            tasks.append(_greeter_task(name, variant))
        else:
            prefix = f"pkg_{NAMES[i % len(NAMES)]}_{variant % 100}"
            tasks.append(_multi_file_task(prefix, variant))
        i += 1
    return tasks[:count]


def write_generated(tasks: list[dict[str, Any]], out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ids: list[str] = []
    for t in tasks:
        p = out_dir / f"{t['id']}.json"
        p.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")
        ids.append(t["id"])
    return ids
