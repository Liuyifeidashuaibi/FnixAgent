"""Spec 2 端到端验证：直接调用 run_work_stream，统计 chunk_type 分布。

绕过 HTTP 层，但保留 work_pipeline 9 步完整流程，专注验证 loop.py 的
thought/action/observation chunk 真实产出。
"""
import asyncio
import json
import sys
from pathlib import Path

# 读 .env
api_key = ""
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DASHSCOPE_API_KEY="):
        api_key = line.split("=", 1)[1].strip()
        break

if not api_key:
    print("FAIL: 未读到 DASHSCOPE_API_KEY")
    sys.exit(1)

print(f"key prefix: {api_key[:12]}...")

from fnixagent.services.work_pipeline import run_work_stream


async def main():
    llm_cfg = {
        "provider": "qwen",
        "model": "qwen-plus-latest",
        "api_key": api_key,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    }

    chunk_counts = {}
    samples = {}

    print("\n开始流式执行：'用一句话介绍 Python 的 list comprehension' (mode=ask)\n")

    async for event in run_work_stream(
        user_input="用一句话介绍 Python 的 list comprehension",
        workspace=str(Path.cwd()),
        llm=llm_cfg,
        work_mode="ask",
    ):
        et = event.get("type", "unknown")
        data = event.get("data", "")
        chunk_counts[et] = chunk_counts.get(et, 0) + 1
        if et not in samples:
            if isinstance(data, (dict, list)):
                sample_str = json.dumps(data, ensure_ascii=False)[:200]
            else:
                sample_str = str(data)[:200]
            samples[et] = sample_str
        # 实时打印（截断）
        if isinstance(data, str):
            preview = data[:80].replace("\n", " ")
        else:
            preview = json.dumps(data, ensure_ascii=False)[:80]
        print(f"  [{et}] {preview}")
        if et == "done" or et == "error":
            break

    print("\n=== chunk_type 分布 ===")
    for k in sorted(chunk_counts.keys()):
        print(f"  {k}: {chunk_counts[k]}")

    print("\n=== 首条样本 ===")
    for k in ["mission", "pipeline", "thought", "action", "observation", "tool_call", "tool_result", "text", "evolution", "done", "error"]:
        if k in samples:
            print(f"\n[{k}]")
            print(samples[k])

    print("\n=== Spec 2 验收 ===")
    if "thought" not in chunk_counts:
        print("FAIL: thought chunk 未产出（loop.py S2.1 改动未生效）")
        sys.exit(2)
    print(f"PASS: thought chunk 真实流出 ({chunk_counts['thought']} 条)")
    if "action" in chunk_counts and "observation" in chunk_counts:
        print(f"PASS: action/observation 配对 ({chunk_counts['action']}/{chunk_counts['observation']})")
    else:
        print("INFO: 本次 ask 任务未调用工具（action/observation 未出现，正常）")
    if "error" in chunk_counts and "text" not in chunk_counts:
        print(f"FAIL: 任务异常退出 (error chunk)")
        sys.exit(3)

    # Spec 2 关键验收：thought 不应与 text 完全重复（避免"答案当思考"反模式）
    if "thought" in samples and "text" in samples:
        thought_text = samples["thought"].strip()
        text_text = samples["text"].strip()
        if thought_text and text_text and thought_text == text_text:
            print(f"WARN: thought chunk 与 text chunk 内容完全重复（设计反模式，应优先用 reasoning_content）")
        elif thought_text and not text_text.startswith(thought_text[:50]):
            print(f"PASS: thought chunk 与 text chunk 内容不同（reasoning_content 通路生效）")
        else:
            print(f"INFO: thought 是 text 的前缀（可能 reasoning_content 为空，走了 ReAct 决策独白路径）")
    elif "thought" in samples and "text" not in samples:
        print(f"PASS: thought chunk 已产出但无 text chunk（说明走的是 reasoning_content 路径，未发 text）")


if __name__ == "__main__":
    asyncio.run(main())
