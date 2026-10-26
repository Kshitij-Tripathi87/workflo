# Judge (deterministic, security-critical)

**Purpose:** decide what is real. **Why:** a convincing explanation of a bug that does not exist is the failure mode of AI QA. The Judge is plain code and the only authority on status.

**Input:** Candidate. **Output:** Finding.

## Algorithm
1. Replay the candidate request twice against fresh app state (restart or reset hook if configured).
2. Run a healthy-control request that should succeed. If the control fails, the app is unhealthy: mark Unconfirmed with reason `unhealthy_control`.
3. Status: both reproduce = Confirmed; one = Flaky; none = Unconfirmed.
4. Fingerprint = hash(kind, normalized request, normalized observed). Dedup on fingerprint.
5. Confidence from reproduction counts and control health. Severity from rule table, not a model.
6. Attach evidence refs for each reproduction and the control. Refs must exist in the manifest.

## Hard rules
- No LLM call, no import of the model provider, no network access except through the sandbox app URL.
- A Finding is immutable once written.

## Acceptance tests
Static check that the package does not import the provider; Confirmed needs two repro refs plus a control ref; flaky fixture yields Flaky; unhealthy control yields Unconfirmed; dedup merges identical candidates.
