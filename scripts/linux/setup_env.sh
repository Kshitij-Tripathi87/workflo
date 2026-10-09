#!/bin/bash
# Workflo Linux environment setup: system packages, Python packages
# (editable), runtime image, and the golden-run fixture repo.
#
# Designed for WSL2 Ubuntu and GitHub Actions ubuntu-latest, run as root.
# Idempotent — safe to re-run.
set -euo pipefail

REPO_ROOT="${WORKFLO_REPO_ROOT:-$(cd "$(dirname "${0}")/../.." && pwd)}"

echo "==> Repo root: $REPO_ROOT"

# --- System packages ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq bubblewrap dnsmasq nftables iproute2 iputils-ping \
  git python3 python3-pip >/dev/null

# --- Python environment: dedicated venv (PEP 668 clean) ---
VENV=/opt/workflo/venv
python3 -m venv "$VENV"
export PATH="$VENV/bin:$PATH"
PIP="$VENV/bin/pip"

"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet \
  pydantic click cryptography pyyaml httpx prompt_toolkit psutil \
  pytest pytest-asyncio pytest-json-report

"$PIP" install --quiet -e "$REPO_ROOT/packages/workflo-schema"
# worker-engine declares workflo-utils as a dependency; install the local
# package before the worker so pip never tries to resolve it from PyPI.
"$PIP" install --quiet -e "$REPO_ROOT/packages/workflo-utils"
"$PIP" install --quiet -e "$REPO_ROOT/packages/sandbox-isolation"
"$PIP" install --quiet -e "$REPO_ROOT/packages/probe-engine"
"$PIP" install --quiet -e "$REPO_ROOT/packages/cortex-auth"
"$PIP" install --quiet -e "$REPO_ROOT/apps/sandbox-executor"
"$PIP" install --quiet -e "$REPO_ROOT/apps/worker-engine"
"$PIP" install --quiet -e "$REPO_ROOT/packages/sandbox-runtime"
"$PIP" install --quiet -e "$REPO_ROOT/supervisor"
"$PIP" install --quiet -e "$REPO_ROOT/apps/workflo-cli"

# --- Runtime image ---
WORKFLO_REPO_ROOT="$REPO_ROOT" WORKFLO_PIP="$PIP" \
  "$REPO_ROOT/scripts/linux/build_runtime_image.sh"

# --- Fixture repo: a tiny git repo whose own tests prove, from inside
# the sandbox, that isolation holds (egress blocked, DNS blocked,
# filesystem sealed, host invisible) plus 3 trivial green tests.
FIXTURE=/root/wf-fixture
rm -rf "$FIXTURE"
mkdir -p "$FIXTURE"
cd "$FIXTURE"

cat > test_sanity.py <<'EOF'
def test_arithmetic():
    assert 1 + 1 == 2

def test_string_ops():
    assert "workflo".upper() == "WORKFLO"

def test_sorting():
    assert sorted([3, 1, 2]) == [1, 2, 3]
EOF

cat > test_sandbox_isolation.py <<'EOF'
"""Adversarial tests: the repo's own test suite proves — from INSIDE the
sandbox — that Workflo's isolation guarantees hold. If any of these pass
in an unsandboxed environment, they fail here: they assert on denial."""
import errno
import os
import pathlib
import socket


def test_no_external_egress():
    """An exfiltration attempt must not be able to connect out."""
    try:
        s = socket.create_connection(("8.8.8.8", 53), timeout=3)
        s.close()
        raise AssertionError("EGRESS SUCCEEDED - network isolation is broken")
    except OSError:
        pass


def test_no_external_dns():
    try:
        socket.getaddrinfo("example.com", 80)
        raise AssertionError("external DNS resolved - isolation is broken")
    except socket.gaierror:
        pass


def test_no_writes_outside_approved_dirs():
    for p in ("/etc/.workflo_write_test", "/usr/.workflo_write_test",
              "/root/.workflo_write_test", "/opt/.workflo_write_test"):
        try:
            with open(p, "w") as f:
                f.write("x")
            pathlib.Path(p).unlink()
            raise AssertionError(f"write to {p} succeeded - fs isolation is broken")
        except OSError as e:
            assert e.errno in (errno.EPERM, errno.EACCES, errno.EROFS,
                               errno.ENOENT), f"unexpected error for {p}: {e}"


def test_docker_socket_absent():
    assert not os.path.exists("/var/run/docker.sock")
    assert not os.path.exists("/run/containerd/containerd.sock")


def test_host_processes_invisible():
    pids = [p for p in os.listdir("/proc") if p.isdigit()]
    assert len(pids) < 20, f"too many PIDs visible: {len(pids)}"


def test_snapshot_manifest_present():
    assert pathlib.Path("/workspace/repo/.workflo_manifest.json").exists()
EOF

# --- Fixture app: a tiny HTTP server the agent probes in the deep tier
cat > app.py <<'EOF'
"""Fixture app: stdlib HTTP server the Workflo agent operates."""
import http.server
import os
import socketserver
import sys

PORT = int(os.environ.get("PORT", "3000"))


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"status":"ok"}'
        else:
            body = b"<html><body>workflo fixture app</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if self.path == "/health" else "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()


if __name__ == "__main__":
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print("fixture app listening on %s" % PORT, flush=True)
        httpd.serve_forever()
EOF

git init -q
git config user.email "golden@workflo.dev"
git config user.name "Workflo Golden Run"
git add -A
git commit -qm "fixture: sanity + adversarial isolation tests + app under test"

echo "==> Fixture repo ready at $FIXTURE"
echo "==> Setup complete."
