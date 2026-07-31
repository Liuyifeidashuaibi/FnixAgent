"""
API 路由 - AgentOS Shell HTTP 接口。

将 AgentShell 的 31 个命令包装为 /api/v1/agentos/* HTTP 端点。
统一 POST + JSON body 传参 (GET 端点用于无副作用的查询)。

设计要点:
  - Shell 单例: 模块级 _shell, get_shell() 懒加载 (首次调用自动 boot)
  - 统一响应: AgentOSResponse{success, output, error, duration_ms}
  - 错误处理: 命令失败 → 200 + success=false (保持 shell 语义);
              未捕获异常 → 500
  - 鉴权: 复用 verify_jwt_token 依赖 (与 privacy.py / rbac.py 一致)
  - 参数分发: 直接调用 shell._commands[cmd](args), 绕过命令行解析,
              避免 fs.write / llm 等含特殊字符内容时的引号问题
  - router 前缀: /agentos (由主流程在 main.py 注册时挂到 /api/v1 下)
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from fnixagent.api.routers.auth import verify_jwt_token
from fnixagent.core.agent.shell import AgentShell, ShellResult, create_shell

router = APIRouter(prefix="/agentos", tags=["agentos"])


# ============================================================================
# 统一响应模型
# ============================================================================


class AgentOSResponse(BaseModel):
    """AgentOS 命令统一响应 (对齐 ShellResult)。"""

    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: int = 0


# ============================================================================
# 请求体模型
# ============================================================================


class SpawnRequest(BaseModel):
    name: str
    priority: str | None = None
    capabilities: list[str] | None = None
    parent_pid: str | None = None


class KillRequest(BaseModel):
    pid: str
    reason: str | None = None


class ExecRequest(BaseModel):
    syscall: str
    args: dict[str, Any] | None = None
    pid: str | None = None


class LlmRequest(BaseModel):
    prompt: str
    pid: str | None = None
    system: str | None = None


class FsReadRequest(BaseModel):
    path: str


class FsWriteRequest(BaseModel):
    path: str
    content: str


class FsListRequest(BaseModel):
    path: str | None = None


class FsMkdirRequest(BaseModel):
    path: str


class FsDeleteRequest(BaseModel):
    path: str


class MemRecallRequest(BaseModel):
    query: str
    layers: list[str] | None = None
    top_k: int | None = None


class MemStoreRequest(BaseModel):
    content: str
    layer: str | None = None


class MemSearchRequest(BaseModel):
    query: str
    layer: str | None = None
    top_k: int | None = None


class MemForgetRequest(BaseModel):
    memory_id: str


class ToolInvokeRequest(BaseModel):
    tool_name: str
    args: dict[str, Any] | None = None


class A2aDiscoverRequest(BaseModel):
    capability: str | None = None


class A2aSendRequest(BaseModel):
    target: str
    content: str
    type: str | None = None


class A2aBroadcastRequest(BaseModel):
    content: str


class SkillLoadRequest(BaseModel):
    dir: str


class SkillRunRequest(BaseModel):
    name: str
    args: dict[str, Any] | None = None


class PolicyAddRequest(BaseModel):
    action: str
    effect: str
    subject: str | None = None
    priority: int | None = None


class CheckpointRequest(BaseModel):
    pid: str


class NaturalRequest(BaseModel):
    text: str


# ============================================================================
# Shell 单例管理
# ============================================================================

_shell: AgentShell | None = None


async def _new_shell() -> AgentShell:
    """构造并启动一个新 Shell (内存后端)。

    使用 create_shell(boot=False) 避免其在 async 上下文中调用 asyncio.run,
    随后手动 await kernel.boot() 完成启动。
    """
    shell = create_shell(in_memory=True, boot=False)
    await shell.kernel.boot()
    return shell


async def get_shell() -> AgentShell:
    """获取单例 Shell (懒加载, 首次调用自动 boot)。"""
    global _shell
    if _shell is None:
        _shell = await _new_shell()
    return _shell


def _safe_output(out: Any) -> Any:
    """确保 output 可 JSON 序列化 (类比 ShellResult.format 的 default=str)。"""
    if out is None:
        return None
    try:
        return json.loads(json.dumps(out, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return str(out)


def _to_response(result: ShellResult, start: float) -> AgentOSResponse:
    """ShellResult → AgentOSResponse。"""
    dur = result.duration_ms if result.duration_ms else (time.monotonic() - start) * 1000
    return AgentOSResponse(
        success=result.success,
        output=_safe_output(result.output),
        error=result.error,
        duration_ms=int(dur),
    )


async def _dispatch(cmd: str, args: dict[str, Any]) -> AgentOSResponse:
    """直接调用 shell 命令处理器 (绕过命令行解析, 避免引号/换行问题)。"""
    shell = await get_shell()
    handler = shell._commands.get(cmd)
    if handler is None:
        return AgentOSResponse(success=False, error=f"未知命令: {cmd}", duration_ms=0)
    start = time.monotonic()
    try:
        result = await handler(args)
        return _to_response(result, start)
    except Exception as e:
        return AgentOSResponse(
            success=False,
            error=f"命令执行异常: {type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# ============================================================================
# 内核生命周期
# ============================================================================


@router.post("/boot", response_model=AgentOSResponse)
async def boot(_payload: dict = Depends(verify_jwt_token)):
    """启动内核。"""
    global _shell
    if _shell is None:
        _shell = await _new_shell()
    return AgentOSResponse(
        success=True,
        output={"booted": True, "shell_pid": _shell._shell_pid},
        duration_ms=0,
    )


@router.post("/shutdown", response_model=AgentOSResponse)
async def shutdown(_payload: dict = Depends(verify_jwt_token)):
    """关闭内核。"""
    global _shell
    if _shell is None:
        return AgentOSResponse(success=False, error="内核未启动", duration_ms=0)
    resp = await _dispatch("shutdown", {})
    if resp.success:
        _shell = None
    return resp


# ============================================================================
# 进程管理
# ============================================================================


@router.post("/spawn", response_model=AgentOSResponse)
async def spawn(req: SpawnRequest, _payload: dict = Depends(verify_jwt_token)):
    """创建 Agent 进程。"""
    args: dict[str, Any] = {"_positional": [req.name]}
    if req.priority is not None:
        args["priority"] = req.priority
    if req.capabilities is not None:
        args["capabilities"] = ",".join(req.capabilities)
    if req.parent_pid is not None:
        args["parent"] = req.parent_pid
    return await _dispatch("spawn", args)


@router.post("/kill", response_model=AgentOSResponse)
async def kill(req: KillRequest, _payload: dict = Depends(verify_jwt_token)):
    """终止 Agent 进程。"""
    args: dict[str, Any] = {"_positional": [req.pid]}
    if req.reason is not None:
        args["reason"] = req.reason
    return await _dispatch("kill", args)


@router.get("/ps", response_model=AgentOSResponse)
async def ps(_payload: dict = Depends(verify_jwt_token)):
    """列出所有进程。"""
    return await _dispatch("ps", {})


@router.get("/info/{pid}", response_model=AgentOSResponse)
async def info(pid: str, _payload: dict = Depends(verify_jwt_token)):
    """进程详情。"""
    return await _dispatch("info", {"_positional": [pid]})


# ============================================================================
# Syscall / LLM
# ============================================================================


@router.post("/exec", response_model=AgentOSResponse)
async def exec_syscall(req: ExecRequest, _payload: dict = Depends(verify_jwt_token)):
    """执行 syscall。"""
    args: dict[str, Any] = {"_positional": [req.syscall]}
    if req.pid is not None:
        args["pid"] = req.pid
    if req.args:
        args.update(req.args)
    return await _dispatch("exec", args)


@router.post("/llm", response_model=AgentOSResponse)
async def llm(req: LlmRequest, _payload: dict = Depends(verify_jwt_token)):
    """LLM 推理。"""
    args: dict[str, Any] = {"_positional": [req.prompt]}
    if req.pid is not None:
        args["pid"] = req.pid
    if req.system is not None:
        args["system"] = req.system
    return await _dispatch("llm", args)


# ============================================================================
# 文件系统
# ============================================================================


@router.post("/fs/read", response_model=AgentOSResponse)
async def fs_read(req: FsReadRequest, _payload: dict = Depends(verify_jwt_token)):
    """读取文件。"""
    return await _dispatch("fs.read", {"_positional": [req.path]})


@router.post("/fs/write", response_model=AgentOSResponse)
async def fs_write(req: FsWriteRequest, _payload: dict = Depends(verify_jwt_token)):
    """写入文件。"""
    return await _dispatch("fs.write", {"_positional": [req.path], "content": req.content})


@router.post("/fs/list", response_model=AgentOSResponse)
async def fs_list(req: FsListRequest, _payload: dict = Depends(verify_jwt_token)):
    """列出目录。"""
    args: dict[str, Any] = {}
    if req.path is not None:
        args["_positional"] = [req.path]
    return await _dispatch("fs.list", args)


@router.post("/fs/mkdir", response_model=AgentOSResponse)
async def fs_mkdir(req: FsMkdirRequest, _payload: dict = Depends(verify_jwt_token)):
    """创建目录。"""
    return await _dispatch("fs.mkdir", {"_positional": [req.path]})


@router.post("/fs/delete", response_model=AgentOSResponse)
async def fs_delete(req: FsDeleteRequest, _payload: dict = Depends(verify_jwt_token)):
    """删除文件/目录。"""
    return await _dispatch("fs.delete", {"_positional": [req.path]})


# ============================================================================
# 记忆
# ============================================================================


@router.post("/mem/recall", response_model=AgentOSResponse)
async def mem_recall(req: MemRecallRequest, _payload: dict = Depends(verify_jwt_token)):
    """回忆记忆。"""
    args: dict[str, Any] = {"_positional": [req.query]}
    if req.layers is not None:
        args["layers"] = req.layers
    if req.top_k is not None:
        args["top_k"] = req.top_k
    return await _dispatch("mem.recall", args)


@router.post("/mem/store", response_model=AgentOSResponse)
async def mem_store(req: MemStoreRequest, _payload: dict = Depends(verify_jwt_token)):
    """存储记忆。"""
    args: dict[str, Any] = {"content": req.content}
    if req.layer is not None:
        args["layer"] = req.layer
    return await _dispatch("mem.store", args)


@router.post("/mem/search", response_model=AgentOSResponse)
async def mem_search(req: MemSearchRequest, _payload: dict = Depends(verify_jwt_token)):
    """搜索记忆。"""
    args: dict[str, Any] = {"_positional": [req.query]}
    if req.layer is not None:
        args["layer"] = req.layer
    if req.top_k is not None:
        args["top_k"] = req.top_k
    return await _dispatch("mem.search", args)


@router.post("/mem/forget", response_model=AgentOSResponse)
async def mem_forget(req: MemForgetRequest, _payload: dict = Depends(verify_jwt_token)):
    """遗忘记忆。"""
    return await _dispatch("mem.forget", {"_positional": [req.memory_id]})


# ============================================================================
# 工具
# ============================================================================


@router.get("/tool/list", response_model=AgentOSResponse)
async def tool_list(
    pid: str | None = Query(None, description="调用方 PID"),
    _payload: dict = Depends(verify_jwt_token),
):
    """列出工具。"""
    args: dict[str, Any] = {}
    if pid is not None:
        args["pid"] = pid
    return await _dispatch("tool.list", args)


@router.post("/tool/invoke", response_model=AgentOSResponse)
async def tool_invoke(req: ToolInvokeRequest, _payload: dict = Depends(verify_jwt_token)):
    """调用工具。"""
    args: dict[str, Any] = {"_positional": [req.tool_name]}
    if req.args is not None:
        args["args"] = req.args
    return await _dispatch("tool.invoke", args)


# ============================================================================
# A2A 通信
# ============================================================================


@router.post("/a2a/discover", response_model=AgentOSResponse)
async def a2a_discover(req: A2aDiscoverRequest, _payload: dict = Depends(verify_jwt_token)):
    """发现 Agent。"""
    args: dict[str, Any] = {}
    if req.capability is not None:
        args["capability"] = req.capability
    return await _dispatch("a2a.discover", args)


@router.post("/a2a/send", response_model=AgentOSResponse)
async def a2a_send(req: A2aSendRequest, _payload: dict = Depends(verify_jwt_token)):
    """发送 A2A 消息。"""
    args: dict[str, Any] = {"target": req.target, "content": req.content}
    if req.type is not None:
        args["type"] = req.type
    return await _dispatch("a2a.send", args)


@router.post("/a2a/broadcast", response_model=AgentOSResponse)
async def a2a_broadcast(req: A2aBroadcastRequest, _payload: dict = Depends(verify_jwt_token)):
    """广播 A2A 消息。"""
    return await _dispatch("a2a.broadcast", {"content": req.content})


# ============================================================================
# Skill
# ============================================================================


@router.get("/skill/list", response_model=AgentOSResponse)
async def skill_list(_payload: dict = Depends(verify_jwt_token)):
    """列出 Skill。"""
    return await _dispatch("skill.list", {})


@router.post("/skill/load", response_model=AgentOSResponse)
async def skill_load(req: SkillLoadRequest, _payload: dict = Depends(verify_jwt_token)):
    """加载 Skill 目录。"""
    return await _dispatch("skill.load", {"_positional": [req.dir]})


@router.post("/skill/run", response_model=AgentOSResponse)
async def skill_run(req: SkillRunRequest, _payload: dict = Depends(verify_jwt_token)):
    """运行 Skill。"""
    args: dict[str, Any] = {"_positional": [req.name]}
    if req.args:
        args.update(req.args)
    return await _dispatch("skill.run", args)


# ============================================================================
# 策略 / 护栏 / 审计 / 统计
# ============================================================================


@router.get("/policy/list", response_model=AgentOSResponse)
async def policy_list(_payload: dict = Depends(verify_jwt_token)):
    """列出策略。"""
    return await _dispatch("policy.list", {})


@router.post("/policy/add", response_model=AgentOSResponse)
async def policy_add(req: PolicyAddRequest, _payload: dict = Depends(verify_jwt_token)):
    """添加策略。"""
    args: dict[str, Any] = {"action": req.action, "effect": req.effect}
    if req.subject is not None:
        args["subject"] = req.subject
    if req.priority is not None:
        args["priority"] = req.priority
    return await _dispatch("policy.add", args)


@router.get("/guardrail/list", response_model=AgentOSResponse)
async def guardrail_list(_payload: dict = Depends(verify_jwt_token)):
    """列出护栏。"""
    return await _dispatch("guardrail.list", {})


@router.get("/audit", response_model=AgentOSResponse)
async def audit(
    _payload: dict = Depends(verify_jwt_token),
    limit: int | None = Query(None, ge=1, description="返回条数上限"),
    action: str | None = Query(None, description="按操作类型筛选"),
):
    """查询审计日志。"""
    args: dict[str, Any] = {}
    if limit is not None:
        args["limit"] = limit
    if action is not None:
        args["action"] = action
    return await _dispatch("audit", args)


@router.get("/stats", response_model=AgentOSResponse)
async def stats(_payload: dict = Depends(verify_jwt_token)):
    """内核统计。"""
    return await _dispatch("stats", {})


@router.post("/checkpoint", response_model=AgentOSResponse)
async def checkpoint(req: CheckpointRequest, _payload: dict = Depends(verify_jwt_token)):
    """保存进程检查点。"""
    return await _dispatch("checkpoint", {"_positional": [req.pid]})


# ============================================================================
# 自然语言接口
# ============================================================================


@router.post("/natural", response_model=AgentOSResponse)
async def natural(req: NaturalRequest, _payload: dict = Depends(verify_jwt_token)):
    """自然语言接口 (转发为 LLM_COMPLETE syscall)。"""
    shell = await get_shell()
    start = time.monotonic()
    try:
        result = await shell.natural_language(req.text)
        return _to_response(result, start)
    except Exception as e:
        return AgentOSResponse(
            success=False,
            error=f"自然语言处理异常: {type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


# ============================================================================
# 帮助
# ============================================================================


@router.get("/help", response_model=AgentOSResponse)
async def help_(_payload: dict = Depends(verify_jwt_token)):
    """显示所有命令。"""
    return await _dispatch("help", {})
