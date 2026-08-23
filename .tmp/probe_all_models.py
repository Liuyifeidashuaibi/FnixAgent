import asyncio
import time

from fnixagent.core.llm.adapter import LLMAdapter

CANDIDATES = [
    "qwen3.7-max-2026-05-20",
    "qwen3.7-max-2026-05-17",
    "qwen3.6-max-preview",
    "qwen3.6-flash-2026-04-16",
    "qwen3.6-plus-2026-04-02",
    "qwen3.5-plus",
    "qwen3.5-max",
    "qwen-turbo",
    "qwen-plus",
    "qwen-max",
    "glm-5.2",
    "kimi-k2.6",
]


async def probe():
    a = LLMAdapter()
    for model in CANDIDATES:
        t0 = time.time()
        try:
            r = await a.chat(
                messages=[{"role": "user", "content": "回复OK"}], model=model
            )
            usage = r.get("usage", {}).get("total_tokens")
            print(f"{model}: OK {time.time()-t0:.1f}s tokens={usage}")
        except Exception as e:
            msg = str(e)
            tag = "QUOTA" if ("403" in msg or "quota" in msg.lower()) else (
                "NOT_FOUND" if "404" in msg else "FAIL"
            )
            print(f"{model}: {tag} {msg[:90]}")
        await asyncio.sleep(1)


asyncio.run(probe())
