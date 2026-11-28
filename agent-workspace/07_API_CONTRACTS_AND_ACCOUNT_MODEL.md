# API contracts and account model

> **Superseded compatibility page.** This file is retained so existing links continue to resolve. It is not an implementation instruction source.

The current, authoritative Workflo engineering plan is in [docs/agent-workspace/README.md](../docs/agent-workspace/README.md).

**Read the canonical document:** [docs/agent-workspace/API-CONTRACT-FREEZE-M1.md](../docs/agent-workspace/API-CONTRACT-FREEZE-M1.md)

Use the M1 API freeze proposal and API/web contract plan. Proposed endpoints are not implemented merely because they are documented.

## Binding decisions

- The accepted language decision is [ADR-0024](../docs/adr/ADR-0024-native-go-cli-and-runner.md): Go for the native CLI and incremental customer-runner host migration. The FastAPI control plane and fit-for-purpose guest adapters remain.
- The authoritative five-agent split is three CLI agents (DeepSeek, GLM, MiniMax) and two platform agents (Gemini frontend, GPT-6 backend).
- The full model-specific plans live under [docs/agent-workspace/agents/](../docs/agent-workspace/README.md#10-agent-runbooks).
- This legacy page must not be used to assign work if it conflicts with the canonical documents above.
