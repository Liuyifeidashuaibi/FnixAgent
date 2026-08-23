"""Optimization hints from system benchmark results."""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

from fnixagent.core.benchmark.system_runner import StageResult

STAGE_HINTS: dict[str, str] = {
    "infra.health": "确认 agentd 已启动：`python -m fnixagent.main serve`",
    "infra.harness_status": "检查 fnix-local sidecar 与 ~/.fnix 目录权限",
    "harness.workspace": "检查 workspace 路径可写；Windows 避免只读盘",
    "harness.config": "在 Settings → Models 填写 API Key 并 Save",
    "code.apply": "检查 DiffEngine 与 workspace 写权限；查看 agentd 日志",
    "code.sessions": "检查 harness session store（~/.fnix 或 workspace/.fnix）",
    "work.engine": "Work 流水线组件未就绪 — 查看 /api/v1/work/status",
    "fcs.smoke": "Code Agent 冒烟失败 — 加强 heal、减少 stub 写入；跑 `run-code-benchmark.py --tag smoke`",
    "fcs.manifest": "运行 `python scripts/generate-code-tasks.py --count 1000`",
    "llm.connectivity": "验证 DashScope Key、模型名与 base_url；Settings 里 Test connection",
    "frontend.ping": "前端无法连 agentd — 核对 VITE_API_BASE 与 agentd 端口",
    "frontend.harness": "harness config 拉取失败 — CORS 或 agentd 未启动",
    "frontend.stream": "NDJSON 流异常 — 检查代理与 /api/v1/benchmark/run",
}

CATEGORY_HINTS: dict[str, str] = {
    "infra": "优先修复 agentd / sidecar / 健康检查",
    "harness": "同步 BYOK、ensure workspace、索引",
    "work": "Work 模式 Ask/Plan/Craft 流水线",
    "code": "Code apply / preview / session 持久化",
    "fcs": "跑 FCS 子集定位最低 capability",
    "llm": "LLM 连通性与模型配置",
    "frontend": "Workbench ↔ agentd 桥接与 Vite proxy",
}


def build_recommendations(
    stages: list[StageResult],
    by_category: dict[str, float],
    overall: float,
) -> list[str]:
    recs: list[str] = []

    for s in stages:
        if not s.ok and s.id in STAGE_HINTS:
            recs.append(f"[{s.id}] {STAGE_HINTS[s.id]}")

    for cat, score in sorted(by_category.items(), key=lambda x: x[1]):
        if score < 80 and cat in CATEGORY_HINTS:
            recs.append(f"[{cat} ↓{score}] {CATEGORY_HINTS[cat]}")

    if overall >= 90:
        recs.insert(0, "系统整体健康 — 可跑全量 FCS (`--limit 1000`) 做深度回归")
    elif overall >= 70:
        recs.insert(0, "基础链路可用 — 建议开启 include_llm 跑 Code 冒烟")
    else:
        recs.insert(0, "基础链路未通过 — 先修 infra/harness/code.apply 再测 LLM")

    seen: set[str] = set()
    deduped: list[str] = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return deduped[:12]
