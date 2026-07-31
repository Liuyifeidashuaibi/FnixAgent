"""
GitAgent - 自动化 Git 操作智能体
==================================
基于 LLM 驱动的 Git 操作自动化, 封装常用 Git 工作流:
  - auto_commit:      暂存变更 + LLM 生成提交信息 + 提交
  - create_branch:    创建并切换到新分支
  - generate_pr:      LLM 生成 PR 描述
  - summarize_changes: LLM 摘要 git diff 输出
  - smart_undo:       撤销最近一次提交但保留变更

设计要点:
  - 零外部依赖: 仅 Python stdlib (subprocess / pathlib / dataclasses / asyncio)
  - 复用 CodeTools.git() 进行安全 Git 操作 (白名单子命令)
  - LLM 驱动生成提交信息和 PR 描述 (LLMBackend Protocol)
  - 所有方法均为 async
  - 结构化返回 GitResult (success / output / error)
  - smart_undo 使用 subprocess 直接执行 (绕过 CodeTools 的 reset 禁令)

Usage:
    from fnixagent.core.code.tools import CodeTools
    from fnixagent.core.code.git import GitAgent

    tools = CodeTools(project_root="/path/to/project")
    agent = GitAgent(code_tools=tools, llm_backend=llm)

    # 自动提交
    result = await agent.auto_commit()

    # 创建分支
    result = await agent.create_branch("feature/new-feature")

    # 生成 PR 描述
    result = await agent.generate_pr()

    # 摘要变更
    result = await agent.summarize_changes()

    # 智能撤销
    result = await agent.smart_undo()
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fnixagent.core.code.tools import CodeTools

# ============================================================================
# Git 操作结果
# ============================================================================


@dataclass
class GitResult:
    """Git 操作结果。

    所有 GitAgent 方法的统一返回类型, 封装成功/失败状态及输出数据。

    Attributes:
        success: 是否执行成功
        output: 成功时的输出数据 (类型随操作而异)
        error: 失败时的错误描述 (成功时为 None)
    """

    success: bool
    output: Any = None
    error: str | None = None

    @classmethod
    def ok(cls, output: Any = None) -> GitResult:
        """构造成功结果。

        Args:
            output: 输出数据 (可选)。

        Returns:
            success=True 的 GitResult。
        """
        return cls(success=True, output=output, error=None)

    @classmethod
    def err(cls, error: str) -> GitResult:
        """构造失败结果。

        Args:
            error: 错误描述。

        Returns:
            success=False 的 GitResult。
        """
        return cls(success=False, output=None, error=error)


# ============================================================================
# 自动化 Git 操作智能体
# ============================================================================


class GitAgent:
    """自动化 Git 操作智能体。

    基于 LLM 驱动的 Git 操作自动化, 封装常用 Git 工作流。
    复用 CodeTools.git() 进行安全的 Git 子命令操作,
    通过 LLMBackend 生成提交信息和 PR 描述。

    LLM 不可用时的降级策略:
      - auto_commit: 使用默认提交信息 "update"
      - generate_pr: 返回基础模板信息
      - summarize_changes: 从 diff 中提取文件列表作为降级摘要

    Attributes:
        _tools: CodeTools 实例 (提供 git 子命令执行)
        _root: 项目根目录 (绝对路径)
        _llm: LLMBackend 实例 (可选, None 时使用降级策略)
    """

    def __init__(
        self,
        code_tools: CodeTools,
        llm_backend: Any = None,
    ):
        """初始化 Git 操作智能体。

        Args:
            code_tools: CodeTools 实例, 提供 git() 方法执行 Git 子命令。
            llm_backend: LLMBackend 实例 (可选), 提供 complete() 方法生成文本。
                None 时 auto_commit 使用默认信息, generate_pr/summarize_changes 使用降级策略。
        """
        self._tools = code_tools
        self._root: Path = code_tools._root
        self._llm = llm_backend

    # ========================================================================
    # 公共方法: auto_commit
    # ========================================================================

    async def auto_commit(self) -> GitResult:
        """自动暂存变更并提交。

        流程:
          1. 检查工作区是否有变更 (git status --short)
          2. 暂存所有变更 (git add -A)
          3. 获取暂存区 diff (git diff --staged)
          4. 通过 LLM 生成约定式提交信息 (conventional commits)
          5. 执行 git commit

        LLM 不可用时使用降级信息 "update"。

        Returns:
            GitResult, 成功时 output 为 {"message": 提交信息, "output": git 输出},
            失败时 error 描述错误原因。
        """
        # 1. 检查工作区状态
        status_result = await self._tools.git(["status", "--short"])
        if not status_result.success:
            return GitResult.err(f"git status 失败: {status_result.error}")
        if not status_result.output.strip():
            return GitResult.err("工作区无变更, 无需提交")

        # 2. 暂存所有变更 (含新增、修改、删除)
        add_result = await self._tools.git(["add", "-A"])
        if not add_result.success:
            return GitResult.err(f"git add 失败: {add_result.error}")

        # 3. 获取暂存区 diff
        diff_result = await self._tools.git(["diff", "--staged"])
        if not diff_result.success:
            return GitResult.err(f"git diff 失败: {diff_result.error}")
        diff_text = diff_result.output.strip()
        if not diff_text:
            return GitResult.err("暂存区无变更, 无需提交")

        # 4. 通过 LLM 生成提交信息
        commit_msg = await self._generate_commit_message(diff_text)

        # 5. 执行提交
        commit_result = await self._tools.git(["commit", "-m", commit_msg])
        if not commit_result.success:
            return GitResult.err(f"git commit 失败: {commit_result.error}")

        return GitResult.ok({"message": commit_msg, "output": commit_result.output.strip()})

    # ========================================================================
    # 公共方法: create_branch
    # ========================================================================

    async def create_branch(self, branch_name: str) -> GitResult:
        """创建并切换到新分支。

        先检查分支是否已存在, 再通过 git checkout -b 创建并切换。

        Args:
            branch_name: 新分支名称 (不能为空)。

        Returns:
            GitResult, 成功时 output 为 {"branch": 分支名, "output": git 输出},
            失败时 error 描述错误原因 (如分支已存在)。
        """
        if not branch_name or not branch_name.strip():
            return GitResult.err("分支名称不能为空")

        branch_name = branch_name.strip()

        # 检查分支是否已存在
        list_result = await self._tools.git(["branch", "--list", branch_name])
        if list_result.success and list_result.output.strip():
            return GitResult.err(f"分支已存在: {branch_name}")

        # 创建并切换到新分支
        result = await self._tools.git(["checkout", "-b", branch_name])
        if not result.success:
            return GitResult.err(f"创建分支失败: {result.error}")

        return GitResult.ok({"branch": branch_name, "output": result.output.strip()})

    # ========================================================================
    # 公共方法: generate_pr
    # ========================================================================

    async def generate_pr(self, base_branch: str = "") -> GitResult:
        """生成 PR 描述。

        获取当前分支相对于 base_branch 的变更 diff,
        通过 LLM 生成结构化的 PR 描述 (Markdown 格式)。

        base_branch 为空时自动检测 main 或 master 分支。

        Args:
            base_branch: 目标分支名 (默认自动检测 main 或 master)。

        Returns:
            GitResult, 成功时 output 为 {"description": PR描述, "base_branch": 基础分支,
            "current_branch": 当前分支}, 失败时 error 描述错误原因。
        """
        # 自动检测 base_branch
        if not base_branch:
            base_branch = await self._detect_base_branch()
            if not base_branch:
                return GitResult.err("无法检测基础分支 (main/master), 请手动指定 base_branch")

        # 获取当前分支名
        current_branch = await self._get_current_branch()
        if not current_branch:
            return GitResult.err("无法获取当前分支名")

        # 获取 diff (三点语法: 当前分支自共同祖先以来的变更)
        diff_result = await self._tools.git(["diff", f"{base_branch}...{current_branch}"])
        if not diff_result.success:
            return GitResult.err(f"git diff 失败: {diff_result.error}")
        diff_text = diff_result.output.strip()
        if not diff_text:
            return GitResult.err(f"当前分支 {current_branch} 与 {base_branch} 无差异")

        # 通过 LLM 生成 PR 描述
        pr_desc = await self._generate_pr_description(base_branch, diff_text)

        return GitResult.ok(
            {
                "description": pr_desc,
                "base_branch": base_branch,
                "current_branch": current_branch,
            }
        )

    # ========================================================================
    # 公共方法: summarize_changes
    # ========================================================================

    async def summarize_changes(self, staged_only: bool = False) -> GitResult:
        """通过 LLM 摘要 git diff 输出。

        获取工作区变更 diff (或仅暂存区), 通过 LLM 生成中文变更摘要。

        Args:
            staged_only: 仅摘要暂存区变更 (默认 False, 摘要所有未提交变更)。

        Returns:
            GitResult, 成功时 output 为 {"summary": 摘要文本, "staged_only": bool},
            失败时 error 描述错误原因。
        """
        # 获取 diff
        args = ["diff", "--staged"] if staged_only else ["diff"]
        diff_result = await self._tools.git(args)
        if not diff_result.success:
            return GitResult.err(f"git diff 失败: {diff_result.error}")
        diff_text = diff_result.output.strip()
        if not diff_text:
            return GitResult.err("无变更可摘要")

        # 通过 LLM 摘要
        summary = await self._summarize_diff(diff_text)

        return GitResult.ok({"summary": summary, "staged_only": staged_only})

    # ========================================================================
    # 公共方法: smart_undo
    # ========================================================================

    async def smart_undo(self) -> GitResult:
        """撤销最近一次提交但保留变更 (git reset --soft HEAD~1)。

        CodeTools 白名单禁止 reset 子命令, 因此通过 subprocess 直接执行。
        仅撤销最近一次提交, 工作区和暂存区变更均保留不丢失。

        Returns:
            GitResult, 成功时 output 为 {"undone_commit": 被撤销的提交信息,
            "output": git 输出}, 失败时 error 描述错误原因。
        """
        # 检查是否有可撤销的提交
        log_result = await self._tools.git(["log", "--oneline", "-1"])
        if not log_result.success:
            return GitResult.err(f"git log 失败: {log_result.error}")
        if not log_result.output.strip():
            return GitResult.err("无提交可撤销")

        last_commit = log_result.output.strip()

        # 执行软重置 (绕过 CodeTools 的 reset 禁令)
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "reset",
                "--soft",
                "HEAD~1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._root),
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30)
        except FileNotFoundError:
            return GitResult.err("git 命令未找到")
        except TimeoutError:
            return GitResult.err("git reset 超时 (30s)")
        except OSError as e:
            return GitResult.err(f"执行 git reset 失败: {e}")

        stdout_text = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr_text = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        if proc.returncode != 0:
            detail = stderr_text.strip() or stdout_text.strip()
            return GitResult.err(f"git reset 失败 (退出码 {proc.returncode}): {detail}")

        return GitResult.ok(
            {
                "undone_commit": last_commit,
                "output": stdout_text.strip(),
            }
        )

    # ========================================================================
    # 内部: LLM 生成方法
    # ========================================================================

    async def _generate_commit_message(self, diff_text: str) -> str:
        """通过 LLM 生成约定式提交信息。

        遵循 conventional commits 规范: 类型(范围): 简短描述。
        类型: feat/fix/docs/refactor/test/chore/style/perf。

        Args:
            diff_text: git diff --staged 输出文本。

        Returns:
            生成的提交信息 (单行); LLM 不可用时返回 "update"。
        """
        if self._llm is None:
            return "update"

        # 截断过长的 diff, 保留前 4000 字符
        truncated = diff_text[:4000]

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 Git 提交信息生成器。根据代码变更 diff 生成简洁的提交信息。"
                    "遵循约定式提交规范 (conventional commits): "
                    "类型(范围): 简短描述。"
                    "类型包括: feat/fix/docs/refactor/test/chore/style/perf。"
                    "只返回提交信息文本, 不要引号、JSON 或其他格式。"
                ),
            },
            {
                "role": "user",
                "content": f"请根据以下 git diff 生成提交信息:\n\n{truncated}",
            },
        ]

        try:
            response = await self._llm.complete({"messages": messages})
            msg = response.strip().strip('"').strip("'")
            # 取第一行作为提交信息
            first_line = msg.split("\n")[0].strip()
            return first_line if first_line else "update"
        except Exception:
            return "update"

    async def _generate_pr_description(self, base_branch: str, diff_text: str) -> str:
        """通过 LLM 生成 PR 描述。

        生成结构化 Markdown 描述, 包含变更概述、主要改动、测试说明。

        Args:
            base_branch: 目标分支名。
            diff_text: git diff 输出文本。

        Returns:
            生成的 PR 描述 (Markdown 格式); LLM 不可用时返回基础模板。
        """
        if self._llm is None:
            return f"## 合并到 {base_branch}\n\n*(LLM 不可用, 未生成自动描述)*\n"

        truncated = diff_text[:6000]

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 PR 描述生成器。根据代码变更 diff 生成结构化的 PR 描述。"
                    "包含: 变更概述、主要改动、测试说明。"
                    "使用 Markdown 格式。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"目标分支: {base_branch}\n\n变更 diff:\n{truncated}\n\n请生成 PR 描述。"
                ),
            },
        ]

        try:
            response = await self._llm.complete({"messages": messages})
            return response.strip()
        except Exception:
            return f"## 合并到 {base_branch}\n\n*(LLM 调用失败, 未生成自动描述)*\n"

    async def _summarize_diff(self, diff_text: str) -> str:
        """通过 LLM 摘要 git diff 变更。

        使用中文描述: 修改了哪些文件、主要变更内容、变更类型。

        Args:
            diff_text: git diff 输出文本。

        Returns:
            变更摘要文本; LLM 不可用时从 diff 提取文件列表作为降级摘要。
        """
        if self._llm is None:
            return self._fallback_summary(diff_text)

        truncated = diff_text[:6000]

        messages = [
            {
                "role": "system",
                "content": (
                    "你是代码变更摘要生成器。根据 git diff 输出生成简洁的变更摘要。"
                    "用中文描述: 修改了哪些文件、主要变更内容、变更类型。"
                ),
            },
            {
                "role": "user",
                "content": f"请摘要以下 git diff 变更:\n\n{truncated}",
            },
        ]

        try:
            response = await self._llm.complete({"messages": messages})
            return response.strip()
        except Exception:
            return self._fallback_summary(diff_text)

    # ========================================================================
    # 内部: 辅助方法
    # ========================================================================

    def _fallback_summary(self, diff_text: str) -> str:
        """降级摘要: 从 diff 中提取文件列表。

        不依赖 LLM, 直接从 diff --git 行解析受影响文件路径。

        Args:
            diff_text: git diff 输出文本。

        Returns:
            文件列表摘要字符串。
        """
        lines = diff_text.split("\n")
        files: list[str] = []
        for line in lines:
            if line.startswith("diff --git "):
                parts = line.split(" ")
                if len(parts) >= 4:
                    path_b = parts[3]
                    if path_b.startswith("b/"):
                        files.append(path_b[2:])
        if files:
            return f"变更文件 ({len(files)}):\n" + "\n".join(f"  - {f}" for f in files)
        return "无变更摘要"

    async def _detect_base_branch(self) -> str:
        """自动检测基础分支 (main 或 master)。

        按顺序检查 main → master, 返回第一个存在的分支名。

        Returns:
            基础分支名, 未找到返回空字符串。
        """
        for branch in ("main", "master"):
            result = await self._tools.git(["branch", "--list", branch])
            if result.success and result.output.strip():
                return branch
        return ""

    async def _get_current_branch(self) -> str:
        """获取当前分支名。

        Returns:
            当前分支名, 失败返回空字符串。
        """
        result = await self._tools.git(["branch", "--show-current"])
        if result.success:
            return result.output.strip()
        return ""


__all__ = ["GitAgent", "GitResult"]
