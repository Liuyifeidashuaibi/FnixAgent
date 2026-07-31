#!/usr/bin/env bash
# FnixAgent Standalone 一键启动（macOS / Linux）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export FNIXAGENT_PROFILE="${FNIXAGENT_PROFILE:-standalone}"
if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
  echo "[dev:all] 已从 .env.example 创建 .env"
fi
exec node "$ROOT/scripts/dev-all.mjs"
