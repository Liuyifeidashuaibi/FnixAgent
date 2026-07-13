"""MCP 客户端(P2-3)。

负责与外部 MCP 服务器通信:
  - STDIO 传输:启动子进程,通过 stdin/stdout 收发 JSON-RPC
  - SSE 传输:HTTP POST 发送请求,SSE 接收响应
  - 握手(initialize)→ 列工具(tools/list)→ 调用工具(tools/call)

设计:
  - 异步优先:所有 IO 方法为 async,同步版用 asyncio.run 包装
  - 无第三方依赖:STDIO 用 asyncio.subprocess;SSE 用 urllib(避免引入 httpx)
  - 协议兼容 Anthropic MCP(2024-11-05 版本)
  - 单 server 单 client;多 server 由 MCPToolRegistry 管理多个 client

不依赖官方 mcp SDK,避免安装负担;若需更完整能力,可子类化扩展。
"""
from __future__ import annotations

import asyncio
import itertools
import json
import os
import threading
import time
import uuid
from typing import Any, Optional
from urllib.parse import urlparse

from fnixagent.core.mcp.types import (
    MCPErrorCode,
    MCPRequest,
    MCPResponse,
    MCPServerInfo,
    MCPServerStatus,
    MCPToolDef,
    MCPTransport,
    JSONRPCRequest,
    JSONRPCResponse,
)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class MCPClientError(Exception):
    """MCP 客户端基础异常。"""


class MCPConnectionError(MCPClientError):
    """连接失败/已断开。"""


class MCPTimeoutError(MCPClientError):
    """调用超时。"""


class MCPToolExecutionError(MCPClientError):
    """工具执行失败(server 返回 error)。"""


# ---------------------------------------------------------------------------
# 传输层抽象
# ---------------------------------------------------------------------------


class _BaseTransport:
    """传输层基类:发送 JSON-RPC 请求,接收 JSON-RPC 响应。"""

    async def send(self, request: JSONRPCRequest) -> None:
        raise NotImplementedError

    async def recv(self) -> Optional[dict[str, Any]]:
        """接收下一条消息;无消息返回 None,连接关闭抛 ConnectionError。"""
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


class _StdioTransport(_BaseTransport):
    """STDIO 传输:子进程的 stdin/stdout,每行一条 JSON-RPC 消息。"""

    def __init__(self, command: str, args: list[str], env: Optional[dict] = None) -> None:
        self._command = command
        self._args = list(args)
        self._env = env
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            self._proc = await asyncio.create_subprocess_exec(
                self._command,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, **(self._env or {})},
            )
        except FileNotFoundError as e:
            raise MCPConnectionError(
                f"Failed to start MCP server command '{self._command}': {e}"
            ) from e
        except PermissionError as e:
            raise MCPConnectionError(
                f"Permission denied to run MCP command '{self._command}': {e}"
            ) from e
        except OSError as e:
            # 兜底网络/系统级错误(如命令不存在于 PATH)
            raise MCPConnectionError(
                f"OS error starting MCP server '{self._command}': {e}"
            ) from e

    async def send(self, request: JSONRPCRequest) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPConnectionError("STDIO transport not started")
        line = request.model_dump_json() + "\n"
        self._proc.stdin.write(line.encode("utf-8"))
        await self._proc.stdin.drain()

    async def recv(self) -> Optional[dict[str, Any]]:
        if self._proc is None or self._proc.stdout is None:
            raise MCPConnectionError("STDIO transport not started")
        line = await self._proc.stdout.readline()
        if not line:
            return None  # EOF
        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise MCPConnectionError(f"Invalid JSON from MCP server: {e}") from e

    async def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        except Exception:
            pass
        finally:
            self._proc = None


class _SSETransport(_BaseTransport):
    """SSE 传输:HTTP POST 发送请求,通过 SSE 长连接接收响应。

    简化实现:每次请求-响应独立 HTTP 连接(server 在响应中通过 SSE event 返回)。
    生产环境可换成长连接复用。

    身份认证:若 server_info.auth_token 提供,自动注入 `Authorization: Bearer <token>`
    到请求头,实现 MCP server 身份验证。
    连接池:用 urllib.request 的全局 opener 复用 TCP 连接(HTTP/1.1 keep-alive)。
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict] = None,
        auth_token: Optional[str] = None,
    ) -> None:
        # URL 合法性校验(防止 SSRF / 非 HTTP scheme)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise MCPConnectionError(
                f"SSE transport requires http(s) URL, got '{parsed.scheme}://'"
            )
        if not parsed.netloc:
            raise MCPConnectionError(f"Invalid SSE URL (no host): {url}")
        self._url = url
        self._headers = headers or {}
        # 注入 Bearer Token 认证头
        if auth_token:
            self._headers["Authorization"] = f"Bearer {auth_token}"
        # 用 urllib(避免引入 httpx/aiohttp 依赖)
        import urllib.request
        self._urllib = urllib.request
        # 连接池:复用 opener 以利用 HTTP/1.1 keep-alive
        self._opener = urllib.request.build_opener()

    async def send(self, request: JSONRPCRequest) -> None:
        """SSE 模式下 send 与 recv 合并:send 时同步等待响应,缓存到 _pending。"""
        # 实际发送在 recv 中完成(因为 SSE 是单次请求-响应)
        self._pending_request = request

    async def recv(self) -> Optional[dict[str, Any]]:
        req = getattr(self, "_pending_request", None)
        if req is None:
            return None
        del self._pending_request
        # 同步 HTTP 调用放到线程池
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._http_call, req)

    def _http_call(self, request: JSONRPCRequest) -> dict[str, Any]:
        body = request.model_dump_json().encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **self._headers,
        }
        req = self._urllib.Request(self._url, data=body, headers=headers, method="POST")
        # 网络调用 try-except:区分超时/HTTP 错误/解析错误
        try:
            with self._opener.open(req, timeout=30) as resp:
                # 解析 SSE 格式:data: {...}\n\n
                content = resp.read().decode("utf-8")
        except TimeoutError as e:
            raise MCPTimeoutError(f"SSE call timed out: {e}") from e
        except ConnectionError as e:
            raise MCPConnectionError(f"SSE connection failed: {e}") from e
        except Exception as e:
            # 兜底:HTTPError / URLError 等
            raise MCPConnectionError(f"SSE call failed: {e}") from e
        # 响应解析(独立 try-except,与网络错误区分)
        try:
            for line in content.splitlines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload:
                        return json.loads(payload)
            # 非标准 SSE:直接返回 JSON
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise MCPConnectionError(
                f"Invalid JSON in SSE response: {e}"
            ) from e

    async def close(self) -> None:
        pass  # 无状态连接


# ---------------------------------------------------------------------------
# MCPClient
# ---------------------------------------------------------------------------


class MCPClient:
    """MCP 客户端:与单个 MCP server 通信。

    生命周期:
        connect() ──→ 握手(initialize)→ tools/list 缓存
        call_tool() × N
        disconnect()

    异步优先,提供同步包装:
        client.connect_sync() / client.call_tool_sync() / client.disconnect_sync()
    """

    def __init__(self, server_info: MCPServerInfo) -> None:
        self._info = server_info
        self._transport: Optional[_BaseTransport] = None
        self._tools_cache: list[MCPToolDef] = []
        self._connected = False
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._pending: dict[str, asyncio.Future] = {}
        # JSON-RPC id 计数器(线程安全,防止并发请求 id 冲突)
        # 格式:"{uuid前8位}-{自增序号}",确保全局唯一
        self._id_prefix = uuid.uuid4().hex[:8]
        self._id_counter = itertools.count(1)
        self._id_lock = threading.Lock()

    def _next_request_id(self) -> str:
        """生成线程安全的唯一 JSON-RPC 请求 id。

        Returns:
            形如 "a1b2c3d4-1" / "a1b2c3d4-2" 的唯一 id
        """
        with self._id_lock:
            seq = next(self._id_counter)
        return f"{self._id_prefix}-{seq}"

    @property
    def server_info(self) -> MCPServerInfo:
        return self._info

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def tools(self) -> list[MCPToolDef]:
        return list(self._tools_cache)

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    async def connect(self) -> MCPServerInfo:
        """连接 server 并完成握手。

        步骤:
          1. 启动传输层(STDIO 启动子进程 / SSE 准备 HTTP)
          2. 发送 initialize 请求,接收 server info
          3. 发送 initialized 通知
          4. 调 list_tools 缓存工具列表
        """
        if self._connected:
            return self._info
        self._info.status = MCPServerStatus.CONNECTING
        try:
            self._transport = self._make_transport()
            if isinstance(self._transport, _StdioTransport):
                await self._transport.start()
            # 握手
            await self._initialize()
            # 列工具
            await self.list_tools()
            self._connected = True
            self._info.status = MCPServerStatus.CONNECTED
            self._info.last_connected_at = time.time()
            return self._info
        except Exception as e:
            self._info.status = MCPServerStatus.ERROR
            self._info.last_error = str(e)
            await self._safe_close()
            raise MCPConnectionError(
                f"Failed to connect MCP server '{self._info.name}': {e}"
            ) from e

    async def disconnect(self) -> None:
        """断开连接(发送 shutdown 通知 + 关闭传输层)。"""
        if not self._connected:
            return
        try:
            # 发送 initialized 关闭通知(可选)
            try:
                notif = JSONRPCRequest(
                    id=self._next_request_id(),
                    method="notifications/cancelled",
                )
                await self._transport.send(notif)
            except Exception:
                pass
        finally:
            await self._safe_close()
            self._connected = False
            self._info.status = MCPServerStatus.DISCONNECTED

    async def ping(self, timeout_ms: int = 5000) -> bool:
        """心跳(ping 方法)。"""
        if not self._connected:
            return False
        try:
            response = await self._call_method(
                "ping", {}, timeout_ms=timeout_ms
            )
            return response is not None
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 工具管理
    # ------------------------------------------------------------------

    async def list_tools(self) -> list[MCPToolDef]:
        """获取 server 暴露的全部工具并缓存。"""
        if not self._connected and self._transport is None:
            # connect 流程中调用,允许继续
            pass
        response = await self._call_method("tools/list", {})
        tools_data = (response or {}).get("tools", [])
        self._tools_cache = [
            MCPToolDef(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
                output_schema=t.get("outputSchema", {}),
                server_id=self._info.server_id,
                annotations=t.get("annotations", {}),
            )
            for t in tools_data
        ]
        return list(self._tools_cache)

    async def get_tool(self, tool_name: str) -> Optional[MCPToolDef]:
        """获取单个工具定义(从缓存查找)。"""
        for t in self._tools_cache:
            if t.name == tool_name:
                return t
        # 缓存未命中,刷新一次
        await self.list_tools()
        for t in self._tools_cache:
            if t.name == tool_name:
                return t
        return None

    async def call_tool(self, request: MCPRequest) -> MCPResponse:
        """调用工具(tools/call)。"""
        if not self._connected:
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error="MCP server not connected",
                error_code=MCPErrorCode.SERVER_NOT_CONNECTED,
                server_id=self._info.server_id,
                tool_name=request.tool_name,
            )
        t0 = time.monotonic()
        try:
            response = await self._call_method(
                "tools/call",
                {
                    "name": request.tool_name,
                    "arguments": request.arguments,
                },
                timeout_ms=request.timeout_ms,
            )
            latency_ms = (time.monotonic() - t0) * 1000
            # MCP 响应格式:{isError, content: [{type, text}]}
            if isinstance(response, dict) and response.get("isError"):
                error_text = self._extract_error_text(response)
                return MCPResponse(
                    request_id=request.request_id,
                    success=False,
                    error=error_text or "Tool execution failed",
                    error_code=MCPErrorCode.TOOL_EXECUTION_FAILED,
                    latency_ms=latency_ms,
                    server_id=self._info.server_id,
                    tool_name=request.tool_name,
                )
            result = self._extract_result(response)
            return MCPResponse(
                request_id=request.request_id,
                success=True,
                result=result,
                latency_ms=latency_ms,
                server_id=self._info.server_id,
                tool_name=request.tool_name,
            )
        except MCPTimeoutError as e:
            latency_ms = (time.monotonic() - t0) * 1000
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=str(e),
                error_code=MCPErrorCode.TIMEOUT,
                latency_ms=latency_ms,
                server_id=self._info.server_id,
                tool_name=request.tool_name,
            )
        except Exception as e:
            latency_ms = (time.monotonic() - t0) * 1000
            return MCPResponse(
                request_id=request.request_id,
                success=False,
                error=str(e),
                error_code=MCPErrorCode.TOOL_EXECUTION_FAILED,
                latency_ms=latency_ms,
                server_id=self._info.server_id,
                tool_name=request.tool_name,
            )

    async def call_tool_async(self, request: MCPRequest) -> MCPResponse:
        """异步调用工具(语义同 call_tool,显式 async 入口)。"""
        return await self.call_tool(request)

    # ------------------------------------------------------------------
    # 同步包装
    # ------------------------------------------------------------------

    def connect_sync(self) -> MCPServerInfo:
        return self._run_async(self.connect())

    def disconnect_sync(self) -> None:
        self._run_async(self.disconnect())

    def list_tools_sync(self) -> list[MCPToolDef]:
        return self._run_async(self.list_tools())

    def call_tool_sync(self, request: MCPRequest) -> MCPResponse:
        return self._run_async(self.call_tool(request))

    def ping_sync(self, timeout_ms: int = 5000) -> bool:
        return self._run_async(self.ping(timeout_ms))

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _make_transport(self) -> _BaseTransport:
        if self._info.transport == MCPTransport.STDIO:
            if not self._info.command:
                raise MCPConnectionError(
                    "STDIO transport requires 'command' in server_info"
                )
            return _StdioTransport(
                command=self._info.command,
                args=self._info.args,
                env=self._info.env,
            )
        elif self._info.transport == MCPTransport.SSE:
            # URL 校验(防止非法 URL 导致 SSRF 或解析错误)
            self._info.validate_url()
            return _SSETransport(
                url=self._info.url,
                headers=self._info.headers,
                auth_token=self._info.auth_token,
            )
        else:
            raise MCPConnectionError(
                f"Unsupported transport: {self._info.transport}"
            )

    async def _initialize(self) -> None:
        """MCP 握手(initialize 请求)。"""
        response = await self._call_method(
            "initialize",
            {
                "protocolVersion": self._info.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "fnixagent-mcp-client",
                    "version": "1.0.0",
                },
            },
            timeout_ms=10000,
        )
        if response:
            server_info = response.get("serverInfo", {})
            self._info.name = server_info.get("name", self._info.name)
            self._info.version = server_info.get("version", self._info.version)
            self._info.protocol_version = response.get(
                "protocolVersion", self._info.protocol_version
            )
            self._info.capabilities = response.get("capabilities", {})
        # 发送 initialized 通知(server 期望收到后才认为握手完成)
        notif = JSONRPCRequest(
            id=self._next_request_id(),
            method="notifications/initialized",
        )
        try:
            await self._transport.send(notif)
        except Exception:
            pass  # 通知失败不阻断

    async def _call_method(
        self,
        method: str,
        params: dict[str, Any],
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """发送 JSON-RPC 请求并等待响应。

        JSON-RPC 协议要点:
          - 每个请求带唯一 id(server 在响应中回填)
          - 响应通过 id 与请求匹配(本实现为同步 send-recv,id 匹配由调用顺序保证)
          - error 字段非空表示调用失败,按 code 分类抛异常
        """
        if self._transport is None:
            raise MCPConnectionError("Transport not initialized")
        request = JSONRPCRequest(
            id=self._next_request_id(),
            method=method,
            params=params,
        )
        await self._transport.send(request)
        try:
            response_data = await asyncio.wait_for(
                self._transport.recv(),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError as e:
            raise MCPTimeoutError(
                f"MCP call '{method}' timed out after {timeout_ms}ms"
            ) from e
        if response_data is None:
            raise MCPConnectionError("MCP server closed connection")
        # JSON-RPC 响应
        response = JSONRPCResponse(**response_data)
        if response.error:
            code = response.error.get("code", MCPErrorCode.INTERNAL_ERROR)
            message = response.error.get("message", "Unknown error")
            if code == MCPErrorCode.METHOD_NOT_FOUND:
                raise MCPClientError(f"Method '{method}' not found: {message}")
            raise MCPToolExecutionError(
                f"MCP error [{code}]: {message}"
            )
        return response.result or {}

    def _extract_result(self, response: Any) -> Any:
        """从 MCP 响应提取结果数据。"""
        if not isinstance(response, dict):
            return response
        content = response.get("content", [])
        if not content:
            return response
        # content 是 [{type: "text", text: "..."}] 格式
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
                else:
                    texts.append(str(item))
            if len(texts) == 1:
                return texts[0]
            return "\n".join(texts)
        return content

    def _extract_error_text(self, response: dict[str, Any]) -> str:
        content = response.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text", "")
        return str(response)

    async def _safe_close(self) -> None:
        if self._transport is not None:
            try:
                await self._transport.close()
            except Exception:
                pass
            self._transport = None

    def _run_async(self, coro):
        """同步运行异步方法(在独立事件循环中)。"""
        with self._sync_lock:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 已在事件循环中,创建新线程运行
                    result_holder: dict[str, Any] = {}
                    thread = threading.Thread(
                        target=self._run_in_thread,
                        args=(coro, result_holder),
                    )
                    thread.start()
                    thread.join()
                    if "error" in result_holder:
                        raise result_holder["error"]
                    return result_holder["result"]
                else:
                    return loop.run_until_complete(coro)
            except RuntimeError:
                # 没有事件循环
                return asyncio.run(coro)

    def _run_in_thread(self, coro, result_holder: dict) -> None:
        try:
            result = asyncio.run(coro)
            result_holder["result"] = result
        except Exception as e:
            result_holder["error"] = e
