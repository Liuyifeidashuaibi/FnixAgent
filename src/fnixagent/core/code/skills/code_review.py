"""
Skill: 代码审查 (Code Review)
================================
审查代码变更, 检查安全/性能/风格问题。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

SKILL_NAME = "code_review"
SKILL_DESCRIPTION = "审查代码变更, 检查安全/性能/风格问题"
SKILL_CAPABILITIES = {"code.read", "code.search"}


async def handler(kernel, args):
    """审查代码。

    Args:
        kernel: AgentKernel 实例
        args: {"file": "path/to/file.py"} 或 {"diff": "unified diff text"}
    """
    file_path = args.get("file")
    if not file_path:
        return {"error": "缺少 file 参数"}

    # 读取文件内容
    from fnixagent.core.agent.syscall import SyscallRequest, SyscallType

    req = SyscallRequest(
        syscall=SyscallType.FS_READ,
        args={"path": f"/workspace/{file_path}"},
        caller_pid="kernel",
    )
    resp = await kernel.syscall(req)
    if not resp.success:
        return {"error": f"读取文件失败: {resp.error}"}

    content = resp.result or ""
    issues: list[dict[str, str]] = []

    # 基础检查规则
    checks = [
        ("eval/exec 使用", "eval(", "high", "安全"),
        ("subprocess shell=True", "shell=True", "high", "安全"),
        ("硬编码密码", "password = '", "high", "安全"),
        ("except: 裸捕获", "except:", "medium", "风格"),
        ("print 调试残留", "print(", "low", "风格"),
        ("TODO 未完成", "TODO", "low", "维护"),
        ("FIXME 未修复", "FIXME", "low", "维护"),
        ("超长函数 (>200 行)", None, "medium", "可维护性"),
    ]

    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        for name, pattern, severity, category in checks:
            if pattern and pattern in line:
                issues.append(
                    {
                        "line": i,
                        "severity": severity,
                        "category": category,
                        "issue": name,
                        "snippet": line.strip()[:80],
                    }
                )

    # 函数长度检查
    if len(lines) > 200:
        issues.append(
            {
                "line": 1,
                "severity": "medium",
                "category": "可维护性",
                "issue": f"文件过长 ({len(lines)} 行)",
                "snippet": "",
            }
        )

    return {
        "file": file_path,
        "total_lines": len(lines),
        "issues_found": len(issues),
        "issues": issues,
    }
