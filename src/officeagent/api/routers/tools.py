"""
API 路由 - 工具管理接口。

接入真实 ToolRegistry,替换之前的 Mock 实现。
"""
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from officeagent.api.schemas.models import (
    BaseResponse,
    ToolExecutionRequest,
    ToolExecutionResponse,
    ToolRegister,
    ToolResponse,
)
from officeagent.core.tools.protocol import ToolMetadata, validate_arguments
from officeagent.core.types import ToolCall, ToolPermission

router = APIRouter(prefix="/tools", tags=["tools"])


def _get_registry(request: Request):
    """从应用状态获取 ToolRegistry。"""
    scheduler = request.app.state.scheduler
    return scheduler._ctx.tool_registry


def _get_executor(request: Request):
    """从应用状态获取 ToolExecutor。"""
    scheduler = request.app.state.scheduler
    return scheduler._ctx.tool_executor


@router.post("/register", response_model=ToolResponse)
async def register_tool(request: ToolRegister, http_request: Request):
    """注册新工具。"""
    registry = _get_registry(http_request)

    metadata = ToolMetadata(
        name=request.name,
        description=request.description,
        category=request.category,
        input_schema=request.input_schema,
        output_schema=request.output_schema or {},
        permission_level=ToolPermission.LOW,
        timeout_ms=request.timeout_ms,
        rate_limit=request.rate_limit,
    )

    # 默认空函数(实际需通过代码注册)
    def placeholder(args: dict) -> dict:
        return {"error": "工具函数尚未实现"}

    registry.register(metadata, placeholder)

    return ToolResponse(
        id=0,
        name=request.name,
        description=request.description,
        category=request.category,
        enabled=True,
        version="1.0.0",
    )


@router.get("/list")
async def list_tools(
    category: Optional[str] = None,
    http_request: Request = None,
):
    """查询工具列表。"""
    registry = _get_registry(http_request)
    tools = registry.list_tools(category=category)

    return [
        ToolResponse(
            id=0,
            name=t.name,
            description=t.description,
            category=t.category,
            enabled=t.enabled,
            version=t.version,
        )
        for t in tools
    ]


@router.get("/{tool_name}")
async def get_tool(tool_name: str, http_request: Request):
    """获取工具详情。"""
    registry = _get_registry(http_request)

    if not registry.has(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    tool = registry.get(tool_name)
    meta = tool.metadata
    return ToolResponse(
        id=0,
        name=meta.name,
        description=meta.description,
        category=meta.category,
        enabled=meta.enabled,
        version=meta.version,
    )


@router.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(request: ToolExecutionRequest, http_request: Request):
    """执行工具(调试接口)。"""
    registry = _get_registry(http_request)
    executor = _get_executor(http_request)

    if not registry.has(request.tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{request.tool_name}' not found")

    # 入参校验
    tool = registry.get(request.tool_name)
    valid, errors = validate_arguments(tool.metadata, request.arguments)
    if not valid:
        raise HTTPException(status_code=400, detail=f"参数校验失败: {errors}")

    # 执行
    t0 = time.monotonic()
    call = ToolCall(name=request.tool_name, arguments=request.arguments)

    try:
        result = executor.execute(call)
        ms = (time.monotonic() - t0) * 1000

        return ToolExecutionResponse(
            execution_id=0,
            tool_name=request.tool_name,
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            result=result.data if result.data else {"output": str(result.output)},
            duration_ms=round(ms, 2),
            error=result.error,
        )
    except Exception as e:
        ms = (time.monotonic() - t0) * 1000
        return ToolExecutionResponse(
            execution_id=0,
            tool_name=request.tool_name,
            status="failed",
            result=None,
            duration_ms=round(ms, 2),
            error=str(e),
        )


@router.put("/{tool_name}/enable")
async def enable_tool(tool_name: str, http_request: Request):
    """启用工具。"""
    registry = _get_registry(http_request)
    if not registry.has(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    tool = registry.get(tool_name)
    tool.metadata.enabled = True
    return BaseResponse(success=True, message=f"Tool {tool_name} enabled")


@router.put("/{tool_name}/disable")
async def disable_tool(tool_name: str, http_request: Request):
    """禁用工具。"""
    registry = _get_registry(http_request)
    if not registry.has(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    tool = registry.get(tool_name)
    tool.metadata.enabled = False
    return BaseResponse(success=True, message=f"Tool {tool_name} disabled")


@router.get("/{tool_name}/schema")
async def get_tool_schema(tool_name: str, http_request: Request):
    """获取工具的 JSON Schema。"""
    registry = _get_registry(http_request)
    if not registry.has(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    tool = registry.get(tool_name)
    meta = tool.metadata
    return {
        "name": meta.name,
        "description": meta.description,
        "input_schema": meta.input_schema,
        "output_schema": meta.output_schema,
        "permission_level": meta.permission_level.value if hasattr(meta.permission_level, "value") else str(meta.permission_level),
        "timeout_ms": meta.timeout_ms,
        "rate_limit": meta.rate_limit,
    }


@router.get("/{tool_name}/stats")
async def get_tool_stats(tool_name: str, http_request: Request):
    """获取工具执行统计。"""
    registry = _get_registry(http_request)
    if not registry.has(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    # 返回基本统计(完整统计需要从 DB 查询)
    return {
        "tool_name": tool_name,
        "registered": True,
        "category": registry.get(tool_name).metadata.category,
    }
