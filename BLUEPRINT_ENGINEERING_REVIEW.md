# Engineering Review — Workflo Implementation Blueprint

**Reviewed package:** 9 core documents + product/market strategy + README + MANIFEST
(`00-master-implementation-plan.md` … `09-product-market-strategy.md`)
**Repository snapshot reviewed against:** `main` @ `5e82478` (= this branch's base; the blueprint's declared review base)
**Review date:** 2026-11-21
**Reviewer:** coding agent (repo-grounded fact-check of every load-bearing claim)

---

## 1. Verdict

**APPROVED WITH CHANGES.** The blueprint is unusually well grounded in the actual
repository: of ~30 load-bearing factual claims checked against code, ~27 verified
exactly, 0 claims materially wrong, and the remaining items are scope/consistency
gaps rather than factual errors. The security posture (fail-closed, no
strict→development fallback, positive-allowlist privacy, independent teardown
measurement) is consistent with ADR-0022 and the repo's own reconciliation docs.

**Must fix before landing** (3 items, all documentation-level):

| # | Severity | Finding |
|---|---|---|
| F1 | Should-fix | ADR ratification scope too narrow — ADR-0016…0021 are also `Proposed` and load-bearing; doc 08 drafts parallel decisions instead of referencing them |
| F2 | Should-fix | Master §2.4 illustrative lifecycle graph diverges substantially from the canonical enum in `contracts/lifecycle.py` |
| F3 | Should-fix | Doc 04's proposed `.workflo/workflo.yaml` collides with two config paths the CLI already uses today |

**Nits** (F4–F6) and confirmations below. None of the findings block starting Phase 0.

---

## 2. Package integrity (independently re-validated)

| Check | Result |
|---|---|
| MANIFEST.json SHA-256 for all 11 listed files | ✅ all match (bytes + hash) |
| Corrected master `00-…` vs first-handoff master | ✅ differs only in the 14 flattened link paths; content otherwise identical |
| Package-local Markdown links (`00`–`09`, README) | ✅ 0 broken |
| Stale files still present in the folder | ⚠️ `workflo_implementation_plan.md` and `workflo_product_market_strategy.md` (first handoff) are **not** in the manifest; the stale master has **14 broken links** to the old `security/`, `ai/`, `product/` folder layout. Remove them from any ZIP/review copy so reviewers cannot open the superseded version. |

---

## 3. Claims verified against the repository

### 3.1 Confirmed accurate (selection; file:line evidence)

| Claim (document) | Evidence |
|---|---|
| ADR-0015 is `Proposed (pending project-owner ratification)` (master §3.3, 08) | `docs/adr/ADR-0015…` status line |
| Receipt v5 = DSSE-style envelope (master §3.3, 08 DRAFT-06) | `contracts/receipt.py:1` — "Receipt v5: validated payload inside a DSSE-style envelope (ADR-0018)" |
| **run-dev already has a v5 receipt flow** (08 SP-05) | `packages/sandbox-isolation/dev_receipt.py` builds `ReceiptV5Payload`/`SignedReceiptV5`; CLI `main.py:1776-1788` verifies via `verify_dev_receipt` |
| Manager does **not** create cgroups/netns; checks inspect absence (02 §8.3, 08 risk 1) | `worker/src/workflo_worker_host/manager.py:288-290` — "jailer runs without `--cgroup`/`--netns`" |
| Direct-inference privacy bypass exists (03 §6.1, 08 risk 3) | `llm_config.py:48` default `mode: str = "direct"`; `sandbox-runtime/planner.py:117-149` direct `base_url` calls; `PHASE_0_WORKFLO_TRUST.md:42` flags exactly this |
| Standalone direct cloud client still in tree (03 §12.1) | `PHASE_0…md:43` — `workflo_worker/model/cloud_llm.py` "do not wire into release execution" |
| Dashboard branded Tenant Shield (master §0.2, 08 risk 5) | `apps/dashboard/app/layout.tsx:5`, `app/page.tsx:4` |
| CLI command inventory: init/doctor/run/run-dev/status/verify/inspect/explain/keygen/update/security-gate (master §0.2, 04) | `workflo_cli/main.py` — all present (`keygen` :1803, `update` :1927, `security_gate` registered) |
| User config at `~/.config/workflo/config.json` under `llm` (04 §5) | `llm_config.py:3,25` |
| P4 per-package pytest split + schema-export commands (06 §3) | all 7 test dirs exist; `export_schemas.py` + `requirements-schema-export.txt` exist; `@workflo/contracts` / `@workflo/events` package names match |
| `P4_ACCEPTANCE.md` dated 2026-10-11 (08 risk 7) | `P4_ACCEPTANCE.md:3` |
| Landlock/hardening gaps are real repo themes (market §3.2) | referenced in `PRODUCT_BOUNDARIES.md`, `CODE_REVIEW.md`, `doctor.py`, `security_gate.py` |
| Legacy receipt versions 1–v4 with `AgentActivity` at v3 (08 DRAFT-06, market §3.1) | `sandbox.py:32` `SUPPORTED_RECEIPT_VERSIONS = (1,2,3,4)`, `CURRENT_RECEIPT_VERSION = 4`; `AgentActivity` at `sandbox.py:338` |
| Eight teardown checks (02 §8.3) | matches `default_teardown_probes` (8 `TeardownCheckId`s) shipped in PR #22 |
| Guest slice = fixed workload only, not full workload (master §0.2) | accurate — `worker/…/workload.py` pinned fixture; repo materialization/tests/agent remain open (WF-0103) |
| ADR-0022 accepted; microVM boundary | `ADR-0022` status `Accepted` |

### 3.2 Targets phrased as targets (not errors)

- **01 §3.3** lists `api/v1/projects.py`, `runners.py`, `providers.py` as "Required modules" — these routers do not exist yet (`v1/` has runs, inference, auth, orgs, artifacts, audit, keys…). Correctly phrased as required work; just don't misread as current state.
- **04 §2** command table is explicitly "target UX, not a command list to implement all at once" — correctly hedged.

---

## 4. Findings requiring changes

### F1 — ADR ratification scope is too narrow (Should-fix)

**Where:** `08-open-decisions-and-ADRs.md` §2/§5; master Phase 0; `07` WF-0001.

**Issue:** The ratification checklist covers ADR-0015 plus eight new `ADR-DRAFT-01…08`.
But the repository contains **seven** `Proposed` ADRs dated 2026-11-11, all of which
the blueprint's designs depend on:

| Existing ADR (Proposed) | Blueprint overlap |
|---|---|
| ADR-0016 canonical JSON & evidence chain | 01 §6 evidence pipeline |
| ADR-0017 run lifecycle and outcomes | master §2.4 lifecycle |
| ADR-0018 receipt v5 | 08 **DRAFT-06** essentially restates it |
| ADR-0019 policy admission | 02 §10 admission matrix |
| ADR-0020 event/finding/evidence contracts | 08 **DRAFT-07** overlaps it |
| ADR-0021 patch protocol | 02 §7.4 / 04 §3.6 repair suggestions |

Only ADR-0022 is `Accepted`. Risk: two parallel decision records (existing ADR vs
new DRAFT) for the same decisions will drift, exactly the "contract drift" ADR-0015
was written to prevent.

**Recommendation:**
1. Extend WF-0001 and the §5 checklist to **ratify-or-supersede ADR-0016…0021** alongside ADR-0015.
2. Rewrite DRAFT-01/06/07 as explicit references to ADR-0015/0018/0020 (keeping only genuinely new drafts: backend strategy, cloud privacy, local broker, runner topology, labels).
3. One-line note in master Phase 0: "ratification covers the whole proposed ADR family (0015–0021)".

### F2 — Master §2.4 illustrative lifecycle graph diverges from the canonical enum (Should-fix)

**Where:** master §2.4.

**Issue:** The illustrative graph uses `REQUESTED → VALIDATING → ADMITTED → QUEUED →
PROVISIONING → RUNNING → COLLECTING_EVIDENCE → TERMINATING → VERIFYING_TEARDOWN →
FINALIZING → COMPLETED | FAILED | CANCELLED | REJECTED`. The actual canonical enum
(`packages/workflo-schema/src/workflo_schema/contracts/lifecycle.py:17-34`) is:

```
CREATED, ADMITTED, PROVISIONING, SOURCE_ACQUISITION, PREPARING, EXECUTING,
EVALUATING, COLLECTING_EVIDENCE, TEARDOWN, VERIFYING_TEARDOWN, SIGNING,
COMPLETED, INFRASTRUCTURE_FAILED, EXECUTION_FAILED, TEARDOWN_FAILED,
ATTESTATION_FAILED, REJECTED, CANCEL_REQUESTED
```

`REQUESTED/VALIDATING/QUEUED/RUNNING/TERMINATING/FINALIZING/FAILED/CANCELLED`
do not exist. The master does self-flag "use actual canonical enum names", but the
picture is what gets copied into tickets and UI.

**Bonus the blueprint currently misses:** the canonical failure states map cleanly
onto the master's own three-outcome model —
`INFRASTRUCTURE_FAILED` = Execution, `EXECUTION_FAILED` = QA,
`TEARDOWN_FAILED`/`ATTESTATION_FAILED` = Trust. Calling that out would strengthen §0.

**Recommendation:** replace the illustrative graph with the actual enum (or a
diagram generated from it) and add the outcome-mapping note.

### F3 — Project config path collision (Should-fix)

**Where:** `04-cli-and-configuration.md` §3.1, §5.

**Issue:** Doc 04 has init generate `.workflo/workflo.yaml`. Today the repo has
**three** config-path concepts:

1. `.workflo/config.yaml` — what doctor tells the user to create via `workflo init` (`doctor.py:146`);
2. `.workflo/policies.yaml` — written by init (`main.py:477`);
3. root-level `workflo.yaml` / `workflo.yml` — already read by `workflo run --config` and `_read_cli_workflo_yaml` (`main.py:352`).

Doc 04 §5's migration list covers only the user-level `~/.config/workflo/config.json`
→ provider-profile migration. The project-level consolidation (three files → one)
is unspecified, and the name `workflo.yaml` already means something different at
repo root.

**Recommendation:** add a project-config migration item (map `config.yaml` +
`policies.yaml` + root `workflo.yaml` semantics, with a deprecation window), and
state explicitly whether init writes `.workflo/workflo.yaml` or the repo-root file.

### F4 — Doc 08 §1 stale decision row (Nit)

The row *"Primary stack | Review repo; retain TypeScript CLI + Python runtime as
preference, but choose based on code"* contradicts its own Consequence cell and
every other document (Python CLI canonical; TypeScript = web + validated mirror).
Rewrite the Selection cell to record the resolved outcome.

### F5 — Market strategy: stale/ambiguous status references (Nit)

- §3.1's "**Phase 5** reported complete / **Phase 6** specification / **Phase 7** run
  contract" uses numbering from older project-context notes; neither the repo
  (`AGENTIC_EXECUTION_PHASE_PLAN_V1.md` uses Phase A–F) nor this blueprint
  (Phase 0–8) matches it. Readers will collide with blueprint Phases 5–7. Label the
  source or renumber.
- §3.1 headlines "Receipt version 3"; the repo's `CURRENT_RECEIPT_VERSION` is **4**
  (v3 does include `AgentActivity`, so the claim is literally true but stale).
  Suggested wording: "legacy v1–v4 (current v4); canonical DSSE v5".
- §3 statuses are correctly framed as *reported, not audited* — keep that framing.

### F6 — Package hygiene (Nit)

Remove the two superseded first-handoff files from the package folder/ZIP (see §2).

---

## 5. What the blueprint got right (worth stating explicitly)

These are the claims most reviewers would get wrong, and all verified true:

1. **The real Gate B blockers are correctly prioritized.** WF-0201 (cgroups) and
   WF-0202 (egress) are marked `P0 security blocker`, matching `manager.py`'s own
   comment that jailer runs without `--cgroup`/`--netns` — i.e., today's eight
   teardown checks mostly prove *absence of unmanaged paths*, not enforcement.
2. **The direct-inference bypass is real and correctly scoped** — three separate
   paths (`llm_config` direct mode, `sandbox-runtime/planner.py`, unused
   `cloud_llm.py`), with the repo's own PHASE_0 doc flagging them.
3. **"No strict→development fallback"** matches ADR-0022 and the CLI honesty rules
   the worker suite already enforces.
4. **The receipt-version rule** ("if v5 bytes were ever issued, evolve to v6, never
   mutate") matches how `sandbox.py` documents version handling.
5. **Phase ordering is dependency-correct.** WF-0001…0005 → WF-0101…0106 → Gate B
   matches the repo's actual state: contracts exist but ADRs are unratified, the
   guest slice (PR #22) is fixed-workload, and no v5 production receipt has been
   issued yet — so now is exactly the right moment for Phase 0.
6. **Test-fragmentation warning (06 §3) is accurate** — the repo genuinely requires
   per-package pytest invocations, and the commands listed all exist.

---

## 6. Recommendation and next steps

1. **Land the package** under e.g. `docs/blueprint/` after applying F1–F3 (small,
   surgical edits) and F4–F6 (trivial). The README's status note ("proposed
   specifications, not proof of implementation") should stay.
2. **Start Phase 0 immediately after landing** — its five tickets are all
   documentation/inventory work that needs no KVM host:
   - WF-0001 ratify ADR-0015 **(+ ADR-0016…0021 per F1)** — needs the project owner;
   - WF-0002 produce `docs/implementation/BASELINE.md` (note: existing baselines
     live in `docs/reconciliation/BASELINE_2026-11-11.md` — decide the home);
   - WF-0003 receipt v5 writer/verifier inventory (already partially mapped in §3.1
     above: writer = `sandbox_isolation/dev_receipt.py`, verifier = CLI `main.py`,
     legacy writer = `SignedReceipt` call sites in CLI + control plane);
   - WF-0004 inference-egress inventory + regression tests;
   - WF-0005 runtime labeling.
3. **Gate B evidence remains a separate KVM-host activity** — the blueprint is
   correct that no amount of in-sandbox work substitutes for it (ADR-0022).

*Review scope note: this review verified repository-grounded claims, internal
consistency and package integrity. It did not re-audit the external market data
sources cited in `09-product-market-strategy.md`.*
