"""启动 bench run 50条批次 — qwen3.6-plus-2026-04-02，纯启发式判定。"""
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
os.environ["BENCH_MODEL"] = "qwen3.6-plus-2026-04-02"
os.environ["BENCH_MODEL_FALLBACKS"] = ""
os.environ["PYTHONPATH"] = r"E:\FNIX\FnixAgent\src"
os.environ["FNIXAGENT_PROFILE"] = "standalone"

sys.path.insert(0, r"E:\FNIX\FnixAgent\src")

from fnixagent.main import main
sys.argv = [
    "fnixagent", "bench", "run",
    "--limit", "50",
    "--no-llm-judge",
    "--concurrency", "3",
    "--max-steps", "20",
    "--quota-abort", "10",
    "--out", r"benchmarks/benchforge/runs/batch-v3-20260822",
]
main()
