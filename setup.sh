#!/usr/bin/env bash
# Cortex Autopilot — one-command setup.
#
# Brings up Postgres + backend + frontend, waits for /health, and
# opens the UI in the default browser.
#
# Usage:
#   ./setup.sh
#
# Override defaults with env vars:
#   COMPOSE_ENV=staging ./setup.sh
#   SKIP_BROWSER=1 ./setup.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()   { printf "${BLUE}[cortex]${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}[ok]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
fail()  { printf "${RED}[fail]${NC} %s\n" "$*" >&2; exit 1; }

# ---------- Pre-flight checks ----------
log "Pre-flight checks..."

command -v docker >/dev/null 2>&1 || fail "Docker is required. Install: https://docs.docker.com/get-docker/"
command -v node   >/dev/null 2>&1 || fail "Node.js 18+ is required. Install: https://nodejs.org/"
command -v npm    >/dev/null 2>&1 || fail "npm is required."

DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
NODE_VERSION=$(node --version | tr -d 'v')
ok "docker $DOCKER_VERSION"
ok "node $NODE_VERSION"

# ---------- Environment ----------
if [ ! -f compose.env ]; then
  if [ -f compose.env.example ]; then
    cp compose.env.example compose.env
    warn "Created compose.env from compose.env.example — edit it to set POSTGRES_PASSWORD"
  fi
fi

# ---------- Start backend stack ----------
log "Starting Postgres + backend via docker compose..."
docker compose --env-file compose.env up -d postgres backend
ok "Backend container started"

# ---------- Wait for /health ----------
log "Waiting for backend /health..."
ATTEMPTS=30
until curl -sf http://localhost:8000/health > /dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    warn "Backend did not become healthy in time. Showing last 50 log lines:"
    docker compose --env-file compose.env logs --tail=50 backend
    fail "Backend failed to start"
  fi
  printf "."
  sleep 2
done
printf "\n"
ok "Backend healthy"

# ---------- Install frontend deps ----------
if [ ! -d frontend/node_modules ]; then
  log "Installing frontend dependencies..."
  (cd frontend && npm install)
  ok "Frontend deps installed"
else
  ok "Frontend deps already installed"
fi

# ---------- Start frontend ----------
log "Starting frontend..."
docker compose --env-file compose.env up -d frontend
ok "Frontend container started"

# Wait for frontend
log "Waiting for frontend on http://localhost:3000..."
ATTEMPTS=20
until curl -sf http://localhost:3000 > /dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    warn "Frontend did not respond. Showing last 30 log lines:"
    docker compose --env-file compose.env logs --tail=30 frontend
    fail "Frontend failed to start"
  fi
  printf "."
  sleep 2
done
printf "\n"
ok "Frontend ready"

# ---------- Detailed health ----------
log "Detailed health report:"
curl -s http://localhost:8000/health/detailed | python -m json.tool 2>/dev/null || true

# ---------- Open browser ----------
if [ "${SKIP_BROWSER:-0}" != "1" ]; then
  log "Opening http://localhost:3000 in your browser..."
  if command -v xdg-open > /dev/null 2>&1; then
    xdg-open http://localhost:3000
  elif command -v open > /dev/null 2>&1; then
    open http://localhost:3000
  elif command -v start > /dev/null 2>&1; then
    start http://localhost:3000
  else
    warn "No browser launcher found. Open http://localhost:3000 manually."
  fi
fi

echo ""
ok "Cortex Autopilot is running!"
echo "  Frontend : http://localhost:3000"
echo "  Backend  : http://localhost:8000"
echo "  Health   : http://localhost:8000/health"
echo "  Detailed : http://localhost:8000/health/detailed"
echo ""
echo "  Demo     : python examples/demo/run_demo.py"
echo "  Stop     : docker compose --env-file compose.env down"

