# Engineering task contract and implementation handoff

Every non-trivial task assigned to one of the five models must use this contract. Agents do not receive broad repository write access through a vague prompt. A task must have one owner, one reviewer, one immutable base, a specific path allowlist and executable acceptance criteria.

## 1. Mandatory task definition

    task_id: WF2-XXX
    title: Action-oriented, observable outcome
    status: READY
    priority: P0 | P1 | P2 | P3

    ownership:
      agent_name: Gemini | DeepSeek | MiniMax | GPT-6 Luna | GLM
      exact_model_id: exact model identifier and version
      implementation_owner: one agent only
      reviewer: a different agent
      human_approver: project owner

    source:
      repository: Kshitij-Tripathi87/workflo
      base_sha: immutable full commit SHA
      branch: task-specific branch
      worktree: isolated sibling path
      baseline_run_id: test/build run or explicit "not available"

    context:
      product_boundary: Workflo Trust MVP
      governing_docs: exact ADR/spec/status file list
      current_behavior: observed code behavior with source references
      prior_attempts: related commits/PRs and unresolved findings

    objective:
      required_outcome: verifiable observable behavior
      user_impact: user problem solved
      non_goals: explicit exclusions

    paths:
      allowed:
        - exact/path/file-or-directory
      forbidden:
        - exact/path/file-or-directory

    interfaces:
      public_contracts: affected CLI/API/schema/protocol
      compatibility: behavior that must not change
      migration: versioned migration or none
      deprecation: removal condition and rollback

    invariants:
      security: exact trust boundaries preserved
      privacy: permitted/prohibited data classes
      tenancy: resource ownership and authorization
      reliability: idempotency, retries, recovery and limits
      performance: measured target or "not yet baselined"

    implementation:
      steps:
        - inspect current implementation and tests
        - state a minimal design and files to change
        - implement only the approved slice
        - run required positive and negative tests
        - record evidence and handoff

    acceptance:
      functional: observable expected behavior
      negative: prohibited behaviors that must fail closed
      regression: compatibility that must remain
      security: trust boundary and required proof
      operational: restart, retry, rollback, install or recovery proof

    test_plan:
      unit: exact modules/commands
      integration: exact modules/commands
      security: exact negative tests
      system: exact end-to-end checks
      platform: OS/architecture matrix
      unavailable: explicit reason and impact

    handoff:
      report: agent-workspace/agents/<model>/handoffs/<task-id>.md
      artifacts: logs, reports, hashes and test results
      allowed_status: IMPLEMENTED_UNVERIFIED | BLOCKED

## 2. Rules for task design

- Objective describes observable behavior, not merely “refactor”, “improve” or “make robust”.
- Allowed paths are specific enough to prevent accidental repo-wide refactoring.
- Acceptance is executable or independently inspectable.
- Security-relevant changes require positive and negative tests.
- Every task has exact base SHA, branch and clean worktree.
- Cross-component changes require an interface contract and dependency owner.
- New dependencies require reason, exact version, license, maintenance status and security review.
- Do not make an ADR decision in implementation code. Proposed decisions require an ADR and owner ratification.
- No ticket can be marked passed by the model that implemented it.
- Mocked, skipped or xfailed tests are not equivalent to real acceptance. Record all counts and reasons.
- For isolation work, distinguish unit tests, fake process tests, namespace/bwrap development tests and real Firecracker/KVM acceptance.
- For cross-platform work, record target triple, host OS and actual clean-machine result for each target.

## 3. Required implementation report

    # Handoff: WF2-XXX

    ## Result
    Status: IMPLEMENTED_UNVERIFIED or BLOCKED
    Base SHA:
    Result SHA:
    Agent/model:
    Reviewer:

    ## Behavior delivered
    User-visible and system-level behavior, including what is not delivered.

    ## Files changed
    | Path | Change | Reason |
    |---|---|---|

    ## Contracts and invariants
    - Governing ADRs:
    - Contracts/version:
    - Security boundaries preserved:
    - Privacy/data-flow impact:
    - Tenant scope:
    - Compatibility preserved:

    ## Validation
    | Command | Exit | Passed | Failed | Skipped | Not run | Environment |
    |---|---:|---:|---:|---:|---:|---|

    ## Negative-path evidence
    Each attack/failure input, expected behavior, observed result and artifact reference.

    ## Operational proof
    Startup, cancellation, restart, retry, idempotency, teardown and rollback as relevant.

    ## Review findings
    | Severity | File/line | Finding | Reproduction | Resolution |
    |---|---|---|---|---|

    ## Risks and limitations
    What is not proven, unavailable hardware, skipped gates and required owner decisions.

    ## Follow-up tasks
    Exact task IDs or none.

## 4. Status transitions

- NOT_STARTED → READY only after dependencies, owner, path scope and acceptance are explicit.
- READY → IN_PROGRESS only after base SHA/worktree are recorded and baseline is run.
- IN_PROGRESS → IMPLEMENTED_UNVERIFIED only after code is committed and handoff is complete.
- IMPLEMENTED_UNVERIFIED → VERIFIED only after independent review and mandatory tests pass.
- VERIFIED → ACCEPTED only after human approval.
- Any active state may become BLOCKED with exact evidence and reason.
- DEFERRED and REJECTED require a recorded decision.

A mandatory test that is skipped, mocked or not run cannot silently count as a pass. If the gate requires real hardware and that hardware is unavailable, the task remains blocked for that acceptance dimension.
