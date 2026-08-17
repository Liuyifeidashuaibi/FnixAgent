"""
工具注册中心 (Tool Registry)。

管理所有已注册工具的元数据与执行函数。
支持: 注册/注销/查询/按分类列出/生成 LLM 工具描述列表。
线程安全: threading.RLock。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from fnixagent.core.exceptions import ToolNotFoundError
from fnixagent.core.tools.protocol import RegisteredTool, ToolFunc, ToolMetadata
from fnixagent.core.types import ToolPermission


class ToolRegistry:
    """
    工具注册中心。

    用法:
        registry = ToolRegistry()

        # 方式1: 直接注册
        registry.register(metadata, func)

        # 方式2: 装饰器风格
        @registry.tool("search_paper", "搜索学术论文", category="search")
        def search_paper(args: dict) -> dict:
            ...
    """

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self._lock = threading.RLock()

    # -- 注册 --------------------------------------------------------------

    def register(
        self,
        metadata: ToolMetadata,
        func: ToolFunc,
    ) -> None:
        """注册一个工具。若 name 已存在则覆盖。

        Args:
            metadata: 工具元数据(name 非空,由 ToolMetadata.__post_init__ 校验)
            func: 工具执行函数,签名为 (dict) -> Any

        Raises:
            ValueError: metadata.name 为空
            TypeError: func 不是可调用对象
        """
        if not callable(func):
            raise TypeError(f"func 必须可调用, 实为 {type(func).__name__}")
        with self._lock:
            self._tools[metadata.name] = RegisteredTool(metadata=metadata, func=func)

    def unregister(self, name: str) -> bool:
        """注销工具。

        Args:
            name: 工具名

        Returns:
            是否成功删除(False 表示工具不存在)
        """
        with self._lock:
            return self._tools.pop(name, None) is not None

    def tool(
        self,
        name: str,
        description: str,
        category: str = "general",
        permission_level: ToolPermission = ToolPermission.LOW,
        input_schema: dict | None = None,
        timeout_ms: int = 30000,
        **kwargs: Any,
    ) -> Callable[[ToolFunc], ToolFunc]:
        """装饰器风格注册工具。

        @registry.tool("my_tool", "我的工具", category="utils")
        def my_tool(args: dict) -> dict:
            return {"result": "ok"}

        Args:
            name: 工具唯一名(非空)
            description: 功能描述(非空)
            category: 分类
            permission_level: 权限等级
            input_schema: JSON Schema 入参描述
            timeout_ms: 超时毫秒(正整数)
            **kwargs: 透传给 ToolMetadata 的额外字段

        Returns:
            装饰器函数
        """

        def decorator(func: ToolFunc) -> ToolFunc:
            meta = ToolMetadata(
                name=name,
                description=description,
                category=category,
                permission_level=permission_level,
                input_schema=input_schema or {},
                timeout_ms=timeout_ms,
                **kwargs,
            )
            self.register(meta, func)
            return func

        return decorator

    # -- 查询 --------------------------------------------------------------

    def get(self, name: str) -> RegisteredTool:
        """获取已注册工具。

        Args:
            name: 工具名

        Returns:
            RegisteredTool(含 metadata 与 func)

        Raises:
            ToolNotFoundError: 工具未注册
        """
        with self._lock:
            tool = self._tools.get(name)
            if tool is None:
                raise ToolNotFoundError(f"工具 '{name}' 未注册")
            return tool

    def has(self, name: str) -> bool:
        """是否存在。

        Args:
            name: 工具名

        Returns:
            是否已注册
        """
        with self._lock:
            return name in self._tools

    def list_tools(self, category: str | None = None) -> list[ToolMetadata]:
        """列出所有(或指定分类的)工具元数据。

        Args:
            category: 可选分类过滤;None 表示全部

        Returns:
            工具元数据列表
        """
        with self._lock:
            tools = list(self._tools.values())
            if category:
                tools = [t for t in tools if t.metadata.category == category]
            return [t.metadata for t in tools]

    def list_for_llm(
        self,
        permission_filter: ToolPermission | None = None,
    ) -> list[dict]:
        """生成给 LLM function-calling 的工具描述列表。

        可按权限过滤(如不暴露 HIGH 权限工具给普通用户)。

        Args:
            permission_filter: 权限上限;None 表示不过滤

        Returns:
            OpenAI tools API 兼容的工具描述列表
        """
        with self._lock:
            result = []
            for tool in self._tools.values():
                if not tool.metadata.enabled:
                    continue
                if permission_filter is not None:
                    # LOW < MIDDLE < HIGH, 过滤掉高于指定权限的
                    perm_order = {
                        ToolPermission.LOW: 0,
                        ToolPermission.MIDDLE: 1,
                        ToolPermission.HIGH: 2,
                    }
                    if perm_order[tool.metadata.permission_level] > perm_order[permission_filter]:
                        continue
                result.append(tool.metadata.to_llm_description())
            return result

    @property
    def count(self) -> int:
        """已注册工具总数。"""
        with self._lock:
            return len(self._tools)

    def clear(self) -> None:
        """清空全部注册。"""
        with self._lock:
            self._tools.clear()

    # ============================================================
    # AgenticLoop 兼容接口
    # ============================================================

    def execute(self, tool_name: str, args: dict) -> Any:
        """执行工具调用 (AgenticLoop 兼容接口)。

        调用已注册工具的执行函数，返回原始结果。

        Args:
            tool_name: 工具名
            args: 工具参数字典

        Returns:
            工具执行结果 (ToolResult / dict / str 等)

        Raises:
            ToolNotFoundError: 工具未注册
        """
        from fnixagent.core.tools.policy import get_tool_policy

        args = dict(args or {})
        decision = get_tool_policy().evaluate(tool_name, args)
        if decision.cached_result is not None and decision.reason == "idempotent_cache_hit":
            return decision.cached_result
        if not decision.allowed:
            return {
                "success": False,
                "error": decision.reason,
                "risk": decision.risk.value,
                "requires_approval": decision.requires_approval,
                "idempotency_key": decision.idempotency_key,
            }

        with self._lock:
            tool = self._tools.get(tool_name)
            if tool is None:
                raise ToolNotFoundError(f"工具 '{tool_name}' 未注册")
        result = tool.func(args)
        get_tool_policy().remember_success(decision.idempotency_key, result)
        return result

    def get_tool_definitions(self) -> list[dict]:
        """获取 OpenAI tools API 兼容的工具定义列表 (AgenticLoop 兼容接口)。

        Returns:
            OpenAI function-calling 格式的工具定义列表
        """
        return self.list_for_llm()

    def get_tools_description(self) -> str:
        """获取人类可读的工具描述文本 (AgenticLoop 兼容接口)。

        Returns:
            格式化的工具列表文本
        """
        with self._lock:
            lines = []
            for tool in self._tools.values():
                if not tool.metadata.enabled:
                    continue
                lines.append(f"- {tool.metadata.name}: {tool.metadata.description}")
            return "\n".join(lines) if lines else "(无可用工具)"
