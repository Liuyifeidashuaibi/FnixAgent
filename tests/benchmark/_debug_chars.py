import sys

sys.path.insert(0, "E:/FNIX/FnixAgent")
from tests.benchmark.dataset_loader import load_prototypebench, load_swe_bench_lite

pb = load_prototypebench()
sw = load_swe_bench_lite()

for name, tasks in [("prototypebench", pb), ("swe-bench", sw)]:
    p = tasks[0].prompt
    print(f"=== {name} ===")
    print(f"Length: {len(p)}")
    print(f"Has backticks: {'`' in p}")
    print(f"Has dollar: {'$' in p}")
    print(f"Has double quote: {'"' in p}")
    print(f"Has single quote: {chr(39) in p}")
    print(f"Has backslash: {'\\' in p}")
    print(f"Has newline: {chr(10) in p}")
    print(f"Repr first 300: {repr(p[:300])}")
    print()
