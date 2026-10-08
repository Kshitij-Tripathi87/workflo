#!/usr/bin/env bash
# Workflo — one-command setup.
#
# Brings up the dev dependencies (Postgres) in Docker, starts the backend and
# frontend from this checkout, waits for both to answer, and opens the UI.
#
# Usage:
#   ./setup.sh
#
# Override defaults with env vars:
#   COMPOSE_ENV=staging ./setup.sh
#   SKIP_BROWSER=1 ./setup.sh
#   SKIP_DEPS=1 ./setup.sh        # don't (re)install python/node deps
#   BACKEND_PORT=8001 FRONTEND_PORT=3001 ./setup.sh
#
# Why the apps are not started through docker compose:
#   docker-compose.yml declares the dev *dependencies* only (db, redis, minio).
#   It has no `backend`/`frontend` services, and the database service is named
#   `db` — so the historical `docker compose up -d postgres backend` lines could
#   never succeed. A full-container flow needs those service definitions added;
#   see PRODUCT_BOUNDARIES.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()   { printf "${BLUE}[workflo]${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}[ok]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[warn]${NC} %s\n" "$*"; }
fail()  { printf "${RED}[fail]${NC} %s\n" "$*" >&2; exit 1; }

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
LOG_DIR="$REPO_ROOT/.workflo-dev"
COMPOSE_ENV="${COMPOSE_ENV:-compose.env}"

# ---------- Pre-flight checks ----------
log "Pre-flight checks..."

command -v docker >/dev/null 2>&1 || fail "Docker is required. Install: https://docs.docker.com/get-docker/"
command -v node   >/dev/null 2>&1 || fail "Node.js 18+ is required. Install: https://nodejs.org/"
command -v npm    >/dev/null 2>&1 || fail "npm is required."
PYTHON="$(command -v python3 || command -v python || true)"
[ -n "$PYTHON" ] || fail "Python 3.11+ is required. Install: https://www.python.org/downloads/"

DOCKER_VERSION=$(docker --version | awk '{print $3}' | tr -d ',')
NODE_VERSION=$(node --version | tr -d 'v')
ok "docker $DOCKER_VERSION"
ok "node $NODE_VERSION"
ok "$($PYTHON --version 2>&1)"

mkdir -p "$LOG_DIR"

# ---------- Environment ----------
if [ ! -f "$COMPOSE_ENV" ]; then
  if [ -f compose.env.example ]; then
    cp compose.env.example "$COMPOSE_ENV"
    warn "Created $COMPOSE_ENV from compose.env.example — edit it to set POSTGRES_PASSWORD"
  else
    warn "$COMPOSE_ENV not found; compose will use default credentials"
  fi
fi

# ---------- Dev dependencies (Postgres) ----------
log "Starting Postgres via docker compose (service: db)..."
docker compose --env-file "$COMPOSE_ENV" up -d db
ok "Postgres container started"

# ---------- Backend dependencies + server ----------
if [ "${SKIP_DEPS:-0}" != "1" ] && [ ! -x .venv/bin/python ]; then
  log "Creating backend virtualenv (.venv) and installing requirements..."
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  .venv/bin/python -m pip install -r backend/requirements.txt
  ok "Backend deps installed"
fi
[ -x .venv/bin/python ] || fail "No backend virtualenv at .venv (run without SKIP_DEPS=1 first)"

log "Starting backend on http://localhost:$BACKEND_PORT ..."
(cd backend && exec "$REPO_ROOT/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 --port "$BACKEND_PORT") >"$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

log "Waiting for backend /health..."
ATTEMPTS=30
until curl -sf "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    warn "Backend process exited. Last 50 log lines:"
    tail -50 "$LOG_DIR/backend.log" || true
    fail "Backend failed to start (see $LOG_DIR/backend.log)"
  fi
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    warn "Backend did not become healthy in time. Last 50 log lines:"
    tail -50 "$LOG_DIR/backend.log" || true
    fail "Backend failed to start (see $LOG_DIR/backend.log)"
  fi
  printf "."
  sleep 2
done
printf "\n"
ok "Backend healthy"

# ---------- Frontend dependencies + server ----------
if [ "${SKIP_DEPS:-0}" != "1" ] && [ ! -d frontend/node_modules ]; then
  log "Installing frontend dependencies..."
  (cd frontend && npm install)
  ok "Frontend deps installed"
else
  ok "Frontend deps already installed"
fi

log "Starting frontend on http://localhost:$FRONTEND_PORT ..."
(cd frontend && NEXT_PUBLIC_API_BASE_URL="http://localhost:$BACKEND_PORT" \
  exec npm run dev -- --port "$FRONTEND_PORT") >"$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

log "Waiting for frontend..."
ATTEMPTS=40
until curl -sf "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; do
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    warn "Frontend process exited. Last 30 log lines:"
    tail -30 "$LOG_DIR/frontend.log" || true
    fail "Frontend failed to start (see $LOG_DIR/frontend.log)"
  fi
  ATTEMPTS=$((ATTEMPTS - 1))
  if [ "$ATTEMPTS" -le 0 ]; then
    warn "Frontend did not respond. Last 30 log lines:"
    tail -30 "$LOG_DIR/frontend.log" || true
    fail "Frontend failed to start (see $LOG_DIR/frontend.log)"
  fi
  printf "."
  sleep 2
done
printf "\n"
ok "Frontend ready"

# ---------- Detailed health ----------
log "Detailed health report:"
curl -s "http://localhost:$BACKEND_PORT/health/detailed" | "$PYTHON" -m json.tool 2>/dev/null || true

# ---------- Open browser ----------
if [ "${SKIP_BROWSER:-0}" != "1" ]; then
  log "Opening http://localhost:$FRONTEND_PORT in your browser..."
  if command -v xdg-open > /dev/null 2>&1; then
    xdg-open "http://localhost:$FRONTEND_PORT"
  elif command -v open > /dev/null 2>&1; then
    open "http://localhost:$FRONTEND_PORT"
  elif command -v start > /dev/null 2>&1; then
    start "http://localhost:$FRONTEND_PORT"
  else
    warn "No browser launcher found. Open http://localhost:$FRONTEND_PORT manually."
  fi
fi

echo ""
ok "Workflo is running!"
echo "  Frontend : http://localhost:$FRONTEND_PORT   (pid $FRONTEND_PID)"
echo "  Backend  : http://localhost:$BACKEND_PORT   (pid $BACKEND_PID)"
echo "  Health   : http://localhost:$BACKEND_PORT/health"
echo "  Detailed : http://localhost:$BACKEND_PORT/health/detailed"
echo "  Logs     : $LOG_DIR/backend.log, $LOG_DIR/frontend.log"
echo ""
echo "  Demo     : python examples/demo/run_demo.py"
echo "  Stop     : kill $BACKEND_PID $FRONTEND_PID && docker compose --env-file $COMPOSE_ENV down"
echo ""
