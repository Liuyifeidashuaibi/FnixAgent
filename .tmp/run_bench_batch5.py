"""启动 batch-v5 评测 — 验证 B5（只读工具不缓存）+ B6（项目级工作区共享）。
web-bench 的 calculator/bom 项目链应恢复正常（init 建文件 → task-N 修改）。
"""
import os, sys
from pathlib import Path

env = {}
for line in Path(r"E:\FNIX\FnixAgent\.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

os.environ["BENCH_API_KEY"] = env.get("CUSTOM_API_KEY", "")
os.environ["BENCH_BASE_URL"] = env.get("CUSTOM_BASE_URL", "")
os.environ["BENCH_MODEL"] = "qwen3.7-max-2026-05-17"
os.environ["BENCH_MODEL_FALLBACKS"] = "qwen3.6-plus-2026-04-02"
os.environ["PYTHONPATH"] = r"E:\FNIX\FnixAgent\src"
os.environ["FNIXAGENT_PROFILE"] = "standalone"

sys.path.insert(0, r"E:\FNIX\FnixAgent\src")

from fnixagent.main import main
sys.argv = [
    "fnixagent", "bench", "run",
    "--dataset", "web-bench",
    "--no-llm-judge",
    "--concurrency", "2",
    "--max-steps", "20",
    "--quota-abort", "10",
    "--out", r"benchmarks/benchforge/runs/batch-v5-20260822",
]
main()
