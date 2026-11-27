# Workflo engineering implementation package

This package contains the master implementation plan, eight companion specifications, and the product/market strategy. It incorporates findings F1–F6 from the repository-grounded engineering review merged in PR #26.

## Documents

| File | Purpose |
|---|---|
| `00-master-implementation-plan.md` | Product scope, architecture decisions, end-to-end goals, implementation phases and gates |
| `01-system-architecture.md` | Component boundaries, run lifecycle, control/data planes, contracts and trust model |
| `02-platform-sandbox-security.md` | Threat model, Linux/Windows/macOS runtime boundaries, isolation and teardown requirements |
| `03-inference-provider-privacy.md` | Cloud/local provider abstraction, settings, credential handling and source privacy |
| `04-cli-and-configuration.md` | CLI commands, configuration hierarchy, profiles, exit codes and distribution |
| `05-web-app-and-runner.md` | Website vs web app, dashboard, customer runner, APIs and UX flows |
| `06-testing-and-acceptance.md` | Test layers, adversarial matrix, real-platform gates and release acceptance |
| `07-backlog-and-milestones.md` | Dependency-ordered work breakdown, phases, owners and done criteria |
| `08-open-decisions-and-ADRs.md` | Decisions, unresolved questions, proposed ADRs and ratification gates |
| `09-product-market-strategy.md` | Product positioning, customers, competition, market sizing and commercialization |

## Reading order

Start with `00-master-implementation-plan.md`, then read specifications 01–08 in numerical order. Use the product/market strategy as supporting context, not as an implementation authority.

## Repository review baseline

The documentation review and F1–F6 corrections are based on `main` at `e864c42a160cc85638d0763574814d3aaeeac933` (merge of PR #26). No claim is made that the implementation tasks in these specifications are already complete.

## Important status note

These are proposed engineering specifications based on the inspected Workflo repository snapshot. They are not proof that the described capabilities are implemented or production-ready. The master plan identifies repository assumptions, open decisions and acceptance gates. Changes to implementation must be validated against the current `main` branch before execution.
