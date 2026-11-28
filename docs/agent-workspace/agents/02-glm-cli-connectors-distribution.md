# Agent 02 — GLM-5.3-Flash
## CLI Command Experience, Connectors, Language Profiles and Distribution

**Workstream:** CLI productization  
**Branch:** agent/glm-cli-connectors-distribution  
**Primary owner:** GLM-5.3-Flash  
**Reviewers:** DeepSeek (CLI-core interface), GPT-6 Luna (API and GitHub server contracts), MiniMax (credential/security tests), human owner (public UX and package namespace).

## 1. Why this model owns this work

Z.ai's GLM-5.3-Flash release reports:
- Terminal-Bench 2.1: **84.3**
- Toolathlon Verified: **78.4**
- DeepSWE v1.1: **63.4**
- AutomationBench v1.0.6: **48.8**

Z.ai states Toolathlon Verified results use the official evaluation service and pass@1 averaged over three independent runs. The Terminal-Bench 2.1 score is a different benchmark version from the Terminal-Bench 4.0/4.1 results reported by other labs.

Primary source: https://z.ai/blog/glm-5.3-flash

**Routing hypothesis:** command orchestration, multi-tool workflows, connectors, installer/package-manager integration and repeated edge-case handling. Do not treat 84.3 on Terminal-Bench 2.1 as higher than a 42.3 on Terminal-Bench 4.0.

## 2. Mission

Make Workflo feel like a polished native developer tool:
- commands are discoverable and consistent;
- connectors resolve exact repository identity and commit;
- local and GitHub workflows behave predictably;
- Python/Node/Go/Java test profiles are explicit and auditable;
- npm, pnpm, Bun and native installers deliver the Go binary without Python runtime setup;
- installation and update are verifiable and reversible.

## 3. Owned paths

Primary:
- apps/workflo-cli-go/internal/commands/
- apps/workflo-cli-go/internal/connectors/
- apps/workflo-cli-go/internal/source/ connector adapters only (coordinate interface with DeepSeek)
- packages/npm-workflo/
- profiles/python/
- profiles/node/
- profiles/go/
- profiles/java/
- scripts/release/install/
- tests/installation/
- connector-specific CLI tests.

Shared CLI boundary:
- DeepSeek owns root entrypoint, CLI app lifecycle, core API client, runtime and low-level config interface.
- GLM owns user-facing command handlers/flags/help and connector adapters.
- Do not modify files under DeepSeek's runtime packages without a reviewed interface PR.

Must not own:
- apps/workflo-runner-go/ and Firecracker implementation.
- packages/workflo-policy-go/ and security/ policy implementation.
- apps/control-plane/ backend routes/DB (GPT-6).
- apps/dashboard/ (Gemini).
- canonical schemas without owner approval.

## 4. Authority and constraints

You may:
- implement commands that call existing typed interfaces;
- implement connector clients for GitHub and local repositories;
- write test profile manifests and detection logic;
- replace Python-based npm distribution with platform-specific native-binary packages;
- add installer documentation and smoke tests;
- propose API scope/permission requirements to GPT-6.

You may not:
- create a second Go CLI or a Python sidecar dependency;
- execute project setup scripts during host-side discovery;
- put GitHub tokens into argv, environment dumps, guest or receipts;
- ask for broad GitHub permissions;
- silently turn a dev runner into strict runner;
- merge source or publish release packages;
- alter user-facing command behavior without compatibility/release notes;
- introduce a marketplace, arbitrary connector plugin loader or automatic repository write access.

## 5. Work packages

### GLM-01 — Current CLI and package audit

Inspect:
- current Python CLI command/flag set and exit codes;
- CLI configuration schema and existing workflo.yaml behavior;
- packages/npm-workflo/bin/workflo.js;
- postinstall.js, build-wheels.py and vendor manifest;
- GitHub auth/device flow and existing connector code;
- current workflo-schema RunRequest/RunStatus structures;
- current installer scripts and CI workflows.

The current npm wrapper launches a package-local Python venv and requires Python >=3.11. That is the migration target, not the desired final UX.

**Acceptance:** command/flag compatibility inventory, current package dependency map, installer support table, connector API gap report.

### GLM-02 — Command tree and UX

Implement handlers against DeepSeek's CLI app/core interfaces.

Required command groups:
- init, doctor, version/help/completion;
- auth login/logout/status/whoami;
- org/workspace selection;
- connect github/disconnect/status;
- repo/project list/select;
- run with profile stages and safe dry-run;
- runs/status/cancel/logs;
- evidence/verify/inspect/explain;
- runner enrollment/status/drain/revoke client workflows;
- config get/set/validate.

For each command define:
- syntax and flags;
- required scope;
- preflight checks;
- API call(s);
- success output;
- error cases;
- JSON output schema;
- idempotency and retry behavior;
- exit code class;
- example.

Help output is part of the product contract.

**Acceptance:** golden CLI transcript tests; stable human and JSON output; invalid flag combinations fail before API submission.

### GLM-03 — Safe project detection

- Detect Python, Node, Go and Java manifests without executing any project code.
- Display detected candidates and ask for explicit profile when ambiguous.
- Discover lockfiles and toolchain hints.
- Identify frameworks only as hints until a profile is selected.
- Respect existing project config location after a source audit.
- Do not introduce a conflicting .workflo configuration path.
- Never run preinstall/postinstall hooks on the developer host during detection.

**Acceptance:** malicious repo fixtures cannot cause host-side script execution; detection output is deterministic.

### GLM-04 — Local repository connector

- Validate path and Git repository safely.
- Read current HEAD and working-tree state.
- User must choose whether to run against committed revision or explicit working-tree snapshot.
- Canonicalize file inventory and exclude unsafe/sensitive paths according to policy.
- Detect symlinks, submodules, LFS and nested repositories.
- Bound file count, total bytes, per-file size and traversal depth.
- Produce a source manifest/digest for the runner.
- Do not copy source to the control plane by default.

**Acceptance:** source snapshot tests for clean repo, uncommitted work, branch move, symlink/path escape, oversize files, submodule and secret fixtures.

### GLM-05 — GitHub client connector

- Integrate GitHub App installation workflow and device/browser authorization.
- List only repositories visible to the selected installation.
- Distinguish public/private repository and permission errors.
- Resolve selected ref to full immutable SHA before admission.
- Store only installation identity and short-lived credential references.
- Request no Contents write permission.
- PR/commit checks require Checks:write and are published by the control plane.
- Show clear status when check write is not authorized.
- Handle revoked installation, expired token and repository removed from installation.

**Acceptance:** public/private selection, no-permission, revoked app, expired token, moved branch and PR check test matrix.

### GLM-06 — Language profile registry

Profiles initially:
- Python + pytest; app profiles for FastAPI/Flask/Django where explicit.
- Node.js with npm/pnpm/Bun and approved Jest/Vitest/Playwright profile.
- Go modules with go test ./....
- Java Maven/Gradle profile.

Each profile declares:
- profile ID/version;
- supported OS/guest image digest;
- language/runtime version;
- manifest/lockfile requirements;
- dependency preparation command arrays;
- test command arrays;
- output report schema;
- default time/resource limits;
- network/dependency policy;
- known limitations.

Profile selection is not permission to run arbitrary host commands. The execution engine resolves commands inside the guest image.

**Acceptance:** every profile has a minimal passing and failing fixture; command arrays and profile digest appear in RunSpec.

### GLM-07 — Native binary package distribution

Target UX:
~~~bash
npm install -g @workflo/cli
pnpm add -g @workflo/cli
bun add -g @workflo/cli
workflo --help
~~~

Proposed implementation:
- small JS shim package;
- platform-specific optional dependency packages carrying the Go binary;
- no Python wheels/venv;
- no unverified network download from postinstall;
- npm/pnpm/Bun compatibility test;
- exact @workflo scope verified before first publish;
- maintain old @cortexstudio/workflo package only as an explicit compatibility/deprecation path if there are users.

Platform packages initially:
- darwin-arm64, darwin-x64;
- linux-x64;
- win32-x64.
Linux ARM64 and Windows ARM64 only after actual build/test runners are available.

### GLM-08 — Native installers

- macOS: signed archive; Homebrew formula/tap after release validation.
- Windows: verified ZIP/archive and optional signed MSI; Scoop/WinGet manifest after test.
- Linux: signed tarball first; .deb/.rpm when install/upgrade/uninstall matrix is stable.
- customer runner: Linux KVM-specific installer, separate from CLI client installer.

Installers must:
- validate checksum and provenance;
- install to user-owned location where possible;
- avoid root requirement for CLI client;
- support explicit version pin;
- prevent partial install;
- preserve config on upgrade;
- remove binary without deleting user receipts/config unless asked;
- support rollback.

### GLM-09 — UX and platform test

Test:
- zsh/bash/fish/PowerShell;
- spaces/unicode in paths;
- proxy and offline network;
- PATH setup;
- antivirus/SmartScreen warning path;
- package-manager script disabled path;
- package cache and reinstall;
- Windows Ctrl-C and Unix signals;
- upgrade while CLI process is active;
- broken/corrupt binary checksum;
- incorrect CPU architecture.

**Acceptance:** a clean machine can install the binary with each claimed method, run help/version and perform authenticated non-execution commands without Python.

### GLM-10 — Handoff

Deliver command reference, profile reference, connector permission table, installer matrix, package namespace record, compatibility/deprecation notes and CI evidence.

## 6. Security rules

- Never print bearer token, private key, PAT, provider key or refresh token.
- Do not place secrets in command-line arguments.
- Use OS credential store.
- Do not send source archive to control plane.
- Do not execute repository code in local project detection.
- No PR or branch write capability in initial GitHub App.
- Use short-lived installation token for source acquisition.
- No untrusted postinstall script that downloads arbitrary binary.
- Verify downloaded and packaged binary.
- No automatic fallback from GitHub private access to public/anonymous clone.
- No repo content in telemetry.

## 7. Definition of done

A developer on each claimed OS can install Workflo using npm, pnpm, Bun or native channel, run help, authenticate, connect a private GitHub repository or local project, pin an exact SHA, select a supported profile, submit a run, inspect status and verify the receipt without needing Python. Every connector/install negative case has a test.
