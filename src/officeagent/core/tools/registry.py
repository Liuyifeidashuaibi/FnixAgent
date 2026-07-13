"""
工具注册中心 (Tool Registry)。

管理所有已注册工具的元数据与执行函数。
支持: 注册/注销/查询/按分类列出/生成 LLM 工具描述列表。
线程安全: threading.RLock。
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Optional

from officeagent.core.exceptions import ToolNotFoundError
from officeagent.core.tools.protocol import RegisteredTool, ToolFunc, ToolMetadata
from officeagent.core.types import ToolPermission


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
            self._tools[metadata.name] = RegisteredTool(
                metadata=metadata, func=func
            )

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

    def list_tools(
        self, category: Optional[str] = None
    ) -> list[ToolMetadata]:
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
        permission_filter: Optional[ToolPermission] = None,
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
