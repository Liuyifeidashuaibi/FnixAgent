# FnixAgent — FSE 2027 Reproduction Package

This package lets reviewers reproduce the experiments reported in the FSE 2027
submission of **FnixAgent: A Local-First AI Agent with Self-Evolving Knowledge
Topology**. It is designed so that a reviewer can validate the *structure* of
every experiment and the *local (no-LLM) results* without an API key, and can
optionally plug in their own key (BYOK) to reproduce the LLM-dependent numbers.

> **Anonymization notice (submission version):** author names, affiliations,
> and identifying URLs have been removed from this reproduction package. The
> code, scripts, and benchmark data are unchanged. Any reviewer-visible identity
> is limited to what is necessary to run the artifacts.

---

## 1. Environment Requirements

| Component | Minimum | Notes |
|-----------|---------|-------|
| OS | Linux / macOS / Windows 10+ | Docker path recommended for reviewers; native path works on all three |
| Python | 3.11+ | Required for `agentd` and all experiments |
| Node.js | 18+ | Required only to build the Workbench UI from source; **not** required for experiments |
| Rust (toolchain) | Optional | Only needed to build the Tauri Desktop / `fnix-local` sidecar from source |
| Disk | ~1.5 GB | Repo + Python deps + 1000 FCS tasks |
| Memory | 2 GB | Mock/local experiments; raise to 4 GB if running live `agentd` + LLM |
| Docker / Docker Compose | Optional | For the one-click containerized reproduction |

FnixAgent follows a **BYOK** (Bring Your Own Key) model: it ships **no** bundled
model credentials. Two reproduction modes are supported:

- **Mock mode** (default for reviewers, no key needed): set `FNIX_MOCK_LLM=1`.
  The local experiments (exp1, exp4) run unchanged; the LLM-dependent ablations
  (exp2, exp3) are reproduced with the lightweight `eval_mock.py`, which emits
  structurally identical result files with clearly-marked placeholder numbers.
- **Live mode** (optional): provide your own API key for one of the supported
  providers and start `agentd`. See §5 (BYOK Configuration).

---

## 2. Three-Step Reproduction Flow

### Step 1 — Environment setup

```bash
# Clone the (anonymized) submission artifact
git clone <submission-repo-url> fnixagent
cd fnixagent

# Create a Python 3.11+ virtual environment
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Install Python dependencies (standalone profile, no optional cloud deps)
pip install --upgrade pip
pip install -r requirements.txt

# (Optional) Node.js — only if you intend to build the Workbench UI
# Requires pnpm: npm install -g pnpm
# pnpm install
```

### Step 2 — Run the test suite

```bash
python -m pytest tests -q
```

Expected: ~1800+ tests collected and passing. This validates that the
codebase is intact and the local harness compiles.

### Step 3 — Run the experiments

```bash
# All four experiments in sequence. exp2/exp3 gracefully degrade to
# placeholders when agentd is not running (mock mode).
python paper/experiments/run_all.py

# Reviewers without an API key (mock mode) — local-only path:
export FNIX_MOCK_LLM=1            # Windows PowerShell: $env:FNIX_MOCK_LLM="1"
python paper/experiments/run_all.py --skip exp2 exp3   # exp1 + exp4 (no LLM)
python paper/reproduction/eval_mock.py                 # mock ablation for exp2/exp3
```

Results are written to `paper/experiments/results/`:

| File | Experiment | Needs LLM? |
|------|------------|------------|
| `exp1_fcs_stats.json` | exp1 — FCS benchmark scale-up & coverage | No |
| `exp2_ktg_ablation.json` | exp2 — KTG vs Vector RAG vs GraphRAG vs No-RAG | Scores need agentd (degrades to placeholder) |
| `exp3_ablation.json` | exp3 — MFP × DAAO factorial ablation | Scores need agentd (degrades to placeholder) |
| `exp4_longitudinal.json` | exp4 — longitudinal self-evolution | No |
| `all_results.json` | Aggregated summary of the above | — |
| `mock_ablation_results.json` | Mock placeholders for exp2/exp3 (reviewer path) | No (mock) |

---

## 3. Expected Output & Runtime per Experiment

Run on a 4-core / 8 GB machine with Python 3.11. Times are indicative.

| Experiment | Command | Expected runtime | Key outputs |
|------------|---------|------------------|-------------|
| exp1 | `python paper/experiments/exp1_fcs_scale.py` | ~30–90 s | `total_tasks=1000`, `valid_rate≈100%`, distribution matrix |
| exp2 (local) | `python paper/experiments/exp2_ktg_ablation.py --no-agent` | ~5–15 s | retrieval hit-rate per config; `task_score_avg=null` (placeholder) |
| exp3 (local) | `python paper/experiments/exp3_mfp_daao_ablation.py --no-agent` | ~5–15 s | routing + MFP metrics; `task_score_avg=null` (placeholder) |
| exp4 | `python paper/experiments/exp4_longitudinal.py` | ~20–60 s | KTG growth across 1/7/30/90-day horizons |
| Mock ablation | `python paper/reproduction/eval_mock.py` | < 2 s | `mock_ablation_results.json` (deterministic placeholders) |
| Full suite | `python paper/experiments/run_all.py` | ~1–3 min (no agentd) | `all_results.json` + stdout summary table |

With a live `agentd` + LLM, exp2/exp3 additionally populate real `task_score_avg`
and `hard_pass_rate_percent`. Expect exp2/exp3 to take several minutes depending
on provider latency and the `--limit` task cap (default 9 seed tasks).

### Sample stdout (run_all summary)

```
=== FSE 2027 Experiments Summary ===
        experiment   status   exit
        exp1_fcs_scale      ok     0
      exp2_ktg_ablation      ok     0
  exp3_mfp_daao_ablation      ok     0
      exp4_longitudinal      ok     0

  total elapsed: 87.4s

--- Key Metrics ---
  exp1: tasks=1000 valid_rate=100.0% effective=...
  exp4 (90d): nodes=... solidified=... retrieval_hit=...%
```

---

## 4. BYOK Configuration (Optional, Live Mode)

FnixAgent supports OpenAI, Qwen (DashScope), DeepSeek, and GLM. Copy the
template and fill in one key:

```bash
cp .env.example .env
```

Relevant variables in `.env`:

```dotenv
FNIX_API_ONLY=1                      # BYOK mode (no bundled key)
FNIXAGENT_PROFILE=standalone         # local-first, zero-Docker default
FNIX_LOCAL_URL=http://127.0.0.1:8710

# Provide exactly ONE of the following:
OPENAI_API_KEY=sk-...
QWEN_API_KEY=sk-...        # alias: DASHSCOPE_API_KEY
DEEPSEEK_API_KEY=sk-...
GLM_API_KEY=...
# Or a custom OpenAI-compatible endpoint:
CUSTOM_API_KEY=...
CUSTOM_BASE_URL=https://your-endpoint/v1
```

Desktop users normally enter the key in **Settings** (the app encrypts it at
rest). For headless reproduction, the `.env` file is the documented path.

Then start the agent daemon (port 8003) and, if needed, the local sidecar
(port 8710):

```bash
python -m fnixagent                 # starts agentd on :8003
# The fnix-local sidecar (Rust) is only required for the Desktop app;
# experiments talk to agentd directly.
```

Verify agentd is reachable before running exp2/exp3 without `--no-agent`:

```bash
curl -s http://127.0.0.1:8003 || echo "agentd not running"
```

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ModuleNotFoundError: fnixagent` | `src/` not on path | Run from repo root; the scripts prepend `src/` automatically. For ad-hoc use: `set PYTHONPATH=src` (PowerShell) / `export PYTHONPATH=src` |
| exp2/exp3 `task_score_avg` is `null` | agentd not running (expected in mock mode) | Either keep placeholders (mock mode) or start `python -m fnixagent` and re-run without `--no-agent` |
| `Address already in use: 8003` | another process holds the port | `lsof -i :8003` (macOS/Linux) or `netstat -ano \| findstr :8003` (Windows); stop it or use `--base http://127.0.0.1:OTHER` |
| `pytest` collection errors | wrong Python version | Confirm `python --version` is 3.11+ |
| Node/`pnpm` not found | UI toolchain missing | Only needed for Workbench build, not for experiments; experiments are pure Python |
| pip install fails on Windows | missing build tools for a wheel | Prefer the standalone `requirements.txt` (no optional deps); ensure Python 3.11+ 64-bit |

### Diagnostic commands

```bash
# Environment doctor (Node toolchain checks)
pnpm doctor            # runs scripts/fnix-doctor.mjs

# Python harness doctor
python -c "from fnixagent.cli.doctor import run_doctor; run_doctor()"

# Port availability (agentd :8003, fnix-local :8710)
python -c "import socket; [print(p, 'free' if socket.socket().connect_ex(('127.0.0.1',p)) else 'IN USE') for p in (8003,8710)]"
```

---

## 6. One-Click Docker Reproduction

For reviewers who prefer not to install Python/Node locally:

```bash
cd paper/reproduction
docker compose build
docker compose run repro            # runs exp1 + exp4 (no LLM), writes results to the mounted volume
```

The container sets `FNIX_MOCK_LLM=1` and mounts `paper/experiments/results` to
the host so artifacts survive container exit. See `Dockerfile` and
`docker-compose.yml` in this directory.

For the full protocol (requirements, expected numeric ranges, copy-paste
commands, and failure diagnostics) see **`REPRODUCE.md`**.
