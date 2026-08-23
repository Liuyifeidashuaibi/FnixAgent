# FnixAgent 后端代码审查报告

**审查范围**: `src/fnixagent/` 全部后端源码
**审查日期**: 2026-08-21
**审查重点**: 已确认 Bug、API 健壮性、性能优化、安全性

---

## 1. 已确认的 Bug

### Bug 1.1: SSE step 计数 "Step 1/N" 不更新

**文件**: `src/fnixagent/api/routers/work.py:266-267`
**关联文件**: `src/fnixagent/core/agent/loop.py:788-795`, `src/fnixagent/services/work_pipeline.py:1375-1469`

**问题描述**: SSE 流式响应中 step 计数始终显示 "Step 1/25"，不随 AgenticLoop 实际执行步骤更新。

**根因分析**:

AgenticLoop 在 `loop.py:788-795` 正确发射 `step_start` 事件：

```python
yield {
    "type": "step_start",
    "data": {
        "step": step_idx + 1,
        "total": self.max_steps,
        "description": f"Step {step_idx + 1}/{self.max_steps}",
    },
}
```

事件经过 `work_loop_source` → `RunEngine._normalize` → `step6_run_agent_stream` → `run_work_stream` 的 `else: yield event`（`work_pipeline.py:1468`）→ `work.py` 的 `else` 分支（`work.py:267`），最终输出为：

```json
{"chunk_type": "step_start", "content": {"step": 1, "total": 30, ...}, "done": false}
```

**后端事件链路本身是完整的**，但存在一个关键缺陷：`work.py:267` 的 `else` 分支将 `step_start` 事件作为**未识别事件类型**透传，`chunk_type` 为原始的 `"step_start"`，而非前端可能期望的标准化进度事件类型。如果前端只监听特定 `chunk_type`（如 `"step"` 或 `"progress"`），则 `step_start` 事件会被忽略。

此外，`work_jobs.py:266-276` 的 `_EVENT_TYPE_TO_STEP` 映射表**未包含 `step_start` 和 `step_end` 事件类型**，导致后台任务队列的 9 步流水线进度跟踪器也无法感知 AgenticLoop 内部步骤变化。

**修复建议**:

在 `work.py` 中为 `step_start` / `step_end` 添加显式处理，将其映射为标准化的 `progress` chunk 类型：

```diff
--- a/src/fnixagent/api/routers/work.py
+++ b/src/fnixagent/api/routers/work.py
@@ -263,6 +263,14 @@ async def work_stream(body: WorkStreamRequest, request: Request):
                 elif et == "error":
                     yield _ndjson("error", str(data), True, trace_id)
+                elif et == "step_start" and isinstance(data, dict):
+                    yield _ndjson("progress", {
+                        "step": data.get("step", 1),
+                        "total": data.get("total", 1),
+                        "description": data.get("description", ""),
+                        "status": "running",
+                    }, False, trace_id)
+                elif et == "step_end" and isinstance(data, dict):
+                    yield _ndjson("progress", {
+                        "step": data.get("step", 1),
+                        "total": data.get("total", 1),
+                        "description": data.get("description", ""),
+                        "status": "completed",
+                    }, False, trace_id)
                 else:
                     yield _ndjson(et or "event", data, False, trace_id)
```

同时在 `work_jobs.py` 的 `_EVENT_TYPE_TO_STEP` 中补充映射：

```diff
--- a/src/fnixagent/harness/work_jobs.py
+++ b/src/fnixagent/harness/work_jobs.py
@@ -266,6 +266,8 @@ _APP_STATES: dict[str, Any] = {}
 _EVENT_TYPE_TO_STEP: dict[str, str] = {
     "mission": "mission",
     "evolution": "evolution",
     "pipeline": "pipeline",
+    "step_start": "thought",
+    "step_end": "thought",
     "thought": "thought",
     "action": "action",
     "artifact": "artifact",
```

---

### Bug 1.2: 执行过程中所有操作时间显示 "0s"

**文件**: `src/fnixagent/core/agent/loop.py:788-795` (step_start), `loop.py:968-975` / `loop.py:1003-1010` (step_end)
**关联文件**: `src/fnixagent/harness/work_jobs.py:169-202`

**问题描述**: 前端显示每个步骤的执行时间始终为 "0s"。

**根因分析**:

AgenticLoop 在 `loop.py:784` 记录了 `step_start = time.time()`，并在 `loop.py:1061` 和 `loop.py:1073` 正确计算了 `duration_ms`，但这些时长数据**仅包含在 `observation` 事件中**（工具调用结果），未包含在 `step_start` 和 `step_end` 事件中：

```python
# loop.py:788-795 — step_start 事件，无 started_at / timestamp
yield {
    "type": "step_start",
    "data": {
        "step": step_idx + 1,
        "total": self.max_steps,
        "description": f"Step {step_idx + 1}/{self.max_steps}",
        # 缺少: "started_at": step_start  或  "ts": time.time()
    },
}

# loop.py:968-975 — step_end 事件，无 duration_ms
yield {
    "type": "step_end",
    "data": {
        "step": step_idx + 1,
        "total": self.max_steps,
        "description": f"Step {step_idx + 1}/{self.max_steps} (done)",
        # 缺少: "duration_ms": (time.time() - step_start) * 1000
    },
}
```

同时，`work_jobs.py:174-177` 中所有 9 个流水线步骤初始化时使用同一个 `_utc_now()` 时间戳：

```python
steps = [
    {"key": k, "label": label, "status": "pending", "ts": _utc_now()}
    for k, label in _PIPELINE_STEPS
]
```

`_update_step_status`（`work_jobs.py:181-202`）在更新步骤状态时更新 `ts`，但**不记录 `started_at`，也不计算 `duration`**。前端只能通过相邻步骤的 `ts` 差值推算时长，但由于步骤初始化时全部使用同一时间戳，且某些步骤可能被跳过，推算结果可能为 0。

**修复建议**:

1. 在 `step_end` 事件中注入 `duration_ms`：

```diff
--- a/src/fnixagent/core/agent/loop.py
+++ b/src/fnixagent/core/agent/loop.py
@@ -786,6 +786,7 @@ yield {
                 "type": "step_start",
                 "data": {
                     "step": step_idx + 1,
                     "total": self.max_steps,
                     "description": f"Step {step_idx + 1}/{self.max_steps}",
+                    "started_at": step_start,
                 },
             }
@@ -966,6 +967,7 @@ yield {
                     "type": "step_end",
                     "data": {
                         "step": step_idx + 1,
                         "total": self.max_steps,
                         "description": f"Step {step_idx + 1}/{self.max_steps} (done)",
+                        "duration_ms": round((time.time() - step_start) * 1000, 1),
                     },
                 }
```

对 `loop.py` 中所有 4 处 `step_end` 事件（行 905-912, 968-975, 1003-1010, 以及 error 分支）统一添加 `duration_ms` 字段。

2. 在 `work_jobs.py` 的 session steps 中增加 `started_at` 和 `duration_ms` 字段：

```diff
--- a/src/fnixagent/harness/work_jobs.py
+++ b/src/fnixagent/harness/work_jobs.py
@@ -181,12 +181,18 @@ def _update_step_status(session_id: str, step_key: str, step_status: str) -> Non
     for st in steps:
         if st.get("key") == step_key:
+            now = _utc_now()
+            if step_status == "running" and not st.get("started_at"):
+                st["started_at"] = now
+            elif step_status == "completed" and st.get("started_at"):
+                from datetime import datetime, UTC
+                start = datetime.fromisoformat(st["started_at"])
+                end = datetime.fromisoformat(now)
+                st["duration_ms"] = round((end - start).total_seconds() * 1000, 1)
             st["status"] = step_status
-            st["ts"] = _utc_now()
+            st["ts"] = now
             found = True
             break
```

---

### Bug 1.3: LLM 模型自我认知错误（报告为 Qwen 而非 kimi-k2.5）

**文件**: `src/fnixagent/services/work_agent.py:33-54` (系统提示词), `work_agent.py:1021,1037,1081` (提示词组装)
**关联文件**: `src/fnixagent/core/llm/adapter.py:297-298` (模型名传递), `src/fnixagent/services/llm_policy.py` (模型名归一化)

**问题描述**: 当用户配置使用 kimi-k2.5 模型时，LLM 自我认知为 Qwen。

**根因分析**:

`WORK_SYSTEM_PROMPT`（`work_agent.py:33-54`）硬编码为：

```python
WORK_SYSTEM_PROMPT = """你是 FnixAgent 办公工作台助手（对齐行业最佳实践 + Work 内的 Code 能力）。
...
你当前的工作目录是: {workspace_root}
"""
```

系统提示词组装链路（`work_agent.py:988-1081`）：

```python
system_prompt = WORK_SYSTEM_PROMPT                    # line 988: 基础提示词
system_prompt = WORK_SYSTEM_PROMPT + _format_ktg_context(ktg_paths)  # line 1021: + KTG 上下文
if prompt_extra:
    system_prompt = system_prompt + prompt_extra      # line 1037: + 额外提示
# line 1081: 传入 AgenticLoop
loop = AgenticLoop(..., system_prompt=system_prompt, ...)
```

**整个链路中没有任何位置注入实际使用的模型名。** 模型名仅通过 `LLMAdapter` → `LLMRequest.model` → `OpenAICompatibleProvider._do_chat` 的 `payload["model"]` 字段传递给 LLM API（`adapter.py:298`, `openai.py:124`），但 LLM 不会从 API 请求的 `model` 字段中读取自己的身份——它依赖系统提示词中的自我认知声明。

当用户通过 BYOK 配置 `provider=custom, model=kimi-k2.5, base_url=https://api.moonshot.cn/v1/` 时：

- `adapter_from_llm_override`（`work_agent.py:359-387`）正确构建了 `LLMAdapter(model_name="kimi-k2.5")`
- API 请求的 `model` 字段正确为 `"kimi-k2.5"`
- 但系统提示词仍为 "你是 FnixAgent 办公工作台助手"，**未告知 LLM 它是 kimi-k2.5**
- 如果该模型基于 Qwen 微调，或 base_url 实际指向 DashScope 兼容端点，模型会默认报告为 Qwen

此外，`llm_policy.py` 的 `normalize_llm_model()` 仅处理 DashScope 别名重写（如 `qwen3.7-plus` → `qwen-plus`），**不处理 kimi/moonshot 等非 DashScope 模型名**，不会造成名称篡改但也不会注入自我认知。

**修复建议**:

在 `build_work_agent_loop` 中，从 adapter 提取模型名并注入系统提示词：

```diff
--- a/src/fnixagent/services/work_agent.py
+++ b/src/fnixagent/services/work_agent.py
@@ -1036,9 +1036,18 @@ def build_work_agent_loop(
         if prompt_extra:
             system_prompt = system_prompt + prompt_extra

         adapter = adapter_from_llm_override(llm)
+
+        # 注入模型自我认知：告知 LLM 它实际使用的模型名，避免误报为其他模型
+        _model_name = ""
+        if adapter and adapter.is_configured:
+            _model_name = adapter._model_name or ""
+        if not _model_name and llm and llm.get("model"):
+            _model_name = str(llm["model"])
+        if _model_name:
+            system_prompt = (
+                f"你当前由模型 {_model_name} 驱动。当被问及你的模型身份时，"
+                f"请如实回答你是由 {_model_name} 驱动的 FnixAgent 助手。\n"
+                + system_prompt
+            )
+
         temperature = 0.7
```

---

## 2. API 健壮性

### 2.1: 输入验证不充分

**文件**: `src/fnixagent/api/routers/work.py:48-59`

**问题描述**: `WorkStreamRequest` 的多个字段缺乏充分验证。

**根因分析**:

```python
class WorkStreamRequest(BaseModel):
    user_input: str = Field(..., min_length=1, max_length=20000)  # 有验证
    workspace: str | None = None          # 无验证：可为任意路径
    session_id: str | None = None         # 无验证：可为任意字符串
    work_mode: str | None = Field(default="craft", max_length=16)  # 无枚举校验
    disabled_skills: list[str] | None = Field(default=None, max_length=64)  # max_length 限制列表长度非字符串
```

- `workspace` 未验证是否为合法路径，可传入 `../../etc` 等路径遍历字符串（虽然 `_safe_path` 会拦截，但应在入口层就拒绝）
- `work_mode` 只限制长度，不限制取值——传入 `"exploit"` 不会报错，而是走默认 `craft` 逻辑
- `disabled_skills` 的 `max_length=64` 限制的是列表元素数量，不是字符串长度

**修复建议**:

```diff
--- a/src/fnixagent/api/routers/work.py
+++ b/src/fnixagent/api/routers/work.py
@@ -13,6 +13,7 @@
 from typing import Any

 from fastapi import APIRouter, HTTPException, Request
+from pydantic import field_validator
 from fastapi.responses import StreamingResponse
 from pydantic import BaseModel, Field
@@ -51,9 +52,16 @@ class WorkStreamRequest(BaseModel):
     user_input: str = Field(..., min_length=1, max_length=20000)
     workspace: str | None = None
     session_id: str | None = None
     llm: LlmOverride | None = None
     user_id: str | None = None
-    work_mode: str | None = Field(default="craft", max_length=16)
+    work_mode: str | None = Field(default="craft")
     disabled_skills: list[str] | None = Field(default=None, max_length=64)
+
+    @field_validator("work_mode")
+    @classmethod
+    def _validate_work_mode(cls, v: str | None) -> str | None:
+        if v is None:
+            return "craft"
+        v = v.strip().lower()
+        if v not in ("ask", "plan", "craft"):
+            raise ValueError(f"work_mode must be one of: ask, plan, craft; got: {v}")
+        return v
+
+    @field_validator("workspace")
+    @classmethod
+    def _validate_workspace(cls, v: str | None) -> str | None:
+        if v is None:
+            return None
+        # 拒绝路径遍历
+        if ".." in v or v.startswith("/"):
+            raise ValueError("workspace must be a relative path without parent traversal")
+        return v
```

### 2.2: SSE 流式响应缺少超时和异常恢复

**文件**: `src/fnixagent/api/routers/work.py:112-272`

**问题描述**: SSE 生成器无超时机制，客户端断连后服务端可能继续执行。

**根因分析**:

```python
@router.post("/stream")
async def work_stream(body: WorkStreamRequest, request: Request):
    async def generate():
        ...
        async for event in run_work_stream(...):
            ...
            yield _ndjson(...)
    return StreamingResponse(generate(), media_type="application/x-ndjson")
```

- 无全局超时：如果 LLM 调用挂起，SSE 流会无限等待
- 未检查 `request.is_disconnected()`：客户端关闭连接后，服务端仍在执行流水线
- 无断点续传：SSE 中断后无法从上次位置恢复（虽然 `resume_from` 机制存在于 pipeline 中，但未通过 API 暴露）

**修复建议**:

```diff
--- a/src/fnixagent/api/routers/work.py
+++ b/src/fnixagent/api/routers/work.py
@@ -169,6 +169,12 @@ async def work_stream(body: WorkStreamRequest, request: Request):
         try:
             async for event in run_work_stream(
+                timeout=300,  # 5 分钟总超时
                 ...
             ):
+                # 检测客户端是否已断开
+                if await request.is_disconnected():
+                    _logger.info("SSE client disconnected, stopping stream")
+                    break
                 et = event.get("type", "")
                 ...
```

### 2.3: 并发请求处理——SessionStore 同步锁阻塞事件循环

**文件**: `src/fnixagent/harness/session.py:86,115-122`

**问题描述**: `SessionStore` 使用 `threading.Lock` 保护 JSON 文件写入，在 async 上下文中调用会阻塞事件循环。

**根因分析**:

```python
class SessionStore:
    def __init__(self, ...):
        self._lock = threading.Lock()          # 线程锁

    def save(self, session: WorkSession) -> None:
        session.updated_at = _utc_now()
        path = self._path(session.id)
        tmp = str(path) + ".tmp"
        with self._lock:                       # 阻塞 event loop
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
```

`save()` 和 `update()` 在 `work_jobs.py:285` 等 async 上下文中被同步调用。当并发任务数增加时，`threading.Lock` 会阻塞 asyncio 事件循环，导致所有协程（包括 SSE 心跳）被挂起。

**修复建议**:

将文件 I/O 操作改为 `asyncio.to_thread`：

```diff
--- a/src/fnixagent/harness/session.py
+++ b/src/fnixagent/harness/session.py
@@ -115,12 +115,16 @@ def save(self, session: WorkSession) -> None:
         session.updated_at = _utc_now()
         path = self._path(session.id)
         tmp = str(path) + ".tmp"
-        with self._lock:
-            with open(tmp, "w", encoding="utf-8") as f:
-                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
-            os.replace(tmp, path)
+        self._save_sync(session, path, tmp)
+
+    def _save_sync(self, session, path, tmp):
+        with self._lock:
+            with open(tmp, "w", encoding="utf-8") as f:
+                json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
+            os.replace(tmp, path)
+
+    async def asave(self, session: WorkSession) -> None:
+        """Async 版本：将同步 I/O 卸载到线程池。"""
+        session.updated_at = _utc_now()
+        path = self._path(session.id)
+        tmp = str(path) + ".tmp"
+        await asyncio.to_thread(self._save_sync, session, path, tmp)
```

---

## 3. 性能优化点

### 3.1: SessionStore.list_sessions() 全量扫描性能瓶颈

**文件**: `src/fnixagent/harness/session.py:178-220`

**问题描述**: `list_sessions()` 扫描全部 JSON 文件并逐一反序列化，O(n) 复杂度。

**根因分析**:

```python
def list_sessions(self, *, user_id=None, workspace=None, status=None, limit=50):
    files = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files:
        with open(path, encoding="utf-8") as f:      # 逐文件读取
            data = json.load(f)                      # 逐文件反序列化
        session = WorkSession.from_dict(data)
        if user_id and session.user_id != user_id:   # 内存中过滤
            continue
        ...
```

当 session 文件超过 200 个（`compact_old_sessions` 默认保留 200），每次列表请求需读取并反序列化全部 200 个 JSON 文件。

**修复建议**:

维护一个内存索引（session_id → metadata），仅在 session 变更时更新索引：

```python
class SessionStore:
    def __init__(self, ...):
        self._index: dict[str, dict] = {}  # sid -> {user_id, workspace, status, mtime}
        self._rebuild_index()

    def _rebuild_index(self):
        """启动时扫描一次，构建轻量索引。"""
        for path in self._dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                self._index[data["id"]] = {
                    "user_id": data.get("user_id"),
                    "workspace": data.get("workspace"),
                    "status": data.get("status"),
                    "mtime": path.stat().st_mtime,
                }
            except Exception:
                continue

    def list_sessions(self, *, user_id=None, workspace=None, status=None, limit=50):
        # 从索引中过滤，仅读取匹配的文件
        candidates = [
            (sid, meta) for sid, meta in self._index.items()
            if (not user_id or meta["user_id"] == user_id)
            and (not workspace or meta["workspace"] == workspace)
            and (not status or meta["status"] == status)
        ]
        candidates.sort(key=lambda x: x[1]["mtime"], reverse=True)
        # 仅反序列化前 limit 个
        for sid, _ in candidates[:limit]:
            session = self.get(sid)
            if session:
                yield session
```

### 3.2: LLM 调用链路——同步 httpx 阻塞与重试策略

**文件**: `src/fnixagent/core/llm/adapter.py:309`, `src/fnixagent/core/llm/providers/openai.py:103-159`

**问题描述**: LLM 调用通过 `asyncio.to_thread` 卸载，但 httpx 客户端未复用连接池。

**根因分析**:

```python
# adapter.py:309 — 正确卸载到线程
response: LLMResponse = await asyncio.to_thread(provider.chat, request)

# openai.py:96-100 — 每次调用创建新 httpx.Client
def _get_client(self):
    if self._client is None or self._client.is_closed:
        self._client = httpx.Client(timeout=self._timeout)
    return self._client
```

`_get_client` 有懒初始化缓存，但 `httpx.Client` 在同步线程中使用，与 asyncio 事件循环的并发模型不匹配。多个并发请求可能竞争同一个 `httpx.Client` 实例。

此外，重试策略（`openai.py:152`）仅对 5xx/429/网络错误重试，但**未实现指数退避**：

```python
for attempt in range(self._max_retries):
    try:
        resp = client.post(url, json=payload, headers=headers)
        ...
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        last_error = str(e)
        continue  # 立即重试，无退避
```

**修复建议**:

```diff
--- a/src/fnixagent/core/llm/providers/openai.py
+++ b/src/fnixagent/core/llm/providers/openai.py
@@ -150,6 +150,12 @@ def _do_chat(self, request: LLMRequest, messages: list[dict]) -> LLMResponse:
         last_error: str | None = None
         for attempt in range(self._max_retries):
             try:
+                if attempt > 0:
+                    import time as _time
+                    # 指数退避：1s, 2s, 4s...
+                    _time.sleep(min(2 ** (attempt - 1), 8))
                 resp = client.post(url, json=payload, headers=headers)
```

### 3.3: work_jobs.py 后台任务无内存泄漏保护

**文件**: `src/fnixagent/harness/work_jobs.py:263,334-339`

**问题描述**: `_APP_STATES` 全局字典在 worker 异常崩溃时可能泄漏。

**根因分析**:

```python
_APP_STATES: dict[str, Any] = {}  # 全局字典

async def _run_one(item: ScheduleItem) -> bool:
    ...
    try:
        ...
    except Exception as e:
        ...
        return False
    finally:
        with _active_lock:
            _active_sessions.discard(sid)
        ...
        _APP_STATES.pop(sid, None)  # 清理逻辑在 finally 中
```

清理逻辑在 `finally` 块中，正常情况下会执行。但如果 worker 被 `SIGKILL` 或 `asyncio.CancelledError` 在 `finally` 执行前中断，`_APP_STATES` 中的条目不会被清理。

此外，`_active_sessions: set[str]` 也在 `finally` 中清理，存在同样的风险。

**修复建议**:

添加定期清理机制：

```python
async def _cleanup_stale_states():
    """定期清理可能泄漏的 app_state 和 active_session。"""
    while not _stop.is_set():
        await asyncio.sleep(300)  # 每 5 分钟
        store = get_session_store()
        with _active_lock:
            stale = [sid for sid in _active_sessions
                     if store.get(sid) and store.get(sid).status in ("completed", "failed", "cancelled")]
            for sid in stale:
                _active_sessions.discard(sid)
                _APP_STATES.pop(sid, None)
```

---

## 4. 安全性

### 4.1: Capability Token 使用 `==` 比较——时序攻击风险

**文件**: `src/fnixagent/core/gateway/capability.py:116`

**问题描述**: Capability token 验证使用 `==` 字符串比较，存在时序攻击风险。

**根因分析**:

```python
def check_capability(scope: dict) -> bool:
    ...
    presented = extract_presented_token(scope)
    return bool(presented) and presented == expected  # 非恒定时间比较
```

Python 的 `==` 对字符串做逐字符比较，在第一个不匹配字符处短路返回。攻击者可通过测量响应时间逐字符推断 token 值。

对比 `sidecar_app.py` 中正确使用了 `hmac.compare_digest` 进行恒定时间比较。

**修复建议**:

```diff
--- a/src/fnixagent/core/gateway/capability.py
+++ b/src/fnixagent/core/gateway/capability.py
@@ -1,6 +1,7 @@
 from __future__ import annotations

+import hmac
 import os
 from typing import Any
@@ -113,6 +114,9 @@ def check_capability(scope: dict) -> bool:
     if path_is_public(path):
         return True
     presented = extract_presented_token(scope)
-    return bool(presented) and presented == expected
+    if not presented:
+        return False
+    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))
```

### 4.2: Sidecar `/v1/read` 端点路径遍历——workspace 参数未限制

**文件**: `src/fnixagent/local/sidecar_app.py:203-216`

**问题描述**: `/v1/read` 端点接受任意 `workspace` 参数，攻击者可传入 `/` 读取系统任意文件。

**根因分析**:

```python
@app.get("/v1/read")
async def read_file(
    workspace: str = Query(...),           # 无验证：可为 "/"
    path: str = Query(..., alias="path"),  # 可为 "/etc/passwd"
    ...
) -> dict[str, Any]:
    tools = WorkspaceTools(workspace)      # workspace_root = "/"
    result = tools.read_file(path, ...)    # _safe_path 检查 path 在 "/" 内——永远为 True
```

`_safe_path`（`workspace.py:114-127`）检查 `target.relative_to(root)`。当 `workspace_root` 为 `/` 时，**任何绝对路径都在 `/` 下**，路径遍历检查完全失效。

攻击示例：

```
GET /v1/read?workspace=/&path=/etc/shadow
GET /v1/read?workspace=C:&path=C:\Windows\System32\config\SAM
```

**修复建议**:

```diff
--- a/src/fnixagent/local/sidecar_app.py
+++ b/src/fnixagent/local/sidecar_app.py
@@ -203,9 +203,18 @@ async def read_file(
     workspace: str = Query(...),
     path: str = Query(..., alias="path"),
     offset: int = Query(default=0, ge=0),
     limit: int | None = Query(default=None, ge=1),
 ) -> dict[str, Any]:
+    # 安全校验：workspace 不可为根目录或系统目录
+    import os
+    _forbidden = {"/", "\\", "C:", "C:\\", "/etc", "/usr", "/var", "/root", "/home"}
+    ws_norm = os.path.normpath(workspace).rstrip("/\\")
+    if ws_norm in _forbidden or len(ws_norm) <= 2:
+        raise HTTPException(
+            status_code=403,
+            detail="workspace must be a specific project directory, not a system root",
+        )
+
     from fnixagent.core.tools.workspace import WorkspaceTools
     tools = WorkspaceTools(workspace)
     result = tools.read_file(path, offset=offset, limit=limit)
```

### 4.3: API Key 可能通过错误消息泄露

**文件**: `src/fnixagent/core/llm/adapter.py:250-257`, `src/fnixagent/core/llm/providers/openai.py:120`

**问题描述**: LLM 调用失败时，错误消息可能包含 API Key 或请求头信息。

**根因分析**:

```python
# adapter.py:250-257
if self._provider is None:
    raise LLMError(
        "未配置 LLM API Key。请在 .env 文件中设置以下任一环境变量:\n"
        "  OPENAI_API_KEY=sk-xxx\n"        # 示例中包含 sk- 前缀格式
        ...
    )
```

虽然错误消息中没有实际 Key 值，但 `openai.py:155` 的 `client.post()` 在某些 httpx 异常中可能将完整 URL（含 base_url）暴露在异常字符串中。如果 base_url 包含 API Key（如某些 provider 的 URL 格式为 `https://api.example.com/v1/?key=sk-xxx`），Key 会通过异常链传递到 SSE 错误事件。

此外，`work.py:270` 的异常处理直接将异常字符串发送给客户端：

```python
except Exception as e:
    yield _ndjson("error", str(e), True, trace_id)  # 可能泄露内部信息
```

**修复建议**:

```diff
--- a/src/fnixagent/api/routers/work.py
+++ b/src/fnixagent/api/routers/work.py
@@ -267,7 +267,13 @@ async def work_stream(body: WorkStreamRequest, request: Request):
                     yield _ndjson(et or "event", data, False, trace_id)

         except Exception as e:
-            yield _ndjson("error", str(e), True, trace_id)
+            # 避免内部异常消息泄露到客户端
+            _safe_msg = str(e)
+            # 过滤可能包含密钥的模式
+            import re
+            _safe_msg = re.sub(r'(sk-[A-Za-z0-9]{20,})', '[REDACTED]', _safe_msg)
+            _safe_msg = re.sub(r'(Bearer\s+[\w\-\.]+)', 'Bearer [REDACTED]', _safe_msg)
+            _logger.exception("SSE stream error")  # 服务端记录完整异常
+            yield _ndjson("error", _safe_msg, True, trace_id)
```

### 4.4: `run_command` 工具危险命令黑名单可绕过

**文件**: `src/fnixagent/core/tools/workspace.py:44-111`

**问题描述**: 危险命令检测使用子串匹配，可被编码/引号/变量替换绕过。

**根因分析**:

```python
_DANGEROUS_COMMANDS = [
    "rm -rf /",
    "rm -rf/*",
    ...
]

def _is_dangerous_command(cmd: str) -> bool:
    cmd_lower = cmd.lower().strip()
    for danger in _DANGEROUS_COMMANDS:
        if danger in cmd_lower:  # 子串匹配
            return True
    return False
```

绕过方式示例：

- `rm -rf /` → `rm -rf  /`（多空格）不匹配 `"rm -rf /"`
- `rm -rf /` → `rm -rf ${HOME}` 变量替换
- `rm -rf /` → `r""m -rf /` 引号拼接
- `rm -rf /` → `rm -rf /tmp/../../` 路径等价
- PowerShell：`Remove-Item -Recurse -Force C:\` 不在黑名单中

**修复建议**:

采用更严格的命令解析+正则模式：

```diff
--- a/src/fnixagent/core/tools/workspace.py
+++ b/src/fnixagent/core/tools/workspace.py
@@ -99,6 +99,18 @@ def _is_dangerous_command(cmd: str) -> bool:
     """检查是否为危险命令"""
     cmd_lower = cmd.lower().strip()
+    # 规范化：移除多余空格
+    import re
+    cmd_normalized = re.sub(r'\s+', ' ', cmd_lower)
     for danger in _DANGEROUS_COMMANDS:
-        if danger in cmd_lower:
+        if danger in cmd_normalized:
             return True
+    # 正则模式：匹配 rm -rf 根目录的各种变体
+    _DANGER_PATTERNS = [
+        r'rm\s+(-[a-z]*r[a-z]*\s+)?(-[a-z]*f[a-z]*\s+)?(/\s*$|/\s*[;|&]|/\*|\$|~|/home|/users|/etc)',
+        r'remove-item\s+.*-recurse.*-force',
+        r'del\s+/[fs].*\.',
+        r'mkfs\.',
+        r'dd\s+if=.*of=/dev/',
+        r':\(\)\s*\{.*\};:',
+    ]
+    for pattern in _DANGER_PATTERNS:
+        if re.search(pattern, cmd_normalized):
+            return True
     import re
```

---

## 5. 其他发现

### 5.1: `done` 事件在 `run_work_stream` 中被静默丢弃

**文件**: `src/fnixagent/services/work_pipeline.py:1428-1429`

**问题描述**: AgenticLoop 发射的 `done` 事件（包含 `duration_ms` 和 `steps` 统计）被 `continue` 跳过，未传递到 SSE。

```python
elif et == "done":
    continue  # AgenticLoop 的 done 事件被丢弃
```

`run_work_stream` 在末尾生成自己的 `done` 事件（约行 1700+），但**丢失了 AgenticLoop 的原始 `duration_ms` 数据**。这导致前端无法获取精确的 Agent 执行时长。

### 5.2: `SessionStore._path()` 路径净化不完整

**文件**: `src/fnixagent/harness/session.py:88-90`

```python
def _path(self, session_id: str) -> Path:
    safe = session_id.replace("/", "_").replace("\\", "_")
    return self._dir / f"{safe}.json"
```

仅替换 `/` 和 `\\`，未处理 `..`、空字节 `\x00`、Windows 保留名（`CON`、`PRN`、`AUX`）等。攻击者传入 `session_id="..\\..\\..\\etc\\passwd\x00"` 可能导致意外行为。

**修复建议**: 使用 UUID 或正则白名单校验 `session_id` 格式：

```python
def _path(self, session_id: str) -> Path:
    import re
    if not re.match(r'^[a-f0-9]{8,32}$', session_id):
        raise ValueError(f"Invalid session_id: {session_id}")
    return self._dir / f"{session_id}.json"
```

### 5.3: OpenAICompatibleProvider 同步 httpx.Client 未关闭

**文件**: `src/fnixagent/core/llm/providers/openai.py:96-100`

```python
def _get_client(self):
    if self._client is None or self._client.is_closed:
        self._client = httpx.Client(timeout=self._timeout)
    return self._client
```

`httpx.Client` 持有连接池，但 `OpenAICompatibleProvider` 没有实现 `close()` 或 `__del__` 方法。在长生命周期进程中（如 FastAPI 服务），如果 provider 被替换或重建，旧 client 的连接池不会被释放。

---

## 总结

| 类别       | 严重度 | 数量 | 关键项                                         |
| ---------- | ------ | ---- | ---------------------------------------------- |
| 已确认 Bug | P0     | 3    | step 计数不更新、时间显示 0s、模型自我认知错误 |
| API 健壮性 | P1-P2  | 3    | 输入验证、SSE 恢复、并发锁阻塞                 |
| 性能优化   | P2-P3  | 3    | session 全量扫描、LLM 连接池重试、内存泄漏保护 |
| 安全性     | P0-P1  | 4    | 时序攻击、路径遍历、API Key 泄露、命令绕过     |
| 其他       | P2-P3  | 3    | done 事件丢弃、路径净化、连接池泄漏            |

**优先修复顺序**:

1. **P0 安全**: capability.py 时序攻击 (4.1) + sidecar 路径遍历 (4.2)
2. **P0 Bug**: 模型自我认知 (1.3) + 时间显示 0s (1.2)
3. **P1 健壮性**: SessionStore 锁阻塞 (2.3) + API Key 泄露 (4.3)
4. **P2 性能**: session 索引 (3.1) + LLM 重试退避 (3.2)
