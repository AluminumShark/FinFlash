<#
.SYNOPSIS
  One-click deploy / start for FinFlash.

.DESCRIPTION
  up     (default)  Build & start the full stack (Postgres+pgvector, Redis, backend, frontend) via Docker.
  down              Stop and remove the stack.
  logs              Tail all service logs.
  local             Run backend (uv) + frontend (pnpm) locally without Docker (two windows).

.EXAMPLE
  ./start.ps1
  ./start.ps1 down
  ./start.ps1 local
#>
param(
  [ValidateSet('up', 'down', 'logs', 'local')]
  [string]$Action = 'up'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

function Ensure-Env {
  if (-not (Test-Path "$root/.env")) {
    Copy-Item "$root/backend/.env.example" "$root/.env"
    Write-Host "Created .env from template — add at least one provider key + EXA_API_KEY, then re-run." -ForegroundColor Yellow
    exit 1
  }
}

function Wait-Health($url, $timeoutSec = 90) {
  Write-Host "Waiting for $url ..." -NoNewline
  for ($i = 0; $i -lt $timeoutSec; $i++) {
    try {
      $r = Invoke-RestMethod -Uri $url -TimeoutSec 2
      if ($r.status -eq 'ok') { Write-Host " ready." -ForegroundColor Green; return $true }
    } catch { Start-Sleep -Seconds 1; Write-Host '.' -NoNewline }
  }
  Write-Host " timed out." -ForegroundColor Red
  return $false
}

switch ($Action) {
  'down' {
    docker compose down
    break
  }
  'logs' {
    docker compose logs -f
    break
  }
  'local' {
    Write-Host 'Starting backend (uv) and frontend (pnpm) in new windows...' -ForegroundColor Cyan
    if (-not (Test-Path "$root/backend/.env")) { Copy-Item "$root/backend/.env.example" "$root/backend/.env" }
    Start-Process powershell -ArgumentList @(
      '-NoExit', '-Command',
      "Set-Location '$root/backend'; uv sync --extra dev; uv run uvicorn app.main:app --reload --port 8000"
    )
    Start-Process powershell -ArgumentList @(
      '-NoExit', '-Command',
      "Set-Location '$root/frontend'; pnpm install; pnpm dev"
    )
    Write-Host 'Backend -> http://localhost:8000/docs   Frontend -> http://localhost:5173' -ForegroundColor Green
    Write-Host 'The backend window prints a bootstrap API key on first start — copy it into the UI.' -ForegroundColor Yellow
    break
  }
  default {
    # up
    docker version *> $null
    if ($LASTEXITCODE -ne 0) { Write-Host 'Docker is not running. Start Docker Desktop first.' -ForegroundColor Red; exit 1 }
    Ensure-Env
    Write-Host 'Building and starting the FinFlash stack...' -ForegroundColor Cyan
    docker compose up -d --build
    if (Wait-Health 'http://localhost:8000/health') {
      Start-Sleep -Seconds 1
      $key = (docker compose logs backend 2>$null | Select-String -Pattern 'ff_[A-Za-z0-9_-]+' |
        ForEach-Object { $_.Matches.Value } | Select-Object -Last 1)
      Write-Host ''
      Write-Host '==================================================' -ForegroundColor Green
      Write-Host '  FinFlash is up!' -ForegroundColor Green
      Write-Host '  Frontend : http://localhost:8080'
      Write-Host '  API docs : http://localhost:8000/docs'
      if ($key) { Write-Host "  API key  : $key  (paste into the UI)" -ForegroundColor Cyan }
      else { Write-Host '  API key  : run `docker compose logs backend | Select-String ff_`' }
      Write-Host '==================================================' -ForegroundColor Green
      Write-Host 'Stop with: ./start.ps1 down'
    }
    break
  }
}
