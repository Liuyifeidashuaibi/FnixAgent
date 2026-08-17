"""Spec 2 端到端验证：跑一次 ask 任务，统计 chunk_type 分布。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import json
import os
import urllib.request
import sys
from pathlib import Path

# 优先从 .env 读 DASHSCOPE_API_KEY
ENV_PATH = Path(__file__).parent.parent / ".env"
api_key = ""
if ENV_PATH.is_file():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("DASHSCOPE_API_KEY="):
            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
        if line.startswith("OPENAI_API_KEY=") and not api_key:
            api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

URL = "http://127.0.0.1:8003/api/v1/work/stream"
PAYLOAD = {
    "user_input": "用一句话介绍 Python 的 list comprehension",
    "work_mode": "ask",
    "llm": {
        "provider": "qwen",
        "model": "qwen-plus",
        "api_key": api_key,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
}

print(f"使用 API key: {api_key[:8]}{'*' * (max(0, len(api_key) - 8)) if api_key else '(空)'}")
print(f"POST {URL}\n")

req = urllib.request.Request(
    URL,
    data=json.dumps(PAYLOAD).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

chunk_counts = {}
samples = {}
raw_lines = []
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        buf = b""
        done_seen = False
        while True:
            chunk = resp.read(1024)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                raw_lines.append(line.decode("utf-8", errors="replace"))
                try:
                    obj = json.loads(line.decode("utf-8"))
                except Exception:
                    continue
                ct = obj.get("chunk_type") or obj.get("type") or "unknown"
                chunk_counts[ct] = chunk_counts.get(ct, 0) + 1
                if ct not in samples:
                    data = obj.get("content") or obj.get("data")
                    if isinstance(data, (dict, list)):
                        data_str = json.dumps(data, ensure_ascii=False)[:200]
                    else:
                        data_str = str(data)[:200]
                    samples[ct] = data_str
                if ct == "done":
                    done_seen = True
                    break
            if done_seen:
                break
except Exception as e:
    print("ERR:", type(e).__name__, str(e))
    print(f"已收到 raw_lines: {len(raw_lines)}")
    for i, l in enumerate(raw_lines[:5]):
        print(f"  raw[{i}]: {l[:300]}")
    sys.exit(1)

print(f"=== raw_lines total: {len(raw_lines)} ===")
for i, l in enumerate(raw_lines[:5]):
    print(f"  raw[{i}]: {l[:300]}")
print()

print("=== chunk_type 分布 ===")
for k in sorted(chunk_counts.keys()):
    print(f"  {k}: {chunk_counts[k]}")

print("\n=== 首条样本预览 ===")
for k in ["thought", "action", "observation", "tool_call", "tool_result", "text", "mission", "pipeline", "evolution", "done", "error"]:
    if k in samples:
        print(f"\n[{k}]")
        print(samples[k])

# 关键验证：thought 必须出现；action/observation 仅在调用工具时出现
print("\n=== Spec 2 验收 ===")
if "thought" not in chunk_counts:
    print(f"FAIL: 缺失 thought chunk（思考链未流出）")
    sys.exit(2)
if "error" in chunk_counts and "text" not in chunk_counts:
    print(f"FAIL: 只有 error chunk，任务异常")
    sys.exit(3)
print(f"PASS: thought chunk 真实流出（{chunk_counts['thought']} 条）")
if "action" in chunk_counts and "observation" in chunk_counts:
    print(f"PASS: action/observation 配对出现（{chunk_counts['action']}/{chunk_counts['observation']}）")
else:
    print(f"INFO: 本次 ask 任务未调用工具（action/observation 未出现，正常）")

