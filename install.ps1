# Fnix Harness — Windows install (Hermes-style)
# End users: download Release .exe from GitHub — no script needed.
# Developers:
#   git clone ... && powershell -ExecutionPolicy Bypass -File install.ps1
#   pnpm dev

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "`n=== Fnix Harness ===" -ForegroundColor Cyan
Write-Host "Local-first AI workspace · No account · BYOK`n" -ForegroundColor Gray

function Require-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    Write-Host "Missing: $name" -ForegroundColor Red
    exit 1
  }
}

Require-Command python
Require-Command node
Require-Command pnpm

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env (standalone defaults)" -ForegroundColor Yellow
}

Write-Host "Running pnpm setup..."
pnpm setup
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running pnpm doctor..."
pnpm doctor
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`n=== Ready ===" -ForegroundColor Green
Write-Host @"

Start Desktop (Tauri + agentd + fnix-local):
  pnpm dev

First launch:
  1. No login — setup wizard opens
  2. Paste YOUR API Key (OpenAI / Qwen / DeepSeek / GLM)
  3. Pick a workspace folder → Work or Code

Download install package (no compile):
  https://github.com/Liuyifeidashuaibi/FnixAgent/releases

Docs: docs/GETTING_STARTED.md
"@
