"""Export the frozen v1 contracts as language-neutral JSON Schema.

ADR-0015: `packages/workflo-schema` is the single authored contract home.
This script derives JSON Schema artifacts from the Pydantic models so the
web layer (and any other language) can validate against the same shapes
without a second authority. Generated files are committed; regenerating
must produce zero diffs (CI check follows in a later phase).

Usage:
    python packages/workflo-schema/scripts/export_schemas.py [--check]

``--check`` fails when regeneration would change committed files.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workflo_schema.contracts import (
    DsseEnvelopeV1,
    ExecutionPolicyBundleV1,
    EvidenceArtifactV1,
    EvidenceManifestV1,
    FindingV1,
    PatchApprovalV1,
    PatchProposalV1,
    ReceiptV5Payload,
    RunEventV1,
    RunOutcomeV1,
    RunSpecV1,
    TeardownVerificationV1,
)

REPO_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas" / "v1"

#: name -> model; names are stable file names, do not rename casually.
EXPORTED: dict[str, type] = {
    "run-spec": RunSpecV1,
    "run-outcome": RunOutcomeV1,
    "run-event": RunEventV1,
    "finding": FindingV1,
    "evidence-artifact": EvidenceArtifactV1,
    "evidence-manifest": EvidenceManifestV1,
    "execution-policy-bundle": ExecutionPolicyBundleV1,
    "teardown-verification": TeardownVerificationV1,
    "receipt-v5-payload": ReceiptV5Payload,
    "dsse-envelope": DsseEnvelopeV1,
    "patch-proposal": PatchProposalV1,
    "patch-approval": PatchApprovalV1,
}


def schema_document(model: type) -> dict:
    document = model.model_json_schema()
    document["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    document["$id"] = f"https://workflo.dev/schemas/v1/{model.__name__}.json"
    return document


def render(model: type) -> str:
    return json.dumps(schema_document(model), indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if regeneration would change the committed schemas",
    )
    args = parser.parse_args()

    REPO_SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    changed: list[str] = []

    for name, model in EXPORTED.items():
        path = REPO_SCHEMA_DIR / f"{name}.schema.json"
        rendered = render(model)
        if path.exists() and path.read_text(encoding="utf-8") == rendered:
            continue
        changed.append(path.name)
        if not args.check:
            path.write_text(rendered, encoding="utf-8")
            print(f"wrote {path.name}")
        else:
            print(f"DRIFT: {path.name} does not match regeneration")

    if args.check:
        if changed:
            print(f"{len(changed)} schema file(s) are stale; re-run export_schemas.py")
            return 1
        print(f"ok: {len(EXPORTED)} schemas up to date")
        return 0

    if not changed:
        print(f"ok: {len(EXPORTED)} schemas already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
