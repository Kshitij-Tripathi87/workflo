# 06 — Testing Strategy, Quality Gates and Acceptance Matrix

**Parent:** [Implementation Blueprint](00-master-implementation-plan.md)  
**Purpose:** turn “it works” into repeatable evidence for every product surface and isolation backend.

## 1. Testing philosophy

Workflo's tests must prove both **functional behavior** and **trust-boundary behavior**. A mocked VM client can verify the manager's orchestration but cannot prove VM isolation. A mocked provider can verify the adapter's request format but cannot prove real provider semantics. A unit test with a fake PostgreSQL connection cannot prove Row Level Security. Tests must be tagged by what they actually demonstrate.

Use these evidence labels consistently:

- `UNIT`: pure logic with controlled dependencies.
- `SERVICE_INTEGRATION`: real service/database with test configuration.
- `PLATFORM_INTEGRATION`: real OS/hypervisor/runner.
- `PROVIDER_LIVE`: real provider API under protected credentials.
- `ADVERSARIAL`: deliberately malicious or fault-injected scenario.
- `END_TO_END`: user journey crossing multiple product components.
- `RELEASE`: fresh artifact/install/upgrade/rollback acceptance.

A test report must show pass, fail, blocked, not-run and skipped separately. Security release gates must fail on mandatory `SKIPPED` or `NOT_RUN` cases.

## 2. Test layers

### L0 — static and build quality

| Area | Tests |
|---|---|
| Python | ruff/formatter/lint, mypy or pyright where configured, compileall, dependency checks |
| TypeScript | eslint, tsc, Next build, Zod mirror schema parity |
| Schema | Pydantic model tests, export JSON Schema `--check`, cross-language golden contract vectors |
| Packaging | wheel/sdist build, lockfile integrity, pinned dependency policy |
| Security hygiene | secret scan, dependency/SBOM scan, SAST, license/policy check |
| Workflow integrity | YAML parse, action pinning, workflow paths/branch triggers, no `continue-on-error` hiding security failures |

### L1 — unit tests

Cover:

- RunSpec validation, policy resolution and immutable digest calculation.
- Lifecycle state machine: legal and illegal transitions, repeated commands, retry and cancellation.
- Source snapshot path rules, symlinks, file count/size/determinism.
- Assignment signature, expiry, one-time capability, fencing token and sequence number.
- Host backend eligibility and no-fallback logic.
- VM resource limit construction and invalid limits.
- Host/guest frame parser, size guard, unknown type, replay and out-of-order sequence.
- Agent plan validation, capability mapping, tool arguments and per-tool budgets.
- Provider configuration, adapter selection, retry policy and normalized response.
- Cloud sanitization allowlist and secret/source marker denials.
- Local model endpoint verification and no cloud fallback.
- Event digest chain, evidence manifest, DSSE envelope, signature verification and key trust.
- Teardown state mapping and receipt finalization rules.
- CLI exit-code mapping and configuration migration.

### L2 — service integration

Real dependencies where their correctness matters:

- PostgreSQL with migrations, RLS, `FORCE ROW LEVEL SECURITY`, non-owner/non-superuser role, no `BYPASSRLS`.
- Dispatch transaction: run + attempt + outbox committed atomically.
- Runner claim/lease/heartbeat and fencing behavior.
- Auth scopes, refresh/revoke, per-project permission.
- Provider secret storage with fake KMS for unit integration and an actual supported KMS test in protected environment.
- Inference gateway with stub upstream that captures exact serialized request in memory.
- Evidence upload size caps, digests, event sequence and partial upload recovery.
- Dashboard API client and SSE replay cursor.
- OS credential vault integration on GitHub hosted runner per OS, where available.

### L3 — platform integration

Must execute on real OS/hypervisor hardware or a trusted runner that exposes the real hypervisor:

- Linux Firecracker/KVM boot, guest protocol, source transfer, workload, app test and teardown.
- macOS Virtualization.framework boot, guest protocol, disk lifecycle, network isolation and teardown.
- Windows Hyper-V boot, guest protocol, VM isolation, networking, force stop and disk cleanup.
- OS native helper signing/entitlement/service registration and update.

Do not run these suites with a fake Firecracker client and call them “platform tests”. Mocks may coexist for unit test speed, but the real gate is separate.

### L4 — adversarial/security testing

Use controlled fixtures and benign exploit attempts; do not run production malware or destructive test payloads. Each security scenario has a success criterion, evidence item and owner.

### L5 — end-to-end/regression

- Install CLI from published artifact.
- `init`, `doctor`, provider selection and project configuration.
- Exact source snapshot, run submission and backend execution.
- All nine agent capabilities under policy.
- Report/evidence/receipt/verification.
- CLI and web create same RunSpec, same receipt verifier and lifecycle outcome.
- Upgrading a previous CLI/runtime/guest image without corrupting active runs.

### L6 — release acceptance

- Signed CLI/native helper/guest images and immutable digests.
- SBOM/provenance artifact verification.
- Real backend gate evidence for every OS/backend advertised as strict.
- Provider privacy acceptance and tenant isolation.
- Fresh-machine install/uninstall/rollback tests.
- Full release checklist with explicit blockers and limitations.

## 3. Repository-specific test commands

The repository has several Python packages whose tests use generic top-level test module names. Run suites separately to avoid collection/import collisions. The repository's own P4 guidance lists this per-package split:

```bash
pytest -q workflo-ai-integration/tests
pytest -q apps/worker-engine/tests
pytest -q apps/sandbox-executor/tests
pytest -q packages/workflo-schema/tests
pytest -q apps/workflo-cli/tests
pytest -q packages/sandbox-runtime/tests
pytest -q worker/tests
```

Schema and TypeScript contract parity (from `docs/reconciliation/PHASE_0_WORKFLO_TRUST.md`):

```bash
python -m pip install -r packages/workflo-schema/requirements-schema-export.txt \
  -e './packages/workflo-schema[dev]' -e ./packages/sandbox-isolation
python packages/workflo-schema/scripts/export_schemas.py --check
python -m pytest -q packages/workflo-schema/tests
pnpm install --frozen-lockfile
pnpm --filter @workflo/contracts test
pnpm --filter @workflo/events test
```

Additional active surfaces:

```bash
# FastAPI control plane (run in its own env, with required test extras)
pytest -q apps/control-plane/tests

# Dashboard
pnpm --dir apps/dashboard lint
pnpm --dir apps/dashboard build

# Workspace regression (may include legacy root app compatibility scripts)
pnpm lint
pnpm typecheck
pnpm test
```

Before release, inspect workflow commands and ensure these tests actually run on the intended Python/Node versions. A test command passing locally doesn't replace CI evidence from the exact commit.

## 4. Coverage and mutation targets

Coverage targets are floors:

| Area | Target |
|---|---:|
| Policy admission and no-fallback logic | ≥90% branch |
| Source snapshot/path resolver | ≥90% branch |
| Host/guest protocol and capability verifier | ≥90% branch |
| Provider privacy allowlist/sanitizer | ≥95% branch |
| Agent tool authorization/argument validation | ≥90% branch |
| Lifecycle and outcome computation | ≥90% branch |
| Receipt canonicalization, signature and evidence verifier | ≥95% branch |
| Teardown verification and trust outcome | ≥95% branch |
| General application code | ≥80% line |

Mutation tests should kill changes that:

- skip signature verification;
- accept an expired or replayed capability;
- permit unknown tools or widen capabilities;
- send free-form log text to cloud model;
- bypass privacy gateway;
- ignore an egress firewall failure;
- map a failed teardown probe to clean;
- let guest overwrite evidence or receipt payload;
- allow a development runtime to satisfy strict profile;
- ignore source/policy mismatch.

Coverage percent is not a substitute for these security semantics.

## 5. Fixture repository suite

Create a maintained `tests/fixtures/prototype-lab/` or separate `examples/workflo-lab/` with reproducible pinned fixtures. All fixture source is test material and may be read in CI; do not use arbitrary user project examples.

| Fixture | Contents | Purpose |
|---|---|---|
| `python-fastapi-good` | FastAPI service, tests, health endpoint | Passing basic run; app start/API |
| `python-fastapi-broken` | One deliberate functional regression | QA failure vs infrastructure failure |
| `node-api-good` | Node/TypeScript API with lockfile | Node build/test and app readiness |
| `browser-checkout` | Local storefront stub with login/cart/checkout forms | Playwright flows, assertions and browser evidence |
| `api-contract-change` | Baseline/candidate provider response schema | Exact revision comparison |
| `log-failure` | Known safe error code and structured logs | Log summarization and failure classification |
| `hostile-repository` | Benign path traversal/symlink/archive/large-file/prompt-injection markers | Source handling and agent defenses |
| `network-probe` | Attempts to reach allowed and denied endpoints | Egress default deny/proxy allowlist |
| `resource-pressure` | Bounded CPU/memory/disk/process load tests | Host resource limits and cleanup |
| `secret-canary` | Fake token strings and unique source sentinel markers | Prove no secret/source egress or artifact leakage |
| `agent-plan-malformed` | Unknown tools, unsafe args, oversized plan | Tool gateway schema rejection |
| `receipt-tamper` | Altered receipt/evidence, swapped run bundles | Offline verifier rejects |

Keep fixture repositories deterministic and include expected commit/tree digests in fixture manifest. The `hostile-repository` fixture must use fake credentials and safe actions only.

## 6. Agent capability test matrix

| Capability | Positive test | Negative test | Acceptance evidence |
|---|---|---|---|
| Repository inspection | Local model reads allowed `src/` file | Path traversal, excluded secret file, cloud read-file plan | Resolved path audit, capability denial, no source in cloud request |
| Test execution | Runs configured `unit-tests` command | Agent invents `curl|bash` or arbitrary command | argv hash, allowed check id, timeout result |
| App startup | Declared app starts and health endpoint responds | Command tries host mount, port collision, hangs | Guest process record, health status, termination |
| API testing | Expected 200/401/404 behavior | External host, private network, credential header injection | Route id, method, status, egress denial, body policy |
| Browser testing | Login and checkout happy-path fixture | Navigate external origin, download malicious file, read host cookie | Origin check, browser action ledger, artifact quarantine |
| Log analysis | Safe structured exception class summarized | Full stack trace contains fake secret/source; oversized logs | Redaction count, event ID, no raw text in cloud request |
| Failure analysis | Explain failing test based on evidence | Model claims observed behavior not present in ledger | Claim provenance tag and verifier checks |
| Agent activity | Allowed/denied actions recorded in order | Replayed event, duplicate sequence, missing tool result | Event chain and signed activity summary |
| Repair suggestions | Local model creates valid diff artifact | Patch tries absolute path/symlink or modifies original worktree | Patch digest, safe output, original git status unchanged |

## 7. Provider and privacy tests

### 7.1 Cloud request capture

Create unique canaries, e.g. `WF_SOURCE_CANARY_<random>` and `WF_SECRET_CANARY_<random>`, in source files, logs, test output, environment variables and browser page text. Use fake provider servers which capture the full request in-memory. Assert the canary bytes never appear in request body, URL, headers or telemetry. Also verify the request contains only allowed enums, counts, IDs and timing data.

Run at least one test per cloud provider adapter; common schema/privacy tests should run against all adapters through the same adapter contract suite.

### 7.2 Local endpoint privacy

- Local profile default must resolve to loopback.
- Attempt to set cloud endpoint class with local source context: schema rejects.
- Local endpoint down: zero outbound cloud traffic; no fallback.
- Configured LAN endpoint must require explicit user acknowledgement and supported TLS/auth.
- If endpoint reports a different model/provider than expected, display mismatch and reject strict profile if pinning is required.

### 7.3 Live-provider checks

Protected/manual only; use dedicated test accounts/keys with low budgets. The CI system must not print prompts/responses or retain key bytes. Record only:

- provider adapter version;
- model id;
- API response class/status;
- schema valid/invalid;
- latency;
- token counters/usage when returned;
- request ID;
- retry count.

### 7.4 Model quality suite

Build an evaluation set with labeled test missions and expected useful probes. Score plan validity, capability violations, probe coverage, duplicate tool rate, failure-class quality and total budget compliance. Do not present evaluation score as production defect detection rate without a customer-grounded benchmark.

## 8. Platform security gate criteria

Each OS/backend gate must be run on actual hardware/hypervisor. Example suite layout:

```text
platform-gates/
  linux-firecracker/
    test_real_boot.py
    test_filesystem_boundary.py
    test_cgroup_limits.py
    test_egress_default_deny.py
    test_forced_termination.py
    test_teardown_inventory.py
  macos-virtualization/
    test_real_boot.py
    test_vz_entitlement.py
    test_disk_and_network_boundary.py
    test_forced_stop.py
    test_teardown_inventory.py
  windows-hyperv/
    test_real_boot.py
    test_vm_network_boundary.py
    test_resource_limits.py
    test_host_service_permissions.py
    test_force_stop_and_teardown.py
```

Mandatory cases cannot be skipped based on runtime feature detection. If runner lacks KVM/Hyper-V/VZ support, mark the gate `BLOCKED` and do not merge a release attestation. Development unit tests can skip platform-specific hardware paths if clearly isolated from required gate job.

## 9. Failure-injection catalogue

Inject failures at each transition:

- signature invalid before admission;
- snapshot digest mismatch;
- assignment expired or replayed;
- capacity reservation fails;
- firewall apply partially fails;
- scratch disk creation fails;
- VM launch fails;
- guest never connects;
- guest sends malformed/oversized frame;
- app startup fails;
- test command hangs or returns no results;
- agent planner timeout/malformed plan;
- provider HTTP timeout/429/5xx/refusal;
- evidence write fails/disk full;
- guest shutdown hangs;
- VMM force kill fails;
- scratch disk delete fails;
- cgroup/network policy removal fails;
- signer key unavailable;
- control plane connection drops during event upload;
- process/runner host reboots during active attempt.

For each injected failure assert:

1. no false success state;
2. correct run and trust outcome;
3. no resource leak or an explicit incomplete-cleanup state;
4. partial redacted evidence retained where possible;
5. no source/secrets leak to logs or provider;
6. retry is safe/idempotent and does not duplicate workload or receipt.

## 10. Performance measurement

Do not set performance SLOs without baseline measurement. Instrument and report:

- runner claim delay and queue age;
- source snapshot duration and transfer throughput;
- VM provision/boot/readiness time;
- dependency resolution/install time separately from test runtime;
- test and app boot time;
- model first-token and complete-plan latency;
- provider token usage/cost metadata;
- tool execution duration and timeout rate;
- evidence bytes and finalization time;
- shutdown/force-termination/teardown duration;
- CLI startup, dashboard load and SSE reconnect performance.

Measure p50/p95 across at least 30 runs per fixture/hardware class before publishing a claim. Separate first-run image pull/model warm-up from steady-state results. Security gates must not be weakened to improve latency.

## 11. Release gates

| Gate | Required proof | Blocks |
|---|---|---|
| G0 Contract/baseline | Schema export, compatibility, test baseline | Any code changes to shared contract/runtime |
| G1 Vertical slice | Local deterministic run + offline receipt verification | Agent/AI feature expansion if lifecycle remains unstable |
| G2 Linux strict isolation | Real KVM, resource/network/filesystem boundary, cleanup evidence | Any public strict Linux execution claim |
| G3 Inference privacy | Cloud payload capture, local no-fallback, credentials safe | Cloud provider profile launch |
| G4 Agent capabilities | All tool positive/negative cases and activity evidence | Agent features in public beta |
| G5 macOS/Windows backend | Real platform gate on each advertised backend | Local strict execution on that OS |
| G6 Dashboard | Tenant isolation, connected runner and real run E2E | Dashboard launch with run management |
| G7 Release packaging | Signed installer, immutable artifacts, install/upgrade/uninstall | Public release |
| G8 CI integration | Same receipt outcome and verifier with CI run | GitHub Action marketplace/public release |

## 12. CI workflow hygiene

- Required security tests must be separate workflows/jobs with clear prerequisites.
- Fail if a required platform capability is missing in the designated self-hosted runner.
- Do not use `|| true`, `continue-on-error`, or catch-all skip to make tests green.
- Save evidence as CI artifacts with exact commit and workflow run identity.
- Store protected secrets only in protected environments.
- Use immutable action commit references where practical.
- Have a separate verifier job with no producer secrets to download and validate receipt/evidence artifacts.
- Pin guest/VMM/runtime image by digest in release workflows.
- Ensure PR workflows cannot access production provider keys or customer data.
- Keep live-provider tests opt-in or protected and low-cost; unit contract test always runs.