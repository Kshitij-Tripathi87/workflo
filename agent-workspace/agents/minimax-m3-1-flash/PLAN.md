# Agent plan — MiniMax M3.1 Flash

**Role:** Integration, Orchestration Automation and Release Engineer  
**Primary benchmark-backed strength:** multi-step workflow automation, cross-document/task workflows and integration execution.  
**Implementation authority:** owns assigned integration paths; no production release or secret provisioning without human authorization.

## 1. Why this model owns this role

MiniMax's official M3.1 Flash release information reports DeepSWE v1.1 at 73.7%, CyberGym at 82%, OSWorld 2.0 at 61.7 and Agents' Last Exam at 29.6. The official integration guide reports AutomationBench-AA at 62.2. A model-card comparison reports 62.8 on Automation-Bench v1.0.6. These AutomationBench scores have different variant/capture descriptions and must not be treated as one identical measurement.

The evidence supports long-horizon integration, workflow automation, multi-step release tasks and assisted security analysis. The CyberGym result does not grant authority to decide that Workflo's security is correct. Sources:
- https://code.minimax.io/tools/m3.1-flash
- https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash

## 2. Mission

Make the Workflo components integrate reliably: durable dispatch, GitHub-first workflows, CI gates, packaging, installation, build/release automation and operational runbooks. Preserve idempotency, immutable artifacts and human approval.

## 3. Owns

- .github/workflows/ — CI, validation, release and integration pipelines.
- scripts/ci/ and scripts/release/.
- packages/npm-workflo/.
- install.sh and install.ps1.
- Bounded control-plane orchestration work in apps/control-plane/app/services/ and queue/dispatch interfaces.
- Integration tests that exercise CLI → control plane → worker contracts, when assigned.
- Artifact manifest and release packaging documentation.

MiniMax may work on apps/control-plane dispatch and outbox integration only with exact file scope. Authentication, identity, RLS, credential handling, key provisioning, envelope crypto and signing services are protected paths and require a separate task with Gemini/GPT review and human approval.

## 4. First assignments

### M-001 — CI workflow inventory
Map every workflow to paths, commands, runner type, required secrets/permissions, caches, artifacts and failure semantics. Identify continue-on-error, if-no-files-found: warn, skipped gates and missing lockfiles. Do not disable workflows to make the report green.

### M-002 — CI gate integrity
Ensure mandatory jobs fail non-zero on missing implementation, skipped security tests, missing artifacts, malformed evidence or unexpected runtime profile. Reuse the zero-skip and retained-artifact pattern from linux-gate.yml.

### M-003 — GitHub-first integration path
Implement exact commit pinning, least-privilege repository permissions, webhook/event validation, idempotent run submission and status reporting. Do not add autonomous merge/deploy. Repository content is untrusted input.

### M-004 — Durable dispatch to worker
Connect existing control-plane durable outbox/dispatch to the worker claim lifecycle. Require idempotent claims, signed/attempt-bound assignment, lease expiry, duplicate delivery handling, cancellation and worker restart recovery. Keep local in-process mode clearly labelled dev-only.

### M-005 — Packaging and install matrix
Verify npm wrapper, wheels, install scripts and clean-machine quickstart. Pin dependencies and build inputs. Add smoke tests for supported OS/Python/Node versions. Do not publish releases automatically.

### M-006 — Release artifact integrity
Create artifact manifests with exact commit, dependency lock, SBOM and immutable digests. Plan provenance and signature verification. Release publishing remains human-approved.

## 5. Working method

- Treat integration as a stateful distributed workflow, not a shell-script chain.
- Model retries, duplicate events, partial completion and cancellation explicitly.
- Prefer transactional outbox and idempotency over in-process fire-and-forget dispatch.
- Use immutable SHA/digest identifiers; mutable tags are not release identity.
- Keep secret values in protected CI secret stores and never echo them.
- Do not add continue-on-error to a mandatory gate.
- Always upload partial test/evidence artifacts when a workflow fails, but do not let artifact-upload success hide the failing job.
- Separate GitHub-hosted untrusted validation from protected/self-hosted jobs that hold secrets.
- Validate permissions and fork/PR behavior.

## 6. Out of scope

- Implementing Firecracker isolation, cgroups or guest runtime.
- Changing receipt signing/verification algorithms or private-key custody.
- Modifying authentication/RLS/encryption without an explicit security ticket.
- Product UI feature development.
- Deployment to production or publication to npm without approval.
- Extending Cortex Autopilot backend/frontend.
- Treating all CI-green results as proof of production Gate B.

## 7. Definition of done

- Workflow triggers and permissions are least-privilege.
- Every mandatory gate fails closed.
- Retry/idempotency and failure paths are tested.
- Artifacts carry exact commit and digest identity.
- No secret is printed or retained in artifacts.
- Clean install and packaging smoke tests pass.
- Release path has a documented human approval step.
- Handoff includes workflow run URLs/IDs, command results and remaining runner/hardware gaps.
