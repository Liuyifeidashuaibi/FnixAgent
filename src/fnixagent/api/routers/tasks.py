"""
API 路由 - 任务管理接口。

接入真实 TaskStore(任务生命周期管理),替换之前的 Mock 实现。

任务生命周期:
  pending → running → succeeded/failed
                 ↘ cancelled

支持操作:
  - 创建任务
  - 查询任务/状态/步骤
  - 取消/重试任务
  - 列表查询
"""

from fastapi import APIRouter, HTTPException

from fnixagent.api.schemas.models import (
    BaseResponse,
    TaskCreate,
    TaskResponse,
    TaskStatus,
)
from fnixagent.services.storage import get_task_store

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _task_to_response(task) -> TaskResponse:
    """StoredTask → TaskResponse。"""
    return TaskResponse(
        id=task.id,
        session_id=task.session_id,
        intent=task.intent,
        reasoning_mode=task.reasoning_mode,
        status=task.status,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
    )


def _coerce_task_id(task_id) -> int:
    """将路径参数 task_id 转换为 int,非法值抛 404(而非 Pydantic 默认 422)。

    这样 /tasks/abc 返回 404(资源不存在),符合 REST 语义,
    也避免前端因 422 误判为参数校验错误。
    """
    try:
        return int(task_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")


def _get_task_or_404(task_id):
    """按 ID 取任务,失败抛 404。接受 str/int 输入。"""
    tid = _coerce_task_id(task_id)
    task = get_task_store().get(tid)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {tid} 不存在")
    return task


@router.post("/", response_model=TaskResponse)
async def create_task(request: TaskCreate):
    """
    创建任务。

    - 在 TaskStore 中创建 pending 状态的任务记录
    - 后续可由调度器拉起执行,或通过 /retry 重试
    """
    store = get_task_store()
    task = store.create(
        session_id=request.session_id,
        intent=request.intent,
        reasoning_mode=request.reasoning_mode,
    )
    return _task_to_response(task)


@router.post("/create", response_model=TaskResponse)
async def create_task_alt(request: TaskCreate):
    """创建任务(别名路由,便于不带尾斜杠的客户端调用)。"""
    return await create_task(request)


@router.get("/list")
async def list_tasks(
    user_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
):
    """查询任务列表(支持按用户/状态过滤)。"""
    # 服务层已对 limit 做 [1, MAX_LIST_LIMIT] 钳制,这里再防御性校验
    if limit < 1:
        limit = 50
    store = get_task_store()
    tasks = store.list(user_id=user_id, status=status, limit=limit)
    return [_task_to_response(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """获取任务信息。"""
    return _task_to_response(_get_task_or_404(task_id))


@router.get("/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    获取任务状态。

    返回: status / progress(0.0-1.0) / current_step / total_steps
    """
    task_id = _coerce_task_id(task_id)
    _get_task_or_404(task_id)  # 确保 task 存在
    status_info = get_task_store().get_status(task_id)
    if not status_info:
        raise HTTPException(status_code=404, detail="任务状态不可用")
    return TaskStatus(**status_info)


@router.get("/{task_id}/steps")
async def get_task_steps(task_id: str):
    """获取任务执行步骤列表。"""
    task_id = _coerce_task_id(task_id)
    task = _get_task_or_404(task_id)
    return [
        {
            "step_no": s.step_no,
            "description": s.description,
            "tool_name": s.tool_name,
            "status": s.status,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "finished_at": s.finished_at.isoformat() if s.finished_at else None,
            "result": s.result,
            "error": s.error,
        }
        for s in task.steps
    ]


@router.post("/{task_id}/steps")
async def add_task_step(
    task_id: str,
    description: str,
    tool_name: str = "",
):
    """为任务添加一个执行步骤。"""
    task_id = _coerce_task_id(task_id)
    _get_task_or_404(task_id)
    step = get_task_store().add_step(task_id, description, tool_name)
    if not step:
        raise HTTPException(status_code=500, detail="添加步骤失败")
    return {
        "step_no": step.step_no,
        "description": step.description,
        "tool_name": step.tool_name,
        "status": step.status,
    }


@router.post("/{task_id}/start", response_model=TaskResponse)
async def start_task(task_id: str):
    """启动任务(标记为 running)。"""
    task_id = _coerce_task_id(task_id)
    task = _get_task_or_404(task_id)
    if task.status not in ("pending",):
        raise HTTPException(
            status_code=409,
            detail=f"任务当前状态为 {task.status},无法启动(仅 pending 可启动)",
        )
    started = get_task_store().start(task_id)
    return _task_to_response(started)


@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(task_id: str, result: dict | None = None):
    """标记任务成功完成。"""
    task_id = _coerce_task_id(task_id)
    _get_task_or_404(task_id)
    completed = get_task_store().complete(task_id, result=result)
    return _task_to_response(completed)


@router.post("/{task_id}/fail", response_model=TaskResponse)
async def fail_task(task_id: str, error: str):
    """标记任务失败。"""
    task_id = _coerce_task_id(task_id)
    _get_task_or_404(task_id)
    failed = get_task_store().fail(task_id, error=error)
    return _task_to_response(failed)


@router.post("/{task_id}/cancel", response_model=BaseResponse)
async def cancel_task(task_id: str):
    """
    取消任务。

    - 只能取消未完成的任务(pending/running)
    - 已完成的任务(succeeded/failed/cancelled)无法取消
    """
    task_id = _coerce_task_id(task_id)
    _get_task_or_404(task_id)
    cancelled = get_task_store().cancel(task_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail="任务已完成,无法取消",
        )
    return BaseResponse(success=True, message=f"任务 {task_id} 已取消")


@router.post("/{task_id}/retry", response_model=TaskResponse)
async def retry_task(task_id: str):
    """
    重试任务。

    - 重置任务状态为 pending,清空步骤状态
    - 后续可由调度器重新拉起执行
    """
    task_id = _coerce_task_id(task_id)
    _get_task_or_404(task_id)
    retried = get_task_store().retry(task_id)
    return _task_to_response(retried)
