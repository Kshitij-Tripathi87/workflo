# Engineering task contract and handoff template

Every non-trivial task assigned to any of the five agents must use this contract. Do not issue broad natural-language requests without scope, acceptance criteria and path ownership.

## 1. Task template

    task_id: WF-XXXX
    title: short action-oriented title
    status: READY
    priority: P0 | P1 | P2 | P3

    owner:
      agent: Gemini | DeepSeek | MiniMax | GLM | GPT-6 Luna
      exact_model_id: exact provider/model version
      reviewer: named different agent
      human_approver: project owner

    baseline:
      repository: Kshitij-Tripathi87/workflo
      base_sha: full immutable commit SHA
      branch: task-specific branch
      worktree: isolated path

    context:
      product_boundary: Workflo Trust MVP
      governing_docs: exact ADR/spec/status paths
      current_behavior: observed behavior with source references
      prior_attempts: known relevant work

    objective:
      required_outcome: one verifiable outcome
      user_impact: why it matters

    allowed_paths:
      - exact/path/one
      - exact/path/two

    forbidden_paths:
      - exact/path/secret-or-sensitive
      - exact/path/out-of-scope

    interfaces:
      public_contracts: affected APIs/schemas/CLI
      compatibility: behavior that must remain stable
      migration: required versioned migration or none

    constraints:
      security_invariants: list
      performance_limits: list or unknown
      dependencies: existing approved dependencies only
      no_go: explicit operations the agent cannot perform

    implementation_plan:
      - inspect existing implementation
      - propose minimal design
      - implement
      - test
      - handoff

    acceptance:
      functional:
        - observable expected result
      negative:
        - prohibited behavior must fail
      regression:
        - existing behavior that must remain
      security:
        - trust boundaries and proof required

    required_tests:
      unit: exact test modules/commands
      integration: exact test modules/commands
      security: exact negative tests
      system: exact end-to-end checks

    evidence:
      expected_artifacts:
        - test logs
        - changed-file list
        - reports
        - hashes if applicable

    handoff:
      report_path: agent-workspace/agents/<owner>/handoffs/<task-id>.md
      status_allowed: IMPLEMENTED_UNVERIFIED | VERIFIED | BLOCKED

## 2. Task design rules

- The objective must describe observable behavior, not an implementation preference.
- Allowed paths must be exact enough to prevent repository-wide accidental refactoring.
- Acceptance criteria must be executable or independently inspectable.
- Positive and negative paths are both required for security-relevant behavior.
- Every task needs a baseline SHA and a clean worktree.
- A task should normally change one component boundary. Cross-component work needs an integration plan.
- Do not add a dependency unless the contract names the reason, licence, version and security review.
- Do not make an ADR decision in code. Proposed decisions need an ADR and owner ratification.
- No ticket can define itself as passed by the same model that implemented it.
- A test that is skipped, xfailed, mocked or not executed is not a passed real-world security test. Record exact counts and reasons.
- For Linux/KVM work, distinguish unit tests, mocked tests, namespace/bwrap development tests and real Firecracker/KVM acceptance.

## 3. Required implementation report

    # Handoff: WF-XXXX

    ## Result
    Status: IMPLEMENTED_UNVERIFIED or VERIFIED
    Base SHA:
    Result SHA:
    Agent/model:
    Reviewer:

    ## Summary
    What changed and what user-visible/system behavior it enables.

    ## Files changed
    | Path | Change | Reason |
    | --- | --- | --- |

    ## Design and invariants
    - Governing ADRs:
    - Contracts affected:
    - Security boundaries preserved:
    - Compatibility preserved:

    ## Validation
    | Command | Exit code | Passed | Failed | Skipped | Notes |
    | --- | ---: | ---: | ---: | ---: | --- |

    ## Negative-path evidence
    List each tested failure path and outcome. Do not replace evidence with assertion.

    ## Review findings
    | Severity | Finding | Evidence | Resolution |
    | --- | --- | --- | --- |

    ## Risks and limitations
    State what is not proven.

    ## Follow-up tasks
    Exact task IDs or "none".

## 4. State transitions

- NOT_STARTED → READY only after prerequisites, scope and owner are explicit.
- READY → IN_PROGRESS only after base SHA and worktree are recorded.
- IN_PROGRESS → IMPLEMENTED_UNVERIFIED only after code is committed and handoff is complete.
- IMPLEMENTED_UNVERIFIED → VERIFIED only after independent review and required deterministic tests pass.
- VERIFIED → ACCEPTED only after human approval.
- Any active state may transition to BLOCKED with evidence and reason.
- DEFERRED and REJECTED require a recorded decision.

No task moves to VERIFIED if a mandatory test was skipped or if a critical acceptance criterion is not demonstrated.
