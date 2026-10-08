# Cortex Autopilot — Policy Authoring Guide

Policies are declarative YAML rules that gate every data change. They
turn advisory impact analysis into enforcement — the difference between
a tool that *describes* the problem and one that *prevents* it.

## How Policy Evaluation Works

When the engine computes a `FuturePlan`, it returns a `ranked_choice`
with `predicted_severity`, `predicted_blast_radius`, and a `has_owner`
flag (derived from the asset graph). The policy engine takes those
values plus your policy list and returns a verdict:

```
verdict = block if any policy.action == block fired
        = warn  if any policy.action == warn  fired (and no block)
        = pass  otherwise
```

`block` always dominates `warn` which always dominates `pass`.

## The `cortex.yml` Format

The simplest possible config:

```yaml
# cortex.yml
asset_urn: "urn:dbt:model:jaffle_shop:orders"

policies:
  - name: Block critical-severity changes
    max_severity: 75
    action: block

objective: minimize incident risk
```

### Top-level fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `asset_urn` | string | yes | Cortex URN of the asset being changed. Required unless provided via the GitHub Action's `schema_change` input. |
| `change` | object | no | Default change description. The action auto-detects from the PR diff if omitted. |
| `policies` | array | no | Policy list (see below). |
| `objective` | string | no | Ranking objective: `minimize incident risk` (default), `minimize effort`, `maximize reliability`, `balance cost and risk`. |

### Policy fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | `"default"` | Human-readable policy name. Shown in PR comments and Slack alerts. |
| `max_severity` | number | — | Block/warn when `predicted_severity > max_severity`. |
| `max_blast_radius` | number | — | Block/warn when `predicted_blast_radius > max_blast_radius`. |
| `require_owner` | boolean | `false` | Block/warn when the asset has no assigned owner. |
| `action` | string | `"block"` | `pass`, `warn`, or `block`. What verdict to emit when the policy fires. |

## Example Policy Sets

### Strict (recommended for early adoption)

```yaml
policies:
  - name: Block critical-severity changes
    max_severity: 75
    max_blast_radius: 10
    action: block

  - name: Require an owner on every critical asset
    require_owner: true
    action: block
```

### Permissive (good for staged rollout)

```yaml
policies:
  - name: Warn on any non-trivial blast radius
    max_blast_radius: 5
    action: warn

  - name: Block only on critical severity
    max_severity: 90
    action: block
```

### Environment-specific

You can override policies per branch via the GitHub Action's `policy`
input — useful for `main` being strict and feature branches being
permissive:

```yaml
# .github/workflows/cortex-gate.yml
- uses: cortex-autopilot/impact-gate@v1
  with:
    policy: |
      - name: Override for hotfix branches
        max_severity: 95
        action: block
```

## Policy Resolution Hierarchy

The Impact Gate evaluates policies in this priority order:

1. **Inline action input** — `with: policy: <yaml>` (highest priority).
2. **Repo `cortex.yml`** — committed at the repo root.
3. **Backend defaults** — fetched from `GET /policy/defaults`.

If layer 1 is provided, layers 2 and 3 are ignored. Same for 2 vs 3.
This makes per-PR overrides possible without forcing the user to
update `cortex.yml`, while still allowing teams to ship a baseline
that applies to every PR.

## What Makes a Good Policy

### Do

- **Start permissive, then tighten.** Begin with `warn` only. Once you
  trust the verdicts, switch to `block`.
- **Tie thresholds to severity bands.** Severity is on a 0–100 scale:
  - 0–24 = low
  - 25–49 = medium
  - 50–74 = high
  - 75–100 = critical

  Reasonable block threshold: `max_severity: 75`. Reasonable warn:
  `max_severity: 50`.
- **Require owners on gold assets.** `require_owner: true` is a low-cost
  high-impact rule.
- **Review the policy every quarter.** Schema graphs grow; the right
  threshold today will be wrong in 6 months.

### Don't

- **Don't block on `max_blast_radius: 0`.** That's "any change breaks
  something" and will frustrate your team.
- **Don't use `pass` as a policy action.** A `pass` action means the
  policy never fires.
- **Don't write more than 5 policies.** Beyond that, the team will
  lose track of which rule fired.
- **Don't conflate *severity* with *blast radius*.** A small change on
  a critical asset has high severity but small blast radius. A large
  change on a non-critical asset has low severity but big blast radius.

## Tweak Loop (Real-Time Verdict)

The frontend includes a **Policy Tweaker** that lets you slide
`max_severity` and `max_blast_radius` values and watch the verdict
flip in real time. This is the easiest way to tune your policies
before committing them to `cortex.yml`.

You can also do this via the API:

```bash
curl -X POST http://localhost:8000/policy/validate \
  -H "Content-Type: application/json" \
  -d '{
    "policies": [
      { "name": "Test", "max_severity": 80, "action": "block" }
    ],
    "severity": 88,
    "blast_radius": 3,
    "has_owner": true
  }'
```

Returns:

```json
{
  "verdict": "block",
  "results": [
    {
      "policy_name": "Test",
      "verdict": "block",
      "reason": "severity 88 exceeds max 80",
      "trigger_values": { "severity": 88, "blast_radius": 3, "has_owner": true }
    }
  ]
}
```

## Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `POLICY_VIOLATION` | 200 (in plan) | A policy fired — see `policy_result.verdict` |
| `POLICY_INVALID_CONFIG` | 400 | A policy field is malformed or unknown |
| `SNAPSHOT_EMPTY` | 400 | The graph snapshot has no nodes (usually a manifest path issue) |
| `CONNECTOR_MANIFEST_MISSING` | 400 | dbt manifest not found |

## Next Steps

- **Install guide:** [`docs/install.md`](./install.md)
- **Tutorial:** [`docs/tutorial.md`](./tutorial.md)
- **API reference:** [`docs/api.md`](./api.md)
- **Connectors:** [`docs/connectors.md`](./connectors.md)
