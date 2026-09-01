# Workflo

**Privacy-first autonomous QA agent.** Run tests in isolated sandboxes. Get cryptographic receipts you can verify.

---

## Installation

```bash
# Package registry
pnpm add -D @workflo/qa

# Standalone CLI
curl -L https://releases.your-workflo-domain.com/cli/latest -o workflo
chmod +x workflo

# Container image
docker pull registry.your-workflo-domain.com/workflo/agent:latest
```

---

## Usage

```bash
# Run tests in current workspace
workflo run --tests

# Run tests from a remote repository
workflo --repo https://github.com/owner/repo --tests

# Run with security scanning (SAST, dependencies, secrets)
workflo --repo https://github.com/owner/repo --tests --security

# Target specific environment
workflo run --tests --environment staging

# Generate receipt for verification
workflo run --tests --receipt

# Verify and open a receipt
workflo verify wf://receipts/0ec7-9b20
```

---

## Flags

| Flag | Description |
|------|-------------|
| `run --tests` | Execute tests in current workspace |
| `--repo <url>` | Clone and test a remote repository |
| `--security` | Enable security scanning (SAST, dependencies, secrets) |
| `--receipt` | Generate cryptographic receipt |
| `--environment <name>` | Target environment (staging, production, etc.) |
| `verify <receipt-uri>` | Validate and open receipt in console |

---

## License

MIT