"""
IDEServer - IDE 集成服务
========================
fnixagent 编码智能体的 IDE 集成层, 对外提供两种接口:

  1. CLI: agentos-coding <command> [args]
     命令: index / search / read / write / edit / git / test / task / map / help

  2. MCP: Model Context Protocol 工具调用接口
     工具: code.read / code.write / code.edit / code.search /
           code.git / code.test / coding.task

设计要点:
  - 零外部依赖: 仅 Python stdlib (argparse / asyncio / json / sys)
  - 延迟初始化: CodeTools / CodeIndexer / CodingAgent 首次调用时创建
  - 统一结果格式: MCP 接口返回 {"success", "result", "error"}

Usage:
    # CLI 方式
    server = IDEServer(project_root=".")
    await server.run_cli(["search", "AgentKernel"])

    # MCP 方式 (供 Trae/VS Code 调用)
    result = await server.mcp_call("code.read", {"file_path": "src/main.py"})
    tools = server.mcp_list_tools()
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fnixagent.core.code.agent import CodingAgent, CodingTask
from fnixagent.core.code.context import ContextBuilder
from fnixagent.core.code.diff import DiffEngine
from fnixagent.core.code.indexer import CodeIndexer
from fnixagent.core.code.tools import CodeTools

# ============================================================================
# CLI 命令描述
# ============================================================================

@dataclass
class CLICommand:
    """CLI 命令描述。

    Attributes:
        name: 命令名 (如 "search" / "read")。
        description: 命令简述 (用于 help 输出)。
        handler: 命令处理协程, 接收 argparse.Namespace, 返回退出码。
    """

    name: str
    description: str
    handler: Callable[..., Awaitable[int]]  # 返回退出码

# ============================================================================
# IDE 集成服务 (CLI + MCP Server)
# ============================================================================

class IDEServer:
    """IDE 集成服务 (CLI + MCP Server 接口)。

    对外提供:
      - CLI: agentos-coding <command> [args]
      - MCP: 工具调用接口 (供 Trae/VS Code 连接)

    Usage:
        server = IDEServer(project_root=".")
        await server.run_cli(["search", "AgentKernel"])
    """

    def __init__(self, project_root: str = "."):
        """初始化 IDE 集成服务。

        Args:
            project_root: 项目根目录 (相对或绝对路径), 代码操作均基于此。
        """
        # 解析为绝对路径, 便于后续传递给 CodeTools / DiffEngine 等
        self._root: str = str(Path(project_root).resolve())
        self._code_tools: CodeTools | None = None  # 延迟初始化
        self._indexer: CodeIndexer | None = None  # 延迟初始化
        self._agent: CodingAgent | None = None  # 延迟初始化
        self._commands: dict[str, CLICommand] = {}
        self._register_commands()

    # ------------------------------------------------------------------
    # 命令注册
    # ------------------------------------------------------------------

    def _register_commands(self) -> None:
        """注册 CLI 命令。

        注册 10 个命令: index / search / read / write / edit /
        git / test / task / map / help。
        """
        specs: list[CLICommand] = [
            CLICommand("index", "索引项目代码", self._cmd_index),
            CLICommand("search", "语义搜索代码", self._cmd_search),
            CLICommand("read", "读取文件", self._cmd_read),
            CLICommand("write", "写入文件", self._cmd_write),
            CLICommand("edit", "精确替换文件内容", self._cmd_edit),
            CLICommand("git", "执行 Git 命令 (沙箱)", self._cmd_git),
            CLICommand("test", "运行测试", self._cmd_test),
            CLICommand("task", "执行编码任务", self._cmd_task),
            CLICommand("map", "输出仓库地图", self._cmd_map),
            CLICommand("help", "显示帮助", self._cmd_help),
        ]
        for cmd in specs:
            self._commands[cmd.name] = cmd

    # ------------------------------------------------------------------
    # CLI 入口
    # ------------------------------------------------------------------

    async def run_cli(self, args: list[str]) -> int:
        """运行 CLI 命令, 返回退出码。

        解析 args[0] 为命令名, 调用对应 handler。
        未知命令 → 打印帮助, 返回 1。

        Args:
            args: 命令行参数 (不含程序名), 如 ["search", "AgentKernel"]。

        Returns:
            退出码 (0 = 成功, 1 = 失败/未知命令)。
        """
        # 空参数 → 显示帮助
        if not args:
            return await self._cmd_help(argparse.Namespace())

        # 解析命令名
        name = args[0]
        cmd = self._commands.get(name)
        if cmd is None:
            # 未知命令
            print(f"未知命令: {name}")
            print(self._help_text())
            return 1

        # 构建解析器并解析参数
        parser = self._build_parser()
        try:
            ns = parser.parse_args(args)
        except SystemExit as exc:
            # argparse 解析失败或触发 --help 时会调用 sys.exit, 捕获后转为退出码
            code = exc.code
            return int(code) if isinstance(code, int) else 1

        # 调用对应处理器
        try:
            return await cmd.handler(ns)
        except Exception as exc:
            print(f"命令 '{name}' 执行失败: {type(exc).__name__}: {exc}")
            return 1

    def _build_parser(self) -> argparse.ArgumentParser:
        """构建参数解析器。

        构建含所有子命令的顶层解析器, 每个子命令注册各自参数。

        Returns:
            argparse.ArgumentParser 实例, 支持 <command> [args] 形式。
        """
        parser = argparse.ArgumentParser(
            prog="agentos-coding",
            description="fnixagent 编码智能体 CLI",
            add_help=False,
        )
        sub = parser.add_subparsers(dest="command", help="可用命令")

        # index: 索引项目代码
        p_index = sub.add_parser("index", help="索引项目代码")
        p_index.add_argument(
            "path",
            nargs="?",
            default=".",
            help="待索引路径 (默认项目根)",
        )
        p_index.add_argument(
            "--no-incremental",
            action="store_true",
            help="禁用增量索引",
        )

        # search: 语义搜索代码
        p_search = sub.add_parser("search", help="语义搜索代码")
        p_search.add_argument("query", help="搜索查询 (自然语言或关键词)")
        p_search.add_argument(
            "--top_k",
            type=int,
            default=10,
            help="返回结果数上限 (默认 10)",
        )

        # read: 读取文件
        p_read = sub.add_parser("read", help="读取文件")
        p_read.add_argument("file", help="文件路径 (相对项目根)")
        p_read.add_argument(
            "--start",
            type=int,
            default=0,
            help="起始行 (1-indexed, 0=从头)",
        )
        p_read.add_argument(
            "--end",
            type=int,
            default=0,
            help="结束行 (exclusive, 0=到尾)",
        )

        # write: 写入文件
        p_write = sub.add_parser("write", help="写入文件")
        p_write.add_argument("file", help="文件路径 (相对项目根)")
        p_write.add_argument("--content", required=True, help="文件内容")

        # edit: 精确替换
        p_edit = sub.add_parser("edit", help="精确替换文件内容")
        p_edit.add_argument("file", help="文件路径 (相对项目根)")
        p_edit.add_argument("--old", required=True, help="要替换的原文 (须唯一匹配)")
        p_edit.add_argument("--new", required=True, help="替换后的新文本")

        # git: Git 命令 (透传剩余参数)
        p_git = sub.add_parser("git", help="执行 Git 命令 (沙箱)")
        p_git.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="Git 子命令及参数",
        )

        # test: 运行测试 (透传剩余参数)
        p_test = sub.add_parser("test", help="运行测试")
        p_test.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            help="pytest 参数 (省略 = 默认 -x --tb=short)",
        )

        # task: 编码任务
        p_task = sub.add_parser("task", help="执行编码任务")
        p_task.add_argument(
            "description",
            nargs="+",
            help="任务描述 (自然语言)",
        )

        # map: 仓库地图
        p_map = sub.add_parser("map", help="输出仓库地图")
        p_map.add_argument(
            "--max-tokens",
            type=int,
            default=4096,
            help="仓库地图 token 上限 (默认 4096)",
        )

        # help: 显示帮助
        sub.add_parser("help", help="显示帮助")

        return parser

    # ------------------------------------------------------------------
    # 延迟初始化
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """延迟初始化 CodeTools / CodeIndexer / ContextBuilder / CodingAgent。

        首次调用时创建实例并相互装配; 后续调用直接返回。
        LLM 后端优先使用 InMemoryLLMBackend (导入失败时降级为 None,
        CodingAgent 将走降级路径, _call_llm 异常被捕获返回空串)。
        """
        if self._code_tools is not None and self._indexer is not None:
            return

        # 创建 CodeIndexer (语义索引器)
        self._indexer = CodeIndexer()

        # 创建 DiffEngine (原子编辑引擎)
        diff_engine = DiffEngine(project_root=self._root)

        # 创建 CodeTools (共享 indexer, 避免重复索引)
        self._code_tools = CodeTools(
            project_root=self._root,
            diff_engine=diff_engine,
            code_indexer=self._indexer,
        )

        # 创建 ContextBuilder (上下文工程引擎)
        context_builder = ContextBuilder(
            indexer=self._indexer,
            project_root=self._root,
        )

        # 创建 LLM 后端 (延迟导入, 失败时降级为 None)
        llm_backend: Any = None
        try:
            from fnixagent.core.agent.backends.in_memory import (
                InMemoryLLMBackend,
            )

            llm_backend = InMemoryLLMBackend()
        except Exception:
            llm_backend = None

        # 创建 CodingAgent (编码智能体)
        self._agent = CodingAgent(
            code_tools=self._code_tools,
            context_builder=context_builder,
            llm_backend=llm_backend,
            workspace=self._root,
        )

    async def _ensure_indexed(self) -> None:
        """确保索引器已索引项目 (若未索引则触发全量索引)。

        供 search / map 等命令在执行前自动补全索引。
        """
        self._ensure_initialized()
        assert self._indexer is not None
        stats = self._indexer.get_stats()
        if stats.get("total_files", 0) == 0:
            await self._indexer.index_directory(self._root)

    # ------------------------------------------------------------------
    # 命令处理器
    # ------------------------------------------------------------------

    async def _cmd_index(self, args: argparse.Namespace) -> int:
        """index [path] - 索引项目代码。

        Args:
            args: Namespace, 含 path / no_incremental 属性。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        self._ensure_initialized()
        assert self._indexer is not None

        path = getattr(args, "path", ".") or "."
        incremental = not getattr(args, "no_incremental", False)

        try:
            stats = await self._indexer.index_directory(
                path,
                incremental=incremental,
            )
        except Exception as exc:
            print(f"索引失败: {type(exc).__name__}: {exc}")
            return 1

        # 打印统计信息
        print("索引完成:")
        print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
        return 0

    async def _cmd_search(self, args: argparse.Namespace) -> int:
        """search <query> [--top_k=10] - 语义搜索代码。

        Args:
            args: Namespace, 含 query / top_k 属性。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        await self._ensure_indexed()
        assert self._indexer is not None

        query = args.query
        top_k = getattr(args, "top_k", 10)

        try:
            slices = await self._indexer.search_code(query, top_k=top_k)
        except Exception as exc:
            print(f"搜索失败: {type(exc).__name__}: {exc}")
            return 1

        if not slices:
            print(f"未找到匹配结果: {query}")
            return 0

        print(f"找到 {len(slices)} 个结果:")
        for i, sl in enumerate(slices, 1):
            print(f"\n--- 结果 {i} ---")
            print(json.dumps(sl.to_dict(), ensure_ascii=False, indent=2))
        return 0

    async def _cmd_read(self, args: argparse.Namespace) -> int:
        """read <file> [--start=<line>] [--end=<line>] - 读取文件。

        Args:
            args: Namespace, 含 file / start / end 属性。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        self._ensure_initialized()
        assert self._code_tools is not None

        result = await self._code_tools.read(
            args.file,
            start_line=getattr(args, "start", 0),
            end_line=getattr(args, "end", 0),
        )
        if not result.success:
            print(f"读取失败: {result.error}")
            return 1
        print(result.output)
        return 0

    async def _cmd_write(self, args: argparse.Namespace) -> int:
        """write <file> --content=<text> - 写入文件。

        Args:
            args: Namespace, 含 file / content 属性。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        self._ensure_initialized()
        assert self._code_tools is not None

        result = await self._code_tools.write(args.file, args.content)
        if not result.success:
            print(f"写入失败: {result.error}")
            return 1
        print(f"写入成功: {json.dumps(result.output, ensure_ascii=False)}")
        return 0

    async def _cmd_edit(self, args: argparse.Namespace) -> int:
        """edit <file> --old=<text> --new=<text> - 精确替换。

        Args:
            args: Namespace, 含 file / old / new 属性。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        self._ensure_initialized()
        assert self._code_tools is not None

        result = await self._code_tools.edit(args.file, args.old, args.new)
        if not result.success:
            print(f"编辑失败: {result.error}")
            return 1
        print(f"编辑成功: {json.dumps(result.output, ensure_ascii=False)}")
        return 0

    async def _cmd_git(self, args: argparse.Namespace) -> int:
        """git <args...> - 执行 Git 命令。

        Args:
            args: Namespace, 含 args 属性 (list[str])。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        self._ensure_initialized()
        assert self._code_tools is not None

        git_args = getattr(args, "args", []) or []
        # 过滤 REMAINDER 可能吞入的开头 "--" 分隔符
        if git_args and git_args[0] == "--":
            git_args = git_args[1:]

        result = await self._code_tools.git(git_args)
        if not result.success:
            print(f"Git 失败: {result.error}")
            return 1
        print(result.output)
        return 0

    async def _cmd_test(self, args: argparse.Namespace) -> int:
        """test [args...] - 运行测试。

        Args:
            args: Namespace, 含 args 属性 (list[str])。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        self._ensure_initialized()
        assert self._code_tools is not None

        test_args = getattr(args, "args", []) or []
        # 过滤开头 "--" 分隔符
        if test_args and test_args[0] == "--":
            test_args = test_args[1:]

        # 空参数 → None 触发 CodeTools 默认参数 (-x --tb=short)
        result = await self._code_tools.test(test_args if test_args else None)
        if not result.success:
            print(f"测试失败: {result.error}")
            return 1
        print(result.output)
        return 0

    async def _cmd_task(self, args: argparse.Namespace) -> int:
        """task <description> - 执行编码任务 (Plan→Execute→Review)。

        Args:
            args: Namespace, 含 description 属性 (list[str], nargs="+")。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        self._ensure_initialized()
        assert self._agent is not None

        # description 为 nargs="+" 的列表, 合并为单个字符串
        desc_list = args.description
        description = " ".join(desc_list) if isinstance(desc_list, list) else str(desc_list)

        # 构造编码任务
        task = CodingTask(description=description)

        # 执行任务 (Plan → Execute → Review)
        try:
            result = await self._agent.execute_task(task)
        except Exception as exc:
            print(f"任务执行失败: {type(exc).__name__}: {exc}")
            return 1

        # 打印结果摘要
        print(f"任务 ID: {result.task_id}")
        print(f"状态: {result.status.value}")
        print(f"耗时: {result.duration_sec:.3f}s")
        print(f"审查通过: {result.review_passed}")
        if result.changeset_id:
            print(f"变更集: {result.changeset_id}")
        if result.review_notes:
            print(f"审查意见: {result.review_notes}")
        if result.error:
            print(f"错误: {result.error}")

        # 打印执行计划
        print(f"\n执行计划 ({len(result.plan)} 步):")
        for i, step in enumerate(result.plan, 1):
            desc_preview = step.description[:80]
            print(f"  {i}. [{step.status}] {step.action} {step.target} - {desc_preview}")
            if step.error:
                print(f"     错误: {step.error}")

        # 完成且审查通过 → 0, 否则 → 1
        return 0 if result.status.value == "completed" else 1

    async def _cmd_map(self, args: argparse.Namespace) -> int:
        """map - 输出仓库地图 (RepoMap)。

        Args:
            args: Namespace, 含 max_tokens 属性。

        Returns:
            退出码 (0 = 成功, 1 = 失败)。
        """
        await self._ensure_indexed()
        assert self._indexer is not None

        max_tokens = getattr(args, "max_tokens", 4096)
        try:
            repo_map = self._indexer.get_repo_map(max_tokens=max_tokens)
        except Exception as exc:
            print(f"生成仓库地图失败: {type(exc).__name__}: {exc}")
            return 1

        if not repo_map:
            print("(仓库地图为空, 请先 index)")
            return 0
        print(repo_map)
        return 0

    async def _cmd_help(self, args: argparse.Namespace) -> int:
        """help - 显示帮助。

        Args:
            args: 未使用。

        Returns:
            退出码 0。
        """
        print(self._help_text())
        return 0

    # ------------------------------------------------------------------
    # 帮助文本
    # ------------------------------------------------------------------

    def _help_text(self) -> str:
        """生成帮助文本。

        Returns:
            多行帮助字符串, 列出所有可用命令。
        """
        lines = [
            "agentos-coding - fnixagent 编码智能体 CLI",
            "",
            "用法: agentos-coding <command> [args]",
            "",
            "可用命令:",
        ]
        for cmd in self._commands.values():
            lines.append(f"  {cmd.name:<8} {cmd.description}")
        lines.append("")
        lines.append("详细帮助: agentos-coding <command> --help")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # MCP 接口 (供外部 IDE 调用)
    # ------------------------------------------------------------------

    async def mcp_call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """MCP 工具调用入口 (供 Trae/VS Code 通过 MCP 协议调用)。

        Args:
            tool: 工具名 (code.read / code.write / code.edit / code.search /
                code.git / code.test / coding.task)。
            arguments: 工具参数。

        Returns:
            {"success": bool, "result": Any, "error": str | None}
        """
        self._ensure_initialized()
        assert self._code_tools is not None
        assert self._agent is not None

        try:
            if tool == "code.read":
                # 读取文件
                result = await self._code_tools.read(
                    arguments["file_path"],
                    start_line=arguments.get("start_line", 0),
                    end_line=arguments.get("end_line", 0),
                )
                return self._tool_result_to_mcp(result)

            elif tool == "code.write":
                # 写入文件
                result = await self._code_tools.write(
                    arguments["file_path"],
                    arguments["content"],
                )
                return self._tool_result_to_mcp(result)

            elif tool == "code.edit":
                # 精确替换
                result = await self._code_tools.edit(
                    arguments["file_path"],
                    arguments["old_text"],
                    arguments["new_text"],
                )
                return self._tool_result_to_mcp(result)

            elif tool == "code.search":
                # 语义搜索 (确保已索引)
                await self._ensure_indexed()
                assert self._indexer is not None
                slices = await self._indexer.search_code(
                    arguments["query"],
                    top_k=arguments.get("top_k", 10),
                )
                return {
                    "success": True,
                    "result": [s.to_dict() for s in slices],
                    "error": None,
                }

            elif tool == "code.git":
                # Git 命令 (沙箱)
                result = await self._code_tools.git(arguments.get("args", []))
                return self._tool_result_to_mcp(result)

            elif tool == "code.test":
                # 运行测试
                result = await self._code_tools.test(arguments.get("args"))
                return self._tool_result_to_mcp(result)

            elif tool == "coding.task":
                # 执行编码任务 (Plan → Execute → Review)
                task = CodingTask(
                    description=arguments["description"],
                    files=arguments.get("files", []),
                    constraints=arguments.get("constraints", []),
                )
                task_result = await self._agent.execute_task(task)
                return {
                    "success": task_result.status.value == "completed",
                    "result": {
                        "task_id": task_result.task_id,
                        "status": task_result.status.value,
                        "changeset_id": task_result.changeset_id,
                        "review_passed": task_result.review_passed,
                        "review_notes": task_result.review_notes,
                        "duration_sec": task_result.duration_sec,
                        "error": task_result.error,
                        "plan": [
                            {
                                "id": s.id,
                                "description": s.description,
                                "action": s.action,
                                "target": s.target,
                                "status": s.status,
                                "result": s.result,
                                "error": s.error,
                            }
                            for s in task_result.plan
                        ],
                    },
                    "error": task_result.error,
                }

            else:
                # 未知工具
                return {
                    "success": False,
                    "result": None,
                    "error": f"未知工具: {tool}",
                }

        except Exception as exc:
            # 捕获所有异常, 返回统一错误格式
            return {
                "success": False,
                "result": None,
                "error": f"{type(exc).__name__}: {exc}",
            }

    @staticmethod
    def _tool_result_to_mcp(result: Any) -> dict[str, Any]:
        """将 ToolResult 转换为 MCP 统一响应格式。

        Args:
            result: CodeTools 工具返回的 ToolResult (含 success/output/error)。

        Returns:
            {"success": bool, "result": Any, "error": str | None}
        """
        return {
            "success": result.success,
            "result": result.output,
            "error": result.error,
        }

    def mcp_list_tools(self) -> list[dict[str, Any]]:
        """列出 MCP 工具 (供 MCP 协议 tools/list 响应)。

        Returns:
            7 个工具的描述列表, 每项含 name / description / parameters。
        """
        return [
            {
                "name": "code.read",
                "description": "读取文件内容 (支持行范围)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "相对项目根的文件路径",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "起始行 (1-indexed, 0=从头)",
                            "default": 0,
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "结束行 (exclusive, 0=到尾)",
                            "default": 0,
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "code.write",
                "description": "写入文件 (创建或覆盖, 原子应用)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "相对项目根的文件路径",
                        },
                        "content": {
                            "type": "string",
                            "description": "文件内容",
                        },
                    },
                    "required": ["file_path", "content"],
                },
            },
            {
                "name": "code.edit",
                "description": "精确替换文件内容 (old_text 须唯一匹配)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "相对项目根的文件路径",
                        },
                        "old_text": {
                            "type": "string",
                            "description": "要替换的原文 (须唯一匹配)",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "替换后的新文本",
                        },
                    },
                    "required": ["file_path", "old_text", "new_text"],
                },
            },
            {
                "name": "code.search",
                "description": "语义搜索代码 (基于 CodeIndexer)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索查询 (自然语言或关键词)",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回结果数上限",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "code.git",
                "description": (
                    "执行 Git 命令 (沙箱白名单: "
                    "status/diff/log/add/commit/checkout/branch/show/stash)"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": 'Git 子命令及参数 (如 ["status", "--short"])',
                        },
                    },
                    "required": ["args"],
                },
            },
            {
                "name": "code.test",
                "description": "运行测试 (pytest)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "pytest 参数 (省略 = 默认 -x --tb=short)",
                        },
                    },
                },
            },
            {
                "name": "coding.task",
                "description": "执行编码任务 (Plan → Execute → Review)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "任务描述 (自然语言)",
                        },
                        "files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "涉及文件列表 (可选)",
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "约束条件 (可选)",
                        },
                    },
                    "required": ["description"],
                },
            },
        ]

# ============================================================================
# CLI 入口
# ============================================================================

def main() -> int:
    """CLI 入口 (agentos-coding 命令)。

    Returns:
        退出码。
    """
    server = IDEServer()
    args = sys.argv[1:]
    return asyncio.run(server.run_cli(args))

if __name__ == "__main__":
    sys.exit(main())
