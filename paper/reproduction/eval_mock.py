#!/usr/bin/env python3
"""Mock LLM evaluation mode — reviewer reproduction without an API key.

This script reproduces the *structure* of the two LLM-dependent ablation
experiments (exp2: KTG retrieval ablation; exp3: MFP x DAAO factorial ablation)
without contacting any real model. It ships a lightweight, deterministic
``MockLLMAdapter`` that emits plausible placeholder scores, so a reviewer can
exercise the full result-pipeline and obtain files whose schema matches the
real experiment outputs (every placeholder is explicitly flagged).

Activating mock mode:
    export FNIX_MOCK_LLM=1            # PowerShell: $env:FNIX_MOCK_LLM="1"

Run (standalone, no project imports required):
    python paper/reproduction/eval_mock.py

Output:
    paper/experiments/results/mock_ablation_results.json

The numbers below are NOT scientific results — they are stable placeholders
that demonstrate the experiment scaffolding. To obtain real numbers, provide a
BYOK key and run the live scripts (see paper/reproduction/README.md §4).
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

# --- Path setup (repo-relative, independent of fnixagent imports) -----------
# This file lives at <repo>/paper/reproduction/eval_mock.py
ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "paper" / "experiments" / "results"

# Experiment configurations — mirror exp2_ktg_ablation.py and
# exp3_mfp_daao_ablation.py exactly so the mock output is schema-compatible.
EXP2_CONFIGS = ["full_ktg", "no_ktg", "vector_rag", "graph_rag_sim"]
EXP3_CONFIGS = ["full", "mfp_off", "daao_off", "both_off"]

# FCS seed tasks used by exp2/exp3 (see benchmarks/code/manifest.json: 9 seeds).
SEED_TASKS = [
    "seed.api.health",
    "seed.bugfix.subtract",
    "seed.cli.greet",
    "seed.heal.syntax_error",
    "seed.multi.calc_package",
    "seed.refactor.extract_parse",
    "seed.search.fix_helper",
    "seed.test_gen.counter",
    "seed.write.fibonacci",
]


class MockLLMAdapter:
    """A no-network LLM stand-in.

    ``FNIX_MOCK_LLM=1`` is the documented reviewer switch. The adapter never
    opens a socket; it derives a deterministic score from the task id and the
    active ablation config so that (a) the full-KTG / full configs score higher
    than their ablated counterparts (matching the paper's qualitative claim),
    and (b) re-runs are byte-identical.
    """

    # Per-config quality ceiling. The real system would produce these via a
    # live model; here they encode the expected *ordering* reported in the paper.
    CONFIG_QUALITY = {
        "full_ktg": 0.86,
        "vector_rag": 0.71,
        "graph_rag_sim": 0.66,
        "no_ktg": 0.52,
        "full": 0.84,
        "mfp_off": 0.69,
        "daao_off": 0.74,
        "both_off": 0.58,
    }

    def __init__(self, seed: int = 2027) -> None:
        self.rng = random.Random(seed)
        self.enabled = os.environ.get("FNIX_MOCK_LLM", "1").strip() not in ("", "0", "false", "False")

    def score_task(self, task_id: str, config: str) -> dict:
        """Return a plausible per-task score for ``config``.

        The score oscillates around the config's quality ceiling with a small
        deterministic jitter derived from the task id, so the ordering of
        configs is preserved while individual tasks vary.
        """
        ceiling = self.CONFIG_QUALITY.get(config, 0.6)
        # Stable per-task jitter in [-0.02, +0.02). Kept smaller than the
        # smallest gap between config ceilings (0.05) so the documented config
        # ordering is always preserved across tasks.
        jitter = ((_stable_id(task_id) ^ (seed_offset(config) * 2654435761)) % 40) / 1000.0 - 0.02
        task_score = max(0.0, min(1.0, round(ceiling + jitter, 3)))
        correctness = round(min(1.0, task_score + self.rng.uniform(-0.03, 0.05)), 3)
        completeness = round(min(1.0, task_score - self.rng.uniform(0.0, 0.06)), 3)
        hard_pass = task_score >= 0.70
        return {
            "task_id": task_id,
            "config": config,
            "task_score": task_score,
            "correctness": correctness,
            "completeness": completeness,
            "hard_pass": hard_pass,
            "heal_rounds": self.rng.randint(0, 2),
            "steps": self.rng.randint(8, 18),
            "placeholder": True,
        }


def seed_offset(config: str) -> int:
    return sum(ord(c) for c in config)


def _stable_id(s: str) -> int:
    """Stable integer hash for a string, independent of PYTHONHASHSEED.

    Python's built-in ``hash()`` randomizes str/bytes hashing per process by
    default, which would make the mock output non-reproducible across runs.
    This polynomial rolling hash is deterministic and sufficient for jitter.
    """
    h = 0
    for ch in s:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return h


def mock_exp2(adapter: MockLLMAdapter) -> dict:
    """Reproduce exp2 (KTG vs Vector RAG vs GraphRAG vs No-RAG) structure.

    Retrieval metrics mirror the local, no-agentd path of exp2; task scores
    are mock placeholders that preserve the paper's ordering
    (full_ktg > vector_rag > graph_rag_sim > no_ktg).
    """
    # Retrieval hit-rate per config (deterministic, plausible).
    retrieval = {
        "full_ktg": {"hit_rate_percent": 100.0, "avg_paths_per_query": 2.6, "avg_latency_ms": 1.35},
        "vector_rag": {"hit_rate_percent": 77.8, "avg_paths_per_query": 1.9, "avg_latency_ms": 0.82},
        "graph_rag_sim": {"hit_rate_percent": 66.7, "avg_paths_per_query": 1.4, "avg_latency_ms": 1.91},
        "no_ktg": {"hit_rate_percent": 0.0, "avg_paths_per_query": 0.0, "avg_latency_ms": 0.04},
    }

    summary: dict[str, dict] = {}
    task_scores: dict[str, list[dict]] = {}
    for cfg in EXP2_CONFIGS:
        scores = [adapter.score_task(t, cfg) for t in SEED_TASKS]
        task_scores[cfg] = scores
        rm = retrieval[cfg]
        avg_score = round(sum(s["task_score"] for s in scores) / len(scores), 3)
        avg_correct = round(sum(s["correctness"] for s in scores) / len(scores), 3)
        avg_complete = round(sum(s["completeness"] for s in scores) / len(scores), 3)
        hard_rate = round(100.0 * sum(1 for s in scores if s["hard_pass"]) / len(scores), 2)
        summary[cfg] = {
            "task_score_avg": avg_score,
            "correctness_avg": avg_correct,
            "completeness_avg": avg_complete,
            "hard_pass_rate_percent": hard_rate,
            "retrieval_hit_rate_percent": rm["hit_rate_percent"],
            "avg_paths_per_query": rm["avg_paths_per_query"],
            "retrieval_latency_ms": rm["avg_latency_ms"],
            "placeholder": True,
        }

    return {
        "experiment": "exp2_ktg_ablation_mock",
        "paper_section": "Section 5.2 — Knowledge Topology Graph Ablation (MOCK)",
        "configs": EXP2_CONFIGS,
        "task_count": len(SEED_TASKS),
        "agentd_reachable": False,
        "mock_llm": True,
        "retrieval_metrics": [
            {"config": c, **retrieval[c]} for c in EXP2_CONFIGS
        ],
        "task_scores": task_scores,
        "summary": summary,
        "note": (
            "MOCK placeholders produced by paper/reproduction/eval_mock.py "
            "(FNIX_MOCK_LLM=1). Retrieval metrics are deterministic; task scores "
            "are NOT scientific results. For live numbers, start agentd and run "
            "paper/experiments/exp2_ktg_ablation.py without --no-agent."
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def mock_exp3(adapter: MockLLMAdapter) -> dict:
    """Reproduce exp3 (MFP x DAAO 2x2 factorial) structure.

    Routing + MFP metrics mirror the local path of exp3; task scores are mock
    placeholders that preserve the paper's ordering (full > daao_off >
    mfp_off > both_off), yielding a positive self-evolution gain.
    """
    # Routing summary per config (deterministic).
    routing = {
        "full": {"avg_max_steps": 14.2, "modes": {"react": 6, "plan_execute": 3}},
        "mfp_off": {"avg_max_steps": 14.2, "modes": {"react": 6, "plan_execute": 3}},
        "daao_off": {"avg_max_steps": 16.0, "modes": {"react": 9}},
        "both_off": {"avg_max_steps": 16.0, "modes": {"react": 9}},
    }
    # MFP evolution only fires when mfp_on=True (full, daao_off).
    mfp = {
        "full": {"evolution_runs": 1, "weak_links_fixed": 2, "patterns_solidified": 2, "stale_nodes": 1},
        "mfp_off": {"evolution_runs": 0, "weak_links_fixed": 0, "patterns_solidified": 0, "stale_nodes": 0},
        "daao_off": {"evolution_runs": 1, "weak_links_fixed": 2, "patterns_solidified": 2, "stale_nodes": 1},
        "both_off": {"evolution_runs": 0, "weak_links_fixed": 0, "patterns_solidified": 0, "stale_nodes": 0},
    }

    summary: dict[str, dict] = {}
    for cfg in EXP3_CONFIGS:
        scores = [adapter.score_task(t, cfg) for t in SEED_TASKS]
        avg_score = round(sum(s["task_score"] for s in scores) / len(scores), 3)
        hard_rate = round(100.0 * sum(1 for s in scores if s["hard_pass"]) / len(scores), 2)
        avg_heal = round(sum(s["heal_rounds"] for s in scores) / len(scores), 2)
        avg_steps = round(sum(s["steps"] for s in scores) / len(scores), 2)
        rt = routing[cfg]
        mf = mfp[cfg]
        summary[cfg] = {
            "task_score_avg": avg_score,
            "hard_pass_rate_percent": hard_rate,
            "avg_heal_rounds": avg_heal,
            "avg_steps": avg_steps,
            "routing_avg_max_steps": rt["avg_max_steps"],
            "mode_distribution": rt["modes"],
            "mfp_patterns_solidified": mf["patterns_solidified"],
            "placeholder": True,
        }

    full_score = summary["full"]["task_score_avg"]
    baseline_score = summary["both_off"]["task_score_avg"]
    evolution_gain = round(full_score - baseline_score, 3)

    return {
        "experiment": "exp3_mfp_daao_ablation_mock",
        "paper_section": "Section 5.3 — MFP & DAAO Factorial Ablation (MOCK)",
        "design": "2x2 factorial (MFP on/off x DAAO on/off)",
        "configs": EXP3_CONFIGS,
        "task_count": len(SEED_TASKS),
        "agentd_reachable": False,
        "mock_llm": True,
        "routing_metrics": {c: routing[c] for c in EXP3_CONFIGS},
        "mfp_metrics": {c: mfp[c] for c in EXP3_CONFIGS},
        "summary": summary,
        "self_evolution_gain": evolution_gain,
        "note": (
            "MOCK placeholders produced by paper/reproduction/eval_mock.py "
            "(FNIX_MOCK_LLM=1). Routing/MFP metrics are deterministic; task "
            "scores and the self-evolution gain are NOT scientific results. "
            "For live numbers, start agentd and run "
            "paper/experiments/exp3_mfp_daao_ablation.py without --no-agent."
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def main() -> int:
    mock_env = os.environ.get("FNIX_MOCK_LLM", "1")
    if mock_env.strip() in ("0", "false", "False", ""):
        print("[eval_mock] FNIX_MOCK_LLM is disabled; nothing to do.")
        print("[eval_mock] To enable mock mode: export FNIX_MOCK_LLM=1")
        return 0

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    adapter = MockLLMAdapter(seed=2027)

    print("[eval_mock] FNIX_MOCK_LLM=1 -> generating placeholder ablation results")
    print(f"[eval_mock] seed tasks = {len(SEED_TASKS)} (FCS seed set)")

    exp2_out = mock_exp2(adapter)
    exp3_out = mock_exp3(adapter)

    bundle = {
        "experiment": "mock_ablation_results",
        "paper_section": "Section 5.2 + 5.3 — Mock Ablation (reviewer reproduction)",
        "mock_llm": True,
        "fnix_mock_llm_env": mock_env,
        "exp2_ktg_ablation": exp2_out,
        "exp3_mfp_daao_ablation": exp3_out,
        "seed_tasks": SEED_TASKS,
        "note": (
            "Generated by paper/reproduction/eval_mock.py for reviewers without "
            "an API key. All task scores are explicitly flagged placeholder=true "
            "and are deterministic. They reproduce the EXPERIMENT STRUCTURE, not "
            "the paper's quantitative claims."
        ),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    out_path = RESULTS_DIR / "mock_ablation_results.json"
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval_mock] wrote {out_path}")

    # Console summary mirroring the real experiment summary tables.
    print("\n=== Mock Exp2 KTG Ablation Summary ===")
    print(f"{'config':>14} {'hit%':>6} {'paths':>6} {'lat_ms':>7} {'score':>7} {'hard%':>6}")
    for cfg in EXP2_CONFIGS:
        s = exp2_out["summary"][cfg]
        print(
            f"{cfg:>14} {s['retrieval_hit_rate_percent']:>6} "
            f"{s['avg_paths_per_query']:>6} {s['retrieval_latency_ms']:>7} "
            f"{s['task_score_avg']:>7} {s['hard_pass_rate_percent']:>6}"
        )

    print("\n=== Mock Exp3 MFP x DAAO Factorial Summary ===")
    print(f"{'config':>10} {'score':>7} {'hard%':>6} {'heal':>5} {'steps':>6} {'solid':>5}")
    for cfg in EXP3_CONFIGS:
        s = exp3_out["summary"][cfg]
        print(
            f"{cfg:>10} {s['task_score_avg']:>7} "
            f"{s['hard_pass_rate_percent']:>6} {s['avg_heal_rounds']:>5} "
            f"{s['avg_steps']:>6} {s['mfp_patterns_solidified']:>5}"
        )
    print(f"\n  self-evolution gain (full - both_off) = {exp3_out['self_evolution_gain']}  (MOCK)")
    print("\n[eval_mock] NOTE: all values are placeholders (FNIX_MOCK_LLM=1).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
