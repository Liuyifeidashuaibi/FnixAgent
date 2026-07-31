# FnixAgent — FSE 2027 Reproduction Image
# One-click containerized reproduction of the paper experiments.
#
# Build context MUST be the repository root:
#   docker build -t fnixagent-repro -f paper/reproduction/Dockerfile .
# Or, more conveniently, via docker-compose (see docker-compose.yml).

FROM python:3.11-slim

# ---- 1. System dependencies -------------------------------------------------
# curl/ca-certificates/git for the Node setup and any pip VCS deps.
# Build essentials are intentionally omitted: requirements.txt ships only
# pre-built wheels for the standalone profile.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# ---- 2. Node.js 18 LTS (optional, for Workbench UI build) -------------------
# Kept lightweight. Experiments do NOT require Node; it is available so a
# reviewer can optionally rebuild the frontend from source.
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

WORKDIR /fnixagent

# ---- 3. Python dependencies (layer-cached) ----------------------------------
# Install only the standalone requirements.txt (no optional cloud deps such as
# ldap3 / pymilvus / minio). This keeps the image small and build reproducible.
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---- 4. Application source --------------------------------------------------
# Copy what the experiments actually need: the Python package, the experiment
# scripts, the FCS benchmark task pack, the test suite, and config assets.
COPY src/ ./src/
COPY paper/ ./paper/
COPY benchmarks/ ./benchmarks/
COPY tests/ ./tests/
COPY config/ ./config/
COPY README.md LICENSE ./

# ---- 5. Reproduction environment --------------------------------------------
# FNIX_MOCK_LLM=1  -> reviewers can reproduce experiment STRUCTURE without an
#                     API key. exp1/exp4 are fully real; exp2/exp3 scores are
#                     emitted as clearly-marked placeholders (see eval_mock.py).
# FNIX_API_ONLY=1   -> BYOK mode (no bundled model credentials).
# PYTHONPATH        -> make the `fnixagent` package importable without install.
ENV FNIX_MOCK_LLM=1 \
    FNIX_API_ONLY=1 \
    FNIXAGENT_PROFILE=standalone \
    PYTHONPATH=/fnixagent/src \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Sanity gate at build time: confirm the package imports and the FCS benchmark
# task pack is discoverable. Fails the build early if the copy is incomplete.
RUN python -c "import fnixagent; print('fnixagent import OK')" \
    && python -c "import json,pathlib; m=json.load(open('benchmarks/code/manifest.json')); print('FCS tasks:', m['total'])"

# Default command: run the two no-LLM experiments (exp1 + exp4) end-to-end.
# `run_all.py` with --skip exp2 exp3 executes exactly exp1 then exp4.
# Override at runtime, e.g.:
#   docker compose run repro python paper/reproduction/eval_mock.py
#   docker compose run repro python paper/experiments/run_all.py
CMD ["python", "paper/experiments/run_all.py", "--skip", "exp2", "exp3"]
