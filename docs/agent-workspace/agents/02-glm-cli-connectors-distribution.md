# Agent 02 — GLM-5.3 Flash
## CLI Command Experience, GitHub Source Connector, Profiles and Distribution Design

**Branch:** `agent/glm-cli-connectors-distribution`  
**Primary owner:** GLM  
**Reviewers:** DeepSeek (CLI core/interfaces), GPT-6 Luna (API/GitHub server auth), MiniMax (source/path security), human owner (scope/package release)  
**M1 priority:** P0 client integration; package publishing is deferred

## 1. Mission and expected capability fit

**Mission:** turn the Go CLI core into a predictable command-line product and implement the GitHub source-selection/ref-resolution experience consumed by M1.

Routing hypothesis: command UX, tool/workflow integration, validation, connector fixtures, profile metadata and package distribution design. Published tool-use benchmark results support the task hypothesis, not a guarantee of Workflo-specific correctness.

**Use this agent for:** command syntax and help, flag validation, JSON/human output, exit codes, GitHub ref resolution, source metadata and safe connector test matrices.

**Do not treat it as:** owner of Go CLI entrypoint/core transport, Firecracker runtime, backend auth/DB, security sign-off or permission to publish packages.

## 2. M1 architecture and ownership boundary

- DeepSeek owns executable entrypoint, API transport/core, auth client contract, verifier and runner client.
- GLM owns command packages, connector packages, presentation/error UX and CLI golden fixtures.
- Luna owns server-side GitHub App/auth broker and FastAPI operations.
- MiniMax owns policy/security test specification and independent review.
- M1 target source is GitHub only, pinned by a full immutable commit.
- Local-folder connector, multiple VCS and broad package-manager publishing are post-M1.
- The CLI binary must not install or invoke Python, Node, Docker or a model provider as a runtime dependency.
- Never leak GitHub installation credentials into guest, RunSpec, stdout, logs, receipt or evidence.

## 3. Owned paths

**Primary**
- `apps/workflo-cli-go/internal/commands/`
- `apps/workflo-cli-go/internal/connectors/github/`
- `apps/workflo-cli-go/internal/clioutput/`
- `apps/workflo-cli-go/internal/profiles/` (M1 metadata for the single pinned pytest profile only)
- `apps/workflo-cli-go/tests/golden/`
- connector/command documentation and fixtures under the agreed CLI docs path.

**Not owned**
- `cmd/workflo/`, CLI app lifecycle, API transport/auth implementation, core state machine, runner client and receipt verifier (DeepSeek).
- FastAPI routes, OAuth, GitHub App private key storage, database and dispatch (Luna).
- `worker/`, guest runtime, policy enforcement defaults and receipt signer (DeepSeek + human).
- Security acceptance and exploit disposition (MiniMax + human).
- Dashboard UI (Gemini).
- Public npm publishing, installer release and production credentials without separate owner approval.

**Shared interface:** agree exported Go types/functions with DeepSeek before implementation. Do not write around internal implementation details or use reflection/dynamic maps to evade type ownership.

## 4. M1 command behavior

| Command | GLM deliverable | Required behavior |
|---|---|---|
| `auth login/status/logout` | UX/flags/help/errors | Use DeepSeek auth client; never print token or auth code after exchange |
| `doctor` | Output sections and JSON schema presentation | Client vs strict runner eligibility; show why KVM is unavailable without implying local fallback |
| `run` | Flag model/help/golden transcript | Exact GitHub repo + full SHA, pinned profile, runner, idempotency; invalid combinations rejected pre-submit |
| `status` | Human/JSON rendering | Execution, QA and trust shown separately; unknown values remain unknown |
| `cancel` | UX and confirmation | Explicitly says cancellation requested, not termination proven |
| `verify` | Flag/help/error UX | Offline mode explicit; no provider/API call |

Command flags and outputs are frozen on D2 with DeepSeek, Luna and MiniMax.

## 5. Work packages

### GLM-01 — Existing client/package audit · D1

Inspect Python CLI, npm wrapper, Go target plan and GitHub integration paths.

Deliver:
- command/flag compatibility inventory;
- current Python and npm dependency map;
- GitHub auth/read-scope inventory;
- unsupported/ambiguous command semantics;
- proposed minimal M1 command tree.

**Acceptance:** exact paths/symbols and a list of behavior to preserve vs intentionally defer. No rewrite during audit.

### GLM-02 — Command and output contract · D2–D3

Freeze:
- commands/subcommands/flags;
- defaults and required inputs;
- argument validation order;
- human output and JSON output schema;
- stable exit-code taxonomy;
- cancellation and timeout semantics;
- help examples and shell completion requirements only where cheap.

**Acceptance:** golden transcripts and table-driven invalid-input cases; command handlers compile against DeepSeek's approved interfaces; no hand-maintained duplicate state machine.

### GLM-03 — GitHub source/ref resolution · D4–D8

Implement the M1 GitHub-only connector through the approved auth/broker flow:
- canonical repository identity;
- resolve branch/tag/ref to full object ID;
- display the resolved full SHA before submission;
- verify repository and commit access;
- distinguish 404/no permission from not found where provider behavior allows;
- handle revoked/expired auth and rate limit;
- never accept abbreviated commit ID as immutable identity;
- do not download source to the CLI host unless the approved interface explicitly requires it.

Coordinate with Luna on GitHub installation/repository selection and DeepSeek on RunSpec input.

**Acceptance:** public repo fixture and private repo fixture (when authorized installation is available) resolve exact SHAs; branch-move-after-resolution test remains pinned; missing/revoked scopes fail closed; credential scanning finds no token in request/log/evidence.

### GLM-04 — Safe source metadata and UX · D7–D11

Prepare client-visible source metadata and validate server responses. Source archive policy is enforced by host/policy implementation; GLM provides test cases for:
- path traversal and absolute path names;
- symlink escape;
- large file/count/total archive;
- submodule and LFS declaration;
- case normalization and Unicode path collisions;
- dirty/uncommitted state only if local connector is later enabled.

**Acceptance:** connector rejects unsupported source states before admission where it can know them; server/host rejects them authoritatively; tests cover the handoff.

### GLM-05 — M1 profile registry · D10–D12

Expose only the approved `python-pytest@PINNED_VERSION` profile:
- stable profile ID/version;
- structured argv contract;
- image/toolchain identity;
- supported test report schema;
- time/resource bounds displayed to user.

Do not invent language detection that suggests unsupported profiles are runnable.

**Acceptance:** CLI profile list has exactly the approved M1 profile; golden RunSpec binds correct profile/version/policy digest; profile mismatch is rejected before VM provisioning.

### GLM-06 — CLI end-to-end tests · D12–D20

Build a fixture-driven CLI suite:
- valid run;
- full vs abbreviated SHA;
- auth expired/revoked;
- unauthorized repository;
- duplicate idempotency key;
- runner unavailable/ineligible;
- queued/claimed/running/completed state;
- test failure vs infrastructure failure vs trust failure;
- cancel request vs confirmed termination;
- tampered evidence and wrong trust key;
- no-KVM strict failure.

**Acceptance:** test transcript and exact commands are attached; all mock-server tests are labelled MOCKED-INTEGRATION; only real CLI+KVM acceptance is credited as REAL-KVM.

### GLM-07 — Native distribution design and smoke tests · D18–D22

For M1:
- help DeepSeek verify clean Go binary launch on supported CI targets;
- ensure no Python or Node dependency is added;
- produce archive/checksum/provenance design and clean-machine test procedure;
- verify CLI behavior does not depend on repository working directory or a local virtualenv.

Post-M1:
- npm/pnpm/Bun platform packages;
- installers and update/rollback;
- signature/provenance release workflows;
- public package publishing after owner approves scope/name.

**Acceptance:** clean target machines run `--help`, `--version` and eligible client `doctor`; unsupported strict execution is reported correctly. Do not claim production distribution until signed release acceptance.

### GLM-08 — Handoff · D23–D25

Deliver:
- command contract and golden transcript paths;
- connector API and auth sequence;
- source/SHA behavior;
- profile registry entry;
- test report with mock vs real labels;
- compatibility/deferred-command list;
- packaging design and known limitations.

**Acceptance:** DeepSeek and Luna can maintain the command/connector interface without undocumented knowledge from GLM.

## 6. How to work

1. D1 audit first; do not start package rewrite.
2. Freeze exported interfaces with DeepSeek before parallel coding.
3. Implement one command and one connector path per PR.
4. Prefer static types and exhaustive enum handling.
5. Add positive and negative golden tests in the same PR.
6. Rebase daily and report blockers before they cost a full day.
7. Use synthetic repositories and mock GitHub server tests; never run adversarial tests against unrelated public targets.
8. Link each PR to GLM task IDs and interface version.

## 7. Do not

- create a second `main.go` or duplicate API/auth client;
- introduce Python or Node as a CLI runtime dependency;
- fabricate unsupported profile availability;
- accept a branch name as final source identity;
- send source/GitHub token to hosted inference or guest;
- store credentials in CLI config as plaintext;
- write a generic shell wrapper around repository-supplied strings;
- change FastAPI contracts without Luna/owner approval;
- alter receipt/trust semantics;
- publish npm/native packages or claim installer support before clean-machine proof;
- approve own security-sensitive behavior.

## 8. Completion evidence

Every PR includes command tree, changed-file list, API/schema impact, golden test command and counts, fixture provenance, exact mock/real classification, known limitations and handoff owner.
