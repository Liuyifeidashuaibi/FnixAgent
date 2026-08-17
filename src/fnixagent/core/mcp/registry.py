"""MCP 工具注册表(P2-3)。

管理多个 MCP server 连接,把它们暴露的工具统一注册为本地可用工具。
职责:
  - register_server:添加 MCP server 配置,自动连接 + 同步工具列表
  - unregister_server:断开连接 + 移除该 server 全部工具
  - sync_tools / sync_all:重新拉取工具列表(刷新缓存)
  - to_tool_metadata:把 MCPToolDef 转换为本地 ToolMetadata(供 ToolExecutor 调度)
  - make_executor:为指定 MCP 工具生成 ToolFunc(供 ToolRegistry.register 使用)
  - call:直接调用 MCP 工具(无需经过 ToolRegistry,适合临时调用)

设计:
  - 阻塞调用为主(底层 MCPClient 自带同步包装),简化使用
  - 工具名冲突解决:加上 server_id 前缀(如 "feishu.send_message")
  - 工具列表为快照,server 端变化需显式 sync_tools
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import threading
from typing import Any

from fnixagent.core.mcp.client import (
    MCPClient,
    MCPToolExecutionError,
)
from fnixagent.core.mcp.types import (
    MCPRequest,
    MCPServerInfo,
    MCPServerStatus,
    MCPToolDef,
    MCPTransport,
)
from fnixagent.core.tools.protocol import ToolFunc, ToolMetadata
from fnixagent.core.types import ToolPermission

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class MCPRegistryError(Exception):
    """MCP 注册表基础异常。"""

class MCPServerNotFoundError(MCPRegistryError):
    """server_id 不存在。"""

class MCPServerAlreadyExistsError(MCPRegistryError):
    """server_id 已存在。"""

class MCPToolNotFoundError(MCPRegistryError):
    """工具名在所有 server 中找不到。"""

# ---------------------------------------------------------------------------
# MCPToolRegistry
# ---------------------------------------------------------------------------

class MCPToolRegistry:
    """MCP 工具注册表:管理多 server + 多工具。

    用法:
        registry = MCPToolRegistry()
        registry.register_server(
            server_id="feishu",
            transport=MCPTransport.STDIO,
            command="npx",
            args=["-y", "@feishu/mcp-server"],
        )
        # 获取所有工具的 ToolMetadata(供 LLM function-calling)
        tools = registry.list_all_tools_metadata()
        # 调用工具
        result = registry.call("feishu.send_message", {"user_id": "x", "text": "hi"})
    """

    def __init__(self) -> None:
        self._servers: dict[str, MCPClient] = {}  # server_id → client
        self._tools: dict[str, MCPToolDef] = {}  # 全局工具名 → def
        self._tool_to_server: dict[str, str] = {}  # 全局工具名 → server_id
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # server 管理
    # ------------------------------------------------------------------

    def register_server(
        self,
        server_id: str,
        transport: MCPTransport = MCPTransport.STDIO,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        description: str = "",
        auto_connect: bool = True,
    ) -> MCPServerInfo:
        """注册并(可选)连接 MCP server。

        Args:
            server_id: 本地唯一 ID(用于路由工具调用)
            transport: 传输协议(STDIO/SSE/WebSocket)
            command/args/env: STDIO 模式下的启动命令
            url/headers: SSE 模式下的服务器 URL 与 HTTP 头
            auto_connect: 是否自动连接 + 同步工具(默认 True)

        Raises:
            MCPServerAlreadyExistsError: server_id 已存在
            MCPConnectionError: 连接失败(仅 auto_connect=True 时)
            ValueError: server_id 为空
        """
        if not server_id or not isinstance(server_id, str):
            raise ValueError("server_id must be a non-empty string")

        # Trust ledger fail-closed (Beta): approve before connect
        from fnixagent.core.mcp.trust import McpTrustError, assert_trusted_for_connect

        try:
            assert_trusted_for_connect(
                server_id,
                command=command,
                args=list(args or []),
                remote_url=url or "",
            )
        except McpTrustError:
            raise

        with self._lock:
            if server_id in self._servers:
                raise MCPServerAlreadyExistsError(f"MCP server '{server_id}' already registered")
            server_info = MCPServerInfo(
                server_id=server_id,
                name=server_id,
                transport=transport,
                command=command,
                args=list(args or []),
                env=dict(env or {}),
                url=url,
                headers=dict(headers or {}),
                description=description,
            )
            client = MCPClient(server_info)
            self._servers[server_id] = client
            if auto_connect:
                try:
                    client.connect_sync()
                    self._refresh_server_tools(server_id)
                except Exception:
                    # 连接失败也保留配置,允许后续 retry
                    self._servers[server_id] = client
                    raise
            return server_info

    def unregister_server(self, server_id: str) -> MCPServerInfo:
        """注销 server(断开连接 + 移除该 server 全部工具)。

        Raises:
            MCPServerNotFoundError: server_id 不存在
        """
        with self._lock:
            client = self._servers.get(server_id)
            if client is None:
                raise MCPServerNotFoundError(f"MCP server '{server_id}' not registered")
            try:
                client.disconnect_sync()
            except Exception:
                pass
            # 移除该 server 全部工具
            tools_to_remove = [
                name for name, sid in self._tool_to_server.items() if sid == server_id
            ]
            for name in tools_to_remove:
                self._tools.pop(name, None)
                self._tool_to_server.pop(name, None)
            del self._servers[server_id]
            return client.server_info

    def list_servers(self) -> list[MCPServerInfo]:
        """列出全部已注册 server 的信息。"""
        with self._lock:
            return [c.server_info for c in self._servers.values()]

    def get_server(self, server_id: str) -> MCPClient | None:
        """按 ID 获取 MCPClient(不存在返回 None)。"""
        with self._lock:
            return self._servers.get(server_id)

    def reconnect(self, server_id: str) -> MCPServerInfo:
        """重连 server(用于网络抖动后恢复)。"""
        with self._lock:
            client = self._servers.get(server_id)
            if client is None:
                raise MCPServerNotFoundError(f"MCP server '{server_id}' not registered")
            try:
                client.disconnect_sync()
            except Exception:
                pass
            client.server_info.status = MCPServerStatus.CONNECTING
            client.connect_sync()
            self._refresh_server_tools(server_id)
            return client.server_info

    # ------------------------------------------------------------------
    # 工具同步
    # ------------------------------------------------------------------

    def sync_tools(self, server_id: str) -> list[MCPToolDef]:
        """重新拉取指定 server 的工具列表(刷新缓存)。"""
        with self._lock:
            client = self._servers.get(server_id)
            if client is None:
                raise MCPServerNotFoundError(f"MCP server '{server_id}' not registered")
            if not client.is_connected:
                client.connect_sync()
            return self._refresh_server_tools(server_id)

    def sync_all(self) -> dict[str, list[MCPToolDef]]:
        """同步全部 server 的工具列表。

        Returns:
            {server_id: [tools]}(失败 server 返回空列表,不抛异常)
        """
        results: dict[str, list[MCPToolDef]] = {}
        with self._lock:
            server_ids = list(self._servers.keys())
        for sid in server_ids:
            try:
                results[sid] = self.sync_tools(sid)
            except Exception:
                results[sid] = []
        return results

    def _refresh_server_tools(self, server_id: str) -> list[MCPToolDef]:
        """从 client 拉取工具列表,加上 server_id 前缀后写入索引。"""
        client = self._servers[server_id]
        # 先清理旧工具
        old_tools = [name for name, sid in self._tool_to_server.items() if sid == server_id]
        for name in old_tools:
            self._tools.pop(name, None)
            self._tool_to_server.pop(name, None)
        # 拉取新工具
        raw_tools = client.list_tools_sync()
        for tool in raw_tools:
            # 全局名:server_id.tool_name(避免冲突)
            global_name = f"{server_id}.{tool.name}"
            global_tool = MCPToolDef(
                name=global_name,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                server_id=server_id,
                annotations=tool.annotations,
                source=tool.source,
                cost_score=tool.cost_score,
                layer=tool.layer,
            )
            self._tools[global_name] = global_tool
            self._tool_to_server[global_name] = server_id
        return list(self._tools.values())

    # ------------------------------------------------------------------
    # 工具查询
    # ------------------------------------------------------------------

    def list_all_tools(self) -> list[MCPToolDef]:
        """列出全部 server 的全部工具(MCPToolDef 格式)。"""
        with self._lock:
            return list(self._tools.values())

    def list_all_tools_metadata(self) -> list[ToolMetadata]:
        """列出全部工具的本地 ToolMetadata 格式(供 LLM function-calling)。"""
        with self._lock:
            return [self.to_tool_metadata(t) for t in self._tools.values()]

    def get_tool(self, tool_name: str) -> MCPToolDef | None:
        """按全局工具名获取 MCPToolDef。"""
        with self._lock:
            return self._tools.get(tool_name)

    def to_tool_metadata(self, tool: MCPToolDef) -> ToolMetadata:
        """把 MCPToolDef 转换为本地 ToolMetadata。

        保留 input_schema;permission_level 默认 LOW(可由 caller 覆盖)。
        skill_level 根据 annotations.readOnlyHint 决定。
        """
        # 根据 MCP 注解推断 skill_level
        annotations = tool.annotations or {}
        is_readonly = annotations.get("readOnlyHint", False)
        is_destructive = annotations.get("destructiveHint", False)
        if is_destructive:
            skill_level = "reasoning"  # 破坏性操作需确认
        elif is_readonly:
            skill_level = "basic"  # 只读操作自动调用
        else:
            skill_level = "reasoning"  # 默认需确认
        return ToolMetadata(
            name=tool.name,
            description=tool.description or f"MCP tool from {tool.server_id}",
            category=f"mcp_{tool.server_id}",
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            permission_level=ToolPermission.LOW,
            skill_level=skill_level,
            version="1.0.0",
        )

    # ------------------------------------------------------------------
    # 工具调用
    # ------------------------------------------------------------------

    def make_executor(self, tool_name: str) -> ToolFunc:
        """为指定 MCP 工具生成 ToolFunc(供 ToolRegistry.register 使用)。

        ToolFunc 签名:(args: dict) -> Any
        内部封装:args → MCPRequest → client.call_tool → MCPResponse.result
        """
        if tool_name not in self._tools:
            raise MCPToolNotFoundError(f"MCP tool '{tool_name}' not found in registry")

        def executor(args: dict[str, Any]) -> Any:
            return self.call(tool_name, args)

        return executor

    def call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int = 30000,
        trace_id: str = "",
        user_id: str = "",
        tenant_id: str = "",
    ) -> Any:
        """直接调用 MCP 工具(无需经过 ToolRegistry)。

        Args:
            tool_name: 全局工具名(如 "feishu.send_message")
            arguments: 工具参数
            timeout_ms: 超时毫秒

        Returns:
            工具返回结果(成功时)

        Raises:
            MCPToolNotFoundError: 工具不存在
            MCPToolExecutionError: 调用失败
            ValueError: tool_name 为空
        """
        if not tool_name:
            raise ValueError("tool_name must be non-empty")
        with self._lock:
            server_id = self._tool_to_server.get(tool_name)
            if server_id is None:
                raise MCPToolNotFoundError(f"MCP tool '{tool_name}' not found")
            client = self._servers[server_id]
        # 去掉 server_id 前缀,还原原始工具名
        original_name = tool_name
        if tool_name.startswith(f"{server_id}."):
            original_name = tool_name[len(server_id) + 1 :]
        request = MCPRequest(
            tool_name=original_name,
            arguments=arguments,
            timeout_ms=timeout_ms,
            server_id=server_id,
            trace_id=trace_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        response = client.call_tool_sync(request)
        if not response.success:
            raise MCPToolExecutionError(f"MCP tool '{tool_name}' failed: {response.error}")
        return response.result

    async def call_async(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        timeout_ms: int = 30000,
    ) -> Any:
        """异步调用 MCP 工具。

        Raises:
            MCPToolNotFoundError: 工具不存在
            MCPToolExecutionError: 调用失败
            ValueError: tool_name 为空
        """
        if not tool_name:
            raise ValueError("tool_name must be non-empty")
        with self._lock:
            server_id = self._tool_to_server.get(tool_name)
            if server_id is None:
                raise MCPToolNotFoundError(f"MCP tool '{tool_name}' not found")
            client = self._servers[server_id]
        original_name = tool_name
        if tool_name.startswith(f"{server_id}."):
            original_name = tool_name[len(server_id) + 1 :]
        request = MCPRequest(
            tool_name=original_name,
            arguments=arguments,
            timeout_ms=timeout_ms,
            server_id=server_id,
        )
        response = await client.call_tool(request)
        if not response.success:
            raise MCPToolExecutionError(f"MCP tool '{tool_name}' failed: {response.error}")
        return response.result

    # ------------------------------------------------------------------
    # 注册到本地 ToolRegistry
    # ------------------------------------------------------------------

    def register_to_tool_registry(self, tool_registry: Any) -> list[str]:
        """把全部 MCP 工具注册到本地 ToolRegistry。

        Args:
            tool_registry: 本地 ToolRegistry 实例(需实现 register(metadata, func))

        Returns:
            已注册的工具名列表
        """
        registered: list[str] = []
        with self._lock:
            tools = list(self._tools.values())
        for tool in tools:
            try:
                metadata = self.to_tool_metadata(tool)
                executor = self.make_executor(tool.name)
                tool_registry.register(metadata, executor)
                registered.append(tool.name)
            except Exception:
                continue  # 单个工具注册失败不影响其他
        return registered

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """注册表统计。"""
        with self._lock:
            servers = list(self._servers.values())
            by_status: dict[str, int] = {}
            for s in servers:
                status = s.server_info.status.value
                by_status[status] = by_status.get(status, 0) + 1
            return {
                "servers": len(servers),
                "tools": len(self._tools),
                "by_status": by_status,
                "connected": sum(1 for s in servers if s.is_connected),
            }
