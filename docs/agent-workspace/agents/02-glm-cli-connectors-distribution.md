# Agent 02 — GLM-5.3 Flash
## Native CLI Commands, GitHub/Local Connectors, Language Profiles and Distribution

**Workstream:** CLI productization and cross-platform developer experience  
**Branch:** `agent/glm-cli-connectors-distribution`  
**Implementation owner:** GLM-5.3 Flash  
**Core integration owner:** DeepSeek V4.1 Flash-1017  
**Reviewers:** DeepSeek (CLI-core interfaces), GPT-6 Luna (API/GitHub server contracts), MiniMax (credential/security tests), human owner (public command contract and package namespace).

---

## 1. Mission and expected result

Make the Go-based `workflo` executable usable as a polished developer tool. Own user-facing command handlers, command semantics, GitHub/local repository connectors, language-profile detection/manifests and the npm/pnpm/Bun/native install experience.

You are the CLI productization owner, not the CLI core/runtime owner. DeepSeek owns the root executable, application lifecycle, API transport, process control, platform runtime and runner. You add commands and connectors through stable interfaces agreed in advance.

**Expected final CLI user journey:**
1. Install `workflo` from npm, pnpm, Bun or a native OS package.
2. Run `workflo --help`, `--version` and `doctor`.
3. Authenticate as an individual or select a team workspace.
4. Initialize/select a project.
5. Connect a GitHub installation/repository or local repository.
6. Resolve and display the immutable full commit SHA.
7. Detect/choose a Python, Node.js, Go or Java profile.
8. Preview Core, Deep AI and Security stages, runner mode, resource request and privacy policy.
9. Submit a run using the approved API and idempotency contract.
10. Inspect the actual run, gate states, evidence and offline-verification result.

M1 remains intentionally narrower: `doctor`, `run` and `verify`, one deterministic Python/pytest profile, one customer-controlled Linux x86_64 KVM runner. Do not imply all language profiles, deep AI/security or packages are M1-complete.

## 2. Why this model owns this work

Z.ai's GLM-5.3-Flash release reports:
- Terminal-Bench 2.1: **84.3**
- Toolathlon Verified: **78.4**
- DeepSWE v1.1: **63.4**
- NL2Repo: **56.3**
- AutomationBench v1.0.6: **48.8**

Z.ai describes Toolathlon Verified as an official evaluation with pass@1 averaged over three independent runs. Terminal-Bench 2.1 is not comparable with Terminal-Bench 4.0 or 4.1 results reported by other model providers.

Source: https://z.ai/blog/glm-5.3-flash

**Routing hypothesis:** bounded tool use, CLI command orchestration, connectors, profile definition, package-manager compatibility and repeated integration edge cases. These results do not establish UI/visual quality or security authority.

## 3. Ownership and exact file boundaries

### Primary owned paths

| Path | Work |
|---|---|
| `apps/workflo-cli-go/internal/commands/` | command groups, flags, help, preflight and command-level JSON contracts |
| `apps/workflo-cli-go/internal/connectors/` | GitHub/local provider adapters and connector state |
| `apps/workflo-cli-go/internal/source/` | source-provider adapters only; coordinate immutable snapshot interfaces with DeepSeek |
| `packages/npm-workflo/` | package-manager shim and platform optional dependencies |
| `profiles/python/` | Python profile manifest and detection rules |
| `profiles/node/` | Node.js profile manifest and detection rules |
| `profiles/go/` | Go profile manifest and detection rules |
| `profiles/java/` | Java profile manifest and detection rules |
| `scripts/release/install/` | native installer scripts/manifests |
| `tests/installation/` | install/update/uninstall/platform smoke tests |
| Connector-specific CLI tests | fixtures, mock servers and regression tests |

### Shared interfaces

DeepSeek owns:
- root executable, `cmd/workflo`, core app lifecycle;
- API client transport, process/runtime, cancellation and structured logging;
- platform capability and core config interfaces;
- runner lifecycle and low-level protocol.

GLM owns:
- user-facing command tree, command handler code, help text and usage;
- connector adapters and source-selection UX;
- profile discovery and profile manifests;
- package-manager and installer distribution.

No two agents write the same file. If a command needs a core capability missing from DeepSeek's interface, raise an interface request with the input/output types and acceptance tests; do not add a second implementation.

### Must not own

- `apps/workflo-runner-go/`, Firecracker/jailer, cgroup, vsock or host teardown code.
- `packages/workflo-policy-go/`, threat model or security decision logic.
- `apps/control-plane/`, auth/DB/RLS/route implementation.
- `apps/dashboard/`.
- canonical contracts under `packages/workflo-schema/`.
- release publishing, production credentials or GitHub organization administration.

## 4. Work packages

Each package produces a small PR and the listed artifacts. Use dependency IDs from the delivery roadmap and current milestone board.

### GLM-00 — Calibration and repository inventory
1. Record exact model identifier/settings, branch/base SHA and tool permissions.
2. Read ADR-0024, CLI Product Spec, M1 acceptance, API freeze, Repository Structure and operating model.
3. Inventory Python CLI commands, flags, defaults, exit codes, config handling and docs.
4. Inspect `packages/npm-workflo/`: shim, postinstall, vendored wheels, virtualenv behavior and package metadata.
5. Inspect GitHub OAuth/App integration, source helpers and existing workflows.
6. Locate existing `workflo.yaml` / `workflo.yml` readers and writers; identify collision/precedence rules.
7. Identify current package namespaces and public package compatibility obligations.

Deliverables:
- command/flag/output/exit-code matrix;
- package dependency map;
- source connector current-state map;
- profile/config inventory;
- install OS/architecture support matrix;
- migration/deprecation proposal.

Acceptance: source citations and commands reproduced; no source changes in audit.

### GLM-01 — Command contract and navigation
Define commands by user job rather than internal implementation.

Proposed groups:
- root: help, version, completion;
- doctor;
- init;
- auth: login, logout, status, whoami;
- workspace/org: list, select, current, members (only where API exists);
- connect: github, disconnect, status;
- project: init, list, show, select;
- source: inspect, list, select;
- run;
- runs: list, show/status, cancel, logs;
- evidence: list/show/download;
- verify;
- runner: enroll, status, capabilities, drain, revoke;
- config: get, set, validate, explain;
- profile: list, inspect, validate.

For every command, define:

| Dimension | Required decision |
|---|---|
| Invocation | Positional args, flags, aliases, defaults and mutually exclusive options |
| Auth | Required principal, scope and membership |
| Preflight | Local checks before API call |
| API | Exact endpoint/method/contract version |
| Success | Stable human output and JSON schema |
| Errors | Validation/auth/permission/policy/network/server/state distinctions |
| Idempotency | Retry semantics and stable operation identity |
| Exit code | Shared error class; numeric mapping is an owner-approved contract |
| Safety | Confirmation, no-host-execution and no-secret rules |
| Examples | Interactive, noninteractive CI and failure case |

Required acceptance:
- golden transcript tests for TTY and non-TTY;
- JSON output tested against a published schema;
- invalid flag combinations rejected before submission;
- no command implies a feature that is not implemented;
- help includes examples and OS/runner limitations.

### GLM-02 — Safe project and language detection
Detection is observational. It must not execute repository code.

Inspect only bounded manifest/lock files such as:
- Python: `pyproject.toml`, requirements/lock files;
- Node: `package.json`, npm/pnpm/Bun lockfiles;
- Go: `go.mod`, `go.sum`;
- Java: `pom.xml`, Gradle build/wrapper files.

Rules:
1. Do not run npm scripts, Python setup, Gradle wrapper, Maven extensions, Makefiles or project shell scripts on the developer host.
2. Do not execute postinstall/preinstall scripts during detection.
3. Treat file names and manifest content as untrusted input.
4. Apply maximum manifest size, directory depth, file count and scan time.
5. Respect ignore/exclusion rules only after safe parsing; user config cannot bypass policy.
6. If multiple languages are found, show candidate profiles and ask the user to choose or use an explicit config.
7. Framework inference is a hint, not authority.
8. Record detection reason, confidence category and files inspected without copying source into telemetry.
9. User or organization policy can disable a profile.
10. A selected profile is resolved and pinned in RunSpec; guest image/tool versions are not inherited from the client machine.

Acceptance: deterministic fixtures for normal, ambiguous, malformed, malicious and oversized manifests; no host process execution.

### GLM-03 — Local repository connector
Implement:
- path validation and canonicalization;
- Git worktree/repository detection;
- current branch and full HEAD object ID;
- dirty/staged/untracked state;
- explicit choice between committed revision and a policy-approved working-tree snapshot;
- ignored file and sensitive-path treatment;
- submodule and LFS detection;
- symlink/hardlink and nested .git policy;
- source file-count/byte/depth caps;
- canonical source manifest request to DeepSeek's snapshot primitive;
- preview output showing what would be included/excluded.

Requirements:
- No host execution of project code.
- No silent inclusion of untracked or ignored files.
- If working-tree snapshot mode is unsupported, reject it clearly rather than silently running HEAD.
- Never upload source bytes to control plane by default.
- Source archive is produced by the approved snapshot component and sent only to customer-controlled runner.

Acceptance cases:
- clean repository;
- dirty working tree;
- staged/untracked changes;
- missing .git metadata;
- detached HEAD;
- nested repository;
- submodule allowed/denied;
- LFS pointer allowed/denied;
- symlink escape and hardlink ambiguity;
- huge file/tree and depth overflow;
- secret file candidate;
- Unicode/spaces/reserved characters;
- branch changes after source preview.

### GLM-04 — GitHub App client workflow
Build the CLI client-side flow against GPT-6's server contract:
1. Start device/browser authorization using a high-entropy anti-CSRF state/nonce.
2. Display requested scopes and selected organization/repository.
3. Receive installation identity/status; do not receive or store App private key.
4. List repositories visible to the selected installation only.
5. Allow user to select a repo and show whether Contents:read / Checks:write are present.
6. Resolve branch/tag to a full 40-character SHA-1 commit for M1; store algorithm separately if later object formats are supported.
7. Display exact repo, SHA and runner target before submitting.
8. Handle revoked installation, expired grant, missing repo permission, not-found, rate limit and network failure.
9. Show PR-check publication status only when server confirms check permission and publication.

Security rules:
- No PAT prompt as default.
- Do not place tokens in argv, shell history, logs, config or JSON transcript.
- Never request Contents:write, administration or merge permissions for launch.
- Client stores only safe installation/repository references; token brokering is server/runner-side.
- No fallback to anonymous public clone when private authorization fails.

Acceptance:
- public repo;
- private repo;
- repository excluded from installation;
- installation revoked;
- token expired between selection and source checkout;
- wrong account/organization selected;
- branch movement after SHA resolution;
- invalid webhook signature surfaced by backend;
- check publication denied due to missing Checks:write;
- repeated command/request remains idempotent.

### GLM-05 — Language profile registry
Profiles launch in phases. The first M1 path is Python/pytest only; the full beta must deliver Python, Node.js, Go and Java.

Profile metadata required:
- ID and immutable profile version;
- language and framework (optional);
- guest image digest;
- runtime/toolchain version;
- manifest and lockfile requirements;
- preparation stage and dependency source;
- explicit argv arrays for build/test/start/readiness;
- allowed environment variable names (not values);
- output/artifact allowlist;
- default resource/time/output limits;
- network class per stage;
- security scanner/tool IDs and version;
- report parser/schema version;
- known limitations and support level.

Language-specific acceptance:
- Python: pytest/unittest; FastAPI later as explicit app profile.
- Node: respect npm/pnpm/Bun project lock; Jest/Vitest; Express first; Playwright only with pinned browser image.
- Go: Go version pinned; `go test ./...` baseline and optional `go vet`.
- Java: JDK + Maven/Gradle wrapper pinned; JUnit profile; validate wrapper distribution/checksum.

Dependency preparation must be isolated from test execution. Never run arbitrary host shell or use globally installed host toolchain as fallback.

Acceptance for each language:
- minimal passing fixture;
- deterministic failing fixture;
- timeout fixture;
- missing dependency/toolchain fixture;
- bad lockfile fixture;
- malformed test report;
- oversized stdout/stderr/artifact;
- unexpected network attempt;
- guest crash;
- exact profile digest in RunSpec/evidence.

### GLM-06 — Package manager distribution
Target developer experience:

```bash
npm install -g @workflo/cli
pnpm add -g @workflo/cli
bun add -g @workflo/cli
workflo --help
```

Implementation decisions:
- retain current package name until owner approves a rename; verify namespace ownership before publishing new scope;
- thin JS shim that resolves an OS/architecture-specific optional native package;
- Go binary is the actual CLI; no Python wheel, venv or runtime setup;
- avoid arbitrary postinstall downloads; package-resolved binaries preferred;
- validate binary digest before first execution;
- unsupported platform/arch fails closed with actionable guidance;
- package install works with lifecycle scripts disabled where package-manager design permits;
- offline/proxy/corrupt cache behavior is explicit;
- old Python package compatibility/deprecation is versioned, not removed silently.

Target initial package matrix:
- darwin-arm64;
- darwin-x64;
- linux-x64;
- win32-x64.

Linux ARM64 and Windows ARM64 are conditional on real build/test runner availability. Do not publish unsupported target labels.

### GLM-07 — Native OS distribution
Prepare and test:
- Linux x64 tarball first; .deb/.rpm after script and upgrade stability;
- macOS arm64/x64 archives and optional Homebrew tap;
- Windows x64 portable archive/MSI;
- runner installation package distinct from client package (Linux KVM-only strict runner).

Every installer must:
- install to a user-owned location where possible;
- avoid root/admin unless required and explained;
- validate SHA-256 and provenance before execution;
- not overwrite active processes;
- preserve user config and evidence on upgrade/uninstall;
- provide explicit rollback;
- clean partial install on failure;
- support pinned version;
- never delete customer receipts/config by default;
- be truthful about signature/notarization status.

Zero budget means no false claim of Apple notarization or Windows publisher trust if signing identity is unavailable.

### GLM-08 — Install and shell compatibility
Run clean-machine tests:
- bash/zsh/fish and PowerShell;
- Unicode and spaces in paths;
- paths with reserved characters;
- PATH setup and shell restart;
- proxy and offline environments;
- package lifecycle scripts disabled;
- corrupt download/package cache;
- wrong architecture;
- Windows SmartScreen/antivirus path;
- Ctrl-C and signal propagation;
- upgrade while process active;
- rollback and uninstall;
- reinstall after partial failure.

Acceptance: every claimed OS/package combination has a reproducible CI or clean-machine report.

### GLM-09 — Documentation and migration
Produce:
- CLI reference from actual help output;
- install guide per OS/package manager;
- connector permission guide;
- profile reference;
- `workflo.yaml` configuration reference;
- error/exit-code guide;
- migration matrix from current Python CLI;
- troubleshooting for authentication, private repo, KVM eligibility, profile missing and receipt verification.

Every command must be tested against the current binary; don't document planned commands as available.

### GLM-10 — Handoff and review obligations
Handoff to DeepSeek:
- command handler interfaces;
- connector/source adapter interface;
- expected error types and JSON output;
- package binary naming/target triples;
- install/update lifecycle.

Handoff to GPT-6:
- required API endpoints, scopes, response fields and error semantics;
- repo selection and installation-grant behavior;
- check-run permission requirements.

Handoff to MiniMax:
- token exposure test points;
- source filtering and secret-canary fixtures;
- installer binary integrity cases;
- malicious manifest fixtures.

Handoff to Gemini:
- actual command and gate state vocabulary;
- source connection and installation statuses;
- output semantics for evidence and trust status.

## 5. Required test matrix

| Area | Required cases |
|---|---|
| Commands | help, missing arg, conflicting flags, unknown flag, JSON and TTY output |
| Config | missing, malformed, old version, unknown field, secret-like value redaction |
| Detection | 4 language manifests, ambiguous, malformed, malicious, oversized |
| Local connector | clean/dirty/untracked, branch movement, symlink, submodule, LFS, traversal |
| GitHub | public/private, unauthorized, revoked, expired, wrong installation, rate limit |
| Profiles | good/broken/timeout/missing runtime/malformed report/resource cap |
| npm | npm, pnpm, Bun, scripts-disabled, offline, proxy, wrong arch, bad digest |
| Native | Linux/macOS/Windows install, update, rollback, uninstall, reinstall |
| Privacy | no source/log/env/token in CLI telemetry or hosted payload |
| Compatibility | existing Python commands/config/receipts remain supported during migration |

## 6. Performance and usability targets

- Help/version/doctor should complete promptly without network unless doctor explicitly checks configured control-plane.
- Repository detection is bounded by file count, depth, bytes and time.
- No full repository scan is run by default on every CLI invocation.
- Connector/API output uses pagination and bounded sizes.
- CLI JSON output is stable and scriptable.
- No command hangs indefinitely on token/device flow, proxy or runner connection; every wait has cancellation and timeout.
- User sees whether a command is local-only, remote API, queued or executing.

## 7. Stop conditions

Stop and raise a task/contract request if:
- a command requires a new state or schema field;
- a connector needs broader GitHub permissions;
- source content would be sent to the control plane or hosted model without approved data path;
- a profile requires host execution or unpinned tools;
- the package namespace is not confirmed;
- binary integrity cannot be verified;
- a platform cannot be tested;
- command behavior would break a documented compatibility surface;
- a PR would require changing DeepSeek's core API/runtime files without reservation.

## 8. Definition of done

Developers on all claimed client targets can install the same Go-based `workflo` UX through npm, pnpm, Bun or native distribution; use discoverable commands; connect local or authorized private GitHub repositories; resolve and confirm an exact commit; choose one of the supported language profiles; submit/status/cancel runs; inspect evidence and verify receipts; and do so without Python execution dependency, token leakage or unsupported local strict-isolation claims.
