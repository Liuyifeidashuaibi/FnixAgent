"""
FnixAgent Coding — Code 对齐演示
=====================================
模拟 Code 真实使用流程: 接收任务 → 规划 → 执行 → 审查 → 输出 diff。

场景: 修复 calculator.py 的除零 bug + 自动生成测试。
使用 ScriptedLLM 按调用顺序返回预设 JSON, 让 Plan→Execute→Review 三阶段真实跑通。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fnixagent.core.code import (
    CodeIndexer,
    CodeTools,
    ContextBuilder,
    DiffEngine,
    IDEServer,
)
from fnixagent.core.code.agent import CodingAgent, CodingTask

# ============================================================================
# ScriptedLLM — 按调用顺序返回预设响应 (模拟真实 LLM)
# ============================================================================


class ScriptedLLM:
    """脚本化 LLM, 按调用顺序返回预设响应。

    对齐工程实践 背后的 GPT-4: 接收上下文 → 返回结构化 JSON。
    每次调用消耗一个预设响应, 超出时返回空串 (降级)。
    """

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self._idx = 0
        self.call_log: list[str] = []  # 记录每次调用最后一条 user 消息

    async def complete(self, payload, **kwargs):
        """模拟 LLM 调用。

        Args:
            payload: CodingAgent 传入 {"messages": [...]}; 兼容 list 形式。
        """
        # 兼容两种调用形式: {"messages": [...]} 或 [...]
        if isinstance(payload, dict):
            messages = payload.get("messages", [])
        else:
            messages = payload

        # 记录最后一条 user 消息 (用于调试)
        last_user = ""
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                last_user = str(msg.get("content", ""))[:120]
        self.call_log.append(last_user)

        # 按顺序返回预设响应
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        return ""


# ============================================================================
# 演示场景
# ============================================================================

BUGGY_CALC = '''"""计算器模块 (含除零 bug)。"""


def add(a, b):
    """加法。"""
    return a + b


def divide(a, b):
    """除法。"""
    return a / b


def multiply(a, b):
    """乘法。"""
    return a * b
'''

EXPECTED_TEST = '''"""calculator 测试。"""
import pytest
from calculator import add, divide, multiply


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0


def test_divide_normal():
    assert divide(10, 2) == 5.0
    assert divide(7, 1) == 7.0


def test_divide_by_zero():
    with pytest.raises(ValueError, match="除数不能为零"):
        divide(10, 0)


def test_multiply():
    assert multiply(3, 4) == 12
    assert multiply(0, 5) == 0
'''

EXPECTED_FIXED = '''"""计算器模块 (含除零 bug)。"""


def add(a, b):
    """加法。"""
    return a + b


def divide(a, b):
    """除法。"""
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b


def multiply(a, b):
    """乘法。"""
    return a * b
'''


def build_plan_response():
    """构造 Plan 阶段 LLM 返回的 JSON (真实分解为 4 步)。"""
    plan = {
        "steps": [
            {
                "description": "读取 calculator.py 了解当前实现",
                "action": "read",
                "target": "calculator.py",
            },
            {
                "description": '    return a / b|||    if b == 0:\n        raise ValueError("除数不能为零")\n    return a / b',
                "action": "edit",
                "target": "calculator.py",
            },
            {
                "description": EXPECTED_TEST,
                "action": "write",
                "target": "test_calculator.py",
            },
            {
                "description": "运行 pytest 验证修复",
                "action": "test",
                "target": "",
            },
        ]
    }
    return json.dumps(plan, ensure_ascii=False)


def build_review_response():
    """构造 Review 阶段 LLM 返回的 JSON (审查通过)。"""
    return json.dumps(
        {
            "passed": True,
            "notes": "除零检查正确, 测试覆盖正常路径和异常路径, 修复通过。",
        },
        ensure_ascii=False,
    )


# ============================================================================
# 演示主流程
# ============================================================================


def print_stage(title):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def print_sub(title):
    print(f"\n--- {title} ---")


async def demo_codex_flow():
    """演示 1: 完整 Plan→Execute→Review 流程 (对齐工程实践)。"""
    print_stage("场景 1: Code 式编码任务 — 修复除零 bug + 生成测试")

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- 准备含 bug 的项目 ---
        (Path(tmpdir) / "calculator.py").write_text(BUGGY_CALC, encoding="utf-8")
        print(f"项目目录: {tmpdir}")
        print("初始文件: calculator.py (含 divide 除零 bug)")

        # --- 装配 CodingAgent ---
        indexer = CodeIndexer()
        await indexer.index_directory(tmpdir)
        diff_engine = DiffEngine(project_root=tmpdir)
        tools = CodeTools(project_root=tmpdir, diff_engine=diff_engine, code_indexer=indexer)
        ctx_builder = ContextBuilder(indexer, project_root=tmpdir)
        llm = ScriptedLLM(
            [
                build_plan_response(),  # 第 1 次调用: Plan 阶段
                build_review_response(),  # 第 2 次调用: Review 阶段
            ]
        )
        agent = CodingAgent(tools, ctx_builder, llm)

        # --- 执行任务 ---
        task = CodingTask(
            description="修复 calculator.py 的 divide 函数除零 bug, 并添加测试",
            files=["calculator.py", "test_calculator.py"],
            constraints=["保持其他函数不变", "使用 pytest 框架"],
        )

        print_sub("任务描述")
        print(f"  {task.description}")
        print(f"  涉及文件: {task.files}")
        print(f"  约束条件: {task.constraints}")

        result = await agent.execute_task(task)

        # --- 输出 Plan ---
        print_sub(f"PLAN 阶段 — {len(result.plan)} 步执行计划")
        for i, step in enumerate(result.plan, 1):
            desc_preview = step.description[:60].replace("\n", "\\n")
            print(f"  {i}. [{step.action or 'skip'}] {step.target}")
            print(f"     {desc_preview}")

        # --- 输出 Execute 结果 ---
        print_sub("EXECUTE 阶段 — 步骤执行结果")
        for i, step in enumerate(result.plan, 1):
            status_icon = {"done": "OK", "failed": "FAIL", "skipped": "SKIP"}.get(step.status, "?")
            print(f"  {i}. [{status_icon}] {step.action} {step.target}")
            if step.error:
                print(f"     错误: {step.error[:100]}")

        # --- 输出 Review 结果 ---
        print_sub("REVIEW 阶段 — 审查结果")
        print(f"  审查通过: {result.review_passed}")
        print(f"  审查意见: {result.review_notes}")
        print(f"  任务状态: {result.status.value}")
        print(f"  执行耗时: {result.duration_sec:.3f}s")

        # --- 验证文件变更 ---
        print_sub("文件变更验证")
        fixed = Path(tmpdir) / "calculator.py"
        test = Path(tmpdir) / "test_calculator.py"
        actual_fixed = fixed.read_text(encoding="utf-8")
        actual_test = test.read_text(encoding="utf-8")

        # write 步骤经 _parse_plan strip(), 末尾换行可能被去除, 用 rstrip 比较
        fixed_ok = actual_fixed.rstrip() == EXPECTED_FIXED.rstrip()
        test_ok = actual_test.rstrip() == EXPECTED_TEST.rstrip()

        print(f"  calculator.py 修复正确: {'YES' if fixed_ok else 'NO'}")
        if not fixed_ok:
            print(f"    期望:\n{EXPECTED_FIXED}")
            print(f"    实际:\n{actual_fixed}")
        print(f"  test_calculator.py 生成正确: {'YES' if test_ok else 'NO'}")
        if not test_ok:
            print(f"    期望:\n{EXPECTED_TEST}")
            print(f"    实际:\n{actual_test}")

        # --- 输出 diff ---
        print_sub("变更 diff (unified)")
        if result.changeset_id:
            for cs, _ in diff_engine.get_history():
                if cs.id == result.changeset_id:
                    print(cs.to_diff())
                    break

        # --- LLM 调用日志 ---
        print_sub("LLM 调用日志")
        for i, log in enumerate(llm.call_log, 1):
            print(f"  调用 {i}: {log[:80]}")

        overall = (
            result.status.value == "completed" and result.review_passed and fixed_ok and test_ok
        )
        print_sub("总结")
        print(f"  对齐工程实践 流程完整跑通: {'YES' if overall else 'NO'}")
        return overall


async def demo_cli_mcp():
    """演示 2: CLI + MCP 双接口 (对齐工程实践 IDE 集成)。"""
    print_stage("场景 2: CLI + MCP 双接口 — IDE 集成能力")

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "hello.py").write_text(
            "def greet(name):\n    return f'hello {name}'\n",
            encoding="utf-8",
        )
        server = IDEServer(project_root=tmpdir)

        # --- CLI 接口演示 ---
        print_sub("CLI: agentos-coding index")
        code = await server.run_cli(["index"])
        print(f"  退出码: {code}")

        print_sub("CLI: agentos-coding map")
        code = await server.run_cli(["map"])
        print(f"  退出码: {code}")

        print_sub("CLI: agentos-coding read hello.py")
        code = await server.run_cli(["read", "hello.py"])
        print(f"  退出码: {code}")

        print_sub("CLI: agentos-coding search greet")
        code = await server.run_cli(["search", "greet", "--top_k", "3"])
        print(f"  退出码: {code}")

        # --- MCP 接口演示 (对齐 IDE 调用) ---
        print_sub("MCP: mcp_list_tools()")
        tools = server.mcp_list_tools()
        print(f"  工具数: {len(tools)}")
        for t in tools:
            print(f"  - {t['name']}: {t['description'][:50]}")

        print_sub("MCP: code.read hello.py")
        r = await server.mcp_call("code.read", {"file_path": "hello.py"})
        print(f"  success={r['success']}")
        print(f"  output={str(r.get('result', ''))[:60]}")

        print_sub("MCP: code.write new_module.py")
        r = await server.mcp_call(
            "code.write",
            {
                "file_path": "new_module.py",
                "content": "x = 42\n",
            },
        )
        print(f"  success={r['success']}, result={r.get('result')}")

        print_sub("MCP: code.search greet")
        r = await server.mcp_call("code.search", {"query": "greet", "top_k": 3})
        print(f"  success={r['success']}, 结果数={len(r.get('result', []))}")

        print_sub("MCP: code.edit hello.py (唯一匹配替换)")
        r = await server.mcp_call(
            "code.edit",
            {
                "file_path": "hello.py",
                "old_text": "hello {name}",
                "new_text": "hi {name}",
            },
        )
        print(f"  success={r['success']}, result={r.get('result')}")

        r = await server.mcp_call("code.read", {"file_path": "hello.py"})
        print(f"  验证: {str(r.get('result', ''))[:60]}")

        # --- 沙箱安全演示 ---
        print_sub("安全: 路径穿越防护")
        r = await server.mcp_call(
            "code.read",
            {
                "file_path": "../../../etc/passwd",
            },
        )
        print(f"  success={r['success']} (应 False), error={r.get('error', '')[:60]}")

        print_sub("安全: Git 危险命令拦截")
        r = await server.mcp_call("code.git", {"args": ["push"]})
        print(f"  success={r['success']} (应 False), error={r.get('error', '')[:60]}")

        return True


async def demo_repo_map():
    """演示 3: 仓库地图 (对齐  RepoMap)。"""
    print_stage("场景 3: 仓库地图 —  RepoMap 对齐")

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建多模块项目
        (Path(tmpdir) / "auth.py").write_text(
            "class AuthManager:\n"
            "    def login(self, user, pwd):\n"
            "        pass\n"
            "    def logout(self, token):\n"
            "        pass\n"
            "def hash_password(pwd):\n"
            "    pass\n",
            encoding="utf-8",
        )
        (Path(tmpdir) / "db.py").write_text(
            "class Database:\n"
            "    def query(self, sql):\n"
            "        pass\n"
            "    def execute(self, sql):\n"
            "        pass\n",
            encoding="utf-8",
        )
        (Path(tmpdir) / "utils.py").write_text(
            "def format_time(ts):\n    pass\ndef parse_json(text):\n    pass\n",
            encoding="utf-8",
        )

        indexer = CodeIndexer()
        stats = await indexer.index_directory(tmpdir)
        print(f"索引: {stats.total_files} 文件, {stats.total_symbols} 符号")

        print_sub("仓库地图 (RepoMap)")
        repo_map = indexer.get_repo_map()
        print(repo_map)

        print_sub("符号查询: Database")
        sym = indexer.get_symbol_info("Database")
        if sym:
            print(f"  类型: {sym.kind.value}, 文件: {sym.location.file}")

        print_sub("引用查找: AuthManager")
        refs = indexer.find_references("AuthManager")
        print(f"  找到 {len(refs)} 处引用")

        return True


async def main():
    print("=" * 70)
    print("  FnixAgent Coding — Code 对齐演示")
    print("  完整 Plan→Execute→Review + CLI/MCP + RepoMap")
    print("=" * 70)

    results = []
    results.append(await demo_codex_flow())
    results.append(await demo_cli_mcp())
    results.append(await demo_repo_map())

    print_stage("总结")
    passed = sum(results)
    total = len(results)
    print(f"  场景通过: {passed}/{total}")
    if passed == total:
        print("  结论: 完整对齐工程实践 核心能力 (Plan→Execute→Review + 原子编辑 + IDE 集成)")
    else:
        print("  结论: 部分场景未通过, 需排查")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
