# REPRODUCE — Detailed Reproduction Protocol (FSE 2027)

This document is the step-by-step protocol a reviewer should follow to
reproduce the FnixAgent experiments. It follows the artifact-evaluation
format requested by FSE: requirements, expected runtimes, expected numeric
ranges to cross-check, copy-paste commands, and failure diagnostics.

Companion files in this directory:
- `README.md` — quick-start overview
- `Dockerfile` / `docker-compose.yml` — one-click containerized path
- `eval_mock.py` — mock LLM evaluator for the no-API-key path

All commands assume the working directory is the **repository root** unless a
`cd paper/reproduction` is explicitly shown. Lines starting with `#` are
comments; `$` denotes a shell prompt (do not paste the `$`).

---

## 1. Requirements

### 1.1 Hardware

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| CPU | 2 cores | 4 cores | exp1 dry-checks are CPU-bound |
| Memory | 2 GB | 4–8 GB | 8 GB if also running a live LLM via `agentd` |
| Disk | 1.5 GB free | 2 GB free | Repo + Python deps + 1000 FCS tasks |
| Network | None for mock path | Outbound HTTPS for live LLM | Mock path is fully offline |

### 1.2 Software

| Component | Version | Required for | How to verify |
|-----------|---------|--------------|---------------|
| OS | Linux / macOS / Windows 10+ | All | `uname -a` / `ver` |
| Python | 3.11+ (3.11, 3.12, 3.13) | Experiments, tests, `agentd` | `python --version` |
| pip | latest | Dependency install | `pip --version` |
| Git | any | Cloning artifact | `git --version` |
| Node.js | 18+ | **Only** Workbench UI build from source | `node --version` |
| pnpm | 8+ | **Only** Workbench UI build / `pnpm doctor` | `pnpm --version` |
| Rust toolchain | optional | **Only** Tauri Desktop / `fnix-local` build | `cargo --version` |
| Docker + Compose | optional | One-click containerized path | `docker --version` |

> Experiments do **not** require Node, pnpm, Rust, or Docker. They are pure
> Python. Node is listed because the project as a whole ships a Tauri Desktop
> app; a reviewer reproducing only the paper's experiments can skip it.

### 1.3 Optional — BYOK API key (live numbers only)

Provide exactly one key in `.env` (see §4) to reproduce the LLM-dependent scores
in exp2/exp3. **Without** a key, reviewers still reproduce exp1, exp4, the
retrieval/routing sub-metrics of exp2/exp3, and the mock ablation — i.e. the
full experiment structure and all local results.

---

## 2. Expected Runtime

Measured on a 4-core / 8 GB / SSD machine, Python 3.11, no live LLM.

| Step | Command | Mock / no-LLM path | Live (agentd + LLM) |
|------|---------|--------------------|---------------------|
| Dependency install | `pip install -r requirements.txt` | 60–120 s | same |
| Test suite | `python -m pytest tests -q` | 30–90 s | same |
| exp1 | `python paper/experiments/exp1_fcs_scale.py` | 30–90 s | same |
| exp2 | `python paper/experiments/exp2_ktg_ablation.py --no-agent` | 5–15 s | 2–10 min (9 tasks × provider latency) |
| exp3 | `python paper/experiments/exp3_mfp_daao_ablation.py --no-agent` | 5–15 s | 2–10 min |
| exp4 | `python paper/experiments/exp4_longitudinal.py` | 20–60 s | same |
| Mock ablation | `python paper/reproduction/eval_mock.py` | < 2 s | n/a |
| Full suite | `python paper/experiments/run_all.py` | 1–3 min | 5–25 min |
| Docker build | `docker compose build` | 3–8 min | n/a |

`run_all.py` imposes a 30-minute per-experiment timeout. Total wall time for
the reviewer (mock path): under 5 minutes.

---

## 3. Expected Results (Cross-Check Ranges)

These ranges are for the **local / mock** path. A reviewer should see numbers
within these bounds; large deviations indicate an environment problem (see §6).

### exp1 — `paper/experiments/results/exp1_fcs_stats.json`

| Field | Expected range | Meaning |
|-------|----------------|---------|
| `total_tasks` | **1000** | seed (9) + generated (991) |
| `seed_count` | 9 | curated FCS seeds |
| `generated_count` | 991 | template-generated tasks |
| `valid_rate` | ~100.0% | schema-valid task rate |
| `dry_check_sample` | ≤ 1000 | sample size of dry validation |
| `capabilities` | 10 dimensions | FCS capability axes |
| `by_difficulty` | levels 1–4 present | difficulty distribution |

### exp2 — `paper/experiments/results/exp2_ktg_ablation.json` (local path)

| Config | `retrieval_hit_rate_percent` | `task_score_avg` |
|--------|------------------------------|------------------|
| `full_ktg` | ~100% | `null` (placeholder, no agentd) |
| `no_ktg` | 0% | `null` |
| `vector_rag` | > 0%, < 100% | `null` |
| `graph_rag_sim` | > 0%, < 100% | `null` |

In mock mode (`eval_mock.py`), `task_score_avg` is populated with explicit
`placeholder=true` values and preserves the ordering
`full_ktg > vector_rag > graph_rag_sim > no_ktg`.

### exp3 — `paper/experiments/results/exp3_ablation.json` (local path)

| Config | `routing_avg_max_steps` | `mfp_patterns_solidified` | `task_score_avg` |
|--------|-------------------------|---------------------------|------------------|
| `full` | ~14 | > 0 | `null` (placeholder) |
| `mfp_off` | ~14 | 0 | `null` |
| `daao_off` | 16 (fixed) | > 0 | `null` |
| `both_off` | 16 (fixed) | 0 | `null` |

`self_evolution_gain` is `null` in the local path; mock mode reports a positive
placeholder (~0.2–0.3) preserving `full > both_off`.

### exp4 — `paper/experiments/results/exp4_longitudinal.json`

| Horizon (days) | Trend | Notes |
|----------------|-------|-------|
| 1 → 7 → 30 → 90 | `final.active_nodes` non-decreasing | KTG accumulates |
| 90d | `retrieval_hit_rate_percent` ~100% | all 6 pattern seeds resolvable |
| 90d | `final.solidified_patterns` ≥ initial | MFP hill-climbing effect |
| 90d | `simulated_tasks` = 90 × 12 = 1080 | 12 tasks/day × days |

### mock_ablation_results.json (mock path only)

Deterministic across runs. `exp2` and `exp3` summaries contain
`placeholder: true` on every score. `self_evolution_gain` (mock) is positive.

---

## 4. Step-by-Step Commands (Copy-Paste)

### Path A — Native (no Docker), mock mode (recommended for reviewers)

```bash
# 0. Clone and enter the artifact
$ git clone <submission-repo-url> fnixagent
$ cd fnixagent

# 1. Create + activate a Python 3.11+ virtualenv
$ python -m venv .venv
$ source .venv/bin/activate         # Windows PowerShell: .\.venv\Scripts\Activate.ps1

# 2. Install dependencies (standalone profile; no optional cloud deps)
$ pip install --upgrade pip
$ pip install -r requirements.txt

# 3. Verify the codebase with the test suite (~1800+ tests)
$ python -m pytest tests -q

# 4. Enable mock LLM mode (no API key needed)
$ export FNIX_MOCK_LLM=1            # Windows PowerShell: $env:FNIX_MOCK_LLM="1"

# 5. Run the no-LLM experiments (exp1 + exp4)
$ python paper/experiments/run_all.py --skip exp2 exp3

# 6. Run the local retrieval/routing sub-metrics for exp2 and exp3
$ python paper/experiments/exp2_ktg_ablation.py --no-agent
$ python paper/experiments/exp3_mfp_daao_ablation.py --no-agent

# 7. Generate the mock ablation placeholders (mirrors exp2/exp3 schemas)
$ python paper/reproduction/eval_mock.py

# 8. Inspect outputs
$ ls paper/experiments/results/
#   exp1_fcs_stats.json  exp2_ktg_ablation.json  exp3_ablation.json
#   exp4_longitudinal.json  all_results.json  mock_ablation_results.json
```

### Path A (full suite, single command)

```bash
$ export FNIX_MOCK_LLM=1
$ python paper/experiments/run_all.py            # runs exp1→exp4; exp2/exp3 degrade gracefully
```

### Path B — Native with live LLM (BYOK, optional)

```bash
# 1. Configure BYOK
$ cp .env.example .env
$ # Edit .env and set exactly ONE key, e.g.:
$ #   OPENAI_API_KEY=sk-...
$ #   FNIX_API_ONLY=1
$ #   FNIXAGENT_PROFILE=standalone

# 2. Start the agent daemon (port 8003)
$ python -m fnixagent &
$ curl -s http://127.0.0.1:8003 || echo "agentd not ready"

# 3. Run the full suite WITHOUT --no-agent (uses live agentd)
$ python paper/experiments/run_all.py
```

### Path C — Docker (one-click, mock mode)

```bash
$ cd paper/reproduction
$ docker compose build
$ docker compose run repro                                   # exp1 + exp4 (no LLM)
$ docker compose run repro python paper/reproduction/eval_mock.py   # mock ablation
# Results appear on the host at: paper/experiments/results/
```

---

## 5. Individual Experiment Commands

```bash
# exp1 — FCS benchmark scale-up & coverage (NO LLM)
$ python paper/experiments/exp1_fcs_scale.py
$ python paper/experiments/exp1_fcs_scale.py --limit 50      # cap dry-check sample

# exp2 — KTG vs Vector RAG vs GraphRAG vs No-RAG (local retrieval; scores need agentd)
$ python paper/experiments/exp2_ktg_ablation.py --no-agent
$ python paper/experiments/exp2_ktg_ablation.py --base http://127.0.0.1:8003   # live

# exp3 — MFP x DAAO factorial (local routing/MFP; scores need agentd)
$ python paper/experiments/exp3_mfp_daao_ablation.py --no-agent
$ python paper/experiments/exp3_mfp_daao_ablation.py --base http://127.0.0.1:8003   # live

# exp4 — longitudinal self-evolution (NO LLM, seeded simulation)
$ python paper/experiments/exp4_longitudinal.py --seed 42
$ python paper/experiments/exp4_longitudinal.py --horizons 1,7,30,90

# Mock ablation (reviewer path, no key)
$ python paper/reproduction/eval_mock.py
```

Common flags for `run_all.py`:
- `--skip exp2 exp3` — skip listed experiments
- `--no-agent` — pass to exp2/exp3 (placeholder scores)
- `--base http://127.0.0.1:8003` — agentd URL
- `--limit N` — cap seed tasks for exp2/exp3 (default 9)

---

## 6. Failure Diagnostics

### 6.1 Environment doctor

```bash
# Node toolchain doctor (checks Python, Node, pnpm, ports, Tauri crate)
$ pnpm doctor                  # runs scripts/fnix-doctor.mjs

# Python harness doctor (checks FNIX_HOME, config, paths, secrets)
$ python -c "from fnixagent.cli.doctor import run_doctor; run_doctor()"
```

### 6.2 Port checks (agentd :8003, fnix-local :8710)

```bash
# Linux / macOS
$ python -c "import socket; \
print('8003:', 'IN USE' if socket.socket().connect_ex(('127.0.0.1',8003))==0 else 'free'); \
print('8710:', 'IN USE' if socket.socket().connect_ex(('127.0.0.1',8710))==0 else 'free')"

# Windows PowerShell
$ Test-NetConnection -ComputerName 127.0.0.1 -Port 8003
$ Test-NetConnection -ComputerName 127.0.0.1 -Port 8710
```

### 6.3 Is agentd reachable?

```bash
$ curl -sS -m 3 http://127.0.0.1:8003/ && echo OK || echo "agentd NOT reachable"
# If not reachable: python -m fnixagent   (starts agentd on :8003)
```

### 6.4 Common failures and fixes

| Failure | Diagnostic | Fix |
|---------|-----------|-----|
| `ModuleNotFoundError: No module named 'fnixagent'` | `python -c "import sys; print(sys.path)"` | Run from repo root (scripts prepend `src/`); or `export PYTHONPATH=src` |
| `python --version` < 3.11 | — | Install Python 3.11+; recreate venv |
| exp2/exp3 `task_score_avg` is `null` | agentd down | Expected in mock mode; or start `python -m fnixagent` and drop `--no-agent` |
| `OSError: [Errno 48] Address already in use` on :8003 | port occupied | `lsof -i :8003` (macOS/Linux) / `netstat -ano | findstr :8003` (Win); stop the process or change `--base` |
| `pip install` fails | partial wheel build | Ensure Python 3.11+ 64-bit; the standalone `requirements.txt` ships prebuilt wheels |
| Docker build fails at Node setup | no network in build | Pre-pull `node:18-slim` or use native Path A |
| exp1 `total_tasks` ≠ 1000 | benchmark pack incomplete | `git status benchmarks/code/`; re-clone; task files live in `benchmarks/code/seed/` + `benchmarks/code/generated/` |

### 6.5 Reproducibility sanity (determinism check)

```bash
# exp4 is seeded — two runs must produce identical output
$ python paper/experiments/exp4_longitudinal.py --seed 42
$ cp paper/experiments/results/exp4_longitudinal.json /tmp/run1.json
$ python paper/experiments/exp4_longitudinal.py --seed 42
$ diff /tmp/run1.json paper/experiments/results/exp4_longitudinal.json     # expect: no differences

# mock ablation is deterministic
$ python paper/reproduction/eval_mock.py
$ cp paper/experiments/results/mock_ablation_results.json /tmp/mock1.json
$ python paper/reproduction/eval_mock.py
$ diff /tmp/mock1.json paper/experiments/results/mock_ablation_results.json  # expect: no differences
```

---

## 7. Output Inventory

After a full mock-path run, `paper/experiments/results/` contains:

| File | Producer | LLM needed |
|------|----------|-----------|
| `exp1_fcs_stats.json` | exp1 | No |
| `exp2_ktg_ablation.json` | exp2 (`--no-agent` → placeholder scores) | Retrieval: no; scores: yes (placeholder otherwise) |
| `exp3_ablation.json` | exp3 (`--no-agent` → placeholder scores) | Routing/MFP: no; scores: yes (placeholder otherwise) |
| `exp4_longitudinal.json` | exp4 | No |
| `all_results.json` | `run_all.py` (aggregated) | — |
| `mock_ablation_results.json` | `eval_mock.py` | No (mock) |
| `fcs_distribution.json` | exp1 (in `paper/figures/`) | No |

Each JSON includes a `generated_at` timestamp and, where relevant, a `note`
field stating whether scores are live or placeholder.

---

## 8. Anonymization

This submission artifact is anonymized:
- Author names and affiliations are removed from the code and docs.
- No private API keys, tokens, or personal endpoints are included.
- Repository URLs in commands are placeholders (`<submission-repo-url>`).
- The `fnix-local` Rust sidecar binary is not required for any experiment and
  is not distributed with the review artifact.

Reviewer identity disclosure happens only via the standard FSE rebuttal
process, not through these artifacts.
