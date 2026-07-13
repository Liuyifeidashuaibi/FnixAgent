"""MCP 服务器(P2-3)。

把本地工具暴露为 MCP server,供外部 MCP client(如 Claude Desktop / 其他 agent)消费。
职责:
  - list_exposed_tools:列出已暴露的工具
  - is_exposed:检查工具是否在白名单
  - add_to_whitelist / remove_from_whitelist:管理白名单
  - handle_call:处理 MCP tools/call 请求(调度到本地 ToolExecutor)
  - server_info:返回 server 元信息(initialize 响应)
  - serve_stdio / serve_sse:启动 server(两种传输模式)

设计:
  - 白名单模式:默认不暴露任何工具,需显式 add_to_whitelist
  - 兼容 Anthropic MCP 协议(2024-11-05)
  - STDIO server:stdin 读 JSON-RPC,stdout 写 JSON-RPC
  - SSE server:HTTP POST 接收请求,SSE event 返回响应
  - 复用现有 ToolExecutor 执行工具(不绕过权限/审计/重试)
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import uuid
from typing import Any, Callable, Optional

from fnixagent.core.mcp.types import (
    JSONRPCRequest,
    JSONRPCResponse,
    MCPServerInfo,
    MCPServerStatus,
    MCPToolDef,
    MCPTransport,
)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class MCPServerError(Exception):
    """MCP 服务器基础异常。"""


class MCPServerAlreadyRunningError(MCPServerError):
    """server 已在运行。"""


class MCPToolNotExposedError(MCPServerError):
    """工具未在白名单(不可暴露)。"""


# ---------------------------------------------------------------------------
# MCPServer
# ---------------------------------------------------------------------------


class MCPServer:
    """MCP 服务器:把本地工具暴露给外部 MCP client。

    用法:
        server = MCPServer(
            server_id="my-fnix-agent",
            tool_registry=my_registry,
            tool_executor=my_executor,
        )
        server.add_to_whitelist("search_paper")
        server.add_to_whitelist("create_word")

        # STDIO 模式(供 Claude Desktop 等调用)
        server.serve_stdio()

        # 或 SSE 模式(供远程调用)
        # server.serve_sse(host="0.0.0.0", port=8080)
    """

    def __init__(
        self,
        server_id: str,
        tool_registry: Any,
        tool_executor: Any,
        name: str = "fnixagent-mcp-server",
        version: str = "1.0.0",
        description: str = "",
        default_expose_all: bool = False,
        auth_token: Optional[str] = None,
    ) -> None:
        """
        Args:
            server_id: server 标识
            tool_registry: 本地 ToolRegistry(需实现 list_tools/get_tool)
            tool_executor: 本地 ToolExecutor(需实现 execute(call)->ToolResult)
            name: server 自报名(initialize 返回)
            version: server 版本
            default_expose_all: 是否默认暴露全部工具(默认 False,白名单模式)
            auth_token: SSE 模式下的身份认证 Token(客户端须提供 Bearer Token)
        """
        self._server_id = server_id
        self._registry = tool_registry
        self._executor = tool_executor
        self._name = name
        self._version = version
        self._description = description
        self._auth_token = auth_token  # SSE 身份认证 Token
        self._whitelist: set[str] = set()
        self._lock = threading.RLock()
        self._running = False
        self._server_info = MCPServerInfo(
            server_id=server_id,
            name=name,
            version=version,
            transport=MCPTransport.STDIO,
            description=description,
            status=MCPServerStatus.DISCONNECTED,
        )
        if default_expose_all:
            self._expose_all_default()

    # ------------------------------------------------------------------
    # 白名单管理
    # ------------------------------------------------------------------

    def add_to_whitelist(self, tool_name: str) -> "MCPServer":
        """添加工具到白名单(允许暴露)。

        Args:
            tool_name: 工具名(非空)

        Raises:
            ValueError: tool_name 为空
        """
        if not tool_name:
            raise ValueError("tool_name must be non-empty")
        with self._lock:
            self._whitelist.add(tool_name)
        return self

    def remove_from_whitelist(self, tool_name: str) -> "MCPServer":
        """从白名单移除工具(不再暴露)。"""
        if not tool_name:
            return self  # 幂等:空名直接返回
        with self._lock:
            self._whitelist.discard(tool_name)
        return self

    def is_exposed(self, tool_name: str) -> bool:
        """检查工具是否在白名单。"""
        with self._lock:
            return tool_name in self._whitelist

    def list_exposed_tools(self) -> list[MCPToolDef]:
        """列出已暴露的全部工具(MCPToolDef 格式)。"""
        with self._lock:
            exposed: list[MCPToolDef] = []
            for name in sorted(self._whitelist):
                tool = self._get_local_tool(name)
                if tool is None:
                    continue
                exposed.append(self._local_to_mcp_tool(tool))
            return exposed

    def _expose_all_default(self) -> None:
        """把全部本地工具加入白名单(default_expose_all=True 时调用)。"""
        try:
            for tool in self._registry.list_tools():
                self._whitelist.add(tool.metadata.name)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 处理 MCP 请求
    # ------------------------------------------------------------------

    def handle_call(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """处理 JSON-RPC 请求,返回响应。

        支持的方法:
          - initialize:握手
          - ping:心跳
          - tools/list:列出工具
          - tools/call:调用工具
          - notifications/initialized:通知(无响应)
        """
        method = request.method
        try:
            if method == "initialize":
                return self._handle_initialize(request)
            elif method == "ping":
                return JSONRPCResponse(id=request.id, result={})
            elif method == "tools/list":
                return self._handle_list_tools(request)
            elif method == "tools/call":
                return self._handle_call_tool(request)
            elif method.startswith("notifications/"):
                # 通知类无响应(返回特殊标记,由传输层过滤)
                return JSONRPCResponse(
                    id=request.id, result=None, error={"code": -32000, "message": "notification (no response)"}
                )
            else:
                return JSONRPCResponse(
                    id=request.id,
                    error={
                        "code": -32601,
                        "message": f"Method '{method}' not found",
                    },
                )
        except Exception as e:
            return JSONRPCResponse(
                id=request.id,
                error={
                    "code": -32603,
                    "message": f"Internal error: {e}",
                },
            )

    def server_info(self) -> MCPServerInfo:
        """返回 server 元信息。"""
        return self._server_info

    # ------------------------------------------------------------------
    # STDIO 传输
    # ------------------------------------------------------------------

    def serve_stdio(self) -> None:
        """以 STDIO 模式启动 server(阻塞,主循环)。

        从 stdin 读取 JSON-RPC 请求,处理后写回 stdout。
        每行一条消息(以 \\n 分隔)。
        """
        if self._running:
            raise MCPServerAlreadyRunningError("MCP server already running")
        self._running = True
        self._server_info.status = MCPServerStatus.CONNECTED
        self._server_info.last_connected_at = time.time()
        try:
            while self._running:
                line = sys.stdin.readline()
                if not line:
                    break  # EOF
                line = line.strip()
                if not line:
                    continue
                try:
                    request = JSONRPCRequest.model_validate_json(line)
                except Exception as e:
                    # 解析失败,返回错误
                    error_resp = JSONRPCResponse(
                        id="",
                        error={
                            "code": -32700,
                            "message": f"Parse error: {e}",
                        },
                    )
                    sys.stdout.write(error_resp.model_dump_json() + "\n")
                    sys.stdout.flush()
                    continue
                response = self.handle_call(request)
                # 通知类请求无响应(error.code=-32000 标记)
                if (
                    response.error
                    and response.error.get("code") == -32000
                    and "notification" in response.error.get("message", "")
                ):
                    continue
                sys.stdout.write(response.model_dump_json() + "\n")
                sys.stdout.flush()
        finally:
            self._running = False
            self._server_info.status = MCPServerStatus.DISCONNECTED

    def stop(self) -> None:
        """停止 server(仅 STDIO 模式有效,设置 _running=False 让主循环退出)。"""
        self._running = False

    # ------------------------------------------------------------------
    # SSE 传输(简化版,基于 http.server)
    # ------------------------------------------------------------------

    def serve_sse(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """以 SSE 模式启动 server(阻塞)。

        简化实现:用 http.server.HTTPServer,POST /mcp 接收 JSON-RPC,SSE 返回响应。
        生产环境建议换 uvicorn + FastAPI。
        """
        if self._running:
            raise MCPServerAlreadyRunningError("MCP server already running")
        from http.server import BaseHTTPRequestHandler, HTTPServer

        outer = self

        class _SSEHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                # 身份认证校验(若 server 配置了 auth_token)
                if outer._auth_token:
                    auth_header = self.headers.get("Authorization", "")
                    expected = f"Bearer {outer._auth_token}"
                    if auth_header != expected:
                        err = JSONRPCResponse(
                            id="",
                            error={
                                "code": -32001,
                                "message": "Unauthorized: invalid or missing token",
                            },
                        )
                        self.send_response(401)
                        self.send_header("Content-Type", "text/event-stream")
                        self.end_headers()
                        payload = f"data: {err.model_dump_json()}\n\n"
                        self.wfile.write(payload.encode("utf-8"))
                        return
                content_length = int(self.headers.get("Content-Length", 0))
                # 消息大小限制(防止恶意大包,上限 1MB)
                if content_length > 1_048_576:
                    err = JSONRPCResponse(
                        id="",
                        error={
                            "code": -32600,
                            "message": "Request too large (max 1MB)",
                        },
                    )
                    self._respond_sse(err)
                    return
                body = self.rfile.read(content_length).decode("utf-8")
                try:
                    request = JSONRPCRequest.model_validate_json(body)
                except Exception as e:
                    error_resp = JSONRPCResponse(
                        id="",
                        error={"code": -32700, "message": f"Parse error: {e}"},
                    )
                    self._respond_sse(error_resp)
                    return
                response = outer.handle_call(request)
                self._respond_sse(response)

            def _respond_sse(self, response: JSONRPCResponse) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                payload = f"data: {response.model_dump_json()}\n\n"
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()

            def log_message(self, format, *args):
                pass  # 静默日志

        self._running = True
        self._server_info.status = MCPServerStatus.CONNECTED
        self._server_info.transport = MCPTransport.SSE
        self._server_info.url = f"http://{host}:{port}/mcp"
        self._server_info.last_connected_at = time.time()
        httpd = HTTPServer((host, port), _SSEHandler)
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()
            self._running = False
            self._server_info.status = MCPServerStatus.DISCONNECTED

    # ------------------------------------------------------------------
    # 内部:方法处理
    # ------------------------------------------------------------------

    def _handle_initialize(self, request: JSONRPCRequest) -> JSONRPCResponse:
        params = request.params or {}
        client_info = params.get("clientInfo", {})
        self._server_info.capabilities = params.get("capabilities", {})
        return JSONRPCResponse(
            id=request.id,
            result={
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                },
                "serverInfo": {
                    "name": self._name,
                    "version": self._version,
                },
            },
        )

    def _handle_list_tools(self, request: JSONRPCRequest) -> JSONRPCResponse:
        tools = self.list_exposed_tools()
        return JSONRPCResponse(
            id=request.id,
            result={
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.input_schema,
                        "outputSchema": t.output_schema or None,
                        "annotations": t.annotations,
                    }
                    for t in tools
                ]
            },
        )

    def _handle_call_tool(self, request: JSONRPCRequest) -> JSONRPCResponse:
        params = request.params or {}
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        # 参数消毒:拒绝空工具名与非 dict 参数
        if not tool_name or not isinstance(tool_name, str):
            return JSONRPCResponse(
                id=request.id,
                result={
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "Missing or invalid 'name' field"}
                    ],
                },
            )
        if not isinstance(arguments, dict):
            return JSONRPCResponse(
                id=request.id,
                result={
                    "isError": True,
                    "content": [
                        {"type": "text", "text": "'arguments' must be an object"}
                    ],
                },
            )
        # 参数消毒:递归清理参数中的危险字符串(防止 path traversal / 命令注入)
        sanitized_args = self._sanitize_arguments(arguments)
        if not self.is_exposed(tool_name):
            return JSONRPCResponse(
                id=request.id,
                result={
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool '{tool_name}' not exposed",
                        }
                    ],
                },
            )
        try:
            result = self._invoke_local_tool(tool_name, sanitized_args)
            return JSONRPCResponse(
                id=request.id,
                result={
                    "isError": False,
                    "content": [
                        {
                            "type": "text",
                            "text": self._stringify_result(result),
                        }
                    ],
                },
            )
        except Exception as e:
            return JSONRPCResponse(
                id=request.id,
                result={
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Tool execution failed: {e}",
                        }
                    ],
                },
            )

    def _invoke_local_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """通过本地 ToolExecutor 调用工具。"""
        from fnixagent.core.types import ToolCall

        call = ToolCall(
            name=tool_name,
            arguments=arguments,
        )
        result = self._executor.execute(call)
        if result.error:
            raise RuntimeError(result.error)
        return result.output

    @staticmethod
    def _sanitize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        """递归消毒工具参数(防止路径遍历 / 命令注入)。

        规则:
          - 字符串值:拒绝包含 ".." 路径遍历、null 字节、shell 元字符序列
          - 递归处理嵌套 dict / list
          - 其他类型(int/float/bool/None)原样保留

        Args:
            arguments: 原始参数 dict

        Returns:
            消毒后的参数 dict(若含危险内容,对应值替换为空字符串)
        """
        # 危险模式:路径遍历、null 字节、shell 注入尝试
        dangerous_patterns = ("..", "\x00", ";rm ", "&&rm", "|rm", "$(", "`")

        def _sanitize_value(val: Any) -> Any:
            if isinstance(val, str):
                lower = val.lower()
                for pat in dangerous_patterns:
                    if pat.lower() in lower:
                        return ""  # 替换为空字符串
                return val
            elif isinstance(val, dict):
                return {k: _sanitize_value(v) for k, v in val.items()}
            elif isinstance(val, list):
                return [_sanitize_value(v) for v in val]
            return val

        return {k: _sanitize_value(v) for k, v in arguments.items()}

    def _stringify_result(self, result: Any) -> str:
        """把工具结果转换为字符串(MCP text content)。"""
        if isinstance(result, str):
            return result
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)

    # ------------------------------------------------------------------
    # 内部:工具元数据转换
    # ------------------------------------------------------------------

    def _get_local_tool(self, name: str) -> Any:
        """从本地 registry 查找工具(返回 RegisteredTool 或 None)。"""
        try:
            return self._registry.get_tool(name)
        except Exception:
            return None

    def _local_to_mcp_tool(self, registered: Any) -> MCPToolDef:
        """把本地 RegisteredTool 转换为 MCPToolDef。"""
        metadata = registered.metadata if hasattr(registered, "metadata") else registered
        return MCPToolDef(
            name=metadata.name,
            description=metadata.description,
            input_schema=metadata.input_schema,
            output_schema=getattr(metadata, "output_schema", {}),
            server_id=self._server_id,
            annotations={
                "readOnlyHint": getattr(metadata, "skill_level", "") == "basic",
                "destructiveHint": getattr(metadata, "skill_level", "") == "meta",
            },
        )
