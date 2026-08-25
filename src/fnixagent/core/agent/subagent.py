"""子代理 (Subagent) — 隔离上下文的探索执行单元。

对齐一线 Agent 产品的 Task/子代理架构:
  主循环通过 dispatch_subtask 工具把"读代码/搜资料/大文件梳理"等
  探索性子任务派生到全新 AgenticLoop 中执行——子代理拥有独立 messages、
  独立 token 预算,只把最终结论(而非全部过程)回传主循环,
  从而保护主上下文窗口不被中间噪声淹没。

安全设计:
  - 深度防护: contextvar 记录派生深度,默认 max_depth=1(子代理不得再派生)
  - 最小权限: 子代理默认只有只读工具(read/grep/glob/ls/web),
    不含 write/edit/run_command 等副作用工具
  - 预算隔离: 独立 max_steps(默认 15),独立会话,不污染主循环 trace

用法(在 work_agent.py 注册后由 LLM 调用):
    dispatch_subtask({"description": "梳理 auth 模块结构", "prompt": "..."})
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import contextvars
import logging
from collections.abc import Callable
from typing import Any

_logger = logging.getLogger(__name__)

# 当前派生深度(contextvar 保证并发任务各自独立计数)
_SUBAGENT_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("subagent_depth", default=0)

# 子代理默认允许的只读工具(白名单制,新工具需显式加入)
_READONLY_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "read_lines",
        "list_dir",
        "list_directory",
        "ls",
        "glob",
        "grep",
        "search",
        "search_code",
        "search_project",
        "web_search",
        "web_fetch",
        "calculate",
        "get_context",
    }
)

SUBAGENT_SYSTEM_PROMPT = (
    "你是 FnixAgent 的子代理(Subagent),负责执行主代理委派的探索性子任务。\n"
    "规则:\n"
    "1. 只使用只读工具收集信息,不做任何写入/删除/命令执行\n"
    "2. 直接围绕委派目标工作,不要寒暄或复述任务\n"
    "3. 最终回复必须是结构化结论(要点列表/代码位置/数据),控制在 800 字内\n"
    "4. 信息不足时明确说明缺失了什么,不要编造\n"
    "工作区根目录: {workspace_root}"
)


class SubagentManager:
    """子代理管理器 — 派生并运行隔离子循环。"""

    def __init__(
        self,
        llm_factory: Callable[[], tuple[Callable[..., Any], Callable[..., Any] | None]],
        workspace_root: str,
        *,
        max_depth: int = 1,
        default_max_steps: int = 15,
        default_timeout_s: float = 300.0,
        allowed_tools: frozenset[str] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        """
        Args:
            llm_factory: 返回 (llm_call, llm_stream_call|None) 的工厂,
                与主循环同一 LLM 配置(每次调用时惰性取,保证覆盖生效)
            workspace_root: 工作区根目录
            max_depth: 最大嵌套深度(1=禁止子代理再派生)
            default_max_steps: 默认步数预算
            default_timeout_s: 单次子任务超时秒数
            allowed_tools: 工具白名单(None=默认只读集);
                团队角色系统据此构造不同能力的工人
            system_prompt: 角色系统提示词(None=默认子代理提示词)
        """
        self._llm_factory = llm_factory
        self.workspace_root = str(workspace_root)
        self.max_depth = max(1, int(max_depth))
        self.default_max_steps = max(3, int(default_max_steps))
        self.default_timeout_s = float(default_timeout_s)
        self.allowed_tools = frozenset(allowed_tools) if allowed_tools else None
        self._system_prompt_override = system_prompt

    # -- 核心执行 ----------------------------------------------------------

    async def run_subtask(
        self,
        description: str,
        prompt: str,
        *,
        max_steps: int | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        """运行一次隔离子任务,返回 {success, result, steps, depth, error}。

        失败不抛异常(返回 error 字段),与项目 fail-open 风格一致。
        """
        import asyncio

        depth = _SUBAGENT_DEPTH.get()
        if depth >= self.max_depth:
            return {
                "success": False,
                "result": "",
                "steps": 0,
                "depth": depth,
                "error": f"子代理嵌套深度超限(depth={depth} >= max={self.max_depth})",
            }

        steps_budget = max(3, int(max_steps or self.default_max_steps))
        timeout = float(timeout_s or self.default_timeout_s)

        try:
            llm_call, llm_stream = self._llm_factory()
        except Exception as exc:
            return {"success": False, "result": "", "steps": 0, "depth": depth, "error": str(exc)}

        registry = self._build_registry()

        from fnixagent.core.agent.loop import AgenticLoop

        prompt_template = self._system_prompt_override or SUBAGENT_SYSTEM_PROMPT
        loop = AgenticLoop(
            llm_call=llm_call,
            llm_stream_call=llm_stream,
            tool_executor=registry,
            workspace_root=self.workspace_root,
            max_steps=steps_budget,
            enable_reflection=True,
            enable_evolution=False,  # 子代理不触发自进化飞轮(避免重复计数)
            system_prompt=prompt_template.replace(
                "{workspace_root}", self.workspace_root
            ),
            max_reflect_rounds=1,
        )

        token = _SUBAGENT_DEPTH.set(depth + 1)
        try:
            result = await asyncio.wait_for(loop.run(prompt), timeout=timeout)
        except TimeoutError:
            return {
                "success": False,
                "result": "",
                "steps": len(loop.traces),
                "depth": depth + 1,
                "error": f"子任务超时(>{timeout}s)",
            }
        except Exception as exc:
            _logger.warning("subagent subtask failed", exc_info=True)
            return {
                "success": False,
                "result": "",
                "steps": len(loop.traces),
                "depth": depth + 1,
                "error": f"{type(exc).__name__}: {exc}",
            }
        finally:
            _SUBAGENT_DEPTH.reset(token)

        return {
            "success": bool(result.success),
            "result": (result.response or "")[:8000],
            "steps": len(result.steps or []),
            "tokens": result.total_tokens,
            "duration_ms": result.total_duration_ms,
            "depth": depth + 1,
            "error": result.error or "",
        }

    # -- 工具集 --------------------------------------------------------------

    def _build_registry(self):
        """构建白名单工具注册表(默认只读; 团队角色可携带写工具)。

        注意: 无论白名单如何, dispatch_subtask 永远被剥离 —— 工人是叶子节点,
        禁止再派生(与 Claude Code "无嵌套团队"红线一致)。
        """
        from fnixagent.core.tools.registry import ToolRegistry
        from fnixagent.core.tools.workspace import register_workspace_tools

        registry = ToolRegistry()
        register_workspace_tools(registry, self.workspace_root)

        whitelist = self.allowed_tools or _READONLY_TOOLS
        for name in list(getattr(registry, "_tools", {}).keys()):
            if name == "dispatch_subtask" or name not in whitelist:
                registry.unregister(name)
        return registry

    def _build_readonly_registry(self):
        """兼容旧名: 默认只读注册表。"""
        return self._build_registry()


def register_subagent_tool(
    registry,
    workspace_root: str,
    make_llm: Callable[[], tuple[Callable[..., Any], Callable[..., Any] | None]],
    *,
    max_depth: int = 1,
    default_max_steps: int = 15,
) -> SubagentManager:
    """把 dispatch_subtask 工具注册到给定 ToolRegistry。

    Args:
        registry: 主循环的 ToolRegistry
        workspace_root: 工作区根目录
        make_llm: 返回 (llm_call, llm_stream_call|None) 的零参工厂
        max_depth: 嵌套上限(1=扁平派生)
        default_max_steps: 子代理默认步数预算

    Returns:
        SubagentManager 实例(供测试/观测复用)
    """
    from fnixagent.core.tools.protocol import ToolMetadata
    from fnixagent.core.types import ToolPermission

    manager = SubagentManager(
        make_llm,
        workspace_root,
        max_depth=max_depth,
        default_max_steps=default_max_steps,
    )

    def _run(args: dict) -> dict:
        import asyncio

        description = str(args.get("description") or "").strip()[:200]
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            return {"success": False, "error": "prompt 不能为空"}
        steps = args.get("max_steps")
        try:
            coro = manager.run_subtask(
                description,
                prompt,
                max_steps=int(steps) if steps else None,
            )
        except (TypeError, ValueError):
            coro = manager.run_subtask(description, prompt)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # 已在事件循环中: 返回协程, 由 AgenticLoop._execute_tool 统一 await
        del loop
        return coro

    registry.register(
        ToolMetadata(
            name="dispatch_subtask",
            description=(
                "派发探索性子任务给隔离子代理(独立上下文/只读工具)。"
                "适用于大范围代码检索、多文件梳理、资料调研等会产生大量中间输出的场景,"
                "只回传最终结论以保护主上下文。参数: description(一句话目标), "
                "prompt(详细指令), max_steps(可选步数预算)"
            ),
            category="agent",
            permission_level=ToolPermission.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "子任务一句话目标"},
                    "prompt": {"type": "string", "description": "给子代理的详细指令"},
                    "max_steps": {
                        "type": "integer",
                        "description": "步数预算(默认15,范围3-30)",
                        "default": 15,
                    },
                },
                "required": ["prompt"],
            },
            timeout_ms=330_000,
        ),
        _run,
    )
    return manager


__all__ = [
    "SUBAGENT_SYSTEM_PROMPT",
    "SubagentManager",
    "register_subagent_tool",
]
