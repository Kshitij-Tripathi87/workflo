# Owner review checklist (security-critical steps)

Review the diff, not the summary. For each item mark pass or fail in docs/reviews/Sxx.md.

1. No docker.sock mount, no --privileged, no host path bind-mounts, no host env passthrough.
2. Egress denial is tested and the canary result is stored as evidence. A failed canary aborts the run.
3. Teardown is verified by querying labeled resources, not by trusting the remove command.
4. Receipts and evidence derive runtime_type, backend version and image digest from the backend that ran.
5. ToolGateway denies by default: allowlisted host only, method/path allowlist, call and byte budgets, no redirects off-host, every call logged by hash.
6. Judge contains no LLM call and no import of the model provider. Confirmed requires two reproductions and a clean control.
7. Findings reference only evidence ids that exist in the manifest.
8. No prompt or source body in logs or diagnostics.
9. Every failure path maps to the correct exit code and has a test.
10. No test was skipped, xfailed or weakened in this step.

Sign-off: add `APPROVED-BY: owner` and the date at the bottom of docs/reviews/Sxx.md.
