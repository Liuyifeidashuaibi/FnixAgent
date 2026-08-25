"""API 路由 — Work 模式（README 9 步流水线主路径）。

对齐工程实践：
  安全 → 记忆 → 推理选择 → KTG/STP → 执行 → 审核 → MFP/持久化
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from fnixagent.harness.paths import default_workspace

router = APIRouter(prefix="/work", tags=["work"])

_ARTIFACT_RE = re.compile(
    r"(?P<path>[^\s\"']+\.(?:docx|xlsx|pptx|pdf|md|csv|txt|html|htm|css|js|json|png|jpg|jpeg|svg))",
    re.IGNORECASE,
)


class LlmOverride(BaseModel):
    """Desktop BYOK / 请求级模型覆盖。"""

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    # 管理员：使用服务端 .env Key（不传真实 Key）
    use_server_key: bool | None = None


class WorkStreamRequest(BaseModel):
    """Work 流式任务请求。"""

    user_input: str = Field(..., min_length=1, max_length=20000)
    workspace: str | None = None
    session_id: str | None = None
    llm: LlmOverride | None = None
    user_id: str | None = None
    # 工作台：ask=问一问 / plan=想一想 / craft=做一做（默认）
    work_mode: str | None = Field(default="craft", max_length=16)
    # 前端技能开关：禁用的内置技能名（builtin skills 注入时跳过）
    disabled_skills: list[str] | None = Field(default=None, max_length=64)


class WorkJobRequest(BaseModel):
    """后台挂机 Work 任务（不占用 SSE 连接）。"""

    user_input: str = Field(..., min_length=1, max_length=20000)
    workspace: str | None = None
    session_id: str | None = None
    llm: LlmOverride | None = None
    user_id: str | None = None
    priority: int = 10


def _extract_artifacts(payload: Any) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        path = path.strip().rstrip(".,;")
        if not path or path in seen:
            return
        seen.add(path)
        found.append({"path": path, "name": os.path.basename(path)})

    if isinstance(payload, dict):
        for key in ("file_path", "output_path", "path", "output"):
            val = payload.get(key)
            if isinstance(val, str) and _ARTIFACT_RE.search(val):
                add(val)
        for val in payload.values():
            if isinstance(val, str):
                for m in _ARTIFACT_RE.finditer(val):
                    add(m.group("path"))
    elif isinstance(payload, str):
        for m in _ARTIFACT_RE.finditer(payload):
            add(m.group("path"))
        for m in re.finditer(r"已写入:\s*([^\s(]+)", payload):
            add(m.group(1))
    return found


def _ndjson(chunk_type: str, content: Any, done: bool = False, trace_id: str = "") -> str:
    payload: dict[str, Any] = {
        "chunk_type": chunk_type,
        "content": content,
        "done": done,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return json.dumps(payload, ensure_ascii=False) + "\n"


@router.post("/stream")
async def work_stream(body: WorkStreamRequest, request: Request):
    """办公任务流式执行 — README 9 步流水线。"""
    from fnixagent.services.llm_policy import principal_is_admin, resolve_llm_for_request

    workspace = body.workspace or str(default_workspace())
    raw_llm = body.llm.model_dump(exclude_none=True) if body.llm else None
    is_admin = principal_is_admin(request)
    llm_dict, llm_err = resolve_llm_for_request(raw_llm, is_admin=is_admin)

    async def generate():
        from fnixagent.services.work_pipeline import merge_artifact, run_work_stream

        trace_id = ""

        # H1 史诗级优化: Input Guardrail
        # 在请求入口拦截提示注入 / API Key 泄露 / 超长输入
        try:
            from fnixagent.core.agent.artifact_guardrail import run_input_guardrails

            input_passed, input_reasons = run_input_guardrails(body.user_input)
            if not input_passed:
                yield _ndjson(
                    "guardrail",
                    {
                        "passed": False,
                        "stage": "input",
                        "summary": "Input Guardrail 拦截",
                        "missing": [],
                        "issues": [input_reasons],
                        "validation_count": 0,
                        "blocked": True,
                    },
                    True,
                    trace_id,
                )
                yield _ndjson(
                    "error", f"输入被安全策略拦截: {'; '.join(input_reasons)}", True, trace_id
                )
                return
        except Exception as _ig_exc:
            print(f"[input guardrail ERROR] {_ig_exc}")  # 不阻断主流程

        artifacts_all: list[dict[str, str]] = []
        exec_mode = (body.work_mode or "craft").strip().lower()

        def add_artifact(path: str) -> dict[str, str] | None:
            n = len(artifacts_all)
            merge_artifact(artifacts_all, path, workspace)
            if len(artifacts_all) > n:
                return artifacts_all[-1]
            return None

        if llm_err:
            yield _ndjson("error", llm_err, True, trace_id)
            return

        try:
            async for event in run_work_stream(
                user_input=body.user_input,
                workspace=workspace,
                llm=llm_dict,
                session_id=body.session_id,
                user_id=body.user_id or "desktop",
                app_state=request.app.state,
                work_mode=body.work_mode or "craft",
                disabled_skills=body.disabled_skills,
            ):
                et = event.get("type", "")
                data = event.get("data", "")

                if isinstance(data, dict) and data.get("trace_id"):
                    trace_id = data["trace_id"]

                if et == "evolution":
                    yield _ndjson("evolution", data, False, trace_id)
                elif et == "decision_context":
                    # Spec 5: 决策上下文面板 — 透传给前端 DecisionCard
                    yield _ndjson("decision_context", data, False, trace_id)
                elif et == "mission":
                    yield _ndjson("mission", data, False, trace_id)
                elif et == "pipeline":
                    yield _ndjson("pipeline", data, False, trace_id)
                elif et == "thinking":
                    yield _ndjson("thought", str(data), False, trace_id)
                elif et == "tool_call":
                    yield _ndjson("action", data, False, trace_id)
                    if isinstance(data, dict):
                        name = str(data.get("name") or data.get("tool") or "")
                        args = data.get("args") or data.get("arguments") or {}
                        # H1 史诗级优化: Tool Guardrail
                        # 检测路径穿越 / API Key 泄露 / 破坏性命令
                        try:
                            from fnixagent.core.agent.artifact_guardrail import run_tool_guardrails

                            tool_passed, tool_reasons = run_tool_guardrails(name, args, workspace)
                            if not tool_passed:
                                yield _ndjson(
                                    "guardrail",
                                    {
                                        "passed": False,
                                        "stage": "tool",
                                        "summary": f"Tool Guardrail 拦截: {name}",
                                        "missing": [],
                                        "issues": [tool_reasons],
                                        "validation_count": 0,
                                        "blocked": True,
                                        "tool_name": name,
                                    },
                                    False,
                                    trace_id,
                                )
                        except Exception:
                            pass
                        if name in ("write_file", "edit_file") and isinstance(args, dict):
                            p = str(
                                args.get("path")
                                or args.get("rel_path")
                                or args.get("file_path")
                                or ""
                            ).strip()
                            if p:
                                art = add_artifact(p)
                                if art:
                                    yield _ndjson("artifact", art, False, trace_id)
                elif et == "tool_result":
                    text = str(data)
                    yield _ndjson("observation", text, False, trace_id)
                    if exec_mode == "craft":
                        arts = _extract_artifacts(data)
                        if not arts:
                            arts = _extract_artifacts(text)
                        for art in arts:
                            merged = add_artifact(art["path"])
                            if merged:
                                yield _ndjson("artifact", merged, False, trace_id)
                elif et == "artifact":
                    if isinstance(data, dict) and data.get("path"):
                        merged = add_artifact(str(data["path"]))
                        if merged:
                            yield _ndjson("artifact", merged, False, trace_id)
                elif et == "guardrail":
                    # 史诗级优化: Artifact Guardrail + Reflexion 修复循环
                    yield _ndjson("guardrail", data, False, trace_id)
                elif et == "text":
                    yield _ndjson("text", str(data), True, trace_id)
                elif et == "done":
                    if isinstance(data, dict):
                        for art in data.get("artifacts") or []:
                            if isinstance(art, dict) and art.get("path"):
                                add_artifact(str(art["path"]))
                        data = {**data, "artifacts": artifacts_all}
                        if data.get("trace_id"):
                            trace_id = data["trace_id"]
                    yield _ndjson("done", data, True, trace_id)
                elif et == "error":
                    yield _ndjson("error", str(data), True, trace_id)
                else:
                    yield _ndjson(et or "event", data, False, trace_id)

        except Exception as e:
            yield _ndjson("error", str(e), True, trace_id)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/status")
async def work_status(request: Request):
    """Work 内核状态：KTG/STP/MFP/记忆/安全 + fnix-local 降级信息。"""
    from fnixagent.services.engine_status import merge_work_status
    from fnixagent.services.llm_policy import principal_is_admin

    return merge_work_status(
        request.app.state,
        is_admin=principal_is_admin(request),
    )


@router.get("/llm-profile")
async def work_llm_profile(request: Request):
    """管理员 LLM 展示配置（不含真实 Key）。普通用户也可见策略说明。"""
    from fnixagent.services.llm_policy import principal_is_admin, server_llm_profile

    profile = server_llm_profile()
    profile["is_admin"] = principal_is_admin(request)
    return profile


@router.get("/sessions")
async def list_work_sessions(
    workspace: str | None = None,
    user_id: str | None = None,
    mode: str | None = None,
    limit: int = 50,
):
    """列出持久化的 Work/Code 任务 session（Harness）。"""
    from fnixagent.harness.session import get_session_store

    store = get_session_store()
    sessions = store.list_sessions(
        user_id=user_id,
        workspace=workspace,
        limit=min(max(limit, 1), 100),
    )
    if mode in ("work", "code"):
        sessions = [s for s in sessions if s.mode == mode]
    return {
        "ok": True,
        "sessions": [s.to_dict() for s in sessions],
    }


@router.get("/sessions/{session_id}")
async def get_work_session(session_id: str):
    """获取单个 Work session。"""
    from fnixagent.harness.session import get_session_store

    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, "session": session.to_dict()}


@router.post("/jobs")
async def enqueue_work_job(body: WorkJobRequest, request: Request):
    """将 Work 任务放入后台队列；关闭 SSE 后仍可继续执行。"""
    from fnixagent.harness.work_jobs import enqueue_work_job as _enqueue
    from fnixagent.services.llm_policy import principal_is_admin, resolve_llm_for_request

    workspace = body.workspace or str(default_workspace())
    raw_llm = body.llm.model_dump(exclude_none=True) if body.llm else None
    is_admin = principal_is_admin(request)
    llm_dict, llm_err = resolve_llm_for_request(raw_llm, is_admin=is_admin)
    if llm_err:
        raise HTTPException(status_code=400, detail=llm_err)

    result = _enqueue(
        user_input=body.user_input,
        workspace=workspace,
        llm=llm_dict,
        session_id=body.session_id,
        user_id=body.user_id or "desktop",
        priority=body.priority,
        app_state=request.app.state,
    )
    return result


@router.get("/jobs/{session_id}/events")
async def work_job_events(session_id: str, limit: int = 50):
    """拉取后台任务事件尾部（重连用）。"""
    from fnixagent.harness.session import get_session_store
    from fnixagent.harness.work_jobs import get_job_events

    store = get_session_store()
    session = store.get(session_id)
    events = get_job_events(session_id, limit=min(max(limit, 1), 200))
    return {
        "ok": True,
        "session": session.to_dict() if session else None,
        "events": events,
    }


# ── P0 多任务并行可视化：列表/取消/统计/活跃 ──────────────────────────────


@router.get("/jobs")
async def list_work_jobs(
    workspace: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    """列出所有后台 jobs（含排队/运行/完成/失败/取消）。

    支持按 workspace 和 status 过滤，返回字段包含 progress/steps/priority/error。
    """
    from fnixagent.harness.work_jobs import list_jobs

    jobs = list_jobs(
        workspace=workspace,
        status=status,
        limit=min(max(limit, 1), 200),
    )
    return {
        "ok": True,
        "jobs": jobs,
        "count": len(jobs),
    }


@router.post("/jobs/{session_id}/cancel")
async def cancel_work_job(session_id: str):
    """取消正在执行或排队的 job（协作式取消）。

    - 若 job 正在执行：worker 在下一个事件循环点检查并停止
    - 若 job 还在排队：从队列移除
    - 若 job 已完成：返回 409
    """
    from fnixagent.harness.session import get_session_store
    from fnixagent.harness.work_jobs import cancel_job, is_cancelled

    store = get_session_store()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"job already {session.status}")
    if is_cancelled(session_id):
        return {"ok": True, "session_id": session_id, "status": "already_cancelled"}
    ok = cancel_job(session_id)
    return {
        "ok": ok,
        "session_id": session_id,
        "status": "cancelled" if ok else "not_active",
    }


@router.get("/jobs/stats")
async def work_jobs_stats():
    """返回多任务聚合统计（pending/running/completed/failed/cancelled/active/total）。"""
    from fnixagent.harness.work_jobs import job_stats

    return {"ok": True, "stats": job_stats()}


@router.get("/jobs/active")
async def work_jobs_active():
    """返回当前正在执行的 job session_id 列表。"""
    from fnixagent.harness.work_jobs import active_job_sessions

    sids = active_job_sessions()
    return {"ok": True, "active": sids, "count": len(sids)}


# ─── Spec 3: Artifact Canvas 内联预览端点 ────────────────────────────────
# 安全策略：
#   1. 路径必须在 workspace 下（防穿越）
#   2. 文件大小 < 2 MB（防 OOM）
#   3. 仅允许预览安全类型（html/svg/md/txt/json/code/image）
#   4. 返回 {path, name, ext, size, mime, content, encoding}
#      - 文本类型: content=字符串, encoding="utf-8"
#      - 图片类型: content=base64, encoding="base64"
#   5. 前端 iframe sandbox="allow-scripts" 渲染 HTML（不加 allow-same-origin 隔离 DOM）

_ALLOWED_PREVIEW_EXT = {
    "html",
    "htm",
    "svg",
    "md",
    "markdown",
    "txt",
    "json",
    "csv",
    "js",
    "ts",
    "jsx",
    "tsx",
    "css",
    "scss",
    "less",
    "py",
    "rs",
    "go",
    "java",
    "c",
    "cpp",
    "h",
    "hpp",
    "yaml",
    "yml",
    "toml",
    "ini",
    "sh",
    "bash",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "ico",
}

_MIME_MAP = {
    "html": "text/html",
    "htm": "text/html",
    "svg": "image/svg+xml",
    "md": "text/markdown",
    "markdown": "text/markdown",
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "js": "text/javascript",
    "jsx": "text/javascript",
    "ts": "text/typescript",
    "tsx": "text/typescript",
    "css": "text/css",
    "scss": "text/css",
    "less": "text/css",
    "py": "text/x-python",
    "rs": "text/x-rust",
    "go": "text/x-go",
    "java": "text/x-java",
    "c": "text/x-c",
    "cpp": "text/x-c++",
    "h": "text/x-c",
    "hpp": "text/x-c++",
    "yaml": "text/yaml",
    "yml": "text/yaml",
    "toml": "application/toml",
    "ini": "text/plain",
    "sh": "text/x-shellscript",
    "bash": "text/x-shellscript",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "ico": "image/x-icon",
}

_MAX_PREVIEW_BYTES = 2 * 1024 * 1024  # 2 MB


@router.get("/artifacts/read")
async def work_read_artifact(path: str, request: Request):
    """读取产物文件内容供前端 Canvas 内联预览。

    Query:
        path: 文件绝对路径或相对 workspace 路径

    Returns:
        {ok, path, name, ext, size, mime, content, encoding, error?}
    """
    import base64
    from pathlib import Path as PathLib

    workspace = str(default_workspace())
    ws_abs = PathLib(workspace).resolve()

    # 路径解析：相对 workspace 或绝对路径
    raw_path = PathLib(path).expanduser()
    try:
        if raw_path.is_absolute():
            target = raw_path.resolve()
        else:
            target = (ws_abs / raw_path).resolve()
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"invalid path: {e}"}

    # 安全检查：必须在 workspace 下（使用路径前缀比较，防 startswith 绕过）
    try:
        target.relative_to(ws_abs)
    except ValueError:
        # 严格路径边界检查：确保 target 是 ws_abs 的子路径
        ws_parts = ws_abs.parts
        tgt_parts = target.parts
        if len(tgt_parts) <= len(ws_parts) or tgt_parts[: len(ws_parts)] != ws_parts:
            return {"ok": False, "error": "path outside workspace"}

    if not target.exists():
        return {"ok": False, "error": "file not found"}
    if not target.is_file():
        return {"ok": False, "error": "not a file"}

    # 扩展名白名单检查
    ext = target.suffix.lstrip(".").lower()
    if ext not in _ALLOWED_PREVIEW_EXT:
        return {"ok": False, "error": f"extension .{ext} not previewable"}

    # 大小检查
    size = target.stat().st_size
    if size > _MAX_PREVIEW_BYTES:
        return {"ok": False, "error": f"file too large ({size} bytes > {_MAX_PREVIEW_BYTES})"}

    mime = _MIME_MAP.get(ext, "application/octet-stream")
    is_image = ext in {"png", "jpg", "jpeg", "gif", "webp", "ico"}
    is_svg = ext == "svg"

    try:
        if is_image:
            # 图片：base64 编码
            data = target.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            return {
                "ok": True,
                "path": str(target),
                "name": target.name,
                "ext": ext,
                "size": size,
                "mime": mime,
                "encoding": "base64",
                "content": b64,
            }
        else:
            # 文本/SVG/HTML：utf-8
            text = target.read_text(encoding="utf-8", errors="replace")
            return {
                "ok": True,
                "path": str(target),
                "name": target.name,
                "ext": ext,
                "size": size,
                "mime": mime,
                "encoding": "utf-8",
                "content": text,
                "is_svg": is_svg,
                "is_html": ext in {"html", "htm"},
                "is_markdown": ext in {"md", "markdown"},
            }
    except Exception as e:
        return {"ok": False, "error": f"read failed: {e}"}


# ─── Spec 3: Artifact 增量编辑 (diff-apply) ──────────────────────────────
# 画布编辑 / 内联编辑 / 搜索替换块
#
# 设计:
#   - POST /artifacts/write  用户手动编辑后整文件写入
#   - POST /artifacts/apply  接收 SEARCH/REPLACE patch 增量应用
#
# 安全:
#   - 写入路径必须在 workspace 下
#   - 扩展名必须在 _ALLOWED_WRITE_EXT 白名单(防止覆盖代码文件)
#   - 写入大小限制 2MB
#   - 原子写入:先写 .tmp,再 rename,避免半写文件
#
# SEARCH/REPLACE 格式:
#   <<<<<<< SEARCH
#   原始片段
#   =======
#   替换片段
#   >>>>>>> REPLACE

_ALLOWED_WRITE_EXT = {
    # 文档与产物(用户/AI 都可改)
    "md",
    "markdown",
    "txt",
    "csv",
    "json",
    # 网页产物(Craft 模式生成,用户可手改)
    "html",
    "htm",
    "css",
    "js",
    "ts",
    "jsx",
    "tsx",
    # 配置(可改)
    "yaml",
    "yml",
    "toml",
    "ini",
    # SVG(可改)
    "svg",
}

_MAX_WRITE_BYTES = 2 * 1024 * 1024  # 2 MB


class ArtifactWriteRequest(BaseModel):
    """整文件写入请求(用户手动保存)。"""

    path: str = Field(..., min_length=1, max_length=1024)
    content: str = Field(..., max_length=_MAX_WRITE_BYTES)
    workspace: str | None = None


class ArtifactApplyRequest(BaseModel):
    """增量编辑请求(AI patch 应用)。

    patch 字段含多个 SEARCH/REPLACE block,格式见模块注释。
    """

    path: str = Field(..., min_length=1, max_length=1024)
    patch: str = Field(..., max_length=_MAX_WRITE_BYTES)
    workspace: str | None = None


def _resolve_artifact_path(path: str, workspace: str | None = None) -> tuple[Any, Any]:
    """解析 artifact 路径,返回 (target, ws_abs) 或抛 HTTPException。

    安全检查:
      - 路径必须在 workspace 下
      - 路径必须存在(对 write 操作)
    """
    from pathlib import Path as PathLib

    ws = workspace or str(default_workspace())
    ws_abs = PathLib(ws).resolve()
    raw_path = PathLib(path).expanduser()
    try:
        if raw_path.is_absolute():
            target = raw_path.resolve()
        else:
            target = (ws_abs / raw_path).resolve()
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"invalid path: {e}") from e

    # 安全:必须在 workspace 下
    try:
        target.relative_to(ws_abs)
    except ValueError:
        # 允许 .fnix/artifacts 在 workspace 同级
        if not str(target).startswith(str(ws_abs)):
            raise HTTPException(
                status_code=403,
                detail="path outside workspace",
            ) from None

    return target, ws_abs


def _atomic_write(target: Any, content: str) -> None:
    """原子写入:先写 .tmp,再 rename。"""
    import tempfile

    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    # 在同目录建临时文件,确保 rename 是原子的
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    except Exception:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@router.post("/artifacts/write")
async def work_write_artifact(req: ArtifactWriteRequest, request: Request):
    """用户手动编辑后整文件写入。

    Body:
        { "path": "...", "content": "...", "workspace": "..." }

    Returns:
        { "ok": true, "path": "...", "size": N }
        { "ok": false, "error": "..." }
    """
    target, _ = _resolve_artifact_path(req.path, req.workspace)

    ext = target.suffix.lstrip(".").lower()
    if ext not in _ALLOWED_WRITE_EXT:
        raise HTTPException(
            status_code=403,
            detail=f"extension .{ext} not writable (allowed: {sorted(_ALLOWED_WRITE_EXT)})",
        )

    if len(req.content.encode("utf-8")) > _MAX_WRITE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"content too large (max {_MAX_WRITE_BYTES} bytes)",
        )

    try:
        _atomic_write(target, req.content)
        return {
            "ok": True,
            "path": str(target),
            "size": len(req.content.encode("utf-8")),
        }
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}


@router.post("/artifacts/apply")
async def work_apply_artifact_patch(req: ArtifactApplyRequest, request: Request):
    """应用 SEARCH/REPLACE patch 到 artifact 文件(增量编辑)。

    对齐: 搜索替换块 + 内联编辑 + 画布编辑

    流程:
        1. 读取原文件
        2. 解析 patch 为 SearchReplaceBlock 列表
        3. 逐个应用 block,记录失败
        4. 若全部成功 → 原子写入新内容
        5. 若部分失败 → 返回 results 数组,不写入

    Body:
        { "path": "...", "patch": "<<<<<<< SEARCH\\n...\\n=======\\n...\\n>>>>>>> REPLACE", "workspace": "..." }

    Returns:
        {
            "ok": true,
            "path": "...",
            "size": N,
            "applied_blocks": 3,
            "results": [{"applied": true, "diffRanges": [{...}]}]
        }
        {
            "ok": false,
            "error": "...",
            "results": [{"applied": false, "error": "SEARCH not found"}]
        }
    """

    target, _ = _resolve_artifact_path(req.path, req.workspace)

    ext = target.suffix.lstrip(".").lower()
    if ext not in _ALLOWED_WRITE_EXT:
        raise HTTPException(
            status_code=403,
            detail=f"extension .{ext} not writable (allowed: {sorted(_ALLOWED_WRITE_EXT)})",
        )

    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")
    if not target.is_file():
        raise HTTPException(status_code=400, detail="not a file")

    # 读取原内容
    try:
        original = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"ok": False, "error": f"read failed: {e}"}

    # 解析 patch (与前端 artifactPatch.ts 一致)
    SEARCH_START = "<<<<<<< SEARCH"
    DIVIDER = "======="
    REPLACE_END = ">>>>>>> REPLACE"
    lines = req.patch.split("\n")
    blocks: list[dict[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().upper().startswith(SEARCH_START):
            search: list[str] = []
            replace: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(DIVIDER):
                search.append(lines[i])
                i += 1
            if i >= len(lines):
                break
            i += 1  # 跳过 DIVIDER
            while i < len(lines) and not lines[i].strip().upper().startswith(REPLACE_END):
                replace.append(lines[i])
                i += 1
            if i >= len(lines):
                break
            i += 1  # 跳过 REPLACE_END
            blocks.append(
                {
                    "search": "\n".join(search).rstrip("\n"),
                    "replace": "\n".join(replace).rstrip("\n"),
                }
            )
        else:
            i += 1

    if not blocks:
        return {"ok": False, "error": "no SEARCH/REPLACE block found in patch"}

    # 应用 patches
    content = original
    results: list[dict[str, Any]] = []
    all_ok = True
    offset = 0
    for idx, block in enumerate(blocks):
        search = block["search"]
        replace = block["replace"]
        if not search:
            results.append({"applied": False, "error": "empty SEARCH"})
            all_ok = False
            continue
        pos = content.find(search)
        if pos < 0:
            results.append(
                {
                    "applied": False,
                    "error": f"block #{idx + 1}: SEARCH not found in original",
                }
            )
            all_ok = False
            continue
        before = content[:pos]
        after = content[pos + len(search) :]
        content = before + replace + after
        # 计算改动行范围(1-based)
        start_line = content[: offset + len(before)].count("\n") + 1
        end_line = content[: offset + len(before) + len(replace)].count("\n") + 1
        results.append(
            {
                "applied": True,
                "diffRanges": [{"startLine": start_line, "endLine": end_line}],
            }
        )
        offset += len(replace) - len(search)

    if not all_ok:
        return {
            "ok": False,
            "error": "some blocks failed to apply",
            "results": results,
            "applied_blocks": sum(1 for r in results if r.get("applied")),
        }

    # 全部成功 → 原子写入
    if len(content.encode("utf-8")) > _MAX_WRITE_BYTES:
        return {"ok": False, "error": f"result too large (max {_MAX_WRITE_BYTES} bytes)"}

    try:
        _atomic_write(target, content)
        return {
            "ok": True,
            "path": str(target),
            "size": len(content.encode("utf-8")),
            "applied_blocks": len(blocks),
            "results": results,
        }
    except Exception as e:
        return {"ok": False, "error": f"write failed: {e}"}


# ─── Spec 4: 长程任务 resume_from_checkpoint ─────────────────────────────
# 长程任务中断后（崩溃/用户停止/超时），从最后一个 checkpoint 恢复执行
# 对齐 LangGraph Checkpoint / OpenAI Agents SDK session resume
#
# 核心流程：
#   1. GET /work/runs — 列出所有 runs（含状态、可恢复标志）
#   2. GET /work/runs/{run_id} — 获取 run 详情 + checkpoint state
#   3. POST /work/resume/{run_id} — 从 checkpoint 恢复执行，流式返回 events
#
# 恢复语义：
#   - 加载 checkpoint state（含 messages_so_far / artifacts_so_far）
#   - 重放历史 events 到 LLM 上下文（system + user + assistant + tool 历史）
#   - 调用 AgenticLoop.run_stream(user_input="", resume_from=state)
#   - 新 events 流式返回，同时持久化到同一 run_id


def _redact_run_meta(meta: dict) -> dict:
    """runs 对外响应脱敏：不把 API Key 回传给客户端。

    存储层保留完整凭据供 resume 使用；仅在 HTTP 响应出口遮罩。
    """
    import copy

    sanitized = copy.deepcopy(meta or {})
    llm = sanitized.get("llm")
    if isinstance(llm, dict):
        for key_field in ("api_key", "apiKey"):
            if llm.get(key_field):
                llm[key_field] = "***redacted***"
    return sanitized

@router.get("/runs")
async def work_list_runs(
    status: str | None = None,
    channel: str | None = None,
    limit: int = 50,
):
    """列出所有 run（含状态、可恢复标志）。Spec 4 长程任务恢复入口。

    Query:
        status: 过滤状态 (running/completed/failed/interrupted)
        channel: 过滤通道 (work/code)
        limit: 最多返回条数 (1-200)
    """
    from fnixagent.core.run.checkpoint import RunCheckpointStore

    store = RunCheckpointStore()
    limit_clamped = min(max(limit, 1), 200)

    with store._lock:
        conn = store._connect()
        try:
            sql = """
                SELECT run_id, channel, session_id, status, created_at, updated_at, meta_json
                FROM runs
            """
            args: list = []
            conditions = []
            if status:
                conditions.append("status = ?")
                args.append(status)
            if channel:
                conditions.append("channel = ?")
                args.append(channel)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
            sql += " ORDER BY updated_at DESC LIMIT ?"
            args.append(limit_clamped)
            rows = conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    runs = []
    for row in rows:
        meta = json.loads(row[6] or "{}")
        runs.append(
            {
                "run_id": row[0],
                "channel": row[1],
                "session_id": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
                "meta": _redact_run_meta(meta),
                "resumable": row[3] in ("running", "failed", "interrupted"),
            }
        )
    return {"ok": True, "runs": runs, "count": len(runs)}


@router.get("/runs/{run_id}")
async def work_get_run(run_id: str):
    """获取单个 run 详情 + checkpoint state + 最近 events。"""
    from fnixagent.core.run.checkpoint import RunCheckpointStore

    store = RunCheckpointStore()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    checkpoint = store.load_checkpoint(run_id)
    events = store.load_events(run_id, after_sequence=0)

    public_run = dict(run)
    if isinstance(public_run.get("meta"), dict):
        public_run["meta"] = _redact_run_meta(public_run["meta"])
    return {
        "ok": True,
        "run": public_run,
        "checkpoint": checkpoint,
        "events": events[-50:],  # 最近 50 条
        "events_total": len(events),
        "resumable": run["status"] in ("running", "failed", "interrupted"),
    }


def _build_resume_state_from_events(events: list[dict], checkpoint: dict | None) -> dict:
    """从历史 events 重建 LLM 消息上下文 (Spec 4 resume 核心)。

    重放策略：
    - thinking/thought → 不入消息（只是 step 标记）
    - tool_call → assistant message with tool_calls
    - tool_result → tool message
    - text → assistant message (最终答复)
    - 其他类型 → 跳过

    Returns:
        {
            "messages": [...],  # OpenAI chat 格式
            "completed_steps": int,
            "artifacts": [...],
        }
    """
    messages: list[dict] = []
    artifacts: list[dict] = []
    completed_steps = 0

    for ev in events:
        et = ev.get("type") or ev.get("event_type") or ""
        data = ev.get("data") or ev.get("payload") or ""

        if et in ("thinking", "thought"):
            # 思考标记不入消息
            continue
        elif et in ("tool_call", "action"):
            # 工具调用 → assistant message with tool_calls
            if isinstance(data, dict):
                name = str(data.get("name") or data.get("tool") or "")
                args = data.get("args") or data.get("arguments") or {}
                tool_call_id = f"call_{completed_steps}"
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(args, ensure_ascii=False),
                                },
                            }
                        ],
                    }
                )
                completed_steps += 1
        elif et in ("tool_result", "observation"):
            # 工具结果 → tool message
            content = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
            messages.append(
                {
                    "role": "tool",
                    "content": content[:4000],  # 截断防止上下文爆炸
                    "tool_call_id": f"call_{completed_steps - 1}",
                }
            )
        elif et == "text":
            # 最终答复 → assistant message
            if isinstance(data, str) and data.strip():
                messages.append({"role": "assistant", "content": data})
        elif et == "artifact":
            if isinstance(data, dict) and data.get("path"):
                artifacts.append({"path": data["path"], "name": data.get("name", "")})
        elif et == "done":
            # 任务完成的标记
            continue

    # 如果消息为空，尝试从 checkpoint state 恢复
    if not messages and checkpoint and checkpoint.get("messages_so_far"):
        messages = checkpoint["messages_so_far"]

    return {
        "messages": messages,
        "completed_steps": completed_steps,
        "artifacts": artifacts,
    }


@router.post("/resume/{run_id}")
async def work_resume_run(run_id: str, request: Request):
    """从 checkpoint 恢复执行长程任务。Spec 4 核心端点。

    流式返回 NDJSON events（同 /work/stream 格式）。
    """
    from fnixagent.core.run.checkpoint import RunCheckpointStore
    from fnixagent.services.llm_policy import principal_is_admin, resolve_llm_for_request

    store = RunCheckpointStore()
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")

    checkpoint = store.load_checkpoint(run_id)
    events = store.load_events(run_id, after_sequence=0)

    if not events:
        raise HTTPException(status_code=400, detail="no events to resume from")

    # 重建 resume state
    resume_state = _build_resume_state_from_events(events, checkpoint)
    if not resume_state["messages"]:
        raise HTTPException(status_code=400, detail="cannot rebuild messages from events")

    # LLM 配置从 run meta 恢复（如果有）
    meta = run.get("meta") or {}
    raw_llm = meta.get("llm")
    is_admin = principal_is_admin(request)
    llm_dict, llm_err = resolve_llm_for_request(raw_llm, is_admin=is_admin)

    async def generate():
        from fnixagent.services.work_pipeline import run_work_stream

        trace_id = run_id
        artifacts_all: list[dict[str, str]] = list(resume_state["artifacts"])

        if llm_err:
            yield _ndjson("error", llm_err, True, trace_id)
            return

        try:
            # 标记恢复开始
            yield _ndjson(
                "thinking",
                f"Spec 4: 从 run_id={run_id} 恢复，已重放 {len(resume_state['messages'])} 条消息，{len(artifacts_all)} 个 artifacts",
                False,
                trace_id,
            )

            # 用空 user_input + resume_from 触发恢复路径
            # Spec 4+: 传 run_id_override 让原 run_id 续写, 避免原 run 永远停留 interrupted
            async for event in run_work_stream(
                user_input="(resume)",
                workspace=meta.get("workspace") or str(default_workspace()),
                llm=llm_dict,
                session_id=run.get("session_id") or "",
                user_id=meta.get("user_id") or "desktop",
                app_state=request.app.state,
                work_mode=meta.get("work_mode") or "craft",
                resume_from=resume_state,  # 透传到 AgenticLoop
                run_id_override=run_id,  # Spec 4+: 同一 run 续写
            ):
                et = event.get("type", "")
                data = event.get("data", "")

                if et == "thinking":
                    yield _ndjson("thought", str(data), False, trace_id)
                elif et == "tool_call":
                    yield _ndjson("action", data, False, trace_id)
                elif et == "tool_result":
                    yield _ndjson("observation", str(data), False, trace_id)
                elif et == "text":
                    yield _ndjson("text", str(data), True, trace_id)
                elif et == "done":
                    if isinstance(data, dict):
                        data = {**data, "artifacts": artifacts_all, "resumed_from": run_id}
                    yield _ndjson("done", data, True, trace_id)
                elif et == "error":
                    yield _ndjson("error", str(data), True, trace_id)
                else:
                    yield _ndjson(et or "event", data, False, trace_id)

        except Exception as e:
            yield _ndjson("error", str(e), True, trace_id)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


# ── 用户反馈信号回路 (用户反馈信号机制) ──────────────────────


class FeedbackRequest(BaseModel):
    """用户反馈请求。

    feedback: "up"=有帮助 / "down"=没帮助 / "none"=取消反馈
    user_input: 用户原始输入 (后端用同样算法计算 task_hash, 保证匹配)
    comment: 可选文字反馈

    设计取舍: 前端传 user_input 而非 task_hash, 让后端统一计算 hash,
    避免前后端 hash 算法不一致导致反馈失配 (前端无 MD5, 浏览器 SubtleCrypto 不支持 MD5)。
    """

    feedback: str = Field(..., pattern="^(up|down|none)$")
    user_input: str = Field(..., min_length=1, max_length=20000)
    comment: str | None = Field(default="", max_length=500)
    workspace: str | None = None


@router.post("/feedback")
async def work_feedback(req: FeedbackRequest, request: Request):
    """用户反馈信号回流端点 (用户反馈信号机制)。

    用户 👍/👎 写入 HERA SkillLibrary 的 user_feedback 字段,
    影响下次 retrieve_skills 召回权重:
      - up: 权重 *1.3 (用户验证过的可靠路径)
      - down: 权重 *0.2 (用户否定的路径, 优先避开)
      - none: 清除反馈

    返回 {"updated": bool} — 未找到匹配技能时 updated=False (静默降级)。
    """
    workspace = req.workspace or os.environ.get("FNIX_WORKSPACE", "")
    if not workspace:
        workspace = os.path.expanduser("~/.fnix/workspace")

    try:
        import hashlib

        from fnixagent.core.skills.library import SkillLibrary

        # 后端统一计算 task_hash, 与 add_new_skill 算法一致
        task_hash = hashlib.md5(req.user_input.strip()[:200].encode("utf-8")).hexdigest()[:12]

        library = SkillLibrary(workspace)
        updated = library.add_feedback(
            task_hash=task_hash,
            feedback=req.feedback,
            comment=req.comment or "",
        )
        return {"updated": updated, "feedback": req.feedback}
    except Exception as e:
        return {"updated": False, "error": str(e)}
