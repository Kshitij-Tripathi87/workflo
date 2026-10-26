# Workflo Run Contract

This document defines the stable contract for `workflo run` execution, receipt structure, and exit codes.

## §5 Receipt Fields

Every `SignedReceipt` carries the following top-level fields:

| Field | Type | Description |
|-------|------|-------------|
| `sandbox_id` | string | Unique run identifier (e.g., `sandbox-a1b2c3d4`) |
| `issued_at` | datetime | RFC3339 timestamp when the receipt was signed |
| `receipt_version` | integer | Protocol version (current: 1) |
| `run_report` | RunReport | Test execution summary |
| `teardown_proof` | TeardownProof | Post-execution cleanup verification |
| `canary_check` | CanaryCheckResult | Egress isolation probe result |
| `lifecycle_events` | list[SandboxLifecycleEvent] | Ordered lifecycle event trail |
| `web_probes` | WebProbeResult? | Browser probe results (if `--web`) |
| `security_probes` | SecurityProbeResult? | Security probe results (if `--security`) |
| `local_model_provenance` | LocalModelProvenance? | Local inference provenance (if model used) |
| `dependency_install_had_network` | boolean | True iff Stage 1 prep ran with network |
| `datahub_writeback` | boolean | Opt-in DataHub assertion writeback |
| `datahub_status` | string | DataHub writeback status |
| `signature` | string | Ed25519 signature over canonical payload |
| `signature_algorithm` | string | Always `Ed25519` |
| `public_key_fingerprint` | string | SHA-256 of the signing public key |
| `key_id` | string? | Provisioned key identifier (if any) |
| `provisioned_at` | datetime? | Key provisioning timestamp |
| `device_id` | string? | Device identifier for provisioned keys |

## §6 Exit Codes

Exit codes are part of Workflo's PUBLIC developer API. Never changed casually.

| Code | Constant | Meaning |
|------|----------|---------|
| 0 | `EXIT_VERIFIED` | Clean: verified teardown, no findings |
| 1 | `EXIT_VERIFIED_WITH_FINDINGS` | Verified but tests failed or findings reported |
| 2 | `EXIT_POLICY_BLOCKED` | Policy denied something material |
| 3 | `EXIT_EXECUTION_FAILED` | Sandbox didn't run such that no receipt can prove |
| 4 | `EXIT_VERIFICATION_FAILED` | The receipt's claims failed verification |
| 5 | `EXIT_CONFIGURATION_ERROR` | Bad config / bad flags / unreadable receipt |
| 6 | `EXIT_INFRASTRUCTURE_ERROR` | Host cannot satisfy the contract |

### Failure Stage → Exit Code Mapping

When a run fails, the `failure_stage` field determines the exit code:

| failure_stage | Exit Code | Notes |
|---------------|-----------|-------|
| `preflight` | 6 | Host cannot satisfy backend (missing bwrap, cgroups, etc.) |
| `config` | 5 | Bad workflo.yaml / flags |
| `snapshot`, `deps`, `rootfs`, `app` | 3 | Code didn't get in or app never booted |
| `tests` | 1 | Tests failed in a sandbox that ran |
| `teardown` | 4 | Cleanup unproven |
| `receipt` | 4 | Artifact could not be produced |
| `isolation` | 4/6 | Backend setup error → 6; isolation claim failed → 4 |
| `probes` | 3/4 | Harness crashed → 3; isolation invariant violated → 4 |
| `agent` | 3 | Deep-test required, no fallback succeeded |
| *(unknown)* | 4 | Default: stricter signal |

### Verify / Inspect / Explain Exit Codes

| Command | Code | Meaning |
|---------|------|---------|
| `verify` | 0 | Signature + teardown + canary + evidence all verified |
| `verify` | 4 | Signature invalid / teardown failed / canary passed / evidence binding mismatch |
| `verify` | 5 | Receipt unreadable / invalid JSON / schema mismatch / no key available |
| `verify` | 6 | Control plane unreachable |
| `inspect` | 0 | Artifact verified (warnings may apply) |
| `inspect` | 4 | Untrusted / unverified / corrupt / unsupported |
| `inspect` | 5 | Receipt file not found / unknown --finding |
| `explain` | 0 | Explanation produced from verified artifact |
| `explain` | 4 | Artifact not verified (cannot explain untrusted material) |
| `explain` | 5 | Receipt file not found / unknown --finding |

## §7 Receipt Schema Versioning

- Receipts carry `receipt_version` (integer)
- CLI supports a set of known versions (`SUPPORTED_RECEIPT_VERSIONS`)
- Unknown versions → `SCHEMA_UNSUPPORTED` → exit 4 (verify) / 4 (inspect)
- Schema-breaking changes increment the version

## §8 Evidence Binding

Namespace-runtime runs include an `evidence_binding` object with:
- `evidence_dir`: Path to the evidence bundle
- `events_count`: Number of ledger events
- `events_sha256`: Hash of events.jsonl
- `bundle_sha256`: Hash of entire evidence bundle
- `manifest_sha256`: Hash of manifest.json

Verification recomputes these digests and compares against the signed binding.

## §9 Teardown Proof

The `TeardownProof` varies by runtime:

### Namespaces Runtime
| Field | Type | Verified When |
|-------|------|---------------|
| `processes_terminated` | boolean | All sandbox processes gone |
| `cgroup_removed` | boolean | cgroup directory removed |
| `network_namespace_removed` | boolean | Netns deleted |
| `workspace_removed` | boolean | Workspace directory removed |

### Docker Runtime
| Field | Type | Verified When |
|-------|------|---------------|
| `container_removed` | boolean | `docker rm -f` succeeded |
| `filesystem_removed` | boolean | tmpfs unmounted and gone |

### Model Inference Teardown
| Field | Type | Verified When |
|-------|------|---------------|
| `model_inference_teardown` | boolean? | Local model process/state wiped |
| `model_inference_error` | string? | Error if teardown failed |

## §10 Canary Check

The `CanaryCheckResult` proves network isolation from inside the sandbox:
- `request_succeeded: false` → egress blocked (expected)
- `request_succeeded: true` → isolation broken (FAIL)
- `error` string explains why check couldn't run

## §11 Canonical Serialization

Receipts are signed over a canonical JSON representation:
1. All fields sorted lexicographically
2. Datetimes in RFC3339 UTC (`Z` suffix)
3. No whitespace, no trailing commas
4. `null` for absent optional fields

This ensures every verifier derives the same signed payload.