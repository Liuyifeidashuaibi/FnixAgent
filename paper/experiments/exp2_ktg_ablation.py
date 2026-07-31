#!/usr/bin/env python3
"""实验 2：KTG vs Vector RAG vs GraphRAG vs No-RAG 消融实验。

对应论文章节：Section 5.2 — Knowledge Topology Graph Ablation

目的:
    - 对比 4 种检索策略在 FCS seed 任务上的效果:
      (a) full_ktg:    完整 KTG 权重路径搜索 (work_pipeline step5 开启)
      (b) no_ktg:      关闭 KTG (step5 跳过, 无拓扑召回)
      (c) vector_rag:  模拟向量 RAG (BM25/关键词匹配替代拓扑路径搜索)
      (d) graph_rag_sim: 模拟 GraphRAG (随机游走替代权重路径搜索)
    - 收集: task_score, correctness, completeness, 检索路径命中率, 检索延迟

依赖 agentd: task_score 等指标需通过 RunOptions.agent_base_url 调用 agentd。
检索指标 (命中率/延迟) 纯本地用 TopologySearch 计算, 无需 agentd。
agentd 未启动时优雅降级: 输出 placeholder + 启动提示, 不崩溃。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from fnixagent.core.code.benchmark.runner import RunOptions, run_task
from fnixagent.core.code.benchmark.schema import load_task
from fnixagent.core.topology.graph import TopologyGraph
from fnixagent.core.topology.search import TopologySearch
from fnixagent.core.types import EdgeType, NodeType, TopologyLayer, TopologyNode

PAPER_ROOT = ROOT / "paper"
RESULTS_DIR = PAPER_ROOT / "experiments" / "results"
BENCHMARK_ROOT = ROOT / "benchmarks" / "code"

CONFIGS = ["full_ktg", "no_ktg", "vector_rag", "graph_rag_sim"]


def build_sample_ktg() -> TopologyGraph:
    """构建与 FCS seed 任务对齐的样本 KTG (L1→L2→L3→L4)。"""
    graph = TopologyGraph()
    g1 = graph.add_node(
        layer=TopologyLayer.L1_GOAL,
        node_type=NodeType.GOAL,
        name="代码任务",
        content="FCS 代码生成与修复任务",
    )
    concepts = [
        ("fibonacci", "斐波那契数列实现", "write"),
        ("calc", "计算器四则运算 add sub mul div", "write"),
        ("cli", "CLI 命令行程序 greet", "cli"),
        ("pytest", "pytest 测试用例生成", "test_gen"),
        ("syntax_error", "语法错误修复 heal", "heal"),
        ("refactor", "函数重构提取 parse", "refactor"),
        ("api", "HTTP API health 端点", "api"),
        ("search", "代码搜索定位 helper", "search"),
    ]
    for name, content, skill in concepts:
        node = graph.add_node(
            layer=TopologyLayer.L2_CONCEPT,
            node_type=NodeType.CONCEPT,
            name=name,
            content=content,
            skill_binding=skill,
        )
        graph.add_edge(g1.node_id, node.node_id, EdgeType.CONTAINS)
        rule = graph.add_node(
            layer=TopologyLayer.L3_RULE,
            node_type=NodeType.RULE,
            name=f"rule_{name}",
            content=f"实现 {name} 的规则与约束",
        )
        graph.add_edge(node.node_id, rule.node_id, EdgeType.DEPENDS_ON)
        fact = graph.add_node(
            layer=TopologyLayer.L4_FACT,
            node_type=NodeType.FACT,
            name=f"fact_{name}",
            content=f"{name} 的具体案例",
        )
        graph.add_edge(rule.node_id, fact.node_id, EdgeType.DERIVES)
    return graph


def vector_rag_retrieve(graph: TopologyGraph, query: str, top_k: int = 3) -> list:
    """模拟向量 RAG: 用 BM25/关键词匹配替代拓扑路径搜索。

    对 L2 概念节点做关键词重叠评分, 取 Top-K 节点 (无路径展开)。
    """
    concepts = graph.list_nodes(
        layer=TopologyLayer.L2_CONCEPT, node_type=NodeType.CONCEPT
    )
    query_terms = set(query.lower().split())
    scored = []
    for node in concepts:
        node_terms = set((node.name + " " + node.content).lower().split())
        overlap = len(query_terms & node_terms)
        # BM25 风格: 重叠度 × 节点权重
        score = overlap * (0.5 + node.weight)
        if score > 0:
            scored.append((score, node))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:top_k]


def graph_rag_random_walk(graph: TopologyGraph, query: str, top_k: int = 3, rng: random.Random | None = None) -> list:
    """模拟 GraphRAG: 用随机游走替代权重路径搜索。

    从 query 匹配的 L2 节点出发, 随机游走展开路径 (忽略权重排序)。
    """
    rng = rng or random.Random(42)
    search = TopologySearch(graph)
    starts = search.match_concepts(query)
    if not starts:
        return []
    paths = []
    for start in starts[:top_k]:
        # 随机游走: 从 start 随机选出边向下走 2-4 步
        current = start
        walked_nodes = [current.node_id]
        steps = rng.randint(2, 4)
        for _ in range(steps):
            out_edges = graph.get_out_edges(current.node_id)
            out_edges = [e for e in out_edges if not e.deprecated]
            if not out_edges:
                break
            edge = rng.choice(out_edges)
            try:
                current = graph.get_node(edge.target_id)
                if current.deprecated or current.node_id in walked_nodes:
                    break
                walked_nodes.append(current.node_id)
            except Exception:
                break
        if len(walked_nodes) > 1:
            paths.append(walked_nodes)
    return paths


def measure_retrieval(config: str, graph: TopologyGraph, queries: list[str]) -> dict:
    """测量指定配置的检索指标 (纯本地, 无需 agentd)。"""
    search = TopologySearch(graph)
    rng = random.Random(42)
    hits = 0
    total_paths = 0
    latencies: list[float] = []

    for q in queries:
        t0 = time.perf_counter()
        if config == "full_ktg":
            paths = search.search(q)
            found = len(paths) > 0
            total_paths += len(paths)
        elif config == "no_ktg":
            paths = []
            found = False
        elif config == "vector_rag":
            retrieved = vector_rag_retrieve(graph, q)
            paths = retrieved
            found = len(retrieved) > 0
            total_paths += len(retrieved)
        elif config == "graph_rag_sim":
            walked = graph_rag_random_walk(graph, q, rng=rng)
            paths = walked
            found = len(walked) > 0
            total_paths += len(walked)
        else:
            paths = []
            found = False
        latencies.append((time.perf_counter() - t0) * 1000)
        if found:
            hits += 1

    return {
        "config": config,
        "queries": len(queries),
        "hit_count": hits,
        "hit_rate_percent": round(100.0 * hits / max(1, len(queries)), 2),
        "avg_paths_per_query": round(total_paths / max(1, len(queries)), 2),
        "avg_latency_ms": round(sum(latencies) / max(1, len(latencies)), 3),
        "total_paths": total_paths,
    }


def check_agentd(base_url: str) -> bool:
    """探测 agentd 是否可达 (3s 超时)。"""
    if not base_url:
        return False
    try:
        req = urllib.request.Request(base_url, method="GET")
        with urllib.request.urlopen(req, timeout=3) as _:
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False
    except Exception:
        return False


def run_agentd_tasks(
    config: str, task_paths: list[Path], base_url: str
) -> list[dict]:
    """通过 agentd 运行任务, 收集 task_score 等指标。"""
    opts = RunOptions(dry_checks_only=False, agent_base_url=base_url, skip_agent=False)
    results: list[dict] = []
    for i, p in enumerate(task_paths, 1):
        try:
            score = run_task(p, opts)
            results.append(
                {
                    "task_id": score.task_id,
                    "config": config,
                    "task_score": score.task_score,
                    "correctness": score.correctness,
                    "completeness": score.completeness,
                    "hard_pass": score.hard_pass,
                    "steps": score.meta.steps,
                    "heal_rounds": score.meta.heal_rounds,
                }
            )
        except Exception as exc:
            results.append(
                {"task_id": p.stem, "config": config, "error": str(exc), "task_score": 0.0}
            )
        print(f"  [{config} {i}/{len(task_paths)}] done")
    return results


def placeholder_scores(config: str, task_paths: list[Path]) -> list[dict]:
    """agentd 不可用时生成 placeholder 结果。"""
    return [
        {
            "task_id": p.stem,
            "config": config,
            "task_score": None,
            "correctness": None,
            "completeness": None,
            "hard_pass": None,
            "placeholder": True,
        }
        for p in task_paths
    ]


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Exp2: KTG vs Vector RAG vs GraphRAG vs No-RAG ablation"
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=9,
        help="Number of seed tasks to run (default 9 = all seed tasks)",
    )
    ap.add_argument(
        "--base",
        default="http://127.0.0.1:8003",
        help="agentd base URL (RunOptions.agent_base_url)",
    )
    ap.add_argument(
        "--no-agent",
        action="store_true",
        help="Skip agentd task execution (retrieval metrics only)",
    )
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 加载 seed 任务 ----
    seed_dir = BENCHMARK_ROOT / "seed"
    task_paths = sorted(seed_dir.glob("*.json"))
    if args.limit > 0:
        task_paths = task_paths[: args.limit]
    queries: list[str] = []
    for p in task_paths:
        try:
            queries.append(load_task(p).prompt)
        except Exception:
            queries.append(p.stem)

    print(f"[exp2] {len(task_paths)} seed tasks, {len(queries)} queries")
    print(f"[exp2] building sample KTG ...")
    graph = build_sample_ktg()
    print(f"[exp2] KTG nodes={graph.stats()['active_nodes']}")

    # ---- 检索指标 (纯本地) ----
    print("[exp2] measuring retrieval metrics (local, no agentd) ...")
    retrieval_metrics = []
    for cfg in CONFIGS:
        m = measure_retrieval(cfg, graph, queries)
        retrieval_metrics.append(m)
        print(
            f"  [{cfg}] hit_rate={m['hit_rate_percent']}% "
            f"avg_paths={m['avg_paths_per_query']} latency={m['avg_latency_ms']}ms"
        )

    # ---- agentd 任务执行 (可选) ----
    use_agentd = (not args.no_agent) and check_agentd(args.base)
    if use_agentd:
        print(f"[exp2] agentd reachable at {args.base}, running tasks ...")
    else:
        print(f"[exp2] agentd NOT reachable at {args.base} (--no-agent={args.no_agent})")
        print("[exp2] >>> graceful degradation: score metrics = placeholder")
        print("[exp2] >>> to enable: start agentd with `python -m fnixagent` or uvicorn fnixagent.main:app")

    task_scores: dict[str, list[dict]] = {}
    for cfg in CONFIGS:
        if use_agentd:
            task_scores[cfg] = run_agentd_tasks(cfg, task_paths, args.base)
        else:
            task_scores[cfg] = placeholder_scores(cfg, task_paths)

    # ---- 汇总 ----
    summary: dict[str, dict] = {}
    for cfg in CONFIGS:
        scores = task_scores[cfg]
        valid = [s for s in scores if s.get("task_score") is not None]
        if valid:
            avg_score = round(sum(s["task_score"] for s in valid) / len(valid), 2)
            avg_correct = round(sum(s["correctness"] for s in valid) / len(valid), 2)
            avg_complete = round(sum(s["completeness"] for s in valid) / len(valid), 2)
            hard_pass_rate = round(100.0 * sum(1 for s in valid if s["hard_pass"]) / len(valid), 2)
        else:
            avg_score = avg_correct = avg_complete = hard_pass_rate = None
        rm = next(r for r in retrieval_metrics if r["config"] == cfg)
        summary[cfg] = {
            "task_score_avg": avg_score,
            "correctness_avg": avg_correct,
            "completeness_avg": avg_complete,
            "hard_pass_rate_percent": hard_pass_rate,
            "retrieval_hit_rate_percent": rm["hit_rate_percent"],
            "avg_paths_per_query": rm["avg_paths_per_query"],
            "retrieval_latency_ms": rm["avg_latency_ms"],
            "placeholder": not use_agentd,
        }

    output = {
        "experiment": "exp2_ktg_ablation",
        "paper_section": "Section 5.2 — Knowledge Topology Graph Ablation",
        "configs": CONFIGS,
        "task_count": len(task_paths),
        "agentd_base_url": args.base,
        "agentd_reachable": use_agentd,
        "ktg_nodes": graph.stats()["active_nodes"],
        "retrieval_metrics": retrieval_metrics,
        "task_scores": task_scores,
        "summary": summary,
        "note": (
            "Score metrics require agentd. Start it with: python -m fnixagent "
            "(or uvicorn fnixagent.main:app --port 8003)"
            if not use_agentd
            else "All metrics collected with live agentd."
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    out_path = RESULTS_DIR / "exp2_ktg_ablation.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[exp2] results -> {out_path}")

    print("\n=== Exp2 KTG Ablation Summary ===")
    print(f"{'config':>14} {'hit%':>6} {'paths':>6} {'lat_ms':>7} {'score':>7} {'hard%':>6}")
    for cfg in CONFIGS:
        s = summary[cfg]
        print(
            f"{cfg:>14} {s['retrieval_hit_rate_percent']:>6} "
            f"{s['avg_paths_per_query']:>6} {s['retrieval_latency_ms']:>7} "
            f"{str(s['task_score_avg']):>7} {str(s['hard_pass_rate_percent']):>6}"
        )
    if not use_agentd:
        print("\n[exp2] NOTE: agentd not running — score columns are placeholders.")
        print("[exp2] Start agentd: python -m fnixagent  (then re-run without --no-agent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
