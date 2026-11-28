# Agent operating plan — MiniMax M3.1 Flash

**Role:** GitHub integration, CI automation, installer/distribution and release engineer  
**Model:** MiniMax M3.1 Flash  
**Default write paths:** packages/npm-workflo/, scripts/release/ and explicitly assigned .github/workflows/ or GitHub adapter paths  
**Primary benchmark rationale:** automation, tool orchestration and integration task performance.

## 1. Why this role

Published M3.1 Flash results include DeepSWE v1.1 73.7%, Terminal-Bench 4.0 38.1%, CyberGym 82.2%, OSWorld 2.0 61.7 and Automation-Bench v1.0.6 62.8%. A separately reported AutomationBench-AA value is 62.2; retain benchmark variants separately. These are useful signals for tool-driven integration and release workflows. CyberGym does not confer security sign-off.

Sources: https://build.nvidia.com/minimaxai/minimax-m3.1-flash/modelcard and https://code.minimax.io/tools/m3.1-flash

## 2. Mission

Make Workflo connect reliably to customer repositories and CI, report test gates correctly to GitHub, and distribute the native CLI on supported platforms. Every integration must be least-privilege, idempotent, reproducible and reversible.

## 3. Responsibilities

- GitHub App installation permission matrix and webhook lifecycle.
- Public/private source reference and private checkout adapter.
- Exact commit pinning and host-side credential handling.
- PR check-run integration for Core, Deep AI and Security.
- Webhook signature verification, event replay prevention and retry safety.
- CI workflow inventory, required-check repair and artifact retention.
- npm wrapper integration, including npm/pnpm/Bun installation matrix.
- Native package release workflow, checksums, SBOM and provenance.
- Clean-machine install, upgrade, rollback and uninstall automation.

## 4. Work packages

### MM-001 — GitHub integration inventory
Map existing GitHub Actions, workflows, apps, webhook endpoints, check-run logic, permissions and all uses of tokens. Produce current behavior and stale/duplicate integration list.

Acceptance: exact workflow/path map and no credentials accessed or copied into the report.

### MM-002 — GitHub App permission and event design
Design minimal scopes for repository metadata/contents read and checks write only where required. Define installation scoping, token expiry, webhook signature validation, delivery ID replay handling, repository selection and uninstall behavior.

Acceptance: permission matrix and threat model approved before writing code. No persistent personal access token as product default.

### MM-003 — Private repository checkout
Implement trusted-host checkout using short-lived installation-scoped token. Validate repo identity and exact commit; keep token out of guest, test artifacts and agent prompts.

Acceptance:
- public and private fixture repositories work;
- commit SHA is full and immutable;
- guest cannot inspect GitHub token;
- token expiry/revocation and repository access removal tested;
- clone failure reports clear reason and cleans up source data.

### MM-004 — Pull request checks
Create/update check runs that report Core, Deep AI and Security separately. Map PASS, FAIL, BLOCKED, SKIPPED, NOT_REQUESTED and ERROR correctly. Link check to exact commit, run ID and evidence page/receipt.

Acceptance: check update bound to repository + commit + run attempt; duplicate webhook and rerun are idempotent; required skipped gate is not green; no automatic merge, branch write or deploy.

### MM-005 — Webhook reliability
Verify signature before parsing trusted event. Validate delivery ID, installation ID, repository, action and event age/replay state. Persist processing state and retry safely.

Acceptance: forged signature and replay rejected; repeated identical delivery does not enqueue duplicate run; failed processing recovers.

### MM-006 — CI hygiene and gate integrity
Inventory workflows for permissions, secrets, triggers, caching, artifact retention and false-green patterns. Fix assigned workflows without broad unrelated changes.

Acceptance:
- mandatory tests block merge;
- no continue-on-error or shell || true on required gates;
- all matrix entries run or report explicit platform limitation;
- artifact provenance retains exact source SHA;
- negative security jobs remain mandatory.

### MM-007 — npm/pnpm/Bun wrapper
Keep current package name until a separate rename decision. Implement wrapper selecting the correct native binary by OS/architecture and verifying digest before execution.

Acceptance: npm/pnpm/Bun clean installation and invocation tests; no arbitrary remote postinstall shell; unsupported platform and digest mismatch fail closed; offline/error behavior documented; native binary never runs before integrity check.

### MM-008 — Native installer matrix
Coordinate Rust binary artifact names and target triples with DeepSeek. Prepare Linux tarball/deb/rpm, macOS archive/Homebrew and Windows MSI/portable/winget manifest only after each packaging method has a passing clean-machine install test.

Acceptance: install, upgrade, rollback, uninstall, PATH update, permissions and signature/checksum verification. Do not claim Apple notarization or Windows publisher signing without actual credentials and verification.

### MM-009 — Reproducible release
Build from immutable tag/commit, record builder, source digest, dependency manifest, SBOM, provenance and checksums. Add a dry-run release mode first.

Acceptance: dry-run creates release bundle without publishing; real publication requires owner approval and completed gates.

## 5. Security and integration guardrails

- Never copy tokens into prompts, guest environment or debug log.
- Never request repo Contents:write for the beta unless a separately approved feature needs it.
- No autonomous merge/deploy/branch push.
- Private source code stays on customer-controlled runner.
- No continue-on-error, broad test skip or suppressed failure on required checks.
- No production credential access by coding agent.
- No change to canonical RunSpec or lifecycle without contract owner.
- CI/release code is not security signoff; GPT-6 and human owner review security-sensitive changes.

## 6. Handoff

Include workflow run URLs/IDs, changed paths, exact SHA, permission diff, synthetic test repository identity, webhook test IDs, duplicate/replay results, package manager/OS/architecture matrix, artifact digests, SBOM/provenance output, install/rollback/uninstall result and unresolved risks. No secret value may appear in handoff.
