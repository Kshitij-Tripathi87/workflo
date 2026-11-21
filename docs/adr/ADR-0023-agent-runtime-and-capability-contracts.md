# ADR-0023 — Registered agent profiles, bounded plans, and capability grants

**Status:** Proposed · 2026-11-21  
**Scope:** Agentic execution Phase A

## Context

Workflo already has a durable run/attempt/outbox path, canonical execution-policy and evidence contracts, an initial Firecracker worker-host model, and a bounded in-guest agent runner. The existing agent runner and tool gateway are useful foundations, but there is no canonical versioned contract tying an approved agent runtime, profile, task DAG, tool registry, capability grant, model identity, and execution result to one tenant-scoped sandbox attempt.

Ad hoc task JSON, environment flags, and tool allowlists are insufficient for dispatching agents to customer-controlled workers. Agents must not be able to widen their own tools, filesystem access, network access, model use, or budgets. The TypeScript UI also needs a validated mirror without becoming a second contract authority.

## Decision

1. Canonical agentic contracts are authored in the Python package workflo-schema as immutable Pydantic v2 models. JSON Schema exports are generated from those models. The TypeScript package mirrors these wire shapes; it does not define authority or policy.
2. Agent runtime profiles are immutable and digest-addressed. A tenant registry binds profiles and typed tool definitions. A profile is usable only when it is present in the admitted registry snapshot and its digest is not revoked.
3. The initial profile registry is Workflo-owned. Customer-supplied runtime bundles and third-party plugins are not admitted by this decision.
4. A mission pins organization, project, run, exact source commit, execution-policy digest, registry digest, selected profile references, idempotency key, and hard budgets.
5. A plan is a bounded DAG of typed tasks. The contract rejects duplicate IDs, missing dependencies, cycles, role/profile mismatches, unselected or revoked profiles, unregistered tools, and budgets exceeding the selected profile or mission grant.
6. Each capability grant is short-lived and scoped to one organization/project/run/attempt/sandbox/task/profile. It carries exact tool IDs, named filesystem roots, a network-policy digest, a budget, a nonce, and a signature over its canonical digest. No arbitrary host path or generic host RPC is a capability.
7. Source snapshots are read-only. Artifact output is write-only in v1. Network-write tools require explicit approval. The v1 model-access rule reserves local inference to the Explorer role; no other role receives model artifacts.
8. Agent action events contain typed action state, request/result digests, and bounded observable summaries only. They do not contain chain-of-thought. Guest events are observations and cannot drive product lifecycle transitions.
9. A new SandboxAssignmentV2 extends the existing worker assignment without changing V1. V2 binds the profile registry digest, exact selected profile references, compiled plan digest, tool registry digest, capability-grant-set digest, and model manifest/artifact digests to the existing run/attempt/sandbox, policy, guest image, resource, network, and signature binding.
10. The first supported production execution remains one mission supervisor with sequential specialist stages. Parallelism is contract-bounded but defaults to one; multi-agent concurrency requires later scheduler and quota acceptance.

## Consequences

- The existing V1 assignment and legacy API/receipt formats remain compatible.
- Admission must construct and sign V2 only after validating the mission, registry, compiled plan, policy, and capability grants.
- Workers must verify the signature and digest of the entire V2 assignment before provisioning. The next phase will connect this contract to the real Firecracker/vsock path.
- The guest Tool Gateway must enforce each grant independently of model prompts and profile metadata.
- Registry revocation and policy changes affect future attempts; they cannot mutate an already admitted assignment.
- A passing contract suite is not proof of microVM isolation, live model acceptance, or production readiness. Those remain separate gates.

## Alternatives considered

- Reuse unversioned agent task JSON: rejected because it does not bind task identity, tenant scope, profile, tools, budget, and runtime artifacts to the worker assignment.
- Allow agents to register or spawn arbitrary tools: rejected because agent output is untrusted and cannot grant authority.
- Put all fields directly into RunSpec: rejected because a run request and a compiled attempt plan have different lifecycle and trust boundaries.
- Replace assignment V1 in place: rejected because existing development and compatibility consumers must remain valid during migration.
