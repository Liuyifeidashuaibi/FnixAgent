"""BenchForge — 评测报告生成器（Markdown + HTML）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import html
import json
import time
from pathlib import Path
from typing import Any

_FAILURE_LABELS = {
    "planning_error": "规划拆解错误",
    "mcp_call_error": "MCP调用异常",
    "path_error": "多文件路径错误",
    "context_loss": "上下文记忆丢失",
    "requirement_misunderstanding": "需求理解偏差",
    "crash": "运行崩溃",
    "incomplete_output": "输出残缺",
    "other": "其他错误",
}


def load_summary(run_dir: Path | str) -> dict[str, Any]:
    p = Path(run_dir) / "summary.json"
    if not p.exists():
        raise FileNotFoundError(f"summary.json 不存在: {p}")
    return json.loads(p.read_text("utf-8"))


def write_markdown(summary: dict[str, Any], out: Path | str) -> Path:
    totals = summary["totals"]
    lines = [
        "# FnixAgent 全量基准评测报告",
        "",
        f"- 运行 ID: `{summary['run_id']}`  | 模型: **{summary.get('model') or 'n/a'}**",
        f"- 开始: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(summary['started_at']))}",
        (f"- 结束: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(summary['finished_at']))}"
         if summary.get("finished_at") else "- 状态: 运行中"),
        f"- 总 Token: {summary.get('total_tokens', 0):,}",
        "",
        "## 总体结果",
        "",
        f"- 总任务: **{totals['total']}** | 成功: **{totals['success']}** | "
        f"失败: **{totals['failure']}** | 拉取异常: {totals['fetch_error']}",
        f"- 总成功率: **{totals['success_rate'] * 100:.1f}%**",
        "",
        "## 分数据集统计",
        "",
        "| 数据集 | 总数 | 成功 | 失败 | 成功率 |",
        "|---|---|---|---|---|",
    ]
    for name, ds in summary["datasets"].items():
        lines.append(
            f"| {name} | {ds['total']} | {ds['success']} | {ds['failure']} "
            f"| {ds['success_rate'] * 100:.1f}% |"
        )
    lines += ["", "## 失败类型分布", "", "| 失败类型 | 数量 |", "|---|---|---|"]
    for ft, cnt in sorted(totals["failure_type_counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {_FAILURE_LABELS.get(ft, ft)} | {cnt} |")
    out_path = Path(out)
    out_path.write_text("\n".join(lines), "utf-8")
    return out_path


def write_html(summary: dict[str, Any], out: Path | str) -> Path:
    totals = summary["totals"]
    ds_rows = "".join(
        f"<tr><td>{html.escape(n)}</td><td>{d['total']}</td><td class='ok'>{d['success']}</td>"
        f"<td class='bad'>{d['failure']}</td><td>{d['success_rate'] * 100:.1f}%</td></tr>"
        for n, d in summary["datasets"].items()
    )
    max_ft = max(totals["failure_type_counts"].values(), default=1)
    ft_rows = "".join(
        f"<tr><td>{html.escape(_FAILURE_LABELS.get(ft, ft))}</td><td>{cnt}</td>"
        f"<td><div class='bar' style='width:{cnt / max_ft * 100:.0f}%'></div></td></tr>"
        for ft, cnt in sorted(totals["failure_type_counts"].items(), key=lambda kv: -kv[1])
    )
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>FnixAgent 基准评测报告 · {html.escape(summary['run_id'])}</title>
<style>
body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;margin:2rem auto;max-width:960px;color:#1a1a2e}}
h1{{border-bottom:3px solid #4f63ff;padding-bottom:.5rem}}
.kpi{{display:flex;gap:1rem;margin:1.5rem 0}}
.kpi div{{flex:1;background:#f4f6ff;border-radius:10px;padding:1rem;text-align:center}}
.kpi .num{{font-size:2rem;font-weight:700;color:#4f63ff}}
table{{width:100%;border-collapse:collapse;margin:1rem 0}}
th,td{{border-bottom:1px solid #e2e5f1;padding:.5rem .75rem;text-align:left}}
th{{background:#f4f6ff}} .ok{{color:#0a9d58;font-weight:600}} .bad{{color:#d93025;font-weight:600}}
.bar{{background:linear-gradient(90deg,#ff7a59,#d93025);height:14px;border-radius:4px}}
footer{{margin-top:2rem;color:#8a8fa8;font-size:.85rem}}
</style></head><body>
<h1>FnixAgent 全量基准评测报告</h1>
<p>运行 ID: <code>{html.escape(summary['run_id'])}</code> · 模型: <b>{html.escape(summary.get('model') or 'n/a')}</b></p>
<div class="kpi">
  <div><div class="num">{totals['total']}</div>总任务</div>
  <div><div class="num ok">{totals['success']}</div>成功</div>
  <div><div class="num bad">{totals['failure']}</div>失败</div>
  <div><div class="num">{totals['success_rate'] * 100:.1f}%</div>成功率</div>
  <div><div class="num">{summary.get('total_tokens', 0) // 1000}k</div>总Token</div>
</div>
<h2>分数据集统计</h2>
<table><thead><tr><th>数据集</th><th>总数</th><th>成功</th><th>失败</th><th>成功率</th></tr></thead>
<tbody>{ds_rows}</tbody></table>
<h2>失败类型分布</h2>
<table><thead><tr><th>类型</th><th>数量</th><th></th></tr></thead>
<tbody>{ft_rows}</tbody></table>
<footer>由 BenchForge 生成 · 数据仅用于优化 Agent 控制层（Runtime/MCP/记忆/Workflow），禁止用于 SFT。</footer>
</body></html>"""
    out_path = Path(out)
    out_path.write_text(doc, "utf-8")
    return out_path
