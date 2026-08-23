import asyncio
import time

from fnixagent.core.llm.adapter import LLMAdapter


async def probe():
    a = LLMAdapter()
    for model in ("qwen3.7-max-2026-05-20",):
        t0 = time.time()
        try:
            r = await a.chat(
                messages=[{"role": "user", "content": "回复OK两个字"}], model=model
            )
            usage = r.get("usage", {}).get("total_tokens")
            print(f"{model}: OK {time.time()-t0:.1f}s tokens={usage}")
        except Exception as e:
            print(f"{model}: FAIL {str(e)[:200]}")


asyncio.run(probe())
