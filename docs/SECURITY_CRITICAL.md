# Security-critical paths (owner review required)

Maintained by tasks/S01.md; review rules live in docs/review-checklist.md.
One repo-relative path per line. Blank lines and lines starting with `#`
are ignored. A directory entry covers everything beneath it.

Changes to these paths require `docs/reviews/<Sxx>.md` containing the line
`APPROVED-BY: owner` in the same step commit. The gate lives in
`scripts/ci/check_security_review.py` and runs as a required CI job.

## Sandbox backends and probes
packages/sandbox-runtime
packages/sandbox-isolation
packages/sandbox
apps/sandbox-executor
packages/probe-engine

## ToolGateway
packages/tool-gateway

## Evidence ledger and receipts
packages/notary
packages/events

## Judge
packages/judge
