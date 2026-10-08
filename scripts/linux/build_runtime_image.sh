#!/bin/bash
# Build the Workflo worker runtime image at /opt/workflo/workflo-worker.
#
# The image is a minimal, self-contained Linux tree able to run:
#   - python3 (interpreter + stdlib + system libs)
#   - pytest + pytest-json-report (installed via pip --target)
#   - sandbox_runtime.probes_report (copied from the repo source)
#
# Layout mirrors the host's merged-/usr so symlinks like /bin -> usr/bin
# resolve identically. The tree is bind-mounted READ-ONLY by bwrap.
#
# Must run as root (installs into /opt). Usage:
#   WORKFLO_REPO_ROOT=/path/to/workflo-project ./build_runtime_image.sh
set -euo pipefail

REPO_ROOT="${WORKFLO_REPO_ROOT:-$(cd "$(dirname "${0}")/../.." && pwd)}"
IMAGE=/opt/workflo/workflo-worker

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: must run as root (installs into /opt)" >&2
  exit 1
fi

echo "==> Building runtime image at $IMAGE (repo: $REPO_ROOT)"
rm -rf "$IMAGE"
mkdir -p "$IMAGE"/usr/bin "$IMAGE"/usr/lib "$IMAGE"/etc "$IMAGE"/opt \
         "$IMAGE"/tmp "$IMAGE"/proc "$IMAGE"/dev "$IMAGE"/run \
         "$IMAGE"/home/workflo "$IMAGE"/root "$IMAGE"/var "$IMAGE"/sys \
         "$IMAGE"/workspace "$IMAGE"/workflo/artifacts

# --- Mirror the host's merged-/usr symlinks (bin, lib, lib64, sbin) ---
for d in bin lib lib64 sbin; do
  if [ -L "/$d" ]; then
    ln -s "usr/$d" "$IMAGE/$d"
  elif [ -d "/$d" ] && [ ! -e "$IMAGE/$d" ]; then
    cp -a "/$d" "$IMAGE/$d"
  fi
done
# /var/run -> /run (docker-socket probe checks /var/run/docker.sock)
ln -sfn /run "$IMAGE/var/run"

# --- Python interpreter + stdlib + system libraries ---
PY_BIN=$(readlink -f /usr/bin/python3)
PY_VER=$("$PY_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "==> Python $PY_VER ($PY_BIN)"

cp -a "$PY_BIN" "$IMAGE/usr/bin/$(basename "$PY_BIN")"
ln -sf "$(basename "$PY_BIN")" "$IMAGE/usr/bin/python3"
ln -sf python3 "$IMAGE/usr/bin/python"

cp -a "/usr/lib/python$PY_VER" "$IMAGE/usr/lib/"
# Strip the stdlib test suite (~30MB, never needed inside the sandbox)
rm -rf "$IMAGE/usr/lib/python$PY_VER/test"

# --- /usr/bin + /usr/sbin: the app under test runs via /bin/sh and may
# use standard tools (env, cat, ls, ...). The runtime contract is "a real
# userland", not a python-only stub. ---
if [ -d /usr/bin ]; then
  cp -a /usr/bin/. "$IMAGE/usr/bin/"
fi
if [ -d /usr/sbin ]; then
  mkdir -p "$IMAGE/usr/sbin"
  cp -a /usr/sbin/. "$IMAGE/usr/sbin/"
fi

# System libraries (glibc, libssl, libexpat, ...) — needed by the
# interpreter and its lib-dynload extension modules.
if [ -d /usr/lib/x86_64-linux-gnu ]; then
  mkdir -p "$IMAGE/usr/lib/x86_64-linux-gnu"
  cp -a /usr/lib/x86_64-linux-gnu/. "$IMAGE/usr/lib/x86_64-linux-gnu/"
fi
# The dynamic loader dir (/lib64 -> usr/lib64 must not dangle)
if [ -d /usr/lib64 ] && [ ! -L /usr/lib64 ]; then
  cp -a /usr/lib64 "$IMAGE/usr/lib64"
fi

# --- bwrap file-bind mount points ---
# bubblewrap can only mount a FILE over a PATH if the destination already
# exists as a file in the (read-only) rootfs — otherwise it fails with
# "Can't create file at ...: Read-only file system". The Landlock wrapper
# and its rules JSON are RO-bound per run (bwrap.py), so create the
# placeholder destinations here. The real content arrives per run.
touch "$IMAGE/workflo/landlock_exec.py" "$IMAGE/workflo/landlock-rules.json"

# --- Minimal /etc ---
cp /etc/passwd "$IMAGE/etc/passwd"
cp /etc/group  "$IMAGE/etc/group"
printf 'hosts: files dns\n' > "$IMAGE/etc/nsswitch.conf"
printf '127.0.0.1 localhost\n' > "$IMAGE/etc/hosts"
printf 'nameserver 127.0.0.53\n' > "$IMAGE/etc/resolv.conf"  # bind-overridden per run
[ -f /etc/localtime ] && cp /etc/localtime "$IMAGE/etc/localtime"

# --- pytest + json-report plugin (pip --target, no venv inside image) ---
echo "==> Installing pytest + pytest-json-report into image"
PIP_BIN="${WORKFLO_PIP:-python3 -m pip}"
$PIP_BIN install --quiet --target "$IMAGE/opt/workflo/site" \
  pytest pytest-json-report

# --- sandbox_runtime + agent modules (for in-sandbox probes and the
# governed agent runtime) ---
echo "==> Copying sandbox_runtime + workflo_worker agent modules into image"
mkdir -p "$IMAGE/opt/workflo/runtime/workflo_worker"
cp -a "$REPO_ROOT/packages/sandbox-runtime/src/sandbox_runtime" \
      "$IMAGE/opt/workflo/runtime/sandbox_runtime"
# The agent runs INSIDE the sandbox: governed tool gateway + runner.
cp -a "$REPO_ROOT/apps/worker-engine/src/workflo_worker/agent_tools.py" \
      "$IMAGE/opt/workflo/runtime/workflo_worker/agent_tools.py"
cp -a "$REPO_ROOT/apps/worker-engine/src/workflo_worker/agent_runner.py" \
      "$IMAGE/opt/workflo/runtime/workflo_worker/agent_runner.py"
touch "$IMAGE/opt/workflo/runtime/workflo_worker/__init__.py"
# Drop caches; the rootfs is read-only inside the sandbox anyway
find "$IMAGE/opt/workflo/runtime" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# --- Fix-uid: the sandbox's /tmp, /home, /workspace, /workflo are bind
# mounts owned by uid 100000 (see supervisor._build_rootfs) — no image
# action needed, just document the contract.

echo "==> Runtime image built:"
du -sh "$IMAGE"
ls "$IMAGE"
