#!/bin/bash
# Provision the pinned Firecracker toolchain for a workflo KVM host.
#
# Downloads (or verifies from a local archive) the pinned Firecracker
# release, checks its sha256 against the release digest, extracts the
# firecracker + jailer binaries, and installs them to the target prefix.
# Nothing is installed unless the digest matches — a failed verification
# is a hard error, never a warning.
#
# Pinned: Firecracker v1.18.0 (see worker/src/workflo_worker_host/ for
# the version the admission probe expects).
#
# Usage:
#   sudo ./provision_firecracker.sh [--prefix /usr/local/bin] [--from-archive FILE]
#
#   --from-archive FILE   verify+install from a pre-downloaded tgz
#                         (offline hosts; digest check still applies)
#   --prefix DIR          install location (default /usr/local/bin)
set -euo pipefail

VERSION="v1.18.0"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  SHA256="1ac8eec866dd5eea14efecf6323e22b23eea24054545338a5b34bc5bca6623cd" ;;
  aarch64) SHA256="2a6130ff0338901ff9d7fbd73ce046c6b1c6123889dc84a34d678aa53bd0c0c2" ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac
TARBALL="firecracker-${VERSION}-${ARCH}.tgz"
URL="https://github.com/firecracker-microvm/firecracker/releases/download/${VERSION}/${TARBALL}"

PREFIX="/usr/local/bin"
ARCHIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --from-archive) ARCHIVE="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

if [ -n "$ARCHIVE" ]; then
  cp "$ARCHIVE" "$WORK/$TARBALL"
else
  echo "==> downloading $URL"
  curl -fsSL --retry 3 -o "$WORK/$TARBALL" "$URL"
fi

echo "==> verifying sha256 (pinned ${VERSION}/${ARCH})"
echo "  expected: $SHA256"
ACTUAL="$(sha256sum "$WORK/$TARBALL" | awk '{print $1}')"
echo "  actual:   $ACTUAL"
if [ "$ACTUAL" != "$SHA256" ]; then
  echo "FATAL: digest mismatch — refusing to install" >&2
  exit 1
fi

echo "==> extracting"
tar -xzf "$WORK/$TARBALL" -C "$WORK"
# The release tgz nests binaries under <version>-<arch>/.
BIN_DIR="$(find "$WORK" -type f -name firecracker -printf '%h\n' | head -1)"
if [ -z "$BIN_DIR" ]; then
  echo "FATAL: firecracker binary not found in archive" >&2
  exit 1
fi
JAILER="$BIN_DIR/jailer"
if [ ! -f "$JAILER" ]; then
  echo "FATAL: jailer binary not found in archive (both are required)" >&2
  exit 1
fi

echo "==> installing to $PREFIX"
install -m 0755 "$BIN_DIR/firecracker" "$PREFIX/firecracker"
install -m 0755 "$JAILER" "$PREFIX/jailer"

echo "==> installed versions"
"$PREFIX/firecracker" --version
# jailer has no --version; --help exiting 0/1 both prove it executes.
"$PREFIX/jailer" --help >/dev/null 2>&1 || true

echo "==> done: firecracker + jailer ${VERSION} provisioned (digest verified)"
