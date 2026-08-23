"""
Completeness Check — AST 解析 + 多语言完整性检查
=================================================
替代 agent.py 中的正则提取式完整性检查，用 AST 解析（Python）
和增强正则（TypeScript/JavaScript）精确提取函数/类定义名。

优势：
    1. AST 精确提取 Python 函数/类定义名，不受注释/字符串干扰
    2. 多语言支持：Python (AST) + TypeScript/JavaScript (增强正则)
    3. 从任务描述提取要求的函数/类名 — 分层匹配策略
    4. 检测嵌套定义（AST walk 遍历所有节点）

零外部依赖：仅 Python stdlib (ast / re / typing)
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code is proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import ast
import re
from typing import NamedTuple


class CompletenessResult(NamedTuple):
    """完整性检查结果。"""

    passed: bool
    notes: str
    missing: list[str]


# ============================================================================
# 从任务描述提取要求的函数/类名
# ============================================================================

# 编程关键字和通用词 — 不应作为"要求的函数名"
_STOPWORDS = {
    # 编程关键字
    "write", "read", "edit", "test", "compile",
    "print", "assert", "return", "raise", "import", "from",
    "true", "false", "none", "self", "cls", "new", "const", "let", "var",
    "if", "else", "elif", "for", "while", "with", "try", "except",
    "async", "await", "yield", "lambda", "del", "pass", "break", "continue",
    # 通用描述词
    "task", "step", "plan", "file", "code", "function", "method",
    "python", "pytest", "module", "class", "object", "string",
    # 内置函数/类型
    "len", "range", "str", "int", "float", "list", "dict",
    "type", "isinstance", "open", "sort", "split", "join",
    "format", "strip", "replace", "encode", "decode",
    "sum", "max", "min", "abs", "round", "map", "filter", "zip",
    "enumerate", "print", "input",
}


def _extract_required_names(task_description: str) -> set[str]:
    """从任务描述提取要求的函数/类名 — 分层匹配策略。

    策略优先级：
        1. 反引号包裹的函数签名 `func_name(args)` — 最可靠
        2. def func_name( — 任务描述中直接写了 def
        3. class ClassName — 任务描述中直接写了 class
        4. 中文模式 "实现 X 函数" / "创建 X 类"
        5. 明确的 "X(a, b)" 不带反引号但带参数 — 仅在前 4 种无结果时使用
    """
    text = task_description or ""
    names: set[str] = set()

    # 模式1: `func_name(args)` — 反引号包裹（最可靠）
    for m in re.finditer(r"`([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)`", text):
        name = m.group(1)
        if name.lower() not in _STOPWORDS and len(name) >= 2:
            names.add(name)

    # 模式2: def func_name( — 直接写了 def
    for m in re.finditer(r"\bdef\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", text):
        name = m.group(1)
        if name.lower() not in _STOPWORDS and len(name) >= 2:
            names.add(name)

    # 模式3: class ClassName — 直接写了 class
    for m in re.finditer(r"\bclass\s+([a-zA-Z_][a-zA-Z0-9_]*)\b", text):
        name = m.group(1)
        if name.lower() not in _STOPWORDS and len(name) >= 2:
            names.add(name)

    # 模式4: 中文模式 "实现 add 函数" / "创建 Calculator 类" / "编写 X 方法"
    for m in re.finditer(
        r"(?:实现|创建|编写|定义|添加|声明)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:函数|方法|类|接口)",
        text,
    ):
        name = m.group(1)
        if name.lower() not in _STOPWORDS and len(name) >= 2:
            names.add(name)

    # 模式5: "add(a, b)" 不带反引号但带参数列表 — 仅在前 4 种无结果时使用
    if not names:
        for m in re.finditer(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\((?:[a-zA-Z_][a-zA-Z0-9_]*\s*(?:,\s*[a-zA-Z_][a-zA-Z0-9_]*)*)\)",
            text,
        ):
            name = m.group(1)
            if name.lower() in _STOPWORDS or len(name) < 2:
                continue
            # 排除首字母大写的非函数词（如 Identity, Rules）
            if name[0].isupper():
                continue
            names.add(name)

    return names


# ============================================================================
# Python AST 解析
# ============================================================================


def _extract_python_defined_names(content: str) -> set[str]:
    """用 AST 解析 Python 代码，提取所有函数/类定义名。

    比 regex 更可靠：
        - 精确提取 def/class 定义名
        - 不受注释/字符串中的 "def" 干扰
        - 能检测嵌套定义（ast.walk 遍历所有节点）
    """
    defined: set[str] = set()
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
            elif isinstance(node, ast.ClassDef):
                defined.add(node.name)
    except SyntaxError:
        # 语法错误由编译检查单独报告，此处跳过
        pass
    except Exception:
        pass
    return defined


# ============================================================================
# TypeScript/JavaScript 增强正则
# ============================================================================

# TS/JS 函数/类定义模式
_TS_PATTERNS = [
    # function funcName(
    re.compile(r"\bfunction\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\("),
    # const/let/var funcName = ( | function
    re.compile(r"\b(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:\(|function)"),
    # class ClassName
    re.compile(r"\bclass\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\b"),
    # funcName(params): return_type {  — 类方法
    re.compile(r"\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{"),
    # export function funcName / export default function
    re.compile(r"\bexport\s+(?:default\s+)?function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\("),
    # funcName = (params) =>  — 箭头函数
    re.compile(r"\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*\([^)]*\)\s*=>"),
]


def _extract_ts_defined_names(content: str) -> set[str]:
    """用增强正则提取 TypeScript/JavaScript 中的函数/类定义名。"""
    defined: set[str] = set()
    for pattern in _TS_PATTERNS:
        for m in pattern.finditer(content):
            defined.add(m.group(1))
    return defined


# ============================================================================
# 多语言完整性检查入口
# ============================================================================


def check_completeness_ast(
    task_description: str,
    code_contents: dict[str, str],
) -> CompletenessResult:
    """用 AST 解析检查 Python 代码完整性。"""
    required_names = _extract_required_names(task_description)
    if not required_names:
        return CompletenessResult(True, "", [])

    defined_names: set[str] = set()
    for path, content in code_contents.items():
        if not path.endswith(".py"):
            continue
        defined_names |= _extract_python_defined_names(content)

    missing = sorted(required_names - defined_names)
    if missing:
        return CompletenessResult(
            False,
            f"任务要求的函数/类未实现: {', '.join(missing)}。"
            "请确保所有要求的函数都有对应的 def/class 定义。",
            missing,
        )
    return CompletenessResult(True, "", [])


def check_completeness_ts(
    task_description: str,
    code_contents: dict[str, str],
) -> CompletenessResult:
    """TypeScript/JavaScript 完整性检查。"""
    required_names = _extract_required_names(task_description)
    if not required_names:
        return CompletenessResult(True, "", [])

    defined_names: set[str] = set()
    for path, content in code_contents.items():
        if not path.endswith((".ts", ".tsx", ".js", ".jsx", ".vue")):
            continue
        defined_names |= _extract_ts_defined_names(content)

    missing = sorted(required_names - defined_names)
    if missing:
        return CompletenessResult(
            False,
            f"任务要求的函数/类未实现: {', '.join(missing)}。"
            "请确保所有要求的函数都有对应的 function/class 定义。",
            missing,
        )
    return CompletenessResult(True, "", [])


def check_completeness(
    task_description: str,
    code_contents: dict[str, str],
) -> CompletenessResult:
    """多语言完整性检查入口。

    根据文件扩展名自动选择检查器（Python AST / TS 增强 regex）。
    任一语言检查失败即失败。
    """
    has_py = any(p.endswith(".py") for p in code_contents)
    has_ts = any(
        p.endswith((".ts", ".tsx", ".js", ".jsx", ".vue")) for p in code_contents
    )

    results: list[CompletenessResult] = []
    if has_py:
        results.append(check_completeness_ast(task_description, code_contents))
    if has_ts:
        results.append(check_completeness_ts(task_description, code_contents))

    if not results:
        # 无代码文件：回退到 Python 检查（可能全是非代码文件）
        return check_completeness_ast(task_description, code_contents)

    # 合并结果：任一语言检查失败即失败
    all_missing: list[str] = []
    all_notes: list[str] = []
    for r in results:
        if not r.passed:
            all_missing.extend(r.missing)
            all_notes.append(r.notes)

    if all_missing:
        return CompletenessResult(False, " ".join(all_notes), all_missing)
    return CompletenessResult(True, "", [])


__all__ = [
    "CompletenessResult",
    "check_completeness",
    "check_completeness_ast",
    "check_completeness_ts",
]
