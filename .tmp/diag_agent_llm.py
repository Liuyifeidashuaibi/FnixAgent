# -*- coding: utf-8 -*-
"""进程内诊断 CodingAgent 的 LLM 链路"""
import asyncio, sys, os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for k in ("DASHSCOPE_API_KEY","QWEN_API_KEY","OPENAI_API_KEY","GLM_API_KEY","DEEPSEEK_API_KEY","CUSTOM_API_KEY"):
    os.environ.pop(k, None)

from fnixagent.core.code.server import IDEServer

async def main():
    ws = r"C:\Users\liuyi\.fnix\workspaces\bench\web-bench\angular"
    server = IDEServer(project_root=ws)
    server._ensure_initialized()
    agent = server._agent
    print("llm backend type:", type(agent._llm).__name__)
    # 直接探测 complete
    try:
        resp = await agent._llm.complete({"messages": [{"role": "user", "content": "只回复 OK"}]})
        print("complete ->", repr(resp[:200]))
    except Exception as e:
        print("complete EXCEPTION:", type(e).__name__, str(e)[:300])

asyncio.run(main())
