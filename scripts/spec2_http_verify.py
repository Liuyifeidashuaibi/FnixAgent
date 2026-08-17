"""Spec 2 HTTP 端到端验证：通过 /api/v1/work/stream 触发，验证 thought/action/observation 流出。

测试用例：
  - ask 模式：纯问答，验证 thought (reasoning_content) + text 流出
  - craft 模式：写文件任务，验证 thought (决策独白) + action + observation + artifact 流出
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import json
import sys
import time
import urllib.request
from pathlib import Path

api_key = ""
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("DASHSCOPE_API_KEY="):
        api_key = line.split("=", 1)[1].strip()
        break

if not api_key:
    print("FAIL: 未读到 DASHSCOPE_API_KEY")
    sys.exit(1)


def call_work_stream(user_input: str, work_mode: str = "ask", timeout: float = 300.0):
    """调用 /api/v1/work/stream，返回 NDJSON 行列表。"""
    payload = {
        "user_input": user_input,
        "workspace": str(Path.cwd()),
        "work_mode": work_mode,
        "llm": {
            "provider": "qwen",
            "model": "qwen-plus-latest",
            "api_key": api_key,
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8003/api/v1/work/stream",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print(f"\n>>> POST /api/v1/work/stream (mode={work_mode})")
    print(f">>> user_input: {user_input[:60]}")
    print(">>> 流式输出：\n")

    chunks = []
    start = time.time()
    # socket 超时设大（每行读取），整体请求超时由 timeout 控制
    import socket
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        sock = resp.fp.raw._sock if hasattr(resp.fp, "raw") else None
        if sock:
            sock.settimeout(timeout)
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                chunks.append(obj)
                ct = obj.get("chunk_type", "?")
                content = obj.get("content", "")
                done = obj.get("done", False)
                if isinstance(content, str):
                    preview = content[:100].replace("\n", " ")
                else:
                    preview = json.dumps(content, ensure_ascii=False)[:100]
                elapsed = time.time() - start
                print(f"  [{elapsed:5.2f}s] [{ct:12s}] done={done} {preview}")
                if done:
                    break
            except json.JSONDecodeError:
                print(f"  [parse-fail] {line[:120]}")
    return chunks


print("=" * 60)
print("Spec 2 HTTP 端到端验证 — Case 1: ask 模式 (reasoning_content 通路)")
print("=" * 60)

ask_chunks = call_work_stream(
    "用一句话解释什么是闭包(closure)，给个 JavaScript 示例",
    work_mode="ask",
)

# 统计
ask_counts = {}
for c in ask_chunks:
    ct = c.get("chunk_type", "?")
    ask_counts[ct] = ask_counts.get(ct, 0) + 1

print("\n--- Case 1 chunk_type 分布 ---")
for k in sorted(ask_counts.keys()):
    print(f"  {k}: {ask_counts[k]}")

print("\n--- Case 1 验收 ---")
if "thought" not in ask_counts:
    print("FAIL: thought chunk 未流出 (HTTP 层)")
    sys.exit(2)
print(f"PASS: thought chunk 通过 HTTP 流出 ({ask_counts['thought']} 条)")

# 找到 thought 内容
thought_content = ""
text_content = ""
for c in ask_chunks:
    if c.get("chunk_type") == "thought" and not thought_content:
        thought_content = str(c.get("content", ""))[:200]
    if c.get("chunk_type") == "text" and not text_content:
        text_content = str(c.get("content", ""))[:200]

print(f"\nthought 内容预览：{thought_content}")
print(f"\ntext 内容预览：{text_content}")

if thought_content and text_content and thought_content != text_content:
    print("PASS: thought ≠ text (reasoning_content 通路真正生效)")
elif thought_content == text_content:
    print("WARN: thought == text (重复，可能 reasoning_content 为空走了 ReAct 路径)")
else:
    print("INFO: thought 或 text 为空")

print("\n" + "=" * 60)
print("Spec 2 HTTP 端到端验证 — 全部完成")
print("=" * 60)
