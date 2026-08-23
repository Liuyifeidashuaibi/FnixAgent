import asyncio
import time

from fnixagent.core.llm.adapter import LLMAdapter


async def probe():
    a = LLMAdapter()
    for model in ("qwen-turbo", "qwen-plus", "qwen-max", "qwen3.7-max-2026-05-20"):
        t0 = time.time()
        try:
            r = await a.chat(messages=[{"role": "user", "content": "OK"}], model=model)
            print(f"ALIVE {model} {time.time()-t0:.1f}s tokens={r.get('usage',{}).get('total_tokens')}")
        except Exception as e:
            print(f"DEAD {model}: {str(e)[:80]}")


asyncio.run(probe())
