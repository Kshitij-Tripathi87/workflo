# Contributing to Cortex Autopilot

Thank you for your interest in contributing. Cortex Autopilot is an
open-source project under the Apache 2.0 license and we welcome
contributions from the community.

## Code of Conduct

We expect all contributors to be respectful, constructive, and
collaborative. Disagreements happen — that's fine. Personal attacks
are not.

## How to Contribute

There are several ways to contribute, in increasing order of effort:

1. **Report a bug.** Open a GitHub issue with the `bug` template.
2. **Suggest a feature.** Open a GitHub issue with the `feature_request` template.
3. **Improve documentation.** Submit a PR with doc fixes.
4. **Add a connector.** See [`docs/connectors.md`](./connectors.md) for the SDK.
5. **Improve the engine.** Submit a PR with new ranking algorithms or
   optimization techniques.
6. **Add a policy template.** Submit a PR with new example policies.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker
- Git

### Clone the repo

```bash
git clone https://github.com/cortex-autopilot/cortex-autopilot.git
cd cortex-autopilot
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run tests
pytest

# Run linting + typecheck
ruff check .
mypy app
```

### Frontend

```bash
cd frontend
npm install

# Run dev server
npm run dev

# Run lint + typecheck
npm run lint
npm run typecheck
```

### One-command setup

If you just want to try it:

```bash
./setup.sh
```

This brings up the full stack in Docker.

## Adding a New Connector

See [`docs/connectors.md`](./connectors.md) for the SDK. The general
process:

1. Create a new directory under `backend/app/connectors/<name>/`.
2. Implement `BaseConnector` in `connector.py`.
3. Implement the parser in `parser.py` (if reading from disk) or
   `client.py` (if reading from an external service).
4. Implement a config loader in `config.py`.
5. Register with `register("<name>", MyConnector)` at module bottom.
6. Add tests under `backend/tests/test_<name>_connector.py`.
7. Update `docs/connectors.md` with a section for your connector.

## Pull Request Process

1. **Open an issue first** for non-trivial changes. Maintainers can
   tell you upfront whether the change fits the roadmap.
2. **Fork the repo** and create a feature branch.
3. **Write tests** for new behavior. We require ≥ 80% coverage on new
   code.
4. **Run the full test suite** locally before pushing.
5. **Update documentation** if you change behavior.
6. **Reference the issue** in your PR description.
7. **Wait for review.** A maintainer will review within 5 business days.

## Coding Conventions

### Python

- **Line length:** 100 chars (set in `pyproject.toml`).
- **Type hints:** required on all new code.
- **Docstrings:** required on all public functions.
- **Naming:** snake_case for functions/variables, PascalCase for classes.
- **Imports:** use `isort` ordering (handled by `ruff`).
- **Async:** all I/O is async. Use `httpx.AsyncClient`, not `requests`.

### TypeScript

- **Strict mode** is enabled.
- **No `any`** unless absolutely necessary.
- **Naming:** camelCase for variables/functions, PascalCase for types/components.
- **Component style:** functional components with hooks.

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add BigQuery connector
fix: handle missing catalog.json gracefully
docs: clarify policy hierarchy in cortex.md
test: add test for severity calibration
chore: bump dbt-core to 1.5
```

## Adding a Connector to the Engine (Process)

We accept new built-in connectors when:

1. **3 distinct customers** have asked for it (see
   [`docs/business/feature_requests.md`](./business/feature_requests.md)).
2. **A community contributor** submits a PR with tests + docs.
3. **The connector author** agrees to maintain it for at least 6 months.

If you want a connector that's not on the list, the easiest path is
to write it as a community connector (under
`backend/app/connectors/community/`) and submit a PR.

## Releases

- **Patch releases** (`0.3.1`) — bug fixes, weekly.
- **Minor releases** (`0.4.0`) — new features, monthly.
- **Major releases** (`1.0.0`) — breaking changes, quarterly.

We follow [Semantic Versioning](https://semver.org/).

## Security

Report security vulnerabilities to `security@cortex.dev` (private
email). Do not open a public GitHub issue for security bugs.

## License

By contributing, you agree that your contributions will be licensed
under the Apache 2.0 license, matching the project's license.
