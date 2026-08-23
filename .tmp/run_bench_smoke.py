"""启动 bench run 烟雾测试 — 10 条，纯启发式判定，qwen3.6-plus-2026-04-02。"""
import os, sys
from pathlib import Path

# 从 .env 读取 key（不打印）
env = {}
for line in Path(r"E:\FNIX\FnixAgent\.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

os.environ["BENCH_API_KEY"] = env.get("CUSTOM_API_KEY", "")
os.environ["BENCH_BASE_URL"] = env.get("CUSTOM_BASE_URL", "")
os.environ["BENCH_MODEL"] = "qwen3.6-plus-2026-04-02"
os.environ["BENCH_MODEL_FALLBACKS"] = ""  # 禁用 fallback，配额耗尽直接熔断
os.environ["PYTHONPATH"] = r"E:\FNIX\FnixAgent\src"
os.environ["FNIXAGENT_PROFILE"] = "standalone"

sys.path.insert(0, r"E:\FNIX\FnixAgent\src")

from fnixagent.main import main
sys.argv = [
    "fnixagent", "bench", "run",
    "--limit", "10",
    "--no-llm-judge",
    "--concurrency", "2",
    "--max-steps", "20",
    "--out", r"benchmarks/benchforge/runs/smoke-v3-20260822",
    "--no-quota-probe",  # 已知有配额，跳过预探省一次请求
]
main()
