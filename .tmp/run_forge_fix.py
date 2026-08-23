"""Forge 熔炉：用 qwen-turbo 生成 LLM 根因诊断（耗少量配额）。"""
import os, sys
from pathlib import Path
env = {}
for line in Path(r"E:/FNIX/FnixAgent/.env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
os.environ["BENCH_API_KEY"] = env.get("CUSTOM_API_KEY", "")
os.environ["BENCH_BASE_URL"] = env.get("CUSTOM_BASE_URL", "")
os.environ["BENCH_MODEL"] = "qwen-turbo"
os.environ["BENCH_JUDGE_MODEL"] = "qwen-turbo"
os.environ["PYTHONPATH"] = r"E:/FNIX/FnixAgent/src"
sys.path.insert(0, r"E:/FNIX/FnixAgent/src")
from fnixagent.main import main
sys.argv = ["fnixagent", "bench", "fix", "--run", r"benchmarks/benchforge/runs/batch-v4-20260822"]
main()
