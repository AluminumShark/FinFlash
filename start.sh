#!/usr/bin/env bash
# One-click deploy / start for FinFlash (Linux/macOS).
#   ./start.sh         build & start full stack via Docker
#   ./start.sh down    stop and remove the stack
#   ./start.sh logs    tail logs
#   ./start.sh local   run backend (uv) + frontend (pnpm) without Docker
set -euo pipefail
cd "$(dirname "$0")"

action="${1:-up}"

case "$action" in
  down) docker compose down ;;
  logs) docker compose logs -f ;;
  local)
    [ -f backend/.env ] || cp backend/.env.example backend/.env
    echo "Backend  -> http://localhost:8000/docs"
    echo "Frontend -> http://localhost:5173"
    ( cd backend && uv sync --extra dev && uv run uvicorn app.main:app --reload --port 8000 ) &
    ( cd frontend && pnpm install && pnpm dev ) &
    wait
    ;;
  up|*)
    docker info >/dev/null 2>&1 || { echo "Docker is not running. Start it first."; exit 1; }
    if [ ! -f .env ]; then
      cp backend/.env.example .env
      echo "Created .env from template — add a provider key + EXA_API_KEY, then re-run."
      exit 1
    fi
    echo "Building and starting the FinFlash stack..."
    docker compose up -d --build
    printf "Waiting for backend"
    for _ in $(seq 1 90); do
      if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then echo " ready."; break; fi
      printf "."; sleep 1
    done
    key=$(docker compose logs backend 2>/dev/null | grep -oE 'ff_[A-Za-z0-9_-]+' | tail -1 || true)
    echo "=================================================="
    echo "  FinFlash is up!"
    echo "  Frontend : http://localhost:8080"
    echo "  API docs : http://localhost:8000/docs"
    [ -n "$key" ] && echo "  API key  : $key  (paste into the UI)"
    echo "=================================================="
    echo "Stop with: ./start.sh down"
    ;;
esac
