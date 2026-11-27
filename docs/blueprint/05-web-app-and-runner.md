# 05 — Workflo Web App, Customer Runner and Installation Experience

**Parent:** [Implementation Blueprint](00-master-implementation-plan.md)

## 1. Product surface separation

There are two web properties and one local execution component:

| Surface | Repository path | What it does |
|---|---|---|
| Public website | `website/` | Marketing, documentation, install guides, download verification, product status and links to app |
| Workflo web app | `apps/dashboard/` | Authentication, workspaces/projects, providers/settings, runner management, run creation, live status, reports and receipts |
| Workflo runner daemon | Python runner service + OS helper | Executes on customer-controlled machine/infrastructure and connects outbound to the control plane |

Do not put source execution logic in Next.js API routes. Do not expand `frontend/` in the Cortex Autopilot path. The dashboard is a product UI, not another runner.

## 2. Web-app goals

The user should be able to:

- create an account/workspace and project;
- configure provider profiles and select model/policy;
- connect one or more local or customer-managed runners;
- view platform capabilities and backend eligibility;
- select an exact branch/commit or a local runner workspace;
- request an execution with an explicit mission and test capabilities;
- observe the run timeline and cancel safely;
- inspect test/probe findings and agent actions;
- distinguish host evidence from guest/agent/model claims;
- download a report, receipt and evidence bundle;
- independently verify a receipt and understand limitations;
- install/update the CLI and runner from verified packages.

## 3. Information architecture and page specifications

### 3.1 Home / workspace overview

Show:
- active projects and recent runs;
- connected runner status and strict/development eligibility;
- failed/inconclusive runs requiring attention;
- provider profile health summary (configured/tested without showing keys);
- links to documentation and install instructions.

Do not show global vanity metrics until based on measured data. Empty workspace must have a working quick start, not fabricated sample activity unless clearly labeled as demo data.

### 3.2 Projects

Fields:
- project name/slug;
- repository provider and URL (optional; repo content remains customer controlled);
- default source policy;
- default checks and app configuration;
- default inference profile and privacy mode;
- default execution profile;
- assigned runners;
- organization-level policies inherited and locked.

The project page shows exact policy version/digest. If a policy is changed, future runs use the new version; existing runs retain old policy snapshot.

### 3.3 Runners

Each runner card/detail contains:

- display name and stable runner ID;
- OS, OS build, architecture;
- Workflo runner/CLI version;
- backend adapter, hypervisor and runtime version;
- guest image version/digest;
- capacity (CPU/memory/disk headroom) as coarse metadata;
- status: `online`, `busy`, `offline`, `upgrade_required`, `strict_ready`, `development_only`, `ineligible`;
- last heartbeat and current attempt IDs;
- security gate version + evidence link.

Do not show local host pathnames, user names, IPs or detailed fingerprinting beyond what is required for the operator. Runner capabilities are visible only to users authorized for that workspace.

Runner enrollment UI:
1. Generate short-lived pairing code.
2. Present CLI command `workflo runner connect --code ...`.
3. Runner authenticates and signs a challenge using local private key.
4. Pairing code expires after use/short TTL.
5. User can rename runner, set project scope and revoke.

### 3.4 Run creation

Form controls:

- source selection: repository commit or connected runner local workspace;
- exact ref/commit preview (local source snapshot requires CLI/runner handshake);
- execution profile: strict/development/remote strict;
- selected runner with backend eligibility;
- test suites and declared checks;
- app start/health config;
- agent mission;
- agent capability toggles (only those allowed by policy);
- provider profile, mode, data policy and model identity;
- wall-clock, CPU, memory/disk and action budgets, clamped to policy ceiling;
- network policy and any requested destinations;
- retention/export policy.

Before submission, show a resolved summary:

- source identity/snapshot digest;
- runtime/backend and assurance label;
- provider/model/data policy;
- enabled capabilities;
- commands and network rules;
- estimated limits, not speculative cost if price not known;
- warning if local model is unreachable or cloud metadata mode cannot inspect source.

### 3.5 Run timeline

Use server-sent events (SSE) or an authenticated WebSocket only if bidirectional control is actually required. SSE is sufficient for the prototype's one-way lifecycle feed. Cancellation is a separate authenticated API call.

Events should be stable and append-only:

- run admitted/rejected;
- runner claimed/lease renewed;
- backend preflight result;
- VM provisioned/guest ready;
- source snapshot verified;
- check started/completed;
- app start/health status;
- agent tool requested/allowed/denied/completed;
- inference request/response metadata (no prompt);
- evidence item finalized;
- shutdown requested/forced termination;
- teardown check result;
- receipt finalized/verification verdict.

The UI must show the source of each event and not convert unknown state to “running” or “passed”.

### 3.6 Run detail and report

Tabs/sections:

1. **Overview:** execution, QA and trust outcomes independently.
2. **Tests:** suites, counts, skipped/failed/inconclusive reasons, test evidence identifiers.
3. **API:** route IDs, method/status/latency, assertion results.
4. **Browser:** actions, origins, assertion outcome, optional screenshot preview only when customer policy permits.
5. **Agent:** ordered tool calls, permission decision, result code, duration, denied operations.
6. **Logs:** filtered/sanitized log summary; raw logs downloadable only if retention policy permits and user has access.
7. **Findings:** observed issue, evidence links, severity/priority (if computed), model hypothesis visibly separate.
8. **Repair suggestion:** patch preview and digest; download only, no apply button.
9. **Trust:** runtime identity, isolation profile, evidence manifest, teardown checks, signer identity, receipt version and verifier result.
10. **Artifacts:** signed receipt, public key/certificate, evidence index and exported report.

### 3.7 Provider Settings

For each profile display:

- provider, endpoint class (cloud/local), model ID;
- base URL (redacted if it contains a credential or sensitive path);
- model features supported: structured output, tool plan, streaming, context estimate;
- privacy mode and disabled capabilities;
- key status: `not configured`, `stored`, `revoked`, `test failed` (never key characters);
- last health test and latency;
- scope: personal/workspace/project;
- default profile.

When endpoint class is Cloud, the Settings form must lock `local_source_context=false`. The UI can never override the server's policy.

### 3.8 Installation and downloads

The website should present:

- Linux install command/package;
- macOS signed/notarized package + CLI install path;
- Windows signed installer/package + requirements checker;
- `pipx` expert install path;
- CLI-only vs runner install distinction;
- runtime backend support matrix;
- checksums/signatures and release manifest;
- link to Workflo app and docs.

Install page must state that CLI works cross-platform but strict local execution requires the appropriate hypervisor backend and certified build. Windows Home and unsupported macOS/CPU configurations may use a customer-managed remote strict runner.

## 4. Runner daemon design

### 4.1 Process model

Start with one Python daemon service, reusing CLI/worker packages. Native helper process only for hypervisor-specific API calls on macOS/Windows. Do not introduce multiple microservices on the desktop.

Runner functions:

- enrol and refresh identity;
- open outbound authenticated control channel;
- receive signed assignments and lease token;
- verify project/runner scope;
- resolve local source selection when explicitly delegated;
- dispatch to backend adapter;
- upload bounded evidence and event chunks;
- heartbeat, track active runs and clean after crash/restart;
- install signed updates and report version;
- manage local provider adapters and credential vault.

### 4.2 Network channel

- Runner establishes outbound TLS connection to the control plane; no public inbound server port.
- Use a short-lived access token or mutually authenticated identity, with rotation.
- Each assignment is separately signed and bound to runner ID, project ID, attempt, expiry and nonce.
- Heartbeats/commands have sequence numbers and replay protection.
- Use message-size and rate limits.
- Cancel request is a typed message; runner acknowledges and reports actual termination state.
- If control plane is disconnected, runner may finish the current run if assignment allows offline completion and deadline has not expired; no new assignment accepted.
- Run result may be stored locally in encrypted spool until connection restores; TTL/size cap and no raw source in the spool.

### 4.3 Source hand-off

Two options:

**Option A — CLI/runner local path:** CLI asks runner to snapshot an authorized path. Source stays local and is materialized into a VM; only source metadata and digest are sent to dashboard.

**Option B — Git repository:** runner fetches the exact commit using a short-lived Git credential in a trusted preflight component; credential is removed before VM creation. Do not let guest access the Git provider or use host token mounts.

Do not implement browser-to-runner raw filesystem upload in prototype. A browser page should not use arbitrary localhost WebSockets/HTTP as a general file access bridge.

## 5. Control-plane API and event streaming

Suggested route families (exact route version must align with existing `/v1` compatibility):

| Endpoint family | Purpose |
|---|---|
| `POST /api/v2/runners/enroll` | Complete enrolment challenge |
| `POST /api/v2/runners/heartbeat` | Capacity/version/active-attempt heartbeat |
| `GET /api/v2/runners/assignments/next` or stream | Claim/receive signed assignment |
| `POST /api/v2/runners/assignments/{attempt}/events` | Upload event batch |
| `POST /api/v2/runners/assignments/{attempt}/evidence` | Upload bounded evidence artifact/chunk |
| `POST /api/v2/runners/assignments/{attempt}/complete` | Submit terminal status and receipt reference |
| `POST /api/v2/runs` | Admit a run |
| `GET /api/v2/runs/{id}` | View run metadata and outcomes |
| `GET /api/v2/runs/{id}/events` | SSE timeline |
| `POST /api/v2/runs/{id}/cancel` | Request cancellation |
| `GET /api/v2/runs/{id}/report` | Retrieve report data |
| `GET /api/v2/runs/{id}/artifacts` | List receipt/evidence bundle metadata |
| `POST /api/v2/providers/profiles` | Create provider profile |
| `PUT /api/v2/providers/profiles/{id}/secret` | Replace encrypted secret |
| `POST /api/v2/providers/profiles/{id}/test` | Test profile |

Never accept arbitrary runner callback URLs, provider base URLs or artifact URLs without allowlist/SSRF controls.

## 6. Persistence model

Use existing PostgreSQL and migrations where feasible. Do not add Redis solely because it is popular; use it only if the existing dispatch/event implementation requires it and its state semantics are well defined.

Core tables/entities:

- workspaces/organizations, memberships and roles;
- projects and project policy versions;
- runners and runner public-key identity;
- runner capabilities/attestation snapshots;
- provider profiles and encrypted credential references;
- runs, attempts, assignments and leases;
- lifecycle events (append-only); event id, sequence and digest;
- evidence manifest/index references and content object storage metadata;
- receipts, signer identities and verification summaries;
- artifact retention/deletion records;
- audit events for credentials, policy, runner enrolment and revocation.

All tenant-owned rows require RLS. The control-plane service must connect as a non-owner, non-superuser role without `BYPASSRLS`, and tests must assert `FORCE ROW LEVEL SECURITY` on protected tables. Keep admin/migration role separate.

## 7. Real-time UI implementation

- Use TanStack Query for API cache and request lifecycle.
- Use SSE for run event stream and reconnect with `Last-Event-ID` or a cursor.
- Events must be idempotent and de-duplicated by stable event ID/sequence.
- UI query state is rehydrated from API if stream disconnects; no event-only state loss.
- Use bounded polling for runner heartbeat if stream unavailable.
- Do not show optimistic success for cancel; show “cancellation requested” until termination result is confirmed.
- Do not send hidden telemetry containing prompt/log/source content.

## 8. Security and privacy on the web tier

- Use secure, HttpOnly, SameSite cookies or OAuth device flow; avoid long-lived tokens in localStorage.
- CSRF protection for state-changing requests.
- CSP, strict origin policy and safe markdown rendering.
- No unsafe HTML in model explanations or logs.
- Escape file names and test IDs before rendering.
- Limit screenshot and evidence download permissions.
- Time-limited signed download URLs with tenant/run authorization and expiry.
- Provider keys written once to server secret endpoint; never returned to browser.
- Do not store raw prompts, source bodies or API keys in browser logs or analytics.
- All dashboard queries filter by workspace/project with RLS as second layer.

## 9. Web UI implementation phases

1. Rebrand current dashboard shell to Workflo and remove Tenant Shield copy.
2. Build authenticated shell, workspace selector and API error/loading/empty states.
3. Implement provider profiles and secret replacement UI; use mock provider adapter in storybook/tests only.
4. Implement runner pairing/status/capability view.
5. Implement run submission against a real CLI-created/controlled RunSpec.
6. Implement SSE timeline and cancellation.
7. Implement run detail, report, receipt/evidence download and verifier result.
8. Run Playwright E2E against real local control plane + test runner.
9. Add install/docs links to the public website.

## 10. Web acceptance tests

- User A cannot read/list User B's projects/runners/providers/runs/artifacts.
- Changing workspace invalidates cached previous-tenant data.
- Provider secret never appears in GET responses, DOM, localStorage, error text or telemetry.
- Browser cannot submit `local_source_context` for a cloud profile.
- Browser cannot request a run on an ineligible runner in strict mode.
- `cancel` shows pending until runner confirms termination.
- SSE reconnect doesn't duplicate events or lose state.
- Empty run list is not rendered as fabricated successful activity.
- All statuses have clear execution, QA and trust dimensions.
- Report links bind to correct receipt/evidence digest.
- Download URL expires and cannot be reused across tenant.
- Dashboard-created run and CLI-created run produce the same contract format.