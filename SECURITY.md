# Security Policy

## Reporting a vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report privately via **GitHub Security Advisories**:
`https://github.com/Kshitij-Tripathi87/workflo/security/advisories/new`
(Repository → Security → Report a vulnerability).

Include as much of the following as you can:

- affected component and version (commit SHA if not a release);
- reproduction steps or a minimal proof of concept;
- impact (what an attacker gains, which trust boundary is crossed);
- any suggested fix or mitigation.

You should receive an acknowledgement within **3 business days** and a status
update within **10 business days**. Valid reports are handled through
coordinated disclosure: we will agree a disclosure date with you before any
public write-up, and credit you in the advisory unless you prefer otherwise.

Good-faith research conducted within this policy is welcomed. We will not
pursue legal action against researchers who:

- avoid privacy violations, destruction of data, and service disruption;
- only interact with accounts you own or with explicit permission;
- do not use exploits beyond what is needed to demonstrate the issue;
- report findings promptly and keep them confidential until coordinated.

## Scope

In scope: the Workflo CLI (`apps/workflo-cli`), control plane
(`apps/control-plane`), worker host (`worker/`), guest runtime
(`apps/worker-engine`), sandbox packages (`packages/sandbox-*`), receipt and
evidence verification (`packages/workflo-schema`), GitHub Actions workflows,
and install scripts (`install.sh`, `install.ps1`, `action/`).

Out of scope: denial-of-service against hosted endpoints, social engineering,
physical attacks, and vulnerabilities in third-party dependencies that have
not been demonstrated to affect Workflo's trust boundaries.

## Supported versions

Workflo is pre-release. Security fixes land on `main`; there are no maintained
release branches yet. Always build from the current `main` commit.

## Security engineering references

- Threat model, isolation profiles and the security acceptance matrix:
  `docs/adr/ADR-0022-microvm-boundary.md` and the blueprint security spec
  (reviewed in `BLUEPRINT_ENGINEERING_REVIEW.md`).
- Runtime honesty rules: unproven security conditions fail closed; a cleanup
  command returning success is not teardown evidence (ADR-0022).
- CI security gates: `.github/workflows/security-scan.yml` (bandit
  medium+ findings and hardcoded-credential patterns fail the build),
  dependency updates via `.github/dependabot.yml`.
