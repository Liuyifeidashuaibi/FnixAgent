# FnixAgent Standalone 一键启动（Windows PowerShell）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:PYTHONPATH = Join-Path $Root "src"
$env:FNIXAGENT_PROFILE = if ($env:FNIXAGENT_PROFILE) { $env:FNIXAGENT_PROFILE } else { "standalone" }

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
    Write-Host "[dev:all] 已从 .env.example 创建 .env"
}

Write-Host "[dev:all] 启动 API + Desktop (profile=$env:FNIXAGENT_PROFILE)"
node (Join-Path $Root "scripts\dev-all.mjs")
