"""Work 后台任务 — PriorityTaskQueue + session 可重连。

P0 多任务并行可视化升级：
  - worker_loop 改为多并发（asyncio.Semaphore + create_task）
  - _run_one 推送 progress/steps 到 session
  - 新增 cancel_job / list_jobs / active_job_sessions
  - 新增 _CANCELLED 集合实现取消信号
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from fnixagent.core.scheduler.priority_queue import ScheduleItem, get_priority_queue
from fnixagent.harness.paths import logs_dir
from fnixagent.harness.session import get_session_store

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None
_stop = asyncio.Event()
# 内存事件尾部（供 UI 快速拉取）；完整落盘到 logs
_event_tails: dict[str, list[dict[str, Any]]] = {}
_lock = threading.Lock()
_MAX_TAIL = 80


# ── P0 多任务并行：并发度限制 + 取消信号 ──
# Spec 6+ 改进: 并发上限按 LLM provider 自适应, 避免 BYOK 触发 429
#   - 默认 2 (单机 BYOK, qwen-plus 等免费档位 RPM 有限)
#   - 通过 FNIX_MAX_CONCURRENT_JOBS 环境变量可调
#   - 4 个并发每个跑 9 步 WorkPipeline 对 BYOK 不友好, 默认 2 让限流自然背压
def _resolve_max_concurrent() -> int:
    """从环境变量解析并发上限, 默认 2 (BYOK 友好)。"""
    raw = (os.getenv("FNIX_MAX_CONCURRENT_JOBS") or "").strip()
    if raw:
        try:
            v = int(raw)
            if v >= 1:
                return min(v, 16)  # 上限 16 防误配
        except ValueError:
            pass
    return 2  # BYOK 默认 2 并发


_MAX_CONCURRENT_JOBS = _resolve_max_concurrent()
_cancelled_sessions: set[str] = set()
_cancel_lock = threading.Lock()
_active_sessions: set[str] = set()
_active_lock = threading.Lock()

# 9 步流水线步骤定义（对应 README：mission→evolution→pipeline→thought→action→artifact→observation→text→done）
_PIPELINE_STEPS: list[tuple[str, str]] = [
    ("mission", "安全输入 / 任务接令"),
    ("evolution", "进化内核加载"),
    ("pipeline", "9 步流水线编排"),
    ("thought", "思考"),
    ("action", "动作"),
    ("artifact", "产物生成"),
    ("observation", "观察"),
    ("text", "总结回复"),
    ("done", "完成"),
]


def _event_log_path(session_id: str) -> Path:
    d = logs_dir() / "work_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{session_id}.jsonl"


def append_job_event(session_id: str, event: dict[str, Any]) -> None:
    with _lock:
        tail = _event_tails.setdefault(session_id, [])
        tail.append(event)
        if len(tail) > _MAX_TAIL:
            del tail[: len(tail) - _MAX_TAIL]
    try:
        with open(_event_log_path(session_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def get_job_events(session_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        tail = list(_event_tails.get(session_id, []))
    if tail:
        return tail[-limit:]
    path = _event_log_path(session_id)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def cancel_job(session_id: str) -> bool:
    """请求取消某个正在执行的 job（协作式：worker 在循环点检查）。"""
    with _cancel_lock:
        if session_id not in _active_sessions and session_id not in _event_tails:
            return False
        _cancelled_sessions.add(session_id)
    store = get_session_store()
    store.update(session_id, status="cancelled")
    append_job_event(session_id, {"type": "job", "data": {"status": "cancelled"}})
    return True


def is_cancelled(session_id: str) -> bool:
    with _cancel_lock:
        return session_id in _cancelled_sessions


def list_jobs(
    *,
    workspace: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """列出所有 jobs（含排队/运行/完成）。"""
    store = get_session_store()
    sessions = store.list_sessions(
        workspace=workspace,
        status=status,
        limit=min(max(limit, 1), 200),
    )
    return [s.to_dict() for s in sessions]


def active_job_sessions() -> list[str]:
    """返回当前正在执行的 job session_id 列表。"""
    with _active_lock:
        return list(_active_sessions)


def job_stats() -> dict[str, int]:
    """返回多任务聚合统计。"""
    store = get_session_store()
    all_sessions = store.list_sessions(limit=500)
    stats = {"pending": 0, "running": 0, "completed": 0, "failed": 0, "cancelled": 0, "total": 0}
    for s in all_sessions:
        stats["total"] += 1
        if s.status in stats:
            stats[s.status] += 1
    with _active_lock:
        stats["active"] = len(_active_sessions)
    return stats


def _init_session_steps(session_id: str) -> None:
    """初始化 session 的 steps 字段（9 步流水线占位）。"""
    store = get_session_store()
    from fnixagent.harness.session import _utc_now  # 局部导入避免循环

    steps = [
        {"key": k, "label": label, "status": "pending", "ts": _utc_now()}
        for k, label in _PIPELINE_STEPS
    ]
    store.update(session_id, steps=steps, progress=0)


def _update_step_status(session_id: str, step_key: str, step_status: str) -> None:
    """更新某步的状态并重算 progress。"""
    store = get_session_store()
    sess = store.get(session_id)
    if sess is None:
        return
    from fnixagent.harness.session import _utc_now

    steps = list(sess.steps)
    found = False
    for st in steps:
        if st.get("key") == step_key:
            st["status"] = step_status
            st["ts"] = _utc_now()
            found = True
            break
    if not found:
        steps.append({"key": step_key, "label": step_key, "status": step_status, "ts": _utc_now()})
    # 计算进度：completed 步数 / 总步数 * 100
    done_count = sum(1 for s in steps if s.get("status") == "completed")
    progress = int(done_count * 100 / max(len(_PIPELINE_STEPS), 1))
    store.update(session_id, steps=steps, progress=progress)


def enqueue_work_job(
    *,
    user_input: str,
    workspace: str,
    llm: dict[str, Any] | None = None,
    session_id: str | None = None,
    user_id: str = "desktop",
    priority: int = 10,
    app_state: Any = None,
) -> dict[str, Any]:
    """入队后台 Work；立即返回 session_id。"""
    sid = session_id or uuid.uuid4().hex[:16]
    store = get_session_store()
    title = (user_input[:48] or "后台任务").strip()
    existing = store.get(sid)
    if existing is None:
        store.create(
            session_id=sid,
            user_id=user_id,
            workspace=workspace,
            title=title,
            description=user_input,
            mode="work",
        )
    store.update(sid, status="pending", result="", priority=priority, error="", progress=0)

    item = ScheduleItem(
        task_type="work",
        payload={
            "user_input": user_input,
            "workspace": workspace,
            "session_id": sid,
            "user_id": user_id,
            "llm": llm,
        },
        priority=priority,
        dont_filter=True,
        timeout_seconds=3600.0,
        fingerprint=f"work:{sid}",
    )
    # 挂 app_state 引用（进程内）
    if app_state is not None:
        item.payload["_has_app_state"] = True

    q = get_priority_queue()
    ok = q.put(item)
    with _lock:
        # 暂存 app_state 供 worker 取用（按 session）
        if app_state is not None:
            _APP_STATES[sid] = app_state
    return {
        "ok": bool(ok),
        "session_id": sid,
        "task_id": item.task_id,
        "status": "pending" if ok else "rejected",
    }


_APP_STATES: dict[str, Any] = {}

# ── 事件类型 → step_key 映射（用于实时更新 steps）──
_EVENT_TYPE_TO_STEP: dict[str, str] = {
    "mission": "mission",
    "evolution": "evolution",
    "pipeline": "pipeline",
    "thought": "thought",
    "action": "action",
    "artifact": "artifact",
    "observation": "observation",
    "text": "text",
    "done": "done",
}


async def _run_one(item: ScheduleItem) -> bool:
    from fnixagent.services.work_pipeline import run_work_stream

    payload = item.payload or {}
    sid = str(payload.get("session_id") or "")
    store = get_session_store()
    store.update(sid, status="running", error="")
    _init_session_steps(sid)
    append_job_event(sid, {"type": "job", "data": {"status": "running", "task_id": item.task_id}})

    with _active_lock:
        _active_sessions.add(sid)
    app_state = _APP_STATES.get(sid)
    final_text = ""
    try:
        async for event in run_work_stream(
            user_input=str(payload.get("user_input") or ""),
            workspace=str(payload.get("workspace") or ""),
            llm=payload.get("llm"),
            session_id=sid,
            user_id=str(payload.get("user_id") or "desktop"),
            app_state=app_state,
        ):
            # 取消检查
            if is_cancelled(sid):
                append_job_event(sid, {"type": "job", "data": {"status": "cancelled"}})
                break
            append_job_event(sid, event)
            evt_type = str(event.get("type") or "")
            # 映射到 step
            step_key = _EVENT_TYPE_TO_STEP.get(evt_type)
            if step_key:
                _update_step_status(sid, step_key, "running")
                # 前一步标记 completed（除第一步外）
                idx = next((i for i, (k, _) in enumerate(_PIPELINE_STEPS) if k == step_key), -1)
                if idx > 0:
                    prev_key = _PIPELINE_STEPS[idx - 1][0]
                    _update_step_status(sid, prev_key, "completed")
            if evt_type == "text":
                final_text = str(event.get("data") or final_text)
            if evt_type == "done" and isinstance(event.get("data"), dict):
                final_text = str(event["data"].get("summary") or final_text)
                _update_step_status(sid, "done", "completed")
                store.update(sid, progress=100)
        # session 状态由 run_work_stream 更新；兜底
        sess = store.get(sid)
        if sess and sess.status == "running":
            store.update(sid, status="completed", result=final_text[:4000])
        append_job_event(sid, {"type": "job", "data": {"status": "completed"}})
        return True
    except Exception as e:
        logger.exception("work job failed %s", sid)
        store.update(sid, status="failed", error=str(e)[:2000], result=str(e)[:2000])
        append_job_event(sid, {"type": "error", "data": str(e)})
        return False
    finally:
        with _active_lock:
            _active_sessions.discard(sid)
        with _cancel_lock:
            _cancelled_sessions.discard(sid)
        _APP_STATES.pop(sid, None)


async def worker_loop() -> None:
    """多并发 worker：用 Semaphore 限制并发度，create_task 并行执行。"""
    q = get_priority_queue()
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_JOBS)
    pending_tasks: set[asyncio.Task] = set()
    logger.info("Work background worker started (max_concurrent=%d)", _MAX_CONCURRENT_JOBS)

    async def _execute(item: ScheduleItem) -> None:
        async with semaphore:
            q.mark_active(item)
            try:
                ok = await _run_one(item)
            except Exception:
                ok = False
            q.mark_done(item.task_id, success=ok)

    while not _stop.is_set():
        try:
            item = await asyncio.to_thread(q.get, 1.0)
        except RuntimeError:
            break
        if item is None:
            # 没有新任务时清理已完成的 task
            pending_tasks = {t for t in pending_tasks if not t.done()}
            continue
        if item.task_type != "work":
            q.mark_done(item.task_id, success=False)
            continue
        task = asyncio.create_task(_execute(item))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)
        # 短暂让出，避免忙等
        await asyncio.sleep(0.01)

    # 退出前等待所有 in-flight task 完成（最多 5 秒）
    if pending_tasks:
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending_tasks, return_exceptions=True), timeout=5.0
            )
        except TimeoutError:
            for t in pending_tasks:
                t.cancel()


def start_work_job_worker() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    _stop.clear()

    async def _boot() -> None:
        await worker_loop()

    try:
        loop = asyncio.get_running_loop()
        _worker_task = loop.create_task(_boot())
    except RuntimeError:
        # 无 running loop 时由 lifespan 负责
        pass


async def start_work_job_worker_async() -> None:
    global _worker_task
    if _worker_task is not None and not _worker_task.done():
        return
    _stop.clear()
    _worker_task = asyncio.create_task(worker_loop())


async def stop_work_job_worker_async() -> None:
    global _worker_task
    _stop.set()
    if _worker_task is not None:
        try:
            await asyncio.wait_for(_worker_task, timeout=2.0)
        except (TimeoutError, Exception):
            _worker_task.cancel()
        _worker_task = None
