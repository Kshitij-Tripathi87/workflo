# Workflo CLI Product Specification

## 1. Product contract

The Workflo CLI must be a native executable named workflo. Installing through npm, pnpm, Bun or a native platform channel must not require the user to install Python, Node as an execution runtime, or a model runtime. Node may be used by the package-manager shim only; the actual CLI and local runner client are Go binaries.

Primary command requirement:

~~~bash
workflo --help
workflo --version
workflo doctor
workflo init
workflo auth login
workflo connect github
workflo run --repo https://github.com/owner/repo --ref <full-sha> --test
workflo status <run-id>
workflo verify --receipt ./receipt.json --pubkey ./trusted-key.pem
~~~

Help must present every command, one-line purpose, common flags and examples. Every command needs stable output and predictable errors.

## 2. Command groups

### Root
- help: list command groups and examples.
- version: print CLI version, build commit, platform and protocol versions.
- completion: generate shell completion for supported shells.

### init
- detect supported project manifests without running repository code.
- create or update Workflo config only after showing the proposed diff.
- record project identity and safe default profiles.
- never overwrite existing config without confirmation or explicit --force.
- no credential collection.

### doctor
- client checks: OS, CPU architecture, CLI update, config validity, credential store availability, control-plane connectivity.
- runner checks: Linux, KVM device/read-write permission, Firecracker/jailer versions and digests, cgroups, seccomp, network enforcement, guest image availability, resource limits and disk availability.
- display separate outcomes: CLIENT_READY, RUNNER_STRICT_ELIGIBLE, RUNNER_DEV_ONLY, RUNNER_INELIGIBLE.
- no automatic privileged setup or silent remediation.

### auth
- login, logout, status, whoami, device authorization.
- token scopes and expiry visible; secrets never printed.
- support individual account and selected organization/team context.
- local access/refresh tokens in OS credential store; restricted file fallback only where platform vault is unavailable and explicitly disclosed.

### org/workspace
- list/select organizations and workspaces.
- show membership role and accessible projects.
- never trust an organization ID supplied in the client request without server authorization.

### connect
- github login/install selection, repository listing, permission verification and disconnect.
- local repo connector is always available.
- connector status shows scopes, installation identity and expiration/revocation state.

### project
- init/list/show/select.
- associate repository, policy and runner pool.
- use API authority for membership and resource scope.

### run
Run must accept one source selector and one or more explicit profile stages. Suggested flags:
- --repo URL or --path DIRECTORY (mutually exclusive)
- --ref full SHA or a resolvable Git ref; resolve and display the full SHA before admission
- --profile python|node|go|java|auto
- --test (core deterministic checks)
- --deep-test (AI-assisted exploration; requires BYOK and explicit consent when hosted metadata is enabled)
- --security-test (explicit authorized security stage)
- --config workflo.yaml
- --dry-run
- --json
- --wait / --no-wait
- --output-dir
- --allow-hosted-metadata (per-run opt-in; cannot override org policy)
- --provider-profile name (references local protected config; does not accept a raw API key)
- --timeout / --cpu / --memory / --disk only within policy maximums.

Mutually exclusive and contradictory flags must be rejected before any remote submission. Test stage combinations are visible in the planned run output.

### runs/status/cancel/logs
- runs list supports bounded pagination and filters.
- status reads the canonical server lifecycle and shows run and attempt separately.
- cancel is idempotent and requests cancellation; it must not claim the VM is stopped until host evidence confirms.
- logs streams bounded sanitized logs; raw guest logs remain customer controlled where policy requires.
- no arbitrary file path or host shell access.

### evidence/verify/inspect/explain
- download evidence only after authorization.
- offline verify works without network once receipt/evidence/public key are present.
- distinguish signature verification, trust anchor validation, evidence completeness, QA verdict and teardown status.
- never report “software is defect-free”; it reports tested scope and findings.

### runner
- enroll, status, capabilities, drain, revoke and uninstall.
- installation command produces a one-time enrollment token that expires and is shown only once.
- runner identity is bound to organization/project/pool and certificate identity.
- drain stops new claims and allows bounded current runs to complete/cancel.
- revoked runner cannot claim or upload new evidence.

### config
- get/list/set; validate config schema; redact credentials.
- provider profiles reference OS-vault key aliases; never place raw API key in CLI args or config.
- show effective privacy policy and whether hosted inference is currently permitted.

## 3. Run contract and output

Before submission, CLI prints:
- repository identity;
- exact commit SHA;
- selected test stages;
- language/profile;
- target runner/pool and strict/development profile;
- policy version/digest;
- resource budget;
- BYOK provider alias and metadata consent state if deep AI is selected.

CLI asks for confirmation for sensitive actions unless --yes is used in CI and policy already authorizes the operation. No prompt may be treated as authorization to expand sandbox capabilities.

Run response includes:
- run_id;
- attempt_id if assigned;
- admitted/queued/rejected state;
- status URL/API reference;
- idempotency correlation.

Stable exit codes must distinguish:
- CLI argument/config/auth error;
- policy rejection;
- submission/connectivity failure;
- infrastructure failure;
- QA finding/failure;
- trust/attestation failure;
- user cancellation;
- incomplete/unknown state.

The exact numeric mapping is a shared contract decision, not an agent-local invention.

## 4. Language profile requirements

### Python
- Discover pyproject.toml, requirements files and supported lockfiles.
- Run pytest when configured; do not assume the presence of pytest config is safe to execute.
- Pin Python interpreter in the guest profile.
- Support FastAPI/Flask/Django application startup only through explicit profile fields.
- Report whether dependencies were lock-pinned.

### Node.js
- Discover package.json and lockfiles (npm, pnpm, Bun).
- Respect declared package manager and pinned Node runtime.
- Support npm test, pnpm test, bun test and approved Playwright profile.
- Never execute postinstall in the host. Lifecycle scripts run only in a constrained preparation environment with dependency egress policy.
- No global package install into the runner host.

### Go
- Discover go.mod.
- Pin Go version.
- Run go test ./... as the default only when profile is selected.
- Restrict module fetch to preparation stage.

### Java
- Discover pom.xml, Gradle wrapper/build.gradle.
- Pin approved JDK and Maven/Gradle profile.
- Run mvnw test or gradlew test only inside the guest.
- Verify wrapper distributions/checksums where present.

Detection proposes a profile; policy/user selection determines execution. A repository file cannot silently override org policy.

## 5. Configuration format

Use one versioned Workflo project file. Existing repo currently has workflo.yaml/workflo.yml handling, and a design review identified collision risk with a proposed .workflo/workflo.yaml. Do not introduce another path until the actual existing CLI behavior has been reconciled.

The project config should describe:
- schema version;
- project/repository identity (optional);
- language/profile;
- explicit command arrays, not shell-interpolated strings;
- app startup configuration;
- readiness checks;
- test stages;
- security scope;
- resource bounds within organization policy;
- artifact allowlist;
- provider metadata policy identifier, not provider key.

Unknown fields are rejected or ignored only according to an explicit forward-compatibility rule. No arbitrary script is executed during init or config load.

## 6. Installation and distribution

### npm/pnpm/Bun
Intended experience:
~~~bash
npm install -g @workflo/cli
pnpm add -g @workflo/cli
bun add -g @workflo/cli
workflo --help
~~~

Implementation:
- Publish a tiny JS executable shim plus platform-specific optional binary packages, or an equivalent signed package arrangement validated on all three package managers.
- Prefer package-resolved platform binaries over an unverified postinstall network fetch.
- No Python venv, wheel installation or Python PATH requirement.
- Avoid installation-time execution of arbitrary scripts where package-manager policy can block them.
- Verify package content hashes and release provenance.
- Confirm @workflo registry scope ownership before publication; if unavailable, choose an approved scope and document it.

Target binary matrix:
- darwin-arm64
- darwin-x64
- linux-x64
- linux-arm64 only after runner/build verification
- win32-x64
- win32-arm64 only when supported CI/build host exists

### Native channels
- macOS: signed versioned tarball and optional Homebrew formula/tap; notarized installer only if signing infrastructure exists.
- Windows: signed archive/MSI where signing is available; Scoop/WinGet manifest only after package validation. Unsigned binaries must be transparently labelled and must not claim verified publisher identity.
- Linux: signed checksum manifest and tarball; .deb/.rpm packages after install/uninstall/upgrade tests.
- Customer runner installation is Linux-only for strict KVM under the current ADR.

### Release integrity
- Build on clean CI runners.
- Record version, commit, target OS/arch and build toolchain.
- Generate SHA-256 checksums.
- Produce build provenance/attestation (for example GitHub artifact attestations/Sigstore where available).
- Sign release manifests where signing material is available.
- Verify before installation/update.
- Support pinned version and safe rollback.
- No self-updater may overwrite a running binary or execute an unchecked replacement.

## 7. Compatibility and migration

The current Python CLI at apps/workflo-cli is 1.1.1 and the current npm shim launches a Python venv. Preserve it while the Go CLI reaches command parity. Do not delete it or change public receipts during the first migration slice.

The Go CLI becomes canonical only when:
- help/command parity exists for the launch commands;
- config and auth compatibility is documented;
- core run lifecycle works against the canonical control plane;
- offline receipt verification is correct;
- all installer targets tested are reproducible;
- old Python and new Go implementations agree on shared contract fixtures;
- no strict-profile behavior falls back to dev mode.
