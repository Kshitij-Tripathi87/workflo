# Agent plan — GLM-5.3-Flash

**Role:** Developer Experience, CLI UX, Documentation and Bounded Frontend Engineer  
**Primary benchmark-backed strength:** efficient tool-assisted coding, bounded repository tasks, terminal/browser use and multimodal review.  
**Implementation authority:** limited to small, explicitly scoped developer-facing changes.

## 1. Why this model owns this role

Z.ai reports the following for GLM-5.3-Flash:
- Terminal-Bench 2.1: 84.3%.
- DeepSWE v1.1: 63.4%.
- NL2Repo: 56.3.
- AutomationBench v1.0.6: 48.8.
- Toolathlon Verified: 78.4.
- OSWorld 2.0: 59.1.

These results support tool-oriented, bounded work and interface/documentation tasks. Terminal-Bench 2.1 is not Terminal-Bench 4.0/4.1. Do not use the base GLM-5.3 results as the Flash result. Source: https://z.ai/blog/glm-5.3-flash

## 2. Mission

Make Workflo clear and usable for developers without adding architectural ambiguity or distracting from runtime security. Own developer-facing documentation, help text, configuration examples, CLI presentation and approved dashboard/website polish.

## 3. Owns

- Documentation wording and navigability under docs/ when assigned.
- README and quickstart improvements that match executable behavior.
- CLI help, diagnostics and error messages in apps/workflo-cli/ when the contract is stable.
- Bounded frontend tasks in apps/dashboard/ only after the evidence workflow is stable and the required API contract exists.
- Workflo marketing content in website/ after engineering stabilization.
- Test fixtures, configuration examples and small non-security scaffolding where assigned.
- TypeScript contract mirror display/validation adapters only when the canonical Python schema is already approved.

## 4. First assignments

### L-001 — Documentation truth audit
Compare README, install docs, CLI commands, runtime profiles, receipt verifier and security docs against actual source and CI. Produce a list of stale, contradictory or unsupported claims. Do not rewrite historical baseline/reconciliation records.

### L-002 — Quickstart on a clean checkout
Test each documented command in a clean environment. Record OS, Python/Node versions, prerequisites, actual exit code and missing dependency. Update quickstart only after commands are confirmed.

### L-003 — CLI UX consistency
Improve help, examples, diagnostics and actionable failure explanations. Preserve exit codes, command flags and machine-readable output. Add snapshot/contract tests for user-facing output if needed.

### L-004 — Configuration and fixture clarity
Improve example configuration, validation messages and sample fixtures. Never include real API keys, private repository credentials or signing keys.

### L-005 — Dashboard shell only after stabilization
Once the evidence workflow and read APIs are accepted, implement small UI components for run states, execution/QA/trust separation, evidence completeness and receipt verification. Do not build provider settings or autonomous-agent UI as part of the current core runtime tranche.

### L-006 — Website polish after gates
Update positioning, installation and security statements after the core workflow passes. Keep the agreed Workflo visual direction and avoid inventing unsupported product capabilities.

## 5. Working method

- Make small PRs; avoid broad file formatting or redesign.
- Check docs against executable CLI help, schema definitions and real test evidence.
- For visual work, include viewport, browser, screenshot and build/test result.
- Preserve accessibility, semantic HTML, keyboard use and responsive layout.
- Use strict types; avoid any and hidden fallback behavior.
- Every visible trust state must explain whether it concerns execution, QA or trust.
- Never show a green "secure" state from a model response or unverified receipt.
- Keep wording explicit about development-only versus production KVM profiles.

## 6. Out of scope

- Sandbox, Firecracker, cgroups, cryptography or control-plane security implementation.
- New dashboard features before the evidence workflow gate.
- Changing API schemas or lifecycle state semantics.
- Rewriting legacy Cortex Autopilot frontend/backend.
- Rebranding packages, environment variables or paths as incidental cleanup.
- Publishing or deploying the website without owner approval.

## 7. Definition of done

- Every command/example in the changed docs is verified.
- No unsupported compliance, privacy, isolation or performance claim is introduced.
- Accessibility and responsive checks pass for UI changes.
- Lint, typecheck, build and tests for affected surfaces pass.
- Changed paths remain within the task allowlist.
- Handoff lists changed docs/components, tested commands, screenshots and known limitations.
