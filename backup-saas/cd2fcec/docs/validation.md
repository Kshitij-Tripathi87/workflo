# Architecture Review Pipeline (validate-phase2)

A sandboxed, LLM-assisted architecture review tool that clones a repository,
runs automated quality gates, feeds the diff and key context files to a
fine-tuned Qwen model via vLLM, and emits structured findings as Markdown,
JSON, SARIF, and HTML reports.

## Pipeline Flow

```
 ┌──────────┐    ┌──────────────┐    ┌─────────┐    ┌──────────┐    ┌──────────┐
 │  Clone   │───>│  Baseline &  │───>│  Gates  │───>│  vLLM    │───>│ Reports  │
 │  (shallow)│    │  diff        │    │         │    │  review  │    │ md/json/ │
 └──────────┘    └──────────────┘    └─────────┘    └──────────┘    │ sarif/html│
                                                                      └──────────┘
```

1. **Clone** — shallow clone (`--depth=50`) of the target repo into a temp dir.
2. **Baseline** — merge-base of `origin/main` and `HEAD` (falls back to `HEAD~1`
   on shallow clones). The diff from baseline to HEAD is the review scope.
3. **Gates** — automated checks (import-check, pytest). If any gate fails, LLM
   analysis is skipped and the reports contain only gate results.
4. **LLM review** — the diff + 12 key context files are rendered into a Jinja2
   prompt and sent to a vLLM-hosted OpenAI-compatible endpoint. The model
   returns structured JSON findings.
5. **Reports** — the `ValidationResult` dataclass is passed to format-specific
   reporters that write deterministic output files.

## Quick Start

```bash
# Install (editable, from repo root)
pip install -e ./apps/validation-cli

# Run against the current repo
validate-phase2 --repo . --output ./reports

# Run against a remote repo with a specific model endpoint
validate-phase2 \
  --repo https://github.com/your-org/your-repo.git \
  --model-endpoint https://your-vllm.example.com/v1 \
  --model Qwen/Qwen2.5-Coder-7B-AWQ \
  --flags architecture,security,jwt \
  --formats sarif,md,json,html \
  --output ./reports
```

## CLI Reference

| Option | Default | Description |
|---|---|---|
| `--repo` | *(required)* | Repository URL or local path to validate. |
| `--baseline` | auto | Manual baseline commit hash. Auto-computed from merge-base if omitted. |
| `--model-endpoint` | `http://localhost:8000/v1` | vLLM / OpenAI-compatible endpoint URL. Env: `MODEL_ENDPOINT`. |
| `--model` | `Qwen/Qwen2.5-Coder-7B-AWQ` | Model name for analysis. Env: `MODEL_NAME`. |
| `--flags` | `architecture,patterns` | Comma-separated review flags (see below). |
| `--formats` | `md,json,sarif,html` | Comma-separated output formats. |
| `--output` | `./reports` | Output directory for report files. |
| `--venv-python` | *(current)* | Python interpreter for running gates. |

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | All gates passed, no critical/high findings. |
| 1 | Gate failure, or critical/high findings detected. |
| 2 | Invalid CLI arguments (unknown flag/format). |

## Review Flags

Flags control which review categories the LLM prompt includes. Multiple flags
can be comma-separated.

| Flag | Review focus |
|---|---|
| `architecture` | Module boundaries, dependency direction, separation of concerns, DRY violations. |
| `patterns` | Inconsistent error handling, hidden coupling, shared globals. |
| `oauth-correctness` | OAuth 2.0 / RFC 8628 Device Authorization Grant protocol correctness. |
| `jwt` | JWT claim design (sub, email, org, workspace, exp/iat, iss/aud, no PII). |
| `async-patterns` | No sync DB I/O in async handlers, no blocking calls, proper await/commit. |
| `security` | Password hashing (Argon2id), secrets handling, authz checks, rate limiting. |

## Gates

| Gate | Command | Timeout |
|---|---|---|
| `import-check` | `python -c "from app.main import create_app; print('OK')"` | 60s |
| `pytest` | `python -m pytest apps/control-plane/tests apps/workflo-cli/tests packages/cortex-auth/tests` | 300s |

Gates run inside the cloned repo directory using the system Python (or
`--venv-python` if specified). Gate failures do not crash the pipeline —
they are recorded in the `ValidationResult` and the reports are still written.

## Report Formats

All reporters are deterministic (no LLM calls) and produce a single file
named `validation_report.<ext>` in the output directory.

| Format | Extension | Use case |
|---|---|---|
| `md` | `.md` | Human-readable executive summary with severity badges, gates table, findings detail. |
| `json` | `.json` | Full machine-readable summary (`to_summary_dict()` output). |
| `sarif` | `.sarif` | SARIF 2.1.0 for GitHub Code Scanning upload. |
| `html` | `.html` | Self-contained single-file page with dark/light mode support, collapsible findings. |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MODEL_ENDPOINT` | `http://localhost:8000/v1` | vLLM endpoint URL. Overrides the `--model-endpoint` default. |
| `MODEL_NAME` | `Qwen/Qwen2.5-Coder-7B-AWQ` | Model name. Overrides the `--model` default. |

## Infrastructure Setup

The pipeline is designed to run on **Oracle Cloud Free Tier** (ARM Ampere A1,
24 GB RAM) with vLLM serving a quantized Qwen model, behind a Cloudflare
Tunnel for zero-cost HTTPS.

### 1. Bootstrap the Oracle instance

```bash
# On a fresh Ubuntu 22.04 ARM instance:
bash infra/oracle/setup.sh
```

This script installs Docker, pulls the vLLM image, starts the model, sets up
a Cloudflare Quick Tunnel, and installs the validation CLI via pipx.

### 2. vLLM service

The vLLM service is defined in `infra/vllm/docker-compose.yml`:

- **Image**: `vllm/vllm-openai:latest-arm64`
- **Model**: `Qwen/Qwen2.5-Coder-7B-AWQ` (drop-in placeholder for Qwen3-9B-AWQ)
- **Port**: 8000 (exposed via Cloudflare Tunnel, not directly)
- **Max context**: 32,768 tokens
- **GPU memory**: 85% utilization

To swap to a different model, change the `--model` argument in the compose
file and restart:

```bash
docker compose -f infra/vllm/docker-compose.yml up -d --force-recreate
```

### 3. Configure the endpoint

After `setup.sh` completes, it prints a Cloudflare Tunnel URL. Set it as an
environment variable:

```bash
export MODEL_ENDPOINT=https://<tunnel-url>.trycloudflare.com/v1
```

For stable URLs, configure a named Cloudflare Tunnel with a DNS record.

## CI/CD Integration

The workflow at `.github/workflows/validate.yml` runs the architecture review
on every push and pull request to `main`/`master`.

### What it does

1. Checks out the repo with full history (`fetch-depth: 0`).
2. Installs the validation CLI and gate dependencies.
3. Runs `validate-phase2 --repo . --output ./reports`.
4. Uploads the SARIF file to GitHub Code Scanning (`category: validate-phase2`).
5. Uploads all report files as a workflow artifact.
6. Fails the job if the validation found critical/high issues or gate failures.

### Prerequisites

- **`VLLM_ENDPOINT` secret** (optional): Set this to your vLLM endpoint URL
  (e.g., the Cloudflare Tunnel URL). If not set, the pipeline still runs gates
  and produces reports — the LLM call will fail gracefully and findings will
  be empty.

### Viewing results

- **Code Scanning**: Findings appear under the "Security" tab in GitHub,
  categorized as `validate-phase2`.
- **Artifacts**: Download the `validation-reports` artifact to view the
  Markdown, JSON, and HTML reports locally.

## Architecture Details

### Data model

```
ValidationResult
├── repo: str               # repo URL or path
├── baseline: str           # merge-base commit hash
├── head: str                # HEAD commit hash
├── flags: list[str]        # review flags used
├── model: str              # model name
├── started_at: str         # ISO 8601 timestamp
├── finished_at: str        # ISO 8601 timestamp
├── gates: list[GateResult] # gate execution results
├── findings: list[Finding] # LLM-generated findings
├── notes: str              # overall assessment or error message
├── all_gates_passed: bool  # property: all gates passed
└── severity_counts: dict   # property: {critical, high, medium, low, info}
```

### Context files

The orchestrator collects 12 key context files (truncated to 6,000 chars each)
to give the LLM full architectural context:

- `apps/control-plane/app/api/v1/auth.py`
- `apps/control-plane/app/api/oauth.py`
- `apps/control-plane/app/api/v1/key_provisioning.py`
- `apps/control-plane/app/core/security.py`
- `apps/control-plane/app/core/crypto.py`
- `apps/control-plane/app/db/models.py`
- `apps/control-plane/app/main.py`
- `apps/control-plane/app/core/config.py`
- `apps/workflo-cli/src/workflo_cli/main.py`
- `apps/workflo-cli/src/workflo_cli/auth_commands.py`
- `packages/cortex-auth/src/cortex_auth/session.py`
- `packages/cortex-auth/src/cortex_auth/client.py`

### Prompt template

The Jinja2 prompt template at `validate_phase2/prompts/architecture_review.j2`
conditionally includes review sections based on the selected flags, then
appends the diff and context files, and specifies a strict JSON output format.

The LLM response is parsed with fence tolerance (strips ```` ```json ````
fences, extracts the first `{...}` block if direct JSON parsing fails).
