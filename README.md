# Workflo — Autonomous QA & Verification Agent

> **Privacy-first autonomous QA agent.** Run tests in isolated network-blocked Docker sandboxes and get verifiable cryptographic receipts proving teardown.

---

## ⚡ CLI Installation Methods

You can install and run the `workflo` CLI using any of the following methods:

### 1. Automated Unix / macOS Installer (`install.sh`)
Recommended for Linux, macOS, and Git Bash users working in the repository.

```bash
# Run the automated installer
./install.sh

# Activate the isolated virtual environment
source .workflo-venv/bin/activate

# Verify installation
workflo --version
```

---

### 2. Automated Windows PowerShell Installer (`install.ps1`)
Recommended for Windows developers.

```powershell
# Run the installer in PowerShell
powershell -ExecutionPolicy Bypass -File .\install.ps1

# Activate the virtual environment
.\.workflo-venv\Scripts\Activate.ps1

# Verify installation
workflo --version
```

---

### 3. NPM Package (`@workflo/qa` / `npx`)
For JavaScript and TypeScript environments:

```bash
# Global installation
npm install -g @workflo/qa

# Or add as project dev dependency
pnpm add -D @workflo/qa
# yarn add -D @workflo/qa

# Or run directly via npx without installing
npx @workflo/qa run --tests
```

---

### 4. Manual Python / `pip` Installation (Python 3.11+)
For custom virtual environments:

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate    # Linux / macOS
# .venv\Scripts\Activate.ps1 # Windows

# 2. Install monorepo packages in dependency order
pip install -e packages/workflo-schema \
            -e packages/sandbox-isolation \
            -e apps/sandbox-executor \
            -e packages/probe-engine \
            -e packages/cortex-auth

# 3. Install the Workflo CLI
pip install -e apps/workflo-cli

# 4. Verify
workflo --help
```

---

### 5. Standalone Binary & Docker Container

#### Standalone Binary (Linux / macOS)
```bash
curl -L https://releases.your-workflo-domain.com/cli/latest -o workflo
chmod +x workflo
sudo mv workflo /usr/local/bin/
```

#### Container Image
```bash
docker pull registry.your-workflo-domain.com/workflo/agent:latest
docker run --rm -v $(pwd):/workspace workflo/agent run --tests --security
```

---

## 🚀 Quickstart & Usage

```bash
# 1. Run tests in the current workspace
workflo run --tests

# 2. Run tests on a remote repository with security scanning
workflo run --repo https://github.com/pallets/click.git --tests --security

# 3. Run AI agent deep test with live application execution
workflo run --repo https://github.com/pallets/click.git --deep-test --security

# 4. Target a specific environment
workflo run --tests --environment staging

# 5. Generate a cryptographic receipt
workflo run --tests --receipt

# 6. Independently verify a signed execution receipt
workflo verify wf://receipts/0ec7-9b20
```

---

## 🚩 CLI Flags Reference

| Command / Flag | Description |
|---|---|
| `run --tests` | Execute test suite in an isolated sandbox |
| `--repo <url>` | Clone and execute tests against a remote git repository |
| `--security` | Enable security scanning (SAST, dependencies, secret detection) |
| `--deep-test` | Enable AI tool-calling agent to exercise routes and live endpoints |
| `--receipt` | Generate a signed cryptographic execution receipt (`wf://receipts/...`) |
| `--environment <name>` | Target environment (`dev`, `staging`, `production`) |
| `--dry-run` | Validate run spec and policies without booting Docker containers |
| `auth login` | Authenticate using OAuth 2.0 Device Flow (RFC 8628) |
| `verify <receipt-uri>` | Validate cryptographic signatures and inspect teardown proof |

---

## 🏗️ Repository Architecture

- **`apps/workflo-cli/`** — Click-based CLI entrypoint (`workflo run`, `workflo auth`, `workflo verify`)
- **`apps/control-plane/`** — FastAPI SaaS control plane with OAuth 2.0 device flow and worker fleet management
- **`apps/sandbox-executor/`** — Docker + tmpfs container isolation and outbound canary network verification
- **`apps/worker-engine/`** — Isolated Pytest runner, Playwright web probes, and AI tool-calling agent
- **`packages/workflo-schema/`** — Shared Pydantic v2 models (`RunSpec`, `TestResult`, `SignedReceipt`)
- **`packages/sandbox-isolation/`** — Ephemeral tmpfs lifecycle, network isolation policies, and receipt signer
- **`packages/probe-engine/`** — Security probes, contract test generator, and web probe runner
- **`packages/workflo-datahub/`** — DataHub metadata integration (GraphQL + MCP client)
- **`packages/npm-workflo/`** — Global npm shim package (`@workflo/qa`)
- **`client/`** — Interactive 3D WebGL (Three.js + React 19) sandbox dashboard and console
- **`backend/`** — Full FastAPI backend with impact scoring, policy engine, and RAG context store

---

## 🔒 Privacy & Verifiable Teardown

Workflo operates on a zero-retention guarantee:
1. **Network-Blocked Execution:** Runs inside isolated containers with `--network none`.
2. **Ephemeral Storage:** Mounts filesystems on `tmpfs` RAM-disks that are unmounted and wiped upon test completion.
3. **Outbound Canary Check:** Proactively tests for isolation leaks — any successful outbound connection immediately fails the run.
4. **Cryptographic Proofs:** Generates signed receipts containing SHA-256 parameter hashes, execution durations, and container destruction proofs.

---

## 📄 License

MIT / Apache 2.0 — see [LICENSE](LICENSE) for details.
