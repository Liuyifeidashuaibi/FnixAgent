"""批次完成后生成完整报告：Markdown + HTML + 回归集JSON。"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, r"E:\FNIX\FnixAgent\src")
from fnixagent.bench.report import write_markdown, write_html, load_summary
from fnixagent.bench.fixloop import build_regression_set, cluster_failures

run_dir = Path(r"E:\FNIX\FnixAgent\benchmarks\benchforge\runs\batch-v3-20260822")
out_dir = Path(r"E:\FNIX\FnixAgent\benchmarks\benchforge\reports")
out_dir.mkdir(parents=True, exist_ok=True)

# 1. 加载 summary
summary = load_summary(run_dir)
print(f"=== 评测报告 ===")
print(f"运行ID: {summary['run_id']}")
print(f"模型: {summary.get('model', 'n/a')}")
totals = summary["totals"]
print(f"总任务: {totals['total']} | 成功: {totals['success']} | 失败: {totals['failure']} | 配额跳过: {totals.get('infra_skip', 0)}")
print(f"成功率: {totals['success_rate']*100:.1f}%")
print(f"总Token: {summary.get('total_tokens', 0):,}")
if summary.get("note"):
    print(f"备注: {summary['note']}")

# 2. 生成 Markdown
md_path = out_dir / "batch-v3-report.md"
write_markdown(summary, md_path)
print(f"\nMarkdown报告: {md_path}")

# 3. 生成 HTML
html_path = out_dir / "batch-v3-report.html"
write_html(summary, html_path)
print(f"HTML报告: {html_path}")

# 4. 生成回归集 JSON
try:
    reg_path = run_dir / "regression.json"
    build_regression_set(run_dir, reg_path)
    reg = json.loads(reg_path.read_text("utf-8"))
    print(f"\n回归集: {reg_path}")
    print(f"失败任务数: {reg['total_failures']}")
    if reg.get("by_failure_type"):
        print("失败类型分布:")
        for ft, cnt in sorted(reg["by_failure_type"].items(), key=lambda kv: -kv[1]):
            print(f"  {ft}: {cnt}")

    # 5. 失败聚类
    clusters = cluster_failures(reg_path)
    if clusters:
        print(f"\n失败聚类 ({len(clusters)} 组):")
        for c in clusters:
            print(f"  {c.failure_type}: {c.count} 条 → 疑似 {c.suspected_component}")
except Exception as e:
    print(f"回归集生成: {e}")

# 6. A1/A2 触发统计
results_file = run_dir / "results.jsonl"
a1_count = 0
a2_count = 0
for line in results_file.read_text("utf-8").splitlines():
    if not line.strip():
        continue
    r = json.loads(line)
    err = r.get("error", "") or ""
    if "死循环" in err:
        a1_count += 1
    if "步数限制" in err or "最大步数" in err:
        a2_count += 1

print(f"\n=== 控制层修复触发统计 ===")
print(f"A1(文件级死循环检测): {a1_count} 次触发")
print(f"A2(步数耗尽收尾摘要): {a2_count} 次触发")

print(f"\n=== 完成 ===")
print(f"所有报告已生成到: {out_dir}")
