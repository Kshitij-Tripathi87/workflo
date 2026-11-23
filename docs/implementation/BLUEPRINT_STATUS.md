# Workflo Implementation Blueprint — Task Status

**Audit date:** 2026-11-22 · **Repository base:** `e864c42` (branch `arena/7f41312d-workflo`)
**Sources studied:** the complete blueprint package (`00-master-implementation-plan.md` …
`09-product-market-strategy.md`, manifest SHA-256 verified, all links resolving) plus the
repository itself. Every status below carries file-level evidence gathered at the audit
commit. The review of the package itself is merged at
[`BLUEPRINT_ENGINEERING_REVIEW.md`](../../BLUEPRINT_ENGINEERING_REVIEW.md) (PR #26).

**Question answered: are all blueprint tasks done? — No.**
Of the 43 backlog items in `07-backlog-and-milestones.md`:

| Status | Count |
|---|---:|
| Fully done (acceptance met) | **0** |
| Partial (foundation exists, acceptance unmet) | **17** |
| Blocked (owner ratification decision) | **1** (WF-0001) |
| Not started | **25** (incl. 4 Phase 2 items whose *acceptance* is additionally gated on a real KVM host) |
| Done outside the WF backlog (dashboard rebrand, this change) | 1 |

The repository is a solid foundation — contracts, worker slice, dev receipts, agent tooling
exist — but Phase 0 is incomplete, Phase 2 has barely started (and is KVM-gated), and
Phases 5 and 7 have not begun.

---

## Phase 0 — Baseline, contract ratification, test inventory

| ID | Task | Status | Evidence @ base | Next action |
|---|---|---|---|---|
| WF-0001 | Ratify canonical contract authority (ADR-0015) | **Blocked (owner)** | `docs/adr/ADR-0015…` still `Proposed`; ADR-0016…0021 also `Proposed` (see review F1) | Owner ratifies ADR-0015 **and** 0016–0021 together |
| WF-0002 | Establish current baseline | **Partial** | `docs/reconciliation/BASELINE_2026-11-11.md` exists (stale); CI green on `e864c42` (see Baseline below); `docs/implementation/BASELINE.md` not yet the canonical home | Publish fresh per-suite baseline on this status doc's cadence; resolve baseline-doc home |
| WF-0003 | Reconcile receipt v5 vs legacy | **Partial** | v5 writer+verifier real: `packages/sandbox-isolation/src/sandbox_isolation/dev_receipt.py` (`ReceiptV5Payload`/`SignedReceiptV5`), CLI verify `apps/workflo-cli/src/workflo_cli/main.py:1776-1788`; `workflo run` + control plane still write legacy `SignedReceipt` (`main.py:1215`, `dispatch_service.py:191`); `CURRENT_RECEIPT_VERSION = 4` (`sandbox.py:33`) | Golden receipts for v1–v4 + v5; decide v5-issued-yet question; move new writers to v5 only |
| WF-0004 | Inference egress inventory and freeze | **Not started** | Direct cloud path still default: `llm_config.py:48` `mode: str = "direct"`; `sandbox-runtime/planner.py:117-149` direct `base_url`; unused `workflo_worker/model/cloud_llm.py` (flagged at `PHASE_0_WORKFLO_TRUST.md:42-43`); no inventory doc | Produce egress map; disable direct cloud; add bypass regression tests |
| WF-0005 | Runtime ownership and strict/dev labels | **Not started** | Zero hits for `strict_ready` / `development_only` / `DEVELOPMENT_ONLY` across `apps/ worker/ packages/`; no `--profile` flag on `workflo run` | Label every runtime profile in CLI/report/receipt; add no-fallback tests |

## Phase 1 — Deterministic vertical slice

| ID | Task | Status | Evidence @ base | Next action |
|---|---|---|---|---|
| WF-0101 | Canonical RunSpec + resolved plan | **Partial** | `RunSpecV1` exists (`workflo_schema/contracts`, exported in `__init__.py:68`); no `ResolvedRunPlan`/policy-digest layer anywhere in schema | Add resolved-plan + deterministic digest; cross-language golden vectors |
| WF-0102 | Source snapshot builder | **Not started** | No `source inspect`, no snapshot/archive builder in `apps/workflo-cli` (only `run_state.json` reads) | Build deterministic manifest snapshot with path/symlink controls |
| WF-0103 | Complete guest execution flow | **Partial** | PR #22 slice: capability delivery, fixed workload (`workload.py`, digest `90ade0e9…`), evidence manifest, 8 teardown probes, honest KVM skips (`worker/tests/integration/test_kvm_boot.py`); **no** repo materialization, declared checks, app lifecycle or agent in guest | Feed `RunSpecV1` + snapshot into guest; `python-fastapi-good/broken` fixtures |
| WF-0104 | Host evidence collector + finalizer | **Partial** | Slice evidence manifest + digest frame (`guest_supervisor.build_evidence_manifest`); dev finalizer `dev_receipt.py`; no host event spool/completeness rules for real runs | Completeness validation; tamper/swap tests already specced in 06 §7 |
| WF-0105 | CLI end-to-end command | **Partial** | `run-dev` vertical works end-to-end (policy → execution → teardown → v5 receipt → offline verify; exercised by `linux-gate.yml`); not wired to canonical RunSpec or fixtures | Unify `run`/`run-dev` on RunSpec; report Execution/QA/Trust separately |
| WF-0106 | Prototype demo fixture suite | **Not started** | No `tests/fixtures/prototype-lab` or `examples/workflo-lab`; `examples/demo` is unrelated | Create the 12 fixtures from 06 §5 with pinned digests |

## Phase 2 — Linux Firecracker strict backend (Gate B)

Four items not started, one partial; **every acceptance in this phase requires a real KVM
host** (this sandbox has no `/dev/kvm`, firecracker, nft or vsock — tests skip honestly
per ADR-0022).

| ID | Task | Status | Evidence @ base |
|---|---|---|---|
| WF-0201 | Real per-attempt cgroup scope | **Not started (P0 blocker)** | `manager.py:288-290`: "jailer runs without `--cgroup`/`--netns`"; teardown checks inspect path **absence**, not enforcement |
| WF-0202 | Enforced egress backend | **Not started (P0 blocker)** | `network.py` has `apply_nftables`/`remove_nftables` (runner-injectable) but no per-run namespace/proxy; sandbox has no `nft` |
| WF-0203 | Jailer/seccomp/filesystem admission | **Not started** | `build_jailer_argv` + `--chroot-base-dir` exist (PR #22); no seccomp profile, no image signing |
| WF-0204 | Teardown inventory + crash recovery | **Partial** | All 8 `TeardownCheckId`s have real probes (PR #22) but 4 of them verify absence of unmanaged paths; no manager-restart recovery |
| WF-0205 | Gate B adversarial harness | **Not started** | `worker/tests/integration/test_kvm_boot.py` = 3 honest skips; no SEC-001…032 harness |

## Phase 3 — Providers and privacy-enforced inference

| ID | Task | Status | Evidence @ base | Next action |
|---|---|---|---|---|
| WF-0301 | Provider/profile schemas | **Not started** | No `ProviderProfile` / `endpoint_class` in `workflo-schema` | Add profile + endpoint-class + data-policy models |
| WF-0302 | Adapter contract + local providers | **Partial** | Legacy llama.cpp/GGUF path + generic direct endpoint exist (`llm_config.py`, `planner.py`); no `ProviderAdapter` protocol, no Ollama/LM Studio adapters | Introduce adapter contract; migrate legacy paths |
| WF-0303 | Cloud gateway adapters | **Not started** | Gateway endpoint exists (`apps/control-plane/app/api/v1/inference.py`) but no provider registry/registry-backed adapters | OpenAI/Anthropic/Gemini/OpenRouter behind gateway |
| WF-0304 | Positive allowlist payload schema | **Not started** | Free-form `RuntimeObservation.detail` still in request path (per 03 §12.4) | Replace with typed observation classes; canary tests |
| WF-0305 | Credential vault + config migration | **Partial** | OS credential store + 0600 file fallback in `llm_config.py`; no BYOK control-plane vault; migration unimplemented | Envelope-encrypted tenant vault; config v2 migration |
| WF-0306 | Provider test UI/CLI | **Not started** | No `workflo provider …` commands registered in `main.py` | CLI group + dashboard Settings page |

## Phase 4 — Full agent and evidence workflow

| ID | Task | Status | Evidence @ base |
|---|---|---|---|
| WF-0401 | Tool schema + capability registry | **Partial** | `ToolGateway`/`agent_tools.py` exist in `apps/worker-engine`; cloud/local capability split and per-tool Pydantic schemas incomplete |
| WF-0402 | Deterministic test/app/API tools | **Partial** | Test runner + API capability layers exist (master §0.2 "partial capability layer") |
| WF-0403 | Playwright browser tool | **Partial** | Browser capability present in worker-engine; no pinned guest browser image/quarantine per 02 §7.3 |
| WF-0404 | Log summarizer + failure analyzer | **Partial** | Log/analysis capabilities exist; no typed-only cloud payload enforcement |
| WF-0405 | Agent orchestrator / planner loop | **Partial** | `agent_runner.py` loop exists with budgets; plan-validation hardening per 06 §6 pending |
| WF-0406 | Advisory patch generator | **Not started** | No `workflo suggest-fix`; ADR-0021 (patch protocol) still `Proposed` |
| WF-0407 | Agent evaluation suite | **Not started** | No labeled evaluation set |

## Phase 5 — Cross-platform backends and packaging

**WF-0501 … WF-0505: not started.** No Swift Virtualization helper, no C# Hyper-V helper,
no `SandboxBackend` protocol, no signed installers anywhere in the tree (searched
`*.swift`, `*hyperv*`, `*virtualization*` — zero hits).

## Phase 6 — Dashboard and runner orchestration

| ID | Task | Status | Evidence @ base |
|---|---|---|---|
| WF-0601 | Runner enrolment + heartbeat | **Not started** | No `runner connect`/heartbeat/enrol code in CLI |
| WF-0602 | Run dispatch integration | **Partial foundation** | Durable dispatch/outbox exists (`dispatch_service.py`); no signed assignment → runner claim loop |
| WF-0603 | Dashboard shell + identity | **Partial → polished this change** | Was a Tenant Shield placeholder; rebranded to Workflo here (see below). Auth/workspace shell still to build |
| WF-0604 | Provider settings + runner UI | **Not started** | Dashboard = 3 pages (home only routable); no Settings/Runners pages |
| WF-0605 | Run creation, timeline, reports | **Not started** | No SSE/timeline/report pages |
| WF-0606 | Website installation + docs | **Not started** | `website/` is Workflo-branded marketing; no OS install matrix/signature docs yet |

## Phase 7 — Release acceptance

**WF-0701, WF-0702: not started.** No SBOM/provenance release bundle, no fresh-machine
acceptance record.

## Phase 8 — CI integration

| ID | Task | Status | Evidence @ base |
|---|---|---|---|
| WF-0801 | GitHub Actions consumes same contracts | **Partial** | `linux-gate.yml` already runs `workflo verify --receipt … --evidence …` with a tamper negative control over golden-run bundles — the *verifier* is shared with CI today; no user-facing Action or RunSpec wrapper yet |

---

## Completed in this change (application polish)

Blueprint task **05-web-app-and-runner §9.1 step 1 — "Rebrand current dashboard shell to
Workflo and remove Tenant Shield copy"** — **DONE**, verified with lint + build:

| File | Change |
|---|---|
| `apps/dashboard/app/layout.tsx` | Metadata title → `Workflo`; description → execution-assurance copy |
| `apps/dashboard/app/page.tsx` | Heading/tagline rebranded; nav cards realigned to the blueprint IA (Projects / Runs / Settings); dead `/compliance` (SOC 2) card removed |
| `apps/dashboard/lib/api.ts` | Control-plane comment rebranded |
| `apps/dashboard/tailwind.config.ts` | Theme palette key `shield` → `workflo` (values unchanged) |

Verification: `npm ci` + `npm run lint` (`eslint --max-warnings=0`) + `npm run build`
(`next build`, 4 static pages) — all green locally on this branch.
Left untouched deliberately: `cortex_auth` imports and the published
`@cortexstudio/workflo` npm package name (live dependencies, not branding).

## Baseline (WF-0002 progress)

- **CI on base `e864c42` (2026-11-22): all checks green** — Worker Engine CI `test`,
  Workflo QA, CI (backend, contracts, nextjs ×3, workspace, docker-build),
  Architecture Review `validate`/`validate-phase2`, `linux-sandbox-gate` (8m6s),
  Workflo QA plan checks.
- **Last full local worker run:** 132 passed, 3 skipped (2026-11-21, PR #22 code —
  `worker/` unchanged since; the 3 skips are the honest KVM integrations).
- **Still missing for WF-0002 acceptance:** a committed per-suite baseline on the
  canonical home (this doc vs `docs/reconciliation/BASELINE_*.md` — pick one), and the
  "false-green / ignored-error" workflow review.

## Known blockers (unchanged)

1. **Owner decisions:** ADR-0015…0021 ratification (WF-0001, review F1).
2. **Hardware:** Gate B (Phase 2) needs a real KVM host — never mockable per ADR-0022.
3. **Privacy freeze:** direct-inference paths must close before any provider expansion
   (WF-0004) — flagged in the merged review as the top Phase 0 code task.

*Update this file when a work item's status changes; each entry should keep its evidence
pointer current.*
