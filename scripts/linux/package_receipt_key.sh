#!/usr/bin/env bash
# Package the receipt's public signing key alongside the receipt so the bundle
# can be verified from a clean machine without the producer's home directory.
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: package_receipt_key.sh <receipt.json>" >&2
  exit 2
fi

receipt="$1"
if [[ ! -s "$receipt" ]]; then
  echo "ERROR: receipt missing or empty: $receipt" >&2
  exit 1
fi

fingerprint="$(python3 - "$receipt" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1], encoding="utf-8"))
receipt = doc.get("receipt", doc)
fingerprint = receipt.get("public_key_fingerprint")
if not isinstance(fingerprint, str) or len(fingerprint) != 64:
    raise SystemExit("receipt has no valid Ed25519 public-key fingerprint")
print(fingerprint)
PY
)"

home="$(python3 -c 'from pathlib import Path; print(Path.home())')"
key_source="$home/.config/workflo/keys/${fingerprint}.pub.pem"

# sudo -E may preserve the invoking runner's HOME. Fall back to the common
# CI home roots, without assuming keys always live under /root.
if [[ ! -s "$key_source" ]]; then
  key_source=""
  for search_root in /root /home; do
    [[ -d "$search_root" ]] || continue
    candidate="$(find "$search_root" -type f \
      -path "*/.config/workflo/keys/${fingerprint}.pub.pem" \
      -print -quit 2>/dev/null || true)"
    if [[ -n "$candidate" && -s "$candidate" ]]; then
      key_source="$candidate"
      break
    fi
  done
fi

if [[ -z "$key_source" || ! -s "$key_source" ]]; then
  echo "ERROR: public key not found for receipt fingerprint $fingerprint" >&2
  exit 1
fi

target="$(dirname "$receipt")/receipt-key.pub.pem"
install -m 0644 "$key_source" "$target"
echo "Packaged receipt public key: $target (fingerprint $fingerprint)"
