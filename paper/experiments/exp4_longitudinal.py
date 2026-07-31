#!/usr/bin/env python3
"""实验 4：纵向自进化效果 (模拟长期使用)。

对应论文章节：Section 5.4 — Longitudinal Self-Evolution

目的:
    - 模拟同一用户在 1 / 7 / 30 / 90 天使用后 KTG 权重变化
    - 用 flywheel/climbing.py (HillClimbingFlywheel) 的逻辑, 注入模拟 TraceRecord 序列
    - 收集: KTG 节点数变化、平均权重变化、高频范式固化数、stale 节点淘汰数
    - 验证 MFP 第四阶 (爬坡进化) 的长期收敛性与知识固化效果

纯本地实验: 不依赖 agentd / LLM, 通过注入模拟轨迹驱动 KTG/MFP 权重演化。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.flywheel.climbing import HillClimbingFlywheel
from fnixagent.core.flywheel.trace import TraceStore
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.topology.search import TopologySearch
from fnixagent.core.types import (
    EdgeType,
    FlywheelStage,
    NodeType,
    ReasoningMode,
    TopologyLayer,
    TraceRecord,
)

PAPER_ROOT = ROOT / "paper"
RESULTS_DIR = PAPER_ROOT / "experiments" / "results"

# 模拟时间跨度 (天)
HORIZONS = [1, 7, 30, 90]
# 每天平均任务数 (模拟用户使用强度)
TASKS_PER_DAY = 12
# 高频范式种子 (模拟重复出现的任务模式)
PATTERN_SEEDS = [
    "实现一个 fibonacci 函数",
    "编写 pytest 测试用例",
    "修复语法错误",
    "重构提取解析函数",
    "创建 CLI 问候程序",
    "实现计算器四则运算",
]


def seed_topology(graph: TopologyGraph) -> dict[str, str]:
    """注入初始 KTG 拓扑 (L1 目标 → L2 概念 → L3 规则 → L4 事实)。

    构造一个小型但完整的四层拓扑, 模拟冷启动后的初始知识库。
    返回 concept_id → name 映射, 供轨迹注入时引用。
    """
    ids: dict[str, str] = {}

    # L1 目标层
    g1 = graph.add_node(
        layer=TopologyLayer.L1_GOAL,
        node_type=NodeType.GOAL,
        name="代码生成与修复",
        content="用户代码任务的顶层目标",
    )
    ids["L1_root"] = g1.node_id

    # L2 概念层 (STP 技能绑定锚点)
    concepts = [
        ("fibonacci", "斐波那契数列实现", "write"),
        ("pytest", "pytest 测试生成", "test_gen"),
        ("syntax_fix", "语法错误修复", "heal"),
        ("refactor", "函数重构提取", "refactor"),
        ("cli", "CLI 程序构建", "cli"),
        ("calc", "四则运算计算器", "write"),
        ("api", "HTTP API 实现", "api"),
        ("search", "代码搜索定位", "search"),
    ]
    for name, content, skill in concepts:
        node = graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name=name,
            content=content,
            skill_binding=skill,
        )
        ids[name] = node.node_id
        graph.add_edge(g1.node_id, node.node_id, EdgeType.CONTAINS)

    # L3 规则层 (每个概念下挂一条规则)
    rules = [
        ("rule_fib", "fibonacci", "fib(0)=0, fib(1)=1, 递归/迭代实现"),
        ("rule_test", "pytest", "用 assert 验证函数输出, 覆盖边界值"),
        ("rule_syntax", "syntax_fix", "定位 SyntaxError 行号, 修正缩进/括号"),
        ("rule_refactor", "refactor", "提取重复逻辑为独立函数, 保持行为不变"),
        ("rule_cli", "cli", "argparse/sys.argv 解析参数, print 输出"),
        ("rule_calc", "calc", "def calc(a,b): 支持 + - * /"),
    ]
    for rule_name, concept_key, content in rules:
        if concept_key not in ids:
            continue
        r = graph.add_node(
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.RULE,
            name=rule_name,
            content=content,
        )
        ids[rule_name] = r.node_id
        graph.add_edge(ids[concept_key], r.node_id, EdgeType.DEPENDS_ON)

    # L4 事实层 (少量具体案例)
    facts = [
        ("fact_fib0", "rule_fib", "fib(10)=55"),
        ("fact_test0", "rule_test", "assert calc(2,3)==5"),
    ]
    for fact_name, rule_key, content in facts:
        if rule_key not in ids:
            continue
        f = graph.add_node(
            layer=TopologyLayer.L4_FACT,
            node_type=NodeType.FACT,
            name=fact_name,
            content=content,
        )
        ids[fact_name] = f.node_id
        graph.add_edge(ids[rule_key], f.node_id, EdgeType.DERIVES)

    return ids


def generate_trace_sequence(
    days: int,
    concept_ids: dict[str, str],
    rng: random.Random,
) -> list[TraceRecord]:
    """生成 N 天的模拟 TraceRecord 序列。

    模拟真实用户使用模式:
      - 高频范式重复出现 (PATTERN_SEEDS)
      - 80% 任务成功, 20% 失败 (触发反思)
      - concept_path 从 L2 概念中采样
    """
    traces: list[TraceRecord] = []
    base_time = time.time() - days * 86400
    total_tasks = days * TASKS_PER_DAY
    concept_names = [k for k in concept_ids if not k.startswith(("L1", "rule", "fact"))]

    for i in range(total_tasks):
        # 70% 从高频范式采样, 30% 随机组合 (模拟长尾任务)
        if rng.random() < 0.7:
            goal = rng.choice(PATTERN_SEEDS)
        else:
            goal = f"任务 #{i}: " + rng.choice(PATTERN_SEEDS)

        # 概念路径: 1-3 个 L2 概念
        path_len = rng.randint(1, 3)
        path = [rng.choice(concept_names) for _ in range(path_len)] if concept_names else []
        concept_path = [concept_ids[n] for n in path if n in concept_ids]

        success = rng.random() < 0.8
        tool_calls = [
            {"name": "write_file", "status": "success" if success else "failed"},
            {"name": "pytest", "status": "success" if success else "failed"},
        ]
        trace = TraceRecord(
            trace_id=f"sim_{i}",
            task_id=f"task_{i}",
            goal=goal,
            mode=ReasoningMode.REACT,
            concept_path=concept_path,
            tool_calls=tool_calls,
            success=success,
            duration_ms=rng.uniform(500, 5000),
            usage_tokens=rng.randint(200, 2000),
            reflection_score=rng.uniform(0.4, 0.9),
            created_at=base_time + (i / total_tasks) * days * 86400,
        )
        traces.append(trace)
    return traces


def graph_snapshot(graph: TopologyGraph) -> dict:
    """采集 KTG 当前状态快照指标。"""
    nodes = graph.list_nodes(include_deprecated=False)
    all_nodes = graph.list_nodes(include_deprecated=True)
    active_weights = [n.weight for n in nodes if not n.deprecated]
    stale = sum(1 for n in all_nodes if n.metadata.get("stale"))
    deprecated = sum(1 for n in all_nodes if n.deprecated)
    avg_weight = (
        round(sum(active_weights) / len(active_weights), 4) if active_weights else 0.0
    )
    # L3 规则节点数 (高频范式固化指标)
    rule_nodes = graph.list_nodes(
        layer=TopologyLayer.L3_RULE, node_type=NodeType.RULE, include_deprecated=False
    )
    solidified = sum(1 for n in rule_nodes if n.metadata.get("source") == "hill_climbing")
    return {
        "total_nodes": len(all_nodes),
        "active_nodes": len(nodes),
        "deprecated_nodes": deprecated,
        "stale_nodes": stale,
        "avg_weight": avg_weight,
        "max_weight": round(max(active_weights), 4) if active_weights else 0.0,
        "min_weight": round(min(active_weights), 4) if active_weights else 0.0,
        "l3_rule_nodes": len(rule_nodes),
        "solidified_patterns": solidified,
        "active_edges": len(graph.list_edges(include_deprecated=False)),
    }


def simulate_horizon(days: int, rng: random.Random) -> dict:
    """模拟指定天数后的 KTG 演化状态。"""
    graph = TopologyGraph()
    concept_ids = seed_topology(graph)
    initial = graph_snapshot(graph)

    traces = generate_trace_sequence(days, concept_ids, rng)

    # 用 TraceStore 持久化模拟轨迹 (临时目录)
    tmp_store_dir = RESULTS_DIR / f".tmp_trace_{days}d"
    tmp_store_dir.mkdir(parents=True, exist_ok=True)
    store = TraceStore(str(tmp_store_dir))
    for t in traces:
        store.append(t)

    # 运行爬坡进化飞轮 (MFP 第 4 阶)
    flywheel = HillClimbingFlywheel(graph=graph, trace_store=store, evolution_interval=100)
    evolution_results: list[dict] = []
    # 分批触发进化 (每 100 个任务触发一次)
    for batch_start in range(0, len(traces), 100):
        batch = traces[batch_start : batch_start + 100]
        try:
            result = flywheel.run(traces=batch)
            evolution_results.append(result)
        except Exception as exc:
            evolution_results.append({"error": f"{type(exc).__name__}: {exc}"})

    final = graph_snapshot(graph)

    # 检索路径命中率 (用 TopologySearch 在最终图上测试)
    search = TopologySearch(graph)
    hit = 0
    latencies: list[float] = []
    for seed in PATTERN_SEEDS:
        t0 = time.perf_counter()
        paths = search.search(seed)
        latencies.append((time.perf_counter() - t0) * 1000)
        if paths:
            hit += 1
    retrieval_hit_rate = round(100.0 * hit / len(PATTERN_SEEDS), 2)
    avg_retrieval_ms = round(sum(latencies) / len(latencies), 3) if latencies else 0.0

    # 清理临时轨迹目录
    try:
        trace_file = tmp_store_dir / "traces.jsonl"
        if trace_file.is_file():
            trace_file.unlink()
        tmp_store_dir.rmdir()
    except OSError:
        pass

    return {
        "horizon_days": days,
        "simulated_tasks": len(traces),
        "evolution_runs": len(evolution_results),
        "initial": initial,
        "final": final,
        "delta": {
            "active_nodes": final["active_nodes"] - initial["active_nodes"],
            "avg_weight": round(final["avg_weight"] - initial["avg_weight"], 4),
            "solidified_patterns": final["solidified_patterns"] - initial["solidified_patterns"],
            "stale_nodes": final["stale_nodes"] - initial["stale_nodes"],
            "deprecated_nodes": final["deprecated_nodes"] - initial["deprecated_nodes"],
        },
        "retrieval_hit_rate_percent": retrieval_hit_rate,
        "avg_retrieval_latency_ms": avg_retrieval_ms,
        "last_evolution_result": evolution_results[-1] if evolution_results else {},
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Exp4: Longitudinal self-evolution simulation (no LLM)"
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible simulation",
    )
    ap.add_argument(
        "--horizons",
        type=str,
        default=",".join(str(h) for h in HORIZONS),
        help="Comma-separated day horizons (default: 1,7,30,90)",
    )
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    horizons = [int(h.strip()) for h in args.horizons.split(",") if h.strip()]
    rng = random.Random(args.seed)

    print(f"[exp4] simulating longitudinal self-evolution (seed={args.seed})")
    print(f"[exp4] horizons: {horizons}")

    results: list[dict] = []
    for days in horizons:
        print(f"[exp4] simulating {days} day(s) ...")
        r = simulate_horizon(days, rng)
        results.append(r)
        d = r["delta"]
        print(
            f"  [{days}d] tasks={r['simulated_tasks']} "
            f"nodes={r['initial']['active_nodes']}→{r['final']['active_nodes']} "
            f"avg_w={r['final']['avg_weight']} "
            f"solidified={r['final']['solidified_patterns']} "
            f"stale={r['final']['stale_nodes']} "
            f"retrieval_hit={r['retrieval_hit_rate_percent']}%"
        )

    output = {
        "experiment": "exp4_longitudinal",
        "paper_section": "Section 5.4 — Longitudinal Self-Evolution",
        "random_seed": args.seed,
        "tasks_per_day": TASKS_PER_DAY,
        "pattern_seeds": PATTERN_SEEDS,
        "horizons": results,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    out_path = RESULTS_DIR / "exp4_longitudinal.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[exp4] results -> {out_path}")

    # ---- 摘要表 ----
    print("\n=== Exp4 Longitudinal Summary ===")
    print(f"{'days':>5} {'tasks':>6} {'nodes':>6} {'avg_w':>7} {'solid':>6} {'stale':>6} {'hit%':>6}")
    for r in results:
        print(
            f"{r['horizon_days']:>5} {r['simulated_tasks']:>6} "
            f"{r['final']['active_nodes']:>6} {r['final']['avg_weight']:>7} "
            f"{r['final']['solidified_patterns']:>6} {r['final']['stale_nodes']:>6} "
            f"{r['retrieval_hit_rate_percent']:>6}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
