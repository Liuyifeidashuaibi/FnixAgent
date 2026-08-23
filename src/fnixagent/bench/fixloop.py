"""BenchForge — 失败分析 → 自动修复 → 回归验证闭环。

流程（严格对齐任务规格书）：
  1. 从 results.jsonl 收集全部失败任务 → 保存为回归集 regression.json
  2. 按失败类型聚类，调用 Agent 自身的修复能力定位 FnixAgent 控制层
     （Runtime / MCP / 记忆 / Workflow）的根因代码
  3. 生成修复补丁（由 --Apply 开关控制是否直接落盘；默认先出诊断报告）
  4. 修复后重跑回归集，验证不复发；防止功能退化

设计红线：修复对象是 **Agent 控制层代码**，绝不触碰基座模型权重、不做 SFT。
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fnixagent.bench.schema import FailureType, TaskStatus

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 回归集
# ---------------------------------------------------------------------------

def build_regression_set(run_dir: Path | str, out: Path | str | None = None) -> Path:
    """从一次评测结果中抽取全部失败任务，生成回归测试集 JSON。

    断点续跑可能对同一任务产生多条记录（配额跳过 / 重跑后成功或失败）。
    这里按 (dataset, task_id) 取**最后一条**记录，确保回归集反映最新状态：
    一旦任务重跑成功，就不会再被旧失败记录拖累进回归集。
    """
    run_dir = Path(run_dir)
    results = run_dir / "results.jsonl"
    if not results.exists():
        raise FileNotFoundError(f"结果文件不存在: {results}")
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for line in results.read_text("utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        latest[(rec.get("dataset", ""), rec.get("task_id", ""))] = rec
    failures: list[dict[str, Any]] = [
        rec for rec in latest.values()
        if rec.get("status") in (TaskStatus.FAILURE.value, "failure")
    ]
    payload = {
        "version": 1,
        "generated_at": time.time(),
        "source_run": run_dir.name,
        "total_failures": len(failures),
        "by_failure_type": _count_by(failures, "failure_type"),
        "by_dataset": _count_by(failures, "dataset"),
        "tasks": [
            {
                "dataset": f["dataset"], "task_id": f["task_id"], "prompt": f["prompt"],
                "failure_type": f.get("failure_type", ""), "evidence": f.get("failure_evidence", ""),
            }
            for f in failures
        ],
    }
    out_path = Path(out) if out else run_dir / "regression.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    _logger.info("回归集已生成: %s (失败 %d 条)", out_path, len(failures))
    return out_path


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for r in records:
        counts[str(r.get(key) or "unknown")] += 1
    return dict(counts)


# ---------------------------------------------------------------------------
# 失败根因聚类
# ---------------------------------------------------------------------------

@dataclass
class FailureCluster:
    failure_type: str
    count: int
    tasks: list[dict[str, Any]] = field(default_factory=list)
    suspected_component: str = ""     # runtime / mcp / memory / workflow
    root_cause_hint: str = ""

# 失败类型 → 控制层组件映射（人工规则，作为 Agent 诊断的先验）
_COMPONENT_MAP: dict[str, str] = {
    FailureType.PLANNING_ERROR.value: "workflow/orchestrator（任务拆解与规划）",
    FailureType.MCP_CALL_ERROR.value: "mcp/tools（工具注册、参数校验、错误回传）",
    FailureType.PATH_ERROR.value:     "runtime/workspace（路径解析、相对/绝对路径转换）",
    FailureType.CONTEXT_LOSS.value:   "memory（上下文压缩、摘要、截断策略）",
    FailureType.REQUIREMENT_MISUNDERSTANDING.value: "workflow/intent（需求理解与意图对齐）",
    FailureType.CRASH.value:          "runtime（异常处理、超时控制）",
    FailureType.INCOMPLETE_OUTPUT.value: "runtime/output（产物交付完整性校验）",
    FailureType.OTHER.value:          "待人工分析",
}


def cluster_failures(regression_path: Path | str) -> list[FailureCluster]:
    """把回归集按失败类型聚类，标注疑似控制层组件。"""
    payload = json.loads(Path(regression_path).read_text("utf-8"))
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in payload.get("tasks", []):
        groups[t.get("failure_type") or FailureType.OTHER.value].append(t)
    clusters = [
        FailureCluster(
            failure_type=ft, count=len(tasks), tasks=tasks,
            suspected_component=_COMPONENT_MAP.get(ft, "待人工分析"),
        )
        for ft, tasks in sorted(groups.items(), key=lambda kv: -len(kv[1]))
    ]
    return clusters


# ---------------------------------------------------------------------------
# 修复建议（可选调用 LLM 生成根因分析）
# ---------------------------------------------------------------------------

_FIXER_SYSTEM = """你是 FnixAgent 框架的高级维护工程师。基于以下基准评测失败聚类，
分析 Agent 控制层（Runtime/MCP/记忆/Workflow）的根因，并给出可执行的修复方案。

输出格式（JSON）：
{
  "root_causes": [
    {
      "failure_type": "...",
      "suspected_files": ["src/fnixagent/..."],
      "root_cause": "一句话根因",
      "fix_plan": "具体修复步骤",
      "risk": "low|medium|high"
    }
  ]
}
只输出 JSON。修复原则：
- 只改 Agent 控制层，不改模型权重、不做 SFT
- 优先修影响面最大的失败类型
- 修复必须兼容现有测试
"""


async def analyze_with_llm(
    clusters: list[FailureCluster],
    llm_call,
    repo_root: Path | str,
) -> dict[str, Any]:
    """调用 LLM 对失败聚类做根因分析（返回结构化修复方案）。"""

    repo_root = Path(repo_root)
    summary = []
    for c in clusters[:6]:  # 最多喂 6 个聚类，控制上下文
        sample = c.tasks[0] if c.tasks else {}
        summary.append({
            "failure_type": c.failure_type,
            "count": c.count,
            "suspected_component": c.suspected_component,
            "sample_evidence": str(sample.get("evidence", ""))[:300],
            "sample_task": str(sample.get("prompt", ""))[:400],
        })
    tree_hint = _repo_tree_hint(repo_root)
    user_msg = (
        "失败聚类（按数量降序）：\n"
        + json.dumps(summary, ensure_ascii=False, indent=2)
        + "\n\nFnixAgent 控制层相关目录：\n" + tree_hint
    )
    resp = await llm_call(
        [{"role": "system", "content": _FIXER_SYSTEM},
         {"role": "user", "content": user_msg}],
        tools=None, temperature=0.2, max_tokens=4096,
    )
    content = ""
    if isinstance(resp, dict):
        choices = resp.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content", "") or ""
    elif hasattr(resp, "content"):
        content = resp.content or ""
    from fnixagent.bench.judge import _extract_json  # noqa: PLC0415

    result = _extract_json(content)
    result["raw_response"] = content[:2000]
    result["clusters"] = [
        {
            "failure_type": c.failure_type, "count": c.count,
            "suspected_component": c.suspected_component,
        }
        for c in clusters
    ]
    return result


def _repo_tree_hint(repo_root: Path) -> str:
    """给修复分析用的控制层目录结构摘要。"""
    candidates = [
        "src/fnixagent/core/runner.py",
        "src/fnixagent/core/agent/loop.py",
        "src/fnixagent/core/mcp/",
        "src/fnixagent/core/memory/",
        "src/fnixagent/core/orchestrator/",
        "src/fnixagent/graph/",
        "src/fnixagent/core/tools/",
    ]
    lines = []
    for rel in candidates:
        p = repo_root / rel
        if p.is_dir():
            files = [f.name for f in sorted(p.glob("*.py"))][:15]
            lines.append(f"{rel}/ -> {', '.join(files)}")
        elif p.exists():
            lines.append(f"{rel} ({p.stat().st_size // 1024}KB)")
    return "\n".join(lines) or "(目录探测失败)"


# ---------------------------------------------------------------------------
# 诊断报告
# ---------------------------------------------------------------------------

def write_diagnosis(
    clusters: list[FailureCluster],
    analysis: dict[str, Any] | None,
    out_path: Path | str,
) -> Path:
    """输出修复诊断报告（Markdown）。"""
    lines = [
        "# BenchForge 失败诊断与修复方案",
        "",
        f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 失败聚类总览",
        "",
        "| 失败类型 | 数量 | 疑似组件 |",
        "|---|---|---|",
    ]
    for c in clusters:
        lines.append(f"| {c.failure_type} | {c.count} | {c.suspected_component} |")
    lines += ["", "## LLM 根因分析与修复方案", ""]
    if analysis and analysis.get("root_causes"):
        for rc in analysis["root_causes"]:
            lines += [
                f"### {rc.get('failure_type', '?')}",
                f"- 疑似文件: {', '.join(rc.get('suspected_files', [])) or '待定位'}",
                f"- 根因: {rc.get('root_cause', '')}",
                f"- 修复方案: {rc.get('fix_plan', '')}",
                f"- 风险: {rc.get('risk', 'unknown')}",
                "",
            ]
    else:
        lines.append("（未生成 LLM 修复方案；请审阅上方聚类后人工定位）")
        if analysis and analysis.get("raw_response"):
            lines += ["", "### 模型原始回复（供人工参考）", "",
                      "```", analysis["raw_response"][:1500], "```"]
    out = Path(out_path)
    out.write_text("\n".join(lines), "utf-8")
    return out
