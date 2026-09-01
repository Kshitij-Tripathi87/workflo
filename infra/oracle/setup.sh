#!/usr/bin/env bash
# One-time bootstrap of the Oracle Cloud Free Tier (ARM Ampere A1, 24 GB RAM)
# instance that hosts vLLM + the validation sandbox runner.
#
# Prerequisites:
#   - Ubuntu 22.04 (or any Ubuntu-based ARM image) on Oracle Cloud Always Free tier
#   - Inbound rules: allow SSH (22) only; 8000 is exposed only via Cloudflare Tunnel
#
# Run as the default (ubuntu) user; the script uses sudo where needed.

set -euo pipefail

log() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }

log "Installing system packages"
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  ca-certificates curl git jq python3-pip python3-venv \
  docker.io docker-compose-plugin

log "Adding user to docker group (re-login required if first time)"
sudo usermod -aG docker "$USER"
# Continue even if group change isn't effective in current shell
docker --version || true

log "Installing pipx (for isolated CLI installs)"
sudo apt-get install -y --no-install-recommends pipx
pipx ensurepath || true

log "Starting vLLM (this will pull ~5 GB on first run)"
mkdir -p "$HOME/infra/vllm"
# Use the committed compose file
docker compose -f "$HOME/workflowpro-tests/infra/vllm/docker-compose.yml" up -d

log "Waiting for vLLM to become healthy (initial model pull + load can take 2-5 min)"
for _ in $(seq 1 120); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    log "vLLM healthy at http://localhost:8000"
    break
  fi
  sleep 5
done

log "Installing cloudflared (free HTTPS tunnel; alternative to Oracle public IP)"
if ! command -v cloudflared >/dev/null; then
  ARCH="$(dpkg --print-architecture)"
  wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" \
    -O /tmp/cloudflared.deb
  sudo dpkg -i /tmp/cloudflared.deb
fi

log "Starting Cloudflare Quick Tunnel in background (Ctrl+C to stop; use tmux/screen in prod)"
# NOTE: Quick Tunnel URLs change each restart. For stable URLs use a named tunnel
# + DNS record (free, see https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).
nohup cloudflared tunnel --url http://localhost:8000 --no-autoupdate \
  > "$HOME/cloudflared.log" 2>&1 &
sleep 8
TUNNEL_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$HOME/cloudflared.log" | head -n1 || true)"
if [ -n "${TUNNEL_URL:-}" ]; then
  log "Cloudflare Tunnel URL: ${TUNNEL_URL}"
  log "Set this as MODEL_ENDPOINT in your local shell:"
  log "  export MODEL_ENDPOINT=${TUNNEL_URL}/v1"
else
  log "Tunnel not ready yet; check $HOME/cloudflared.log. Use http://<public-ip>:8000 if exposing."
fi

log "Installing validation CLI"
cd "$HOME/workflowpro-tests"
pipx install --editable ./apps/validation-cli

log ""
log "Setup complete."
log "Next: export MODEL_ENDPOINT, then run:"
log "  validate-phase2 --repo https://github.com/<you>/workflowpro-tests --output ./reports"
