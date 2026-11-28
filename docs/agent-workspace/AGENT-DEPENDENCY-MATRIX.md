# Five-Agent Dependency and Handoff Matrix

**Authority:** subordinate to accepted ADRs, canonical contracts and `docs/agent-workspace/AGENT-OPERATING-MODEL.md`  
**Planning baseline:** main at `c07b93775b6b745edec92acfe1e4051ded14d0b1`  
**Purpose:** make cross-agent dependencies explicit so five agents can move quickly without parallel architectures or overlapping writes.

## 1. Workstream map

| Agent | Workstream | Primary source paths | Must not own |
|---|---|---|---|
| DeepSeek V4.1 Flash-1017 | Go CLI core, customer runner and execution host migration | `apps/workflo-cli-go/`, `apps/workflo-runner-go/`, `packages/workflo-protocol-go/` | FastAPI business logic, CLI command handlers/connectors, policy engine, dashboard |
| GLM-5.3 Flash | CLI commands/UX, GitHub/local connectors, language profiles and binary distribution | `apps/workflo-cli-go/internal/commands/`, `internal/connectors/`, `profiles/`, `packages/npm-workflo/`, `scripts/release/install/` | runner/firecracker, backend/RLS, policy/security, dashboard |
| MiniMax M3.1 Flash | Policy engine, threat model, adversarial/security/privacy test suite | `packages/workflo-policy-go/`, `security/`, `tests/security/`, `tests/privacy/`, `tests/chaos/security/` | runner host implementation, API business logic, CLI command UX, dashboard |
| Gemini 4 Hydrogen | Dashboard IA/design, frontend after M1, browser/accessibility QA | `apps/dashboard/`, dashboard tests, `docs/agent-workspace/ui/` | backend/DB/RLS, CLI/runner, canonical schema, security policy |
| GPT-6 Luna | FastAPI control plane, OpenAPI, identity/team model, DB/RLS and backend reliability | `apps/control-plane/`, migrations/RLS, API contracts and backend tests | CLI/runner implementation, policy engine, dashboard frontend |

All paths are defaults only; each task still receives an exact per-ticket file allowlist.

## 2. Critical interface handoff matrix

| Interface | Producer | Consumer(s) | Required artifact before parallel implementation | Acceptance |
|---|---|---|---|---|
| Canonical RunSpec/policy/evidence/receipt | Human owner + canonical schema owner; GPT-6 contract proposal | DeepSeek, GLM, MiniMax, Gemini | Versioned schema, examples, compatibility policy, golden vectors | Python and Go/TS validation match; no unapproved lifecycle drift |
| M1 API / runner protocol | GPT-6 | DeepSeek, GLM | OpenAPI 3.1, auth principal matrix, request/response examples, errors, idempotency/lease rules | Generated client compiles; contract tests and negative authorization tests pass |
| CLI core interface | DeepSeek | GLM | Go interfaces, typed config/runtime/API client, error model, output primitives | Command package builds and tests without editing core files; golden CLI transcript |
| Source connector interface | DeepSeek (snapshot primitives) + GPT-6 (grant API) | GLM; runner implementation by DeepSeek | Provider interface, exact source identity contract, source manifest/digest and credential custody | Public/private/local fixture; branch movement, token expiry, path and symlink tests |
| Policy evaluator | MiniMax | DeepSeek runner and GPT-6 admission | Pure Go policy package API, schema version, deterministic decisions/reason codes | Same input same output, deny tests, no side effects, golden schema parity |
| Host/guest protocol | DeepSeek | MiniMax adversarial suite; existing Python guest/worker; GPT-6 runner API | Typed operation registry, protocol version, attempt binding, sequence/nonce/size limits | Wrong attempt/replay/unknown/oversize messages rejected |
| Language profiles | GLM | DeepSeek guest/runner; GPT-6 API | Profile ID/version/image digest, argv, test report schema, resource/network budgets | Passing/failing/timeout fixtures per language and image digest recorded |
| Package binary metadata | DeepSeek | GLM | Target triples, artifact names, version/build metadata, SHA-256 and provenance | Correct binary resolved for each claimed OS/arch; digest mismatch rejected |
| Three gate state semantics | GPT-6 proposal; owner-approved canonical contract | GLM CLI, Gemini UI, MiniMax tests | Independent Core/Deep/Security status schema and aggregation table | Required skipped/blocked gate cannot be green |
| Privacy/consent schema | GPT-6 API contract; MiniMax policy | DeepSeek gateway/runner and GLM settings | Typed metadata allowlist, prohibited classes, consent states and audit model | Actual serialized outbound payload contains only allowed metadata |
| Dashboard API view models | GPT-6 | Gemini | Approved OpenAPI, pagination, error, auth and membership contracts | UI uses generated types; no invented enum/field |
| Browser-visible UX copy | GLM command vocabulary + GPT-6 API semantics | Gemini | State/error terminology and CLI/API parity reference | No UI/CLI mismatch; no false trust/security language |

## 3. Required handoff package by producer

### GPT-6 → DeepSeek (API and runner contract)
- OpenAPI version and contract commit SHA;
- request/response schemas for admission, claim, heartbeat, event, completion/failure and status;
- principal types and authorization scope;
- idempotency key scope and conflicting-body behavior;
- assignment signature, expiry, nonce and fencing token semantics;
- error envelope and retryable codes;
- test server or contract fixture package;
- exact compatibility promises for legacy V1 APIs.

DeepSeek must not implement the client against prose alone. No code crosses the interface boundary before schema/examples are frozen for that task.

### DeepSeek → GLM (CLI command host)
- exported Go interfaces and package import paths;
- config load/validation contract;
- API methods and typed errors;
- output renderer and JSON schemas;
- cancellation/context semantics;
- source inspection/snapshot interface;
- target OS/architecture and binary build metadata.

GLM must not edit DeepSeek-owned core files. Missing method requires an interface issue/PR, not duplicate client or runtime.

### GLM → DeepSeek (source connector and profile)
- connector ID and repository identity;
- short-lived grant reference (never token bytes);
- resolved full commit SHA;
- source selection mode: committed revision or explicitly supported working tree;
- source manifest and digest interface;
- profile ID/version, guest image digest, command argv, readiness and report schema.

DeepSeek decides host-side materialization and guest delivery. GLM owns provider-specific selection UX and profile manifests.

### MiniMax → DeepSeek (policy/security)
- deterministic policy input/output types;
- operation capability registry and denial reason enum;
- resource/network/filesystem/source rules;
- attack fixture IDs and expected evidence;
- test hooks and KVM requirements.

DeepSeek must implement the approved policy integration. MiniMax independently runs the suite and reports failures. Neither agent can mark its own portion accepted.

### GPT-6 → Gemini (dashboard APIs)
- generated OpenAPI client and type version;
- auth/session and active workspace semantics;
- role/permission matrix;
- list/detail/timeline/evidence response models;
- exact enum and error semantics;
- cursor pagination and rate/retry behavior;
- endpoint implementation status.

Gemini may design static synthetic prototypes earlier but cannot wire feature screens to unapproved/unstable APIs.

## 4. Critical path and concurrency map

### Parallel before M1
- DeepSeek: read-only Go CLI/runner baseline and module design; implement only approved skeleton/interface tasks.
- GLM: command specification, existing CLI/package audit, connector interface proposals, synthetic detection fixtures.
- MiniMax: threat/data-flow map, deterministic policy proposal and adversarial fixtures.
- GPT-6: route/auth/RLS/outbox audit and M1 OpenAPI/runner contract.
- Gemini: dashboard route audit, user journeys, design system and synthetic prototypes only.

### Serialized dependencies
1. GPT-6 publishes M1 API and runner contract; human owner approves.
2. DeepSeek implements client/runner protocol against contract.
3. GLM command handlers/connectors integrate against DeepSeek API and GPT-6 endpoint shapes.
4. MiniMax policy package/interface is agreed and integrated; negative tests stay independent.
5. Real KVM M1 path completes, including offline receipt verification.
6. GPT-6 completes team membership/RLS and multi-user admission/recovery tests for broader beta.
7. Gemini substantial dashboard implementation begins after M1 and stable API/tenant gates.

### Do not parallelize
- same file or shared contract writes;
- Go runner and Python host replacement in same production path;
- schema/lifecycle and producer/consumer implementation before contract freeze;
- dashboard implementation against guessed APIs;
- policy implementation and policy acceptance by the same reviewer;
- M1 real KVM tests with mocks used as acceptance evidence.

## 5. Shared-file reservation protocol

Any edit to these shared files must be reserved in a task:
- canonical `packages/workflo-schema/` types;
- receipt and trust verifier semantics;
- lifecycle/outcome enums;
- policy and capability schema;
- runner assignment and guest/host protocol;
- OpenAPI source and generated bindings;
- auth/RBAC/RLS;
- network/cgroup/jailer defaults;
- Go module/workspace root;
- npm package name/version and release workflow.

Reservation record must include: task ID, owner, reviewer, path list, base SHA, expected branch, start/end condition and consumer notification. No second agent writes the same reserved path until it is released and integrated.

## 6. Escalation and conflict resolution

When contracts disagree:
1. stop implementation at the boundary;
2. capture both expected shapes and exact source references;
3. identify compatibility and security impact;
4. ask the named contract producer for a versioned change;
5. obtain owner approval if canonical/ADR semantics change;
6. update golden fixtures;
7. resume from an updated base SHA.

Never resolve conflict by accepting whichever model's code compiles. The owner, accepted ADR and canonical contract take precedence.

## 7. Integration gate checklist

A cross-agent integration is READY for review only when:
- producer and consumer agree on a versioned interface;
- changed files obey exclusive ownership;
- examples/golden fixtures validate;
- positive and negative behavior covered;
- retry/idempotency/cancellation/restart semantics defined;
- data classes and credential custody documented;
- platform/hardware test class recorded (mock/dev/real KVM);
- handoff includes exact SHA and commands;
- independent reviewer is assigned;
- unresolved risks are explicit.
