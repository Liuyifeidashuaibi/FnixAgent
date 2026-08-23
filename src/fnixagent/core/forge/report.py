"""FnixForge — 报告输出（JSON + HTML 能力矩阵）。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

def write_json_report(result: dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return out_path

def _bar(pct: float, ok_color: str) -> str:
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div style="background:#1f2430;border-radius:4px;height:10px;width:100%">'
        f'<div style="background:{ok_color};width:{pct:.1f}%;height:10px;border-radius:4px"></div></div>'
    )

def _cap_color(rate: float, threshold: float) -> str:
    if rate >= threshold:
        return "#3fb950"
    if rate >= threshold - 25:
        return "#d29922"
    return "#f85149"

def render_html_report(result: dict[str, Any]) -> str:
    final = result.get("final") or {}
    readiness = result.get("readiness") or {}
    caps = (final.get("capabilities") or {})
    threshold = float(readiness.get("threshold", 90.0))
    e = html.escape

    rows = []
    for cap, m in sorted(caps.items()):
        rate = float(m.get("weighted_pass_rate", 0.0))
        color = _cap_color(rate, threshold)
        rows.append(
            "<tr>"
            f"<td><b>{e(cap)}</b></td>"
            f"<td>{m.get('passed', 0)}/{m.get('tasks', 0)}</td>"
            f"<td>{rate:.1f}%</td>"
            f"<td style='min-width:160px'>{_bar(rate, color)}</td>"
            "</tr>"
        )

    round_rows = []
    for r in result.get("rounds", []):
        agg = r.get("aggregate") or {}
        fix = r.get("fix") or {}
        round_rows.append(
            "<tr>"
            f"<td>Round {r.get('round', 0)}</td>"
            f"<td>{agg.get('passed', 0)}/{agg.get('tasks', 0)}</td>"
            f"<td>{agg.get('overall_score', 0.0):.1f}%</td>"
            f"<td>{e(fix.get('decision', '-'))}</td>"
            f"<td>{e(fix.get('note', ''))}</td>"
            "</tr>"
        )

    verdict = "PRODUCTION READY" if readiness.get("ready") else "NOT READY"
    verdict_color = "#3fb950" if readiness.get("ready") else "#f85149"
    weak = readiness.get("weak_capabilities") or []
    weak_html = (
        f"<p style='color:#d29922'>薄弱能力: {e(', '.join(weak))}</p>" if weak else ""
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>FnixForge 测评报告</title>
<style>
 body {{ background:#0d1117; color:#c9d1d9; font-family:'Segoe UI',system-ui,sans-serif;
        max-width:960px; margin:32px auto; padding:0 24px; }}
 h1 {{ color:#f0f6fc; }} h2 {{ color:#8b949e; font-size:1rem; text-transform:uppercase;
        letter-spacing:.08em; border-bottom:1px solid #21262d; padding-bottom:6px; }}
 table {{ width:100%; border-collapse:collapse; margin:12px 0; }}
 td, th {{ padding:8px 10px; border-bottom:1px solid #21262d; text-align:left; font-size:.92rem; }}
 .verdict {{ font-size:1.6rem; font-weight:700; color:{verdict_color}; margin:18px 0 4px; }}
 .meta {{ color:#8b949e; font-size:.85rem; }}
</style></head><body>
<h1>FnixForge 能力测评报告</h1>
<div class="meta">
  目标: {e(result.get('target_root', ''))} · 套件: {e(result.get('suite', ''))} ·
  模式: {e(result.get('mode', ''))} · 共 {result.get('total_rounds', 0)} 轮 ·
  耗时 {result.get('elapsed_s', 0.0)}s
</div>
<div class="verdict">{verdict}</div>
<p>总体加权分: <b>{final.get('overall_score', 0.0):.1f}%</b>
   （通过 {final.get('passed', 0)}/{final.get('tasks', 0)} 题，阈值 {threshold:.0f}%）</p>
{weak_html}
<h2>能力矩阵</h2>
<table>
<tr><th>能力维度</th><th>通过</th><th>加权通过率</th><th></th></tr>
{''.join(rows)}
</table>
<h2>迭代轮次</h2>
<table>
<tr><th>轮次</th><th>通过</th><th>总分</th><th>修复裁决</th><th>说明</th></tr>
{''.join(round_rows)}
</table>
</body></html>"""

def write_html_report(result: dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html_report(result), encoding="utf-8")
    return out_path
