# Five-agent operating protocol

## 1. Shared workspace model

All five agents share one Workflo repository, one architecture, one task board and one checked-in agent-workspace directory. They must not write concurrently into the same mutable checkout.

The coordinator creates one task branch and one Git worktree per implementation task. Worktrees are sibling directories of the main checkout inside the user's common project workspace. They are never nested inside tracked source directories. Every task records its base SHA and the expected branch head.

One task has one implementation owner. A reviewer is read-only unless a separate test/fix task explicitly grants write permission. The main branch is an integration target, not an agent scratchpad.

Recommended branch names:
- agent/gemini/WF2-002-repository-map
- agent/deepseek/WF2-101-rust-cli
- agent/minimax/WF2-501-github-checks
- agent/gpt6/WF2-602-workspace-contract
- agent/glm/WF2-105-cli-docs

## 2. Agent permissions and capabilities

All agents may:
- Read the source/docs/test output required for their assigned task.
- Create architecture notes, test plans and implementation changes inside an explicit path allowlist.
- Run non-destructive formatting, lint, unit tests, integration tests and local builds.
- Use mock services and synthetic repositories for integration tests, clearly labeling them as mocks.
- Report uncertainty, blockers, risk and missing hardware as first-class task outcomes.

No agent may:
- Read, expose or write production secrets, private signing keys, customer credentials or live customer data.
- Push to main, merge a pull request, force-push, change branch protections or delete a branch.
- Deploy, publish a release, rotate keys, alter billing or create paid infrastructure.
- Change accepted architecture decisions or treat Proposed ADRs as accepted.
- Move, rename or delete source directories during workspace restructuring.
- Expand sandbox privileges, host mounts, network access, cgroup permissions or resource quotas without a specific approved security ticket.
- Disable mandatory tests, remove negative tests, soften assertions, add broad skips or mark required gates continue-on-error.
- Send source text, diffs, code snippets, private repo archives, secrets, environment values or raw logs to hosted models.
- Approve their own code, test evidence, release artifact or security claim.

## 3. Mandatory task lifecycle

1. Coordinator selects an item from coordination/TASK_BOARD.md.
2. A task contract records owner, read-only reviewer, base SHA, allowed paths, forbidden paths, dependencies, acceptance criteria, commands and rollback.
3. Agent reads AGENTS.md, the workspace guide, PRODUCT_BOUNDARIES.md, related ADRs and actual source entry points.
4. Agent runs and records a baseline before editing.
5. Agent implements only the requested vertical slice; no opportunistic cleanup.
6. Agent runs targeted tests and the affected package's required tests/build/security checks.
7. Agent produces a handoff with changed-file inventory, command/exit-code transcript, test counts, artifacts, compatibility impact and unresolved risks.
8. Reviewer inspects the diff and independently reproduces the claimed tests in clean CI or an isolated checkout.
9. Human owner decides whether the change is accepted and merged.

Status transition: READY → IN_PROGRESS → IMPLEMENTED_UNVERIFIED → VERIFIED → ACCEPTED. A failed test, unavailable dependency, absent KVM hardware or unclear requirement moves the task to BLOCKED; it does not justify weakening the gate.

## 4. Ownership and conflict resolution

- The path-ownership matrix is the default write boundary. An agent stops rather than edits an unowned path.
- Contract files have a single writer. Other agents consume the tagged/generated contract or golden vectors.
- MiniMax owns CI workflow edits by default. GPT-6 may propose checks in a review document, but does not concurrently edit those workflow files.
- DeepSeek owns new Rust CLI files after owner-approved language decision.
- GPT-6 owns API contract files; control-plane implementation is a later explicitly scoped tranche.
- Gemini is read-only over product source except a separate ticket; architecture ownership is not permission for code changes.
- GLM owns documentation and UX proposal paths, not the CLI implementation.
- Any task touching worker/, sandbox-isolation, cryptographic signing, policy admission, cgroups, jailer, egress, host/guest protocol or teardown needs a narrow security task, a second independent reviewer and human owner acceptance.

If two tasks need the same path, serialize them. Do not solve contention by merging both changes into one uncontrolled working tree.

## 5. Data handling and inference restrictions

Data classes:
- Public documentation and synthetic fixtures: may be used by any assigned coding agent.
- Internal source code: may only be sent to a model provider when that provider's deployment/privacy arrangement is approved and the owner explicitly permits it.
- Customer repository content: remains customer-controlled; not included in hosted prompts.
- Secrets/credentials/private keys: never included in prompts, issues, logs or test artifacts.
- Hosted prompt payload: typed, schema-allowlisted metadata only, default disabled, per-workspace and per-run explicit consent.

BYOK keys belong to the customer's control plane/secret store. Coding agents never receive the real key. Tests use synthetic short-lived credentials. Consent is not permission to send source.

## 6. Test and environment permissions

- Default development environment has no production credential and no broad network egress.
- Any external dependency download must use pinned versions and documented allowlists or prebuilt caches.
- Test repos are synthetic or explicitly owner-approved fixtures.
- A mocked KVM, fake Firecracker process or namespace run can validate code paths but never counts as Gate B proof.
- A host without /dev/kvm, Firecracker, jailer or required network primitives must record KVM tests as blocked/skipped with reason; never convert them to pass.
- Tests must not run against customer production repositories or services without an explicit task scope and approval.

## 7. Handoff evidence schema

Every handoff must include:
- Task ID, agent/model ID, branch and exact base/head SHA.
- Changed files and the intent of each file.
- Commands executed with working directory and exit code.
- Test counts: pass, fail, skip, xfail and not-run.
- OS, architecture, toolchain versions and relevant feature flags.
- KVM hardware availability and whether any execution was mocked.
- Build/test artifact paths and hashes for receipts, evidence bundles and packages.
- Source/credential/privacy impact and whether hosted prompts were used.
- API, CLI, package, schema and runtime compatibility impact.
- Rollback or migration plan.
- Open risks and precise owner decision requested.

“Tests passed” is not sufficient. “Tests were not run” is not verification. Never hide a skipped required test in a green summary.

## 8. Safe parallel work

Parallelizable at the beginning:
- Gemini repository architecture map.
- GPT-6 read-only API/tenant inventory and draft contract proposal.
- DeepSeek CLI parity inventory and Rust proof only after a ticket allows it.
- MiniMax GitHub/packaging permission design and CI inventory.
- GLM documentation truth audit and UX wireframes.

Parallelizable after interface freeze:
- DeepSeek CLI/protocol client.
- MiniMax GitHub and distribution adapters on non-overlapping paths.
- GPT-6 contract tests/API work on its own paths.
- GLM examples/docs while dashboard code remains deferred.

Not parallelizable:
- Two writers to the same contract/schema.
- Multiple agents editing the same runner/security path.
- Dashboard implementation while API/lifecycle/tenant contracts are unsettled.
- Parallel source moves or sweeping refactors.

## 9. Stop-work triggers

Immediately stop the task and report BLOCKED if:
- A path outside the allowlist becomes necessary.
- The code would expose secrets, source or customer data to an unauthorized system.
- A task conflicts with an accepted ADR or unresolved ADR dependency.
- A change would permit a dev runtime to act as a strict production fallback.
- A security gate needs to be skipped or softened to pass.
- A test's result cannot be explained or reproduced.
- The implementation requires paid Workflo-owned infrastructure contrary to the approved zero-budget design.
