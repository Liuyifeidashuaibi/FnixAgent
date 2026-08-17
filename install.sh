#!/usr/bin/env bash
# Fnix Harness — macOS / Linux install (Hermes-style)
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo "=== Fnix Harness ==="
echo "Local-first · No account · BYOK"
echo ""

for cmd in python3 node pnpm; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "Missing: $cmd"; exit 1; }
done

[[ -f .env ]] || { cp .env.example .env && echo "Created .env"; }

pnpm setup
pnpm doctor

echo ""
echo "=== Ready ==="
echo ""
cat <<'EOF'
Start Desktop:
  pnpm dev

First launch: setup wizard → API Key → workspace → Work/Code
No login required.

Release install (no compile):
  https://github.com/Liuyifeidashuaibi/FnixAgent/releases

Docs: docs/GETTING_STARTED.md
EOF
