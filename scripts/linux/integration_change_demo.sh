#!/usr/bin/env bash
# One synthetic provider contract change, one reviewed migration, two pinned runs.
# Usage: integration_change_demo.sh [--fixture-only] <new-output-dir>
set -euo pipefail

fixture_only=0
if [[ ${1:-} == --fixture-only ]]; then
  fixture_only=1
  shift
fi
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 [--fixture-only] <new-output-dir>" >&2
  exit 2
fi

root=$(cd "$(dirname "$0")/../.." && pwd)
fixture="$root/examples/integration-migration"
mkdir -m 700 -- "$1"
out=$(cd "$1" && pwd)
repo="$out/repo"
mkdir -- "$repo"
cp -R "$fixture/source/." "$repo/"

# Ignore machine/user Git configuration and commit at a fixed author/date.
# Git tracks the same files and modes regardless of the caller's checkout.
chmod -R u+rwX,go-rwx "$repo"
chmod 644 "$repo/integration.py" "$repo/checks/contract.py"
fixture_git() {
  env -i PATH="$PATH" LC_ALL=C TZ=UTC \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    GIT_AUTHOR_NAME=Workflo GIT_AUTHOR_EMAIL=fixture@workflo.invalid \
    GIT_COMMITTER_NAME=Workflo GIT_COMMITTER_EMAIL=fixture@workflo.invalid \
    GIT_AUTHOR_DATE=2026-01-01T00:00:00Z GIT_COMMITTER_DATE=2026-01-01T00:00:00Z \
    git -C "$repo" -c core.hooksPath=/dev/null -c commit.gpgsign=false "$@"
}
fixture_git init -q --initial-branch=main --object-format=sha1 --template=
fixture_git add -- integration.py checks/contract.py
fixture_git commit -qm 'Fixture: incoming provider response contract'
baseline=$(fixture_git rev-parse HEAD)
fixture_git apply --index "$fixture/candidate.patch"
fixture_git commit -qm 'Candidate: accept output_text and retain legacy response support'
candidate=$(fixture_git rev-parse HEAD)
[[ $(fixture_git diff-tree --no-commit-id --name-only -r "$baseline" "$candidate") == integration.py ]]
printf 'Baseline:  %s\nCandidate: %s\n' "$baseline" "$candidate"
if ((fixture_only)); then
  exit 0
fi

workflo=${WORKFLO_CLI:-/opt/workflo/venv/bin/workflo}
# HEAD already points to the candidate. A worktree-based baseline would
# pass and fail this harness; the baseline must use the old Git objects.
status=0
"$workflo" run-dev --repo "$repo" --commit "$baseline" --test-file checks/contract.py \
  --output-dir "$out/baseline" || status=$?
if [[ $status != 1 ]]; then
  echo "Expected a verified baseline QA failure (exit 1), got exit $status" >&2
  exit 1
fi
"$workflo" run-dev --repo "$repo" --commit "$candidate" --test-file checks/contract.py \
  --output-dir "$out/candidate"

for version in baseline candidate; do
  proof="$out/$version"
  "$workflo" verify "$proof/receipt.json" --pubkey "$proof/receipt-key.pub.pem"
  test -s "$proof/evidence/teardown.json"
done

# Both receipts verified independently. Check that the comparison itself is
# meaningful: correct pins, identical policy and checks, and just the
# incoming contract broke in the baseline.
python3 -I - "$out" "$baseline" "$candidate" <<'PY'
import base64
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
policy_digests = set()
for name, commit in zip(("baseline", "candidate"), sys.argv[2:], strict=True):
    proof = root / name
    envelope = json.loads((proof / "receipt.json").read_bytes())["envelope"]
    payload = json.loads(base64.b64decode(envelope["payload"], validate=True))
    policy_digests.add(payload["execution_policy_digest"])
    report = json.loads((proof / "evidence/checks.json").read_bytes())
    expected = [
        {"node_id": "checks/contract.py::test_existing_provider_contract", "outcome": "passed"},
        {"node_id": "checks/contract.py::test_incoming_provider_contract",
         "outcome": "failed" if name == "baseline" else "passed"},
    ]
    if payload["source"]["commit"] != commit or report["checks"] != expected:
        sys.exit(f"Unexpected {name} check scope or result")
if len(policy_digests) != 1:
    sys.exit("Baseline and candidate did not run under the same policy")
PY

echo "Verified baseline FAIL and candidate PASS; evidence in $out/{baseline,candidate}"
