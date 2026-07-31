"""获取 workspace 的本地上下文（索引 + PDG digest + Python 降级召回）。"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any

from fnixagent.harness.context_budget import INDEX_MAX, RULES_MAX, merge_budget_reports, trim_text
from fnixagent.harness.local_bridge import (
    format_local_context_block,
    get_local_bridge,
)


def ensure_indexed(workspace: str, *, session_id: str | None = None) -> dict[str, Any]:
    """确保 workspace 已索引；sidecar 离线时静默降级。"""
    bridge = get_local_bridge()
    if not bridge.enabled:
        return {"ok": False}
    return bridge.index_workspace(workspace, session_id=session_id)


def _run_coro_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result(timeout=90)


def _python_index_context(
    workspace: str,
    *,
    query: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """sidecar 无命中时用 Python IndexStore（HashingEmbedder + BM25）。

    仅复用**已构建**的索引会话；不在此同步执行全量索引——
    在大仓库（数万文件）上同步索引会长时间阻塞请求 / 事件循环，
    拖垮整个后端。索引应由 fnix-local sidecar 或后台任务异步完成，
    sidecar 离线时此处静默降级（返回 ok:false），不再请求内同步扫描。
    """
    try:
        from fnixagent.local.index_store import get_index_store

        store = get_index_store()
        # 只复用内存中已存在的索引；没有就直接降级，避免请求内同步全量扫描。
        session = store.get_session(workspace=workspace)
        if session is None:
            return {
                "ok": False,
                "message": "未预建索引（sidecar 离线，跳过同步索引）",
                "vector_hits": [],
            }

        async def _build():
            return await store.build_context(
                workspace=workspace,
                session_id=session.session_id,
                query=query,
                top_k=8,
            )

        return _run_coro_sync(_build())
    except Exception as e:
        return {"ok": False, "message": str(e), "vector_hits": []}


def fetch_local_context(
    workspace: str,
    *,
    query: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    bridge = get_local_bridge()
    ctx: dict[str, Any] = {"ok": False}
    if bridge.enabled:
        status = bridge.health()
        if status.available:
            try:
                bridge.index_workspace(workspace, session_id=session_id)
                ctx = bridge.get_context(
                    workspace=workspace,
                    session_id=session_id,
                    query=query,
                    top_k=8,
                )
            except Exception as e:
                ctx = {"ok": False, "message": str(e)}

    hits = ctx.get("vector_hits") if isinstance(ctx, dict) else None
    if ctx.get("ok") and hits:
        ctx["source"] = "fnix-local"
        return ctx

    py_ctx = _python_index_context(workspace, query=query, session_id=session_id)
    if py_ctx.get("ok"):
        # 合并：保留 sidecar digest（若有）
        if ctx.get("pdg_digest") and not py_ctx.get("pdg_digest"):
            py_ctx["pdg_digest"] = ctx.get("pdg_digest")
        if ctx.get("stats") and not py_ctx.get("stats"):
            py_ctx["stats"] = ctx.get("stats")
        py_ctx["source"] = "python-index"
        return py_ctx

    if ctx.get("ok"):
        ctx["source"] = "fnix-local"
        return ctx
    return py_ctx if py_ctx else {"ok": False}


def local_context_prompt(
    workspace: str,
    *,
    query: str | None = None,
    session_id: str | None = None,
    cwd: str | None = None,
    budget_out: dict[str, Any] | None = None,
) -> str:
    """拼装注入 Work/Code 的本地上下文。

    顺序：SOUL → memories → skills → **project rules** → PDG/index。
    """
    from fnixagent.harness.memory import build_local_context_prompt
    from fnixagent.harness.project_rules import format_project_rules_block

    reports = []
    rules_block = ""
    try:
        rules_raw = format_project_rules_block(workspace, cwd=cwd or workspace)
        rules_block, r = trim_text(rules_raw, RULES_MAX)
        reports.append(r)
    except Exception:
        rules_block = ""

    ctx = fetch_local_context(workspace, query=query, session_id=session_id)
    index_raw = format_local_context_block(ctx, max_chars=INDEX_MAX)
    index_block, ir = trim_text(index_raw, INDEX_MAX)
    reports.append(ir)

    extra = "\n\n".join(part for part in (rules_block, index_block) if part and part.strip())
    prompt = build_local_context_prompt(extra=extra)
    if budget_out is not None:
        budget_out.update(merge_budget_reports(reports))
        budget_out["index_source"] = ctx.get("source") if isinstance(ctx, dict) else None
        budget_out["vector_hits"] = (
            len(ctx.get("vector_hits") or []) if isinstance(ctx, dict) else 0
        )
    return prompt
