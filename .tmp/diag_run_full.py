# -*- coding: utf-8 -*-
"""进程内完整跑 CodingAgent.run, 定位 review failed 且无 notes 的根因"""
import asyncio, sys, os, json

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for k in ("DASHSCOPE_API_KEY","QWEN_API_KEY","OPENAI_API_KEY","GLM_API_KEY","DEEPSEEK_API_KEY","CUSTOM_API_KEY"):
    os.environ.pop(k, None)

from fnixagent.core.code.server import IDEServer
from fnixagent.core.code.agent import CodingTask

async def main():
    ws = r"C:\Users\liuyi\.fnix\workspaces\bench\web-bench\angular"
    server = IDEServer(project_root=ws)
    server._ensure_initialized()
    agent = server._agent
    agent._tools.preview_mode = False
    print("llm backend:", type(agent._llm).__name__)

    task = CodingTask(
        id="diag1",
        description=("Create components/header/header.component.ts that displays a header "
                     "with the title 'My Blog'. The header should have a height of 60px "
                     "and a gray background color."),
    )
    # plan
    steps = await agent._plan(task)
    print("PLAN steps:")
    for s in steps:
        print("  -", s.action, s.target, "| desc head:", (s.description or "")[:80].replace("\n", " "))
    # execute
    for s in steps:
        try:
            await agent._execute_step(s, task)
        except Exception as e:
            print("  EXEC EXC:", s.action, type(e).__name__, str(e)[:200])
        print("  step", s.action, s.target, "->", s.status, (s.error or "")[:120])
    # review
    passed, notes = await agent._review(task, steps)
    print("REVIEW passed:", passed)
    print("REVIEW notes:", repr(notes))
    print("last_llm_error:", agent._last_llm_error)

asyncio.run(main())
