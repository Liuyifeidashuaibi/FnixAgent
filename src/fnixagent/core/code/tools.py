"""
CodeTools - 代码操作工具集
==========================
对齐工程实践 文件操作和 工具生态, 提供编码智能体的 6 个核心工具:
  - read:   读取文件 (支持行范围)
  - write:  写入文件 (创建或覆盖, 原子应用)
  - edit:   精确替换 (字符串匹配 + 替换)
  - search: 语义搜索代码 (走 CodeIndexer)
  - git:    执行 Git 命令 (沙箱内, 白名单)
  - test:   运行测试 (pytest)

设计要点:
  - 零外部依赖: 仅 Python stdlib (subprocess / pathlib / difflib / asyncio)
  - 原子写操作: 所有写操作通过 DiffEngine 保证原子性
  - 路径安全: 解析后必须仍在 project_root 下, 防止路径穿越
  - Git 沙箱: 白名单子命令, 禁止破坏性操作

Usage:
    tools = CodeTools(project_root="/path/to/project")

    # 读取文件
    result = await tools.read("src/main.py")

    # 写入文件 (原子)
    result = await tools.write("src/new.py", "print('hello')")

    # 精确替换 (原子)
    result = await tools.edit("src/main.py", "old", "new")

    # 语义搜索
    result = await tools.search("数据库连接池")

    # Git 操作 (沙箱)
    result = await tools.git(["status", "--short"])

    # 运行测试
    result = await tools.test(["-x", "--tb=short"])
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fnixagent.core.code.diff import (
    ChangeSet,
    ChangeSetBuilder,
    DiffEngine,
)

_logger = logging.getLogger(__name__)


# ============================================================================
# 工具执行结果
# ============================================================================


@dataclass
class ToolResult:
    """工具执行结果。

    所有工具方法的统一返回类型, 封装成功/失败状态及输出数据。

    Attributes:
        success: 是否执行成功
        output: 成功时的输出数据 (类型随工具而异)
        error: 失败时的错误描述 (成功时为 None)
    """

    success: bool
    output: Any = None
    error: str | None = None

    @classmethod
    def ok(cls, output: Any = None) -> ToolResult:
        """构造成功结果。

        Args:
            output: 输出数据 (可选)。

        Returns:
            success=True 的 ToolResult。
        """
        return cls(success=True, output=output, error=None)

    @classmethod
    def err(cls, error: str) -> ToolResult:
        """构造失败结果。

        Args:
            error: 错误描述。

        Returns:
            success=False 的 ToolResult。
        """
        return cls(success=False, output=None, error=error)


# ============================================================================
# 代码操作工具集
# ============================================================================


class CodeTools:
    """代码操作工具集, 6 个核心工具。

    所有写操作通过 DiffEngine 保证原子性。
    所有 Shell 操作通过 subprocess 异步执行。

    工具清单:
      - read:   读取文件 (支持行范围)
      - write:  写入文件 (创建或覆盖, 原子应用)
      - edit:   精确替换 (字符串匹配 + 替换)
      - search: 语义搜索代码 (走 CodeIndexer)
      - git:    执行 Git 命令 (沙箱内, 白名单)
      - test:   运行测试 (pytest)

    Attributes:
        _root: 项目根目录 (绝对路径)
        _diff: DiffEngine 实例 (原子编辑引擎)
        _indexer: CodeIndexer 实例 (可选, 延迟初始化)
    """

    # Git 安全子命令白名单
    _SAFE_GIT_SUBCOMMANDS: frozenset[str] = frozenset(
        {
            "status",
            "diff",
            "log",
            "add",
            "commit",
            "checkout",
            "branch",
            "show",
            "stash",
        }
    )

    # Git 禁止子命令 (破坏性或网络操作)
    _FORBIDDEN_GIT_SUBCOMMANDS: frozenset[str] = frozenset(
        {
            "push",
            "pull",
            "reset",
            "clean",
            "rm",
        }
    )

    # 危险标志 (即使子命令在白名单中也禁止, 如 reset --hard 中的 --hard)
    _DANGEROUS_FLAGS: frozenset[str] = frozenset(
        {
            "--hard",
            "--force",
            "--force-with-lease",
        }
    )

    def __init__(
        self,
        project_root: str = ".",
        diff_engine: DiffEngine | None = None,
        code_indexer: Any = None,
    ):
        """初始化代码工具集。

        Args:
            project_root: 项目根目录, 所有相对路径基于此解析。
            diff_engine: DiffEngine 实例, None 时内部创建。
            code_indexer: CodeIndexer 实例, None 时延迟初始化 (首次 search 时创建)。
        """
        self._root: Path = Path(project_root).resolve()
        self._diff: DiffEngine = diff_engine or DiffEngine(project_root)
        self._indexer = code_indexer  # 可选, 延迟初始化
        # 行业编码工具-style: True → DiffEngine dry_run (propose, don't write)
        self.preview_mode: bool = False

    # ------------------------------------------------------------------------
    # 工具描述 (供 MCP 注册用)
    # ------------------------------------------------------------------------

    def get_tools(self) -> list[dict[str, Any]]:
        """返回工具描述列表 (供 MCP 注册用)。

        每个工具描述包含:
          - name: 工具名称
          - description: 工具功能描述
          - parameters: 参数 schema (JSON Schema 风格)

        Returns:
            工具描述字典列表, 每项为 {name, description, parameters}。
        """
        return [
            {
                "name": "read",
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
                            "description": "结束行 (0=到尾, exclusive)",
                            "default": 0,
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "write",
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
                "name": "edit",
                "description": "精确替换文件内容 (old_text 必须在文件中唯一匹配)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "相对项目根的文件路径",
                        },
                        "old_text": {
                            "type": "string",
                            "description": "要替换的原文 (必须在文件中唯一匹配)",
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
                "name": "search",
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
                "name": "git",
                "description": "执行 Git 命令 (沙箱内, 白名单: status/diff/log/add/commit/checkout/branch/show/stash)",
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
                "name": "test",
                "description": "运行测试 (pytest)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "args": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "pytest 参数 (None = 默认 -x --tb=short)",
                        },
                    },
                },
            },
        ]

    # ------------------------------------------------------------------------
    # 工具: read
    # ------------------------------------------------------------------------

    async def read(
        self,
        file_path: str,
        *,
        start_line: int = 0,
        end_line: int = 0,
    ) -> ToolResult:
        """读取文件 (支持行范围)。

        Args:
            file_path: 相对项目根的路径。
            start_line: 起始行 (1-indexed, 0=从头)。
            end_line: 结束行 (0=到尾, exclusive)。

        Returns:
            ToolResult, 成功时 output 为带行号的文件内容 (cat -n 风格),
            失败时 error 描述错误原因。
        """
        # 解析路径 (防穿越)
        try:
            full = self._resolve_path(file_path)
        except ValueError as e:
            return ToolResult.err(str(e))

        # 文件存在性检查
        if not full.exists():
            return ToolResult.err(f"文件不存在: {file_path}")
        if not full.is_file():
            return ToolResult.err(f"路径不是文件: {file_path}")

        # 读取文件内容
        try:
            content = full.read_text(encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"读取文件失败: {e}")

        lines = content.splitlines()
        total = len(lines)

        # 计算行范围
        # start_line: 1-indexed, 0=从头 → 转为 0-indexed
        start_idx = max(0, start_line - 1) if start_line > 0 else 0
        # end_line: exclusive, 0=到尾
        end_idx = min(end_line, total) if end_line > 0 else total

        # 范围校验: 起始超出文件范围时返回空
        if start_idx >= total:
            return ToolResult.ok("")

        selected = lines[start_idx:end_idx]

        # 添加行号 (cat -n 风格: 右对齐行号 + 制表符 + 内容)
        actual_start = start_idx + 1
        numbered: list[str] = []
        for offset, line in enumerate(selected):
            line_no = actual_start + offset
            numbered.append(f"{line_no:6d}\t{line}")

        return ToolResult.ok("\n".join(numbered))

    # ------------------------------------------------------------------------
    # 工具: write
    # ------------------------------------------------------------------------

    async def write(self, file_path: str, content: str) -> ToolResult:
        """写入文件 (创建或覆盖)。

        文件不存在时通过 ChangeSet CREATE 创建, 已存在时通过 MODIFY 覆盖。
        通过 DiffEngine 原子应用, 保证写操作原子性。

        Args:
            file_path: 相对项目根的路径。
            content: 文件内容。

        Returns:
            ToolResult, 成功时 output 为 {"path": 相对路径, "bytes": 字节数},
            失败时 error 描述错误原因。
        """
        # 解析路径 (防穿越)
        try:
            full = self._resolve_path(file_path)
        except ValueError as e:
            return ToolResult.err(str(e))

        rel_path = full.relative_to(self._root).as_posix()
        try:
            from fnixagent.core.tools.workspace import _reject_stub_source

            stub_err = _reject_stub_source(rel_path, content or "")
            if stub_err:
                return ToolResult.err(stub_err)
        except Exception:
            _logger.debug('Unhandled exception', exc_info=True)

        # 路径类型检查 (防止写入目录)
        if full.exists() and not full.is_file():
            return ToolResult.err(f"路径已存在且不是文件: {file_path}")

        action = "create"
        old_content = ""
        if full.exists() and full.is_file():
            action = "modify"
            try:
                old_content = full.read_text(encoding="utf-8")
            except OSError as e:
                return ToolResult.err(f"读取原文件失败: {e}")
            cs: ChangeSet = (
                ChangeSetBuilder(f"写入文件: {rel_path}")
                .modify_file(rel_path, old_content, content)
                .build()
            )
        else:
            cs = ChangeSetBuilder(f"创建文件: {rel_path}").create_file(rel_path, content).build()

        # 原子应用变更集（preview_mode 时 dry_run，不落盘）
        result = await self._diff.apply(cs, dry_run=self.preview_mode)
        if not result.success:
            return ToolResult.err(result.error or f"写入失败: {rel_path}")

        return ToolResult.ok(
            {
                "path": rel_path,
                "bytes": len(content.encode("utf-8")),
                "preview": self.preview_mode,
                "content": content,
                "old_content": old_content,
                "diff": cs.to_diff(),
                "action": action,
            }
        )

    # ------------------------------------------------------------------------
    # 工具: edit
    # ------------------------------------------------------------------------

    async def edit(
        self,
        file_path: str,
        old_text: str,
        new_text: str,
    ) -> ToolResult:
        """精确替换 (字符串匹配 + 替换)。

        要求 old_text 在文件中唯一匹配, 否则失败。
        通过 DiffEngine 的 ChangeSet MODIFY 原子应用。

        Args:
            file_path: 相对项目根的路径。
            old_text: 要替换的原文 (必须在文件中唯一匹配)。
            new_text: 替换后的新文本。

        Returns:
            ToolResult, 成功时 output 为 {"path": 相对路径, "replaced": 1},
            失败时 error 描述错误原因 (如 "old_text 匹配 N 次, 期望 1 次")。
        """
        # 解析路径 (防穿越)
        try:
            full = self._resolve_path(file_path)
        except ValueError as e:
            return ToolResult.err(str(e))

        # 文件存在性检查
        if not full.exists():
            return ToolResult.err(f"文件不存在: {file_path}")
        if not full.is_file():
            return ToolResult.err(f"路径不是文件: {file_path}")

        # 读取当前内容
        try:
            content = full.read_text(encoding="utf-8")
        except OSError as e:
            return ToolResult.err(f"读取文件失败: {e}")

        # 统计 old_text 匹配次数 (必须恰好 1 次)
        count = content.count(old_text)
        if count != 1:
            return ToolResult.err(f"old_text 匹配 {count} 次, 期望 1 次")

        # 执行替换 (仅替换第一处, 因 count==1 故只有一处)
        new_content = content.replace(old_text, new_text, 1)

        # 计算相对路径
        rel_path = full.relative_to(self._root).as_posix()

        # 构建 MODIFY 变更集并原子应用
        cs = (
            ChangeSetBuilder(f"编辑文件: {rel_path}")
            .modify_file(rel_path, content, new_content)
            .build()
        )
        result = await self._diff.apply(cs, dry_run=self.preview_mode)
        if not result.success:
            return ToolResult.err(result.error or f"编辑失败: {rel_path}")

        return ToolResult.ok(
            {
                "path": rel_path,
                "replaced": 1,
                "preview": self.preview_mode,
                "content": new_content,
                "old_content": content,
                "diff": cs.to_diff(),
                "action": "modify",
            }
        )

    # ------------------------------------------------------------------------
    # 工具: search
    # ------------------------------------------------------------------------

    async def search(self, query: str, *, top_k: int = 10) -> ToolResult:
        """语义搜索代码 (走 CodeIndexer)。

        首次调用时若未配置 CodeIndexer, 会延迟初始化并索引项目目录。

        Args:
            query: 搜索查询 (自然语言或关键词)。
            top_k: 返回结果数上限。

        Returns:
            ToolResult, 成功时 output 为 CodeSlice 字典列表,
            失败时 error 描述错误原因。
        """
        # 延迟初始化 CodeIndexer
        if self._indexer is None:
            try:
                from fnixagent.core.code.indexer import CodeIndexer

                self._indexer = CodeIndexer()
                await self._indexer.index_directory(str(self._root))
            except Exception as e:
                return ToolResult.err(f"CodeIndexer 初始化失败: {e}")

        # 执行语义搜索
        try:
            slices = await self._indexer.search_code(query, top_k=top_k)
            return ToolResult.ok([s.to_dict() for s in slices])
        except Exception as e:
            return ToolResult.err(f"搜索失败: {e}")

    # ------------------------------------------------------------------------
    # 工具: git
    # ------------------------------------------------------------------------

    async def git(self, args: list[str]) -> ToolResult:
        """执行 Git 命令 (在沙箱内)。

        安全: 只允许 status/diff/log/add/commit/checkout/branch/show/stash
        禁止: push/pull/reset/clean/rm, 以及 --hard/--force 等危险标志。

        Args:
            args: Git 子命令及参数 (如 ["status", "--short"])。

        Returns:
            ToolResult, 成功时 output 为 Git 命令的 stdout 输出,
            失败时 error 描述错误原因 (含不安全命令的拒绝信息)。
        """
        # 空命令检查
        if not args:
            return ToolResult.err("Git 命令不能为空")

        # 安全校验 (白名单)
        if not self._is_safe_git_command(args):
            return ToolResult.err(
                f"不安全的 Git 命令: git {' '.join(args)} "
                f"(允许: {', '.join(sorted(self._SAFE_GIT_SUBCOMMANDS))})"
            )

        # 异步执行 git 命令
        cmd = ["git"] + args
        return await self._run_subprocess(cmd)

    # ------------------------------------------------------------------------
    # 工具: test
    # ------------------------------------------------------------------------

    async def compile_check(self, file_path: str | None = None) -> ToolResult:
        """编译/语法检查（Python: py_compile / compileall）。

        Args:
            file_path: 相对路径；为空则 compileall 整个项目（跳过常见目录）。

        Returns:
            ToolResult — 成功表示无语法错误。

        非 Python 前端项目（web-bench 的 Angular/React/Vue 等，.ts/.html/.css）
        没有 py_compile 语义：target 指向目录或非 .py 文件时跳过编译，
        视为成功（前端产物由 UI 预览/测试验证），避免误报「文件不存在」导致整题失败。
        """
        if file_path:
            try:
                full = self._resolve_path(file_path)
            except ValueError as e:
                return ToolResult.err(str(e))
            # 目录（如 src/app）→ 前端工程，py_compile 无意义，跳过。
            if full.is_dir():
                return ToolResult.ok(f"跳过编译：{file_path} 是目录（前端/非 Python 工程）")
            if not full.is_file():
                return ToolResult.err(f"文件不存在: {file_path}")
            # 非 .py 文件 → 前端/其他语言，跳过 py_compile。
            if full.suffix.lower() != ".py":
                return ToolResult.ok(f"跳过编译：{file_path} 非 Python 源码")
            cmd = ["python", "-m", "py_compile", str(full)]
            return await self._run_subprocess(cmd, timeout=60)

        # 全项目：只编译 .py，排除噪音目录
        cmd = [
            "python",
            "-m",
            "compileall",
            "-q",
            "-x",
            r"(?:[\\/])(?:\.fnix|node_modules|\.venv|venv|__pycache__|\.git)(?:[\\/])",
            str(self._root),
        ]
        return await self._run_subprocess(cmd, timeout=120)

    async def test(self, args: list[str] | None = None) -> ToolResult:
        """运行测试 (pytest)。

        Args:
            args: pytest 参数 (None = 默认 -x --tb=short)。

        Returns:
            ToolResult, 成功时 output 为 pytest 的 stdout 输出,
            失败时 error 描述错误原因 (含退出码和 stderr)。

        Notes:
            - 仓库里没有任何测试文件时直接跳过（成功），避免静态站/空仓误杀。
            - pytest 退出码 5 = no tests collected，同样视为跳过而非失败。
        """
        if not self._has_pytest_targets():
            return ToolResult.ok("跳过测试：未发现 pytest 用例（test_*.py / *_test.py / tests/）")

        # 默认参数: 首个失败即停止 + 简短回溯
        if args is None:
            args = ["-x", "--tb=short"]

        # 通过 python -m pytest 调用 (避免 Windows 上 pytest 脚本路径问题)
        cmd = ["python", "-m", "pytest"] + args
        # 测试可能耗时较长, 使用 300s 超时
        result = await self._run_subprocess(cmd, timeout=300)
        if result.success:
            return result

        # pytest exit code 5 = no tests collected
        err = result.error or ""
        if "退出码 5" in err or "no tests ran" in err.lower() or "collected 0 items" in err.lower():
            return ToolResult.ok(f"跳过测试：未收集到用例\n{err}")
        return result

    def _has_pytest_targets(self) -> bool:
        """是否存在可被 pytest 收集的测试文件。"""
        root = self._root
        skip_dirs = {
            ".git",
            ".fnix",
            "node_modules",
            ".venv",
            "venv",
            "__pycache__",
            ".pytest_cache",
            "dist",
            "build",
            "_references",
        }
        for path in root.rglob("*.py"):
            try:
                parts = set(path.relative_to(root).parts)
            except ValueError:
                continue
            if parts & skip_dirs:
                continue
            name = path.name
            if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
                return True
        return False

    # ------------------------------------------------------------------------
    # 内部: 子进程执行
    # ------------------------------------------------------------------------

    async def _run_subprocess(
        self,
        cmd: list[str],
        *,
        timeout: int = 60,
    ) -> ToolResult:
        """异步执行子进程 (统一入口)。

        使用 asyncio.create_subprocess_exec 创建子进程, 捕获 stdout/stderr,
        超时后强制终止。工作目录设为项目根。

        Args:
            cmd: 命令及参数列表 (如 ["git", "status", "--short"])。
            timeout: 超时秒数 (默认 60s)。

        Returns:
            ToolResult, 成功时 output 为 stdout 文本,
            失败时 error 含退出码和 stderr 详情。
        """
        # 创建子进程 (工作目录 = 项目根)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._root),
            )
        except FileNotFoundError:
            return ToolResult.err(f"命令未找到: {cmd[0]}")
        except OSError as e:
            return ToolResult.err(f"启动子进程失败: {e}")

        # 等待完成 (带超时)
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            # 超时: 强制终止进程, 避免僵尸进程
            try:
                proc.kill()
            except ProcessLookupError:
                # 进程已退出, 忽略
                pass
            await proc.wait()
            return ToolResult.err(f"命令执行超时 ({timeout}s): {' '.join(cmd)}")

        # 解码输出
        stdout_text = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        # 非零退出码视为失败
        if proc.returncode != 0:
            detail = stderr_text.strip() or stdout_text.strip()
            return ToolResult.err(f"命令失败 (退出码 {proc.returncode}): {detail}")

        return ToolResult.ok(stdout_text)

    # ------------------------------------------------------------------------
    # 内部: 路径解析
    # ------------------------------------------------------------------------

    def _resolve_path(self, file_path: str) -> Path:
        """解析相对路径为绝对路径 (限制在 project_root 内, 防穿越)。

        相对路径基于 project_root 解析, 绝对路径直接使用。
        解析后必须仍在 project_root 下, 否则抛出 ValueError。

        防穿越机制: 使用 Path.resolve() 处理 "..", 符号链接等,
        再通过 relative_to 校验结果是否仍在 project_root 内。

        Args:
            file_path: 文件路径 (相对或绝对)。

        Returns:
            解析后的绝对 Path 对象。

        Raises:
            ValueError: 路径越界 (解析后不在 project_root 内)。
        """
        p = Path(file_path)
        if p.is_absolute():
            full = p.resolve()
        else:
            full = (self._root / p).resolve()

        # 防穿越: 解析后必须仍在 project_root 下
        try:
            full.relative_to(self._root)
        except ValueError:
            raise ValueError(f"路径越界: {file_path} 解析为 {full}, 不在项目根目录 {self._root} 内")

        return full

    # ------------------------------------------------------------------------
    # 内部: Git 命令安全检查
    # ------------------------------------------------------------------------

    def _is_safe_git_command(self, args: list[str]) -> bool:
        """检查 Git 命令是否安全 (白名单)。

        检查规则:
          1. 子命令 (args[0]) 必须在白名单内
          2. 不含禁止子命令 (push/pull/reset/clean/rm)
          3. 不含危险标志 (--hard/--force/--force-with-lease)

        白名单: status/diff/log/add/commit/checkout/branch/show/stash
        禁止: push/pull/reset/clean/rm

        Args:
            args: Git 子命令及参数列表。

        Returns:
            True 表示安全, False 表示不安全。
        """
        # 空命令不安全
        if not args:
            return False

        subcommand = args[0]

        # 规则 1: 子命令必须在白名单内
        if subcommand not in self._SAFE_GIT_SUBCOMMANDS:
            return False

        # 规则 2: 检查是否包含禁止子命令 (防御性, 白名单已排除主命令,
        # 但 args 中可能拼接了其他子命令, 如 "stash" 后跟 "drop")
        for arg in args:
            if arg in self._FORBIDDEN_GIT_SUBCOMMANDS:
                return False

        # 规则 3: 检查危险标志 (--hard / --force / --force-with-lease)
        for arg in args:
            if arg in self._DANGEROUS_FLAGS:
                return False

        return True


__all__ = ["CodeTools", "ToolResult"]
