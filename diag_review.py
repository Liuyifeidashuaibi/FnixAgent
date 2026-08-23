# -*- coding: utf-8 -*-
"""进程内复现 review 无 notes 问题: 直接用 CodingAgent.streaming_execute 跑同一任务, 逐事件打印 + 异常栈。"""
import asyncio
import sys
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, "E:/FNIX/FnixAgent/src")

WS = r"C:\Users\liuyi\.fnix\workspaces\bench\verify-fib"
TASK = "Create fib.py with a function fib(n) that returns the nth Fibonacci number, and a __main__ block that prints fib(10)."


async def main():
    from fnixagent.api.routers.chat_agent import get_server

    server = get_server(WS)
    server._ensure_initialized()
    agent = server._agent
    # 复刻 chat_agent 的 LLM 注入
    from fnixagent.services.llm_policy import resolve_llm_for_request
    from fnixagent.services.work_agent import adapter_from_llm_override

    llm_dict, llm_err = resolve_llm_for_request({}, is_admin=False)
    print("llm_dict:", {k: (v[:12] + "***" if k == "api_key" and v else v) for k, v in (llm_dict or {}).items()}, "err:", llm_err)
    if llm_dict is not None:
        from fnixagent.api.routers.chat_agent import _AdapterLLMBackend
        agent._llm = _AdapterLLMBackend(adapter_from_llm_override(llm_dict))
    agent._tools.preview_mode = False

    from fnixagent.core.code.agent import CodingTask

    task = CodingTask(description=TASK)
    async for ev in agent.streaming_execute(task):
        et = getattr(ev, "type", "")
        if et == "done":
            r = getattr(ev, "result", None)
            print(
                "[done] status=%s err=%r review_passed=%s notes=%r"
                % (
                    getattr(getattr(r, "status", None), "value", None),
                    getattr(r, "error", None),
                    getattr(r, "review_passed", None),
                    (getattr(r, "review_notes", None) or "")[:300],
                )
            )
        elif et == "review":
            print("[review] passed=%s notes=%r" % (ev.review_passed, (ev.review_notes or "")[:300]))
        elif et == "step":
            st = getattr(ev, "step", None) or {}
            print("[step]", st.get("action"), st.get("target"), st.get("status"))
        else:
            print("[%s]" % et, str(getattr(ev, "status", "") or getattr(ev, "steps", "") or "")[:120])


try:
    asyncio.run(main())
except Exception:
    traceback.print_exc()
