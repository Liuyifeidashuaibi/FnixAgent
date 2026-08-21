"""BenchForge CLI — `fnixagent bench <action>` 的入口实现。

四个动作：
  fetch   拉取并缓存全部六大基准数据集
  run     全量执行评测（断点续跑，不抽样、不过滤）
  report  生成 Markdown + HTML 汇总报告
  fix     构建回归集 + 失败聚类 + LLM 根因分析/修复诊断
"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

_logger = logging.getLogger("fnixagent.bench")

DEFAULT_DATASET_ROOT = Path("benchmarks/benchforge/datasets")
DEFAULT_RUNS_ROOT = Path("benchmarks/benchforge/runs")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _datasets_list(arg: str) -> list[str] | None:
    return [d.strip() for d in arg.split(",") if d.strip()] or None


def cmd_fetch(args) -> int:
    from fnixagent.bench.datasets import DatasetManager

    mgr = DatasetManager(DEFAULT_DATASET_ROOT)
    total = 0
    names = _datasets_list(args.dataset)
    for name in (names or ["web-bench", "workbuddy-bench", "vibe-code-bench",
                           "prototypebench", "gaia", "swe-bench-lite"]):
        count = sum(1 for _ in mgr.load(name, refresh=args.refresh))
        status = f"{count} 条" if count else f"失败: {mgr.errors.get(name, '未知错误')}"
        print(f"[fetch] {name}: {status}")
        total += count
    print(f"[fetch] 累计可用任务 {total} 条 -> {DEFAULT_DATASET_ROOT}")
    return 0 if total else 1


def _probe_quota(model: str) -> tuple[bool, str]:
    """运行前配额预探：发一条最小请求，判断被测模型当前是否可用。

    避免配额已耗尽时仍启动全量评测、空转刷 1406 次 403。
    返回 (可用?, 说明)。探测自身异常（网络等）不阻断，交由运行期熔断处理。
    """
    try:
        from fnixagent.core.llm.adapter import LLMAdapter

        adapter = LLMAdapter(
            api_key=os.getenv("BENCH_API_KEY", ""),
            base_url=os.getenv("BENCH_BASE_URL", ""),
            model_name=model,
        )
        if not adapter.is_configured:
            return False, "LLM 未配置"

        async def _ping() -> str:
            try:
                await adapter.chat(
                    [{"role": "user", "content": "ping"}], tools=None, max_tokens=4,
                )
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return f"err:{exc}"

        result = asyncio.run(_ping())
        if result == "ok":
            return True, "配额探测通过"
        msg = result[4:]
        if any(k in msg for k in ("403", "quota", "insufficient", "401", "404")):
            return False, f"配额/鉴权不可用: {msg[:160]}"
        # 其他错误（超时/网络）不当作配额问题，放行让运行期处理
        return True, f"探测返回非配额错误（放行）: {msg[:120]}"
    except Exception as exc:  # noqa: BLE001
        return True, f"探测器异常（放行）: {exc}"


def cmd_run(args) -> int:
    from fnixagent.bench.datasets import DatasetManager
    from fnixagent.bench.judge import Judge
    from fnixagent.bench.runner import BenchRunner

    model = os.getenv("BENCH_MODEL", "") or "configured-model"

    # 运行前配额预探（--no-quota-probe 可跳过）
    if not args.no_quota_probe:
        ok, info = _probe_quota(model)
        print(f"[quota-probe] {model}: {info}", file=sys.stderr)
        if not ok:
            print("[run] 被测模型配额/鉴权不可用，已阻止启动。"
                  "请更换 BENCH_MODEL 或待配额恢复后重跑。"
                  "（如确认要强制执行，加 --no-quota-probe）", file=sys.stderr)
            return 3

    mgr = DatasetManager(DEFAULT_DATASET_ROOT)
    tasks = list(mgr.load_all(_datasets_list(args.dataset), refresh=False))
    if args.limit and args.limit > 0:
        # --limit 仅用于本地 smoke test；正式全量评测不得使用
        print(f"[warn] --limit={args.limit} 冒烟模式：只跑前 {args.limit} 条"
              "（正式全量评测请去掉该参数）", file=sys.stderr)
        tasks = tasks[: args.limit]
    if not tasks:
        print("[run] 没有可执行任务；请先 `fnixagent bench fetch`", file=sys.stderr)
        return 1
    if mgr.errors:
        for name, err in mgr.errors.items():
            print(f"[fetch-error] {name}: {err}", file=sys.stderr)

    # 判定模型（默认复用被测模型配置）
    judge_llm = None
    if not args.no_llm_judge:
        try:
            from fnixagent.core.llm.adapter import LLMAdapter

            judge_adapter = LLMAdapter(
                api_key=os.getenv("BENCH_API_KEY", ""),
                base_url=os.getenv("BENCH_BASE_URL", ""),
                model_name=os.getenv("BENCH_JUDGE_MODEL") or os.getenv("BENCH_MODEL", ""),
            )
            if judge_adapter.is_configured:
                judge_llm = judge_adapter.chat
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] LLM 判定器不可用，转纯启发式: {exc}", file=sys.stderr)

    judge = Judge(llm_call=judge_llm, use_llm_for_ambiguous=not args.no_llm_judge)
    run_dir = Path(args.out) if args.out else DEFAULT_RUNS_ROOT / time.strftime("%Y%m%d-%H%M%S")
    runner = BenchRunner(
        output_dir=run_dir, model=model,
        max_steps=args.max_steps, task_timeout=args.timeout,
        max_concurrency=args.concurrency,
        keep_workspaces=args.keep_workspaces,
        quota_abort_threshold=args.quota_abort,
    )

    def _progress(done: int, total: int, run) -> None:
        if run.status.value == "success":
            mark = "OK "
        elif run.status.value == "infra_skip":
            mark = "SKP"
        else:
            mark = "ERR"
        print(f"[{done}/{total}] {mark} {run.dataset}/{run.task_id}"
              f" {run.duration_ms / 1000:.0f}s tokens={run.total_tokens}"
              + (f" fail={run.failure_type}" if run.failure_type else ""))

    summary = runner.run_all(tasks, judge=judge, progress=_progress)
    totals = summary.totals
    print(f"\n[done] run={runner.run_id}")
    print(f"  总任务 {totals['total']} 成功 {totals['success']} 失败 {totals['failure']}"
          f" 配额跳过 {totals.get('infra_skip', 0)}"
          f" 成功率 {totals['success_rate'] * 100:.1f}%（分母=成功+失败）")
    if summary.note:
        print(f"  备注: {summary.note}")
    print(f"  产物目录: {run_dir}")
    if runner._quota_aborted:
        return 4  # 配额熔断：非能力失败，提示需要恢复配额后重跑
    return 0 if totals["failure"] == 0 else 2


def cmd_report(args) -> int:
    from fnixagent.bench.report import load_summary, write_html, write_markdown

    run_dir = Path(args.run)
    summary = load_summary(run_dir)
    md = write_markdown(summary, run_dir / "report.md")
    hp = write_html(summary, run_dir / "report.html")
    print(f"[report] Markdown -> {md}")
    print(f"[report] HTML     -> {hp}")
    return 0


def cmd_fix(args) -> int:
    from fnixagent.bench.fixloop import (
        analyze_with_llm,
        build_regression_set,
        cluster_failures,
        write_diagnosis,
    )

    run_dir = Path(args.run)
    reg = build_regression_set(run_dir)
    clusters = cluster_failures(reg)
    print(f"[fix] 回归集: {reg}（失败 {sum(c.count for c in clusters)} 条）")
    for c in clusters:
        print(f"  - {c.failure_type}: {c.count} 条 -> {c.suspected_component}")

    analysis = None
    if not args.no_llm_analysis:
        try:
            from fnixagent.core.llm.adapter import LLMAdapter

            adapter = LLMAdapter(
                api_key=os.getenv("BENCH_API_KEY", ""),
                base_url=os.getenv("BENCH_BASE_URL", ""),
                model_name=os.getenv("BENCH_JUDGE_MODEL") or os.getenv("BENCH_MODEL", ""),
            )
            if adapter.is_configured:
                analysis = asyncio.run(
                    analyze_with_llm(clusters, adapter.chat, Path.cwd())
                )
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] LLM 根因分析失败: {exc}", file=sys.stderr)

    diag = write_diagnosis(clusters, analysis, run_dir / "fix-diagnosis.md")
    print(f"[fix] 诊断报告 -> {diag}")
    if args.apply:
        print("[fix] --apply：按诊断报告优先修复最高频失败类型"
              "（自动落盘需人工复核，当前仅生成方案）", file=sys.stderr)
    print("[fix] 修复控制层后，请重跑回归集："
          f"  fnixagent bench run --out {run_dir}  # 断点续跑会跳过已成功任务")
    return 0


def register_bench_subcommand(subparsers) -> None:
    """把 bench 子命令挂到主 CLI argparse 树。"""
    bench = subparsers.add_parser(
        "bench", help="全量基准评测与自动修复闭环（BenchForge）",
    )
    bsub = bench.add_subparsers(dest="bench_action", help="动作")

    p_fetch = bsub.add_parser("fetch", help="拉取/缓存六大基准数据集")
    p_fetch.add_argument("--dataset", default="", help="逗号分隔的数据集名（默认全部）")
    p_fetch.add_argument("--refresh", action="store_true", help="忽略缓存重新拉取")

    p_run = bsub.add_parser("run", help="全量执行评测")
    p_run.add_argument("--dataset", default="", help="逗号分隔的数据集名（默认全部）")
    p_run.add_argument("--limit", type=int, default=0, help="冒烟测试条数（正式评测勿用）")
    p_run.add_argument("--concurrency", type=int, default=4, help="并发任务数")
    p_run.add_argument("--max-steps", type=int, default=25, help="单任务最大步数")
    p_run.add_argument("--timeout", type=int, default=600, help="单任务超时（秒）")
    p_run.add_argument("--out", default="", help="产物目录（默认 benchmarks/benchforge/runs/<时间戳>）")
    p_run.add_argument("--no-llm-judge", action="store_true", help="禁用 LLM 判定（纯启发式，省配额）")
    p_run.add_argument("--keep-workspaces", action="store_true", help="保留任务工作区")
    p_run.add_argument("--quota-abort", type=int, default=15,
                       help="连续多少次配额/鉴权错误后提前熔断（默认15）")
    p_run.add_argument("--no-quota-probe", action="store_true",
                       help="跳过运行前配额预探（默认会先发一条最小请求探测配额）")

    p_report = bsub.add_parser("report", help="生成评测报告")
    p_report.add_argument("--run", required=True, help="运行产物目录")

    p_fix = bsub.add_parser("fix", help="构建回归集 + 失败聚类 + 修复诊断")
    p_fix.add_argument("--run", required=True, help="运行产物目录")
    p_fix.add_argument("--apply", action="store_true", help="尝试自动落盘修复（谨慎）")
    p_fix.add_argument("--no-llm-analysis", action="store_true", help="跳过 LLM 根因分析")

    bench.add_argument("--verbose", "-v", action="store_true", help="调试日志")


def dispatch_bench(args) -> int:
    _setup_logging(getattr(args, "verbose", False))
    action = getattr(args, "bench_action", None)
    if action == "fetch":
        return cmd_fetch(args)
    if action == "run":
        return cmd_run(args)
    if action == "report":
        return cmd_report(args)
    if action == "fix":
        return cmd_fix(args)
    print("用法: fnixagent bench {fetch|run|report|fix} ...", file=sys.stderr)
    return 64
